"""Mini Showcase App: Combine Tasks API (live web extraction) + Moss Index + Inference API (grounded Q&A)."""

from __future__ import annotations

import asyncio
import json
import time

from rich.console import Console

from src.common import (
    DEMO_LOG,
    append_jsonl,
    extract_response_summary,
    extract_task_summary,
    load_config,
    make_inference_client,
)

console = Console()


async def main() -> None:
    cfg = load_config()
    secrets = [cfg["project_id"], cfg["project_key"]]
    index_name = cfg["index_name"]

    console.rule("[bold magenta]Demo: Kestrel SDK & Policy Release Readiness Agent")
    async with make_inference_client(cfg, timeout=150.0) as client:
        # 1. Tasks API gathers live PyPI metadata for `moss`
        t0 = time.perf_counter()
        task = await client.tasks.run(
            goal=(
                "Inspect the PyPI page for 'moss' and extract the latest version, "
                "minimum Python requirement, and a 1-sentence summary of the package."
            ),
            environment={"type": "browser", "start_url": "https://pypi.org/project/moss/"},
            limits={"max_runtime_seconds": 75, "max_cost_usd": 0.25},
            effort="low",
            output_schema={
                "type": "object",
                "properties": {
                    "latest_version": {"type": "string"},
                    "requires_python": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["latest_version", "requires_python", "summary"],
            },
        )
        task_s = time.perf_counter() - t0
        live_fact = task.result.output if task.result else {}
        console.print(f"[cyan]Tasks API live observation ({task_s:.1f}s):[/cyan] {live_fact}")

        # 2. Inference API combines live Tasks observation + Moss Knowledge Base index
        prompt = (
            f"Live SDK check from PyPI (`moss`): {json.dumps(live_fact)}.\n\n"
            "Using our Kestrel Systems internal knowledge base, write a concise 4-bullet "
            "engineering & support readiness brief covering:\n"
            "1. The live `moss` package version vs. our Kestrel firmware v4.18.2-rc3 release notes.\n"
            "2. Upcoming TLS 1.0/1.1 deprecation deadline.\n"
            "3. Known macOS Sequoia bug (BUG-884) and workaround.\n"
            "4. Which escalation code applies if a customer hits an outage across 5+ rooms."
        )
        t1 = time.perf_counter()
        stream = await client.responses.create(
            model="moss",
            instructions=(
                "Combine the live observation in the prompt with exact facts from the retrieved "
                "Kestrel Systems index. Be concise and accurate."
            ),
            input=prompt,
            indexes=[index_name],
            cache=False,
            stream=True,
        )
        console.print("\n[bold green]Grounded Streaming Readiness Brief:[/bold green]")
        async with stream:
            async for ev in stream:
                if ev.delta:
                    print(ev.delta, end="", flush=True)
            final_resp = await stream.get_final_response()
        print("\n")
        inf_s = time.perf_counter() - t1

        append_jsonl(
            DEMO_LOG,
            {
                "task_seconds": round(task_s, 2),
                "inference_seconds": round(inf_s, 2),
                "task": extract_task_summary(task),
                "inference": extract_response_summary(final_resp),
            },
            secrets,
        )
        console.print(
            f"[dim]Demo finished: Tasks={task_s:.1f}s (${task.usage.cost_usd if task.usage else '?'}), "
            f"Inference={inf_s:.1f}s[/dim]"
        )


if __name__ == "__main__":
    asyncio.run(main())
