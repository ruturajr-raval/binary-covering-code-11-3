# Solver-Generated DRAT Proof Expansion

Author: Ruturaj R Raval

Date: 2026-09-04

## Objective

This subsystem certifies 140 fourth-word branches that were not closed by
unit propagation but were reported UNSAT by an authenticated exploratory
Glucose4 run. Exploratory solver status was used only to select cases. Every
counted branch has a retained DRAT proof checked independently with the pinned
`drat-trim` revision.

## Certified Result

The published certificate closes 184 of 350 fourth-word branches by RUP.
Its proof index, replay attestation, checksum bundle, and certified source
revision are direct inputs to the expansion plan.

The completed expansion is:

| Child | RUP certified | DRAT certified | Remaining | Total |
| --- | ---: | ---: | ---: | ---: |
| `orbit-005` | 50 | 29 | 6 | 85 |
| `orbit-007` | 53 | 15 | 8 | 76 |
| `orbit-014` | 41 | 28 | 4 | 73 |
| `orbit-015` | 40 | 68 | 8 | 116 |
| **Total** | **184** | **140** | **26** | **350** |

The combined certificate closes 324 of 350 branches. It leaves 26 branches
unresolved, closes none of the four selected third-word children, closes no
normalized parent, and leaves the covering number at 15 or 16.

The retained index is
`evidence/fourth-word-solver-drat-index-v2.json`. Its SHA-256 is
`c528b1358504bad39a3b8770285913d71da0a9ff02e77561d266b2d5dcb11d7f`.
The exact-membership bundle manifest is
`evidence/fourth-word-solver-drat-bundle-v2.sha256`. Its SHA-256 is
`822e78b40e4393ce9b78c8725227f0dd41ab11dd1dc91f4d0bd6d696c7c54786`.
The 420-artifact proof directory has digest
`44504c6320ac22ad62507f70222c2e8b9e6a51977f27ca3c936019c9f657f08f`.
The 82 focused tests and structural audit passed on 2026-09-04. All 140
retained proofs were independently replayed on 2026-09-03.

The retained index records the exact production Python-SAT environment and
checker binary hash. Independent replay may use a different host binary built
from the same pinned checker source revision. The audit still requires the
same Python-SAT version, reconstructs every formula exactly, authenticates the
current checker before and after use, and requires normalized checker output
to match the retained replay record.
The certified revision record retains complete production and replay-host
solver-environment records with canonical hashes, including the replay
Python executable, package tree, native modules, platform, and checker hash.

Finalized releases also retain
`evidence/fourth-word-solver-drat-revision-v2.json`. From the repository
root, `release-tools/manage_fourth_word_solver_drat_revision.py --verify`
checks its certified source revision, retained replay outputs, exact
finalization ancestry, allowed paths, Git file modes, and release scope.

The lower endpoint 15 is inherited from the previously published
computational lower bound. This subsystem does not reconstruct that
historical computation into a new retained certificate.

## Integrity Model

The v2 pipeline:

- reconstructs and audits the exact 140-case plan before every build;
- runs certification scripts in isolated Python processes with fresh
  bytecode caches;
- parses authenticated JSON from the same descriptor-backed byte snapshots
  whose hashes are recorded, rejecting duplicate keys;
- verifies the existing 184-case certificate and checksum bundle;
- binds the complete root `src` and `tools` Python tree;
- records the Python-SAT package tree and native module hashes;
- regenerates and independently audits each branch formula;
- executes the solver and checker only against read-only private snapshots
  of the authenticated formula, checker, and retained-proof bytes;
- verifies each private snapshot's identity, metadata, and content digest
  immediately before and after every parser, decompressor, or checker use;
- checks the raw solver proof before extracting a smaller DRAT core;
- replays every retained proof with the pinned checker;
- checks retained gzip content and canonical encoding during structural
  audits;
- regenerates formulas and replays proofs when resuming checkpoints;
- uses bounded solve time, proof size, memory monitoring, and aggregate
  free-space reservation;
- publishes plans, case checkpoints, proof outputs, journals, and final
  bundles with atomic no-replace operations;
- authenticates file identity, mode, size, modification time, and content
  immediately before publication and again under the destination name;
- reverses and directory-syncs a committed rename when post-publication
  validation or synchronization fails, with caller-level cleanup when the
  reversal cannot be durably confirmed;
- promotes evidence only after complete canonical validation;
- tracks scratch-parent identity across temporary-directory creation and
  use, and removes owned scratch trees through the original parent
  descriptor;
- moves every verified scratch child into a non-listable deletion vault
  under a random 128-bit name and checks its captured identity before
  deletion;
- retains an identity-less scratch path in a random quarantine rather than
  risk deleting a concurrent replacement;
- quarantines staging paths before identity-checked removal;
- rolls back interrupted promotions instead of trusting a journal.

Retained summaries exclude elapsed time, removing the known source of
non-determinism from otherwise equivalent proof runs.

## Commands

Run from `proof-expansion`:

```sh
make test
make audit-plan
make build-bundle
make audit-bundle-structure
make audit-bundle
```

From the repository root, verify the exact plan, index, and proof-tree
membership with:

```sh
.venv/bin/python tools/verify_checksum_manifest.py \
  proof-expansion/evidence/fourth-word-solver-drat-bundle-v2.sha256 \
  --path proof-expansion/evidence/fourth-word-solver-drat-plan-v2.json \
  --path proof-expansion/evidence/fourth-word-solver-drat-index-v2.json \
  --tree proof-expansion/evidence/proofs/fourth-word-solver-drat-v2
.venv/bin/python \
  release-tools/manage_fourth_word_solver_drat_revision.py \
  --verify --release-revision "$(git rev-parse HEAD)"
```

The default is one proof worker. Two workers are permitted only after
hard-case resource measurements establish that concurrent execution is
safe on the host.

## Limitations

The Python proof-generation process has a peak-RSS watchdog, but the
external `drat-trim` process does not have a portable enforced memory
ceiling in this subsystem. Checker runtime, output size, and proof-file
size are bounded. The one-worker default reduces concurrent memory risk,
but independent replay should still be run on a suitably provisioned
machine.

The raw solver proof is checked before core extraction but is not retained.
Its byte count, digest, and extraction log are production records rather
than independently reconstructible evidence. The retained DRAT core,
formula identity, and independent replay are the durable certificate.

Atomic no-replace publication requires `renameatx_np` on Darwin or
`renameat2` on Linux. The pipeline fails closed rather than falling back
to a clobbering rename on unsupported systems.

The integrity controls detect concurrent mutation and path replacement
within the certification workflow. They do not claim containment against
a malicious privileged host.

The clean-replay record is a host-specific self-attestation, not a
third-party signature. GitHub replays on `main` and release tags provide
separate publicly visible executions tied to the released commit.

## Claim Boundary

This work claims 140 additional branch-level DRAT closures relative to the
prior RUP layer, giving 324 certified closures across the selected 350-branch
fourth-word split when combined with the prior 184 RUP certificates. It does
not claim a 15-word covering code, a proof that no such code exists, a closed
third-word child, a closed normalized parent, a new global bound, or a final
value for `K_2(11,3)`.
