# Fourth-Word Hard Frontier

The first child-level portfolio for the parent
`w4-weight5-intersection0` reported UNSAT for 24 of its 28 live third-word
children in bounded exploratory runs. Four children remained unresolved after
independent five-minute solver attempts:

- `w4-weight5-intersection0::orbit-005`
- `w4-weight5-intersection0::orbit-007`
- `w4-weight5-intersection0::orbit-014`
- `w4-weight5-intersection0::orbit-015`

Solver statuses are not proof claims. Reproducible scout reports and their run
records must be retained before this selection is used as research evidence.
The retained fourth-word frontier is an exact symmetry split of those four
unresolved formulas.

## Exact Split

After fixing zero and the first three nonzero words, the remaining coordinate
symmetry permutes positions within the eight membership cells determined by
the fixed nonzero triple. A possible fourth nonzero word is therefore
classified by its eight intersection counts with those cells.

For each hard child, the split:

1. excludes the four already fixed words;
2. enforces the parent threshold and the earlier third-orbit exclusions;
3. excludes words below the certified minimum distance from a fixed word;
4. excludes words that would immediately violate the certified matching
   condition;
5. groups every remaining word by its eight-cell descriptor;
6. selects the least integer as the orbit representative;
7. branches on the first occupied fourth-word orbit by selecting its
   representative and excluding all earlier orbit words.

The four fixed words leave more than 1,200 ambient vertices uncovered in each
case, so every covering code in one of these children must select at least one
additional word. The split is therefore exhaustive.

| Third-word child | Candidate words | Fourth-word orbits | Matching exclusions |
| --- | ---: | ---: | ---: |
| `orbit-005` | 815 | 85 | 233 |
| `orbit-007` | 751 | 76 | 175 |
| `orbit-014` | 727 | 73 | 158 |
| `orbit-015` | 674 | 116 | 187 |
| **Total** | **2,967** | **350** | **753** |

## Independent Audit

`research/fourth-word-hard-frontier.json` records every branch descriptor,
canonical word, orbit size, prefix exclusion count, fixed-word distances, and
content digest.

The auditor does not import the fourth-word generator or its symmetry module.
It independently reconstructs the third-word prefix, the eight coordinate
cells, all static exclusions, the matching condition, all 350 fourth-word
orbits, and every retained digest. It also pins the aggregate and per-child
counts above.

Audit the retained frontier:

```text
make audit-fourth-word-hard-frontier
```

Regenerate and audit it:

```text
make rebuild-and-audit-fourth-word-hard-frontier
```

## Retained Scout

At commit `f968cc7`, a four-worker Glucose 4 portfolio scheduled all 350
branches with a cooperative interrupt request after five seconds per branch.
It reported 324 UNSAT and 26 UNKNOWN statuses, found no cover, and recorded no
worker errors.

- `research/runs/2026-09-02-fourth-word-portfolio.json`
- `research/runs/2026-09-02-fourth-word-portfolio-run.json`

The scout is prioritization evidence only. Its UNSAT statuses have no retained
proof trace, and cooperative interrupt timing can change statuses near the
threshold. The measured solve time can also exceed five seconds before the
solver acknowledges an interrupt.

## Certified RUP Closures

A propagation-only classification was cross-checked with Glucose 4 and
Glucose 4.2. Both solvers agreed on every branch. This identified 184 branch
formulas whose assumptions force a contradiction by reverse unit propagation,
leaving 166 branches outside this proof class.

| Third-word child | Fourth-word branches | RUP-UNSAT | Residual |
| --- | ---: | ---: | ---: |
| `orbit-005` | 85 | 50 | 35 |
| `orbit-007` | 76 | 53 | 23 |
| `orbit-014` | 73 | 41 | 32 |
| `orbit-015` | 116 | 40 | 76 |
| **Total** | **350** | **184** | **166** |

Every one of the 184 formulas was regenerated, independently audited, and
checked with `drat-trim` at commit
`2e3b2dc0ecf938addbd779d42877b6ed69d9a985`. The retained v1 bundle contains
the formula metadata, proof summary, and checker record for each branch. The
large CNF files are reproducible build artifacts and are not retained.

The principal records are:

- `evidence/fourth-word-up-classification.json`
- `evidence/fourth-word-rup-proof-plan.json`
- `evidence/fourth-word-rup-proof-index-v1.json`
- `evidence/fourth-word-rup-replay-attestation-v1.json`
- `evidence/fourth-word-rup-bundle-v1.sha256`
- `evidence/proofs/fourth-word-rup-v1/`

Replay all 184 certificates from regenerated formulas:

```text
make audit-fourth-word-rup-proofs
```

Check the retained index and artifact hashes without replaying the proofs:

```text
make check-fourth-word-rup-proof-index
```

The structural check requires every indexed pipeline file and the complete
`src` and `tools` Python tree to match the current repository bytes. The full
replay additionally rebuilds the checker from the pinned source commit,
validates the tracked modes and raw source bytes, and rejects checker,
pipeline, interpreter, or dependency changes during the run. Compiled checker
hashes can differ across platforms, so the measured binary hash belongs to the
local replay record rather than a universal cross-platform requirement.

The retained replay attestation is an unsigned, hash-bound local
self-attestation for a second successful 184-case replay on 2026-09-03. It
binds the proof index, checker build, pipeline sources, exact interpreter
command in privacy-safe form, Python executable, `pysat` source tree, native
`python-sat` modules, and all case outcomes. The dedicated v1 manifest
authenticates the classification, proof plan, proof index, replay attestation,
and all 554 proof artifacts.

## Certified Solver DRAT Closures

The authenticated scout selected 140 of the 166 non-RUP branches for
proof-producing Glucose4 runs. Each raw solver proof was checked before core
extraction, and every retained DRAT core was independently replayed with the
pinned `drat-trim` revision.

| Third-word child | RUP certified | DRAT certified | Residual | Total |
| --- | ---: | ---: | ---: | ---: |
| `orbit-005` | 50 | 29 | 6 | 85 |
| `orbit-007` | 53 | 15 | 8 | 76 |
| `orbit-014` | 41 | 28 | 4 | 73 |
| `orbit-015` | 40 | 68 | 8 | 116 |
| **Total** | **184** | **140** | **26** | **350** |

The principal v2 records are:

- `proof-expansion/evidence/fourth-word-solver-drat-plan-v2.json`
- `proof-expansion/evidence/fourth-word-solver-drat-index-v2.json`
- `proof-expansion/evidence/fourth-word-solver-drat-bundle-v2.sha256`
- `proof-expansion/evidence/fourth-word-solver-drat-revision-v2.json` in a
  finalized release
- `proof-expansion/evidence/proofs/fourth-word-solver-drat-v2/`

The v2 index SHA-256 is
`c528b1358504bad39a3b8770285913d71da0a9ff02e77561d266b2d5dcb11d7f`.
The exact 422-entry v2 bundle manifest SHA-256 is
`822e78b40e4393ce9b78c8725227f0dd41ab11dd1dc91f4d0bd6d696c7c54786`.
The 420-artifact proof-directory digest is
`44504c6320ac22ad62507f70222c2e8b9e6a51977f27ca3c936019c9f657f08f`.
The structural audit and independent replay of all 140 retained proofs passed
on 2026-09-03.

Verify exact v2 bundle membership from the repository root:

```text
.venv/bin/python tools/verify_checksum_manifest.py proof-expansion/evidence/fourth-word-solver-drat-bundle-v2.sha256 --path proof-expansion/evidence/fourth-word-solver-drat-plan-v2.json --path proof-expansion/evidence/fourth-word-solver-drat-index-v2.json --tree proof-expansion/evidence/proofs/fourth-word-solver-drat-v2
```

Verify a finalized revision attestation:

```text
.venv/bin/python release-tools/manage_fourth_word_solver_drat_revision.py --verify --release-revision "$(git rev-parse HEAD)"
```

The certification remains branch-level. Every selected third-word child still
has at least one residual fourth-word branch, so the combined 324 closures
close no complete third-word child and no normalized parent. The global
frontier therefore remains at 38 unresolved normalized parents, and the exact
value remains 15 or 16.

The next proof step is an audited fifth-word orbit split of the 26 remaining
branches, alongside continued search for a verified 15-word code.
