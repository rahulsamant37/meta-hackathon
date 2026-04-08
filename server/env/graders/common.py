from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence


SCORE_EPSILON = 1e-6


INCIDENT_STATUS_PROGRESS = {
    "new": 0.15,
    "in_progress": 0.45,
    "on_hold": 0.4,
    "resolved": 0.85,
    "closed": 1.0,
}

PROBLEM_STAGE_PROGRESS = {
    "new": 0.1,
    "assess": 0.25,
    "root_cause": 0.5,
    "fix_in_progress": 0.75,
    "resolved": 0.9,
    "closed": 1.0,
}

SLA_STAGE_PROGRESS = {
    "in_progress": 0.4,
    "paused": 0.6,
    "completed": 1.0,
    "breached": 1.0,
}


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def clamp01_open(value: float, epsilon: float = SCORE_EPSILON) -> float:
    bounded = clamp01(value)
    return min(1.0 - epsilon, max(epsilon, bounded))


def is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def parse_iso_ts(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None

    cleaned = raw.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def progress_ratio(
    current: str | None,
    target: str | None,
    mapping: Mapping[str, float],
    target_default: float = 1.0,
) -> float:
    if current is None or target is None:
        return 0.0

    current_rank = mapping.get(current, 0.0)
    target_rank = mapping.get(target, target_default)
    if target_rank <= 0.0:
        return 0.0
    return clamp01(current_rank / target_rank)


def average_or_default(values: Sequence[float], default: float = 1.0) -> float:
    if not values:
        return default
    return sum(values) / len(values)


def field_match_score(
    row: Mapping[str, Any],
    targets: Mapping[str, Any],
    fields: Sequence[str],
    default: float = 1.0,
) -> float:
    checks: list[float] = []
    for field in fields:
        expected = targets.get(field)
        if expected is None:
            continue
        checks.append(1.0 if row.get(field) == expected else 0.0)
    return average_or_default(checks, default)


def weighted_component_score(weights: Mapping[str, float], components: Mapping[str, float]) -> float:
    total = 0.0
    for key, value in components.items():
        total += float(weights.get(key, 0.0)) * value
    return clamp01(total)


def logical_stage_progress(stage: str | None) -> float:
    if stage is None:
        return 0.0
    return PROBLEM_STAGE_PROGRESS.get(stage, 0.0)
