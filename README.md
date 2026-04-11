---
title: itsm-openenv-benchmark
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8000
---

# ITSM OpenEnv Benchmark: Deterministic Enterprise Workflow Environment

[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Tasks](https://img.shields.io/badge/Benchmark%20Tasks-181-2E7D32)](tasks.jsonl)
[![Evaluation](https://img.shields.io/badge/Evaluation-Deterministic-5E35B1)](full_run.log)

This repository provides a fully runnable IT Service Management benchmark environment with deterministic grading and a reproducible 181-task evaluation protocol.

## Abstract

Reliable benchmarking for ITSM agents requires deterministic environment behavior, realistic enterprise workflows, and transparent grading. This project introduces an OpenEnv-style benchmark grounded in seeded operational data, spanning incident lifecycle management, SLA handling, problem management, and incident-knowledge linkage. The environment exposes a standard reset/step/state API, enforces typed interactions, and evaluates each step via deterministic graders. On the provided baseline run, the system achieves 100% task completion across 181 tasks with consistent low interaction cost (3.0 steps per episode on average), making this environment suitable for repeatable agent research and robust comparative experimentation.

## Motivation / Problem Statement

Most task-oriented agent benchmarks in enterprise settings are difficult to reproduce due to one or more of the following:

- hidden state transitions
- non-deterministic scoring
- unclear task manifests
- weak alignment between tasks and seeded backend data

This benchmark addresses those issues by coupling a canonical SQL seed with a fixed task manifest and deterministic graders, enabling controlled evaluation of planning, action validity, and objective completion in ITSM workflows.

## Methodology / Approach

The benchmark is built around four principles:

1. Data-grounded tasks: each objective maps to a concrete entity in the seeded SQL state.
2. Deterministic runtime: transitions and grader outputs are deterministic for a given state/action history.
3. Typed interaction protocol: action, observation, reward, and info objects are schema-defined.
4. Dense reward shaping: each step decomposes reward into validity, progress, consistency, and penalty signals.

High-level evaluation loop:

1. Reset environment to a selected task.
2. Emit one structured action at a time.
3. Apply deterministic transition and grade updated state.
4. Terminate on completion, step budget exhaustion, or invalid-action threshold.

## Benchmark At A Glance

| Item | Value |
|---|---|
| Domain | IT Service Management |
| Task count | 181 |
| Task families | incident, incident_sla, problem, incident_knowledge |
| API | reset, step, state (+ health) |
| Grading | deterministic, bounded in [0, 1] |
| Canonical SQL seed | itsm/dbs/db_1768479715490_ex6u7viv2.sql |
| Task manifest | tasks.jsonl |

Task-family composition:

| Task family | Count |
|---|---:|
| incident | 100 |
| incident_sla | 26 |
| problem | 10 |
| incident_knowledge | 45 |

## Project Structure

```text
.
├── server/
│   ├── app.py                        # FastAPI application and HTTP routes
│   ├── environment.py                # Environment entry wrapper
│   └── env/
│       ├── core.py                   # Deterministic ITSM environment logic
│       ├── loaders.py                # SQL/task loading and indexing
│       ├── models.py                 # Internal environment models
│       └── graders/                  # Family-specific deterministic graders
│           ├── incident.py
│           ├── sla.py
│           ├── problem.py
│           └── knowledge.py
├── models.py                         # Public typed API models (action/obs/reward/info)
├── client.py                         # OpenEnv-style client
├── inference.py                      # Baseline inference runner with START/STEP/END logs
├── tasks.jsonl                       # Canonical machine-readable benchmark tasks
├── full_run.log                      # Baseline full-benchmark run log
├── openenv.yaml                      # Benchmark metadata
├── scripts/generate_metrics_plot.py  # Reproducible metrics figure generator
├── assets/metrics.png                # Multi-panel benchmark dashboard
└── assets/metrics_line.png           # Line chart with markers
```

## Installation & Setup

### Option A: Local (UV)

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

Run server:

```bash
uv run uvicorn server.app:app --host 0.0.0.0 --port 8000
```

### Option B: Docker

```bash
docker build -t itsm-openenv -f server/Dockerfile .
docker run --rm -p 8000:8000 itsm-openenv
```

## Usage Examples

### 1) Run baseline inference (structured protocol logs)

```bash
export ENV_BASE_URL=http://localhost:8000
export API_BASE_URL=https://router.huggingface.co/v1
export MODEL_NAME=Qwen/Qwen2.5-7B-Instruct
export HF_TOKEN=<your_hf_token>

uv run python inference.py
```

Expected log format:

- [START] task=... env=... model=...
- [STEP] step=... action=... reward=... done=... error=...
- [END] success=... steps=... score=... rewards=...

### 2) Interact with API directly

```bash
curl -s http://localhost:8000/health
curl -s -X POST http://localhost:8000/reset -H "Content-Type: application/json" -d '{"task_id":"ITSM-001"}'
```

### 3) Reproduce the metrics figure

```bash
source .venv/bin/activate
uv pip install matplotlib
python scripts/generate_metrics_plot.py \
  --tasks tasks.jsonl \
  --log full_run.log \
  --out assets/metrics.png \
  --line-out assets/metrics_line.png \
  --summary-out assets/metrics_summary.json
```

## GRPO Notebook Workflow

The notebook itsm_grpo_torchforge.ipynb follows this execution pipeline:

1. Install dependencies for TRL, Transformers, PEFT, datasets, bitsandbytes, and TorchForge (with runtime-safe fallbacks).
2. Load configuration (space URL, model, train/eval limits, prompt/completion lengths, output paths).
3. Validate environment health and load canonical benchmark tasks.
4. Define prompt schema and strict JSON action normalization rules.
5. Build environment utility wrappers for reset/step and score normalization.
6. Construct environment-backed reward function combining format validity, action validity, and grader progress.
7. Build training dataset from task prompts and task IDs.
8. Load tokenizer/model with 4-bit quantization when available, otherwise use non-4bit fallback.
9. Attempt TorchForge optimization hooks, with safe fallback to native TRL path.
10. Configure GRPO + LoRA trainer and initialize training loop.
11. Train the policy, then save model/tokenizer artifacts.
12. Run quick one-step evaluation and report mean/median/min/max scores.

This is the exact notebook path used for the above process: itsm_grpo_torchforge.ipynb.

## Results / Performance Evaluation

All numbers below are computed from full_run.log and tasks.jsonl using scripts/generate_metrics_plot.py.

### Overall baseline

| Metric | Value |
|---|---:|
| Episodes | 181 |
| Success rate | 100.0% |
| Avg steps / episode | 3.000 |
| Avg return / episode | 1.467 |
| Avg terminal-step reward | 0.651 |
| Avg per-step reward | 0.489 |

### Family-level summary

| Task family | Count | Success (%) | Avg steps | Avg return | Avg terminal reward | Avg step-budget utilization |
|---|---:|---:|---:|---:|---:|---:|
| incident | 100 | 100.0 | 3.000 | 1.493 | 0.671 | 37.5% |
| incident_sla | 26 | 100.0 | 3.000 | 1.465 | 0.647 | 50.0% |
| problem | 10 | 100.0 | 3.000 | 1.474 | 0.649 | 37.5% |
| incident_knowledge | 45 | 100.0 | 3.000 | 1.410 | 0.610 | 60.0% |

### Visual metrics and plots

![ITSM Benchmark Metrics](assets/metrics.png)

Figure 1: Four-panel dashboard showing completion accuracy, reward efficiency, terminal-step quality, and interaction-cost profile by task family. The results indicate highly stable completion behavior and consistent reward attainment while consuming substantially less than full per-task step budgets.

![ITSM Benchmark Line Chart](assets/metrics_line.png)

Figure 2: Marker-based line visualization with two clean panels to avoid overlap: left panel shows reward trends (avg return, terminal reward, step reward), and right panel shows efficiency trends (success rate and step-budget utilization) across task families.

How to read these visuals:

1. Use Figure 1 for absolute comparisons at a glance (bar heights and exact labels).
2. Use Figure 2 for trend interpretation across families (connected marker trajectories).
3. Cross-check all plotted values with the numeric tables above and assets/metrics_summary.json.

## Experiments & Observations

1. Deterministic grading stability: repeated evaluations over fixed seed/task ordering produce consistent completion and reward statistics.
2. Interaction efficiency: all families complete in 3 steps on average despite family-specific maximum step budgets (5 to 8), indicating strong policy efficiency.
3. Family-specific reward profile: incident and problem tasks achieve the highest return/terminal reward, while incident_knowledge remains the most conservative family.
4. Evaluation suitability: dense reward decomposition plus deterministic transitions make this environment suitable for RL-style and planning-style policy comparison.

## Environment Quality Showcase

### Software/runtime profile

| Category | Specification |
|---|---|
| Python | 3.11+ |
| Reference hardware (optional training notebook) | NVIDIA GeForce RTX 3050 6GB Laptop GPU (CUDA path observed) |
| API framework | FastAPI |
| Packaging | UV + pyproject |
| Containerization | Docker |
| Evaluation protocol | deterministic START/STEP/END logs |
| Optional training notebook | GRPO + QLoRA path (4-bit capable) |

### Efficiency comparison against step budget ceilings

| Task family | Max steps (manifest) | Avg used steps | Unused budget |
|---|---:|---:|---:|
| incident | 8 | 3.0 | 62.5% |
| incident_sla | 6 | 3.0 | 50.0% |
| problem | 8 | 3.0 | 62.5% |
| incident_knowledge | 5 | 3.0 | 40.0% |

Interpretation: the baseline policy consistently reaches completion far below episode ceilings, demonstrating a favorable balance between correctness and action efficiency.

## Reproducibility

To reproduce the reported numbers end-to-end:

1. Use the canonical SQL seed and tasks manifest in this repository.
2. Run the server in local or Docker mode.
3. Execute inference.py to regenerate full_run.log.
4. Run scripts/generate_metrics_plot.py to regenerate assets/metrics.png, assets/metrics_line.png, and assets/metrics_summary.json.

For strict reproducibility across runs:

- keep task ordering deterministic (no custom random shuffling)
- avoid changing grader logic between runs
- keep manifest/seed versions fixed

## Future Work

- Add explicit difficulty labels to tasks.jsonl for direct difficulty-stratified plotting.
- Add CI regression checks that diff metrics_summary.json against pinned tolerances.
- Extend benchmark families (change management, request fulfillment, CMDB updates).
- Provide standardized leaderboards across model classes (heuristic, SFT, RL fine-tuned).

## References / Citations

- OpenEnv-style interaction pattern (reset/step/state) as adopted in benchmarked environment APIs.
- FastAPI documentation: https://fastapi.tiangolo.com/
- Qwen model family (for baseline runner and optional notebook experiments): https://huggingface.co/Qwen