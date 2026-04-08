from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

TaskType = Literal["incident", "incident_sla", "problem", "incident_knowledge"]
ActionStatus = Literal["ok", "invalid", "blocked"]

ActionType = Literal[
	"query",
	"update_incident",
	"update_problem",
	"update_sla",
	"attach_knowledge",
	"add_worknote",
	"set_assignment",
	"resolve",
	"close",
	"noop",
]


class ITSMAction(BaseModel):
	action_type: ActionType
	target_id: str | None = None
	payload: dict[str, Any] = Field(default_factory=dict)
	reasoning: str | None = None


class ITSMReward(BaseModel):
	total: float
	components: dict[str, float] = Field(default_factory=dict)
	normalized_progress: float


class ITSMInfo(BaseModel):
	task_complete: bool
	grader_score: float
	violations: list[str] = Field(default_factory=list)
	state_delta: dict[str, Any] = Field(default_factory=dict)


class ITSMObservation(BaseModel):
	task_id: str
	task_type: TaskType
	step_index: int
	max_steps: int
	ticket_snapshot: dict[str, Any] = Field(default_factory=dict)
	related_entities: dict[str, Any] = Field(default_factory=dict)
	allowed_actions: list[str] = Field(default_factory=list)
	last_action_status: ActionStatus | None = None
	last_action_error: str | None = None
	progress_signals: dict[str, Any] = Field(default_factory=dict)


class ITSMStepResult(BaseModel):
	observation: ITSMObservation
	reward: ITSMReward
	done: bool
	info: ITSMInfo


class TaskDefinition(BaseModel):
	task_id: str
	source_table: TaskType
	source_id: str
	objective: str
	max_steps: int
	success_criteria: list[str]
	failure_criteria: list[str]
	grader_targets: dict[str, Any]
	grader_weights: dict[str, float]
	allowed_action_types: list[str]


class EnvState(BaseModel):
	active_task_id: str | None = None
	task_cursor: int = 0
	step_index: int = 0
	done: bool = False
	invalid_action_count: int = 0
	cumulative_reward: float = 0.0
	grader_score: float = 0.0
	action_history: list[dict[str, Any]] = Field(default_factory=list)
	violations: list[str] = Field(default_factory=list)


__all__ = [
	"ActionStatus",
	"ActionType",
	"EnvState",
	"ITSMAction",
	"ITSMInfo",
	"ITSMObservation",
	"ITSMReward",
	"ITSMStepResult",
	"TaskDefinition",
	"TaskType",
]
