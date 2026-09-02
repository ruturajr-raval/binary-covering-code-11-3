# Release v0.1.1

## What Was Done

This archival patch adds a compact results summary to the README and refreshes
the release and citation metadata after Zenodo integration was enabled. The
verified 16-word cover, structural certificates, checked DRAT traces, 112
certified normalized branch closures, and 38 unresolved branches are
unchanged.

## Supported Claim

The retained 16-word code has covering radius 3. Any hypothetical 15-word
cover satisfies the retained exact distance and overlap bounds. The complete
150-branch normalization has 112 certified branch closures and 38 explicitly
listed residual branches.

## Not Claimed

- No 15-word cover has been found.
- The remaining 38 normalized branches have not been excluded.
- The exact value of `K_2(11,3)` remains either 15 or 16.
- Solver timeouts and statuses without retained proof traces are not
  mathematical exclusions.
- No final resolution or theorem-priority claim is made.

## Evidence

`evidence.json` provides the machine-readable evidence map.
`evidence/min-distance-proof-index.json` and
`evidence/third-word-proof-index.json` authenticate the retained proof traces.
`evidence/case-reduction-summary.json` records the final 112/38 ledger.
`evidence/proof-bundle.sha256` authenticates every retained proof artifact,
and `release-manifest.sha256` authenticates the principal release files.

## Reproduction

```bash
python3 -m venv .venv
.venv/bin/python -m pip install \
  -r requirements-sat.txt \
  -r requirements-proof.txt
make test PYTHON=.venv/bin/python
make proof-checker
make audit-min-distance-proofs PYTHON=.venv/bin/python
make audit-third-word-proofs PYTHON=.venv/bin/python
make case-reduction PYTHON=.venv/bin/python
```

The audit targets reconstruct their exact CNFs before checking the retained
proof traces, so the replay does not depend on ignored local build files.

## Limitations And Remaining Work

The 38 residual branches are the immediate proof frontier. A final lower-bound
result requires checked exclusions for every residual branch. The independent
construction route remains open as well.

## Citation

Citation metadata is provided in `CITATION.cff`, and `.zenodo.json` supplies
the metadata for durable release archival. The archived `v0.1.1` release DOI
is [10.5281/zenodo.22260710](https://doi.org/10.5281/zenodo.22260710). The
stable concept DOI for all versions is
[10.5281/zenodo.22260709](https://doi.org/10.5281/zenodo.22260709).
