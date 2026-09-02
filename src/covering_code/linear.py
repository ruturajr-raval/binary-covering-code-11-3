from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Iterable

from .core import verify_code


def syndrome(word: int, columns: list[int]) -> int:
    value = 0
    for index, column in enumerate(columns):
        if word >> index & 1:
            value ^= column
    return value


def binary_rank(values: Iterable[int]) -> int:
    basis: dict[int, int] = {}
    for original in values:
        value = original
        while value:
            pivot = value.bit_length() - 1
            if pivot not in basis:
                basis[pivot] = value
                break
            value ^= basis[pivot]
    return len(basis)


def kernel_code(columns: list[int]) -> list[int]:
    return [
        word
        for word in range(1 << len(columns))
        if syndrome(word, columns) == 0
    ]


def syndrome_weight_histogram(
    columns: list[int],
    *,
    syndrome_bits: int,
) -> tuple[dict[int, int], int]:
    best: dict[int, int] = {0: 0}
    for weight in range(1, len(columns) + 1):
        for indices in combinations(range(len(columns)), weight):
            value = 0
            for index in indices:
                value ^= columns[index]
            best.setdefault(value, weight)
        if len(best) == 1 << syndrome_bits:
            break
    return dict(sorted(Counter(best.values()).items())), len(best)


def analyze_linear_cover(
    columns: list[int],
    *,
    syndrome_bits: int,
    radius: int,
) -> dict[str, object]:
    if len(set(columns)) != len(columns):
        raise ValueError("parity-check columns must be distinct")
    if any(column <= 0 or column >= 1 << syndrome_bits for column in columns):
        raise ValueError("parity-check column is outside the syndrome space")

    rank = binary_rank(columns)
    code = kernel_code(columns)
    report = verify_code(code, length=len(columns), radius=radius)
    syndrome_histogram, reached_syndromes = syndrome_weight_histogram(
        columns,
        syndrome_bits=syndrome_bits,
    )
    syndrome_radius = max(syndrome_histogram)
    full_syndrome_space = reached_syndromes == 1 << syndrome_bits

    return {
        "length": len(columns),
        "syndrome_bits": syndrome_bits,
        "rank": rank,
        "dimension": len(columns) - rank,
        "code_size": len(code),
        "syndrome_radius": syndrome_radius,
        "reached_syndromes": reached_syndromes,
        "full_syndrome_space": full_syndrome_space,
        "syndrome_weight_histogram": syndrome_histogram,
        "codewords": code,
        "direct_verification": report.to_dict(),
        "valid": (
            rank == syndrome_bits
            and full_syndrome_space
            and report.valid
            and syndrome_radius <= radius
        ),
    }
