from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from .graders import grade_task
from .loaders import DEFAULT_SQL_PATH, DEFAULT_TASKS_PATH, build_entity_index, clone_index, load_sql_tables, load_tasks
from .models import EnvState, ITSMAction, ITSMInfo, ITSMObservation, ITSMReward, ITSMStepResult, TaskDefinition


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ITSMEnvironment:
    """Deterministic ITSM benchmark runtime backed by SQL seed data + tasks.jsonl."""

    def __init__(self, tasks_path=DEFAULT_TASKS_PATH, sql_path=DEFAULT_SQL_PATH) -> None:
        self.tasks: list[TaskDefinition] = load_tasks(tasks_path)
        self.tasks_by_id: dict[str, TaskDefinition] = {task.task_id: task for task in self.tasks}

        table_rows = load_sql_tables(sql_path)
        self.base_index = build_entity_index(table_rows)

        self.db_index = clone_index(self.base_index)
        self.state_data = EnvState()

        self.active_task: TaskDefinition | None = None
        self._last_action_status: str | None = None
        self._last_action_error: str | None = None
        self._last_state_delta: dict[str, Any] = {}
        self._last_components: dict[str, float] = {}

        self._previous_action_signature: str | None = None
        self._noop_streak: int = 0

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def reset(self, task_id: str | None = None) -> ITSMObservation:
        if task_id is None:
            task = self.tasks[self.state_data.task_cursor % len(self.tasks)]
            self.state_data.task_cursor += 1
        else:
            task = self.tasks_by_id.get(task_id)
            if task is None:
                raise ValueError(f"Unknown task_id: {task_id}")

        self.active_task = task
        self.db_index = clone_index(self.base_index)

        self.state_data.active_task_id = task.task_id
        self.state_data.step_index = 0
        self.state_data.done = False
        self.state_data.invalid_action_count = 0
        self.state_data.cumulative_reward = 0.0
        self.state_data.grader_score = 0.0
        self.state_data.action_history = []
        self.state_data.violations = []

        self._last_action_status = None
        self._last_action_error = None
        self._last_state_delta = {}
        self._last_components = {}
        self._previous_action_signature = None
        self._noop_streak = 0

        grading = grade_task(task, self.db_index, self.state_data.action_history)
        self.state_data.grader_score = float(grading.get("score", 0.0))
        self._last_components = dict(grading.get("components", {}))

        return self._build_observation()

    def step(self, action: ITSMAction) -> ITSMStepResult:
        if self.active_task is None:
            raise RuntimeError("Call reset() before step().")
        if self.state_data.done:
            raise RuntimeError("Episode already done. Call reset() to start a new one.")

        task = self.active_task
        action_signature = f"{action.action_type}|{action.target_id}|{sorted(action.payload.items())}"

        valid, error, delta, raw_penalty = self._apply_action(task, action)

        self.state_data.step_index += 1

        if action.action_type == "noop":
            self._noop_streak += 1
        else:
            self._noop_streak = 0

        if action_signature == self._previous_action_signature:
            raw_penalty += 0.25
        self._previous_action_signature = action_signature

        if self._noop_streak >= 2:
            raw_penalty += min(0.5, 0.1 * self._noop_streak)

        if not valid:
            self.state_data.invalid_action_count += 1

        grading = grade_task(task, self.db_index, self.state_data.action_history)
        grader_score = float(grading.get("score", 0.0))
        grader_components = dict(grading.get("components", {}))
        grader_violations = list(grading.get("violations", []))
        consistency = float(grading.get("consistency", 0.0))

        previous_score = self.state_data.grader_score
        progress_delta = grader_score - previous_score

        validity_component = 1.0 if valid else 0.0
        progress_component = _clamp(progress_delta, 0.0, 1.0)
        consistency_component = _clamp(consistency, 0.0, 1.0)
        penalty_component = _clamp(raw_penalty, 0.0, 1.0)

        task_complete = grader_score >= 0.999
        exhausted = self.state_data.step_index >= task.max_steps
        too_many_invalid = self.state_data.invalid_action_count >= 3
        done = task_complete or exhausted or too_many_invalid

        terminal_bonus = 0.20 if task_complete else 0.0

        reward_value = (
            0.20 * validity_component
            + 0.45 * progress_component
            + 0.20 * consistency_component
            - 0.15 * penalty_component
            + terminal_bonus
        )
        reward_value = _clamp(reward_value, -1.0, 1.0)

        if exhausted and not task_complete:
            grader_violations.append("step budget exhausted")
        if too_many_invalid and not task_complete:
            grader_violations.append("too many invalid actions")

        info = ITSMInfo(
            task_complete=task_complete,
            grader_score=_clamp(grader_score, 0.0, 1.0),
            violations=grader_violations,
            state_delta=delta,
        )

        reward_model = ITSMReward(
            total=reward_value,
            components={
                "validity": validity_component,
                "progress": progress_component,
                "consistency": consistency_component,
                "penalty": penalty_component,
                "terminal_bonus": terminal_bonus,
            },
            normalized_progress=_clamp(grader_score, 0.0, 1.0),
        )

        self.state_data.grader_score = _clamp(grader_score, 0.0, 1.0)
        self.state_data.cumulative_reward += reward_value
        self.state_data.done = done
        self.state_data.violations = info.violations

        self._last_action_status = "ok" if valid else "invalid"
        self._last_action_error = error
        self._last_state_delta = delta
        self._last_components = grader_components

        self.state_data.action_history.append(
            {
                "step": self.state_data.step_index,
                "action": action.model_dump(),
                "valid": valid,
                "error": error,
                "state_delta": deepcopy(delta),
                "grader_score": self.state_data.grader_score,
                "reward": reward_value,
            }
        )

        observation = self._build_observation()
        return ITSMStepResult(observation=observation, reward=reward_model, done=done, info=info)

    def state(self) -> dict[str, Any]:
        snapshot = self.state_data.model_dump()
        snapshot["active_task"] = self.active_task.model_dump() if self.active_task is not None else None
        return snapshot

    # ---------------------------------------------------------------------
    # Internal state helpers
    # ---------------------------------------------------------------------

    def _build_observation(self) -> ITSMObservation:
        if self.active_task is None:
            raise RuntimeError("No active task")

        ticket_snapshot = self._get_ticket_snapshot(self.active_task)
        related_entities = self._get_related_entities(self.active_task, ticket_snapshot)

        return ITSMObservation(
            task_id=self.active_task.task_id,
            task_type=self.active_task.source_table,
            step_index=self.state_data.step_index,
            max_steps=self.active_task.max_steps,
            ticket_snapshot=ticket_snapshot,
            related_entities=related_entities,
            allowed_actions=self.active_task.allowed_action_types,
            last_action_status=self._last_action_status,
            last_action_error=self._last_action_error,
            progress_signals={
                "objective": self.active_task.objective,
                "targets_hint": self.active_task.grader_targets,
                "grader_score": self.state_data.grader_score,
                "normalized_progress": self.state_data.grader_score,
                "invalid_action_count": self.state_data.invalid_action_count,
                "cumulative_reward": self.state_data.cumulative_reward,
                "grader_components": self._last_components,
            },
        )

    def _get_ticket_snapshot(self, task: TaskDefinition) -> dict[str, Any]:
        table = task.source_table
        source_id = task.source_id
        row = self.db_index[table].get(source_id)
        return deepcopy(row) if row is not None else {}

    def _get_related_entities(self, task: TaskDefinition, ticket_snapshot: dict[str, Any]) -> dict[str, Any]:
        related: dict[str, Any] = {}

        if task.source_table == "incident":
            incident_id = task.source_id
            related["incident_sla"] = [
                {"incident_sla_id": row["incident_sla_id"], "stage": row.get("stage"), "has_breached": row.get("has_breached")}
                for row in self.db_index["incident_sla"].values()
                if row.get("incident_id") == incident_id
            ]
            related["incident_knowledge"] = [
                {
                    "incident_kb_id": row["incident_kb_id"],
                    "knowledge_id": row.get("knowledge_id"),
                    "used_as": row.get("used_as"),
                }
                for row in self.db_index["incident_knowledge"].values()
                if row.get("incident_id") == incident_id
            ]

            linked_problem = ticket_snapshot.get("problem")
            if linked_problem:
                for problem in self.db_index["problem"].values():
                    if problem.get("number") == linked_problem:
                        related["problem"] = deepcopy(problem)
                        break

        elif task.source_table == "incident_sla":
            incident_id = ticket_snapshot.get("incident_id")
            if incident_id:
                related["incident"] = deepcopy(self.db_index["incident"].get(str(incident_id), {}))

        elif task.source_table == "problem":
            original_task = ticket_snapshot.get("original_task")
            if original_task:
                for incident in self.db_index["incident"].values():
                    if incident.get("number") == original_task:
                        related["incident"] = deepcopy(incident)
                        break

        elif task.source_table == "incident_knowledge":
            incident_id = ticket_snapshot.get("incident_id")
            if incident_id:
                related["incident"] = deepcopy(self.db_index["incident"].get(str(incident_id), {}))

        return related

    # ---------------------------------------------------------------------
    # Action execution
    # ---------------------------------------------------------------------

    def _apply_action(self, task: TaskDefinition, action: ITSMAction) -> tuple[bool, str | None, dict[str, Any], float]:
        if action.action_type not in task.allowed_action_types:
            return False, "action type not allowed for this task", {}, 1.0

        if action.action_type == "query":
            return True, None, {"query": "ok"}, 0.0

        if action.action_type == "noop":
            return True, None, {"noop": True}, 0.2

        if action.action_type == "add_worknote":
            return self._action_add_worknote(task, action)

        if action.action_type == "set_assignment":
            return self._action_set_assignment(task, action)

        if action.action_type == "update_incident":
            return self._action_update_incident(task, action)

        if action.action_type == "update_problem":
            return self._action_update_problem(task, action)

        if action.action_type == "update_sla":
            return self._action_update_sla(task, action)

        if action.action_type == "attach_knowledge":
            return self._action_attach_knowledge(task, action)

        if action.action_type == "resolve":
            return self._action_resolve(task, action)

        if action.action_type == "close":
            return self._action_close(task, action)

        return False, "unsupported action", {}, 1.0

    def _resolve_row(self, table: str, default_id: str, action: ITSMAction) -> tuple[str, dict[str, Any] | None]:
        target_id = action.target_id or default_id
        return target_id, self.db_index[table].get(target_id)

    def _update_fields(self, row: dict[str, Any], payload: dict[str, Any], allowed_fields: set[str]) -> dict[str, Any]:
        delta: dict[str, Any] = {}
        for key, value in payload.items():
            if key not in allowed_fields:
                continue
            if row.get(key) == value:
                continue
            delta[key] = {"from": row.get(key), "to": value}
            row[key] = value

        if delta:
            row["updated_at"] = _now_iso()
            row["updated_on"] = _now_iso()
        return delta

    def _action_add_worknote(self, task: TaskDefinition, action: ITSMAction) -> tuple[bool, str | None, dict[str, Any], float]:
        text = str(action.payload.get("text", "")).strip()
        if not text:
            return False, "payload.text is required for add_worknote", {}, 0.6

        table = task.source_table
        source_id = task.source_id
        if table == "incident_knowledge":
            row = self.db_index["incident_knowledge"].get(source_id)
            if row is None:
                return False, "knowledge link row not found", {}, 0.8
            incident_id = row.get("incident_id")
            if not incident_id or str(incident_id) not in self.db_index["incident"]:
                return False, "linked incident not found", {}, 0.8
            table = "incident"
            source_id = str(incident_id)

        row = self.db_index[table].get(source_id)
        if row is None:
            return False, f"{table} row not found", {}, 0.8

        old_text = row.get("worknotes") or ""
        new_text = (old_text + "\n" + text).strip() if old_text else text
        row["worknotes"] = new_text
        row["updated_at"] = _now_iso()
        row["updated_on"] = _now_iso()

        return True, None, {"worknotes": {"from": old_text, "to": new_text}}, 0.0

    def _action_set_assignment(self, task: TaskDefinition, action: ITSMAction) -> tuple[bool, str | None, dict[str, Any], float]:
        table = "problem" if task.source_table == "problem" else "incident"
        source_id = task.source_id

        if task.source_table == "incident_knowledge":
            link = self.db_index["incident_knowledge"].get(task.source_id)
            if link is None or not link.get("incident_id"):
                return False, "linked incident not found", {}, 0.8
            source_id = str(link.get("incident_id"))

        row = self.db_index[table].get(source_id)
        if row is None:
            return False, f"{table} row not found", {}, 0.8

        delta = self._update_fields(row, action.payload, {"assigned_to", "assignment_group"})
        if not delta:
            return False, "no assignment fields updated", {}, 0.3
        return True, None, delta, 0.0

    def _action_update_incident(self, task: TaskDefinition, action: ITSMAction) -> tuple[bool, str | None, dict[str, Any], float]:
        if task.source_table not in {"incident", "incident_sla", "incident_knowledge"}:
            return False, "update_incident is only valid for incident-related tasks", {}, 0.9

        target_id = task.source_id
        if task.source_table == "incident_sla":
            sla = self.db_index["incident_sla"].get(task.source_id)
            if sla is None:
                return False, "incident_sla row not found", {}, 0.9
            target_id = str(sla.get("incident_id"))
        elif task.source_table == "incident_knowledge":
            link = self.db_index["incident_knowledge"].get(task.source_id)
            if link is None:
                return False, "incident_knowledge row not found", {}, 0.9
            target_id = str(link.get("incident_id"))

        row = self.db_index["incident"].get(target_id)
        if row is None:
            return False, "incident row not found", {}, 0.9

        allowed = {
            "status",
            "category",
            "priority",
            "impact",
            "urgency",
            "description",
            "resolution_notes",
            "close_notes",
            "worknotes",
            "on_hold_reason",
            "resolved",
        }
        delta = self._update_fields(row, action.payload, allowed)
        if not delta:
            return False, "no incident fields updated", {}, 0.3
        return True, None, delta, 0.0

    def _action_update_problem(self, task: TaskDefinition, action: ITSMAction) -> tuple[bool, str | None, dict[str, Any], float]:
        if task.source_table != "problem":
            return False, "update_problem is only valid for problem tasks", {}, 0.9

        row = self.db_index["problem"].get(task.source_id)
        if row is None:
            return False, "problem row not found", {}, 0.9

        allowed = {
            "status",
            "category",
            "priority",
            "impact",
            "urgency",
            "worknotes",
            "workaround",
            "fix_notes",
            "assigned_to",
            "assignment_group",
        }
        delta = self._update_fields(row, action.payload, allowed)
        if not delta:
            return False, "no problem fields updated", {}, 0.3
        return True, None, delta, 0.0

    def _action_update_sla(self, task: TaskDefinition, action: ITSMAction) -> tuple[bool, str | None, dict[str, Any], float]:
        if task.source_table != "incident_sla":
            return False, "update_sla is only valid for incident_sla tasks", {}, 0.9

        row = self.db_index["incident_sla"].get(task.source_id)
        if row is None:
            return False, "incident_sla row not found", {}, 0.9

        allowed = {"stage", "has_breached", "start_time", "breach_time", "completed_time"}
        delta = self._update_fields(row, action.payload, allowed)
        if not delta:
            return False, "no SLA fields updated", {}, 0.3
        return True, None, delta, 0.0

    def _action_attach_knowledge(self, task: TaskDefinition, action: ITSMAction) -> tuple[bool, str | None, dict[str, Any], float]:
        if task.source_table != "incident_knowledge":
            return False, "attach_knowledge is only valid for incident_knowledge tasks", {}, 0.9

        row = self.db_index["incident_knowledge"].get(task.source_id)
        if row is None:
            return False, "incident_knowledge row not found", {}, 0.9

        allowed = {"knowledge_id", "used_as", "incident_id", "org_id"}
        delta = self._update_fields(row, action.payload, allowed)
        if not delta:
            return False, "no knowledge link fields updated", {}, 0.3
        return True, None, delta, 0.0

    def _action_resolve(self, task: TaskDefinition, action: ITSMAction) -> tuple[bool, str | None, dict[str, Any], float]:
        note = str(action.payload.get("resolution_notes", "Resolved by agent workflow.")).strip()

        if task.source_table in {"incident", "incident_sla", "incident_knowledge"}:
            if task.source_table == "incident":
                incident_id = task.source_id
            elif task.source_table == "incident_sla":
                sla = self.db_index["incident_sla"].get(task.source_id)
                if sla is None:
                    return False, "incident_sla row not found", {}, 0.9
                incident_id = str(sla.get("incident_id"))
            else:
                link = self.db_index["incident_knowledge"].get(task.source_id)
                if link is None:
                    return False, "incident_knowledge row not found", {}, 0.9
                incident_id = str(link.get("incident_id"))

            row = self.db_index["incident"].get(incident_id)
            if row is None:
                return False, "incident row not found", {}, 0.9

            previous_status = row.get("status")
            row["status"] = "resolved"
            row["resolved"] = True
            row["resolution_notes"] = note
            if not row.get("worknotes"):
                row["worknotes"] = "Resolution workflow executed"
            row["updated_at"] = _now_iso()
            return True, None, {
                "status": {"from": previous_status, "to": "resolved"},
                "resolution_notes": {"to": note},
            }, 0.0

        if task.source_table == "problem":
            row = self.db_index["problem"].get(task.source_id)
            if row is None:
                return False, "problem row not found", {}, 0.9
            previous_status = row.get("status")
            row["status"] = "resolved"
            row["fix_notes"] = note
            if not row.get("workaround"):
                row["workaround"] = "Temporary mitigation applied"
            if not row.get("worknotes"):
                row["worknotes"] = "Problem resolved"
            row["updated_on"] = _now_iso()
            return True, None, {
                "status": {"from": previous_status, "to": "resolved"},
                "fix_notes": {"to": note},
            }, 0.0

        return False, "resolve not supported for this task type", {}, 0.9

    def _action_close(self, task: TaskDefinition, action: ITSMAction) -> tuple[bool, str | None, dict[str, Any], float]:
        note = str(action.payload.get("close_notes", "Closed by agent workflow.")).strip()

        if task.source_table in {"incident", "incident_sla", "incident_knowledge"}:
            if task.source_table == "incident":
                incident_id = task.source_id
            elif task.source_table == "incident_sla":
                sla = self.db_index["incident_sla"].get(task.source_id)
                if sla is None:
                    return False, "incident_sla row not found", {}, 0.9
                incident_id = str(sla.get("incident_id"))
            else:
                link = self.db_index["incident_knowledge"].get(task.source_id)
                if link is None:
                    return False, "incident_knowledge row not found", {}, 0.9
                incident_id = str(link.get("incident_id"))

            row = self.db_index["incident"].get(incident_id)
            if row is None:
                return False, "incident row not found", {}, 0.9

            previous_status = row.get("status")
            row["status"] = "closed"
            row["close_notes"] = note
            if not row.get("resolution_notes"):
                row["resolution_notes"] = "Closed without explicit resolution notes"
            if not row.get("worknotes"):
                row["worknotes"] = "Close workflow executed"
            row["updated_at"] = _now_iso()
            return True, None, {
                "status": {"from": previous_status, "to": "closed"},
                "close_notes": {"to": note},
            }, 0.0

        if task.source_table == "problem":
            row = self.db_index["problem"].get(task.source_id)
            if row is None:
                return False, "problem row not found", {}, 0.9
            previous_status = row.get("status")
            row["status"] = "closed"
            if not row.get("fix_notes"):
                row["fix_notes"] = "Closed by agent"
            row["updated_on"] = _now_iso()
            return True, None, {
                "status": {"from": previous_status, "to": "closed"},
                "fix_notes": {"to": row.get("fix_notes")},
            }, 0.0

        return False, "close not supported for this task type", {}, 0.9
