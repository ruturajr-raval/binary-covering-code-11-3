from __future__ import annotations

import hashlib
import itertools

from third_word_symmetry import candidate_word, third_orbits, weight


TRIPLE_CELL_ORDER = tuple(itertools.product((0, 1), repeat=3))


def triple_coordinate_masks(
    first_word: int,
    second_word: int,
    third_word: int,
    *,
    length: int,
) -> tuple[int, ...]:
    masks = []
    for signature in TRIPLE_CELL_ORDER:
        mask = 0
        for position in range(length):
            membership = (
                (first_word >> position) & 1,
                (second_word >> position) & 1,
                (third_word >> position) & 1,
            )
            if membership == signature:
                mask |= 1 << position
        masks.append(mask)
    return tuple(masks)


def fourth_descriptor(
    word: int,
    *,
    first_word: int,
    second_word: int,
    third_word: int,
    length: int,
) -> tuple[int, ...]:
    return tuple(
        weight(word & mask)
        for mask in triple_coordinate_masks(
            first_word,
            second_word,
            third_word,
            length=length,
        )
    )


def matching_compatible(
    candidate: int,
    fixed_words: tuple[int, ...],
    *,
    minimum_distance: int,
) -> bool:
    selected = (*fixed_words, candidate)
    for word in selected:
        degree = sum(
            weight(word ^ other) == minimum_distance
            for other in selected
            if other != word
        )
        if degree > 1:
            return False
    return True


def third_prefix_words(
    parent_case: dict[str, object],
    child: dict[str, object],
    *,
    length: int,
) -> list[int]:
    orbits = third_orbits(parent_case, length=length)
    orbit_index = int(child["parent_orbit_index"])
    if orbit_index < 0 or orbit_index >= len(orbits):
        raise RuntimeError("third-word child index is outside the parent")
    descriptor, words = orbits[orbit_index]
    if list(descriptor) != child["descriptor"]:
        raise RuntimeError("third-word child descriptor mismatch")
    if min(words) != int(child["canonical_word"]):
        raise RuntimeError("third-word child representative mismatch")
    if len(words) != int(child["orbit_size"]):
        raise RuntimeError("third-word child orbit size mismatch")
    earlier = [
        word
        for _, earlier_words in orbits[:orbit_index]
        for word in earlier_words
    ]
    if len(earlier) != int(child["earlier_word_count"]):
        raise RuntimeError("third-word child prefix mismatch")
    return earlier


def classify_fourth_words(
    parent_case: dict[str, object],
    child: dict[str, object],
    *,
    length: int,
    matching: bool,
) -> tuple[list[int], dict[str, int]]:
    first_word = int(parent_case["first_word"])
    second_word = int(parent_case["second_word"])
    third_word = int(child["canonical_word"])
    fixed_words = (0, first_word, second_word, third_word)
    fixed_set = set(fixed_words)
    earlier_words = set(
        third_prefix_words(
            parent_case,
            child,
            length=length,
        )
    )
    minimum_distance = int(parent_case["minimum_weight"])
    candidates = []
    counts = {
        "ambient_word_count": 1 << length,
        "fixed_word_count": 0,
        "excluded_parent_threshold_count": 0,
        "excluded_earlier_third_word_count": 0,
        "excluded_fixed_distance_count": 0,
        "excluded_matching_count": 0,
        "candidate_word_count": 0,
    }
    for word in range(1 << length):
        if word in fixed_set:
            counts["fixed_word_count"] += 1
        elif not candidate_word(word, parent_case, length=length):
            counts["excluded_parent_threshold_count"] += 1
        elif word in earlier_words:
            counts["excluded_earlier_third_word_count"] += 1
        elif any(
            weight(word ^ fixed) < minimum_distance
            for fixed in fixed_words
        ):
            counts["excluded_fixed_distance_count"] += 1
        elif (
            matching
            and not matching_compatible(
                word,
                fixed_words,
                minimum_distance=minimum_distance,
            )
        ):
            counts["excluded_matching_count"] += 1
        else:
            candidates.append(word)
            counts["candidate_word_count"] += 1
    if sum(
        value
        for key, value in counts.items()
        if key != "ambient_word_count"
    ) != counts["ambient_word_count"]:
        raise RuntimeError("fourth-word classification is not a partition")
    return candidates, counts


def fourth_orbits(
    parent_case: dict[str, object],
    child: dict[str, object],
    *,
    length: int,
    matching: bool,
) -> tuple[list[tuple[tuple[int, ...], list[int]]], dict[str, int]]:
    candidates, counts = classify_fourth_words(
        parent_case,
        child,
        length=length,
        matching=matching,
    )
    first_word = int(parent_case["first_word"])
    second_word = int(parent_case["second_word"])
    third_word = int(child["canonical_word"])
    grouped: dict[tuple[int, ...], list[int]] = {}
    for word in candidates:
        descriptor = fourth_descriptor(
            word,
            first_word=first_word,
            second_word=second_word,
            third_word=third_word,
            length=length,
        )
        grouped.setdefault(descriptor, []).append(word)
    return (
        [
            (descriptor, grouped[descriptor])
            for descriptor in sorted(grouped)
        ],
        counts,
    )


def orbit_manifest_digest(orbits: list[dict[str, object]]) -> str:
    lines = []
    for orbit in orbits:
        descriptor = ",".join(
            str(value) for value in orbit["descriptor"]
        )
        lines.append(
            f"{orbit['branch_id']}:{descriptor}:"
            f"{orbit['canonical_word']}:{orbit['orbit_size']}:"
            f"{orbit['earlier_word_count']}\n"
        )
    return hashlib.sha256("".join(lines).encode("ascii")).hexdigest()
