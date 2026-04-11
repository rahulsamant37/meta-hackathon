"""Single-episode ITSM sample inference script.

This script is intentionally simple and deterministic. It demonstrates the
HTTP protocol and required log format for one task.
"""

from __future__ import annotations

import json
import os
from typing import Any

import requests


ENV_BASE_URL = os.getenv("ENV_BASE_URL", "http://localhost:8000").rstrip("/")
TASK_ID = os.getenv("TASK_ID", "ITSM-001")


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def clamp01_open(value: float, epsilon: float = 1e-3) -> float:
    bounded = clamp01(value)
    return min(1.0 - epsilon, max(epsilon, bounded))


def log_start(task_name: str) -> None:
    print(f"[START] task={task_name} env=itsm-openenv model=heuristic", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: str | None) -> None:
    err = error if error else "null"
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f} done={str(done).lower()} error={err}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: list[float]) -> None:
    rewards_text = ",".join(f"{value:.2f}" for value in rewards)
    strict_score = clamp01_open(score)
    print(
        f"[END] success={str(success).lower()} steps={steps} score={strict_score:.3f} rewards={rewards_text}",
        flush=True,
    )


def choose_action(observation: dict[str, Any], step_index: int) -> dict[str, Any]:
    task_type = observation.get("task_type")
    snapshot = observation.get("ticket_snapshot", {}) or {}
    targets = observation.get("progress_signals", {}).get("targets_hint", {}) or {}

    if step_index == 1:
        return {
            "action_type": "query",
            "target_id": observation.get("task_id"),
            "payload": {"note": "inspect current state"},
        }

    if task_type == "incident_sla":
        return {
            "action_type": "update_sla",
            "payload": {
                "stage": targets.get("target_stage"),
                "has_breached": bool(targets.get("has_breached")),
            },
        }

    if task_type == "problem":
        if not snapshot.get("worknotes"):
            return {
                "action_type": "add_worknote",
                "payload": {"text": "Sample workflow note for reproducible run."},
            }
        return {
            "action_type": "update_problem",
            "payload": {"status": targets.get("target_status", "fix_in_progress")},
        }

    if task_type == "incident_knowledge":
        return {
            "action_type": "attach_knowledge",
            "payload": {
                "incident_id": targets.get("incident_id"),
                "knowledge_id": targets.get("knowledge_id"),
                "used_as": targets.get("target_used_as"),
            },
        }

    target_status = targets.get("target_status", "resolved")
    if target_status == "closed":
        return {
            "action_type": "close",
            "payload": {"close_notes": "Closed via sample heuristic."},
        }

    return {
        "action_type": "resolve",
        "payload": {"resolution_notes": "Resolved via sample heuristic."},
    }


def main() -> None:
    session = requests.Session()

    log_start(TASK_ID)
    rewards: list[float] = []
    steps_taken = 0
    success = False
    score = 0.0

    reset_response = session.post(f"{ENV_BASE_URL}/reset", json={"task_id": TASK_ID}, timeout=20)
    reset_response.raise_for_status()
    observation = reset_response.json()

    max_steps = int(observation.get("max_steps", 8))

    for step in range(1, max_steps + 1):
        action = choose_action(observation, step)
        action_str = json.dumps(action, separators=(",", ":"), ensure_ascii=False)

        step_response = session.post(f"{ENV_BASE_URL}/step", json=action, timeout=20)
        step_response.raise_for_status()
        result = step_response.json()

        reward_payload = result.get("reward", 0.0)
        reward = float(reward_payload.get("total", 0.0)) if isinstance(reward_payload, dict) else float(reward_payload)
        done = bool(result.get("done", False))
        obs = result.get("observation", {}) or {}

        rewards.append(reward)
        steps_taken = step
        log_step(step=step, action=action_str, reward=reward, done=done, error=obs.get("last_action_error"))

        info = result.get("info", {}) or {}
        try:
            score = clamp01_open(float(info.get("grader_score", score)))
        except (TypeError, ValueError):
            score = clamp01_open(score)

        observation = obs
        if done:
            success = bool(info.get("task_complete", False))
            break

    log_end(success=success, steps=steps_taken, score=score, rewards=rewards)


if __name__ == "__main__":
    main()