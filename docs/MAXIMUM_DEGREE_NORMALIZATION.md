# Maximum-Degree Normalization

## Minimum-Distance Graph

For a hypothetical code with minimum distance `d`, form a graph whose
vertices are the selected codewords and whose edges join pairs at distance
exactly `d`.

Choose a vertex of maximum degree, translate it to zero, choose one of its
neighbors, and permute coordinates so that this neighbor becomes

```text
A = 2^d - 1.
```

The two-word normalization then chooses `B` as the selected word with the
first remaining descriptor. This choice is compatible with the earlier
two-word orbit partition because the translation and coordinate permutation
preserve the cover and all distances.

## Three Classifications

If `weight(B) = d`, zero has at least two minimum-distance neighbors, `A` and
`B`. These are the `multiple_neighbor` cases and no further conclusion is
drawn here.

Suppose instead that `weight(B) > d`. Because `B` is the first remaining
descriptor, there is no selected word of weight `d` other than `A`.
Consequently, zero has degree exactly one.

There are then two possibilities:

1. If `distance(A,B) = d`, vertex `A` has the two neighbors zero and `B`.
   This contradicts the choice of zero as a maximum-degree vertex.
2. If `distance(A,B) > d`, maximum degree is one, so the entire
   minimum-distance graph is a matching.

Applied to the 49 stage-1 residual cases, this gives:

```text
5 maximum-degree contradictions
34 matching cases
10 multiple-neighbor cases
```

The exact case lists are in `evidence/max-degree-reduction.json`.

## Matching CNF

For each case certified as `matching`, a selected vertex may have at most one
selected neighbor at distance `d`. `tools/matching_constraints.py` adds this
condition as a gated at-most-one constraint for every parent-allowed ambient
word.

The gate is the variable selecting the vertex. Excluded parent words are
omitted because their unit clauses already force them false. The sequential
encoding is exhaustively tested on small input sets, and
`tools/audit_third_word_formula.py` independently reconstructs every matching
clause and auxiliary variable.

## Scope

The normalization eliminates only the five contradiction cases. The matching
classification is not itself an exclusion. A matching case is removed from
the ledger only when its matching-constrained formula has a separately
checked proof trace.
