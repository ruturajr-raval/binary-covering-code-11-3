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

The certification is branch-level. Each selected third-word child still has
at least one residual fourth-word branch, so this bundle closes no complete
third-word child and no normalized parent. The global frontier therefore
remains at 38 unresolved normalized parents, and the exact value remains 15 or
16.

The next proof step is to seek checked nontrivial DRAT certificates for the
166 residual branches. Branches that remain hard after proof-producing solver
runs can be subdivided by a fifth-word orbit split.
