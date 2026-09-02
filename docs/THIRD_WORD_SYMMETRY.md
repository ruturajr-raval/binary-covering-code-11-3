# Third-Word Stabilizer Symmetry

## Fixed Parent Case

A canonical two-word parent fixes the selected words

```text
0, A, B.
```

It also excludes every word that is earlier than `B` in the parent
descriptor order. Any additional selected word must therefore satisfy the
parent case's weight and descriptor threshold.

## Stabilizer Orbits

The ordered pair `(A,B)` partitions the 11 coordinate positions into four
cells:

```text
A intersect B
A minus B
B minus A
outside A union B
```

The full coordinate stabilizer of the ordered pair permutes coordinates
independently inside these four cells. Its orbit on a third word `D` is
therefore determined exactly by the four counts

```text
(
  |D intersect A intersect B|,
  |D intersect (A minus B)|,
  |D intersect (B minus A)|,
  |D outside (A union B)|
).
```

`evidence/third-word-cases.json` records the sorted orbit list for every
stage-1 residual parent. The independent audit rebuilds the candidates and
all four-count descriptors without importing the generator.

## Lexicographically First Occupied Orbit

Every parent has at least one selected word beyond `0,A,B`. Choose the first
occupied third-word orbit in the sorted list. A stabilizer permutation maps
one selected word in that orbit to its canonical representative while
leaving `0,A,B` fixed.

The formula introduces one selector per orbit and enforces:

1. exactly one selector is true;
2. a true selector selects that orbit's canonical representative;
3. a true selector excludes every word in all earlier orbits.

This is a disjunction internal to one CNF formula. It is complete because
every normalized parent has a first occupied orbit.

## Optional Matching Constraint

Some parent cases have a separate theorem that their minimum-distance graph
must be a matching. Only those cases may receive the optional matching
clauses. The proof plan records this assumption per case, and the formula
metadata and audit must agree with the plan before a proof can enter the
case ledger.

## Reproducibility

The relevant artifacts are:

- `tools/generate_third_word_cases.py`
- `tools/audit_third_word_cases.py`
- `tools/generate_third_word_formula.py`
- `tools/audit_third_word_formula.py`
- `evidence/third-word-cases.json`
- `evidence/third-word-proof-plan.json`
- `evidence/third-word-proof-index.json`

The proof index is valid only when every formula is reconstructed, every
retained trace is checked, and all hashes match.
