from __future__ import annotations

from typing import Any

from ...models import TaskDefinition
from .common import average_or_default, weighted_component_score


def grade_knowledge(
    task: TaskDefinition,
    db_index: dict[str, dict[str, dict[str, Any]]],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    del history

    targets = task.grader_targets
    link_id = str(targets["incident_kb_id"])
    row = db_index["incident_knowledge"].get(link_id)

    if row is None:
        return {
            "score": 0.0,
            "consistency": 0.0,
            "components": {"knowledge_match": 0.0, "usage_mode": 0.0, "context_alignment": 0.0},
            "violations": [f"incident_knowledge row not found: {link_id}"],
        }

    knowledge_score = 1.0 if row.get("knowledge_id") == targets.get("knowledge_id") else 0.0
    usage_score = 1.0 if row.get("used_as") == targets.get("target_used_as") else 0.0

    context_checks = [
        1.0 if row.get("incident_id") == targets.get("incident_id") else 0.0,
        1.0 if row.get("org_id") == targets.get("org_id") else 0.0,
    ]
    context_score = average_or_default(context_checks, default=1.0)

    components = {
        "knowledge_match": knowledge_score,
        "usage_mode": usage_score,
        "context_alignment": context_score,
    }
    total = weighted_component_score(task.grader_weights, components)

    violations: list[str] = []
    if knowledge_score < 1.0:
        violations.append("knowledge article mismatch")
    if usage_score < 1.0:
        violations.append("knowledge usage mode mismatch")
    if context_score < 1.0:
        violations.append("knowledge link incident/org mismatch")

    return {
        "score": total,
        "consistency": context_score,
        "components": components,
        "violations": violations,
    }
