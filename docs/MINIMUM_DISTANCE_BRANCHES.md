# Closest-Pair Minimum-Distance Branches

## Completeness

Let `C` be a hypothetical 15-word radius-3 cover and let

```text
d = min {distance(x,y) : x,y in C, x != y}.
```

The exact distance-distribution certificate in
`evidence/distance-distribution-bounds.json` proves `d <= 5`. Choose a pair
`x,y` at distance `d`, translate every codeword by `x`, and permute
coordinates so that `y XOR x` becomes

```text
A_d = 2^d - 1.
```

Translation and coordinate permutations preserve code size, covering radius,
and all pairwise distances. The normalized code therefore:

1. contains zero;
2. contains `A_d`;
3. contains no selected pair at distance below `d`;
4. has `d` in the complete range `1,2,3,4,5`.

These five alternatives cover every possible size-15 code.

## Formula Construction

For branch `d`, `tools/generate_min_distance_branches.py` starts from the
audited compact at-most-15 covering formula. It appends:

- one binary exclusion clause for every unordered ambient pair at distance
  below `d`;
- one unit clause selecting `A_d`.

The number of forbidden-pair clauses is

```text
2^10 * sum_{i=1}^{d-1} C(11,i).
```

The formulas do not assume that the displayed closest pair is unique.

## Independent Audit

`tools/audit_min_distance_branches.py` independently reconstructs every
forbidden pair, the canonical selected word, the complete ordered branch
list, and each formula hash. The retained manifest and audit are:

- `evidence/min-distance-branches.json`
- `evidence/min-distance-branch-audit.json`

## Proof Boundary

The branch split is a complete normalization, not an impossibility proof.
An `UNSAT` claim for a branch or a subcase is retained only when its proof
trace is accepted by the recorded independent checker.
