"""Aggregate JSONL run logs into a concise Markdown summary report."""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from src.common import DEMO_LOG, INFERENCE_LOG, LOGS_DIR, TASKS_LOG


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(round((pct / 100.0) * (len(s) - 1)))))
    return s[idx]


def build_report() -> str:
    inf_rows = _read_jsonl(INFERENCE_LOG)
    task_rows = _read_jsonl(TASKS_LOG)
    demo_rows = _read_jsonl(DEMO_LOG)

    lines: list[str] = ["# Moss Inference Evaluation — Automated Summary\n"]

    # Inference section
    streams = [r for r in inf_rows if r.get("test_group") == "streaming_ttft"]
    ttfts = [r["ttft_ms"] for r in streams if r.get("ttft_ms") is not None]
    totals = [r["total_ms"] for r in streams if r.get("total_ms") is not None]
    parity_ok = sum(1 for r in streams if r.get("parity_ok"))

    caches = [r for r in inf_rows if r.get("test_group") == "cache_check"]
    rags = [r for r in inf_rows if r.get("test_group") == "rag_grounding"]
    g_pass = sum(1 for r in rags if r.get("grounded_matched"))
    ug_pass = sum(1 for r in rags if r.get("ungrounded_matched"))
    deltas = [r["latency_delta_ms"] for r in rags if r.get("latency_delta_ms") is not None]

    abst = [r for r in inf_rows if r.get("test_group") == "abstention"]
    abst_ok = sum(1 for r in abst if r.get("abstained"))

    lines.append("## 1. Inference API Metrics\n")
    lines.append("| Metric | Result |")
    lines.append("| :--- | :--- |")
    if ttfts:
        lines.append(
            f"| Streaming TTFT (uncached, n={len(ttfts)}) | p50={statistics.median(ttfts):.1f} ms, p95={_percentile(ttfts, 95):.1f} ms |"
        )
        lines.append(
            f"| Streaming Total Latency (n={len(totals)}) | p50={statistics.median(totals):.1f} ms, p95={_percentile(totals, 95):.1f} ms |"
        )
        lines.append(f"| Stream vs. Final Text Parity | {parity_ok}/{len(streams)} |")
    if len(caches) >= 2:
        lines.append(
            f"| Cache Check (pass 1 vs. pass 2) | {caches[0].get('total_ms')} ms -> {caches[1].get('total_ms')} ms |"
        )
    if rags:
        lines.append(f"| Synthetic KB Grounding Accuracy | {g_pass}/{len(rags)} (vs. {ug_pass}/{len(rags)} ungrounded) |")
        lines.append(
            f"| Grounding Latency Delta (median) | {statistics.median(deltas):+.1f} ms |"
        )
    if abst:
        lines.append(f"| Missing-Fact Abstention Rate | {abst_ok}/{len(abst)} |")

    # Error probes
    err_probes = [r for r in inf_rows if r.get("test_group") == "error_probe"]
    if err_probes:
        lines.append("\n### Inference Error & Edge Probes\n")
        for p in err_probes:
            lines.append(
                f"- `{p.get('probe_id')}`: raised={p.get('raised')} "
                f"status={p.get('status')} type={p.get('error_type')} msg={p.get('message')}"
            )

    # Tasks section
    runs = [r for r in task_rows if r.get("test_group") == "task_run"]
    lines.append("\n## 2. Tasks API Metrics\n")
    if runs:
        direct_cost = sum(
            (r.get("usage") or {}).get("cost_usd") or 0.0 for r in task_rows
        )
        parallel_cost = sum(
            item.get("cost_usd") or 0.0
            for r in task_rows
            if r.get("test_group") == "parallel_tasks"
            for item in r.get("results", [])
        )
        total_cost = direct_cost + parallel_cost
        lines.append(f"**Total Logged Tasks Spend (model_usd):** ${total_cost:.4f}\n")
        lines.append("| Case ID | Tier | Status | Wall (s) | Cost ($) | GW Verif | Local Schema | Error |")
        lines.append("| :--- | :---: | :--- | :---: | :---: | :---: | :---: | :--- |")
        for r in runs:
            cost = (r.get("usage") or {}).get("cost_usd")
            cost_str = f"{cost:.4f}" if isinstance(cost, (int, float)) else "-"
            gw = (r.get("verification") or {}).get("passed")
            err = (r.get("error") or {}).get("code") or r.get("error_type") or "-"
            lines.append(
                f"| `{r.get('case_id')}` | {r.get('tier')} | {r.get('status')} | "
                f"{r.get('wall_seconds')} | {cost_str} | {gw} | {r.get('local_schema_valid')} | {err} |"
            )

    lifecycles = [r for r in task_rows if r.get("test_group") in ("lifecycle_cancel", "parallel_tasks")]
    if lifecycles:
        lines.append("\n### Tasks Lifecycle & Parallel Probes\n")
        for r in lifecycles:
            lines.append(f"- `{r.get('case_id')}`: {json.dumps(r, default=str)[:260]}")

    if demo_rows:
        d = demo_rows[-1]
        lines.append("\n## 3. Combined Demo Run\n")
        lines.append(
            f"- Tasks duration: {d.get('task_seconds')}s | Inference duration: {d.get('inference_seconds')}s"
        )

    return "\n".join(lines) + "\n"


def main() -> None:
    report = build_report()
    out_path = LOGS_DIR / "summary_report.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"Saved report to {out_path}")


if __name__ == "__main__":
    main()
