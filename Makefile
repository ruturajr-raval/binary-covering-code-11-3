PYTHON ?= python3
CXX ?= clang++
CXXFLAGS ?= -O3 -std=c++20 -Wall -Wextra -Wpedantic
DRAT_TRIM ?= build/drat-trim-src/drat-trim
DRAT_TRIM_COMMIT ?= 2e3b2dc0ecf938addbd779d42877b6ed69d9a985
FOURTH_WORD_RUP_ATTESTATION_DATE ?= 2026-09-03
CERTIFIED_REVISION ?=
CERTIFIED_REVISION_DATE ?= 2026-09-03
ALLOW_PENDING_REVISION ?= 0
REVISION_VERIFY_FLAGS := $(if $(filter 1,$(ALLOW_PENDING_REVISION)),--allow-pending,)
PYTHONPATH := src:tools
LOCKED := $(PYTHON) tools/run_with_repository_lock.py --
BUILD_DIR := build
BASELINE := data/baseline/k2-11-3-linear-16.txt
PARITY := data/baseline/k2-11-3-parity-columns-16.json
FOURTH_WORD_RUP_BUNDLE_FILES := \
	evidence/fourth-word-up-classification.json \
	evidence/fourth-word-rup-proof-plan.json \
	evidence/fourth-word-rup-proof-index-v1.json \
	evidence/fourth-word-rup-replay-attestation-v1.json
RELEASE_MANIFEST_FILES := \
	README.md \
	.zenodo.json \
	CITATION.cff \
	PUBLICATION.md \
	LICENSE \
	release.json \
	requirements-proof.txt \
	requirements-replay.txt \
	requirements-sat.txt \
	evidence.json \
	evidence/fourth-word-up-classification.json \
	evidence/fourth-word-rup-proof-plan.json \
	evidence/fourth-word-rup-proof-index-v1.json \
	evidence/fourth-word-rup-replay-attestation-v1.json \
	evidence/fourth-word-rup-bundle-v1.sha256 \
	evidence/fourth-word-rup-revision-v1.json \
	evidence/distance-distribution-bounds.json \
	evidence/overlap-bound.json \
	evidence/min-distance-proof-index.json \
	evidence/third-word-proof-index.json \
	evidence/case-reduction-summary.json \
	evidence/normalized-residual-two-word-cases.json \
	evidence/proof-bundle.sha256

.PHONY: test native-test proof-checker verify-release-manifest verify-release-manifest-locked verify-proof-bundle-manifest verify-fourth-word-rup-bundle-manifest write-fourth-word-rup-revision-pending finalize-fourth-word-rup-revision verify-fourth-word-rup-revision verify-baseline verify-independent analyze-baseline distance-bounds overlap-bound cnf audit-cnf compact-cnf audit-compact-cnf cases audit-cases two-word-cases audit-two-word-cases third-word-cases audit-third-word-cases third-word-child-frontier audit-third-word-child-frontier rebuild-and-audit-third-word-child-frontier fourth-word-hard-frontier audit-fourth-word-hard-frontier rebuild-and-audit-fourth-word-hard-frontier prepare-fourth-word-proof-formulas prepare-fourth-word-proof-formulas-locked fourth-word-rup-plan audit-fourth-word-rup-plan create-fourth-word-rup-proofs verify-fourth-word-rup-proofs audit-fourth-word-rup-proofs check-fourth-word-rup-proof-index fourth-word-rup-proof-smoke third-word-child-formula-smoke fourth-word-formula-smoke min-distance-branches audit-min-distance-branches max-degree-reduction orbit-certificates verify-orbit-certificates integer-profile-certificates verify-integer-profile-certificates prove-residual-case prepare-residual-case verify-residual-case verify-min-distance-proofs audit-min-distance-proofs verify-third-word-proofs audit-third-word-proofs case-reduction-stage1 case-reduction solver-test search-smoke sat-smoke local-search-smoke clean clean-locked

test: prepare-fourth-word-proof-formulas
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m unittest discover -s tests -v

$(BUILD_DIR)/search-local: src/search_local.cpp
	mkdir -p $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) $< -o $@

native-test: $(BUILD_DIR)/search-local
	$(BUILD_DIR)/search-local --self-test

proof-checker:
	$(PYTHON) tools/bootstrap_drat_trim.py \
		--commit $(DRAT_TRIM_COMMIT) \
		--output $(BUILD_DIR)/drat-trim-src

verify-proof-bundle-manifest:
	$(PYTHON) tools/verify_checksum_manifest.py \
		evidence/proof-bundle.sha256 \
		--tree evidence/proofs

verify-fourth-word-rup-bundle-manifest:
	$(PYTHON) tools/verify_checksum_manifest.py \
		evidence/fourth-word-rup-bundle-v1.sha256 \
		$(foreach file,$(FOURTH_WORD_RUP_BUNDLE_FILES),--path $(file)) \
		--tree evidence/proofs/fourth-word-rup-v1

write-fourth-word-rup-revision-pending: check-fourth-word-rup-proof-index verify-fourth-word-rup-bundle-manifest
	$(PYTHON) tools/manage_fourth_word_rup_revision.py \
		evidence/fourth-word-rup-revision-v1.json \
		--write-pending

finalize-fourth-word-rup-revision:
	$(PYTHON) tools/manage_fourth_word_rup_revision.py \
		evidence/fourth-word-rup-revision-v1.json \
		--finalize \
		--revision $(CERTIFIED_REVISION) \
		--completed-on $(CERTIFIED_REVISION_DATE)

verify-fourth-word-rup-revision: check-fourth-word-rup-proof-index verify-fourth-word-rup-bundle-manifest
	$(PYTHON) tools/manage_fourth_word_rup_revision.py \
		evidence/fourth-word-rup-revision-v1.json \
		--verify $(REVISION_VERIFY_FLAGS)

verify-release-manifest:
	$(LOCKED) $(MAKE) --no-print-directory \
		verify-release-manifest-locked PYTHON=$(PYTHON)

verify-release-manifest-locked: verify-proof-bundle-manifest verify-fourth-word-rup-bundle-manifest verify-fourth-word-rup-revision
	$(PYTHON) tools/assert_repository_lock.py
	$(PYTHON) tools/verify_checksum_manifest.py \
		release-manifest.sha256 \
		$(foreach file,$(RELEASE_MANIFEST_FILES),--path $(file))

verify-baseline:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) tools/verify_code.py \
		$(BASELINE) --length 11 --radius 3 --expected-size 16

verify-independent:
	$(PYTHON) tools/verify_code_independent.py \
		$(BASELINE) --length 11 --radius 3 --expected-size 16

analyze-baseline:
	PYTHONPATH=$(PYTHONPATH) $(LOCKED) $(PYTHON) tools/analyze_linear_code.py \
		$(PARITY) --output evidence/baseline-analysis.json

distance-bounds:
	$(LOCKED) $(PYTHON) tools/verify_distance_distribution_bounds.py \
		evidence/distance-distribution-bounds.json

overlap-bound:
	PYTHONPATH=tools $(LOCKED) $(PYTHON) tools/verify_overlap_bound.py \
		evidence/overlap-bound.json

cnf:
	mkdir -p $(BUILD_DIR)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) tools/generate_cnf.py \
		$(BUILD_DIR)/k2-11-3-size15.cnf \
		--length 11 --radius 3 --size 15 --anchor-zero

audit-cnf: cnf
	$(LOCKED) $(PYTHON) tools/audit_covering_cnf.py \
		$(BUILD_DIR)/k2-11-3-size15.cnf \
		--length 11 --radius 3 --size 15 --anchor-zero \
		--output evidence/base-cnf-audit.json

compact-cnf:
	PYTHONPATH=$(PYTHONPATH) $(LOCKED) $(PYTHON) tools/generate_compact_cnf.py \
		$(BUILD_DIR)/compact/k2-11-3-atmost15-kmtotalizer.cnf \
		evidence/compact-kmtotalizer.json \
		--length 11 --radius 3 --size 15 \
		--encoding kmtotalizer --anchor-zero
	PYTHONPATH=$(PYTHONPATH) $(LOCKED) $(PYTHON) tools/generate_compact_cnf.py \
		$(BUILD_DIR)/compact/k2-11-3-atmost15-cardnetwrk.cnf \
		evidence/compact-cardnetwrk.json \
		--length 11 --radius 3 --size 15 \
		--encoding cardnetwrk --anchor-zero

audit-compact-cnf: compact-cnf
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) tools/audit_compact_cnf.py \
		$(BUILD_DIR)/compact/k2-11-3-atmost15-kmtotalizer.cnf \
		evidence/compact-kmtotalizer.json
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) tools/audit_compact_cnf.py \
		$(BUILD_DIR)/compact/k2-11-3-atmost15-cardnetwrk.cnf \
		evidence/compact-cardnetwrk.json

cases: cnf
	PYTHONPATH=$(PYTHONPATH) $(LOCKED) $(PYTHON) tools/generate_min_weight_cases.py \
		$(BUILD_DIR)/cases evidence/min-weight-cases.json

audit-cases: cases
	PYTHONPATH=$(PYTHONPATH) $(LOCKED) $(PYTHON) tools/audit_min_weight_cases.py \
		$(BUILD_DIR)/k2-11-3-size15.cnf evidence/min-weight-cases.json \
		--output evidence/min-weight-case-audit.json

two-word-cases:
	PYTHONPATH=$(PYTHONPATH) $(LOCKED) $(PYTHON) tools/generate_two_word_cases.py \
		evidence/two-word-cases.json

audit-two-word-cases: two-word-cases
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) tools/audit_two_word_cases.py \
		evidence/two-word-cases.json

third-word-cases: case-reduction-stage1
	PYTHONPATH=$(PYTHONPATH):tools $(LOCKED) $(PYTHON) \
		tools/generate_third_word_cases.py \
		evidence/residual-two-word-cases.json \
		evidence/third-word-cases.json

audit-third-word-cases: third-word-cases
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
		tools/audit_third_word_cases.py \
		evidence/residual-two-word-cases.json \
		evidence/third-word-cases.json

third-word-child-frontier:
	PYTHONPATH=$(PYTHONPATH):tools $(LOCKED) $(PYTHON) \
		tools/generate_third_word_child_frontier.py \
		evidence/residual-two-word-cases.json \
		evidence/third-word-cases.json \
		evidence/min-distance-branches.json \
		evidence/max-degree-reduction.json \
		evidence/third-word-proof-index.json \
		evidence/case-reduction-summary.json \
		evidence/normalized-residual-two-word-cases.json \
		research/third-word-child-frontier.json

audit-third-word-child-frontier:
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
		tools/audit_third_word_child_frontier.py \
		evidence/residual-two-word-cases.json \
		evidence/third-word-cases.json \
		evidence/min-distance-branches.json \
		evidence/max-degree-reduction.json \
		evidence/third-word-proof-index.json \
		evidence/case-reduction-summary.json \
		evidence/normalized-residual-two-word-cases.json \
		research/third-word-child-frontier.json

rebuild-and-audit-third-word-child-frontier: third-word-child-frontier audit-third-word-child-frontier

fourth-word-hard-frontier:
	PYTHONPATH=$(PYTHONPATH):tools $(LOCKED) $(PYTHON) \
		tools/generate_fourth_word_frontier.py \
		evidence/residual-two-word-cases.json \
		evidence/third-word-cases.json \
		research/third-word-child-frontier.json \
		research/fourth-word-hard-frontier.json \
		--child-id w4-weight5-intersection0::orbit-005 \
		--child-id w4-weight5-intersection0::orbit-007 \
		--child-id w4-weight5-intersection0::orbit-014 \
		--child-id w4-weight5-intersection0::orbit-015

audit-fourth-word-hard-frontier:
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
		tools/audit_fourth_word_frontier.py \
		evidence/residual-two-word-cases.json \
		evidence/third-word-cases.json \
		research/third-word-child-frontier.json \
		research/fourth-word-hard-frontier.json

rebuild-and-audit-fourth-word-hard-frontier: fourth-word-hard-frontier audit-fourth-word-hard-frontier

prepare-fourth-word-proof-formulas:
	$(LOCKED) $(MAKE) --no-print-directory \
		prepare-fourth-word-proof-formulas-locked PYTHON=$(PYTHON)

prepare-fourth-word-proof-formulas-locked:
	$(PYTHON) tools/assert_repository_lock.py
	mkdir -p $(BUILD_DIR)/compact $(BUILD_DIR)/min-distance \
		.research-artifacts/fourth-word-proof-build
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) \
		tools/generate_compact_cnf.py \
		$(BUILD_DIR)/compact/k2-11-3-atmost15-kmtotalizer.cnf \
		.research-artifacts/fourth-word-proof-build/compact.json \
		--length 11 --radius 3 --size 15 \
		--encoding kmtotalizer --anchor-zero
	cmp \
		.research-artifacts/fourth-word-proof-build/compact.json \
		evidence/compact-kmtotalizer.json
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
		tools/generate_min_distance_branches.py \
		$(BUILD_DIR)/compact/k2-11-3-atmost15-kmtotalizer.cnf \
		evidence/distance-distribution-bounds.json \
		$(BUILD_DIR)/min-distance \
		.research-artifacts/fourth-word-proof-build/min-distance.json
	cmp \
		.research-artifacts/fourth-word-proof-build/min-distance.json \
		evidence/min-distance-branches.json

fourth-word-rup-plan: prepare-fourth-word-proof-formulas
	PYTHONPATH=$(PYTHONPATH):tools $(LOCKED) $(PYTHON) \
		tools/generate_fourth_word_rup_plan.py \
		evidence/residual-two-word-cases.json \
		evidence/third-word-cases.json \
		research/third-word-child-frontier.json \
		research/fourth-word-hard-frontier.json \
		evidence/fourth-word-up-classification.json \
		evidence/fourth-word-rup-proof-plan.json \
		--verify-existing

audit-fourth-word-rup-plan:
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
		tools/audit_fourth_word_rup_plan.py \
		evidence/residual-two-word-cases.json \
		evidence/third-word-cases.json \
		research/third-word-child-frontier.json \
		research/fourth-word-hard-frontier.json \
		evidence/fourth-word-up-classification.json \
		evidence/fourth-word-rup-proof-plan.json

create-fourth-word-rup-proofs: proof-checker prepare-fourth-word-proof-formulas audit-fourth-word-rup-plan
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
		tools/certify_fourth_word_rup_bundle.py \
		--python $(PYTHON) \
		--checker $(DRAT_TRIM) \
		--checker-commit $(DRAT_TRIM_COMMIT) \
		--attestation-date $(FOURTH_WORD_RUP_ATTESTATION_DATE)

verify-fourth-word-rup-proofs: proof-checker prepare-fourth-word-proof-formulas audit-fourth-word-rup-plan
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
		tools/prove_fourth_word_rup_cases.py \
		evidence/residual-two-word-cases.json \
		evidence/third-word-cases.json \
		research/third-word-child-frontier.json \
		research/fourth-word-hard-frontier.json \
		evidence/fourth-word-up-classification.json \
		evidence/fourth-word-rup-proof-plan.json \
		$(BUILD_DIR)/proofs/fourth-word \
		evidence/proofs/fourth-word-rup-v1 \
		evidence/fourth-word-rup-proof-index-v1.json \
		--checker $(DRAT_TRIM) \
		--checker-commit $(DRAT_TRIM_COMMIT) \
		--python $(PYTHON) \
		--verify-existing
	$(MAKE) check-fourth-word-rup-proof-index PYTHON=$(PYTHON)

audit-fourth-word-rup-proofs: verify-fourth-word-rup-proofs

check-fourth-word-rup-proof-index: audit-fourth-word-rup-plan
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
		tools/audit_fourth_word_rup_proofs.py \
		evidence/residual-two-word-cases.json \
		evidence/third-word-cases.json \
		research/third-word-child-frontier.json \
		research/fourth-word-hard-frontier.json \
		evidence/fourth-word-up-classification.json \
		evidence/fourth-word-rup-proof-plan.json \
		evidence/fourth-word-rup-proof-index-v1.json \
		evidence/proofs/fourth-word-rup-v1

fourth-word-rup-proof-smoke: proof-checker prepare-fourth-word-proof-formulas
	mkdir -p .research-artifacts/fourth-word-rup-proof-smoke
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
		tools/generate_fourth_word_formula.py \
		evidence/residual-two-word-cases.json \
		evidence/third-word-cases.json \
		research/third-word-child-frontier.json \
		research/fourth-word-hard-frontier.json \
		w4-weight5-intersection0::orbit-005::fourth-027 \
		.research-artifacts/fourth-word-rup-proof-smoke/formula.cnf \
		.research-artifacts/fourth-word-rup-proof-smoke/formula.json
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
		tools/audit_fourth_word_formula.py \
		.research-artifacts/fourth-word-rup-proof-smoke/formula.cnf \
		.research-artifacts/fourth-word-rup-proof-smoke/formula.json
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
		tools/write_unit_propagation_proof.py \
		.research-artifacts/fourth-word-rup-proof-smoke/formula.cnf \
		.research-artifacts/fourth-word-rup-proof-smoke/proof.drat.gz \
		.research-artifacts/fourth-word-rup-proof-smoke/proof.json \
		--case-id w4-weight5-intersection0::orbit-005::fourth-027
	$(PYTHON) tools/check_drat_proof.py \
		$(DRAT_TRIM) \
		.research-artifacts/fourth-word-rup-proof-smoke/formula.cnf \
		.research-artifacts/fourth-word-rup-proof-smoke/proof.drat.gz \
		.research-artifacts/fourth-word-rup-proof-smoke/proof.json \
		.research-artifacts/fourth-word-rup-proof-smoke/check.json \
		--checker-commit $(DRAT_TRIM_COMMIT)

third-word-child-formula-smoke: min-distance-branches
	mkdir -p .research-artifacts/child-formula-smoke/nonmatching
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
		tools/generate_third_word_child_formula.py \
		evidence/residual-two-word-cases.json \
		evidence/third-word-cases.json \
		research/third-word-child-frontier.json \
		w1-weight1-intersection0::orbit-000 \
		.research-artifacts/child-formula-smoke/nonmatching/formula.cnf \
		.research-artifacts/child-formula-smoke/nonmatching/metadata.json
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
		tools/audit_third_word_child_formula.py \
		.research-artifacts/child-formula-smoke/nonmatching/formula.cnf \
		.research-artifacts/child-formula-smoke/nonmatching/metadata.json
	mkdir -p .research-artifacts/child-formula-smoke/matching
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
		tools/generate_third_word_child_formula.py \
		evidence/residual-two-word-cases.json \
		evidence/third-word-cases.json \
		research/third-word-child-frontier.json \
		w1-weight2-intersection0::orbit-000 \
		.research-artifacts/child-formula-smoke/matching/formula.cnf \
		.research-artifacts/child-formula-smoke/matching/metadata.json
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
		tools/audit_third_word_child_formula.py \
		.research-artifacts/child-formula-smoke/matching/formula.cnf \
		.research-artifacts/child-formula-smoke/matching/metadata.json

fourth-word-formula-smoke: min-distance-branches
	mkdir -p .research-artifacts/fourth-formula-smoke
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
		tools/generate_fourth_word_formula.py \
		evidence/residual-two-word-cases.json \
		evidence/third-word-cases.json \
		research/third-word-child-frontier.json \
		research/fourth-word-hard-frontier.json \
		w4-weight5-intersection0::orbit-005::fourth-001 \
		.research-artifacts/fourth-formula-smoke/formula.cnf \
		.research-artifacts/fourth-formula-smoke/metadata.json
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
		tools/audit_fourth_word_formula.py \
		.research-artifacts/fourth-formula-smoke/formula.cnf \
		.research-artifacts/fourth-formula-smoke/metadata.json

min-distance-branches: compact-cnf distance-bounds
	PYTHONPATH=$(PYTHONPATH):tools $(LOCKED) $(PYTHON) \
		tools/generate_min_distance_branches.py \
		$(BUILD_DIR)/compact/k2-11-3-atmost15-kmtotalizer.cnf \
		evidence/distance-distribution-bounds.json \
		$(BUILD_DIR)/min-distance evidence/min-distance-branches.json

audit-min-distance-branches: min-distance-branches
	PYTHONPATH=$(PYTHONPATH):tools $(LOCKED) $(PYTHON) \
		tools/audit_min_distance_branches.py \
		evidence/min-distance-branches.json \
		--output evidence/min-distance-branch-audit.json

max-degree-reduction: case-reduction-stage1
	PYTHONPATH=$(PYTHONPATH):tools $(LOCKED) $(PYTHON) \
		tools/verify_max_degree_reduction.py \
		evidence/residual-two-word-cases.json \
		evidence/max-degree-reduction.json

orbit-certificates: audit-two-word-cases
	PYTHONPATH=$(PYTHONPATH) $(LOCKED) $(PYTHON) \
		tools/generate_orbit_lp_certificates.py \
		evidence/two-word-cases.json evidence/orbit-lp-certificates.json

verify-orbit-certificates: orbit-certificates
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) \
		tools/verify_orbit_lp_certificates.py \
		evidence/two-word-cases.json evidence/orbit-lp-certificates.json

integer-profile-certificates: verify-orbit-certificates
	PYTHONPATH=$(PYTHONPATH) $(LOCKED) $(PYTHON) \
		tools/generate_integer_profile_certificates.py \
		evidence/two-word-cases.json evidence/orbit-lp-certificates.json \
		evidence/integer-profile evidence/integer-profile-certificates.json

verify-integer-profile-certificates: integer-profile-certificates
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) \
		tools/verify_integer_profile_certificates.py \
		evidence/two-word-cases.json \
		evidence/integer-profile-certificates.json

prove-residual-case: compact-cnf two-word-cases
	PYTHONPATH=$(PYTHONPATH):tools $(LOCKED) $(PYTHON) tools/prove_two_word_case.py \
		$(BUILD_DIR)/compact/k2-11-3-atmost15-kmtotalizer.cnf \
		evidence/two-word-cases.json w2-weight7-intersection1 \
		$(BUILD_DIR)/proofs/w2-weight7-intersection1.cnf \
		evidence/proofs/w2-weight7-intersection1.drat.gz \
		evidence/proofs/w2-weight7-intersection1-proof.json

prepare-residual-case:
	mkdir -p $(BUILD_DIR)/replay/residual-case
	PYTHONPATH=$(PYTHONPATH) $(LOCKED) $(PYTHON) \
		tools/generate_compact_cnf.py \
		$(BUILD_DIR)/compact/k2-11-3-atmost15-kmtotalizer.cnf \
		$(BUILD_DIR)/replay/residual-case/compact-kmtotalizer.json \
		--length 11 --radius 3 --size 15 \
		--encoding kmtotalizer --anchor-zero
	PYTHONPATH=$(PYTHONPATH) $(LOCKED) $(PYTHON) \
		tools/generate_two_word_cases.py \
		$(BUILD_DIR)/replay/residual-case/two-word-cases.json
	PYTHONPATH=$(PYTHONPATH):tools $(LOCKED) $(PYTHON) \
		tools/prove_two_word_case.py \
		$(BUILD_DIR)/compact/k2-11-3-atmost15-kmtotalizer.cnf \
		$(BUILD_DIR)/replay/residual-case/two-word-cases.json \
		w2-weight7-intersection1 \
		$(BUILD_DIR)/proofs/w2-weight7-intersection1.cnf \
		evidence/proofs/w2-weight7-intersection1.drat.gz \
		evidence/proofs/w2-weight7-intersection1-proof.json \
		--verify-existing

verify-residual-case: proof-checker prepare-residual-case
	$(LOCKED) $(PYTHON) tools/check_drat_proof.py \
		$(DRAT_TRIM) \
		$(BUILD_DIR)/proofs/w2-weight7-intersection1.cnf \
		evidence/proofs/w2-weight7-intersection1.drat.gz \
		evidence/proofs/w2-weight7-intersection1-proof.json \
		evidence/proofs/w2-weight7-intersection1-check.json \
		--checker-commit $(DRAT_TRIM_COMMIT) \
		--verify-existing

verify-min-distance-proofs: proof-checker audit-min-distance-branches audit-two-word-cases
	PYTHONPATH=$(PYTHONPATH):tools $(LOCKED) $(PYTHON) \
		tools/prove_min_distance_cases.py \
		evidence/min-distance-proof-plan.json \
		$(BUILD_DIR)/proofs/min-distance \
		evidence/proofs/min-distance \
		evidence/min-distance-proof-index.json \
		--checker $(DRAT_TRIM) \
		--checker-commit $(DRAT_TRIM_COMMIT) \
		--python $(PYTHON)

audit-min-distance-proofs: proof-checker audit-min-distance-branches audit-two-word-cases
	PYTHONPATH=$(PYTHONPATH):tools $(LOCKED) $(PYTHON) \
		tools/prove_min_distance_cases.py \
		evidence/min-distance-proof-plan.json \
		$(BUILD_DIR)/proofs/min-distance \
		evidence/proofs/min-distance \
		evidence/min-distance-proof-index.json \
		--checker $(DRAT_TRIM) \
		--checker-commit $(DRAT_TRIM_COMMIT) \
		--python $(PYTHON) \
		--verify-existing

case-reduction-stage1:
	PYTHONPATH=$(PYTHONPATH):tools $(LOCKED) $(PYTHON) \
		tools/verify_case_reduction.py \
		evidence/two-word-cases.json \
		evidence/orbit-lp-certificates.json \
		evidence/integer-profile-certificates.json \
		evidence/distance-distribution-bounds.json \
		evidence/proofs/w2-weight7-intersection1-check.json \
		evidence/min-distance-proof-index.json \
		evidence/case-reduction-stage1.json \
		evidence/residual-two-word-cases.json

verify-third-word-proofs: proof-checker audit-third-word-cases audit-min-distance-branches
	PYTHONPATH=$(PYTHONPATH):tools $(LOCKED) $(PYTHON) \
		tools/prove_third_word_cases.py \
		evidence/third-word-proof-plan.json \
		$(BUILD_DIR)/proofs/third-word \
		evidence/proofs/third-word \
		evidence/third-word-proof-index.json \
		--checker $(DRAT_TRIM) \
		--checker-commit $(DRAT_TRIM_COMMIT) \
		--python $(PYTHON)

audit-third-word-proofs: proof-checker audit-third-word-cases audit-min-distance-branches
	PYTHONPATH=$(PYTHONPATH):tools $(LOCKED) $(PYTHON) \
		tools/prove_third_word_cases.py \
		evidence/third-word-proof-plan.json \
		$(BUILD_DIR)/proofs/third-word \
		evidence/proofs/third-word \
		evidence/third-word-proof-index.json \
		--checker $(DRAT_TRIM) \
		--checker-commit $(DRAT_TRIM_COMMIT) \
		--python $(PYTHON) \
		--verify-existing

case-reduction: case-reduction-stage1 max-degree-reduction audit-third-word-proofs
	PYTHONPATH=$(PYTHONPATH):tools $(LOCKED) $(PYTHON) \
		tools/verify_advanced_case_reduction.py \
		evidence/case-reduction-stage1.json \
		evidence/residual-two-word-cases.json \
		evidence/max-degree-reduction.json \
		evidence/third-word-proof-index.json \
		evidence/case-reduction-summary.json \
		evidence/normalized-residual-two-word-cases.json

solver-test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m unittest \
		tests.test_search_cp_sat -v

search-smoke:
	mkdir -p search-results
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) tools/search_cp_sat.py \
		search-results/cp-sat-smoke.json \
		--length 7 --radius 1 --size 16 --time-limit 10 \
		--workers 1 --anchor-zero

sat-smoke: audit-cnf
	mkdir -p search-results
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) tools/run_sat.py \
		$(BUILD_DIR)/k2-11-3-size15.cnf \
		search-results/cadical300-smoke.json \
		--solver cadical300 --time-limit 10 \
		--length 11 --radius 3 --size 15 \
		--code-output search-results/cadical300-code.txt || test $$? -eq 2

local-search-smoke: $(BUILD_DIR)/search-local
	mkdir -p search-results
	$(BUILD_DIR)/search-local \
		--iterations 10000 --restart-iterations 5000 --seed 1 \
		--best-code search-results/local-smoke-best.txt \
		--summary search-results/local-smoke.json || test $$? -eq 2

clean:
	$(LOCKED) $(MAKE) --no-print-directory clean-locked PYTHON=$(PYTHON)

clean-locked:
	$(PYTHON) tools/assert_repository_lock.py
	find $(BUILD_DIR) search-results -type f -delete 2>/dev/null || true
