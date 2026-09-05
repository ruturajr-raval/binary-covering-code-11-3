CERTIFIED BRANCH REDUCTIONS FOR K_2(11,3)
========================================

This source archive accompanies:

  Certified Branch Reductions for the Binary Covering Number K_2(11,3)

Author: Ruturaj R Raval
ORCID: 0000-0003-4930-8981

CONTENTS
--------

main.tex
  Manuscript source.

replay.py
  Checks the internal manifest, verifies the compact evidence, and
  regenerates the exact distance and overlap certificates.

RIGHTS.md
  States the repository license and the additional arXiv distribution grant.

verify_technical_report.py
  Standard-library verifier for the retained construction and branch ledgers.

verify_distance_distribution_bounds.py
verify_overlap_bound.py
  Exact standard-library generators for the analytic certificates.

anc/
  Allowlisted evidence records. These include the verified 16-word code,
  structural certificates, complete normalized-case ledger, third-word and
  selected fourth-word frontier manifests, proof indexes, proof-bundle
  manifests, the v0.2.0 release manifest, the Zenodo archive binding, and
  clean-checkout replay records.

MANIFEST.sha256
  SHA-256 digest for every other file in this archive.

REPLAY
------

From the extracted archive:

  python3 replay.py

Do not execute an extracted copy until the downloaded v0.3.0 release asset
has been authenticated against the SHA-256 value published with the GitHub
release. The internal manifest alone does not establish archive authenticity.

The replay requires only standard-library Python. It performs direct
enumeration of the 16-word cover, verifies the exact retained counts, checks
all source digests, and regenerates the distance and overlap certificates
byte-for-byte. It does not replay the large RUP and DRAT proof payloads.

FULL PROOF ARCHIVE
------------------

The complete proof traces and pinned replay environment are preserved in the
immutable v0.2.0 Zenodo deposit:

  https://doi.org/10.5281/zenodo.22302261

The archived file binding is:

  file: ruturajr-raval/binary-covering-code-11-3-v0.2.0.zip
  size: 269833751 bytes
  MD5: 326154a9b17cbced17bf750222744c81
  SHA-256: 750003eba2e9f9baf5fee9ed93c679b3661daf6d8c68ca40eeb681202b5e72ff

The all-versions concept DOI is:

  https://doi.org/10.5281/zenodo.22260709

CLAIM SCOPE
-----------

The report certifies:

- exact structural constraints for every hypothetical 15-word cover;
- a complete 150-case normalized partition with 112 certified normalized
  branch closures and 38 residual branches; and
- 324 certified closures among 350 exhaustive fourth-word branches inside
  four selected hard third-word children.

It does not:

- construct a 15-word radius-3 cover;
- exclude all 15-word covers;
- close a complete selected third-word child or normalized parent;
- prove K_2(11,3) = 15 or K_2(11,3) = 16; or
- change the known interval 15 <= K_2(11,3) <= 16.

REPOSITORY
----------

https://github.com/ruturajr-raval/binary-covering-code-11-3

Release: v0.3.0
