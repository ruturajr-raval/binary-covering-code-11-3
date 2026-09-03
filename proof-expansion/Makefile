PYTHON ?= .venv/bin/python
ROOT := ..
ENV := PYTHONPATH=proof-expansion/src:src:tools
CHECKER_COMMIT := 2e3b2dc0ecf938addbd779d42877b6ed69d9a985

.PHONY: bootstrap-checker test audit-plan build-bundle audit-bundle
.PHONY: audit-bundle-structure

bootstrap-checker:
	cd $(ROOT) && $(PYTHON) -I proof-expansion/cli/bootstrap_checker.py \
		--commit $(CHECKER_COMMIT) --output build/drat-trim-src

test: bootstrap-checker
	cd $(ROOT) && $(ENV) $(PYTHON) -m unittest discover -s proof-expansion/tests -v

audit-plan:
	cd $(ROOT) && $(ENV) $(PYTHON) -I proof-expansion/cli/audit_plan.py \
		evidence/residual-two-word-cases.json \
		evidence/third-word-cases.json \
		research/third-word-child-frontier.json \
		research/fourth-word-hard-frontier.json \
		evidence/fourth-word-up-classification.json \
		evidence/fourth-word-rup-proof-index-v1.json \
		evidence/fourth-word-rup-replay-attestation-v1.json \
		evidence/fourth-word-rup-bundle-v1.sha256 \
		evidence/fourth-word-rup-revision-v1.json \
		research/runs/2026-09-02-fourth-word-portfolio.json \
		research/runs/2026-09-02-fourth-word-portfolio-run.json \
		docs/LITERATURE_AUDIT.md \
		proof-expansion/evidence/fourth-word-solver-drat-plan-v2.json

build-bundle: bootstrap-checker
	cd $(ROOT) && $(ENV) $(PYTHON) -I proof-expansion/cli/build_bundle.py \
		--python $(PYTHON) --workers 1

audit-bundle: bootstrap-checker
	cd $(ROOT) && $(ENV) $(PYTHON) -I proof-expansion/cli/audit_bundle.py \
		--python $(PYTHON) --workers 1

audit-bundle-structure: bootstrap-checker
	cd $(ROOT) && $(ENV) $(PYTHON) -I proof-expansion/cli/audit_bundle.py \
		--python $(PYTHON) --workers 1 --structure-only
