from __future__ import annotations

from typing import Any

from ..models import TaskDefinition
from .common import clamp01_open
from .incident import grade_incident
from .knowledge import grade_knowledge
from .problem import grade_problem
from .sla import grade_sla


def _normalize_result(result: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(result)
    normalized["score"] = clamp01_open(float(normalized.get("score", 0.0)))
    return normalized


def _has_meaningful_action(history: list[dict[str, Any]]) -> bool:
    for step in history:
        if not step.get("valid", False):
            continue

        action = step.get("action", {}) or {}
        action_type = action.get("action_type")
        if action_type in {"query", "noop"}:
            continue

        state_delta = step.get("state_delta", {}) or {}
        if state_delta:
            return True

    return False


def _apply_interaction_gate(result: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    if _has_meaningful_action(history):
        result.setdefault("components", {})
        result["components"]["interaction"] = 1.0
        return _normalize_result(result)

    gated = dict(result)
    gated["score"] = min(float(gated.get("score", 0.0)), 0.90)

    components = dict(gated.get("components", {}))
    components["interaction"] = 0.0
    gated["components"] = components

    violations = list(gated.get("violations", []))
    violations.append("no meaningful state-changing action yet")
    gated["violations"] = violations
    return _normalize_result(gated)


def grade_task(
    task: TaskDefinition,
    db_index: dict[str, dict[str, dict[str, Any]]],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    if task.source_table == "incident":
        return _normalize_result(_apply_interaction_gate(grade_incident(task, db_index, history), history))
    if task.source_table == "incident_sla":
        return _normalize_result(_apply_interaction_gate(grade_sla(task, db_index, history), history))
    if task.source_table == "problem":
        return _normalize_result(_apply_interaction_gate(grade_problem(task, db_index, history), history))
    if task.source_table == "incident_knowledge":
        return _normalize_result(_apply_interaction_gate(grade_knowledge(task, db_index, history), history))

    return _normalize_result({
        "score": 0.0,
        "consistency": 0.0,
        "components": {},
        "violations": [f"unsupported task source_table: {task.source_table}"],
    })
