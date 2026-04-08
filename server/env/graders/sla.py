from __future__ import annotations

from typing import Any

from ..models import TaskDefinition
from .common import SLA_STAGE_PROGRESS, average_or_default, parse_iso_ts, progress_ratio, weighted_component_score


def _stage_score(current: str | None, target: str | None) -> float:
    if current == target:
        return 1.0
    return progress_ratio(current, target, SLA_STAGE_PROGRESS)


def _timestamp_consistency(row: dict[str, Any]) -> float:
    start = parse_iso_ts(row.get("start_time"))
    breach = parse_iso_ts(row.get("breach_time"))
    completed = parse_iso_ts(row.get("completed_time"))

    checks: list[float] = []
    if start is not None and breach is not None:
        checks.append(1.0 if start <= breach else 0.0)
    if start is not None and completed is not None:
        checks.append(1.0 if start <= completed else 0.0)

    return average_or_default(checks, default=1.0)


def _breach_semantics(row: dict[str, Any], targets: dict[str, Any]) -> float:
    expected = bool(targets.get("has_breached"))
    actual = bool(row.get("has_breached"))
    stage = row.get("stage")

    if actual != expected:
        return 0.0

    if expected and stage == "completed":
        return 0.5
    return 1.0


def grade_sla(
    task: TaskDefinition,
    db_index: dict[str, dict[str, dict[str, Any]]],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    targets = task.grader_targets
    sla_id = str(targets["incident_sla_id"])
    row = db_index["incident_sla"].get(sla_id)

    if row is None:
        return {
            "score": 0.0,
            "consistency": 0.0,
            "components": {"stage": 0.0, "breach_semantics": 0.0, "timestamps": 0.0},
            "violations": [f"incident_sla row not found: {sla_id}"],
        }

    stage_score = _stage_score(row.get("stage"), targets.get("target_stage"))
    breach_score = _breach_semantics(row, targets)
    timestamp_score = _timestamp_consistency(row)

    components = {
        "stage": stage_score,
        "breach_semantics": breach_score,
        "timestamps": timestamp_score,
    }
    total = weighted_component_score(task.grader_weights, components)

    violations: list[str] = []
    if stage_score < 1.0:
        violations.append("target SLA stage not matched")
    if breach_score < 1.0:
        violations.append("breach semantics mismatch")
    if timestamp_score < 1.0:
        violations.append("timestamp ordering invalid")

    return {
        "score": total,
        "consistency": timestamp_score,
        "components": components,
        "violations": violations,
    }
