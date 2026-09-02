# Orbit-Profile Exclusions

## Averaged Coverage Constraints

Fix one of the 150 canonical two-word cases. The stabilizer of the first
nonzero word partitions all cube words into orbits indexed by

```text
(inside support size, outside support size).
```

Let `x_(a,b)` be the number of selected codewords in orbit `(a,b)`. Every
actual cover induces nonnegative integer values satisfying:

- the orbit-size upper bounds;
- total code size 15;
- the fixed zero, first-word, and second-orbit conditions;
- zero counts for all forbidden earlier orbits;
- one averaged coverage inequality for every target orbit.

The coefficient in a target-orbit inequality is the exact number of targets
within distance 3 of one center in a given center orbit. It is computed by
summing binomial overlap counts inside and outside the first support.

These constraints are necessary but not sufficient for a vertex-level cover.

## Exact Classification

The real linear relaxation is infeasible in 80 of the 150 cases. Each
infeasible case has an integer-scaled Farkas certificate. The remaining 70
cases have exact rational feasible profiles, showing that this particular
linear relaxation alone cannot exclude them.

`tools/generate_orbit_lp_certificates.py` uses HiGHS only to discover a
numerical dual ray or primal point. It rationalizes the result and rejects it
unless exact arithmetic succeeds.

`tools/verify_orbit_lp_certificates.py` uses only the Python standard library.
It independently rebuilds every orbit coefficient and checks:

- each dual combination against exact row and variable bounds;
- a strict contradiction margin in all 80 infeasible cases;
- every variable and row bound for all 70 rational primal witnesses;
- one certificate for every case in the audited manifest.

## Mathematical Consequence

No 15-word radius-3 cover can lie in any of the 80 dual-certified cases.
Every possible cover is therefore restricted to the 70 LP-feasible
two-word cases.

This is a rigorous structural reduction, not a determination of
`K_2(11,3)`. The 70 surviving cases still require a construction or complete
proof-producing exclusion.
