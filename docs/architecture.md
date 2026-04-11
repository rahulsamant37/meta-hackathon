# Architecture

## Overview

The repository follows a layered architecture:

1. API layer: FastAPI app exposing `reset`, `step`, `state`, and health endpoints.
2. Environment runtime: deterministic transition logic and reward shaping.
3. Grading layer: family-specific deterministic graders with typed outputs.
4. Data layer: canonical SQL seed and task manifest.
5. Evaluation layer: inference and metrics scripts.

## Canonical Module Layout

- `itsm_openenv_benchmark/models.py`: typed contracts used by both server and client.
- `itsm_openenv_benchmark/client.py`: OpenEnv client wrapper.
- `itsm_openenv_benchmark/environment.py`: canonical environment export.
- `itsm_openenv_benchmark/env/core.py`: environment transitions and reward logic.
- `itsm_openenv_benchmark/env/loaders.py`: task and SQL loading.
- `itsm_openenv_benchmark/env/graders/*`: deterministic family graders.

## Compatibility Strategy

The repository keeps root-level and `server/env` compatibility wrappers so existing
OpenEnv deployment and import paths continue to work:

- root `models.py`, `client.py`, and `__init__.py`
- `server/environment.py`
- `server/env/*`

These wrappers re-export from `itsm_openenv_benchmark` and should not host new logic.

## Determinism Notes

- Task order is stable by task ID.
- Grading depends only on task definition, current state, and action history.
