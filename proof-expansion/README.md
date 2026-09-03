# Solver-Generated DRAT Proof Expansion

Author: Ruturaj R Raval

Date: 2026-09-03

## Objective

This workbench targets 140 fourth-word branches that were not closed by
unit propagation but were reported UNSAT by an authenticated exploratory
Glucose4 run. Exploratory solver status is used only to select cases. A
branch is counted as certified only after a retained DRAT proof is checked
independently with the pinned `drat-trim` revision.

## Certified Starting Point

The published certificate closes 184 of 350 fourth-word branches by RUP.
Its proof index, replay attestation, checksum bundle, and certified source
revision are direct inputs to the expansion plan.

The selected expansion is:

| Child | RUP certified | Planned DRAT | Remaining | Total |
| --- | ---: | ---: | ---: | ---: |
| `orbit-005` | 50 | 29 | 6 | 85 |
| `orbit-007` | 53 | 15 | 8 | 76 |
| `orbit-014` | 41 | 28 | 4 | 73 |
| `orbit-015` | 40 | 68 | 8 | 116 |
| **Total** | **184** | **140** | **26** | **350** |

If every planned proof verifies, the combined certificate will close 324
of 350 branches. It will still leave 26 branches unresolved, close none
of the four selected third-word children, close no normalized parent, and
leave the covering number at 15 or 16.

The lower endpoint 15 is inherited from the previously published
computational lower bound. This workbench does not reconstruct that
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

The default is one proof worker. Two workers are permitted only after
hard-case resource measurements establish that concurrent execution is
safe on the host.

## Limitations

The Python proof-generation process has a peak-RSS watchdog, but the
external `drat-trim` process does not have a portable enforced memory
ceiling in this workbench. Checker runtime, output size, and proof-file
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

## Claim Boundary

This work does not claim a 15-word covering code, a proof that no such code
exists, a closed third-word child, a closed normalized parent, or a final
value for `K_2(11,3)`. Any future claim must be derived from retained,
independently replayed proof artifacts rather than exploratory solver
status.
