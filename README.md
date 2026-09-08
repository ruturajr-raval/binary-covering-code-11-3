# Binary Covering Number `K_2(11,3)`

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22260709.svg)](https://doi.org/10.5281/zenodo.22260709)

## Project Overview

This repository develops a certificate-oriented search for the exact binary
covering number `K_2(11,3)`. It verifies the known 16-word upper-bound
construction and records a complete normalized size-15 search frontier with
proof-checked exclusions.

| Field | Value |
| --- | --- |
| Author | Ruturaj R Raval |
| Affiliation | Independent Researcher |
| ORCID | [0000-0003-4930-8981](https://orcid.org/0000-0003-4930-8981) |
| Field | Coding theory, finite geometry, and proof-producing SAT |
| Problem | Determine the binary covering number `K_2(11,3)` |
| Current result | 112 certified normalized branch closures among 150 branches, plus 324 of 350 selected fourth-word closures |
| Result type | Significant certified proof frontier with unchanged global bounds |
| Release | `v0.3.1` |
| Audited release commit | `3543518d89d35f57753caa25a8ce73b004c4561b` |
| Version DOI | [`10.5281/zenodo.22647766`](https://doi.org/10.5281/zenodo.22647766) |
| Concept DOI | [`10.5281/zenodo.22260709`](https://doi.org/10.5281/zenodo.22260709) |
| License | MIT for project-original material |

## Problem And Background

Let `F_2^11` be the set of all 2,048 binary words of length 11. A code
`C` has covering radius at most 3 when every word in `F_2^11` is within
Hamming distance 3 of at least one codeword in `C`. The covering number is

```text
K_2(11,3) = min {|C| : C is a radius-3 cover of F_2^11}.
```

Every radius-3 Hamming ball contains 232 words. The unresolved question is
whether 15 such centers suffice:

```text
15 <= K_2(11,3) <= 16.
```

A valid 15-word code would prove `K_2(11,3) = 15`. A checked exclusion of all
15-word codes, together with a verified 16-word code, would prove
`K_2(11,3) = 16`.

Covering codes arise from placing as few codewords as possible while keeping
every ambient word close to the code. They are related to data compression,
test design, combinatorial coverings, finite geometry, and domination
problems in Hamming graphs.

The specific `K_2(11,3)` interval was recorded in published covering-code
tables and construction literature. The historical origin and dated table
updates are identified in the next section.

## Starting Frontier And Longstanding Gap

Gabor Keri's binary covering-code table records the interval `15-16` for
length 11 and radius 3. Its update log dated 2006-01-17 records the lower
bound 15 as a stepwise-refinement result. The table attributes the upper
bound 16 to the Graham-Sloane construction line from 1985. The table PDF was
generated on 2009-10-15, and the latest dated update on the table site is
2011-11-21.

The recorded one-unit interval has therefore remained unclosed for more than
twenty years. A prior-art search refreshed on 2026-09-03, with metadata
rechecked on 2026-09-05 and status assessed through 2026-09-06, found no
later primary source closing this exact table cell.

At audited commit `2ecbf887d7a29a8137da6b476d1f5de93c3936d4`, the Lean
covering-code database certifies only `9-28` for this cell while retaining
`15-16` as historical reference data. The Gijswijt-Polak semidefinite
hierarchy reports `12.4700` numerically in its binary results table. The
historical lower bound therefore still lacks a modern retained proof
certificate even if the final value is 16.

| Starting item | Status |
| --- | --- |
| Ambient words | 2,048 |
| Radius-3 ball size | 232 |
| Published lower bound | 15 |
| Published upper bound | 16 |
| Exact value | Open |
| Recorded gap | 1 |

This project starts from the recorded interval and does not present either
endpoint as newly established.

## Main Result

The project independently reconstructs and verifies a known 16-word cover,
derives exact structural constraints for every hypothetical 15-word cover,
and partitions the size-15 search into 150 normalized parent branches.
Certificates close 112 normalized branches and leave 38 normalized residual
branches.

Four selected unresolved third-word children were then divided into 350
exhaustive fourth-word branches. Checked evidence closes 324 branches:

```text
184 checked RUP closures
166 branches outside that RUP proof class
140 checked solver-generated DRAT closures
324 total certified closures
26 unresolved fourth-word branches
0 complete third-word children closed
```

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

Direct enumeration and syndrome analysis confirm that this code has covering
radius exactly 3. It reproduces the known upper bound:

```text
K_2(11,3) <= 16.
```

For every hypothetical 15-word cover, the retained exact arguments prove:

- at least 28 codeword pairs have distance at most 6;
- at least 11 codeword pairs have distance at most 5;
- the minimum distance is at most 5;
- total pair-ball overlap is at least 1,712; and
- total triple-ball overlap is at least 280.

The exact value remains open. No 15-word code has been found, and the retained
proofs do not exclude all 15-word codes.

| Question | Verified outcome |
| --- | --- |
| Is the retained 16-word cover valid? | Yes, by two direct enumeration paths and a syndrome-space cross-check. |
| Has a valid 15-word cover been found? | No. |
| Are the size-15 formulas audited? | Yes, for both the full and compact encodings. |
| Is the normalized branch cover complete? | Yes, every hypothetical 15-word cover enters one of 150 canonical parent branches. |
| How much of that cover is certified closed? | 112 normalized branches have independently checkable certificates or checked DRAT traces. |
| What remains unresolved? | 38 normalized residual branches, explicitly listed and authenticated. |
| What does the fourth-word bundle add? | It closes 324 of 350 exhaustive branches within four selected unresolved third-word children. |
| Does the fourth-word bundle close a complete child or parent? | No. All four selected children and all 38 residual normalized parents remain open. |
| Was a new global lower bound proved? | No. |
| Is `K_2(11,3)` determined? | No. The value remains either 15 or 16. |

## Method And Proof Architecture

The work uses independent construction and impossibility routes.

### Construction Route

- Reconstruct the verified 16-word linear cover through a deterministic
  parity-check search.
- Verify every retained construction by direct enumeration, a standalone
  verifier, and syndrome-space analysis.
- Search nonlinear 15-word codes with targeted breakout and exact
  large-neighborhood repair.
- Partition candidates by distance distribution, translation-normalized
  profile, and stabilizer type.
- Retain a candidate only after independent verification.

The best retained 15-word near-cover leaves 28 ambient words uncovered.

### Impossibility Route

1. Use one Boolean variable per possible codeword, require exactly 15
   selected words, and add one coverage clause for every ambient word.
2. Fix the all-zero codeword using translation symmetry.
3. Audit exact and compact at-most-15 CNF encodings. The compact formula has
   9,464 variables and 26,804 clauses.
4. Apply the complete six-case minimum-weight partition to remove translation
   and coordinate-permutation symmetry, then refine it to a complete 150-case
   canonical two-word partition.
5. Apply exact orbit-average incidence constraints. Rational Farkas
   certificates exclude 80 orbit-profile cases and leave 70
   profile-feasible cases.
6. Exhaust exact integer orbit profiles in the survivors. Two additional
   cases are excluded and 68 retain feasible aggregate profiles.
7. Apply shell and parity-refined Delsarte identities to exclude the complete
   weight-6 branch and prove the distance constraints stated above.
8. Use a modular identity to prove the pair-ball and triple-ball overlap
   bounds.
9. Retain one standalone proof and 14 closest-pair proofs with checked DRAT
   traces.
10. Normalize at a maximum-degree vertex in the minimum-distance graph.
    This removes five further residual cases and certifies a matching
    condition for 34 others.
11. Compute 3,238 audited third-word orbits across the 49 stage-1 residual
    parents under the pointwise stabilizers of their fixed pairs.
12. Check six third-word formulas by DRAT, four with the certified matching
    condition and two without it.
13. Produce the exact ledger of 112 certified normalized closures and 38
    residual normalized branches.
14. Split four selected unresolved third-word children into 350 exhaustive
    fourth-word orbits.
15. Close 184 fourth-word branches by checked RUP certificates and 140 more
    by independently replayed solver-generated DRAT proofs.
16. Preserve the 26 residual fourth-word branches for audited fifth-word
    subdivision while continuing independent construction search.

Only sound profile and symmetry partitions with independently checked
completeness arguments enter the theorem. Solver statuses without accepted
proof evidence are not promoted to mathematical claims.

## Verification And Evidence

The verification architecture combines direct enumeration, syndrome
analysis, exact profile certificates, audited formula generation, RUP replay,
and independently checked DRAT traces.

The compact report replay uses Python 3 on a commodity workstation. Full
proof replay additionally requires the archived proof payload, pinned proof
checkers, substantial local storage, and longer CPU-bound runs. Exploratory
construction searches are not part of the claim.

The first fourth-word bundle is bound by
`evidence/fourth-word-rup-revision-v1.json` to certified Git revision
`06ecaa7bc28503efd871faf4450005f43e625124`, tree
`4888ad6c5305b5d30d6c4ca3e8435b9c872307b1`. Its clean-checkout replay
completed on 2026-09-03. The record includes the normalized command sequence,
host-specific self-attested output byte counts and SHA-256 hashes, and
SHA-256 hashes of the Git, Make, and Python executables used for
certification. Exact invocation construction is frozen in the certified
source tree. Host-dependent output text is not expected to hash identically
across equivalent systems; the record validator separately checks the
invariant revision, final diff, and final status semantics.

The solver-generated v2 evidence is indexed by
`proof-expansion/evidence/fourth-word-solver-drat-index-v2.json`, whose
SHA-256 is
`c528b1358504bad39a3b8770285913d71da0a9ff02e77561d266b2d5dcb11d7f`.
Its exact-membership manifest is
`proof-expansion/evidence/fourth-word-solver-drat-bundle-v2.sha256`, whose
SHA-256 is
`822e78b40e4393ce9b78c8725227f0dd41ab11dd1dc91f4d0bd6d696c7c54786`.
The 420-artifact proof-directory digest is
`44504c6320ac22ad62507f70222c2e8b9e6a51977f27ca3c936019c9f657f08f`.
All 140 retained proofs were independently replayed on 2026-09-03.

The v2 index preserves exact production hashes. Cross-platform replay still
requires the same Python-SAT version, exact formula hashes, exact retained
proof bytes, and matching normalized checker output. The certified revision
record includes production and replay-host solver-environment records,
including the replay Python executable, package tree, native modules,
platform, and checker hash.

`proof-expansion/evidence/fourth-word-solver-drat-revision-v2.json` binds the
certified source revision, normalized replay outputs, and strict
single-parent finalization commit. It is checked by
`release-tools/manage_fourth_word_solver_drat_revision.py`.
`release.json` is the authoritative readiness record.

## Reproduction

The direct verifiers require Python 3.9 or newer and use only the standard
library. Exact formula generation and certificate replay additionally require
`python-sat` and `highspy`. The hash-locked replay environment supports
CPython 3.9 through 3.12. Proof replay also requires Git, Make, and a C
compiler. `make proof-checker` fetches and builds the pinned checker revision.
Proof verification reconstructs transient formulas and validates retained
proof identities without rewriting retained evidence.

Create the proof-replay environment:

```bash
python3 -m venv .venv
.venv/bin/python -I -m pip install --isolated --no-cache-dir \
  --require-hashes --only-binary=:all: --no-deps \
  --index-url https://pypi.org/simple -r requirements-replay.txt
```

Build and verify the paper-inclusive release assets with Tectonic 0.16.9:

```bash
make archival-release
```

The Makefile fixes `SOURCE_DATE_EPOCH` to the release date so repeated clean
builds produce the same PDF bytes.

Resource profile: the compact report replay is CPU-only on an ordinary
workstation. Full RUP and DRAT replay requires substantially more local
storage and CPU time, as described in the verification section.

Run the retained verification targets:

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
make -C proof-expansion test
make -C proof-expansion audit-plan
make -C proof-expansion audit-bundle-structure
make -C proof-expansion audit-bundle
.venv/bin/python tools/verify_checksum_manifest.py \
  proof-expansion/evidence/fourth-word-solver-drat-bundle-v2.sha256 \
  --path proof-expansion/evidence/fourth-word-solver-drat-plan-v2.json \
  --path proof-expansion/evidence/fourth-word-solver-drat-index-v2.json \
  --tree proof-expansion/evidence/proofs/fourth-word-solver-drat-v2
.venv/bin/python \
  release-tools/manage_fourth_word_solver_drat_revision.py \
  --verify --release-revision "$(git rev-parse HEAD)"
```

Install and exercise the optional exact-search dependency:

```bash
.venv/bin/python -m pip install -r requirements-solver.txt
make solver-test PYTHON=.venv/bin/python
make search-smoke PYTHON=.venv/bin/python
```

Run the optional CDCL portfolio smoke test with:

```bash
make sat-smoke PYTHON=.venv/bin/python
```

## Claims

The repository supports the following claims:

- the retained known 16-word cover has covering radius exactly 3;
- the exact and compact size-15 formulas pass the documented audits;
- the stated distance and overlap constraints hold for every hypothetical
  15-word cover;
- the 150-case canonical parent partition is complete;
- accepted evidence closes 112 normalized parent branches;
- the authenticated normalized residual frontier contains 38 branches;
- the four selected children have a complete 350-branch fourth-word split;
  and
- checked RUP and DRAT evidence closes 324 of those 350 branches.

The fourth-word work closes no complete selected child or normalized parent.
This is a certified partial reduction, not a new global bound or an exact
determination of `K_2(11,3)`.

A final exact-value claim requires one of these outcomes:

1. A 15-word code accepted by the direct and independent verifiers, mutation
   tests, a refreshed novelty audit, and external mathematical review.
2. A complete size-15 case cover with checked proof traces for every case,
   together with the verified 16-word construction, a refreshed novelty
   audit, and external mathematical review.

## Limitations And Nonclaims

This project does not construct a 15-word covering code, does not change the
global interval, does not settle the exact parent problem, and does not claim
completed external mathematical review.

- The 16-word construction reproduces a known upper bound and is not claimed
  as new.
- No valid 15-word covering code has been found.
- Nonexistence of all 15-word covering codes has not been proved.
- No new global lower bound is claimed.
- The exact value remains either 15 or 16.
- Thirty-eight normalized parent branches remain unresolved.
- The fourth-word bundles leave 26 branches open and close no complete
  third-word child or normalized parent.
- The retained near-cover leaves 28 ambient words uncovered.
- A solver timeout is not evidence of impossibility.
- CP-SAT `INFEASIBLE` without a proof trace is not promoted to a theorem.
- Fixing the all-zero word is sound only because translation preserves
  covering radius and code size.
- The overlap bound is sharp for the retained linear row system, but its
  three sharp distance distributions are not claimed to be realizable
  covers.
- The 2006 lower-bound computation has not been independently reconstructed
  or converted into a retained modern proof certificate.
- The prior-art audit is dated 2026-09-03. A materially delayed novelty claim
  requires a refreshed search.
- No external mathematical review is claimed.
- Fresh replay requires network access to retrieve hash-locked Python wheels
  and pinned checker source. A self-contained third-party artifact archive
  remains future work.
- Final certification verification requires a full Git clone containing the
  certified source revision. A source archive or shallow checkout is
  insufficient for that revision-identity check.
- The retained clean-replay record is a host-specific self-attestation, not a
  third-party signature. GitHub replays on `main` and release tags provide
  separate public executions tied to the released commit.

## Significance And Use

Closing a one-unit covering-code gap gives an exact extremal value rather than
another heuristic benchmark. A 15-word construction would be a small
certificate that can be checked directly. A complete lower-bound proof would
provide a reusable model for proof-logged set-cover exclusions in highly
symmetric Hamming spaces.

The current work already supplies reusable components: orbit averaging,
integer profile certificates, closest-pair normalization, stabilizer-aware
SAT formulas, maximum-degree graph reductions, and independently replayed
proof traces. The same architecture can be adapted to domination and covering
problems whose candidate sets are metric balls in a finite vertex-transitive
graph.

## Remaining Work And Future Directions

The exact value remains open. The next route is an audited fifth-word orbit
split of the 26 residual fourth-word branches, while construction search
continues independently.

1. Subdivide the 26 residual fourth-word branches by audited fifth-word
   orbits.
2. Expand proof coverage until complete selected children and normalized
   parents close.
3. Resolve all 38 normalized residual parent branches, or produce a valid
   15-word code.
4. Continue independent nonlinear construction search and exact repair from
   the strongest retained near-covers.
5. Independently reconstruct or certificate the historical lower-bound
   computation.
6. Build a self-contained third-party replay archive.
7. Refresh the novelty audit and seek external mathematical review before an
   exact-value announcement.

Notification of a bound change to table and formal-database maintainers
remains conditional on satisfying one of the exact-result gates in the
Claims section.

## Repository Layout

- `paper/main.tex` is the technical progress report source.
- `paper/ARXIV_METADATA.md` records submission metadata.
- `dist/arxiv/binary-covering-code-11-3.tar.gz` is the deterministic report
  source package. Run `python3 replay.py` inside the extracted archive for
  its compact standard-library replay.
- `dist/release/` contains the versioned compiled PDF, paper-source archive,
  and `SHA256SUMS` for the paper-inclusive archival release.
- `evidence/` contains branch records, retained certificates, and the v1
  replay attestation.
- `proof-expansion/evidence/` contains the v2 DRAT index, exact-membership
  manifest, proof artifacts, and certified revision record.
- `release-tools/manage_fourth_word_solver_drat_revision.py` validates the v2
  certified revision record.
- `PUBLICATION.md` and `docs/LITERATURE_AUDIT.md` document the claim boundary
  and dated literature audit.
- `CITATION.cff` contains citation metadata.
- `RELEASE_NOTES.md` records release history.
- `release.json` records authoritative release readiness.

## Publication Citation And Archive

The public repository is
[`ruturajr-raval/binary-covering-code-11-3`](https://github.com/ruturajr-raval/binary-covering-code-11-3).
The paper-inclusive archival release is
[`v0.3.1`](https://github.com/ruturajr-raval/binary-covering-code-11-3/releases/tag/v0.3.1).
Its audited release commit is
`3543518d89d35f57753caa25a8ce73b004c4561b`.

The exact archival patch is identified by version DOI
[`10.5281/zenodo.22647766`](https://doi.org/10.5281/zenodo.22647766).
All repository versions are collected under concept DOI
[`10.5281/zenodo.22260709`](https://doi.org/10.5281/zenodo.22260709).

Release `v0.3.1` is an archival and documentation patch. It adds an
explicitly named compiled PDF, a deterministic paper-source archive, and a
checksum file suitable for GitHub and Zenodo. The theorem, proof
certificates, retained data, branch counts, and computations are unchanged
from `v0.3.0`.

The GitHub release and Zenodo record were published on 2026-09-07. The PDF,
paper-source archive, and checksum manifest were downloaded from both public
services and matched the local release assets by size and SHA-256.

The complete earlier proof payload is archived at
[`10.5281/zenodo.22302261`](https://doi.org/10.5281/zenodo.22302261) as
`ruturajr-raval/binary-covering-code-11-3-v0.2.0.zip`, with SHA-256
`750003eba2e9f9baf5fee9ed93c679b3661daf6d8c68ca40eeb681202b5e72ff`.

The report presents a certified frontier reduction, not a new bound or exact
value. GitHub and Zenodo are the current dissemination baseline.
Citation metadata is in `CITATION.cff`, and release history is in
`RELEASE_NOTES.md`.

## Authorship

Ruturaj R Raval<br>
Independent Researcher<br>
ORCID: [`0000-0003-4930-8981`](https://orcid.org/0000-0003-4930-8981)

## Licensing And Provenance

Unless otherwise noted, project-original source code, documentation,
generated certificates, proof traces, and retained project data are released
under the MIT License. External sources are referenced rather than copied.

The 16-word code reproduces a known construction and is not claimed as
original. Project code, certificates, proof records, and documentation were
produced independently. Historical table entries and prior publications are
cited for provenance.

## References

- Gabor Keri, [tables of bounds for covering
  codes](https://old.sztaki.hu/~keri/codes/).
- Keri, [table update log](https://old.sztaki.hu/~keri/codes/index.htm),
  including the 2006-01-17 lower-bound entry.
- Keri, [binary table PDF](https://old.sztaki.hu/~keri/codes/2_tables.pdf).
- Ronald L. Graham and Neil J. A. Sloane, [On the Covering Radius of
  Codes](https://doi.org/10.1109/TIT.1985.1057039), *IEEE Transactions on
  Information Theory* 31(3), 385-401, 1985.
- Gerard Cohen, Iiro Honkala, Simon Litsyn, and Antoine Lobstein,
  *Covering Codes*, North-Holland, 1997.
- Dion Gijswijt and Sven Polak, [Semidefinite lower bounds for covering
  codes](https://arxiv.org/abs/2504.01932).
- [Formal covering-code database at audited commit
  `2ecbf887d7a29a8137da6b476d1f5de93c3936d4`](https://github.com/florath/covering-codes-lean/tree/2ecbf887d7a29a8137da6b476d1f5de93c3936d4).
