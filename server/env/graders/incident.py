from __future__ import annotations

from typing import Any

from ..models import TaskDefinition
from .common import (
    INCIDENT_STATUS_PROGRESS,
    field_match_score,
    is_present,
    progress_ratio,
    weighted_component_score,
)


def _status_score(current: str | None, target: str | None) -> float:
    if current == target:
        return 1.0
    if target == "resolved" and current == "closed":
        return 1.0
    return progress_ratio(current, target, INCIDENT_STATUS_PROGRESS)


def _priority_consistency(row: dict[str, Any], targets: dict[str, Any]) -> float:
    return field_match_score(row, targets, ("priority", "impact", "urgency"))


def grade_incident(
    task: TaskDefinition,
    db_index: dict[str, dict[str, dict[str, Any]]],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    targets = task.grader_targets
    incident_id = str(targets["incident_id"])
    row = db_index["incident"].get(incident_id)

    if row is None:
        return {
            "score": 0.0,
            "consistency": 0.0,
            "components": {"status": 0.0, "assignment": 0.0, "notes": 0.0, "priority_consistency": 0.0},
            "violations": [f"incident row not found: {incident_id}"],
        }

    status_score = _status_score(row.get("status"), targets.get("target_status"))

    expected_group = targets.get("assignment_group")
    assignment_score = 1.0 if (expected_group is None or row.get("assignment_group") == expected_group) else 0.0
    if assignment_score == 0.0 and is_present(row.get("assigned_to")):
        assignment_score = 0.5

    required_fields = targets.get("required_non_null_fields", [])
    notes_hits = sum(1 for field in required_fields if is_present(row.get(field)))
    notes_score = (notes_hits / len(required_fields)) if required_fields else 1.0

    consistency_score = _priority_consistency(row, targets)

    components = {
        "status": status_score,
        "assignment": assignment_score,
        "notes": notes_score,
        "priority_consistency": consistency_score,
    }
    total = weighted_component_score(task.grader_weights, components)

    violations: list[str] = []
    if status_score < 1.0:
        violations.append("target status not reached")
    if assignment_score < 1.0:
        violations.append("assignment group mismatch")
    if notes_score < 1.0:
        violations.append("required fields missing")
    if consistency_score < 1.0:
        violations.append("priority/impact/urgency mismatch")

    return {
        "score": total,
        "consistency": consistency_score,
        "components": components,
        "violations": violations,
    }
