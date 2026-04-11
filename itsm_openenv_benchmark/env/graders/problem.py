from __future__ import annotations

from typing import Any

from ...models import TaskDefinition
from .common import (
    PROBLEM_STAGE_PROGRESS,
    average_or_default,
    field_match_score,
    is_present,
    progress_ratio,
    weighted_component_score,
)


def _status_score(current: str | None, target: str | None) -> float:
    if current == target:
        return 1.0
    return progress_ratio(current, target, PROBLEM_STAGE_PROGRESS)


def _link_integrity(row: dict[str, Any], targets: dict[str, Any]) -> float:
    return field_match_score(row, targets, ("original_task", "service", "service_offering", "configuration_item"))


def _fix_completeness(row: dict[str, Any], targets: dict[str, Any]) -> float:
    target_status = str(targets.get("target_status"))
    current_status = str(row.get("status"))

    if target_status in {"new", "assess"}:
        return 1.0

    checks: list[float] = [1.0 if is_present(row.get("worknotes")) else 0.0]

    if target_status in {"root_cause", "fix_in_progress", "resolved", "closed"}:
        checks.append(1.0 if is_present(row.get("workaround")) else 0.0)
    if target_status in {"fix_in_progress", "resolved", "closed"}:
        checks.append(1.0 if is_present(row.get("fix_notes")) else 0.0)

    if current_status in {"resolved", "closed"} and target_status in {"resolved", "closed"}:
        checks.append(1.0 if is_present(row.get("fix_notes")) else 0.0)

    return average_or_default(checks, default=1.0)


def grade_problem(
    task: TaskDefinition,
    db_index: dict[str, dict[str, dict[str, Any]]],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    del history

    targets = task.grader_targets
    problem_id = str(targets["problem_id"])
    row = db_index["problem"].get(problem_id)

    if row is None:
        return {
            "score": 0.0,
            "consistency": 0.0,
            "components": {"status_progression": 0.0, "link_integrity": 0.0, "fix_completeness": 0.0},
            "violations": [f"problem row not found: {problem_id}"],
        }

    status_score = _status_score(row.get("status"), targets.get("target_status"))
    link_score = _link_integrity(row, targets)
    fix_score = _fix_completeness(row, targets)

    components = {
        "status_progression": status_score,
        "link_integrity": link_score,
        "fix_completeness": fix_score,
    }
    total = weighted_component_score(task.grader_weights, components)

    violations: list[str] = []
    if status_score < 1.0:
        violations.append("target problem status not reached")
    if link_score < 1.0:
        violations.append("problem linkage fields mismatch")
    if fix_score < 1.0:
        violations.append("missing workaround/fix evidence")

    return {
        "score": total,
        "consistency": link_score,
        "components": components,
        "violations": violations,
    }
