#!/usr/bin/env python3
"""
ITSM OpenEnv Benchmark — fixed visualization.
Panel C fixes:
  - Narrower bars with more breathing room between pairs
  - Labels staggered (step below bar top, terminal above) — no collision
  - Legend moved to upper RIGHT, outside bar region
  - y-axis headroom expanded so labels never touch the plot border
  - Value labels use path-effects stroke for readability on any background
"""
from __future__ import annotations

import argparse
import json
import re
import matplotlib.patheffects as pe
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import matplotlib.pyplot as plt
import numpy as np

START_RE = re.compile(r"^\[START\]\s+task=([^\s]+)")
END_RE = re.compile(
    r"^\[END\]\s+success=(true|false)\s+steps=(\d+)(?:\s+score=([0-9.]+))?\s+rewards=([0-9.,-]*)"
)

TYPE_ORDER = ["incident", "incident_sla", "problem", "incident_knowledge"]
TYPE_LABELS = {
    "incident":           "Incident",
    "incident_sla":       "Incident SLA",
    "problem":            "Problem",
    "incident_knowledge": "Incident Knowledge",
}


@dataclass
class Episode:
    task_id: str
    source_table: str
    max_steps: int
    success: bool
    steps: int
    rewards: list[float]

    @property
    def episode_return(self) -> float:
        return float(sum(self.rewards))

    @property
    def terminal_reward(self) -> float:
        return float(self.rewards[-1]) if self.rewards else 0.0


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(np.mean(np.array(values, dtype=np.float64)))


def load_task_manifest(path: Path) -> dict[str, dict[str, object]]:
    tasks: dict[str, dict[str, object]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            row = json.loads(line)
            tasks[str(row["task_id"])] = {
                "source_table": str(row.get("source_table", "unknown")),
                "max_steps":    int(row.get("max_steps", 1)),
            }
    return tasks


def parse_run_log(
    path: Path, task_manifest: dict[str, dict[str, object]]
) -> list[Episode]:
    episodes: list[Episode] = []
    current_task_id: str | None = None

    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            start_match = START_RE.match(line)
            if start_match:
                current_task_id = start_match.group(1)
                continue
            end_match = END_RE.match(line)
            if not end_match:
                continue
            if current_task_id is None:
                continue
            success     = end_match.group(1) == "true"
            steps       = int(end_match.group(2))
            rewards_raw = end_match.group(4)
            rewards     = [float(item) for item in rewards_raw.split(",") if item]
            meta        = task_manifest.get(current_task_id, {})
            episodes.append(
                Episode(
                    task_id      = current_task_id,
                    source_table = str(meta.get("source_table", "unknown")),
                    max_steps    = int(meta.get("max_steps", max(steps, 1))),
                    success      = success,
                    steps        = steps,
                    rewards      = rewards,
                )
            )
            current_task_id = None

    return episodes


def group_episodes(
    episodes: list[Episode],
    key_fn: Callable[[Episode], str],
) -> dict[str, list[Episode]]:
    grouped: dict[str, list[Episode]] = defaultdict(list)
    for episode in episodes:
        grouped[key_fn(episode)].append(episode)
    return grouped


def aggregate(episodes: list[Episode]) -> dict[str, float]:
    if not episodes:
        return dict(count=0., success_rate=0., avg_steps=0., avg_return=0.,
                    avg_terminal_reward=0., avg_step_reward=0., avg_budget_utilization=0.)
    step_rewards: list[float] = []
    for episode in episodes:
        step_rewards.extend(episode.rewards)
    return {
        "count":                  float(len(episodes)),
        "success_rate":           100.0 * mean([1. if e.success else 0. for e in episodes]),
        "avg_steps":              mean([float(e.steps) for e in episodes]),
        "avg_return":             mean([e.episode_return for e in episodes]),
        "avg_terminal_reward":    mean([e.terminal_reward for e in episodes]),
        "avg_step_reward":        mean(step_rewards),
        "avg_budget_utilization": mean(
            [100. * float(e.steps) / float(max(e.max_steps, 1)) for e in episodes]
        ),
    }


def order_keys(keys: set[str], canonical_order: list[str]) -> list[str]:
    known   = [k for k in canonical_order if k in keys]
    unknown = sorted(k for k in keys if k not in canonical_order)
    return known + unknown


def display_labels(type_keys: list[str]) -> list[str]:
    return [TYPE_LABELS.get(k, k.replace("_", " ").title()) for k in type_keys]


def build_summary(episodes: list[Episode]) -> dict[str, object]:
    by_type   = group_episodes(episodes, key_fn=lambda e: e.source_table)
    type_keys = order_keys(set(by_type.keys()), TYPE_ORDER)
    return {
        "overall": aggregate(episodes),
        "by_type": {k: aggregate(by_type[k]) for k in type_keys},
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _stroke(fg: str = "white", lw: float = 2.5):
    """Path-effects stroke that makes small labels readable on any background."""
    return [pe.withStroke(linewidth=lw, foreground=fg)]


def _annotate_bar(ax: plt.Axes, bar, text: str, y_offset: float,
                  color: str = "#222222", bg: str = "white") -> None:
    ax.text(
        bar.get_x() + bar.get_width() / 2,
        bar.get_height() + y_offset,
        text,
        ha="center", va="bottom",
        fontsize=8.5, color=color, fontweight="bold",
        path_effects=_stroke(bg),
        zorder=5,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  plot()  — bar dashboard (A / B / C)
# ─────────────────────────────────────────────────────────────────────────────

def plot(summary: dict[str, object], out_path: Path) -> None:
    by_type = summary["by_type"]
    overall = summary["overall"]

    type_keys    = list(by_type.keys())
    labels       = display_labels(type_keys)
    counts       = [int(by_type[k]["count"]) for k in type_keys]
    family_labels= [f"{l}\n(n={c})" for l, c in zip(labels, counts)]

    avg_returns      = [by_type[k]["avg_return"]             for k in type_keys]
    avg_step_rewards = [by_type[k]["avg_step_reward"]        for k in type_keys]
    terminal_rewards = [by_type[k]["avg_terminal_reward"]    for k in type_keys]
    budget_util      = [by_type[k]["avg_budget_utilization"] for k in type_keys]

    palette = ["#1f77b4", "#2ca02c", "#ff7f0e", "#9467bd"]

    plt.style.use("seaborn-v0_8-whitegrid")
    fig = plt.figure(figsize=(15.8, 9.6), dpi=220, constrained_layout=False)

    # Use tight gridspec with explicit margins
    grid = fig.add_gridspec(
        2, 2,
        height_ratios=[1.0, 1.15],
        left=0.07, right=0.97,
        top=0.91, bottom=0.10,
        hspace=0.52, wspace=0.28,
    )
    ax_a = fig.add_subplot(grid[0, 0])
    ax_b = fig.add_subplot(grid[0, 1])
    ax_c = fig.add_subplot(grid[1, :])

    # ── (A) Return per episode ────────────────────────────────────────────────
    bars = ax_a.bar(family_labels, avg_returns,
                    color=palette, alpha=0.9, edgecolor="white", linewidth=0.8)
    ax_a.set_ylabel("Average return per episode")
    ax_a.set_title("(A) Return profile by task family", pad=8)
    ax_a.set_ylim(min(avg_returns) - 0.06, max(avg_returns) + 0.07)
    for bar, v in zip(bars, avg_returns):
        _annotate_bar(ax_a, bar, f"{v:.3f}", 0.002)
    ax_a.axhline(float(overall["avg_return"]), color="#555", lw=1.2, ls="--")
    ax_a.text(len(type_keys) - 0.48, float(overall["avg_return"]) + 0.003,
              f"overall avg {float(overall['avg_return']):.3f}",
              ha="right", fontsize=8, color="#555")
    ax_a.tick_params(axis="x", rotation=12)

    # ── (B) Interaction cost ──────────────────────────────────────────────────
    bars = ax_b.bar(family_labels, budget_util,
                    color=palette, alpha=0.9, edgecolor="white", linewidth=0.8)
    ax_b.set_ylabel("Step budget used (%)")
    ax_b.set_title("(B) Interaction-cost profile", pad=8)
    ax_b.set_ylim(0.0, 78.0)
    for bar, v in zip(bars, budget_util):
        _annotate_bar(ax_b, bar, f"{v:.1f}%", 0.8)
    ax_b.axhline(float(overall["avg_budget_utilization"]), color="#555", lw=1.2, ls="--")
    ax_b.text(len(type_keys) - 0.48, float(overall["avg_budget_utilization"]) + 1.2,
              f"overall avg {float(overall['avg_budget_utilization']):.1f}%",
              ha="right", fontsize=8, color="#555")
    ax_b.tick_params(axis="x", rotation=12)

    # ── (C) Grouped bar — step vs terminal reward ─────────────────────────────
    #
    # FIX SUMMARY:
    #   1. Narrower bars (0.28 each) with a 0.06 gap between the pair
    #      → each pair only 0.62 wide, leaving ~0.38 clear space between groups
    #   2. Labels staggered: step reward label goes BELOW bar top (inside),
    #      terminal reward label goes ABOVE (outside) — opposite sides → no overlap
    #   3. y-axis top extended to 0.76 so the highest "above" label has room
    #   4. Legend placed at upper RIGHT corner, far from all bars
    #   5. Color-matched labels so reader can map text to bar without looking at legend

    x     = np.arange(len(type_keys), dtype=float)
    width = 0.28          # ← was 0.34; narrower = more whitespace between bars

    C_STEP = "#2E8B57"    # sea-green
    C_TERM = "#5A4FCF"    # indigo

    bars_step = ax_c.bar(
        x - width / 2 - 0.03,   # slight extra gap from center
        avg_step_rewards,
        width=width,
        color=C_STEP, alpha=0.87,
        edgecolor="white", linewidth=0.8,
        label="Avg step reward",
    )
    bars_term = ax_c.bar(
        x + width / 2 + 0.03,
        terminal_rewards,
        width=width,
        color=C_TERM, alpha=0.90,
        edgecolor="white", linewidth=0.8,
        label="Avg terminal reward",
    )

    ax_c.set_xticks(x)
    ax_c.set_xticklabels(family_labels, rotation=12)
    ax_c.set_ylabel("Reward value")
    ax_c.set_title("(C) Step reward vs terminal reward — per task family", pad=8)

    # Headroom: highest terminal is 0.671 + label → need ~0.74 top
    ax_c.set_ylim(0.40, 0.765)

    # Step reward: label INSIDE the bar (near top, pointing down) in white
    for bar, v in zip(bars_step, avg_step_rewards):
        ax_c.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() - 0.012,   # just inside the top edge
            f"{v:.3f}",
            ha="center", va="top",
            fontsize=8.5, color="white", fontweight="bold",
            path_effects=_stroke(C_STEP, lw=1.5),
            zorder=5,
        )

    # Terminal reward: label ABOVE the bar (outside) in dark indigo
    for bar, v in zip(bars_term, terminal_rewards):
        ax_c.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.007,   # just above the bar top
            f"{v:.3f}",
            ha="center", va="bottom",
            fontsize=8.5, color=C_TERM, fontweight="bold",
            path_effects=_stroke("white", lw=2.0),
            zorder=5,
        )

    # Legend: upper-right, well clear of all bars
    ax_c.legend(
        loc="upper right",
        ncol=1,
        frameon=True,
        framealpha=0.92,
        edgecolor="#cccccc",
        fontsize=9,
        handlelength=1.4,
        borderpad=0.6,
    )

    # ── Suptitle + footer ─────────────────────────────────────────────────────
    ov = summary["overall"]
    overall_text = (
        f"Overall: tasks={int(ov['count'])},  success={ov['success_rate']:.1f}%,  "
        f"avg steps={ov['avg_steps']:.2f},  avg return={ov['avg_return']:.3f},  "
        f"avg step reward={ov['avg_step_reward']:.3f}"
    )
    fig.suptitle(
        "ITSM OpenEnv Benchmark Dashboard (181-task deterministic run)",
        fontsize=14, fontweight="bold", y=0.975,
    )
    fig.text(0.5, 0.015, overall_text, ha="center", fontsize=9.5, color="#444444")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


# ─────────────────────────────────────────────────────────────────────────────
#  plot_line_with_markers()  — stacked line panels
# ─────────────────────────────────────────────────────────────────────────────

def plot_line_with_markers(summary: dict[str, object], out_path: Path) -> None:
    by_type   = summary["by_type"]
    type_keys = list(by_type.keys())
    labels    = display_labels(type_keys)
    x         = np.arange(len(type_keys), dtype=float)

    avg_returns   = np.array([by_type[k]["avg_return"]             for k in type_keys])
    terminal_rew  = np.array([by_type[k]["avg_terminal_reward"]    for k in type_keys])
    step_rewards  = np.array([by_type[k]["avg_step_reward"]        for k in type_keys])
    success_rates = np.array([by_type[k]["success_rate"]           for k in type_keys])
    budget_util   = np.array([by_type[k]["avg_budget_utilization"] for k in type_keys])

    plt.style.use("seaborn-v0_8-whitegrid")
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(12.8, 8.2), dpi=220,
        sharex=True,
        gridspec_kw=dict(left=0.09, right=0.97, top=0.87, bottom=0.10,
                         hspace=0.42),
    )

    # ── Top panel: reward trends ──────────────────────────────────────────────
    l1, = ax1.plot(x, avg_returns,  marker="o", lw=2.4, ms=7, color="#1f77b4",
                   label="Avg return / episode")
    l2, = ax1.plot(x, terminal_rew, marker="s", lw=2.1, ms=6, color="#ff7f0e",
                   linestyle="--", label="Avg terminal reward")
    l3, = ax1.plot(x, step_rewards, marker="^", lw=2.1, ms=6, color="#2ca02c",
                   linestyle=":",  label="Avg step reward")

    ax1.set_ylabel("Reward-scale metrics")
    ax1.set_ylim(0.42, max(float(avg_returns.max()) + 0.09, 1.56))
    ax1.set_title("(A) Reward trends by task family", pad=8)

    # Stagger annotations: return above, terminal below, step above (offset right)
    for i, v in enumerate(avg_returns):
        ax1.annotate(f"{v:.3f}", (x[i], v), xytext=(0, 9),
                     textcoords="offset points", ha="center", fontsize=8,
                     color="#1f77b4", fontweight="bold",
                     path_effects=_stroke())
    for i, v in enumerate(terminal_rew):
        ax1.annotate(f"{v:.3f}", (x[i], v), xytext=(0, -14),
                     textcoords="offset points", ha="center", fontsize=8,
                     color="#ff7f0e", fontweight="bold",
                     path_effects=_stroke())
    for i, v in enumerate(step_rewards):
        ax1.annotate(f"{v:.3f}", (x[i], v), xytext=(14, 4),
                     textcoords="offset points", ha="left", fontsize=8,
                     color="#2ca02c", fontweight="bold",
                     path_effects=_stroke())

    # ── Bottom panel: efficiency trends ──────────────────────────────────────
    l4, = ax2.plot(x, success_rates, marker="D", lw=2.1, ms=6, color="#9467bd",
                   label="Success rate (%)")
    l5, = ax2.plot(x, budget_util,   marker="P", lw=2.1, ms=6, color="#8c564b",
                   label="Budget utilization (%)")

    ax2.set_ylabel("Efficiency metrics (%)")
    ax2.set_ylim(20.0, 108.0)
    ax2.set_title("(B) Efficiency trends by task family", pad=8)
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, rotation=15)
    ax2.set_xlabel("Task family")

    for i, v in enumerate(budget_util):
        ax2.annotate(f"{v:.1f}%", (x[i], v), xytext=(0, 9),
                     textcoords="offset points", ha="center", fontsize=8,
                     color="#8c564b", fontweight="bold",
                     path_effects=_stroke())

    # ── Shared legend — above both panels, no overlap ─────────────────────────
    fig.legend(
        [l1, l2, l3, l4, l5],
        [h.get_label() for h in [l1, l2, l3, l4, l5]],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.985),
        ncol=5,
        frameon=True,
        framealpha=0.95,
        edgecolor="#cccccc",
        fontsize=8.5,
        handlelength=1.8,
        borderpad=0.5,
        columnspacing=1.2,
    )

    fig.suptitle(
        "ITSM OpenEnv — task-family profile (line charts with markers)",
        fontsize=13, fontweight="bold", y=1.02,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


# ─────────────────────────────────────────────────────────────────────────────
#  main()
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate research-style benchmark metrics visualization."
    )
    parser.add_argument("--tasks",       type=Path, default=Path("tasks.jsonl"))
    parser.add_argument("--log",         type=Path, default=Path("full_run.log"))
    parser.add_argument("--out",         type=Path, default=Path("assets/metrics.png"))
    parser.add_argument("--line-out",    type=Path, default=Path("assets/metrics_line.png"))
    parser.add_argument("--summary-out", type=Path, default=Path("assets/metrics_summary.json"))
    args = parser.parse_args()

    task_manifest = load_task_manifest(args.tasks)
    episodes      = parse_run_log(args.log, task_manifest)
    if not episodes:
        raise RuntimeError("No episodes parsed. Check --log path.")

    summary = build_summary(episodes)
    plot(summary, args.out)
    plot_line_with_markers(summary, args.line_out)

    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Saved figure    → {args.out}")
    print(f"Saved line chart → {args.line_out}")
    print(f"Saved summary   → {args.summary_out}")


if __name__ == "__main__":
    main()