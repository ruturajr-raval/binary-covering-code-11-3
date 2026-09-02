PYTHON ?= python3
CXX ?= clang++
CXXFLAGS ?= -O3 -std=c++20 -Wall -Wextra -Wpedantic
DRAT_TRIM ?= build/drat-trim-src/drat-trim
DRAT_TRIM_COMMIT ?= 2e3b2dc0ecf938addbd779d42877b6ed69d9a985
PYTHONPATH := src:tools
BUILD_DIR := build
BASELINE := data/baseline/k2-11-3-linear-16.txt
PARITY := data/baseline/k2-11-3-parity-columns-16.json

.PHONY: test native-test proof-checker verify-baseline verify-independent analyze-baseline distance-bounds overlap-bound cnf audit-cnf compact-cnf audit-compact-cnf cases audit-cases two-word-cases audit-two-word-cases third-word-cases audit-third-word-cases third-word-child-frontier audit-third-word-child-frontier rebuild-and-audit-third-word-child-frontier min-distance-branches audit-min-distance-branches max-degree-reduction orbit-certificates verify-orbit-certificates integer-profile-certificates verify-integer-profile-certificates prove-residual-case verify-residual-case verify-min-distance-proofs audit-min-distance-proofs verify-third-word-proofs audit-third-word-proofs case-reduction-stage1 case-reduction solver-test search-smoke sat-smoke local-search-smoke clean

test:
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

verify-baseline:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) tools/verify_code.py \
		$(BASELINE) --length 11 --radius 3 --expected-size 16

verify-independent:
	$(PYTHON) tools/verify_code_independent.py \
		$(BASELINE) --length 11 --radius 3 --expected-size 16

analyze-baseline:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) tools/analyze_linear_code.py \
		$(PARITY) --output evidence/baseline-analysis.json

distance-bounds:
	$(PYTHON) tools/verify_distance_distribution_bounds.py \
		evidence/distance-distribution-bounds.json

overlap-bound:
	PYTHONPATH=tools $(PYTHON) tools/verify_overlap_bound.py \
		evidence/overlap-bound.json

cnf:
	mkdir -p $(BUILD_DIR)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) tools/generate_cnf.py \
		$(BUILD_DIR)/k2-11-3-size15.cnf \
		--length 11 --radius 3 --size 15 --anchor-zero

audit-cnf: cnf
	$(PYTHON) tools/audit_covering_cnf.py \
		$(BUILD_DIR)/k2-11-3-size15.cnf \
		--length 11 --radius 3 --size 15 --anchor-zero \
		--output evidence/base-cnf-audit.json

compact-cnf:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) tools/generate_compact_cnf.py \
		$(BUILD_DIR)/compact/k2-11-3-atmost15-kmtotalizer.cnf \
		evidence/compact-kmtotalizer.json \
		--length 11 --radius 3 --size 15 \
		--encoding kmtotalizer --anchor-zero
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) tools/generate_compact_cnf.py \
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
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) tools/generate_min_weight_cases.py \
		$(BUILD_DIR)/cases evidence/min-weight-cases.json

audit-cases: cases
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) tools/audit_min_weight_cases.py \
		$(BUILD_DIR)/k2-11-3-size15.cnf evidence/min-weight-cases.json \
		--output evidence/min-weight-case-audit.json

two-word-cases:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) tools/generate_two_word_cases.py \
		evidence/two-word-cases.json

audit-two-word-cases: two-word-cases
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) tools/audit_two_word_cases.py \
		evidence/two-word-cases.json

third-word-cases: case-reduction-stage1
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
		tools/generate_third_word_cases.py \
		evidence/residual-two-word-cases.json \
		evidence/third-word-cases.json

audit-third-word-cases: third-word-cases
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
		tools/audit_third_word_cases.py \
		evidence/residual-two-word-cases.json \
		evidence/third-word-cases.json

third-word-child-frontier:
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
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

min-distance-branches: compact-cnf distance-bounds
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
		tools/generate_min_distance_branches.py \
		$(BUILD_DIR)/compact/k2-11-3-atmost15-kmtotalizer.cnf \
		evidence/distance-distribution-bounds.json \
		$(BUILD_DIR)/min-distance evidence/min-distance-branches.json

audit-min-distance-branches: min-distance-branches
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
		tools/audit_min_distance_branches.py \
		evidence/min-distance-branches.json \
		--output evidence/min-distance-branch-audit.json

max-degree-reduction: case-reduction-stage1
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
		tools/verify_max_degree_reduction.py \
		evidence/residual-two-word-cases.json \
		evidence/max-degree-reduction.json

orbit-certificates: audit-two-word-cases
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) \
		tools/generate_orbit_lp_certificates.py \
		evidence/two-word-cases.json evidence/orbit-lp-certificates.json

verify-orbit-certificates: orbit-certificates
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) \
		tools/verify_orbit_lp_certificates.py \
		evidence/two-word-cases.json evidence/orbit-lp-certificates.json

integer-profile-certificates: verify-orbit-certificates
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) \
		tools/generate_integer_profile_certificates.py \
		evidence/two-word-cases.json evidence/orbit-lp-certificates.json \
		evidence/integer-profile evidence/integer-profile-certificates.json

verify-integer-profile-certificates: integer-profile-certificates
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) \
		tools/verify_integer_profile_certificates.py \
		evidence/two-word-cases.json \
		evidence/integer-profile-certificates.json

prove-residual-case: compact-cnf two-word-cases
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) tools/prove_two_word_case.py \
		$(BUILD_DIR)/compact/k2-11-3-atmost15-kmtotalizer.cnf \
		evidence/two-word-cases.json w2-weight7-intersection1 \
		$(BUILD_DIR)/proofs/w2-weight7-intersection1.cnf \
		evidence/proofs/w2-weight7-intersection1.drat.gz \
		evidence/proofs/w2-weight7-intersection1-proof.json

verify-residual-case: proof-checker prove-residual-case
	$(PYTHON) tools/check_drat_proof.py \
		$(DRAT_TRIM) \
		$(BUILD_DIR)/proofs/w2-weight7-intersection1.cnf \
		evidence/proofs/w2-weight7-intersection1.drat.gz \
		evidence/proofs/w2-weight7-intersection1-proof.json \
		evidence/proofs/w2-weight7-intersection1-check.json \
		--checker-commit $(DRAT_TRIM_COMMIT)

verify-min-distance-proofs: proof-checker audit-min-distance-branches audit-two-word-cases
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
		tools/prove_min_distance_cases.py \
		evidence/min-distance-proof-plan.json \
		$(BUILD_DIR)/proofs/min-distance \
		evidence/proofs/min-distance \
		evidence/min-distance-proof-index.json \
		--checker $(DRAT_TRIM) \
		--checker-commit $(DRAT_TRIM_COMMIT) \
		--python $(PYTHON)

audit-min-distance-proofs: proof-checker audit-min-distance-branches audit-two-word-cases
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
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
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
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
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
		tools/prove_third_word_cases.py \
		evidence/third-word-proof-plan.json \
		$(BUILD_DIR)/proofs/third-word \
		evidence/proofs/third-word \
		evidence/third-word-proof-index.json \
		--checker $(DRAT_TRIM) \
		--checker-commit $(DRAT_TRIM_COMMIT) \
		--python $(PYTHON)

audit-third-word-proofs: proof-checker audit-third-word-cases audit-min-distance-branches
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
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
	PYTHONPATH=$(PYTHONPATH):tools $(PYTHON) \
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
	find $(BUILD_DIR) search-results -type f -delete 2>/dev/null || true
