from __future__ import annotations

import hashlib


def weight(word: int) -> int:
    return bin(word).count("1")


def coordinate_masks(
    first_word: int,
    second_word: int,
    *,
    length: int,
) -> tuple[int, int, int, int]:
    ambient_mask = (1 << length) - 1
    both = first_word & second_word
    first_only = first_word & (ambient_mask ^ second_word)
    second_only = second_word & (ambient_mask ^ first_word)
    neither = ambient_mask ^ (first_word | second_word)
    return both, first_only, second_only, neither


def third_descriptor(
    word: int,
    *,
    first_word: int,
    second_word: int,
    length: int,
) -> tuple[int, int, int, int]:
    return tuple(
        weight(word & mask)
        for mask in coordinate_masks(
            first_word,
            second_word,
            length=length,
        )
    )


def canonical_word(
    descriptor: tuple[int, int, int, int],
    *,
    first_word: int,
    second_word: int,
    length: int,
) -> int:
    word = 0
    masks = coordinate_masks(
        first_word,
        second_word,
        length=length,
    )
    for count, mask in zip(descriptor, masks):
        positions = [
            position
            for position in range(length)
            if mask & (1 << position)
        ]
        if count < 0 or count > len(positions):
            raise ValueError("descriptor count is outside its coordinate cell")
        for position in positions[:count]:
            word |= 1 << position
    return word


def candidate_word(
    word: int,
    case: dict[str, object],
    *,
    length: int,
) -> bool:
    if word < 0 or word >= 1 << length:
        return False
    first_word = int(case["first_word"])
    second_word = int(case["second_word"])
    if word in {0, first_word, second_word}:
        return False
    minimum_weight = int(case["minimum_weight"])
    descriptor_payload = case["second_descriptor"]
    second_descriptor = (
        int(descriptor_payload["weight"]),
        int(descriptor_payload["intersection"]),
    )
    return (
        weight(word) >= minimum_weight
        and (
            weight(word),
            weight(word & first_word),
        ) >= second_descriptor
    )


def third_orbits(
    case: dict[str, object],
    *,
    length: int,
) -> list[tuple[tuple[int, int, int, int], list[int]]]:
    first_word = int(case["first_word"])
    second_word = int(case["second_word"])
    orbits: dict[tuple[int, int, int, int], list[int]] = {}
    for word in range(1 << length):
        if not candidate_word(word, case, length=length):
            continue
        descriptor = third_descriptor(
            word,
            first_word=first_word,
            second_word=second_word,
            length=length,
        )
        orbits.setdefault(descriptor, []).append(word)
    return [
        (descriptor, orbits[descriptor])
        for descriptor in sorted(orbits)
    ]


def orbit_manifest_digest(orbits: list[dict[str, object]]) -> str:
    lines = []
    for orbit in orbits:
        descriptor = ",".join(
            str(value) for value in orbit["descriptor"]
        )
        lines.append(
            f"{descriptor}:{orbit['canonical_word']}:"
            f"{orbit['orbit_size']}:{orbit['earlier_word_count']}\n"
        )
    return hashlib.sha256("".join(lines).encode("ascii")).hexdigest()
