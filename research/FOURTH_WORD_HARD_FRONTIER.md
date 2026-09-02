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

No fourth-word branch is considered closed until its audited CNF has a proof
accepted by an independent checker.
