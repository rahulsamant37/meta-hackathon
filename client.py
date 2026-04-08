"""OpenEnv client for the ITSM benchmark environment."""

from typing import Any, Dict

from openenv.core import EnvClient
from openenv.core.client_types import StepResult

try:
    from .models import EnvState, ITSMAction, ITSMObservation
except ModuleNotFoundError:
    from models import EnvState, ITSMAction, ITSMObservation


class ITSMEnv(EnvClient[ITSMAction, ITSMObservation, EnvState]):
    """Client wrapper for reset/step/state interactions."""

    def _step_payload(self, action: ITSMAction) -> Dict[str, Any]:
        return action.model_dump()

    def _parse_result(self, payload: Dict[str, Any]) -> StepResult[ITSMObservation]:
        obs_data = payload.get("observation", {})
        observation = ITSMObservation(**obs_data)
        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: Dict[str, Any]) -> EnvState:
        return EnvState(**payload)
