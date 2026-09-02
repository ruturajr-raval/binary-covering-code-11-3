# Minimum-Weight Symmetry Cases

## Complete Reduction

Suppose a 15-word radius-3 cover `C` exists.

If every pair of codewords had distance at least 7, the radius-3 Hamming balls
around the codewords would be disjoint. Each ball has 232 words, so those 15
balls would contain

```text
15 * 232 = 3,480
```

distinct words. The ambient 11-cube has only 2,048 words. Therefore some pair
`a,b` in `C` has distance at most 6.

Translate the code by `a`. The translated code still has size 15 and covering
radius 3, contains zero, and contains `a XOR b`, whose weight is at most 6.
Let `w` be the minimum nonzero weight in the translated code. Then

```text
1 <= w <= 6.
```

A coordinate permutation can map the support of one weight-`w` codeword to
the first `w` coordinate positions. Coordinate permutations preserve Hamming
distance and covering radius. Consequently, one of six cases contains every
possible cover:

1. no nonzero selected word has weight below `w`;
2. canonical word `2^w - 1` is selected;
3. `w` ranges from 1 through 6.

## Generated Formulas

`tools/generate_min_weight_cases.py` appends only the case unit clauses to the
audited base formula. `tools/audit_min_weight_cases.py` verifies the base
prefix, every forbidden lower-weight word, every canonical word, all hashes,
and the complete ordered case list.

An `UNSAT` proof for every case would imply that no 15-word cover exists.
A model from any case would decode to a 15-word cover and must pass both
standalone verifiers before promotion.

## Proof Boundary

Solver timeouts and unlogged `UNSAT` statuses are not proof. A lower-bound
claim requires a checked proof trace for every case and the audited manifest
showing that the six cases are complete.
