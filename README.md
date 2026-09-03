# Binary Covering Code `K_2(11,3)`

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22260709.svg)](https://doi.org/10.5281/zenodo.22260709)

Certificate-oriented search for the exact value of the binary covering number
`K_2(11,3)`, currently bounded by `15 <= K_2(11,3) <= 16`.

This repository verifies a known 16-word cover and records a complete
150-branch normalization of the size-15 search, with 112 certified normalized
branch closures and 38 unresolved branches. Within four selected hard
third-word children, a further 350-branch split has 184 checked closures and
166 residual branches. No complete child or normalized parent is closed by
that split, so the exact value remains open.

## The Problem

Let `F_2^11` be the set of all 2,048 binary words of length 11. A code
`C` has covering radius at most 3 when every word in `F_2^11` is within
Hamming distance 3 of at least one codeword in `C`.

The covering number is

```text
K_2(11,3) = min {|C| : C is a radius-3 cover of F_2^11}.
```

The open one-unit gap asks whether a 15-word cover exists:

```text
15 <= K_2(11,3) <= 16.
```

A valid 15-word code would prove `K_2(11,3) = 15`. A checked proof that no
15-word code exists, together with a verified 16-word code, would prove
`K_2(11,3) = 16`.

## Origin And History

Covering codes are a classical part of coding theory. They ask how sparsely
one can place codewords while keeping every ambient word close to the code.
They are related to data compression, test design, combinatorial coverings,
and domination problems in Hamming graphs.

The binary tables maintained by Gabor Keri record the one-unit interval
`15-16` for length 11 and radius 3. The lower entry is attributed to Keri's
2006 computation and the upper entry to the Graham-Sloane construction line
from 1985. The table PDF was generated in 2009 and the table site was last
revised in 2011.

A September 2, 2026 audit found no later primary source closing this exact
cell. A recent Lean covering-code database does not currently certify the
table's `15-16` interval, and a recent semidefinite hierarchy reaches only
`12.4700` numerically for this cell. The old lower computation therefore
needs a modern proof certificate even if the final value is 16.

## Starting Frontier

| Item | Status |
| --- | --- |
| Ambient words | 2,048 |
| Radius-3 ball size | 232 |
| Published lower bound | 15 |
| Published upper bound | 16 |
| Exact value | Open |
| Gap present in current table | 1 |

The repository starts from the table interval rather than treating either
endpoint as newly established here.

## Work Completed

The repository now contains a checked construction baseline and a layered
impossibility frontier:

1. A deterministic parity-check search reconstructs a 16-word linear cover.
2. Direct enumeration, a standalone verifier, and syndrome-space analysis all
   confirm covering radius exactly 3.
3. Exact and compact at-most-15 CNF encodings pass structural and semantic
   audits. The smaller compact formula has 9,464 variables and 26,804 clauses.
4. Translation and coordinate symmetry give a complete 150-case canonical
   two-word partition.
5. Exact rational Farkas certificates exclude 80 orbit-profile cases.
6. Exact integer-profile enumeration excludes two more cases.
7. Shell and parity-refined Delsarte identities prove that every hypothetical
   cover has at least 28 pairs at distance at most 6, at least 11 pairs at
   distance at most 5, and minimum distance at most 5.
8. A modular identity proves total pair-ball overlap at least 1,712 and total
   triple-ball overlap at least 280.
9. One standalone proof and 14 closest-pair proofs have checked DRAT traces.
10. Maximum-degree normalization eliminates five further residual cases and
    certifies a matching condition for 34 others.
11. The pointwise stabilizers of the fixed pairs produce 3,238 audited
    third-word orbits across the 49 stage-1 residual parents.
12. Six third-word formulas have checked DRAT traces, four using the certified
    matching condition and two without it.
13. The final exact ledger closes 112 normalized branches from the 150-branch
    canonical cover and leaves 38 normalized residual branches.
14. Four selected hard third-word children have a complete 350-branch
    fourth-word orbit split. Checked RUP certificates close 184 branches and
    leave 166 unresolved, without closing any complete child or normalized
    parent.
15. Construction searches have not found a 15-word cover. The best retained
    near-cover leaves 28 ambient words uncovered.

The retained baseline code is:

```text
00000000000
00010001001
00101010101
00111011100
01001101011
01011100010
01100111110
01110110111
10001001000
10011000001
10100011101
10110010100
11000100011
11010101010
11101110110
11111111111
```

## What Was Achieved

This repository independently verifies the known upper bound

```text
K_2(11,3) <= 16.
```

It also establishes a reproducible structural and proof-checked reduction of
the size-15 search:

```text
150 canonical parent cases
112 certified branch closures
38 normalized residual branches
```

The retained fourth-word refinement additionally establishes:

```text
4 selected hard third-word children
350 exhaustive fourth-word branches
184 checked RUP closures
166 unresolved fourth-word branches
0 complete third-word children closed
```

The exact value remains open. No 15-word code has been found, and the retained
proofs do not yet exclude all 15-word codes. The published interval therefore
remains `15 <= K_2(11,3) <= 16`.

| Question | Outcome |
| --- | --- |
| Is the retained 16-word cover valid? | Yes, by two direct enumeration paths and a syndrome-space cross-check. |
| Has a valid 15-word cover been found? | No. |
| Are the size-15 formulas audited? | Yes, for both the full and compact encodings. |
| What exact structural constraints were proved? | Any hypothetical 15-word cover has minimum distance at most 5, pair-ball overlap at least 1,712, and triple-ball overlap at least 280. |
| Is the normalized branch cover complete? | Yes, all hypothetical 15-word covers enter one of 150 canonical parent branches. |
| How much of that cover is certified closed? | 112 normalized branch closures have independently checkable certificates or checked DRAT traces. |
| What remains unresolved? | 38 normalized residual branches, explicitly listed and authenticated. |
| What does the fourth-word bundle add? | It closes 184 of 350 exhaustive fourth-word branches within four selected hard third-word children. |
| Does that bundle close a complete child or parent? | No. All four selected children and all 38 residual normalized parents remain open. |
| Was a new lower bound proved? | No. |
| Is `K_2(11,3)` determined? | No. The exact value remains either 15 or 16. |

## Why It Matters

Closing a one-unit covering-code gap gives an exact extremal value rather than
another heuristic benchmark. A construction would be a tiny certificate that
anyone can check directly. A lower-bound proof would provide a reusable model
for proof-logged set-cover exclusions in highly symmetric Hamming spaces.

The current reductions already provide reusable components: exact orbit
averaging, integer profile certificates, closest-pair normalization,
stabilizer-aware SAT formulas, maximum-degree graph reductions, and
independently checked proof traces. The same pattern applies to domination and
covering problems whose candidate sets are metric balls in a finite
vertex-transitive graph.

## Search Strategy

The work proceeds on two independent routes.

### Construction Route

- Start from the verified 16-word linear cover.
- Search nonlinear 15-word codes with the targeted breakout implementation,
  then apply exact large-neighborhood repair to the strongest near-covers.
- Partition candidates by distance distribution, translation-normalized
  profiles, and stabilizer type.
- Independently verify every candidate before retaining it.

### Impossibility Route

- Encode one Boolean variable per possible codeword.
- Require exactly 15 selected codewords.
- Add one coverage clause for every ambient word.
- Fix the all-zero codeword by translation symmetry.
- Add sound profile and symmetry partitions only when each partition has an
  independently checked completeness argument.
- Use the complete six-case minimum-weight partition to remove translation and
  coordinate-permutation symmetry before longer proof-producing runs.
- Refine those cases into the complete 150-case canonical two-word orbit
  partition when the first symmetry layer remains difficult.
- Apply exact orbit-average incidence constraints; retained rational
  certificates exclude 80 cases and identify 70 profile-feasible survivors.
- Exhaust the integer orbit profiles in those survivors; two more cases are
  excluded and 68 retain feasible aggregate profiles.
- Use exact shell and parity-refined Delsarte certificates to prove minimum
  distance at most 5, eliminating the complete weight-6 branch.
- Normalize at a maximum-degree vertex in the minimum-distance graph.
- Use the fixed-pair stabilizer to select a canonical third-word orbit.
- Apply the matching constraint only in cases where maximum-degree
  normalization proves it.
- Split selected hard third-word children into exhaustive fourth-word orbits.
- Retain only branch exclusions with proof traces accepted by the separately
  pinned checker.
- Continue proof-producing runs on the 166 residual fourth-word branches, then
  extend the split where needed across the remaining live children.

## Limitations

- The current 16-word code reproduces the known upper bound.
- The retained 15-word near-cover still leaves 28 ambient words uncovered.
- Thirty-eight normalized residual branches remain unresolved.
- The retained fourth-word bundle closes 184 branches but leaves 166 branches
  open and closes no complete third-word child or normalized parent.
- A solver timeout is not evidence that a 15-word code is impossible.
- CP-SAT `INFEASIBLE` without a proof trace is not promoted to a theorem.
- Fixing the all-zero codeword is sound only because translating a binary code
  preserves covering radius and code size.
- The overlap bound is sharp for the retained linear row system, but its three
  sharp distance distributions are not claimed to be realizable covers.
- The 2006 lower-bound computation has not yet been independently reconstructed
  or converted into a retained proof certificate.
- The prior-art audit is dated 2026-09-02 and must be refreshed before any
  novelty claim.
- No external mathematical review has occurred.
- Fresh replay still requires network access to retrieve hash-locked Python
  wheels and the pinned checker source. A self-contained third-party artifact
  archive remains future work.

## Reproduction

The direct verifiers require Python 3.9 or newer and use only the standard
library. Exact formula generation and certificate replay additionally require
`python-sat` and `highspy`. The hash-locked replay environment supports CPython
3.9 through 3.12. Proof replay also requires Git, Make, and a C compiler.
`make proof-checker` fetches and builds the pinned checker revision.
Proof verification reconstructs transient formulas and validates retained
proof identities without rewriting the retained evidence.

`evidence/fourth-word-rup-revision-v1.json` binds the proof index, replay
attestation, bundle manifest, and release manifest to a certified Git revision
after clean-checkout finalization. Its clean-checkout record includes the exact
replay commands and SHA-256 hashes of the Git, Make, and Python executables used
for certification.

Create an environment with all proof-replay dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -I -m pip install --isolated --no-cache-dir \
  --require-hashes --only-binary=:all: --no-deps \
  --index-url https://pypi.org/simple -r requirements-replay.txt
```

```bash
make test PYTHON=.venv/bin/python
make proof-checker
make verify-baseline
make verify-independent
make analyze-baseline
make distance-bounds
make overlap-bound
make cnf
make audit-cnf
make audit-compact-cnf PYTHON=.venv/bin/python
make audit-cases
make audit-two-word-cases
make audit-min-distance-branches PYTHON=.venv/bin/python
make verify-orbit-certificates PYTHON=.venv/bin/python
make verify-integer-profile-certificates PYTHON=.venv/bin/python
make verify-residual-case PYTHON=.venv/bin/python
make audit-min-distance-proofs PYTHON=.venv/bin/python
make audit-third-word-cases PYTHON=.venv/bin/python
make max-degree-reduction PYTHON=.venv/bin/python
make audit-third-word-proofs PYTHON=.venv/bin/python
make case-reduction PYTHON=.venv/bin/python
make audit-third-word-child-frontier PYTHON=.venv/bin/python
make audit-fourth-word-hard-frontier PYTHON=.venv/bin/python
make audit-fourth-word-rup-plan PYTHON=.venv/bin/python
make check-fourth-word-rup-proof-index PYTHON=.venv/bin/python
make audit-fourth-word-rup-proofs PYTHON=.venv/bin/python
make verify-release-manifest PYTHON=.venv/bin/python
make native-test
make local-search-smoke
```

Install the optional exact-search dependency with:

```bash
.venv/bin/python -m pip install -r requirements-solver.txt
make solver-test PYTHON=.venv/bin/python
make search-smoke PYTHON=.venv/bin/python
```

Run `make sat-smoke PYTHON=.venv/bin/python` for the optional CDCL portfolio
smoke test.

## Current Result Status

The current supported claim is:

- a three-path verification of a known 16-word cover;
- audited exact and compact size-15 formulas;
- exact distance and overlap constraints for any hypothetical 15-word cover;
- a complete 150-case canonical parent partition;
- independently checkable certificates closing 112 normalized branches;
- an explicit, hashed frontier of 38 unresolved normalized branches;
- a complete 350-branch fourth-word split within four selected hard children;
- checked RUP certificates closing 184 of those branches, with 166 unresolved
  and no complete child or parent closure.

This is substantive progress on the proof frontier, not a determination of
`K_2(11,3)`.

A new-result announcement requires one of these outcomes:

1. A 15-word code accepted by both the direct and independent verifier,
   mutation tests, a refreshed novelty audit, and external review.
2. A complete size-15 case cover with checked proof traces for every case,
   plus the verified 16-word construction, a refreshed novelty audit, and
   external review.

## Dissemination

After a result passes its gate, the release package should include a tagged
repository version, durable archive, machine-readable certificate, independent
checker, technical manuscript, exact claim statement, and notification to the
maintainers of the covering-code tables and formal database.

## References

- Gabor Keri, tables of bounds for covering codes:
  `https://old.sztaki.hu/~keri/codes/`
- Binary table PDF:
  `https://old.sztaki.hu/~keri/codes/2_tables.pdf`
- Gerard Cohen, Iiro Honkala, Simon Litsyn, and Antoine Lobstein,
  *Covering Codes*, North-Holland, 1997.
- Dion Gijswijt and Sven Polak, semidefinite bounds for covering codes:
  `https://arxiv.org/abs/2504.01932`
- Formal covering-code database:
  `https://github.com/florath/covering-codes-lean`

## License

Unless otherwise noted, the source code, documentation, generated
certificates, proof traces, and retained project data in this repository are
released under the MIT License. External sources are referenced, not copied.
