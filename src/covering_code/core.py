from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Iterable


def hamming_weight(value: int) -> int:
    return bin(value).count("1")


def hamming_distance(left: int, right: int) -> int:
    return hamming_weight(left ^ right)


def parse_code(text: str, *, length: int) -> list[int]:
    code: list[int] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        token = "".join(raw_line.split())
        if not token or token.startswith("#"):
            continue
        if len(token) != length or any(bit not in "01" for bit in token):
            raise ValueError(
                f"line {line_number} is not a {length}-bit binary word"
            )
        code.append(int(token, 2))

    if not code:
        raise ValueError("code is empty")
    if len(set(code)) != len(code):
        raise ValueError("code contains duplicate words")
    return code


def normalized_code_text(code: Iterable[int], *, length: int) -> str:
    words = sorted(code)
    return "".join(f"{word:0{length}b}\n" for word in words)


def code_digest(code: Iterable[int], *, length: int) -> str:
    return sha256(
        normalized_code_text(code, length=length).encode("ascii")
    ).hexdigest()


@dataclass(frozen=True)
class CoverageReport:
    length: int
    radius: int
    code_size: int
    ambient_size: int
    valid: bool
    covering_radius: int
    distance_histogram: dict[int, int]
    coverage_multiplicity_histogram: dict[int, int]
    uncovered_words: list[int]
    normalized_sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def verify_code(
    code: Iterable[int],
    *,
    length: int,
    radius: int,
) -> CoverageReport:
    words = sorted(code)
    if not words:
        raise ValueError("code is empty")
    if len(set(words)) != len(words):
        raise ValueError("code contains duplicate words")
    if any(word < 0 or word >= 1 << length for word in words):
        raise ValueError("codeword is outside the ambient cube")
    if radius < 0 or radius > length:
        raise ValueError("radius is outside the valid range")

    distance_histogram: dict[int, int] = {}
    multiplicity_histogram: dict[int, int] = {}
    uncovered: list[int] = []
    maximum_distance = 0

    for target in range(1 << length):
        distances = [hamming_distance(target, word) for word in words]
        minimum = min(distances)
        multiplicity = sum(distance <= radius for distance in distances)
        maximum_distance = max(maximum_distance, minimum)
        distance_histogram[minimum] = (
            distance_histogram.get(minimum, 0) + 1
        )
        multiplicity_histogram[multiplicity] = (
            multiplicity_histogram.get(multiplicity, 0) + 1
        )
        if multiplicity == 0:
            uncovered.append(target)

    return CoverageReport(
        length=length,
        radius=radius,
        code_size=len(words),
        ambient_size=1 << length,
        valid=not uncovered,
        covering_radius=maximum_distance,
        distance_histogram=distance_histogram,
        coverage_multiplicity_histogram=multiplicity_histogram,
        uncovered_words=uncovered,
        normalized_sha256=code_digest(words, length=length),
    )


def ball(center: int, *, length: int, radius: int) -> list[int]:
    return [
        word
        for word in range(1 << length)
        if hamming_distance(center, word) <= radius
    ]
