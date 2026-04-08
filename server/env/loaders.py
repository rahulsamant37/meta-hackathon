from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from .models import TaskDefinition

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASKS_PATH = ROOT / "tasks.jsonl"
DEFAULT_SQL_PATH = ROOT / "itsm" / "dbs" / "db_1768479715490_ex6u7viv2.sql"

INSERT_RE = re.compile(r"^INSERT INTO\s+([a-zA-Z_]+)\s*\((.*?)\)\s*VALUES\s*$", re.IGNORECASE)

TABLE_ID_FIELD = {
    "incident": "incident_id",
    "incident_sla": "incident_sla_id",
    "problem": "problem_id",
    "incident_knowledge": "incident_kb_id",
}


def load_tasks(tasks_path: Path = DEFAULT_TASKS_PATH) -> list[TaskDefinition]:
    tasks: list[TaskDefinition] = []
    with tasks_path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            tasks.append(TaskDefinition.model_validate(json.loads(line)))

    tasks.sort(key=lambda task: int(task.task_id.split("-")[1]))

    if len(tasks) != 181:
        raise ValueError(f"Expected 181 tasks, found {len(tasks)}")

    ids = [task.task_id for task in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate task_id values found in tasks.jsonl")

    return tasks


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
    idx = 0

    while idx < len(values_text):
        char = values_text[idx]

        if char == "'" and idx + 1 < len(values_text) and values_text[idx + 1] == "'":
            idx += 2
            continue

        if char == "'":
            in_quote = not in_quote
            idx += 1
            continue

        if not in_quote:
            if char == "(":
                if depth == 0:
                    start = idx + 1
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0 and start is not None:
                    tuples.append(values_text[start:idx])
                    start = None
        idx += 1

    return tuples


def split_tuple_values(tuple_text: str) -> list[Any]:
    pieces: list[str] = []
    chunk: list[str] = []
    in_quote = False
    depth = 0
    idx = 0

    while idx < len(tuple_text):
        char = tuple_text[idx]

        if char == "'" and idx + 1 < len(tuple_text) and tuple_text[idx + 1] == "'":
            chunk.append("''")
            idx += 2
            continue

        if char == "'":
            in_quote = not in_quote
            chunk.append(char)
            idx += 1
            continue

        if not in_quote:
            if char == "(":
                depth += 1
            elif char == ")" and depth > 0:
                depth -= 1
            elif char == "," and depth == 0:
                pieces.append("".join(chunk).strip())
                chunk = []
                idx += 1
                continue

        chunk.append(char)
        idx += 1

    pieces.append("".join(chunk).strip())
    return [parse_sql_token(piece) for piece in pieces]


def load_sql_tables(sql_path: Path = DEFAULT_SQL_PATH) -> dict[str, list[dict[str, Any]]]:
    lines = sql_path.read_text(encoding="utf-8").splitlines()
    table_rows: dict[str, list[dict[str, Any]]] = {}

    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        match = INSERT_RE.match(line)
        if not match:
            idx += 1
            continue

        table_name = match.group(1)
        columns = [column.strip() for column in match.group(2).split(",")]

        idx += 1
        value_lines: list[str] = []
        while idx < len(lines):
            part = lines[idx].strip()
            if not part or part.startswith("--"):
                idx += 1
                continue
            value_lines.append(part)
            if part.endswith(";"):
                break
            idx += 1

        tuples = extract_tuples(" ".join(value_lines))
        rows: list[dict[str, Any]] = []
        for tuple_text in tuples:
            values = split_tuple_values(tuple_text)
            if len(values) != len(columns):
                raise ValueError(
                    f"Column/value mismatch for table {table_name}: {len(columns)} columns and {len(values)} values"
                )
            rows.append(dict(zip(columns, values)))

        table_rows.setdefault(table_name, []).extend(rows)
        idx += 1

    return table_rows


def build_entity_index(table_rows: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, dict[str, Any]]]:
    index: dict[str, dict[str, dict[str, Any]]] = {}
    for table_name, id_field in TABLE_ID_FIELD.items():
        rows = table_rows.get(table_name)
        if rows is None:
            raise ValueError(f"Missing required table in SQL seed: {table_name}")

        table_index: dict[str, dict[str, Any]] = {}
        for row in rows:
            row_id = row.get(id_field)
            if row_id is None:
                continue
            table_index[str(row_id)] = row
        index[table_name] = table_index

    return index


def clone_index(index: dict[str, dict[str, dict[str, Any]]]) -> dict[str, dict[str, dict[str, Any]]]:
    return copy.deepcopy(index)
