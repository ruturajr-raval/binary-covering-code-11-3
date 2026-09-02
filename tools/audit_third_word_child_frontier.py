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


def coordinate_cells(first: int, second: int, length: int) -> tuple[int, ...]:
    ambient = (1 << length) - 1
    return (
        first & second,
        first & (ambient ^ second),
        second & (ambient ^ first),
        ambient ^ (first | second),
    )


def orbit_descriptor(
    word: int,
    cells: tuple[int, ...],
) -> tuple[int, int, int, int]:
    return tuple(hamming_weight(word & cell) for cell in cells)


def is_third_word_candidate(
    word: int,
    parent: dict[str, object],
    length: int,
) -> bool:
    first = int(parent["first_word"])
    second = int(parent["second_word"])
    threshold = parent["second_descriptor"]
    return (
        0 <= word < 1 << length
        and word not in {0, first, second}
        and hamming_weight(word) >= int(parent["minimum_weight"])
        and (
            hamming_weight(word),
            hamming_weight(word & first),
        )
        >= (
            int(threshold["weight"]),
            int(threshold["intersection"]),
        )
    )


def independently_enumerate_orbits(
    parent: dict[str, object],
    length: int,
) -> tuple[int, list[dict[str, object]]]:
    first = int(parent["first_word"])
    second = int(parent["second_word"])
    cells = coordinate_cells(first, second, length)
    grouped: dict[tuple[int, int, int, int], tuple[int, int]] = {}
    candidate_count = 0
    for word in range(1 << length):
        if not is_third_word_candidate(word, parent, length):
            continue
        candidate_count += 1
        descriptor = orbit_descriptor(word, cells)
        previous = grouped.get(descriptor)
        if previous is None:
            grouped[descriptor] = (1, word)
        else:
            count, least_word = previous
            grouped[descriptor] = (count + 1, min(least_word, word))

    earlier_word_count = 0
    orbits = []
    for descriptor in sorted(grouped):
        orbit_size, canonical_word = grouped[descriptor]
        orbits.append(
            {
                "canonical_word": canonical_word,
                "descriptor": list(descriptor),
                "earlier_word_count": earlier_word_count,
                "orbit_size": orbit_size,
            }
        )
        earlier_word_count += orbit_size
    if earlier_word_count != candidate_count:
        raise SystemExit(
            f"{parent['case_id']}: candidate partition is incomplete"
        )
    return candidate_count, orbits


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
    encoded = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256((encoded + "\n").encode("ascii")).hexdigest()


def children_sha256(children: list[dict[str, object]]) -> str:
    text = "".join(
        f"{child['child_id']}:{child['child_sha256']}\n"
        for child in children
    )
    return hashlib.sha256(text.encode("ascii")).hexdigest()


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


def unique_ids(
    records: list[dict[str, object]],
    key: str,
    label: str,
) -> set[str]:
    identifiers = [str(record[key]) for record in records]
    if len(identifiers) != len(set(identifiers)):
        raise SystemExit(f"{label} contains duplicate identifiers")
    return set(identifiers)


def verify_sources(
    manifest: dict[str, object],
    paths: dict[str, Path],
    root: Path,
) -> None:
    if set(manifest["sources"]) != set(paths):
        raise SystemExit("frontier source list is incorrect")
    for label, path in paths.items():
        expected = {
            "path": display_path(path, root),
            "sha256": file_sha256(path),
        }
        if manifest["sources"][label] != expected:
            raise SystemExit(f"{label} source authentication failed")


def independently_classify_maximum_degree(
    parents: list[dict[str, object]],
) -> tuple[
    list[dict[str, object]],
    list[str],
    list[str],
    list[str],
]:
    records = []
    eliminated = []
    matching = []
    multiple_neighbor = []
    for parent in parents:
        case_id = str(parent["case_id"])
        minimum_distance = int(parent["minimum_weight"])
        second_weight = int(parent["second_descriptor"]["weight"])
        intersection = int(parent["second_descriptor"]["intersection"])
        first_second_distance = (
            minimum_distance + second_weight - 2 * intersection
        )
        if second_weight == minimum_distance:
            classification = "multiple_neighbor"
            multiple_neighbor.append(case_id)
        elif first_second_distance == minimum_distance:
            classification = "maximum_degree_contradiction"
            eliminated.append(case_id)
        else:
            classification = "matching"
            matching.append(case_id)
        records.append(
            {
                "case_id": case_id,
                "classification": classification,
                "first_second_distance": first_second_distance,
                "minimum_distance": minimum_distance,
                "second_weight": second_weight,
            }
        )
    return records, eliminated, matching, multiple_neighbor


def authenticate_proof_closure(
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
        artifacts[path_key] = {
            "path": display_path(path, root),
            "sha256": file_sha256(path),
        }

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
    parser.add_argument("frontier_manifest", type=Path)
    args = parser.parse_args()

    stage1 = load_json(args.stage1_parent_manifest)
    third = load_json(args.third_word_manifest)
    minimum_distance = load_json(args.minimum_distance_manifest)
    maximum_degree = load_json(args.maximum_degree_manifest)
    proof_index = load_json(args.third_word_proof_index)
    summary = load_json(args.case_reduction_summary)
    final_residual = load_json(args.final_residual_manifest)
    frontier = load_json(args.frontier_manifest)
    root = repository_root(args.stage1_parent_manifest)
    for source_path in (
        args.stage1_parent_manifest,
        args.third_word_manifest,
        args.minimum_distance_manifest,
        args.maximum_degree_manifest,
        args.third_word_proof_index,
        args.case_reduction_summary,
        args.final_residual_manifest,
        args.frontier_manifest,
    ):
        ensure_repository_path(source_path, root)

    verify_sources(
        frontier,
        {
            "case_reduction_summary": args.case_reduction_summary,
            "final_residual_manifest": args.final_residual_manifest,
            "maximum_degree_manifest": args.maximum_degree_manifest,
            "minimum_distance_manifest": args.minimum_distance_manifest,
            "stage1_parent_manifest": args.stage1_parent_manifest,
            "third_word_manifest": args.third_word_manifest,
            "third_word_proof_index": args.third_word_proof_index,
        },
        root,
    )
    if frontier["schema_version"] != 1:
        raise SystemExit("unsupported frontier schema")
    if frontier["problem"] != PROBLEM:
        raise SystemExit("frontier problem metadata is incorrect")
    if frontier["descriptor_order"] != THIRD_DESCRIPTOR_ORDER:
        raise SystemExit("frontier descriptor order is incorrect")
    if frontier["child_identity_fields"] != CHILD_IDENTITY_FIELDS:
        raise SystemExit("frontier child identity fields are incorrect")
    if frontier["index_conventions"] != INDEX_CONVENTIONS:
        raise SystemExit("frontier index conventions are incorrect")
    if stage1["descriptor_order"] != PARENT_DESCRIPTOR_ORDER:
        raise SystemExit("stage-1 descriptor order changed")
    if third["descriptor_order"] != THIRD_DESCRIPTOR_ORDER:
        raise SystemExit("third-word descriptor order changed")
    if int(stage1["length"]) != PROBLEM["length"]:
        raise SystemExit("stage-1 length changed")
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
    if third["source_parent_manifest_sha256"] != file_sha256(
        args.stage1_parent_manifest
    ):
        raise SystemExit("third-word source hash mismatch")
    if maximum_degree["source_residual_manifest_sha256"] != file_sha256(
        args.stage1_parent_manifest
    ):
        raise SystemExit("maximum-degree source hash mismatch")
    if proof_index["parent_manifest_sha256"] != file_sha256(
        args.stage1_parent_manifest
    ):
        raise SystemExit("proof-index parent hash mismatch")
    if proof_index["third_manifest_sha256"] != file_sha256(
        args.third_word_manifest
    ):
        raise SystemExit("proof-index third-word hash mismatch")
    if summary["stage1_residual_sha256"] != file_sha256(
        args.stage1_parent_manifest
    ):
        raise SystemExit("summary stage-1 hash mismatch")
    if final_residual["source_manifest_sha256"] != file_sha256(
        args.stage1_parent_manifest
    ):
        raise SystemExit("final residual source hash mismatch")
    if summary["advanced_inputs"]["maximum_degree"]["sha256"] != file_sha256(
        args.maximum_degree_manifest
    ):
        raise SystemExit("summary maximum-degree hash mismatch")
    if summary["advanced_inputs"]["third_word_proofs"]["sha256"] != file_sha256(
        args.third_word_proof_index
    ):
        raise SystemExit("summary proof-index hash mismatch")
    if not summary["all_accounted_for"]:
        raise SystemExit("case-reduction summary is incomplete")
    if not maximum_degree["valid"] or not proof_index["all_verified"]:
        raise SystemExit("advanced closure evidence is not verified")
    for path_key, hash_key in (
        ("proof_plan", "proof_plan_sha256"),
        ("branch_manifest", "branch_manifest_sha256"),
        ("parent_manifest", "parent_manifest_sha256"),
        ("third_manifest", "third_manifest_sha256"),
    ):
        proof_source = resolve_record_path(proof_index[path_key], root)
        if not proof_source.is_file():
            raise SystemExit(f"proof-index {path_key} is missing")
        if file_sha256(proof_source) != proof_index[hash_key]:
            raise SystemExit(f"proof-index {path_key} hash mismatch")

    stage1_cases = stage1["cases"]
    stage1_ids = unique_ids(stage1_cases, "case_id", "stage-1 manifest")
    proof_ids = unique_ids(
        proof_index["cases"],
        "case_id",
        "proof index",
    )
    (
        independent_maximum_degree_records,
        independent_maximum_degree_closed,
        independent_matching,
        independent_multiple_neighbor,
    ) = independently_classify_maximum_degree(stage1_cases)
    if maximum_degree["cases"] != independent_maximum_degree_records:
        raise SystemExit("maximum-degree case records are incorrect")
    if maximum_degree["maximum_degree_contradiction_cases"] != (
        independent_maximum_degree_closed
    ):
        raise SystemExit("maximum-degree contradiction list is incorrect")
    if maximum_degree["matching_cases"] != independent_matching:
        raise SystemExit("maximum-degree matching list is incorrect")
    if maximum_degree["multiple_neighbor_cases"] != (
        independent_multiple_neighbor
    ):
        raise SystemExit("maximum-degree multiple-neighbor list is incorrect")
    expected_maximum_degree_counts = {
        "matching": len(independent_matching),
        "maximum_degree_contradiction": len(
            independent_maximum_degree_closed
        ),
        "multiple_neighbor": len(independent_multiple_neighbor),
        "total": len(stage1_cases),
    }
    if maximum_degree["counts"] != expected_maximum_degree_counts:
        raise SystemExit("maximum-degree counts are incorrect")
    maximum_degree_closed_ids = set(
        independent_maximum_degree_closed
    )
    active_ids = unique_ids(
        final_residual["cases"],
        "case_id",
        "final residual",
    )
    if active_ids != set(summary["open_cases"]):
        raise SystemExit("active parent sets disagree")
    if proof_ids != set(summary["third_word_drat_cases"]):
        raise SystemExit("proof-closed parent sets disagree")
    if maximum_degree_closed_ids != set(
        summary["maximum_degree_normalization_cases"]
    ):
        raise SystemExit("maximum-degree parent sets disagree")
    if proof_ids | maximum_degree_closed_ids | active_ids != stage1_ids:
        raise SystemExit("parent statuses do not cover stage-1")
    if (
        proof_ids & maximum_degree_closed_ids
        or proof_ids & active_ids
        or maximum_degree_closed_ids & active_ids
    ):
        raise SystemExit("parent statuses overlap")

    maximum_degree_records = {
        str(record["case_id"]): record
        for record in maximum_degree["cases"]
    }
    proof_records = {
        str(record["case_id"]): record
        for record in proof_index["cases"]
    }
    matching_ids = set(independent_matching)
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
    if len(frontier["parents"]) != len(stage1_cases):
        raise SystemExit("frontier parent count is incorrect")

    all_children = []
    parent_status_children: dict[str, list[dict[str, object]]] = {
        ACTIVE: [],
        MAXIMUM_DEGREE_CLOSED: [],
        THIRD_WORD_DRAT_CLOSED: [],
    }
    branch_status_children: dict[str, list[dict[str, object]]] = {
        LIVE: [],
        EXCLUDED_MINIMUM_DISTANCE: [],
        EXCLUDED_MATCHING: [],
        CLOSED_WITH_MAXIMUM_DEGREE_PARENT: [],
        CLOSED_WITH_THIRD_WORD_DRAT_PARENT: [],
    }
    non_drat_children = []
    parent_statuses = Counter()
    stage1_index = 0
    non_drat_index = 0
    active_parent_index = 0
    live_index = 0
    active_parent_matching_parent_count = 0
    active_parent_matching_child_count = 0

    for parent_position, parent in enumerate(stage1_cases):
        case_id = str(parent["case_id"])
        retained_parent = frontier["parents"][parent_position]
        if retained_parent["parent_case_id"] != case_id:
            raise SystemExit(f"{case_id}: parent order is incorrect")
        if case_id in proof_ids:
            status = THIRD_WORD_DRAT_CLOSED
        elif case_id in maximum_degree_closed_ids:
            status = MAXIMUM_DEGREE_CLOSED
        else:
            status = ACTIVE

        candidate_count, orbits = independently_enumerate_orbits(
            parent,
            int(stage1["length"]),
        )
        expected_children = []
        matching_eligible = case_id in matching_ids
        minimum_distance_value = int(parent["minimum_weight"])
        minimum_distance_case = minimum_distance_cases[
            minimum_distance_value
        ]
        expected_constraint_profile = {
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
                "count": int(parent["unit_count"]),
                "sha256": str(parent["unit_sha256"]),
            },
            "matching": {
                "enforced": matching_eligible,
                "fixed_edge": [
                    0,
                    int(parent["first_word"]),
                ],
                "source": {
                    "path": display_path(
                        args.maximum_degree_manifest,
                        root,
                    ),
                    "sha256": file_sha256(
                        args.maximum_degree_manifest
                    ),
                },
            },
            "third_word_orbits": {
                "sha256": str(
                    next(
                        source_parent["orbit_manifest_sha256"]
                        for source_parent in third["parents"]
                        if source_parent["parent_case_id"] == case_id
                    )
                ),
                "source": {
                    "path": display_path(
                        args.third_word_manifest,
                        root,
                    ),
                    "sha256": file_sha256(
                        args.third_word_manifest
                    ),
                },
            },
        }
        for orbit_index, orbit in enumerate(orbits):
            identity = child_identity(case_id, orbit_index, orbit)
            canonical_word = int(orbit["canonical_word"])
            fixed_word_distances = {
                "first": hamming_weight(
                    canonical_word ^ int(parent["first_word"])
                ),
                "second": hamming_weight(
                    canonical_word ^ int(parent["second_word"])
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
                                int(parent["first_word"]),
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
            expected_child = {
                "active_parent_child_index": (
                    active_parent_index if status == ACTIVE else None
                ),
                "branch_status": branch_status,
                "canonical_word": canonical_word,
                "child_id": f"{case_id}::orbit-{orbit_index:03d}",
                "child_sha256": identity_sha256(identity),
                "constraint_units": {
                    "excluded_earlier_word_count": int(
                        orbit["earlier_word_count"]
                    ),
                    "selected_word_literal": canonical_word + 1,
                },
                "descriptor": orbit["descriptor"],
                "earlier_word_count": int(orbit["earlier_word_count"]),
                "fixed_word_distances": fixed_word_distances,
                "live_child_index": (
                    live_index if branch_status == LIVE else None
                ),
                "non_drat_child_index": (
                    non_drat_index
                    if status != THIRD_WORD_DRAT_CLOSED
                    else None
                ),
                "orbit_size": int(orbit["orbit_size"]),
                "parent_orbit_index": orbit_index,
                "parent_status": status,
                "stage1_child_index": stage1_index,
                "static_exclusion": static_exclusion,
            }
            expected_children.append(expected_child)
            stage1_index += 1
            if status != THIRD_WORD_DRAT_CLOSED:
                non_drat_index += 1
            if status == ACTIVE:
                active_parent_index += 1
            if branch_status == LIVE:
                live_index += 1

        if retained_parent["children"] != expected_children:
            raise SystemExit(f"{case_id}: child records are incorrect")
        if status == MAXIMUM_DEGREE_CLOSED:
            expected_closure = {
                "evidence": {
                    "path": display_path(
                        args.maximum_degree_manifest,
                        root,
                    ),
                    "sha256": file_sha256(args.maximum_degree_manifest),
                },
                "kind": "maximum_degree_contradiction",
            }
        elif status == THIRD_WORD_DRAT_CLOSED:
            expected_closure = authenticate_proof_closure(
                proof_records[case_id],
                proof_index,
                matching_ids,
                root,
            )
        else:
            expected_closure = None

        expected_parent_fields = {
            "candidate_word_count": candidate_count,
            "child_count": len(expected_children),
            "child_manifest_sha256": children_sha256(expected_children),
            "closure": expected_closure,
            "constraint_profile": expected_constraint_profile,
            "excluded_matching_child_count": sum(
                child["branch_status"] == EXCLUDED_MATCHING
                for child in expected_children
            ),
            "excluded_minimum_distance_child_count": sum(
                child["branch_status"] == EXCLUDED_MINIMUM_DISTANCE
                for child in expected_children
            ),
            "first_word": int(parent["first_word"]),
            "live_child_count": sum(
                child["branch_status"] == LIVE
                for child in expected_children
            ),
            "matching_eligible": matching_eligible,
            "maximum_degree_classification": str(
                maximum_degree_records[case_id]["classification"]
            ),
            "minimum_distance": int(parent["minimum_weight"]),
            "parent_case_id": case_id,
            "second_word": int(parent["second_word"]),
            "status": status,
        }
        for key, value in expected_parent_fields.items():
            if retained_parent[key] != value:
                raise SystemExit(f"{case_id}: {key} is incorrect")

        parent_statuses[status] += 1
        all_children.extend(expected_children)
        parent_status_children[status].extend(expected_children)
        for child in expected_children:
            branch_status_children[child["branch_status"]].append(
                child
            )
        if status != THIRD_WORD_DRAT_CLOSED:
            non_drat_children.extend(expected_children)
        if status == ACTIVE and matching_eligible:
            active_parent_matching_parent_count += 1
            active_parent_matching_child_count += len(expected_children)

    expected_counts = {
        "active_parent_child_count": len(
            parent_status_children[ACTIVE]
        ),
        "active_parent_matching_child_count": (
            active_parent_matching_child_count
        ),
        "active_parent_matching_parent_count": (
            active_parent_matching_parent_count
        ),
        "active_parent_count": parent_statuses[ACTIVE],
        "closed_maximum_degree_child_count": len(
            parent_status_children[MAXIMUM_DEGREE_CLOSED]
        ),
        "closed_maximum_degree_parent_count": parent_statuses[
            MAXIMUM_DEGREE_CLOSED
        ],
        "closed_third_word_drat_child_count": len(
            parent_status_children[THIRD_WORD_DRAT_CLOSED]
        ),
        "closed_third_word_drat_parent_count": parent_statuses[
            THIRD_WORD_DRAT_CLOSED
        ],
        "excluded_matching_child_count": len(
            branch_status_children[EXCLUDED_MATCHING]
        ),
        "excluded_minimum_distance_child_count": len(
            branch_status_children[EXCLUDED_MINIMUM_DISTANCE]
        ),
        "live_child_count": len(branch_status_children[LIVE]),
        "non_drat_child_count": len(non_drat_children),
        "non_drat_parent_count": (
            parent_statuses[ACTIVE]
            + parent_statuses[MAXIMUM_DEGREE_CLOSED]
        ),
        "stage1_child_count": len(all_children),
        "stage1_parent_count": len(stage1_cases),
    }
    certified_counts = {
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
    if expected_counts != certified_counts:
        raise SystemExit("independent frontier counts changed")
    if frontier["counts"] != expected_counts:
        raise SystemExit("retained frontier counts are incorrect")

    expected_digests = {
        "active_parent_children_sha256": children_sha256(
            parent_status_children[ACTIVE]
        ),
        "closed_maximum_degree_children_sha256": children_sha256(
            parent_status_children[MAXIMUM_DEGREE_CLOSED]
        ),
        "closed_third_word_drat_children_sha256": children_sha256(
            parent_status_children[THIRD_WORD_DRAT_CLOSED]
        ),
        "excluded_matching_children_sha256": children_sha256(
            branch_status_children[EXCLUDED_MATCHING]
        ),
        "excluded_minimum_distance_children_sha256": children_sha256(
            branch_status_children[EXCLUDED_MINIMUM_DISTANCE]
        ),
        "live_children_sha256": children_sha256(
            branch_status_children[LIVE]
        ),
        "non_drat_children_sha256": children_sha256(non_drat_children),
        "stage1_children_sha256": children_sha256(all_children),
    }
    if frontier["digests"] != expected_digests:
        raise SystemExit("retained frontier digests are incorrect")

    print(
        json.dumps(
            {
                "active_parent_child_count": expected_counts[
                    "active_parent_child_count"
                ],
                "active_parent_count": expected_counts[
                    "active_parent_count"
                ],
                "live_child_count": expected_counts[
                    "live_child_count"
                ],
                "non_drat_child_count": expected_counts[
                    "non_drat_child_count"
                ],
                "stage1_child_count": expected_counts[
                    "stage1_child_count"
                ],
                "valid": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
