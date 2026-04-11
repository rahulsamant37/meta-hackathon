"""Minimal programmatic example for running a single task episode.

Usage:
    python examples/run_single_task.py
"""

from __future__ import annotations

import json
import os

import requests


def main() -> None:
    base_url = os.getenv("ENV_BASE_URL", "http://localhost:8000").rstrip("/")
    task_id = os.getenv("TASK_ID", "ITSM-001")

    with requests.Session() as session:
        observation = session.post(f"{base_url}/reset", json={"task_id": task_id}, timeout=20).json()
        print("Reset:", observation.get("task_id"), observation.get("task_type"))

        action = {
            "action_type": "query",
            "target_id": task_id,
            "payload": {"note": "example probe"},
            "reasoning": "Inspect state before taking a targeted action.",
        }
        result = session.post(f"{base_url}/step", json=action, timeout=20).json()
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
