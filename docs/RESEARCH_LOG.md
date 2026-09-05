# Research Log

## 2026-09-04

- Separated retained production provenance from independent replay-host
  provenance. Cross-platform replay now preserves the original checker and
  Python-SAT hashes while rebuilding the same pinned checker source, requiring
  the same Python-SAT version, exact formula and proof identities, and matching
  normalized checker output.
- Retained the complete production and replay-host solver environments in the
  certification output, including the replay Python executable, package tree,
  native modules, platform, and canonical environment digest.
- Added two cross-platform provenance regression tests, bringing the focused
  proof-expansion suite to 82 passing tests.
- Updated the v2 index digest to
  `c528b1358504bad39a3b8770285913d71da0a9ff02e77561d266b2d5dcb11d7f`
  and its 422-entry exact-membership manifest digest to
  `822e78b40e4393ce9b78c8725227f0dd41ab11dd1dc91f4d0bd6d696c7c54786`.
- Required the full 140-proof replay workflow on finalized `main` commits and
  release tags, while allowing manual candidate replay before the final
  revision record exists.
- Aligned the source evidence and release metadata to the current revision
  manager hash before recertification.
- Aligned the package version to 0.2.0 and clarified that the 140 DRAT
  closures are additional to the prior RUP layer rather than a priority claim.

## 2026-09-03

- Authenticated an exact 140-case solver-proof plan selected from the retained
  exploratory scout and recorded the other 26 non-RUP branches separately.
- Benchmarked one difficult selected branch from each of the four hard
  children, then retained the one-worker configuration after checking memory,
  proof size, and free-space margins.
- Generated solver DRAT proofs for all 140 selected branches, checked every raw
  proof before core extraction, and independently replayed every retained core
  with pinned `drat-trim`.
- A pre-promotion run exposed an undefined resource-limit name after all 140
  checkpoints completed. No evidence was promoted. The limit record was
  centralized, staging was restricted to the exact ordered 140-case plan, and
  regression coverage was expanded to a real 420-artifact promotion.
- Passed all 80 focused proof-expansion tests, the authenticated plan audit,
  the structural bundle audit, and the independent full replay of all 140
  retained proofs.
- Promoted the 420-artifact v2 bundle with proof-directory digest
  `44504c6320ac22ad62507f70222c2e8b9e6a51977f27ca3c936019c9f657f08f`
  and index digest
  `342c94b10eb182b18c369a526e3fc9d5ac2b9fc9faa8943b687ea1a357ce3ca8`.
- Retained a 422-entry exact-membership manifest for the v2 plan, index, and
  proof tree with digest
  `be104bad82e54edc2002d9cd089001ddb86d8ae39668b98da9ac9fd319e32cbf`.
- The combined fourth-word certificate now closes 324 of 350 branches and
  leaves 26 unresolved. It closes no complete selected child or normalized
  parent and does not change the interval `15 <= K_2(11,3) <= 16`.
- Classified all 350 fourth-word branches under branch assumptions by unit
  propagation with Glucose 4 and cross-checked every status with Glucose 4.2.
- Identified exactly 184 RUP-conflicting branches and 166 branches outside
  that proof class.
- Regenerated each of the 184 selected branch formulas and audited it with a
  separate reconstruction path.
- Retained an immutable v1 bundle with formula metadata, proof summaries, and
  checker records for all 184 branch certificates.
- Rebuilt `drat-trim` from pinned commit
  `2e3b2dc0ecf938addbd779d42877b6ed69d9a985`, validated the exact tracked
  modes and raw source bytes, and accepted every proof.
- Staged the complete bundle, audited it through the separate reconstruction
  path, rechecked its exact digests, and durably promoted it with interruption
  recovery.
- Replayed all 184 retained certificates in a second fresh run against
  freshly regenerated formulas.
- Retained an unsigned local self-attestation binding the proof-index hash,
  checker binary, pipeline source hashes, exact interpreter command, Python
  executable, `pysat` source tree, native modules, and all 184 outcomes.
- Serialized authenticated writers, auditors, and manifest verification with
  a shared inherited repository lock.
- Made classification and proof-plan publication a crash-recoverable,
  journaled two-file transaction.
- Required structural index audits to match every current pipeline file and
  the complete current Python source tree.
- Added a dedicated 558-entry root manifest for the classification, plan,
  index, attestation, and 554 proof artifacts, with exact declared membership.
- Added a hash-locked replay dependency set for CPython 3.9 through 3.12 and
  checked every retained wheel hash against package-index metadata.
- Added an isolated clean-checkout certification path that sanitizes Git,
  Make, Python, package-manager, hook, filter, and environment state before
  rerunning the full test and proof-audit sequence.
- Required the final certification record to bind a Git revision, release
  manifest, command-result digest, and SHA-256 hashes of the Git, Make, and
  Python executables used for replay.
- Passed all 161 tests in the primary environment. The minimal clean replay
  passed 158 tests and skipped only three optional OR-Tools search tests,
  which are outside the proof-replay dependency lock.
- Completed the isolated replay of certified revision
  `076a0f6703de2c6513799c0b43bfe689480fabda`: regenerated and checked all 184
  formulas and proofs, verified both proof manifests and the release manifest,
  and finished with a clean checkout.
- Recorded the v1 RUP-only claim boundary: 166 fourth-word branches remained,
  no selected third-word child was closed, no normalized parent was newly
  closed, and the exact covering number remained 15 or 16.
- Separated proof generation from proof replay after a full-workflow check
  exposed that the residual verifier regenerated a platform-dependent gzip
  stream and run-dependent timing metadata.
- Made the residual, minimum-distance, third-word, and fourth-word replay
  paths validate retained proofs without rewriting proof records or indexes.
- Restricted cross-platform checker comparison to stable proof identity and
  verification fields while retaining the original checker transcripts.
- Added regression tests and CI clean-tree checks for read-only replay.
- Strengthened the clean-replay record so its aggregate digest is derived from
  ten retained host-specific self-attested per-command output byte counts and
  SHA-256 hashes. The certified revision output and the empty final diff and
  status outputs are checked semantically.
- Refreshed the literature audit against the Keri update log, the audited Lean
  database commit, arXiv:2504.01932v2, and arXiv:2608.19872v1.
- For the `fe73dd0d166b5906faad4c262a4878ec5c9c7ecc` read-only repair, passed
  all 164 tests in the primary environment. Its minimal clean replay passed
  161 tests and skipped only three optional OR-Tools search tests.
- Completed the isolated replay of certified revision
  `fe73dd0d166b5906faad4c262a4878ec5c9c7ecc`: checked all 184 fourth-word
  proofs, verified both proof manifests and the release manifest, and finished
  with a clean checkout.
- The `fe73dd0d166b5906faad4c262a4878ec5c9c7ecc` replay certified the schema-1
  read-only repair. It is superseded for release purposes by the schema-2
  output-attestation source freeze.
- Rebuilt and replayed all 184 fourth-word proofs against the schema-2 source.
  The 554 proof artifacts remained byte-identical, with proof-directory digest
  `927046410d0725a6b3d7ff7cd9832a882ec6f23dd8f6d8c89ddffbcd941368e8`.
- Passed the complete local matrix on 2026-09-03: all 167 tests, the residual
  replay, 14 minimum-distance proofs, 6 third-word proofs, the 112/38 case
  reduction, all 184 fourth-word proofs, both proof manifests, and the
  23-file release manifest.
- Completed the isolated schema-2 clean-checkout replay of certified revision
  `06ecaa7bc28503efd871faf4450005f43e625124`, tree
  `4888ad6c5305b5d30d6c4ca3e8435b9c872307b1`, on 2026-09-03. It passed all
  167 tests with three optional OR-Tools tests skipped, replayed all 184
  fourth-word proofs, verified both proof manifests and the pending release
  manifest, and finished with an empty diff and status.
- Retained ten ordered command-output commitments with aggregate digest
  `527dd5fa22d0a0594cb1a43cac0605869d53bcb4fd5aa5684a3b2eeaf6051b4c`.

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
