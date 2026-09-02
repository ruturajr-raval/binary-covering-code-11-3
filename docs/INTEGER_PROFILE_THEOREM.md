# Integer Orbit-Profile Classification

The exact rational orbit-profile analysis leaves 70 cases feasible over the
reals. Requiring orbit counts to be integers excludes two more cases:

```text
w2-weight7-intersection0
w5-weight6-intersection4
```

For each LP-feasible case, the retained certificate contains either:

- an explicit integer orbit profile satisfying every averaged coverage
  inequality; or
- a compressed exhaustive-search trace whose leaves certify that no integer
  profile exists.

The two infeasible traces cover all distributions of the 12 codewords left
after fixing zero and the canonical first and second words. A trace leaf is
accepted only when:

- the remaining orbit capacities cannot fill the required code size; or
- even assigning all remaining codewords to the best available orbits cannot
  satisfy one named target-orbit coverage inequality.

The standalone checker reconstructs all orbit coefficients, verifies every
prune exactly, and confirms that every branch is covered.

Combining the rational and integer certificates excludes 82 of the 150
two-word cases. Exactly 68 cases retain integer orbit profiles. These profiles
are necessary aggregate data, not vertex-level covering codes.
