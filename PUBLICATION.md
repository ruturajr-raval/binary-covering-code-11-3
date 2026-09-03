# Release Candidate v0.2.0

## What Was Done

This release adds an exhaustive fourth-word orbit split for four selected hard
third-word children. The split contains 350 branches. Checked RUP certificates
close 184 branches and leave 166 unresolved. Each retained proof is bound to
its reconstructed formula, checked by the pinned `drat-trim` revision, and
covered by exact-membership checksum manifests.

## Supported Claim

The retained 16-word code has covering radius 3. Any hypothetical 15-word
cover satisfies the retained exact distance and overlap bounds. The complete
150-branch normalization has 112 certified branch closures and 38 explicitly
listed residual branches. Within four selected hard third-word children under
residual normalized parents, 184 of 350 exhaustive fourth-word branches are
certified unsatisfiable by RUP.

## Not Claimed

- No 15-word cover has been found.
- The remaining 38 normalized branches have not been excluded.
- The 166 residual fourth-word branches have not been excluded.
- No complete third-word child or normalized parent is closed by this bundle.
- The exact value of `K_2(11,3)` remains either 15 or 16.
- Solver timeouts and statuses without retained proof traces are not
  mathematical exclusions.
- No final resolution or theorem-priority claim is made.

## Evidence

`evidence.json` provides the machine-readable evidence map.
`evidence/min-distance-proof-index.json` and
`evidence/third-word-proof-index.json` authenticate the retained proof traces.
`evidence/case-reduction-summary.json` records the final 112/38 ledger.
`evidence/proof-bundle.sha256` authenticates every retained proof artifact.
`evidence/fourth-word-rup-bundle-v1.sha256` authenticates the new fourth-word
index, attestation, classification, plan, and proof tree.
`evidence/fourth-word-rup-revision-v1.json` binds those artifacts to the
certified Git revision `06ecaa7bc28503efd871faf4450005f43e625124`,
tree `4888ad6c5305b5d30d6c4ca3e8435b9c872307b1`, after a clean-checkout
replay completed on 2026-09-03. It records the normalized command sequence,
host-specific self-attested per-command output hashes, and toolchain hashes.
Exact invocation construction is frozen in the certified source tree. The
output hashes include host-dependent text and are not cross-host comparison
targets. Only the revision, final diff, and final status outputs have invariant
semantics checked independently by the record validator.
`release-manifest.sha256` authenticates the principal release files.

## Reproduction

```bash
python3 -m venv .venv
.venv/bin/python -I -m pip install --isolated --no-cache-dir \
  --require-hashes --only-binary=:all: --no-deps \
  --index-url https://pypi.org/simple -r requirements-replay.txt
make test PYTHON=.venv/bin/python
make proof-checker
make verify-residual-case PYTHON=.venv/bin/python
make audit-min-distance-proofs PYTHON=.venv/bin/python
make audit-third-word-proofs PYTHON=.venv/bin/python
make case-reduction PYTHON=.venv/bin/python
make audit-third-word-child-frontier PYTHON=.venv/bin/python
make audit-fourth-word-hard-frontier PYTHON=.venv/bin/python
make audit-fourth-word-rup-plan PYTHON=.venv/bin/python
make audit-fourth-word-rup-proofs PYTHON=.venv/bin/python
make verify-release-manifest PYTHON=.venv/bin/python
```

The proof audit reconstructs every exact CNF, checks every retained trace, and
validates the replay attestation. The release verification also enforces exact
manifest membership, so undeclared additions and missing artifacts fail.

## Limitations And Remaining Work

The 166 residual branches within the selected fourth-word split are the
immediate proof frontier. Even closing all four selected children would leave
other live children under the 38 residual normalized parents. A final
lower-bound result requires a complete checked exclusion cover. The independent
construction route remains open as well.
Fresh replay also requires network access to retrieve hash-locked Python wheels
and the pinned checker source. A self-contained third-party artifact archive
remains future work.
Final certification verification requires a full Git clone containing the
certified source revision. A source archive or shallow checkout cannot verify
that Git revision identity.

## Citation

Citation metadata is provided in `CITATION.cff`, and `.zenodo.json` supplies
the metadata for durable release archival. The stable concept DOI for all
versions is [10.5281/zenodo.22260709](https://doi.org/10.5281/zenodo.22260709).
The citation metadata pairs that concept DOI with repository version `0.2.0`.
Zenodo assigns the version-specific DOI only after the tagged release is
archived, so it cannot be embedded in pre-release metadata.
