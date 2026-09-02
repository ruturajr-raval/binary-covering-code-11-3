# Research Plan

## Objective

Determine whether `K_2(11,3)` equals 15 or 16.

## Phase 1 - Baseline

- Verify a 16-word code by exhaustive distance calculation.
- Verify the same code independently through its parity-check syndromes.
- Reconstruct the historical lower-bound provenance.
- Test the model on exact smaller covering-code values.

Acceptance: both baseline verification paths pass and mutation tests reject
damaged codes.

## Phase 2 - Construction Search

- Implement weighted local search with exact coverage accounting.
- Use the 16-word linear code as one seed, but allow nonlinear candidates.
- Add large-neighborhood repair with independently verified output.
- Search distance-profile and stabilizer partitions rather than relying on one
  trajectory.

Acceptance: a 15-word candidate passes two independent exhaustive verifiers
and adversarial mutation tests.

## Phase 3 - Impossibility Search

- Generate the complete size-15 set-cover CNF.
- Validate the encoding by exhaustive projection on smaller cubes.
- Add translation symmetry by fixing the zero word.
- Develop complete profile partitions with separate case-cover tests.
- Run proof-producing SAT and check each proof independently.

Current status:

- complete 150-case two-word partition;
- 112 certified normalized branch closures;
- 38 normalized residual branches;
- proof-producing continuation required.

Acceptance: every size-15 case has an authenticated checked proof, the case
partition is complete, and the formula semantics are independently tested.

## Phase 4 - Result Promotion

- Refresh the literature audit.
- Freeze code, formulas, proofs, certificates, hashes, and solver versions.
- Obtain external review of the mathematical model and proof replay.
- Prepare a short manuscript and notify table and formal-database maintainers.

## Stop Conditions

Do not promote:

- a timeout;
- an unchecked solver status;
- a candidate that only one implementation accepts;
- an incomplete symmetry or distance-profile partition;
- a lower bound inherited only from an unauthenticated historical log.
