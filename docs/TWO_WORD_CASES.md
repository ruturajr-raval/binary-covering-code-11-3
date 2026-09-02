# Two-Word Orbit Cases

## Stabilizer Reduction

Fix a minimum nonzero weight `w` and its canonical selected word

```text
A = 2^w - 1.
```

The coordinate permutations preserving `A` form

```text
S_w x S_(11-w).
```

Every other word `B` is in an orbit determined exactly by

```text
(weight(B), |support(B) intersect support(A)|).
```

Among the 13 selected words other than zero and `A`, choose the
lexicographically least descriptor, first by total weight and then by
intersection size. Permutations within the support of `A` and its complement
map one selected word in that orbit to a canonical representative.

For each possible descriptor, a case therefore:

1. fixes zero and the canonical first word;
2. excludes all nonzero words of weight below `w`;
3. excludes every remaining word in an earlier descriptor orbit;
4. selects the canonical representative of the current descriptor.

Every hypothetical 15-word cover belongs to at least one of these cases after
translation and coordinate permutation. The six first-word cases split into
150 two-word cases.

## Manifest

`evidence/two-word-cases.json` records every descriptor, canonical pair, unit
count, and SHA-256 digest of the reconstructed unit clauses.
`tools/audit_two_word_cases.py` independently rebuilds the full ordered case
list and rejects any omission or changed unit set.

## Proof Boundary

The partition reduces symmetry but does not decide any case. A complete
lower-bound result requires a checked proof trace for all 150 cases or a
separately checked coarser proof that subsumes them.
