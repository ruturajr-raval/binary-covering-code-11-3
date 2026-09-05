#!/usr/bin/env python3
"""Verify the compact evidence record accompanying the technical report."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = Path("evidence/technical-report-summary-v1.json")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _repository_path(root: Path, value: str) -> Path:
    relative = PurePosixPath(value)
    if (
        not relative.parts
        or relative.is_absolute()
        or ".." in relative.parts
        or relative.as_posix() != value
    ):
        raise ValueError(f"invalid relative path: {value}")
    path = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"path contains a symbolic link: {value}")
    return path


def _regular_file(path: Path, description: str) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise ValueError(f"{description} is missing: {path}") from error
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{description} is not a regular file: {path}")


def _sha256(path: Path) -> str:
    _regular_file(path, "artifact")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, object]:
    _regular_file(path, "JSON artifact")
    try:
        value = json.loads(
            path.read_text(encoding="ascii"),
            object_pairs_hook=_unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid JSON artifact: {path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON artifact is not an object: {path}")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _manifest_entries(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        try:
            digest, name = line.split("  ", maxsplit=1)
        except ValueError as error:
            raise ValueError(f"malformed checksum manifest: {path}") from error
        _repository_path(Path("."), name)
        _require(
            len(digest) == 64
            and all(character in "0123456789abcdef" for character in digest)
            and name not in entries,
            f"invalid checksum manifest entry: {path}",
        )
        entries[name] = digest
    _require(bool(entries), f"checksum manifest is empty: {path}")
    return entries


def _verify_sources(
    root: Path,
    summary: dict[str, object],
) -> dict[str, Path]:
    sources = summary.get("sources")
    _require(isinstance(sources, dict), "summary sources are missing")
    resolved: dict[str, Path] = {}
    for label, reference in sources.items():
        _require(
            isinstance(label, str) and isinstance(reference, dict),
            "summary source reference is invalid",
        )
        _require(
            set(reference) == {"path", "sha256"},
            f"summary source schema differs: {label}",
        )
        relative = reference["path"]
        expected = reference["sha256"]
        _require(
            isinstance(relative, str)
            and isinstance(expected, str)
            and len(expected) == 64,
            f"summary source values are invalid: {label}",
        )
        path = _repository_path(root, relative)
        _require(
            _sha256(path) == expected,
            f"summary source digest differs: {label}",
        )
        resolved[label] = path
    return resolved


def _verify_baseline(path: Path) -> None:
    words = path.read_text(encoding="ascii").splitlines()
    _require(len(words) == 16, "baseline code does not contain 16 words")
    _require(len(set(words)) == 16, "baseline code contains duplicates")
    _require(
        all(len(word) == 11 and set(word) <= {"0", "1"} for word in words),
        "baseline code contains an invalid word",
    )
    code = [int(word, 2) for word in words]
    radius = max(
        min(bin(ambient ^ codeword).count("1") for codeword in code)
        for ambient in range(1 << 11)
    )
    _require(radius == 3, "baseline code does not have covering radius 3")


def verify(root: Path = PROJECT_ROOT) -> dict[str, object]:
    root = root.resolve()
    summary = _load_json(_repository_path(root, SUMMARY_PATH.as_posix()))
    _require(
        summary.get("record_type") == "technical-report-summary"
        and summary.get("schema_version") == 1,
        "technical-report summary schema differs",
    )
    interval = summary.get("known_interval")
    _require(
        interval
        == {
            "lower_bound": 15,
            "upper_bound": 16,
            "exact_value_resolved": False,
        },
        "known interval differs",
    )
    _require(
        summary.get("structural_bounds_for_hypothetical_size_15_cover")
        == {
            "pairs_at_distance_at_most_6_lower_bound": 28,
            "pairs_at_distance_at_most_5_lower_bound": 11,
            "minimum_distance_at_most": 5,
            "pair_ball_overlap_at_least": 1712,
            "triple_ball_overlap_at_least": 280,
        },
        "summary structural bounds differ",
    )
    _require(
        summary.get("normalized_frontier")
        == {
            "canonical_parent_cases": 150,
            "stage1_closures": {
                "orbit_lp_infeasible": 80,
                "integer_profile_infeasible": 2,
                "standalone_drat": 1,
                "minimum_distance_at_most_5": 4,
                "closest_pair_drat": 14,
            },
            "advanced_closures": {
                "maximum_degree_normalization": 5,
                "third_word_drat": 6,
            },
            "certified_normalized_branch_closures": 112,
            "residual_normalized_branches": 38,
        },
        "summary normalized frontier differs",
    )
    _require(
        summary.get("third_word_frontier")
        == {
            "stage1_parent_count": 49,
            "stage1_child_count": 3238,
            "active_parent_count": 38,
            "active_parent_child_count": 2548,
            "excluded_minimum_distance_child_count": 312,
            "excluded_matching_child_count": 73,
            "live_child_count": 2163,
        },
        "summary third-word frontier differs",
    )
    _require(
        summary.get("selected_fourth_word_frontier")
        == {
            "selected_third_word_children": [
                "w4-weight5-intersection0::orbit-005",
                "w4-weight5-intersection0::orbit-007",
                "w4-weight5-intersection0::orbit-014",
                "w4-weight5-intersection0::orbit-015",
            ],
            "fourth_word_branches": 350,
            "rup_certified_branches": 184,
            "solver_drat_certified_branches": 140,
            "combined_certified_branches": 324,
            "unresolved_branches": 26,
            "closed_selected_children": 0,
            "closed_normalized_parents": 0,
        },
        "summary selected fourth-word frontier differs",
    )
    _require(
        summary.get("artifact_archive")
        == {
            "release": "v0.2.0",
            "version_doi": "10.5281/zenodo.22302261",
            "concept_doi": "10.5281/zenodo.22260709",
            "file_key": (
                "ruturajr-raval/"
                "binary-covering-code-11-3-v0.2.0.zip"
            ),
            "size_bytes": 269833751,
            "md5": "326154a9b17cbced17bf750222744c81",
            "sha256": (
                "750003eba2e9f9baf5fee9ed93c679b3"
                "661daf6d8c68ca40eeb681202b5e72ff"
            ),
        },
        "summary artifact archive differs",
    )
    sources = _verify_sources(root, summary)
    _verify_baseline(sources["baseline_code"])

    distance = _load_json(sources["distance_distribution"])
    _require(distance.get("valid") is True, "distance certificate is invalid")
    _require(
        distance.get("conclusions")
        == {
            "pairs_at_distance_at_most_6": 28,
            "pairs_at_distance_at_most_5": 11,
            "minimum_pair_distance_at_most": 5,
        },
        "distance conclusions differ",
    )

    overlap = _load_json(sources["overlap_bound"])
    _require(overlap.get("valid") is True, "overlap certificate is invalid")
    _require(
        overlap["integer_identity"]["base_bound"] == 1708
        and overlap["modular_refinement"]["integral_lower_bound"] == 1712,
        "pair-overlap bound differs",
    )
    _require(
        overlap["triple_overlap_consequence"]["lower_bound"] == 280,
        "triple-overlap bound differs",
    )

    cases = _load_json(sources["case_reduction"])
    stage1 = cases.get("stage1_counts")
    advanced = cases.get("advanced_counts")
    _require(
        stage1
        == {
            "closest_pair_drat": 14,
            "integer_profile_infeasible": 2,
            "minimum_distance_at_most_5": 4,
            "open": 49,
            "orbit_lp_infeasible": 80,
            "standalone_drat": 1,
        },
        "stage-1 case ledger differs",
    )
    _require(
        advanced
        == {
            "maximum_degree_normalization": 5,
            "open": 38,
            "third_word_drat": 6,
        },
        "advanced case ledger differs",
    )
    _require(
        cases.get("total_cases") == 150
        and cases.get("all_accounted_for") is True
        and cases.get("global_exact_value_resolved") is False,
        "case-reduction scope differs",
    )

    third = _load_json(sources["third_word_frontier"])
    _require(
        third.get("counts")
        == {
            "active_parent_child_count": 2548,
            "active_parent_count": 38,
            "active_parent_matching_child_count": 1870,
            "active_parent_matching_parent_count": 30,
            "closed_maximum_degree_child_count": 267,
            "closed_maximum_degree_parent_count": 5,
            "closed_third_word_drat_child_count": 423,
            "closed_third_word_drat_parent_count": 6,
            "excluded_matching_child_count": 73,
            "excluded_minimum_distance_child_count": 312,
            "live_child_count": 2163,
            "non_drat_child_count": 2815,
            "non_drat_parent_count": 43,
            "stage1_child_count": 3238,
            "stage1_parent_count": 49,
        },
        "third-word frontier counts differ",
    )

    fourth = _load_json(sources["fourth_word_frontier"])
    _require(
        fourth.get("counts")
        == {
            "candidate_word_count": 2967,
            "excluded_matching_count": 753,
            "fourth_orbit_count": 350,
            "selected_child_count": 4,
        },
        "fourth-word frontier counts differ",
    )
    children = fourth.get("children")
    _require(
        isinstance(children, list)
        and len(children) == 4
        and sum(child["fourth_orbit_count"] for child in children) == 350
        and all(
            len(child["branches"]) == child["fourth_orbit_count"]
            for child in children
        ),
        "fourth-word branch manifest differs",
    )
    frontier_branches = [
        branch
        for child in children
        for branch in child["branches"]
    ]
    frontier_by_id = {
        branch["branch_id"]: branch
        for branch in frontier_branches
    }
    _require(
        len(frontier_branches) == 350
        and len(frontier_by_id) == 350,
        "fourth-word frontier branch identities differ",
    )

    classification = _load_json(sources["rup_classification"])
    _require(
        classification.get("branch_count") == 350
        and classification.get("rup_conflict_count") == 184
        and classification.get("not_rup_conflict_count") == 166
        and classification.get("solver_agreement") is True,
        "RUP classification differs",
    )
    classified = classification.get("branches")
    _require(
        isinstance(classified, list) and len(classified) == 350,
        "RUP classification branch list differs",
    )
    classified_by_id = {
        branch["branch_id"]: branch
        for branch in classified
    }
    _require(
        len(classified_by_id) == 350
        and set(classified_by_id) == set(frontier_by_id),
        "RUP classification branch identities differ",
    )
    for branch_id, branch in classified_by_id.items():
        frontier = frontier_by_id[branch_id]
        _require(
            branch["branch_sha256"] == frontier["branch_sha256"]
            and branch["parent_child_id"] == frontier["parent_child_id"]
            and branch["fourth_orbit_index"] == frontier["fourth_orbit_index"],
            f"RUP classification branch metadata differs: {branch_id}",
        )
    rup_ids = {
        branch_id
        for branch_id, branch in classified_by_id.items()
        if branch["status"] == "rup-conflict"
    }
    residual_ids = {
        branch_id
        for branch_id, branch in classified_by_id.items()
        if branch["status"] == "not-rup-conflict"
    }
    _require(
        len(rup_ids) == 184
        and len(residual_ids) == 166
        and rup_ids.isdisjoint(residual_ids)
        and rup_ids | residual_ids == set(classified_by_id),
        "RUP classification status partition differs",
    )

    rup = _load_json(sources["rup_proof_index"])
    _require(
        rup.get("case_count") == 184
        and rup.get("all_verified") is True
        and rup.get("certification_scope")
        == {
            "closed_normalized_parents": 0,
            "closed_third_word_children": 0,
            "fourth_word_branches": 350,
            "rup_unsat_branches": 184,
            "selected_third_word_children": 4,
            "unresolved_fourth_word_branches": 166,
        },
        "RUP proof index differs",
    )
    rup_cases = rup.get("cases")
    _require(
        isinstance(rup_cases, list)
        and len(rup_cases) == 184
        and all(case.get("verified") is True for case in rup_cases),
        "RUP proof index contains an unverified case",
    )
    indexed_rup = {case["branch_id"]: case for case in rup_cases}
    _require(
        len(indexed_rup) == 184 and set(indexed_rup) == rup_ids,
        "RUP proof index branch set differs",
    )
    for branch_id, case in indexed_rup.items():
        _require(
            case["branch_sha256"]
            == classified_by_id[branch_id]["branch_sha256"],
            f"RUP proof branch digest differs: {branch_id}",
        )

    solver = _load_json(sources["solver_drat_index"])
    _require(
        solver.get("case_count") == 140
        and solver.get("result")
        == {
            "combined_certified_branch_count": 324,
            "covering_number_status": "15 or 16",
            "frontier_branch_count": 350,
            "fully_closed_normalized_parent_count": 0,
            "fully_closed_selected_child_count": 0,
            "lower_bound_15": {
                "basis": "inherited historical computational result",
                "independently_reconstructed_here": False,
                "literature_source": "literature_audit",
                "table_update_date": "2006-01-17",
            },
            "newly_certified_branch_count": 140,
            "remaining_branch_count": 26,
        },
        "solver DRAT proof index differs",
    )
    solver_cases = solver.get("cases")
    _require(
        isinstance(solver_cases, list)
        and len(solver_cases) == 140
        and all(case.get("verified") is True for case in solver_cases),
        "solver DRAT proof index contains an unverified case",
    )
    indexed_solver = {case["branch_id"]: case for case in solver_cases}
    _require(
        len(indexed_solver) == 140
        and set(indexed_solver) <= residual_ids
        and set(indexed_solver).isdisjoint(rup_ids),
        "solver DRAT proof branch set differs",
    )
    for branch_id, case in indexed_solver.items():
        _require(
            case["branch_sha256"]
            == classified_by_id[branch_id]["branch_sha256"],
            f"solver DRAT branch digest differs: {branch_id}",
        )
    unresolved_ids = residual_ids - set(indexed_solver)
    _require(
        len(rup_ids | set(indexed_solver)) == 324
        and len(unresolved_ids) == 26,
        "combined fourth-word branch partition differs",
    )
    expected_per_child = {
        "w4-weight5-intersection0::orbit-005": (50, 29, 6, 85),
        "w4-weight5-intersection0::orbit-007": (53, 15, 8, 76),
        "w4-weight5-intersection0::orbit-014": (41, 28, 4, 73),
        "w4-weight5-intersection0::orbit-015": (40, 68, 8, 116),
    }
    for child_id, expected_counts in expected_per_child.items():
        all_child = {
            branch_id
            for branch_id, branch in classified_by_id.items()
            if branch["parent_child_id"] == child_id
        }
        observed = (
            len(all_child & rup_ids),
            len(all_child & set(indexed_solver)),
            len(all_child & unresolved_ids),
            len(all_child),
        )
        _require(
            observed == expected_counts,
            f"fourth-word per-child partition differs: {child_id}",
        )

    rup_revision = _load_json(sources["rup_revision"])
    solver_revision = _load_json(sources["solver_drat_revision"])
    _require(
        rup_revision.get("status") == "clean-checkout-replay-passed"
        and rup_revision["clean_checkout_replay"]["passed"] is True,
        "RUP clean-checkout record differs",
    )
    _require(
        solver_revision.get("status") == "clean-checkout-replay-passed"
        and solver_revision["clean_checkout_replay"]["passed"] is True
        and solver_revision["clean_checkout_replay"]["proofs_replayed"] is True,
        "solver DRAT clean-checkout record differs",
    )
    _require(
        rup_revision["bundle_manifest"]["sha256"]
        == _sha256(sources["rup_proof_manifest"]),
        "RUP revision does not bind the included proof manifest",
    )
    _require(
        solver_revision["solver_drat_bundle_manifest"]["sha256"]
        == _sha256(sources["solver_drat_proof_manifest"]),
        "solver revision does not bind the included proof manifest",
    )
    release_manifest = _manifest_entries(sources["v0_2_release_manifest"])
    _require(
        release_manifest.get("evidence/proof-bundle.sha256")
        == _sha256(sources["root_proof_manifest"])
        and release_manifest.get("evidence/fourth-word-rup-bundle-v1.sha256")
        == _sha256(sources["rup_proof_manifest"])
        and release_manifest.get("evidence/fourth-word-rup-revision-v1.json")
        == _sha256(sources["rup_revision"]),
        "v0.2.0 release manifest bindings differ",
    )
    zenodo = _load_json(sources["zenodo_archive_binding"])
    _require(
        zenodo.get("version_doi") == "10.5281/zenodo.22302261"
        and zenodo.get("concept_doi") == "10.5281/zenodo.22260709"
        and zenodo.get("release_commit")
        == "7f5a3b524d703985b5e6c36270173578598c8b3a"
        and zenodo.get("file")
        == {
            "key": (
                "ruturajr-raval/"
                "binary-covering-code-11-3-v0.2.0.zip"
            ),
            "size_bytes": 269833751,
            "md5": "326154a9b17cbced17bf750222744c81",
            "sha256": (
                "750003eba2e9f9baf5fee9ed93c679b3"
                "661daf6d8c68ca40eeb681202b5e72ff"
            ),
        }
        and zenodo["release_manifest"]["sha256"]
        == _sha256(sources["v0_2_release_manifest"])
        and zenodo["proof_manifests"]["root"]["sha256"]
        == _sha256(sources["root_proof_manifest"])
        and zenodo["proof_manifests"]["fourth_word_rup_v1"]["sha256"]
        == _sha256(sources["rup_proof_manifest"])
        and zenodo["proof_manifests"]["fourth_word_solver_drat_v2"]["sha256"]
        == _sha256(sources["solver_drat_proof_manifest"]),
        "Zenodo archive binding differs",
    )

    return {
        "baseline_covering_radius": 3,
        "canonical_parent_cases": 150,
        "certified_normalized_branch_closures": 112,
        "residual_normalized_branches": 38,
        "selected_fourth_word_branches": 350,
        "certified_selected_fourth_word_branches": 324,
        "residual_selected_fourth_word_branches": 26,
        "exact_value_resolved": False,
        "status": "pass",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    print(json.dumps(verify(args.root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
