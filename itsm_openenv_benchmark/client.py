"""OpenEnv client for the ITSM benchmark environment."""

from __future__ import annotations

from typing import Any

from openenv.core import EnvClient
from openenv.core.client_types import StepResult

from .models import EnvState, ITSMAction, ITSMObservation


class ITSMEnv(EnvClient[ITSMAction, ITSMObservation, EnvState]):
    """Client wrapper for reset/step/state interactions."""

    def _step_payload(self, action: ITSMAction) -> dict[str, Any]:
        return action.model_dump()

    def _parse_result(self, payload: dict[str, Any]) -> StepResult[ITSMObservation]:
        obs_data = payload.get("observation", {})
        observation = ITSMObservation(**obs_data)
        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: dict[str, Any]) -> EnvState:
        return EnvState(**payload)
