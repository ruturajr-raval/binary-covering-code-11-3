# Research Workbench

This directory records the attempt to determine the exact value of
`K_2(11,3)`.

The current certified frontier is a verified 16-word cover and a complete
150-parent normalization of the 15-word search with 112 closed parents and 38
residual parents. Neither endpoint of the interval has been newly established:
no 15-word cover is known here, and the retained certificates do not exclude
all 15-word codes.

## Active Target

The exact target is one of:

1. Find and independently verify a 15-word radius-3 covering code.
2. Produce a complete checked proof that no such code exists.

The first proof-lane milestone is an authenticated ledger of every canonical
third-word child orbit below the 38 residual parents, checked by an auditor
that does not import the generator's orbit routines.

The retained frontier record is documented in
`research/THIRD_WORD_CHILD_FRONTIER.md`. It distinguishes the 2,815
intermediate non-DRAT children, the 2,548 raw children below the 38 active
parents, and the 2,163 children that survive all retained static constraints.

## Records

- `claim.yaml` defines the exact scope of the candidate result.
- `release-gate.json` records which promotion requirements have been met.
- `run.schema.json` defines the minimum metadata for retained computations.
- `/.research-artifacts/` holds local exploratory outputs and is not tracked.

Every child branch must be linked to its parent, canonical representative,
stabilizer data, imposed constraints, and content digest. The current ledger
provides these links. A child-level CNF generator and an independent auditor
now reconstruct the exact minimum-distance, parent, orbit-prefix, and matching
constraints for any live child. A complete child-formula manifest is not
retained, and no child is closed without a proof accepted by an independent
checker. Solver status alone is not retained as a mathematical conclusion.

## Promotion Standard

The preferred promotion threshold is an exact determination of `K_2(11,3)`.
A partial result is substantial enough only if it proves a reusable theorem
and reduces the 38 authenticated residual parents to at most 19.

Before promotion, prior art must be refreshed, all evidence must replay from a
clean checkout, the exact claim and non-claim must be explicit, and independent
review must be requested.
