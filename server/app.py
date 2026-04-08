from __future__ import annotations

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from models import ITSMAction
from server.environment import ITSMEnvironment


class ResetRequest(BaseModel):
    task_id: str | None = None


env = ITSMEnvironment()

app = FastAPI(title="ITSM OpenEnv", version="0.1.0")


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "itsm-openenv-benchmark",
        "status": "ok",
        "docs": "/docs",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/web", response_class=HTMLResponse)
def web() -> str:
    return """<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>ITSM OpenEnv Playground</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

        :root {
            --page-top: #f4f9f7;
            --page-bottom: #e9eff6;
            --ink: #153145;
            --ink-soft: #476179;
            --panel: rgba(255, 255, 255, 0.76);
            --panel-border: rgba(21, 49, 69, 0.12);
            --accent: #1a8f6a;
            --accent-2: #0b6ab0;
            --warn: #b3472a;
            --mono: "IBM Plex Mono", "DejaVu Sans Mono", monospace;
            --sans: "Sora", "Trebuchet MS", sans-serif;
        }

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            color: var(--ink);
            font-family: var(--sans);
            background:
                radial-gradient(1200px 500px at 8% -10%, #cbe8dd 0%, transparent 55%),
                radial-gradient(900px 420px at 92% -18%, #c9ddf1 0%, transparent 56%),
                linear-gradient(180deg, var(--page-top) 0%, var(--page-bottom) 100%);
            min-height: 100vh;
        }

        .shell {
            max-width: 1200px;
            margin: 0 auto;
            padding: 24px 18px 36px;
        }

        .topbar {
            display: grid;
            grid-template-columns: 1.25fr 1fr;
            gap: 14px;
            margin-bottom: 14px;
        }

        .panel {
            border: 1px solid var(--panel-border);
            background: var(--panel);
            backdrop-filter: blur(8px);
            border-radius: 16px;
            padding: 14px 16px;
            box-shadow: 0 10px 36px rgba(15, 41, 59, 0.08);
        }

        .title {
            margin: 0;
            font-size: 1.4rem;
            letter-spacing: 0.02em;
        }

        .sub {
            margin-top: 8px;
            font-size: 0.93rem;
            color: var(--ink-soft);
            line-height: 1.45;
        }

        .chips {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 12px;
        }

        .chip {
            border: 1px solid rgba(21, 49, 69, 0.14);
            border-radius: 999px;
            padding: 4px 10px;
            font-size: 0.75rem;
            font-family: var(--mono);
            color: #163a52;
            background: rgba(255, 255, 255, 0.7);
        }

        .status {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            margin-bottom: 8px;
        }

        .status-pill {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            border-radius: 999px;
            border: 1px solid rgba(21, 49, 69, 0.16);
            padding: 6px 10px;
            font-size: 0.78rem;
            font-family: var(--mono);
            background: rgba(255, 255, 255, 0.75);
        }

        .dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #7a8ea3;
        }

        .dot.good {
            background: var(--accent);
        }

        .dot.bad {
            background: var(--warn);
        }

        .layout {
            display: grid;
            grid-template-columns: 1.2fr 1fr;
            gap: 14px;
        }

        .stack {
            display: grid;
            gap: 14px;
        }

        .section-title {
            margin: 0 0 10px;
            font-size: 0.9rem;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            color: #325069;
            font-family: var(--mono);
        }

        label {
            display: block;
            margin-bottom: 6px;
            font-size: 0.8rem;
            color: #2b4a63;
            letter-spacing: 0.02em;
            font-family: var(--mono);
        }

        input,
        select,
        textarea,
        button {
            font: inherit;
            width: 100%;
            border-radius: 10px;
            border: 1px solid rgba(17, 53, 78, 0.2);
        }

        input,
        select,
        textarea {
            padding: 10px 11px;
            background: rgba(255, 255, 255, 0.92);
            color: #0f2f45;
            font-family: var(--mono);
        }

        textarea {
            min-height: 96px;
            resize: vertical;
        }

        .row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }

        .button-row {
            display: flex;
            gap: 8px;
            margin-top: 10px;
        }

        button {
            cursor: pointer;
            padding: 10px 12px;
            transition: transform 0.12s ease, box-shadow 0.12s ease, background 0.2s ease;
            font-weight: 600;
            color: #f4fbff;
            border: 0;
            background: linear-gradient(125deg, var(--accent-2) 0%, #156196 55%, var(--accent) 100%);
            box-shadow: 0 8px 20px rgba(12, 59, 90, 0.18);
        }

        button:hover {
            transform: translateY(-1px);
            box-shadow: 0 10px 24px rgba(12, 59, 90, 0.24);
        }

        button.ghost {
            color: #16405d;
            border: 1px solid rgba(21, 49, 69, 0.24);
            background: rgba(255, 255, 255, 0.85);
            box-shadow: none;
        }

        .mini {
            font-size: 0.78rem;
            color: var(--ink-soft);
            line-height: 1.4;
            margin-top: 8px;
        }

        .console {
            margin: 0;
            border-radius: 12px;
            border: 1px solid rgba(16, 47, 70, 0.16);
            background: #0f2434;
            color: #d8f2ff;
            padding: 12px;
            min-height: 250px;
            max-height: 500px;
            overflow: auto;
            font-size: 0.82rem;
            line-height: 1.45;
            font-family: var(--mono);
        }

        .facts {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 8px;
            margin-bottom: 10px;
        }

        .fact {
            border-radius: 10px;
            border: 1px solid rgba(18, 64, 96, 0.14);
            background: rgba(255, 255, 255, 0.84);
            padding: 10px;
            min-height: 64px;
        }

        .fact span {
            display: block;
            font-family: var(--mono);
            font-size: 0.72rem;
            color: #40647d;
            margin-bottom: 6px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .fact strong {
            display: block;
            font-size: 0.9rem;
            color: #14374f;
            word-break: break-word;
        }

        .timeline {
            margin: 0;
            padding-left: 18px;
            max-height: 260px;
            overflow: auto;
            font-family: var(--mono);
            font-size: 0.78rem;
            color: #2a4f67;
            line-height: 1.35;
        }

        .timeline li {
            margin-bottom: 8px;
        }

        a.doc-link {
            color: #0b5f93;
            font-size: 0.83rem;
            text-decoration: none;
            border-bottom: 1px dashed rgba(11, 95, 147, 0.45);
        }

        @media (max-width: 980px) {
            .topbar,
            .layout,
            .row {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <main class="shell">
        <section class="topbar">
            <article class="panel">
                <h1 class="title">ITSM OpenEnv Playground</h1>
                <p class="sub">
                    Interactive control deck inspired by OpenEnv environment spaces. Use this panel to reset tasks,
                    submit structured actions, inspect reward signals, and watch environment state evolve in real time.
                </p>
                <div class="chips">
                    <span class="chip">POST /reset</span>
                    <span class="chip">POST /step</span>
                    <span class="chip">GET /state</span>
                    <span class="chip">GET /health</span>
                </div>
            </article>

            <article class="panel">
                <div class="status">
                    <strong>Session status</strong>
                    <a class="doc-link" href="/docs" target="_blank" rel="noopener noreferrer">Open API docs</a>
                </div>
                <div id="status-pill" class="status-pill">
                    <span id="status-dot" class="dot"></span>
                    <span id="status-text">Waiting for health check</span>
                </div>
                <p id="status-note" class="mini">Tip: start with Health, then Reset, then Step.</p>
            </article>
        </section>

        <section class="layout">
            <div class="stack">
                <article class="panel">
                    <h2 class="section-title">Service controls</h2>
                    <div class="button-row">
                        <button id="btn-health" type="button">Check health</button>
                        <button id="btn-state" class="ghost" type="button">Fetch state</button>
                    </div>
                </article>

                <article class="panel">
                    <h2 class="section-title">Reset episode</h2>
                    <form id="reset-form">
                        <label for="task-id">Task ID (optional)</label>
                        <input id="task-id" type="text" placeholder="ITSM-001" />
                        <div class="button-row">
                            <button type="submit">POST /reset</button>
                        </div>
                    </form>
                </article>

                <article class="panel">
                    <h2 class="section-title">Send step action</h2>
                    <form id="step-form">
                        <div class="row">
                            <div>
                                <label for="action-type">Action type</label>
                                <select id="action-type"></select>
                            </div>
                            <div>
                                <label for="target-id">Target ID (optional)</label>
                                <input id="target-id" type="text" placeholder="INC_001" />
                            </div>
                        </div>

                        <label for="action-payload">Payload JSON</label>
                        <textarea id="action-payload">{}</textarea>

                        <label for="action-reasoning">Reasoning (optional)</label>
                        <textarea id="action-reasoning" placeholder="Explain your action intent for traceability"></textarea>

                        <div class="button-row">
                            <button type="submit">POST /step</button>
                            <button id="btn-clear-payload" class="ghost" type="button">Clear payload</button>
                        </div>
                        <p class="mini">Allowed actions update automatically after each reset or step response.</p>
                    </form>
                </article>
            </div>

            <div class="stack">
                <article class="panel">
                    <h2 class="section-title">Current snapshot</h2>
                    <div class="facts">
                        <div class="fact"><span>Task ID</span><strong id="fact-task">-</strong></div>
                        <div class="fact"><span>Task type</span><strong id="fact-type">-</strong></div>
                        <div class="fact"><span>Step / max</span><strong id="fact-step">-</strong></div>
                        <div class="fact"><span>Allowed actions</span><strong id="fact-actions">-</strong></div>
                        <div class="fact"><span>Last status</span><strong id="fact-status">-</strong></div>
                        <div class="fact"><span>Progress</span><strong id="fact-progress">-</strong></div>
                    </div>
                </article>

                <article class="panel">
                    <h2 class="section-title">Response console</h2>
                    <pre id="response-console" class="console">No response yet.</pre>
                </article>

                <article class="panel">
                    <h2 class="section-title">Action timeline</h2>
                    <ol id="timeline" class="timeline"></ol>
                </article>
            </div>
        </section>
    </main>

    <script>
        const ACTION_TYPES = [
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
        ];

        const state = {
            observation: null,
            timeline: [],
        };

        const el = {
            actionType: document.getElementById("action-type"),
            taskId: document.getElementById("task-id"),
            payload: document.getElementById("action-payload"),
            targetId: document.getElementById("target-id"),
            reasoning: document.getElementById("action-reasoning"),
            response: document.getElementById("response-console"),
            timeline: document.getElementById("timeline"),
            statusText: document.getElementById("status-text"),
            statusDot: document.getElementById("status-dot"),
            statusNote: document.getElementById("status-note"),
            factTask: document.getElementById("fact-task"),
            factType: document.getElementById("fact-type"),
            factStep: document.getElementById("fact-step"),
            factActions: document.getElementById("fact-actions"),
            factStatus: document.getElementById("fact-status"),
            factProgress: document.getElementById("fact-progress"),
        };

        function setStatus(text, mode) {
            el.statusText.textContent = text;
            el.statusDot.classList.remove("good", "bad");
            if (mode === "good") el.statusDot.classList.add("good");
            if (mode === "bad") el.statusDot.classList.add("bad");
        }

        function updateActionOptions(actions) {
            const source = Array.isArray(actions) && actions.length ? actions : ACTION_TYPES;
            const current = el.actionType.value;
            el.actionType.innerHTML = "";

            source.forEach((item) => {
                const option = document.createElement("option");
                option.value = item;
                option.textContent = item;
                el.actionType.appendChild(option);
            });

            if (source.includes(current)) {
                el.actionType.value = current;
            }
        }

        function setResponse(payload) {
            el.response.textContent = JSON.stringify(payload, null, 2);
        }

        function summarizeObservation(obs) {
            if (!obs) {
                el.factTask.textContent = "-";
                el.factType.textContent = "-";
                el.factStep.textContent = "-";
                el.factActions.textContent = "-";
                el.factStatus.textContent = "-";
                el.factProgress.textContent = "-";
                return;
            }

            const progress = Number(obs.progress_signals?.normalized_progress);
            el.factTask.textContent = obs.task_id || "-";
            el.factType.textContent = obs.task_type || "-";
            el.factStep.textContent = `${obs.step_index ?? "?"} / ${obs.max_steps ?? "?"}`;
            el.factActions.textContent = (obs.allowed_actions || []).slice(0, 5).join(", ") || "-";
            el.factStatus.textContent = obs.last_action_status || "none";
            el.factProgress.textContent = Number.isFinite(progress) ? progress.toFixed(3) : "-";
        }

        function addTimeline(entry) {
            state.timeline.unshift(entry);
            state.timeline = state.timeline.slice(0, 14);

            el.timeline.innerHTML = "";
            state.timeline.forEach((item) => {
                const li = document.createElement("li");
                li.textContent = item;
                el.timeline.appendChild(li);
            });
        }

        async function apiCall(path, method, body) {
            const options = {
                method,
                headers: { "Content-Type": "application/json" },
            };
            if (body !== undefined) {
                options.body = JSON.stringify(body);
            }

            const resp = await fetch(path, options);
            const text = await resp.text();
            let payload;
            try {
                payload = text ? JSON.parse(text) : {};
            } catch {
                payload = { raw: text };
            }

            if (!resp.ok) {
                const detail = payload?.detail || payload?.raw || `${resp.status}`;
                throw new Error(detail);
            }
            return payload;
        }

        async function checkHealth() {
            try {
                const payload = await apiCall("/health", "GET");
                setResponse(payload);
                setStatus("Environment healthy", "good");
                el.statusNote.textContent = "Health check passed. You can reset a task now.";
            } catch (err) {
                setStatus("Health check failed", "bad");
                el.statusNote.textContent = String(err);
            }
        }

        async function fetchState() {
            try {
                const payload = await apiCall("/state", "GET");
                setResponse(payload);
                addTimeline(`state: active_task=${payload.active_task_id || "none"}, step=${payload.step_index}`);
            } catch (err) {
                setStatus("State fetch failed", "bad");
                el.statusNote.textContent = String(err);
            }
        }

        document.getElementById("btn-health").addEventListener("click", checkHealth);
        document.getElementById("btn-state").addEventListener("click", fetchState);

        document.getElementById("reset-form").addEventListener("submit", async (event) => {
            event.preventDefault();
            const taskId = el.taskId.value.trim();
            const body = taskId ? { task_id: taskId } : {};

            try {
                const payload = await apiCall("/reset", "POST", body);
                state.observation = payload;
                summarizeObservation(payload);
                updateActionOptions(payload.allowed_actions || []);
                setResponse(payload);
                addTimeline(`reset: task=${payload.task_id || "unknown"}`);
                setStatus("Task reset successful", "good");
                el.statusNote.textContent = "Step requests are now enabled for this episode.";
            } catch (err) {
                setStatus("Reset failed", "bad");
                el.statusNote.textContent = String(err);
            }
        });

        document.getElementById("step-form").addEventListener("submit", async (event) => {
            event.preventDefault();

            let payloadObj = {};
            const payloadText = el.payload.value.trim();
            if (payloadText) {
                try {
                    payloadObj = JSON.parse(payloadText);
                } catch {
                    setStatus("Invalid payload JSON", "bad");
                    el.statusNote.textContent = "Fix payload JSON before sending /step.";
                    return;
                }
            }

            const action = {
                action_type: el.actionType.value,
                target_id: el.targetId.value.trim() || null,
                payload: payloadObj,
                reasoning: el.reasoning.value.trim() || null,
            };

            try {
                const stepResult = await apiCall("/step", "POST", action);
                setResponse(stepResult);

                if (stepResult.observation) {
                    state.observation = stepResult.observation;
                    summarizeObservation(stepResult.observation);
                    updateActionOptions(stepResult.observation.allowed_actions || []);
                }

                const reward = stepResult.reward?.total;
                const done = stepResult.done ? "done" : "running";
                addTimeline(`step: ${action.action_type}, reward=${reward}, ${done}`);
                setStatus("Step accepted", "good");
                el.statusNote.textContent = stepResult.info?.task_complete
                    ? "Task complete. Reset to start another objective."
                    : "Action processed. Continue stepping or inspect state.";
            } catch (err) {
                setStatus("Step failed", "bad");
                el.statusNote.textContent = String(err);
            }
        });

        document.getElementById("btn-clear-payload").addEventListener("click", () => {
            el.payload.value = "{}";
        });

        updateActionOptions(ACTION_TYPES);
        summarizeObservation(null);
        checkHealth();
    </script>
</body>
</html>"""


@app.post("/reset")
def reset(payload: ResetRequest | None = None) -> dict:
    task_id = payload.task_id if payload else None
    try:
        observation = env.reset(task_id=task_id)
        return observation.model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/step")
def step(action: ITSMAction) -> dict:
    try:
        result = env.step(action)
        return result.model_dump()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/state")
def state() -> dict:
    return env.state()


def main() -> None:
    uvicorn.run("server.app:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
