# Research Log

## 2026-09-02

- Audited the current binary covering-code table and selected the one-gap cell
  `15 <= K_2(11,3) <= 16`.
- Rejected stale candidate `K_8(4,2)` after locating its June 2026 checked
  resolution.
- Deterministically searched parity-check columns in `F_2^7`.
- At trial 1,138 with seed 20260902, found eleven columns whose sums of at most
  three columns cover all 128 syndromes.
- Extracted the 16-word kernel code and verified covering radius exactly 3.
- Added direct verification, syndrome verification, exact CNF generation,
  CP-SAT search support, and tests.
- A preliminary unretained 60-second CP-SAT run for size 15 returned
  `UNKNOWN`. It establishes no mathematical result.
- Added a standalone direct-distance verifier and cross-linked the retained
  code exactly to the parity-check kernel.
- Audited the exact size-15 formula and compared its cardinality projection
  against an unrelated totalizer encoding on all small assignments.
- Proved and generated a complete six-case minimum-nonzero-weight partition
  using translation and coordinate-permutation symmetry.
- Added compact at-most-15 formulas justified by monotone padding. The
  `kmtotalizer` formula has 9,464 variables and 26,804 clauses.
- Implemented targeted breakout search. The first retained 10,000-iteration
  run found a 15-word near-cover with 28 uncovered words.
- Bounded CP-SAT repair runs and the first six exact-case CaDiCaL runs returned
  `UNKNOWN`. None emitted a proof trace.
- Generated and independently audited the complete 150-case canonical
  two-word orbit partition.
- Retained exact Farkas certificates excluding 80 orbit-profile cases.
- Exhaustively checked integer orbit profiles for the 70 LP-feasible cases,
  excluding two further cases.
- Proved minimum distance at most 5, at least 28 pairs at distance at most 6,
  and at least 11 pairs at distance at most 5.
- Proved total pair-ball overlap at least 1,712 through an exact modular
  identity, and derived total triple-ball overlap at least 280.
- Generated five audited closest-pair formulas and retained checked DRAT
  proofs for 14 canonical parent cases.
- Added a machine-checked stage-1 ledger reducing 150 parent cases to 49.
- Normalized at a maximum-degree vertex of the minimum-distance graph,
  eliminating five cases and certifying 34 matching cases.
- Generated and audited 3,238 third-word stabilizer orbits over the 49
  stage-1 residual parents.
- Retained six checked third-word DRAT proofs, including four formulas using
  the certified matching constraint.
- Regenerated the final ledger: 112 normalized branches are closed and 38
  normalized branches remain.
- Extended construction and repair searches without finding a 15-word cover.
  The best retained candidate still leaves 28 words uncovered.
