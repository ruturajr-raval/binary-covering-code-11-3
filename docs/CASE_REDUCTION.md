# Certified Case Reduction

## Complete Parent Partition

The canonical two-word construction partitions every hypothetical 15-word
cover into 150 cases. Each case fixes zero, a closest-pair endpoint, and the
first selected orbit representative under the stabilizer of that endpoint.
The partition and its independent reconstruction are documented in
`docs/TWO_WORD_CASES.md`.

## Stage 1

The first certified ledger classifies all 150 cases as follows:

| Reason | Cases |
| --- | ---: |
| Exact orbit LP infeasibility | 80 |
| Exact integer orbit-profile infeasibility | 2 |
| Standalone checked DRAT proof | 1 |
| Minimum distance at most 5 | 4 |
| Closest-pair checked DRAT proof | 14 |
| Stage-1 residual | 49 |

The categories are disjoint and checked in a fixed precedence order by
`tools/verify_case_reduction.py`. Its retained outputs are:

- `evidence/case-reduction-stage1.json`
- `evidence/residual-two-word-cases.json`

The summary records hashes for the orbit LP certificates, integer-profile
certificates, distance theorem, standalone proof check, and closest-pair proof
index used to produce the ledger.

## Advanced Normalization

Maximum-degree normalization removes five of the 49 residual cases by a
direct graph-degree contradiction. The remaining normalized cases receive a
third-word stabilizer split. Six parent formulas have retained checked DRAT
proofs:

```text
w1-weight7-intersection0
w4-weight6-intersection0
w4-weight6-intersection1
w4-weight6-intersection2
w5-weight5-intersection1
w5-weight5-intersection2
```

The first four use the separately certified matching property. The last two
do not.

The final retained normalized ledger is:

| Advanced reason | Cases |
| --- | ---: |
| Maximum-degree contradiction | 5 |
| Checked third-word DRAT proof | 6 |
| Normalized residual | 38 |

Combining both stages, 112 normalized branches are closed and 38 remain. The
advanced normalization does not claim that each corresponding unrestricted
parent CNF is itself unsatisfiable. The residual distribution by minimum
distance is:

```text
d = 1: 10 cases
d = 2: 12 cases
d = 3: 10 cases
d = 4:  6 cases
```

The machine-readable outputs are:

- `evidence/case-reduction-summary.json`
- `evidence/normalized-residual-two-word-cases.json`

The final summary also records hashes for the maximum-degree classification
and the complete third-word proof index.

## Proof Authentication

Every retained SAT proof in the ledgers is linked to:

1. a hashed DIMACS formula;
2. a compressed DRAT trace;
3. solver metadata;
4. an independent `drat-trim` check record;
5. the checker commit
   `2e3b2dc0ecf938addbd779d42877b6ed69d9a985`.

The case-reduction verifiers rehash these files before accepting a closure.
`make proof-checker` fetches that exact checker revision and builds it in the
ignored `build/` directory.

## What Remains

The 38 residual parent cases still represent complete families of candidate
codes. No SAT model has been found in them, but bounded timeouts are not
mathematical evidence. Determining the exact covering number still requires
either:

- one independently verified 15-word cover; or
- checked exclusions covering all 38 residual cases.
