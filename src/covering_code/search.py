from __future__ import annotations

from typing import Any

from .core import verify_code


def solve_with_cp_sat(
    *,
    length: int,
    radius: int,
    size: int,
    time_limit: float,
    workers: int,
    seed: int,
    anchor_zero: bool,
) -> tuple[dict[str, Any], list[int] | None]:
    try:
        from ortools.sat.python import cp_model
    except ImportError as exc:
        raise RuntimeError(
            "OR-Tools is required for CP-SAT search"
        ) from exc

    if time_limit <= 0:
        raise ValueError("time limit must be positive")
    if workers <= 0:
        raise ValueError("worker count must be positive")

    ambient_size = 1 << length
    model = cp_model.CpModel()
    selected = [
        model.new_bool_var(f"selected_{word}")
        for word in range(ambient_size)
    ]
    model.add(sum(selected) == size)
    if anchor_zero:
        model.add(selected[0] == 1)

    balls: list[list[int]] = []
    for target in range(ambient_size):
        centers = [
            center
            for center in range(ambient_size)
            if bin(center ^ target).count("1") <= radius
        ]
        balls.append(centers)
        model.add(sum(selected[center] for center in centers) >= 1)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = workers
    solver.parameters.random_seed = seed
    status = solver.solve(model)
    status_name = solver.status_name(status)
    summary: dict[str, Any] = {
        "length": length,
        "radius": radius,
        "size": size,
        "anchor_zero": anchor_zero,
        "time_limit_seconds": time_limit,
        "workers": workers,
        "seed": seed,
        "status": status_name,
        "solver_wall_seconds": solver.wall_time,
        "branches": solver.num_branches,
        "conflicts": solver.num_conflicts,
        "proof_trace_available": False,
    }

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        summary["valid"] = False
        return summary, None

    code = [
        word
        for word in range(ambient_size)
        if solver.value(selected[word])
    ]
    report = verify_code(code, length=length, radius=radius)
    if len(code) != size or not report.valid:
        raise RuntimeError("CP-SAT decoded to an invalid covering code")
    summary["valid"] = True
    summary["verification"] = report.to_dict()
    return summary, code


def maximize_coverage_with_cp_sat(
    *,
    length: int,
    radius: int,
    size: int,
    time_limit: float,
    workers: int,
    seed: int,
    anchor_zero: bool,
    initial_code: list[int] | None,
) -> tuple[dict[str, Any], list[int] | None]:
    try:
        from ortools.sat.python import cp_model
    except ImportError as exc:
        raise RuntimeError(
            "OR-Tools is required for CP-SAT search"
        ) from exc

    if time_limit <= 0:
        raise ValueError("time limit must be positive")
    if workers <= 0:
        raise ValueError("worker count must be positive")

    ambient_size = 1 << length
    if initial_code is not None:
        if len(initial_code) != size or len(set(initial_code)) != size:
            raise ValueError("initial code has the wrong size or duplicates")
        if any(word < 0 or word >= ambient_size for word in initial_code):
            raise ValueError("initial codeword is outside the cube")

    model = cp_model.CpModel()
    selected = [
        model.new_bool_var(f"selected_{word}")
        for word in range(ambient_size)
    ]
    covered = [
        model.new_bool_var(f"covered_{word}")
        for word in range(ambient_size)
    ]
    model.add(sum(selected) == size)
    if anchor_zero:
        model.add(selected[0] == 1)

    for target in range(ambient_size):
        centers = [
            center
            for center in range(ambient_size)
            if bin(center ^ target).count("1") <= radius
        ]
        model.add(
            sum(selected[center] for center in centers) >= covered[target]
        )
    model.maximize(sum(covered))

    if initial_code is not None:
        initial = set(initial_code)
        for word, variable in enumerate(selected):
            model.add_hint(variable, int(word in initial))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = workers
    solver.parameters.random_seed = seed
    status = solver.solve(model)
    status_name = solver.status_name(status)
    summary: dict[str, Any] = {
        "length": length,
        "radius": radius,
        "size": size,
        "anchor_zero": anchor_zero,
        "time_limit_seconds": time_limit,
        "workers": workers,
        "seed": seed,
        "status": status_name,
        "solver_wall_seconds": solver.wall_time,
        "branches": solver.num_branches,
        "conflicts": solver.num_conflicts,
        "proof_trace_available": False,
    }
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        summary["valid"] = False
        return summary, None

    code = [
        word
        for word in range(ambient_size)
        if solver.value(selected[word])
    ]
    report = verify_code(code, length=length, radius=radius)
    if len(code) != size:
        raise RuntimeError("CP-SAT decoded to a code with the wrong size")
    covered_count = ambient_size - len(report.uncovered_words)
    summary.update(
        {
            "valid": report.valid,
            "covered_words": covered_count,
            "objective_value": solver.objective_value,
            "best_objective_bound": solver.best_objective_bound,
            "verification": report.to_dict(),
        }
    )
    return summary, code


def repair_with_cp_sat(
    *,
    initial_code: list[int],
    minimum_overlap: int,
    length: int,
    radius: int,
    size: int,
    time_limit: float,
    workers: int,
    seed: int,
    anchor_zero: bool,
) -> tuple[dict[str, Any], list[int] | None]:
    try:
        from ortools.sat.python import cp_model
    except ImportError as exc:
        raise RuntimeError(
            "OR-Tools is required for CP-SAT repair"
        ) from exc

    ambient_size = 1 << length
    if len(initial_code) != size or len(set(initial_code)) != size:
        raise ValueError("initial code has the wrong size or duplicates")
    if minimum_overlap < 0 or minimum_overlap > size:
        raise ValueError("minimum overlap is outside the code size")
    if time_limit <= 0 or workers <= 0:
        raise ValueError("time limit and worker count must be positive")

    model = cp_model.CpModel()
    selected = [
        model.new_bool_var(f"selected_{word}")
        for word in range(ambient_size)
    ]
    model.add(sum(selected) == size)
    model.add(
        sum(selected[word] for word in initial_code) >= minimum_overlap
    )
    if anchor_zero:
        model.add(selected[0] == 1)
    for target in range(ambient_size):
        model.add(
            sum(
                selected[center]
                for center in range(ambient_size)
                if bin(center ^ target).count("1") <= radius
            ) >= 1
        )

    initial = set(initial_code)
    for word, variable in enumerate(selected):
        model.add_hint(variable, int(word in initial))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = workers
    solver.parameters.random_seed = seed
    status = solver.solve(model)
    status_name = solver.status_name(status)
    summary: dict[str, Any] = {
        "length": length,
        "radius": radius,
        "size": size,
        "minimum_overlap": minimum_overlap,
        "anchor_zero": anchor_zero,
        "time_limit_seconds": time_limit,
        "workers": workers,
        "seed": seed,
        "status": status_name,
        "solver_wall_seconds": solver.wall_time,
        "branches": solver.num_branches,
        "conflicts": solver.num_conflicts,
        "proof_trace_available": False,
    }
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        summary["valid"] = False
        return summary, None

    code = [
        word
        for word in range(ambient_size)
        if solver.value(selected[word])
    ]
    report = verify_code(code, length=length, radius=radius)
    overlap = len(set(code) & initial)
    if len(code) != size or overlap < minimum_overlap or not report.valid:
        raise RuntimeError("CP-SAT decoded to an invalid repair")
    summary.update(
        {
            "valid": True,
            "actual_overlap": overlap,
            "verification": report.to_dict(),
        }
    )
    return summary, code
