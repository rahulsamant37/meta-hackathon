---
title: itsm-openenv-benchmark
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8000
---

# ITSM OpenEnv Benchmark (181 Tasks)

This repository now contains a complete, runnable OpenEnv-style ITSM benchmark environment built for the hackathon constraints:

- Real-world domain: IT service management workflows
- Deterministic task set: 181 objectives
- Deterministic graders: score range [0.0, 1.0]
- Dense reward shaping in each step
- Standard API surface: reset, step, state
- Baseline inference runner with required START/STEP/END logs

## Dataset Alignment

Task source is aligned to the canonical SQL seed and manifest artifacts in this repository:

- Canonical seed: itsm/dbs/db_1768479715490_ex6u7viv2.sql
- Runtime task manifest: tasks.jsonl
- Human-readable mirror: task.md

Task composition:

- 100 incident tasks
- 26 incident_sla tasks
- 10 problem tasks
- 45 incident_knowledge tasks
- Total: 181

## Project Layout

- models.py: typed action/observation/reward/info/state models
- client.py: OpenEnv client implementation
- server/environment.py: environment runtime (reset/step/state)
- server/app.py: FastAPI API layer
- server/Dockerfile: container definition
- server/env/loaders.py: deterministic tasks + SQL seed loaders
- server/env/graders/: deterministic graders by task family
- openenv.yaml: benchmark metadata
- inference.py: baseline runner with structured logs
- tasks.jsonl: canonical machine-readable task manifest

## Quick Start (UV)

1. Install dependencies

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

2. Start the environment server

```bash
uv run uvicorn server.app:app --host 0.0.0.0 --port 8000
```

3. In another terminal, run baseline inference

```bash
export ENV_BASE_URL=http://localhost:8000
export API_BASE_URL=https://router.huggingface.co/v1
export MODEL_NAME=Qwen/Qwen2.5-7B-Instruct
export HF_TOKEN=<your_hf_token>

uv run python inference.py
```

The script emits only these line formats:

- [START] task=... env=... model=...
- [STEP] step=... action=... reward=... done=... error=...
- [END] success=... steps=... rewards=...

## Action Space

The environment accepts a typed action envelope:

- action_type: one of query, update_incident, update_problem, update_sla, attach_knowledge, add_worknote, set_assignment, resolve, close, noop
- target_id: optional entity id override for actions that support direct targeting
- payload: action-specific key/value fields
- reasoning: optional rationale string

The allowed action types are constrained per task by tasks.jsonl (allowed_action_types).

## Observation Space

Each reset and step response includes a typed observation object with:

- task_id, task_type, difficulty
- step_index, max_steps
- ticket_snapshot: active row state for the task objective
- related_entities: linked SLA/problem/knowledge records
- allowed_actions: task-scoped action list
- last_action_status, last_action_error
- progress_signals: objective, grader targets hint, normalized progress, invalid-action count, and reward/progress components

Step responses include:

- reward.total: per-step dense reward value in [-1.0, 1.0]
- reward.components: validity/progress/consistency/penalty/terminal_bonus components
- reward.normalized_progress: task progress normalized to [0.0, 1.0]
- done + info.task_complete/info.grader_score/info.violations/info.state_delta

## Task Descriptions and Expected Difficulty

Task difficulty is objective-level and encoded per row in tasks.jsonl.

- incident (100 tasks): lifecycle, assignment, note quality, and priority/impact/urgency consistency. Contains easy, medium, and hard objectives.
- incident_sla (26 tasks): stage progression, breach handling, and timestamp consistency. Includes easy, medium, and hard objectives.
- problem (10 tasks): root-cause workflow progression, service/CI linkage, and fix completeness. Mostly medium/hard objectives.
- incident_knowledge (45 tasks): article linkage and usage-mode alignment for ticket context. Mostly easy/medium objectives.

Deterministic difficulty rubric:

- easy: straightforward single-entity completion objective
- medium: multi-field consistency or cross-entity linkage objective
- hard: breach semantics, critical outage/security handling, or coordinated multi-entity workflow objective

## Baseline Scores

The baseline run in full_run.log covers all 181 tasks and is reproducible with the inference command above.

Overall summary:

- tasks: 181
- success rate: 181/181 (100.0%)
- average steps per task: 3.0000
- average per-step reward: 0.4892
- step reward range: [0.40, 0.77]

Per-task-type summary (from full_run.log + tasks.jsonl):

| task type | count | success rate | avg steps | avg return per task | avg terminal step reward |
|---|---:|---:|---:|---:|---:|
| incident | 100 | 100.0% | 3.0000 | 1.4932 | 0.6712 |
| incident_sla | 26 | 100.0% | 3.0000 | 1.4654 | 0.6469 |
| problem | 10 | 100.0% | 3.0000 | 1.4740 | 0.6490 |
| incident_knowledge | 45 | 100.0% | 3.0000 | 1.4100 | 0.6100 |

Per-difficulty summary:

| difficulty | count | success rate | avg steps | avg return per task | avg terminal step reward |
|---|---:|---:|---:|---:|---:|
| easy | 63 | 100.0% | 3.0000 | 1.4381 | 0.6354 |
| medium | 103 | 100.0% | 3.0000 | 1.4827 | 0.6600 |
| hard | 15 | 100.0% | 3.0000 | 1.4860 | 0.6580 |

## API Endpoints

- GET /health
- POST /reset with optional JSON payload {"task_id": "ITSM-001"}
- POST /step with ITSMAction payload
- GET /state

## Docker

Build and run:

```bash
docker build -t itsm-openenv -f server/Dockerfile .
docker run --rm -p 8000:8000 itsm-openenv
```

## Notes on Determinism

- Task order is stable when no task_id is passed to reset()
- Task-level graders are deterministic over current state + action history
- Scores are always clamped to [0.0, 1.0]