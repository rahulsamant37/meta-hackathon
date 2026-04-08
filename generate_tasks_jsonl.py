#!/usr/bin/env python3
"""Generate tasks.jsonl from task metadata + canonical SQL seed.

Metadata source priority:
1) task.md (if present)
2) existing tasks.jsonl (fallback)

Output schema per row:
- task_id
- source_table
- source_id
- objective
- max_steps
- success_criteria
- failure_criteria
- grader_targets
- grader_weights
- allowed_action_types
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
TASK_MD = ROOT / "task.md"
TASKS_JSONL_SEED = ROOT / "tasks.jsonl"
SQL_SEED = ROOT / "itsm" / "dbs" / "db_1768479715490_ex6u7viv2.sql"
OUT_PATH = ROOT / "tasks.jsonl"

TASK_ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*(ITSM-\d{3})\s*\|\s*([a-z_]+)\s*\|\s*([A-Z0-9_]+)\s*\|\s*(.*?)\s*\|(?:\s*[^|]*\s*\|)?$"
)
INSERT_RE = re.compile(r"^INSERT INTO\s+([a-zA-Z_]+)\s*\((.*?)\)\s*VALUES\s*$", re.IGNORECASE)

STEP_LIMITS = {
    "incident": 8,
    "incident_sla": 6,
    "problem": 8,
    "incident_knowledge": 5,
}

ALLOWED_ACTIONS = {
    "incident": [
        "query",
        "update_incident",
        "set_assignment",
        "add_worknote",
        "resolve",
        "close",
        "noop",
    ],
    "incident_sla": [
        "query",
        "update_sla",
        "update_incident",
        "add_worknote",
        "noop",
    ],
    "problem": [
        "query",
        "update_problem",
        "set_assignment",
        "add_worknote",
        "resolve",
        "noop",
    ],
    "incident_knowledge": [
        "query",
        "attach_knowledge",
        "update_incident",
        "add_worknote",
        "noop",
    ],
}

GRADER_WEIGHTS = {
    "incident": {
        "status": 0.40,
        "assignment": 0.20,
        "notes": 0.20,
        "priority_consistency": 0.20,
    },
    "incident_sla": {
        "stage": 0.50,
        "breach_semantics": 0.30,
        "timestamps": 0.20,
    },
    "problem": {
        "status_progression": 0.35,
        "link_integrity": 0.35,
        "fix_completeness": 0.30,
    },
    "incident_knowledge": {
        "knowledge_match": 0.50,
        "usage_mode": 0.30,
        "context_alignment": 0.20,
    },
}

TABLE_ID_FIELD = {
    "incident": "incident_id",
    "incident_sla": "incident_sla_id",
    "problem": "problem_id",
    "incident_knowledge": "incident_kb_id",
}


def parse_task_md(path: Path) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = TASK_ROW_RE.match(line.strip())
        if not match:
            continue
        _, task_id, source_table, source_id, objective = match.groups()
        tasks.append(
            {
                "task_id": task_id,
                "source_table": source_table,
                "source_id": source_id,
                "objective": objective,
            }
        )

    if len(tasks) != 181:
        raise ValueError(f"Expected 181 tasks from task.md, found {len(tasks)}")

    ids = [t["task_id"] for t in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate task_id values found in task.md")

    return sorted(tasks, key=lambda t: int(t["task_id"].split("-")[1]))


def parse_task_seed_jsonl(path: Path) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            data = json.loads(line)
            tasks.append(
                {
                    "task_id": data["task_id"],
                    "source_table": data["source_table"],
                    "source_id": data["source_id"],
                    "objective": data["objective"],
                }
            )

    if len(tasks) != 181:
        raise ValueError(f"Expected 181 tasks from tasks.jsonl seed, found {len(tasks)}")

    ids = [t["task_id"] for t in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate task_id values found in tasks.jsonl seed")

    return sorted(tasks, key=lambda t: int(t["task_id"].split("-")[1]))


def parse_sql_token(token: str) -> Any:
    token = token.strip()
    upper = token.upper()
    if upper == "NULL":
        return None
    if upper == "TRUE":
        return True
    if upper == "FALSE":
        return False
    if token.startswith("'") and token.endswith("'"):
        return token[1:-1].replace("''", "'")
    if re.fullmatch(r"-?\d+", token):
        return int(token)
    if re.fullmatch(r"-?\d+\.\d+", token):
        return float(token)
    return token


def extract_tuples(values_text: str) -> list[str]:
    tuples: list[str] = []
    in_quote = False
    depth = 0
    start = None
    i = 0

    while i < len(values_text):
        ch = values_text[i]

        if ch == "'" and i + 1 < len(values_text) and values_text[i + 1] == "'":
            i += 2
            continue

        if ch == "'":
            in_quote = not in_quote
            i += 1
            continue

        if not in_quote:
            if ch == "(":
                if depth == 0:
                    start = i + 1
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and start is not None:
                    tuples.append(values_text[start:i])
                    start = None
        i += 1

    return tuples


def split_tuple_values(tuple_text: str) -> list[Any]:
    parts: list[str] = []
    buffer: list[str] = []
    in_quote = False
    depth = 0
    i = 0

    while i < len(tuple_text):
        ch = tuple_text[i]

        if ch == "'" and i + 1 < len(tuple_text) and tuple_text[i + 1] == "'":
            buffer.append("''")
            i += 2
            continue

        if ch == "'":
            in_quote = not in_quote
            buffer.append(ch)
            i += 1
            continue

        if not in_quote:
            if ch == "(":
                depth += 1
            elif ch == ")" and depth > 0:
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append("".join(buffer).strip())
                buffer = []
                i += 1
                continue

        buffer.append(ch)
        i += 1

    parts.append("".join(buffer).strip())
    return [parse_sql_token(p) for p in parts]


def parse_sql_seed(path: Path) -> dict[str, list[dict[str, Any]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    table_rows: dict[str, list[dict[str, Any]]] = {}

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        match = INSERT_RE.match(line)
        if not match:
            i += 1
            continue

        table = match.group(1)
        columns = [c.strip() for c in match.group(2).split(",")]

        i += 1
        chunk_lines: list[str] = []
        while i < len(lines):
            part = lines[i].strip()
            if not part or part.startswith("--"):
                i += 1
                continue
            chunk_lines.append(part)
            if part.endswith(";"):
                break
            i += 1

        values_text = " ".join(chunk_lines)
        tuples = extract_tuples(values_text)
        parsed_rows: list[dict[str, Any]] = []
        for t in tuples:
            values = split_tuple_values(t)
            if len(values) != len(columns):
                raise ValueError(
                    f"Column/value mismatch for table {table}: {len(columns)} columns, {len(values)} values"
                )
            parsed_rows.append(dict(zip(columns, values)))

        table_rows.setdefault(table, []).extend(parsed_rows)
        i += 1

    return table_rows


def incident_target_status(initial_status: str | None) -> str:
    if initial_status in {"new", "in_progress", "on_hold"}:
        return "resolved"
    if initial_status == "resolved":
        return "closed"
    if initial_status == "closed":
        return "closed"
    return "resolved"


def problem_target_status(initial_status: str | None) -> str:
    if initial_status == "new":
        return "assess"
    if initial_status == "assess":
        return "root_cause"
    if initial_status == "root_cause":
        return "fix_in_progress"
    if initial_status == "fix_in_progress":
        return "resolved"
    if initial_status == "resolved":
        return "closed"
    if initial_status == "closed":
        return "closed"
    return "fix_in_progress"


def sla_target_stage(initial_stage: str | None) -> str:
    if initial_stage == "completed":
        return "in_progress"
    if initial_stage == "in_progress":
        return "paused"
    if initial_stage == "paused":
        return "completed"
    if initial_stage == "breached":
        return "breached"
    return "in_progress"


def build_incident_record(task: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    target_status = incident_target_status(row.get("status"))
    required_fields = ["assigned_to", "assignment_group", "worknotes"]
    if target_status in {"resolved", "closed"}:
        required_fields.append("resolution_notes")
    if target_status == "closed":
        required_fields.append("close_notes")

    return {
        **task,
        "max_steps": STEP_LIMITS["incident"],
        "success_criteria": [
            "final incident status matches target_status",
            "required_non_null_fields are present",
            "priority-impact-urgency consistency is maintained",
        ],
        "failure_criteria": [
            "invalid lifecycle transition",
            "missing required notes/assignment fields",
            "destructive or unrelated ticket mutation",
            "step budget exhausted before meeting status/field requirements",
        ],
        "grader_targets": {
            "entity": "incident",
            "incident_id": row.get("incident_id"),
            "incident_number": row.get("number"),
            "org_id": row.get("org_id"),
            "initial_status": row.get("status"),
            "target_status": target_status,
            "required_non_null_fields": required_fields,
            "assignment_group": row.get("assignment_group"),
            "priority": row.get("priority"),
            "impact": row.get("impact"),
            "urgency": row.get("urgency"),
            "category": row.get("category"),
        },
        "grader_weights": GRADER_WEIGHTS["incident"],
        "allowed_action_types": ALLOWED_ACTIONS["incident"],
    }


def build_problem_record(task: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    target_status = problem_target_status(row.get("status"))

    return {
        **task,
        "max_steps": STEP_LIMITS["problem"],
        "success_criteria": [
            "problem status reaches deterministic target_status",
            "link integrity is preserved for incident/service/CI references",
            "workaround/fix fields are populated when required by target status",
        ],
        "failure_criteria": [
            "status regression or invalid transition",
            "broken or removed core linkage fields",
            "missing root-cause/fix evidence for progressed states",
            "step budget exhausted before target status",
        ],
        "grader_targets": {
            "entity": "problem",
            "problem_id": row.get("problem_id"),
            "problem_number": row.get("number"),
            "org_id": row.get("org_id"),
            "initial_status": row.get("status"),
            "target_status": target_status,
            "original_task": row.get("original_task"),
            "service": row.get("service"),
            "service_offering": row.get("service_offering"),
            "configuration_item": row.get("configuration_item"),
            "assignment_group": row.get("assignment_group"),
            "assigned_to": row.get("assigned_to"),
            "priority": row.get("priority"),
            "impact": row.get("impact"),
            "urgency": row.get("urgency"),
        },
        "grader_weights": GRADER_WEIGHTS["problem"],
        "allowed_action_types": ALLOWED_ACTIONS["problem"],
    }


def build_sla_record(task: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    target_stage = sla_target_stage(row.get("stage"))
    has_breached = target_stage == "breached"

    return {
        **task,
        "max_steps": STEP_LIMITS["incident_sla"],
        "success_criteria": [
            "final SLA stage equals target_stage",
            "breach flag remains semantically consistent with stage/timestamps",
            "SLA timestamps remain logically ordered and valid",
        ],
        "failure_criteria": [
            "invalid or contradictory SLA stage",
            "breach semantics mismatch",
            "timestamp corruption or impossible ordering",
            "step budget exhausted without matching target stage",
        ],
        "grader_targets": {
            "entity": "incident_sla",
            "incident_sla_id": row.get("incident_sla_id"),
            "incident_id": row.get("incident_id"),
            "sla_def_id": row.get("sla_def_id"),
            "org_id": row.get("org_id"),
            "target_stage": target_stage,
            "has_breached": has_breached,
            "start_time": row.get("start_time"),
            "breach_time": row.get("breach_time"),
            "completed_time": row.get("completed_time"),
        },
        "grader_weights": GRADER_WEIGHTS["incident_sla"],
        "allowed_action_types": ALLOWED_ACTIONS["incident_sla"],
    }


def build_knowledge_record(task: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    return {
        **task,
        "max_steps": STEP_LIMITS["incident_knowledge"],
        "success_criteria": [
            "incident is linked to target knowledge article",
            "usage mode equals target used_as",
            "link context remains aligned with incident identity",
        ],
        "failure_criteria": [
            "wrong knowledge article attached",
            "wrong usage mode for the target link",
            "link removed or replaced with unrelated incident",
            "step budget exhausted without target knowledge linkage",
        ],
        "grader_targets": {
            "entity": "incident_knowledge",
            "incident_kb_id": row.get("incident_kb_id"),
            "incident_id": row.get("incident_id"),
            "knowledge_id": row.get("knowledge_id"),
            "org_id": row.get("org_id"),
            "target_used_as": row.get("used_as"),
        },
        "grader_weights": GRADER_WEIGHTS["incident_knowledge"],
        "allowed_action_types": ALLOWED_ACTIONS["incident_knowledge"],
    }


def build_record(task: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    table = task["source_table"]
    if table == "incident":
        return build_incident_record(task, row)
    if table == "problem":
        return build_problem_record(task, row)
    if table == "incident_sla":
        return build_sla_record(task, row)
    if table == "incident_knowledge":
        return build_knowledge_record(task, row)
    raise ValueError(f"Unsupported source_table: {table}")


def build_index(seed_tables: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, dict[str, Any]]]:
    index: dict[str, dict[str, dict[str, Any]]] = {}
    for table, id_field in TABLE_ID_FIELD.items():
        rows = seed_tables.get(table)
        if not rows:
            raise ValueError(f"Missing required table in SQL seed: {table}")
        idx = {}
        for row in rows:
            key = row.get(id_field)
            if key is None:
                continue
            idx[str(key)] = row
        index[table] = idx
    return index


def main() -> None:
    if TASK_MD.exists():
        tasks = parse_task_md(TASK_MD)
        print(f"Using task metadata from {TASK_MD}")
    elif TASKS_JSONL_SEED.exists():
        tasks = parse_task_seed_jsonl(TASKS_JSONL_SEED)
        print(f"Using task metadata from {TASKS_JSONL_SEED} (fallback)")
    else:
        raise FileNotFoundError(f"Neither {TASK_MD} nor {TASKS_JSONL_SEED} exists")

    seed_tables = parse_sql_seed(SQL_SEED)
    table_index = build_index(seed_tables)

    records: list[dict[str, Any]] = []
    for task in tasks:
        table = task["source_table"]
        source_id = task["source_id"]
        row = table_index.get(table, {}).get(source_id)
        if row is None:
            raise ValueError(f"Could not find source row for {task['task_id']} -> {table}:{source_id}")
        records.append(build_record(task, row))

    if len(records) != 181:
        raise ValueError(f"Expected 181 output records, got {len(records)}")

    required_keys = {
        "task_id",
        "source_table",
        "source_id",
        "objective",
        "max_steps",
        "success_criteria",
        "failure_criteria",
        "grader_targets",
        "grader_weights",
        "allowed_action_types",
    }

    for rec in records:
        missing = required_keys - rec.keys()
        if missing:
            raise ValueError(f"Record {rec.get('task_id')} missing keys: {sorted(missing)}")

    with OUT_PATH.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    counts = Counter(r["source_table"] for r in records)
    print(f"Wrote {OUT_PATH}")
    print(f"total_records={len(records)}")
    for table in sorted(counts):
        print(f"{table}={counts[table]}")


if __name__ == "__main__":
    main()
