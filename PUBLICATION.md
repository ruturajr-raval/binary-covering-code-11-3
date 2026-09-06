# Release Dossier v0.3.0

## Release Identity

| Field | Value |
| --- | --- |
| Title | Certified Branch Reductions for the Binary Covering Number K_2(11,3) |
| Author | Ruturaj R Raval |
| Affiliation | Independent Researcher |
| ORCID | [0000-0003-4930-8981](https://orcid.org/0000-0003-4930-8981) |
| Tagged release | [`v0.3.0`](https://github.com/ruturajr-raval/binary-covering-code-11-3/releases/tag/v0.3.0) |
| Release date | 2026-09-05 |
| Audited release commit | `4748983fc35d299b14d58522a75bcc9aa6c88b28` |
| Certified full-proof source revision | `b0714133780d9411ece7b815e559658fcaa74851` |
| Version DOI | [`10.5281/zenodo.22332416`](https://doi.org/10.5281/zenodo.22332416) |
| Concept DOI | [`10.5281/zenodo.22260709`](https://doi.org/10.5281/zenodo.22260709) |
| Archive status | Technical report and repository snapshot published; full proof payload archived separately |
| License | MIT for project-original material |

## Claim-Safe Public Summary

Release `v0.3.0` documents a certified partial reduction of the unresolved
size-15 search for `K_2(11,3)`. A complete 150-branch normalized parent
partition has 112 certified normalized branch closures and 38 residual
branches. Within four selected unresolved third-word children, checked RUP and
solver-generated DRAT evidence closes 324 of 350 exhaustive fourth-word
branches, leaving 26 and closing no complete selected child or normalized
parent. The exact value remains open, and the known interval remains
`15 <= K_2(11,3) <= 16`.

## Background

The binary covering number `K_2(11,3)` asks for the smallest number of
length-11 binary words whose radius-3 Hamming balls cover all 2,048 ambient
words. The established table interval is

```text
15 <= K_2(11,3) <= 16.
```

A 15-word cover would settle the value at 15. A checked exclusion of every
15-word cover, together with the verified 16-word construction, would settle
it at 16.

## What This Release Adds

This release adds a publication-ready technical report and a deterministic
arXiv source archive for the certified partial result already represented by
the proof records:

- `paper/main.tex` gives the mathematical definitions, exact structural
  inequalities, symmetry reductions, closure ledgers, certificate model, and
  limitations.
- `paper/ARXIV_METADATA.md` records the exact submission title, abstract,
  categories, and final manual checks.
- `dist/arxiv/binary-covering-code-11-3.tar.gz` is a deterministic,
  allowlisted source archive.
- `paper/replay.py` checks the archive's internal manifest, verifies the
  compact evidence, checks the 16-word construction, and regenerates the
  exact distance and overlap certificates using standard-library Python.
- `evidence/technical-report-summary-v1.json` binds the report's principal
  counts to the retained evidence by SHA-256.

The full RUP and DRAT proof payloads remain in the immutable v0.2.0 Zenodo
deposit at version DOI `10.5281/zenodo.22302261`. Its archived file is
`ruturajr-raval/binary-covering-code-11-3-v0.2.0.zip`, with SHA-256
`750003eba2e9f9baf5fee9ed93c679b3661daf6d8c68ca40eeb681202b5e72ff`.
The compact archive includes the v0.2.0 root release manifest, the root proof
manifest, the fourth-word RUP manifest, the solver-DRAT v2 manifest, and a
machine-readable Zenodo archive binding.

The v0.3.0 report snapshot is archived at version DOI
`10.5281/zenodo.22332416`. `release.json` binds its repository ZIP, release
commit, GitHub source and PDF assets, sizes, and checksums.

## Manifest And Asset Verification

Use `release-manifest.sha256` from a clean checkout of tag `v0.3.0` to verify
the tracked report release. `release.json` records:

- the release tag object and audited release commit;
- source and PDF asset names, sizes, and SHA-256 values;
- the Zenodo `v0.3.0` repository snapshot name, size, MD5, and SHA-256;
- the certified full-proof source revision;
- proof-plan, proof-index, and proof-bundle manifest digests; and
- the archived `v0.2.0` proof payload identity and SHA-256.

The frozen `v0.2.0` manifest snapshot is
`evidence/release-manifest-v0.2.0.sha256`, and its Zenodo binding is
`evidence/zenodo-v0.2.0-archive.json`.

## Supported Claims

For every hypothetical 15-word radius-3 cover in the binary 11-cube:

- at least 28 unordered codeword pairs have distance at most 6;
- at least 11 unordered pairs have distance at most 5;
- the minimum distance is at most 5;
- total pair-ball overlap is at least 1,712; and
- total triple-ball overlap is at least 280.

The complete normalized parent partition has:

```text
150 canonical parent branches
112 certified normalized branch closures
38 residual normalized branches
```

Within four selected unresolved third-word children:

```text
350 exhaustive fourth-word branches
184 checked RUP closures
140 checked solver-generated DRAT closures
324 total certified closures
26 unresolved branches
0 complete selected children closed
0 normalized parents closed by this layer
```

## Claim Boundary

- No 15-word covering code has been found.
- The remaining 38 normalized branches have not been excluded.
- The 26 selected fourth-word residual branches have not been excluded.
- The 324 fourth-word closures do not close a complete selected child or
  normalized parent.
- The exact value of `K_2(11,3)` is not determined.
- No new global lower or upper bound is claimed.
- Solver timeouts and statuses without retained proof traces are not
  mathematical exclusions.
- Feasible aggregate orbit profiles are not covering codes.
- The retained local replay records are not third-party signatures.

The known interval remains

```text
15 <= K_2(11,3) <= 16.
```

## Provenance Boundary

The verified 16-word code reproduces a known upper bound and is not claimed as
a new construction. Project code, formulas, certificates, proof records,
replay tools, and documentation are independently produced and MIT licensed.
External sources are cited rather than copied. The retained proof payloads are
bound to their certified source revision and archived release.

## Review Status

The artifact and technical report are released. Internal manifest,
classification, RUP, DRAT, clean-checkout, claim-scope, and manuscript gates
are recorded as passed. The exact-value theorem announcement remains on hold
because 26 selected fourth-word branches, every selected child, and all 38
residual normalized branches remain open. No external mathematical review is
claimed.

## Reproduction

Compact report replay:

```bash
make paper-bundle
make paper-replay
```

The compact replay uses no network access or third-party Python package. It
does not replay the large proof payloads.

The internal manifest does not authenticate an untrusted download. Before
executing `paper/replay.py`, verify the downloaded release asset against the
SHA-256 published with the GitHub release.

The repository-side archive checker compares every member byte-for-byte with
an allowlist from the checked-out repository. It rejects noncanonical paths,
metadata, member types, duplicate entries, and oversized members, and never
executes code taken from the archive under test.

Full repository verification:

```bash
python3 -m venv .venv
.venv/bin/python -I -m pip install --isolated --no-cache-dir \
  --require-hashes --only-binary=:all: --no-deps \
  --index-url https://pypi.org/simple -r requirements-replay.txt
make test PYTHON=.venv/bin/python
make audit-third-word-child-frontier PYTHON=.venv/bin/python
make audit-fourth-word-hard-frontier PYTHON=.venv/bin/python
make audit-fourth-word-rup-plan PYTHON=.venv/bin/python
make verify-baseline verify-independent PYTHON=.venv/bin/python
make distance-bounds overlap-bound PYTHON=.venv/bin/python
make verify-technical-report PYTHON=.venv/bin/python
make verify-release-manifest PYTHON=.venv/bin/python
```

Full replay of the retained RUP and DRAT proofs must use the frozen v0.2.0
source revision, whose pipeline bytes are authenticated by the proof indexes:

```bash
git worktree add --detach build/v0.2.0-proof-replay v0.2.0
cd build/v0.2.0-proof-replay
python3 -m venv .venv
.venv/bin/python -I -m pip install --isolated --no-cache-dir \
  --require-hashes --only-binary=:all: --no-deps \
  --index-url https://pypi.org/simple -r requirements-replay.txt
make audit-fourth-word-rup-proofs PYTHON=.venv/bin/python
make verify-residual-case PYTHON=.venv/bin/python
make audit-min-distance-proofs PYTHON=.venv/bin/python
make audit-third-word-proofs PYTHON=.venv/bin/python
make case-reduction PYTHON=.venv/bin/python
make verify-release-manifest PYTHON=.venv/bin/python
make -C proof-expansion test audit-plan audit-bundle-structure audit-bundle \
  PYTHON=.venv/bin/python
.venv/bin/python tools/verify_checksum_manifest.py \
  proof-expansion/evidence/fourth-word-solver-drat-bundle-v2.sha256 \
  --path proof-expansion/evidence/fourth-word-solver-drat-plan-v2.json \
  --path proof-expansion/evidence/fourth-word-solver-drat-index-v2.json \
  --tree proof-expansion/evidence/proofs/fourth-word-solver-drat-v2
.venv/bin/python -I \
  release-tools/manage_fourth_word_solver_drat_revision.py \
  --verify --release-revision "$(git rev-parse HEAD)"
```

That replay requires a full Git clone, the v0.2.0 proof payloads, network
access for the hash-locked environment, and the pinned checker source.

## Significance

The release replaces an unauthenticated open-ended search with an explicit,
machine-checkable frontier. Future work can extend a complete branch cover
from the 38 normalized residuals and the 26 selected fourth-word residuals,
or independently search for a 15-word construction. The normalization,
orbit-profile, and proof-logged SAT methods also apply to finite covering and
domination problems with large symmetry groups.

## Remaining Work

The immediate local frontier is an audited fifth-word orbit split of the 26
selected residual branches. Even closing all four selected children would
leave other live children below the 38 residual normalized branches. A final
result therefore requires either a verified 15-word construction or a
complete checked exclusion cover.

## Archive And Citation

Citation metadata is in `CITATION.cff`. The all-versions concept DOI is
`10.5281/zenodo.22260709`. The archived v0.3.0 release DOI is
`10.5281/zenodo.22332416`.

The complete earlier RUP and DRAT proof payload is archived at version DOI
`10.5281/zenodo.22302261` as
`ruturajr-raval/binary-covering-code-11-3-v0.2.0.zip`. Its recorded SHA-256 is
`750003eba2e9f9baf5fee9ed93c679b3661daf6d8c68ca40eeb681202b5e72ff`.

Historical release scope is summarized in `RELEASE_NOTES.md`.

## Next Acceptance Gate

An exact-value result requires one of two outcomes:

1. A 15-word code accepted by independent exhaustive verifiers, followed by a
   refreshed novelty audit and external review.
2. Checked proof coverage for all 38 residual normalized branches, together
   with the verified 16-word construction, a refreshed novelty audit, and
   external review.
