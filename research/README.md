# Research Record

This record documents the attempt to determine the exact value of
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

The four hard children from the first focused parent have an independently
audited fourth-word split documented in
`research/FOURTH_WORD_HARD_FRONTIER.md`. It contains 350 exhaustive orbit
branches. Checked reverse-unit-propagation certificates close 184 branches,
and independently replayed solver-generated DRAT certificates close 140 more.
The remaining 26 branches leave every selected third-word child and normalized
parent open.

## Records

- `research/claim.yaml` defines the exact scope of the candidate result.
- `research/release-gate.json` records which promotion requirements have been
  met.
- `research/run.schema.json` defines the minimum metadata for retained
  computations.
- `research/runs/2026-09-02-fourth-word-portfolio.json` retains the complete
  exploratory fourth-word scout and its adjacent provenance record.
- `evidence/fourth-word-rup-proof-index-v1.json` indexes 184 checked
  fourth-word branch certificates.
- `evidence/fourth-word-rup-replay-attestation-v1.json` records a second full
  replay as an unsigned, hash-bound local self-attestation.
- `evidence/fourth-word-rup-bundle-v1.sha256` authenticates the complete
  fourth-word v1 evidence bundle.
- `proof-expansion/evidence/fourth-word-solver-drat-plan-v2.json` authenticates
  the 140-case solver-proof selection.
- `proof-expansion/evidence/fourth-word-solver-drat-index-v2.json` indexes 140
  independently replayed solver-generated DRAT certificates.
- `proof-expansion/evidence/fourth-word-solver-drat-bundle-v2.sha256`
  authenticates the v2 plan, index, and exact 420-artifact proof tree.
- `proof-expansion/evidence/fourth-word-solver-drat-revision-v2.json`, when
  present in a finalized release, binds the committed source replay and
  strict finalization policy.
- `release-tools/manage_fourth_word_solver_drat_revision.py` validates that
  revision record and the release metadata that points to it.
- `proof-expansion/evidence/proofs/fourth-word-solver-drat-v2/` retains the
  420 v2 proof artifacts.

Every child branch must be linked to its parent, canonical representative,
stabilizer data, imposed constraints, and content digest. The current ledger
provides these links. A child-level CNF generator and an independent auditor
now reconstruct the exact minimum-distance, parent, orbit-prefix, and matching
constraints for any live child. For the four selected hard children, the
retained v1 proof bundle authenticates 184 branch formulas and their
independently checked RUP certificates. The retained v2 bundle authenticates
140 additional formulas and checked DRAT certificates. The remaining 26
branches have no retained closure, and solver status alone is not treated as a
mathematical conclusion.

## Promotion Standard

The preferred promotion threshold is an exact determination of `K_2(11,3)`.
A partial result is substantial enough only if it proves a reusable theorem
and reduces the 38 authenticated residual parents to at most 19.

Before promotion, prior art must be refreshed, all evidence must replay from a
clean checkout, the exact claim and non-claim must be explicit, and independent
review must be requested.
