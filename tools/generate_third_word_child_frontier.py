#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


ACTIVE = "active"
MAXIMUM_DEGREE_CLOSED = "closed_maximum_degree"
THIRD_WORD_DRAT_CLOSED = "closed_third_word_drat"
LIVE = "live"
EXCLUDED_MINIMUM_DISTANCE = "excluded_minimum_distance"
EXCLUDED_MATCHING = "excluded_matching"
CLOSED_WITH_MAXIMUM_DEGREE_PARENT = (
    "closed_with_maximum_degree_parent"
)
CLOSED_WITH_THIRD_WORD_DRAT_PARENT = (
    "closed_with_third_word_drat_parent"
)
PROBLEM = {
    "length": 11,
    "q": 2,
    "radius": 3,
    "target_size": 15,
}
PARENT_DESCRIPTOR_ORDER = [
    "weight",
    "intersection_with_first_word",
]
THIRD_DESCRIPTOR_ORDER = [
    "inside_both_fixed_words",
    "inside_first_only",
    "inside_second_only",
    "inside_neither",
]
CHILD_IDENTITY_FIELDS = [
    "canonical_word",
    "descriptor",
    "earlier_word_count",
    "orbit_size",
    "parent_case_id",
    "parent_orbit_index",
]
INDEX_CONVENTIONS = {
    "active_parent_child_index": (
        "Zero-based index over all children whose parent remains active, "
        "including children excluded by static constraints."
    ),
    "live_child_index": (
        "Zero-based index over children that survive the parent closures, "
        "minimum-distance clauses, and matching constraint."
    ),
    "non_drat_child_index": (
        "Zero-based index after removing checked third-word DRAT "
        "parent closures but before maximum-degree closures."
    ),
    "parent_orbit_index": (
        "Zero-based descriptor-order index within one parent."
    ),
    "stage1_child_index": (
        "Zero-based index over all stage-1 third-word children."
    ),
}


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="ascii"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hamming_weight(word: int) -> int:
    return bin(word).count("1")


def indexed(
    records: list[dict[str, object]],
    key: str,
) -> dict[str, dict[str, object]]:
    result = {str(record[key]): record for record in records}
    if len(result) != len(records):
        raise SystemExit(f"duplicate {key} values")
    return result


def child_identity(
    parent_case_id: str,
    parent_orbit_index: int,
    orbit: dict[str, object],
) -> dict[str, object]:
    return {
        "canonical_word": int(orbit["canonical_word"]),
        "descriptor": [int(value) for value in orbit["descriptor"]],
        "earlier_word_count": int(orbit["earlier_word_count"]),
        "orbit_size": int(orbit["orbit_size"]),
        "parent_case_id": parent_case_id,
        "parent_orbit_index": parent_orbit_index,
    }


def identity_sha256(identity: dict[str, object]) -> str:
    payload = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256((payload + "\n").encode("ascii")).hexdigest()


def digest_children(children: list[dict[str, object]]) -> str:
    payload = "".join(
        f"{child['child_id']}:{child['child_sha256']}\n"
        for child in children
    )
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def source_orbit_digest(orbits: list[dict[str, object]]) -> str:
    payload = ""
    for orbit in orbits:
        descriptor = ",".join(
            str(value) for value in orbit["descriptor"]
        )
        payload += (
            f"{descriptor}:{orbit['canonical_word']}:"
            f"{orbit['orbit_size']}:{orbit['earlier_word_count']}\n"
        )
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def repository_root(stage1_parent_manifest: Path) -> Path:
    return stage1_parent_manifest.resolve().parents[1]


def ensure_repository_path(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise SystemExit(f"path is outside the repository: {path}")
    return resolved


def resolve_record_path(value: object, root: Path) -> Path:
    path = Path(str(value))
    if not path.is_absolute():
        path = root / path
    return ensure_repository_path(path, root)


def display_path(path: Path, root: Path) -> str:
    return str(ensure_repository_path(path, root).relative_to(root))


def source_record(path: Path, root: Path) -> dict[str, str]:
    return {
        "path": display_path(path, root),
        "sha256": file_sha256(path),
    }


def recorded_artifact(
    value: object,
    expected_sha256: object,
    root: Path,
) -> dict[str, str]:
    path = resolve_record_path(value, root)
    if path.is_file() and file_sha256(path) != expected_sha256:
        raise SystemExit(f"artifact hash mismatch: {path}")
    return {
        "path": display_path(path, root),
        "sha256": str(expected_sha256),
    }


def require_hash(
    record: dict[str, object],
    key: str,
    path: Path,
    label: str,
) -> None:
    if record[key] != file_sha256(path):
        raise SystemExit(f"{label} hash mismatch")


def proof_closure(
    proof: dict[str, object],
    proof_index: dict[str, object],
    matching_ids: set[str],
    root: Path,
) -> dict[str, object]:
    case_id = str(proof["case_id"])
    artifact_keys = (
        ("formula_metadata", "formula_metadata_sha256"),
        ("proof", "proof_sha256"),
        ("proof_summary", "proof_summary_sha256"),
        ("proof_check", "proof_check_sha256"),
    )
    artifacts = {}
    for path_key, hash_key in artifact_keys:
        path = resolve_record_path(proof[path_key], root)
        if not path.is_file():
            raise SystemExit(f"{case_id}: {path_key} file is missing")
        if file_sha256(path) != proof[hash_key]:
            raise SystemExit(f"{case_id}: {path_key} hash mismatch")
        artifacts[path_key] = source_record(path, root)

    metadata = load_json(resolve_record_path(proof["formula_metadata"], root))
    proof_summary = load_json(
        resolve_record_path(proof["proof_summary"], root)
    )
    proof_check = load_json(resolve_record_path(proof["proof_check"], root))
    if metadata["parent_case_id"] != case_id:
        raise SystemExit(f"{case_id}: formula metadata case mismatch")
    if metadata["formula_sha256"] != proof["formula_sha256"]:
        raise SystemExit(f"{case_id}: formula metadata hash mismatch")
    matching = bool(
        proof.get("enforce_minimum_distance_matching", False)
    )
    if (
        bool(
            metadata.get(
                "enforce_minimum_distance_matching",
                False,
            )
        )
        != matching
    ):
        raise SystemExit(f"{case_id}: matching metadata mismatch")
    if matching and case_id not in matching_ids:
        raise SystemExit(f"{case_id}: matching proof is outside its scope")
    if proof_summary["case_id"] != case_id:
        raise SystemExit(f"{case_id}: proof summary case mismatch")
    if proof_summary["case_formula_sha256"] != proof["formula_sha256"]:
        raise SystemExit(f"{case_id}: proof summary formula mismatch")
    if proof_summary["proof_compressed_sha256"] != proof["proof_sha256"]:
        raise SystemExit(f"{case_id}: proof summary trace mismatch")
    if proof_check["case_id"] != case_id or not proof_check["verified"]:
        raise SystemExit(f"{case_id}: proof check is not verified")
    if proof_check["checker"] != proof_index["checker"]:
        raise SystemExit(f"{case_id}: proof checker mismatch")
    if proof_check["checker_commit"] != proof_index["checker_commit"]:
        raise SystemExit(f"{case_id}: proof checker commit mismatch")
    if proof_check["formula_sha256"] != proof["formula_sha256"]:
        raise SystemExit(f"{case_id}: checked formula mismatch")
    if proof_check["proof_compressed_sha256"] != proof["proof_sha256"]:
        raise SystemExit(f"{case_id}: checked proof mismatch")
    if not proof["verified"]:
        raise SystemExit(f"{case_id}: proof record is not verified")

    formula_path = resolve_record_path(proof["formula"], root)
    if formula_path.is_file() and file_sha256(formula_path) != (
        proof["formula_sha256"]
    ):
        raise SystemExit(f"{case_id}: generated formula hash mismatch")
    return {
        "artifacts": artifacts,
        "checker": str(proof_index["checker"]),
        "checker_commit": str(proof_index["checker_commit"]),
        "enforce_minimum_distance_matching": matching,
        "formula": {
            "path": display_path(formula_path, root),
            "sha256": str(proof["formula_sha256"]),
        },
        "kind": "checked_drat",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage1_parent_manifest", type=Path)
    parser.add_argument("third_word_manifest", type=Path)
    parser.add_argument("minimum_distance_manifest", type=Path)
    parser.add_argument("maximum_degree_manifest", type=Path)
    parser.add_argument("third_word_proof_index", type=Path)
    parser.add_argument("case_reduction_summary", type=Path)
    parser.add_argument("final_residual_manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    stage1 = load_json(args.stage1_parent_manifest)
    third = load_json(args.third_word_manifest)
    minimum_distance = load_json(args.minimum_distance_manifest)
    maximum_degree = load_json(args.maximum_degree_manifest)
    proof_index = load_json(args.third_word_proof_index)
    summary = load_json(args.case_reduction_summary)
    final_residual = load_json(args.final_residual_manifest)
    root = repository_root(args.stage1_parent_manifest)
    for source_path in (
        args.stage1_parent_manifest,
        args.third_word_manifest,
        args.minimum_distance_manifest,
        args.maximum_degree_manifest,
        args.third_word_proof_index,
        args.case_reduction_summary,
        args.final_residual_manifest,
    ):
        ensure_repository_path(source_path, root)

    require_hash(
        third,
        "source_parent_manifest_sha256",
        args.stage1_parent_manifest,
        "third-word source",
    )
    require_hash(
        maximum_degree,
        "source_residual_manifest_sha256",
        args.stage1_parent_manifest,
        "maximum-degree source",
    )
    require_hash(
        proof_index,
        "parent_manifest_sha256",
        args.stage1_parent_manifest,
        "third-word proof source",
    )
    require_hash(
        proof_index,
        "third_manifest_sha256",
        args.third_word_manifest,
        "third-word proof manifest",
    )
    require_hash(
        summary,
        "stage1_residual_sha256",
        args.stage1_parent_manifest,
        "case-reduction stage-1 source",
    )
    require_hash(
        final_residual,
        "source_manifest_sha256",
        args.stage1_parent_manifest,
        "final residual source",
    )
    if summary["advanced_inputs"]["maximum_degree"]["sha256"] != file_sha256(
        args.maximum_degree_manifest
    ):
        raise SystemExit("case-reduction maximum-degree hash mismatch")
    if summary["advanced_inputs"]["third_word_proofs"]["sha256"] != file_sha256(
        args.third_word_proof_index
    ):
        raise SystemExit("case-reduction third-word proof hash mismatch")
    if not maximum_degree["valid"]:
        raise SystemExit("maximum-degree evidence is not valid")
    if not proof_index["all_verified"]:
        raise SystemExit("third-word proof index is not fully verified")
    if not summary["all_accounted_for"]:
        raise SystemExit("case-reduction summary is incomplete")
    if int(stage1["length"]) != PROBLEM["length"]:
        raise SystemExit("stage-1 length changed")
    if stage1["descriptor_order"] != PARENT_DESCRIPTOR_ORDER:
        raise SystemExit("stage-1 descriptor order changed")
    if third["descriptor_order"] != THIRD_DESCRIPTOR_ORDER:
        raise SystemExit("third-word descriptor order changed")
    if summary["problem"] != PROBLEM:
        raise SystemExit("case-reduction problem metadata changed")
    if minimum_distance["problem"] != {
        "length": 11,
        "q": 2,
        "radius": 3,
        "size": 15,
    }:
        raise SystemExit("minimum-distance problem metadata changed")
    minimum_distance_cases = {
        int(case["minimum_distance"]): case
        for case in minimum_distance["cases"]
    }
    if set(minimum_distance_cases) != {1, 2, 3, 4, 5}:
        raise SystemExit("minimum-distance branches are incomplete")

    stage1_cases = stage1["cases"]
    third_parents = indexed(third["parents"], "parent_case_id")
    stage1_by_id = indexed(stage1_cases, "case_id")
    if set(third_parents) != set(stage1_by_id):
        raise SystemExit("third-word manifest does not cover stage-1 parents")

    maximum_degree_cases = indexed(maximum_degree["cases"], "case_id")
    if set(maximum_degree_cases) != set(stage1_by_id):
        raise SystemExit("maximum-degree classifications are incomplete")

    proof_records = indexed(proof_index["cases"], "case_id")
    proof_ids = set(proof_records)
    maximum_degree_closed_ids = set(
        maximum_degree["maximum_degree_contradiction_cases"]
    )
    active_ids = {
        str(case["case_id"])
        for case in final_residual["cases"]
    }
    if active_ids != set(summary["open_cases"]):
        raise SystemExit("final residual and case-reduction summary disagree")
    if proof_ids != set(summary["third_word_drat_cases"]):
        raise SystemExit("proof index and case-reduction summary disagree")
    if maximum_degree_closed_ids != set(
        summary["maximum_degree_normalization_cases"]
    ):
        raise SystemExit("maximum-degree closures and summary disagree")
    if (
        proof_ids & maximum_degree_closed_ids
        or proof_ids & active_ids
        or maximum_degree_closed_ids & active_ids
    ):
        raise SystemExit("advanced parent classifications overlap")
    if proof_ids | maximum_degree_closed_ids | active_ids != set(stage1_by_id):
        raise SystemExit("advanced parent classifications are incomplete")

    matching_ids = set(maximum_degree["matching_cases"])
    matching_proof_ids = {
        case_id
        for case_id, proof in proof_records.items()
        if proof.get("enforce_minimum_distance_matching", False)
    }
    if not matching_proof_ids <= matching_ids:
        raise SystemExit("matching-constrained proof is outside its scope")
    if matching_proof_ids != set(
        summary["matching_constrained_third_word_drat_cases"]
    ):
        raise SystemExit("matching-constrained proof summary changed")
    parents = []
    all_children: list[dict[str, object]] = []
    children_by_parent_status: dict[str, list[dict[str, object]]] = {
        ACTIVE: [],
        MAXIMUM_DEGREE_CLOSED: [],
        THIRD_WORD_DRAT_CLOSED: [],
    }
    children_by_branch_status: dict[str, list[dict[str, object]]] = {
        LIVE: [],
        EXCLUDED_MINIMUM_DISTANCE: [],
        EXCLUDED_MATCHING: [],
        CLOSED_WITH_MAXIMUM_DEGREE_PARENT: [],
        CLOSED_WITH_THIRD_WORD_DRAT_PARENT: [],
    }
    non_drat_children: list[dict[str, object]] = []
    stage1_child_index = 0
    non_drat_child_index = 0
    active_parent_child_index = 0
    live_child_index = 0

    for parent_case in stage1_cases:
        case_id = str(parent_case["case_id"])
        third_parent = third_parents[case_id]
        if case_id in proof_ids:
            status = THIRD_WORD_DRAT_CLOSED
        elif case_id in maximum_degree_closed_ids:
            status = MAXIMUM_DEGREE_CLOSED
        else:
            status = ACTIVE

        matching_eligible = case_id in matching_ids
        minimum_distance_value = int(parent_case["minimum_weight"])
        minimum_distance_case = minimum_distance_cases[
            minimum_distance_value
        ]
        constraint_profile = {
            "minimum_distance": {
                "formula": recorded_artifact(
                    minimum_distance_case["formula"],
                    minimum_distance_case["sha256"],
                    root,
                ),
                "forbidden_pair_clauses": int(
                    minimum_distance_case["forbidden_pair_clauses"]
                ),
                "threshold": minimum_distance_value,
            },
            "parent_units": {
                "count": int(parent_case["unit_count"]),
                "sha256": str(parent_case["unit_sha256"]),
            },
            "matching": {
                "enforced": matching_eligible,
                "fixed_edge": [
                    0,
                    int(parent_case["first_word"]),
                ],
                "source": source_record(
                    args.maximum_degree_manifest,
                    root,
                ),
            },
            "third_word_orbits": {
                "sha256": str(
                    third_parent["orbit_manifest_sha256"]
                ),
                "source": source_record(
                    args.third_word_manifest,
                    root,
                ),
            },
        }
        children = []
        for orbit_index, orbit in enumerate(third_parent["orbits"]):
            identity = child_identity(case_id, orbit_index, orbit)
            canonical_word = int(identity["canonical_word"])
            fixed_word_distances = {
                "first": hamming_weight(
                    canonical_word ^ int(parent_case["first_word"])
                ),
                "second": hamming_weight(
                    canonical_word ^ int(parent_case["second_word"])
                ),
                "zero": hamming_weight(canonical_word),
            }
            if status == THIRD_WORD_DRAT_CLOSED:
                branch_status = CLOSED_WITH_THIRD_WORD_DRAT_PARENT
                static_exclusion = None
            elif status == MAXIMUM_DEGREE_CLOSED:
                branch_status = CLOSED_WITH_MAXIMUM_DEGREE_PARENT
                static_exclusion = None
            else:
                minimum_distance_violations = [
                    label
                    for label, distance in fixed_word_distances.items()
                    if distance < minimum_distance_value
                ]
                if minimum_distance_violations:
                    branch_status = EXCLUDED_MINIMUM_DISTANCE
                    static_exclusion = {
                        "kind": "minimum_distance",
                        "threshold": minimum_distance_value,
                        "violating_fixed_words": (
                            minimum_distance_violations
                        ),
                    }
                else:
                    matching_violations = [
                        label
                        for label in ("zero", "first")
                        if (
                            matching_eligible
                            and fixed_word_distances[label]
                            == minimum_distance_value
                        )
                    ]
                    if matching_violations:
                        branch_status = EXCLUDED_MATCHING
                        static_exclusion = {
                            "fixed_edge": [
                                0,
                                int(parent_case["first_word"]),
                            ],
                            "kind": "matching",
                            "threshold": minimum_distance_value,
                            "violating_fixed_words": (
                                matching_violations
                            ),
                        }
                    else:
                        branch_status = LIVE
                        static_exclusion = None
            child = {
                "active_parent_child_index": (
                    active_parent_child_index
                    if status == ACTIVE
                    else None
                ),
                "branch_status": branch_status,
                "canonical_word": canonical_word,
                "child_id": f"{case_id}::orbit-{orbit_index:03d}",
                "child_sha256": identity_sha256(identity),
                "constraint_units": {
                    "excluded_earlier_word_count": int(
                        identity["earlier_word_count"]
                    ),
                    "selected_word_literal": canonical_word + 1,
                },
                "descriptor": identity["descriptor"],
                "earlier_word_count": identity["earlier_word_count"],
                "fixed_word_distances": fixed_word_distances,
                "live_child_index": (
                    live_child_index
                    if branch_status == LIVE
                    else None
                ),
                "non_drat_child_index": (
                    non_drat_child_index
                    if status != THIRD_WORD_DRAT_CLOSED
                    else None
                ),
                "orbit_size": identity["orbit_size"],
                "parent_orbit_index": orbit_index,
                "parent_status": status,
                "stage1_child_index": stage1_child_index,
                "static_exclusion": static_exclusion,
            }
            children.append(child)
            all_children.append(child)
            children_by_parent_status[status].append(child)
            children_by_branch_status[branch_status].append(child)
            stage1_child_index += 1
            if status != THIRD_WORD_DRAT_CLOSED:
                non_drat_children.append(child)
                non_drat_child_index += 1
            if status == ACTIVE:
                active_parent_child_index += 1
            if branch_status == LIVE:
                live_child_index += 1

        if len(children) != int(third_parent["orbit_count"]):
            raise SystemExit(f"{case_id}: child count changed")
        if source_orbit_digest(third_parent["orbits"]) != (
            third_parent["orbit_manifest_sha256"]
        ):
            raise SystemExit(f"{case_id}: source orbit digest is invalid")

        classification = str(maximum_degree_cases[case_id]["classification"])
        if status == MAXIMUM_DEGREE_CLOSED:
            closure = {
                "evidence": source_record(
                    args.maximum_degree_manifest,
                    root,
                ),
                "kind": "maximum_degree_contradiction",
            }
        elif status == THIRD_WORD_DRAT_CLOSED:
            closure = proof_closure(
                proof_records[case_id],
                proof_index,
                matching_ids,
                root,
            )
        else:
            closure = None

        parents.append(
            {
                "candidate_word_count": int(
                    third_parent["candidate_word_count"]
                ),
                "child_count": len(children),
                "child_manifest_sha256": digest_children(children),
                "children": children,
                "closure": closure,
                "constraint_profile": constraint_profile,
                "excluded_matching_child_count": sum(
                    child["branch_status"] == EXCLUDED_MATCHING
                    for child in children
                ),
                "excluded_minimum_distance_child_count": sum(
                    child["branch_status"]
                    == EXCLUDED_MINIMUM_DISTANCE
                    for child in children
                ),
                "first_word": int(parent_case["first_word"]),
                "live_child_count": sum(
                    child["branch_status"] == LIVE
                    for child in children
                ),
                "matching_eligible": matching_eligible,
                "maximum_degree_classification": classification,
                "minimum_distance": int(parent_case["minimum_weight"]),
                "parent_case_id": case_id,
                "second_word": int(parent_case["second_word"]),
                "status": status,
            }
        )

    status_parent_counts = Counter(
        str(parent["status"])
        for parent in parents
    )
    status_child_counts = {
        status: len(children)
        for status, children in children_by_parent_status.items()
    }
    active_matching_parents = [
        parent
        for parent in parents
        if parent["status"] == ACTIVE and parent["matching_eligible"]
    ]
    active_parent_matching_children = sum(
        int(parent["child_count"])
        for parent in active_matching_parents
    )

    counts = {
        "active_parent_child_count": status_child_counts[ACTIVE],
        "active_parent_matching_child_count": (
            active_parent_matching_children
        ),
        "active_parent_matching_parent_count": len(
            active_matching_parents
        ),
        "active_parent_count": status_parent_counts[ACTIVE],
        "closed_maximum_degree_child_count": status_child_counts[
            MAXIMUM_DEGREE_CLOSED
        ],
        "closed_maximum_degree_parent_count": status_parent_counts[
            MAXIMUM_DEGREE_CLOSED
        ],
        "closed_third_word_drat_child_count": status_child_counts[
            THIRD_WORD_DRAT_CLOSED
        ],
        "closed_third_word_drat_parent_count": status_parent_counts[
            THIRD_WORD_DRAT_CLOSED
        ],
        "excluded_matching_child_count": len(
            children_by_branch_status[EXCLUDED_MATCHING]
        ),
        "excluded_minimum_distance_child_count": len(
            children_by_branch_status[EXCLUDED_MINIMUM_DISTANCE]
        ),
        "live_child_count": len(children_by_branch_status[LIVE]),
        "non_drat_child_count": len(non_drat_children),
        "non_drat_parent_count": (
            status_parent_counts[ACTIVE]
            + status_parent_counts[MAXIMUM_DEGREE_CLOSED]
        ),
        "stage1_child_count": len(all_children),
        "stage1_parent_count": len(parents),
    }
    expected_counts = {
        "active_parent_child_count": 2548,
        "active_parent_matching_child_count": 1870,
        "active_parent_matching_parent_count": 30,
        "active_parent_count": 38,
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
    }
    if counts != expected_counts:
        raise SystemExit(
            f"third-word frontier counts changed: {counts} != "
            f"{expected_counts}"
        )

    report = {
        "schema_version": 1,
        "problem": PROBLEM,
        "descriptor_order": THIRD_DESCRIPTOR_ORDER,
        "child_identity_fields": CHILD_IDENTITY_FIELDS,
        "counts": counts,
        "digests": {
            "active_parent_children_sha256": digest_children(
                children_by_parent_status[ACTIVE]
            ),
            "closed_maximum_degree_children_sha256": digest_children(
                children_by_parent_status[MAXIMUM_DEGREE_CLOSED]
            ),
            "closed_third_word_drat_children_sha256": digest_children(
                children_by_parent_status[THIRD_WORD_DRAT_CLOSED]
            ),
            "excluded_matching_children_sha256": digest_children(
                children_by_branch_status[EXCLUDED_MATCHING]
            ),
            "excluded_minimum_distance_children_sha256": digest_children(
                children_by_branch_status[EXCLUDED_MINIMUM_DISTANCE]
            ),
            "live_children_sha256": digest_children(
                children_by_branch_status[LIVE]
            ),
            "non_drat_children_sha256": digest_children(non_drat_children),
            "stage1_children_sha256": digest_children(all_children),
        },
        "index_conventions": INDEX_CONVENTIONS,
        "sources": {
            "case_reduction_summary": source_record(
                args.case_reduction_summary,
                root,
            ),
            "final_residual_manifest": source_record(
                args.final_residual_manifest,
                root,
            ),
            "maximum_degree_manifest": source_record(
                args.maximum_degree_manifest,
                root,
            ),
            "minimum_distance_manifest": source_record(
                args.minimum_distance_manifest,
                root,
            ),
            "stage1_parent_manifest": source_record(
                args.stage1_parent_manifest,
                root,
            ),
            "third_word_manifest": source_record(
                args.third_word_manifest,
                root,
            ),
            "third_word_proof_index": source_record(
                args.third_word_proof_index,
                root,
            ),
        },
        "parents": parents,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    print(
        json.dumps(
            {
                "active_parent_count": counts["active_parent_count"],
                "active_parent_child_count": counts[
                    "active_parent_child_count"
                ],
                "live_child_count": counts["live_child_count"],
                "non_drat_child_count": counts["non_drat_child_count"],
                "output": str(args.output),
                "stage1_child_count": counts["stage1_child_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
