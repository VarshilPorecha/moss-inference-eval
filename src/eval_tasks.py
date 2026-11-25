"""Tasks API tiered benchmark and adversarial 'break-it' suite."""

from __future__ import annotations

import argparse
import asyncio
import time
from typing import Any

from moss.inference import InferenceError
from rich.console import Console

from src.common import (
    TASKS_LOG,
    append_jsonl,
    extract_task_summary,
    load_config,
    make_inference_client,
    validate_schema,
)

console = Console()


def _tier1_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "T1_books_top5",
            "tier": 1,
            "goal": (
                "Extract the first 5 books shown on the page. For each book return its exact "
                "title, numeric price in GBP (without the pound symbol), and whether it is in stock."
            ),
            "environment": {"type": "browser", "start_url": "https://books.toscrape.com/"},
            "limits": {"max_runtime_seconds": 90, "max_cost_usd": 0.25},
            "effort": "low",
            "output_schema": {
                "type": "object",
                "properties": {
                    "books": {
                        "type": "array",
                        "minItems": 5,
                        "maxItems": 5,
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "price_gbp": {"type": "number"},
                                "in_stock": {"type": "boolean"},
                            },
                            "required": ["title", "price_gbp", "in_stock"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["books"],
                "additionalProperties": False,
            },
        },
        {
            "case_id": "T1_quotes_top5",
            "tier": 1,
            "goal": (
                "Extract the first 5 quotes visible on the page with each quote's exact text, "
                "author name, and list of tags."
            ),
            "environment": {"type": "browser", "start_url": "https://quotes.toscrape.com/"},
            "limits": {"max_runtime_seconds": 90, "max_cost_usd": 0.25},
            "effort": "low",
            "output_schema": {
                "type": "object",
                "properties": {
                    "quotes": {
                        "type": "array",
                        "minItems": 5,
                        "maxItems": 5,
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "author": {"type": "string"},
                                "tags": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["text", "author", "tags"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["quotes"],
                "additionalProperties": False,
            },
        },
    ]


def _tier2_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "T2_books_science_extremes",
            "tier": 2,
            "goal": (
                "Navigate to the 'Science' category in the left sidebar. Inspect all books in Science "
                "and return the cheapest book, the most expensive book, and the total number of books listed in Science."
            ),
            "environment": {"type": "browser", "start_url": "https://books.toscrape.com/"},
            "limits": {"max_runtime_seconds": 120, "max_cost_usd": 0.35},
            "effort": "medium",
            "output_schema": {
                "type": "object",
                "properties": {
                    "total_books_in_category": {"type": "integer"},
                    "cheapest": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "price_gbp": {"type": "number"},
                        },
                        "required": ["title", "price_gbp"],
                    },
                    "most_expensive": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "price_gbp": {"type": "number"},
                        },
                        "required": ["title", "price_gbp"],
                    },
                },
                "required": ["total_books_in_category", "cheapest", "most_expensive"],
            },
        },
        {
            "case_id": "T2_quotes_page2_life",
            "tier": 2,
            "goal": (
                "Click 'Next' to go to page 2 of quotes.toscrape.com. Find all quotes on page 2 "
                "that have the tag 'life' and return their authors and quote text."
            ),
            "environment": {"type": "browser", "start_url": "https://quotes.toscrape.com/"},
            "limits": {"max_runtime_seconds": 120, "max_cost_usd": 0.35},
            "effort": "medium",
            "output_schema": {
                "type": "object",
                "properties": {
                    "page_number": {"type": "integer"},
                    "matching_quotes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "author": {"type": "string"},
                                "text": {"type": "string"},
                            },
                            "required": ["author", "text"],
                        },
                    },
                },
                "required": ["page_number", "matching_quotes"],
            },
        },
    ]


def _tier3_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "T3_js_rendered_quotes",
            "tier": 3,
            "goal": (
                "Wait for the JavaScript-rendered quotes to load on the page, then extract the first 3 "
                "quotes (author and text)."
            ),
            "environment": {"type": "browser", "start_url": "https://quotes.toscrape.com/js/"},
            "limits": {"max_runtime_seconds": 90, "max_cost_usd": 0.25},
            "effort": "low",
            "output_schema": {
                "type": "object",
                "properties": {
                    "quotes": {
                        "type": "array",
                        "minItems": 3,
                        "maxItems": 3,
                        "items": {
                            "type": "object",
                            "properties": {
                                "author": {"type": "string"},
                                "text": {"type": "string"},
                            },
                            "required": ["author", "text"],
                        },
                    }
                },
                "required": ["quotes"],
            },
        },
        {
            "case_id": "T3_pypi_moss_metadata",
            "tier": 3,
            "goal": (
                "Read the PyPI project page for 'moss' and extract the latest version string, "
                "release date, and required Python version."
            ),
            "environment": {"type": "browser", "start_url": "https://pypi.org/project/moss/"},
            "limits": {"max_runtime_seconds": 90, "max_cost_usd": 0.30},
            "effort": "medium",
            "output_schema": {
                "type": "object",
                "properties": {
                    "package_name": {"type": "string"},
                    "latest_version": {"type": "string"},
                    "release_date": {"type": "string"},
                    "requires_python": {"type": "string"},
                },
                "required": ["package_name", "latest_version", "requires_python"],
            },
        },
    ]


def _tier4_breakit_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "T4_impossible_price_goal",
            "tier": 4,
            "goal": (
                "Find a book on this website priced strictly under 1.00 GBP and return its title and price. "
                "If no book under 1.00 GBP exists anywhere on the site, do not fabricate one."
            ),
            "environment": {"type": "browser", "start_url": "https://books.toscrape.com/"},
            "limits": {"max_runtime_seconds": 60, "max_cost_usd": 0.20},
            "effort": "low",
            "output_schema": {
                "type": "object",
                "properties": {
                    "found": {"type": "boolean"},
                    "title": {"type": ["string", "null"]},
                    "price_gbp": {"type": ["number", "null"]},
                },
                "required": ["found"],
            },
        },
        {
            "case_id": "T4_missing_required_isbn",
            "tier": 4,
            "goal": (
                "Open the first book 'A Light in the Attic' and extract its ISBN-13 code. "
                "Do not guess or fabricate an ISBN if it is not shown on the page."
            ),
            "environment": {"type": "browser", "start_url": "https://books.toscrape.com/"},
            "limits": {"max_runtime_seconds": 75, "max_cost_usd": 0.25},
            "effort": "low",
            "output_schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "isbn_13": {"type": "string", "pattern": "^[0-9]{13}$"},
                },
                "required": ["title", "isbn_13"],
            },
        },
        {
            "case_id": "T4_strict_nested_enum",
            "tier": 4,
            "goal": (
                "Extract the first 2 books on the page including exact title, star rating integer (1 to 5), "
                "and stock status ('In Stock' or 'Out of Stock')."
            ),
            "environment": {"type": "browser", "start_url": "https://books.toscrape.com/"},
            "limits": {"max_runtime_seconds": 75, "max_cost_usd": 0.25},
            "effort": "low",
            "output_schema": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": 2,
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "rating": {"type": "integer", "minimum": 1, "maximum": 5},
                                "pricing": {
                                    "type": "object",
                                    "properties": {
                                        "amount": {"type": "number", "minimum": 0.01},
                                        "currency": {"type": "string", "enum": ["GBP"]},
                                    },
                                    "required": ["amount", "currency"],
                                },
                                "stock_status": {
                                    "type": "string",
                                    "enum": ["In Stock", "Out of Stock"],
                                },
                            },
                            "required": ["title", "rating", "pricing", "stock_status"],
                        },
                    }
                },
                "required": ["items"],
            },
        },
        {
            "case_id": "T4_broken_404_url",
            "tier": 4,
            "goal": "Read the main heading and first paragraph from the page.",
            "environment": {
                "type": "browser",
                "start_url": "https://books.toscrape.com/nonexistent-page-404-test",
            },
            "limits": {"max_runtime_seconds": 60, "max_cost_usd": 0.15},
            "effort": "low",
            "output_schema": {
                "type": "object",
                "properties": {"heading": {"type": "string"}},
                "required": ["heading"],
            },
        },
        {
            "case_id": "T4_non_html_json_url",
            "tier": 4,
            "goal": "Extract the slideshow title and author from the page.",
            "environment": {"type": "browser", "start_url": "https://httpbin.org/json"},
            "limits": {"max_runtime_seconds": 60, "max_cost_usd": 0.15},
            "effort": "low",
            "output_schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "author": {"type": "string"},
                },
                "required": ["title", "author"],
            },
        },
        {
            "case_id": "T4_budget_limit_probe",
            "tier": 4,
            "goal": (
                "Visit all 50 pages of books.toscrape.com and list every single book title and price."
            ),
            "environment": {"type": "browser", "start_url": "https://books.toscrape.com/"},
            "limits": {"max_runtime_seconds": 60, "max_cost_usd": 0.02},
            "effort": "medium",
            "output_schema": {
                "type": "object",
                "properties": {"total_count": {"type": "integer"}},
                "required": ["total_count"],
            },
        },
    ]


async def _run_single_case(client: Any, case: dict[str, Any], secrets: list[str]) -> None:
    case_id = case["case_id"]
    console.print(f"  Running [bold]{case_id}[/bold] (tier={case['tier']})...")
    t0 = time.perf_counter()
    try:
        task = await client.tasks.run(
            goal=case["goal"],
            environment=case["environment"],
            output_schema=case["output_schema"],
            limits=case["limits"],
            effort=case.get("effort"),
            metadata={"case_id": case_id, "tier": case["tier"]},
            timeout=case["limits"]["max_runtime_seconds"] + 30,
        )
        wall_s = time.perf_counter() - t0
        summary = extract_task_summary(task)
        local_valid, local_errors = validate_schema(
            task.result.output if task.result else None, case["output_schema"]
        )

        trace_steps = None
        trace_keys = None
        file_paths: list[str] = []
        if task.trace_available:
            try:
                trace = await client.tasks.trace(task.id)
                if isinstance(trace, list):
                    trace_steps = len(trace)
                elif isinstance(trace, dict):
                    trace_keys = list(trace.keys())
                    raw_steps = trace.get("steps")
                    if isinstance(raw_steps, int):
                        trace_steps = raw_steps
                    elif isinstance(raw_steps, list):
                        trace_steps = len(raw_steps)
                    elif isinstance(trace.get("events"), list):
                        trace_steps = len(trace["events"])
            except InferenceError:
                pass
        try:
            files = await client.tasks.files.list(task.id)
            file_paths = [f.path for f in files.data]
        except InferenceError:
            pass

        append_jsonl(
            TASKS_LOG,
            {
                "test_group": "task_run",
                "case_id": case_id,
                "tier": case["tier"],
                "wall_seconds": round(wall_s, 2),
                "local_schema_valid": local_valid,
                "local_schema_errors": local_errors,
                "trace_steps": trace_steps,
                "trace_keys": trace_keys,
                "file_count": len(file_paths),
                "files_sample": file_paths[:5],
                **summary,
            },
            secrets,
        )
        cost = task.usage.cost_usd if task.usage else None
        console.print(
            f"    -> status={task.status} | wall={wall_s:.1f}s | cost=${cost} | "
            f"gw_verif={task.verification.passed if task.verification else None} | "
            f"local_valid={local_valid} | files={len(file_paths)}"
        )
        if task.error:
            console.print(f"    -> error: [{task.error.code}] {task.error.message}")
    except InferenceError as exc:
        wall_s = time.perf_counter() - t0
        append_jsonl(
            TASKS_LOG,
            {
                "test_group": "task_run",
                "case_id": case_id,
                "tier": case["tier"],
                "wall_seconds": round(wall_s, 2),
                "sdk_exception": True,
                "error_type": exc.type,
                "status": exc.status,
                "code": exc.code,
                "task_id": exc.task_id,
                "message": exc.message,
            },
            secrets,
        )
        console.print(f"    -> InferenceError ({exc.type}, task_id={exc.task_id}): {exc.message}")


async def run_parallel_probe(client: Any, secrets: list[str]) -> None:
    """Run 2 lightweight tasks concurrently via asyncio.gather."""
    console.print("  Running [bold]T4_parallel_2[/bold]...")
    t1 = time.perf_counter()

    async def _mini(idx: int) -> dict[str, Any]:
        st = time.perf_counter()
        try:
            t = await client.tasks.run(
                goal=f"Return the main heading text of the page (parallel probe {idx}).",
                environment={"type": "browser", "start_url": "https://example.com/"},
                limits={"max_runtime_seconds": 60, "max_cost_usd": 0.10},
                output_schema={
                    "type": "object",
                    "properties": {"heading": {"type": "string"}},
                    "required": ["heading"],
                },
                timeout=90,
            )
            return {
                "idx": idx,
                "status": t.status,
                "wall_s": round(time.perf_counter() - st, 2),
                "cost_usd": t.usage.cost_usd if t.usage else None,
            }
        except InferenceError as exc:
            return {"idx": idx, "error": exc.message, "type": exc.type, "status": exc.status}

    par_res = await asyncio.gather(_mini(1), _mini(2))
    append_jsonl(
        TASKS_LOG,
        {
            "test_group": "parallel_tasks",
            "case_id": "T4_parallel_2",
            "tier": 4,
            "wall_seconds": round(time.perf_counter() - t1, 2),
            "results": par_res,
        },
        secrets,
    )
    console.print(f"    -> parallel_2 results={par_res}")


async def run_lifecycle_and_parallel_probes(client: Any, secrets: list[str]) -> None:
    """Test async create + live_view + cancel lifecycle, plus 2 parallel tasks."""
    console.print("  Running [bold]T4_cancel_lifecycle[/bold]...")
    t0 = time.perf_counter()
    created = await client.tasks.create(
        goal="Browse through every category of books and compile a full catalog.",
        environment={
            "type": "browser",
            "start_url": "https://books.toscrape.com/",
            "live_view": True,
        },
        limits={"max_runtime_seconds": 90, "max_cost_usd": 0.20},
    )
    live_url_present = bool(created.live_url)
    await asyncio.sleep(3.0)
    cancel_ack = await client.tasks.cancel(created.id)
    final_task = await client.tasks.wait(created.id, timeout=45)
    wall_s = time.perf_counter() - t0
    append_jsonl(
        TASKS_LOG,
        {
            "test_group": "lifecycle_cancel",
            "case_id": "T4_cancel_lifecycle",
            "tier": 4,
            "wall_seconds": round(wall_s, 2),
            "created_status": created.status,
            "live_url_present": live_url_present,
            "cancel_ack_status": cancel_ack.status,
            "cancel_ack_requested": cancel_ack.cancel_requested,
            **extract_task_summary(final_task),
        },
        secrets,
    )
    console.print(
        f"    -> live_url={live_url_present}, ack={cancel_ack.status} (cancel_req={cancel_ack.cancel_requested}), "
        f"final={final_task.status}, cost=${final_task.usage.cost_usd if final_task.usage else None}"
    )

    await run_parallel_probe(client, secrets)


async def main(tier_arg: str) -> None:
    cfg = load_config()
    secrets = [cfg["project_id"], cfg["project_key"]]

    t4_all = _tier4_breakit_cases()
    cases_by_tier = {
        "1": _tier1_cases(),
        "2": _tier2_cases(),
        "3": _tier3_cases(),
        "4": t4_all,
        "4b": [
            c
            for c in t4_all
            if c["case_id"]
            in {"T4_broken_404_url", "T4_non_html_json_url", "T4_budget_limit_probe"}
        ],
    }

    selected_tiers = ["1", "2", "3", "4"] if tier_arg == "all" else [tier_arg]
    async with make_inference_client(cfg, timeout=180.0, idle_timeout=90.0) as client:
        for t in selected_tiers:
            console.rule(f"[bold cyan]Tasks API — Tier {t}")
            for case in cases_by_tier[t]:
                await _run_single_case(client, case, secrets)
            if t == "4":
                await run_lifecycle_and_parallel_probes(client, secrets)
            elif t == "4b":
                await run_parallel_probe(client, secrets)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Moss Tasks API benchmark suite.")
    parser.add_argument("--tier", choices=["1", "2", "3", "4", "4b", "all"], default="all")
    args = parser.parse_args()
    asyncio.run(main(args.tier))
