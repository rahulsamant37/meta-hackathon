from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - fallback for minimal runtime images
    OpenAI = None  # type: ignore[assignment]

API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct")
HF_TOKEN = os.getenv("HF_TOKEN")

def normalize_env_base_url(url: str) -> str:
    normalized = url.rstrip("/")
    match = re.match(r"^https?://huggingface\.co/spaces/([^/]+)/([^/]+)$", normalized)
    if match:
        username, space = match.groups()
        return f"https://{username}-{space}.hf.space"
    return normalized


ENV_BASE_URL = normalize_env_base_url(
    os.getenv("ENV_BASE_URL", "https://rahulsamant37-itsm-openenv-benchmark.hf.space")
)
TASKS_JSONL_PATH = os.getenv("TASKS_JSONL_PATH", "tasks.jsonl")
# r_t = 0.20 * validity + 0.45 * progress + 0.20 * consistency - 0.15 * penalty + terminal+bonus
MAX_TASKS = int(os.getenv("MAX_TASKS", "181"))
MAX_STEPS_PER_TASK = int(os.getenv("MAX_STEPS_PER_TASK", "8"))


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def clamp01_open(value: float, epsilon: float = 1e-3) -> float:
    bounded = clamp01(value)
    return min(1.0 - epsilon, max(epsilon, bounded))


def log_start(task_name: str, env_name: str, model_name: str) -> None:
    print(f"[START] task={task_name} env={env_name} model={model_name}", flush=True)


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


def load_task_ids(path: str, max_tasks: int) -> list[str]:
    task_ids: list[str] = []
    with open(path, "r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            item = json.loads(line)
            task_ids.append(str(item["task_id"]))
            if len(task_ids) >= max_tasks:
                break
    return task_ids


def llm_reasoning(client: Any, task_id: str, objective: str) -> str | None:
    if client is None:
        return None

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": "You are an ITSM operations assistant. Give one short operational tip.",
                },
                {
                    "role": "user",
                    "content": f"Task {task_id}: {objective}. Provide one short next-step hint.",
                },
            ],
            temperature=0.0,
            max_tokens=32,
        )
        text = response.choices[0].message.content or ""
        text = " ".join(text.split())
        return text[:120] if text else None
    except Exception:
        return None


def choose_action(observation: dict[str, Any], step_index: int, hint: str | None) -> dict[str, Any]:
    task_type = observation.get("task_type")
    snapshot = observation.get("ticket_snapshot", {}) or {}
    signals = observation.get("progress_signals", {}) or {}
    targets = signals.get("targets_hint", {}) or {}

    reasoning = hint

    if step_index == 1:
        return {
            "action_type": "query",
            "target_id": observation.get("task_id"),
            "payload": {"note": "initial state inspection"},
            "reasoning": reasoning,
        }

    if task_type == "incident":
        target_status = targets.get("target_status", "resolved")
        assignment_group = targets.get("assignment_group") or snapshot.get("assignment_group")

        if not snapshot.get("worknotes"):
            return {
                "action_type": "add_worknote",
                "payload": {"text": "Investigated incident and updated troubleshooting notes."},
                "reasoning": reasoning,
            }

        if not snapshot.get("assigned_to") or not snapshot.get("assignment_group"):
            return {
                "action_type": "set_assignment",
                "payload": {"assigned_to": snapshot.get("assigned_to") or "AGENT_AUTO", "assignment_group": assignment_group},
                "reasoning": reasoning,
            }

        if target_status == "closed" and snapshot.get("status") != "closed":
            return {
                "action_type": "close",
                "payload": {"close_notes": "Ticket closed after validation of resolution state."},
                "reasoning": reasoning,
            }

        if target_status == "resolved" and snapshot.get("status") not in {"resolved", "closed"}:
            return {
                "action_type": "resolve",
                "payload": {"resolution_notes": "Root cause addressed and service restored."},
                "reasoning": reasoning,
            }

        if snapshot.get("status") != target_status:
            return {
                "action_type": "update_incident",
                "payload": {"status": target_status},
                "reasoning": reasoning,
            }

        return {"action_type": "noop", "payload": {}, "reasoning": reasoning}

    if task_type == "incident_sla":
        target_stage = targets.get("target_stage")
        expected_breached = bool(targets.get("has_breached"))

        payload: dict[str, Any] = {}
        if target_stage and snapshot.get("stage") != target_stage:
            payload["stage"] = target_stage
        if snapshot.get("has_breached") != expected_breached:
            payload["has_breached"] = expected_breached

        if payload:
            return {"action_type": "update_sla", "payload": payload, "reasoning": reasoning}

        return {"action_type": "noop", "payload": {}, "reasoning": reasoning}

    if task_type == "problem":
        target_status = targets.get("target_status", "fix_in_progress")

        if not snapshot.get("worknotes"):
            return {
                "action_type": "add_worknote",
                "payload": {"text": "Problem investigation updated with current findings."},
                "reasoning": reasoning,
            }

        if target_status in {"root_cause", "fix_in_progress", "resolved", "closed"} and not snapshot.get("workaround"):
            return {
                "action_type": "update_problem",
                "payload": {"workaround": "Temporary mitigation applied while permanent fix is prepared."},
                "reasoning": reasoning,
            }

        if target_status in {"fix_in_progress", "resolved", "closed"} and not snapshot.get("fix_notes"):
            return {
                "action_type": "update_problem",
                "payload": {"fix_notes": "Permanent fix prepared and validated in staging."},
                "reasoning": reasoning,
            }

        if snapshot.get("status") != target_status:
            return {
                "action_type": "update_problem",
                "payload": {"status": target_status},
                "reasoning": reasoning,
            }

        return {"action_type": "noop", "payload": {}, "reasoning": reasoning}

    if task_type == "incident_knowledge":
        payload: dict[str, Any] = {}
        if targets.get("knowledge_id") and snapshot.get("knowledge_id") != targets.get("knowledge_id"):
            payload["knowledge_id"] = targets.get("knowledge_id")
        if targets.get("target_used_as") and snapshot.get("used_as") != targets.get("target_used_as"):
            payload["used_as"] = targets.get("target_used_as")
        if targets.get("incident_id") and snapshot.get("incident_id") != targets.get("incident_id"):
            payload["incident_id"] = targets.get("incident_id")

        if payload:
            return {"action_type": "attach_knowledge", "payload": payload, "reasoning": reasoning}

        return {"action_type": "noop", "payload": {}, "reasoning": reasoning}

    return {"action_type": "noop", "payload": {}, "reasoning": reasoning}


def run_episode(session: requests.Session, client: Any, task_id: str) -> None:
    rewards: list[float] = []
    steps_taken = 0
    success = False
    score = 0.0

    log_start(task_name=task_id, env_name="itsm-openenv", model_name=MODEL_NAME)

    try:
        reset_resp = session.post(f"{ENV_BASE_URL}/reset", json={"task_id": task_id}, timeout=20)
        reset_resp.raise_for_status()
        observation = reset_resp.json()

        objective = str(observation.get("progress_signals", {}).get("objective", ""))
        hint = llm_reasoning(client, task_id, objective)

        max_steps = int(observation.get("max_steps", MAX_STEPS_PER_TASK))

        for step in range(1, max_steps + 1):
            action = choose_action(observation, step, hint)
            action_str = json.dumps(action, separators=(",", ":"), ensure_ascii=False)

            try:
                step_resp = session.post(f"{ENV_BASE_URL}/step", json=action, timeout=20)
                step_resp.raise_for_status()
                result = step_resp.json()
            except Exception as exc:
                steps_taken = step
                log_step(step=step, action=action_str, reward=0.0, done=True, error=str(exc))
                break

            reward_payload = result.get("reward", 0.0)
            if isinstance(reward_payload, dict):
                reward = float(reward_payload.get("total", 0.0))
            else:
                reward = float(reward_payload)
            done = bool(result.get("done", False))
            info = result.get("info", {}) or {}
            obs = result.get("observation", {}) or {}

            try:
                score = clamp01_open(float(info.get("grader_score", score)))
            except (TypeError, ValueError):
                score = clamp01_open(score)

            steps_taken = step
            rewards.append(reward)
            error = obs.get("last_action_error")
            log_step(step=step, action=action_str, reward=reward, done=done, error=error)

            observation = obs
            if done:
                success = bool(info.get("task_complete", False))
                break

    finally:
        log_end(success=success, steps=steps_taken, score=score, rewards=rewards)


def main() -> None:
    task_ids = load_task_ids(TASKS_JSONL_PATH, MAX_TASKS)

    client = None
    if OpenAI is not None and HF_TOKEN:
        client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)

    session = requests.Session()
    for task_id in task_ids:
        run_episode(session, client, task_id)


if __name__ == "__main__":
    main()
