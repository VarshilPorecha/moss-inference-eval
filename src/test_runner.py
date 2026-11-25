"""Selective test runner allowing individual dashboard test IDs to be re-run on demand."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from moss.inference import InferenceError

from src.common import (
    DEMO_LOG,
    INFERENCE_LOG,
    TASKS_LOG,
    append_jsonl,
    extract_response_summary,
    extract_task_summary,
    load_config,
    make_inference_client,
)
from src.eval_inference import (
    ABSTENTION_CASES,
    GROUNDED_CASES,
    GROUNDING_INSTRUCTIONS,
    _check_keywords,
    _looks_like_abstention,
    check_index_preflight,
    run_streaming_and_cache_tests,
)
from src.eval_tasks import (
    _run_single_case,
    _tier1_cases,
    _tier2_cases,
    _tier3_cases,
    _tier4_breakit_cases,
    run_parallel_probe,
)


async def _rerun_single_grounded(client: Any, case: dict[str, Any], cfg: dict[str, str], secrets: list[str]) -> None:
    index_name = cfg["index_name"]
    t0 = time.perf_counter()
    ungrounded = await client.responses.create(
        model="moss",
        instructions=GROUNDING_INSTRUCTIONS,
        input=case["prompt"],
        retrieve=False,
        cache=False,
    )
    ungrounded_ms = (time.perf_counter() - t0) * 1000.0
    ug_ok, ug_missing = _check_keywords(
        ungrounded.output_text, case["expected_all"], case["expected_any"]
    )

    t1 = time.perf_counter()
    grounded = await client.responses.create(
        model="moss",
        instructions=GROUNDING_INSTRUCTIONS,
        input=case["prompt"],
        indexes=[index_name],
        retrieve=True,
        cache=False,
    )
    grounded_ms = (time.perf_counter() - t1) * 1000.0
    g_ok, g_missing = _check_keywords(
        grounded.output_text, case["expected_all"], case["expected_any"]
    )

    append_jsonl(
        INFERENCE_LOG,
        {
            "test_group": "rag_grounding",
            "case_id": case["id"],
            "prompt": case["prompt"],
            "ungrounded_ms": round(ungrounded_ms, 2),
            "ungrounded_matched": ug_ok,
            "ungrounded_missing": ug_missing,
            "ungrounded_summary": extract_response_summary(ungrounded),
            "grounded_ms": round(grounded_ms, 2),
            "latency_delta_ms": round(grounded_ms - ungrounded_ms, 2),
            "grounded_matched": g_ok,
            "grounded_missing": g_missing,
            "grounded_summary": extract_response_summary(grounded),
        },
        secrets,
    )


async def _rerun_single_abstention(client: Any, case: dict[str, Any], cfg: dict[str, str], secrets: list[str]) -> None:
    t0 = time.perf_counter()
    resp = await client.responses.create(
        model="moss",
        instructions=GROUNDING_INSTRUCTIONS,
        input=case["prompt"],
        indexes=[cfg["index_name"]],
        retrieve=True,
        cache=False,
    )
    total_ms = (time.perf_counter() - t0) * 1000.0
    append_jsonl(
        INFERENCE_LOG,
        {
            "test_group": "abstention",
            "case_id": case["id"],
            "prompt": case["prompt"],
            "total_ms": round(total_ms, 2),
            "abstained": _looks_like_abstention(resp.output_text),
            **extract_response_summary(resp),
        },
        secrets,
    )


async def _rerun_error_probe(client: Any, probe_id: str, cfg: dict[str, str], secrets: list[str]) -> None:
    if probe_id == "invalid_key":
        bad_client = make_inference_client(
            {**cfg, "project_key": "moss_invalid_key_000000000000"}, max_retries=0
        )
        async with bad_client:
            try:
                await bad_client.responses.create(model="moss", input="Hello")
            except InferenceError as exc:
                append_jsonl(
                    INFERENCE_LOG,
                    {
                        "test_group": "error_probe",
                        "probe_id": "invalid_key",
                        "raised": True,
                        "error_type": exc.type,
                        "status": exc.status,
                        "code": exc.code,
                        "message": exc.message,
                    },
                    secrets,
                )
        return

    probes = {
        "nonexistent_index": {"model": "moss", "input": "Hello", "indexes": ["index-does-not-exist-999"]},
        "empty_input": {"model": "moss", "input": ""},
        "invalid_model_no_byok": {"model": "gpt-4o-mini", "input": "Hello"},
    }
    kwargs = probes[probe_id]
    try:
        resp = await client.responses.create(**kwargs, cache=False)
        append_jsonl(
            INFERENCE_LOG,
            {
                "test_group": "error_probe",
                "probe_id": probe_id,
                "raised": False,
                **extract_response_summary(resp),
            },
            secrets,
        )
    except InferenceError as exc:
        append_jsonl(
            INFERENCE_LOG,
            {
                "test_group": "error_probe",
                "probe_id": probe_id,
                "raised": True,
                "error_type": exc.type,
                "status": exc.status,
                "code": exc.code,
                "request_id": exc.request_id,
                "message": exc.message,
            },
            secrets,
        )


async def run_selected_tests(test_ids: list[str]) -> list[dict[str, Any]]:
    """Run only the specified test IDs and return execution status per ID."""
    cfg = load_config()
    secrets = [cfg["project_id"], cfg["project_key"]]

    grounded_map = {c["id"]: c for c in GROUNDED_CASES}
    abst_map = {c["id"]: c for c in ABSTENTION_CASES}
    task_map = {
        c["case_id"]: c
        for c in (_tier1_cases() + _tier2_cases() + _tier3_cases() + _tier4_breakit_cases())
    }

    outcomes: list[dict[str, Any]] = []
    stream_or_cache_ran = False

    async with make_inference_client(cfg, timeout=180.0, idle_timeout=90.0) as client:
        for tid in test_ids:
            t0 = time.perf_counter()
            try:
                if tid == "INF-PREFLIGHT":
                    await check_index_preflight(cfg, secrets)
                elif tid in ("INF-STREAM", "INF-CACHE"):
                    if not stream_or_cache_ran:
                        await run_streaming_and_cache_tests(cfg, secrets)
                        stream_or_cache_ran = True
                elif tid in grounded_map:
                    await _rerun_single_grounded(client, grounded_map[tid], cfg, secrets)
                elif tid in abst_map:
                    await _rerun_single_abstention(client, abst_map[tid], cfg, secrets)
                elif tid == "INF-TOOL-CALL":
                    tools = [
                        {
                            "type": "function",
                            "name": "lookup_rma_status",
                            "description": "Look up the shipping status of a Kestrel RMA ticket.",
                            "parameters": {
                                "type": "object",
                                "properties": {"rma_id": {"type": "string"}},
                                "required": ["rma_id"],
                            },
                        }
                    ]
                    r = await client.responses.create(
                        model="moss",
                        input="Check the shipping status for RMA-KST-104829.",
                        tools=tools,
                        tool_choice="auto",
                        cache=False,
                    )
                    append_jsonl(
                        INFERENCE_LOG,
                        {
                            "test_group": "feature_tool_call",
                            "ok": True,
                            "total_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                            **extract_response_summary(r),
                        },
                        secrets,
                    )
                elif tid == "INF-MULTITURN":
                    turn1 = await client.responses.create(
                        model="moss",
                        instructions=GROUNDING_INSTRUCTIONS,
                        input="What is the standard return window in days?",
                        indexes=[cfg["index_name"]],
                        cache=False,
                    )
                    turn2_input = [
                        {"role": "user", "content": "What is the standard return window in days?"},
                        *[getattr(item, "raw", item) for item in turn1.output],
                        {"role": "user", "content": "How does that change for Enterprise accounts?"},
                    ]
                    turn2 = await client.responses.create(
                        model="moss",
                        instructions=GROUNDING_INSTRUCTIONS,
                        input=turn2_input,
                        indexes=[cfg["index_name"]],
                        cache=False,
                    )
                    append_jsonl(
                        INFERENCE_LOG,
                        {
                            "test_group": "feature_multiturn",
                            "ok": True,
                            "total_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                            "has_45": "45" in turn2.output_text,
                            **extract_response_summary(turn2),
                        },
                        secrets,
                    )
                elif tid.startswith("INF-ERR-"):
                    probe_id = tid.replace("INF-ERR-", "").lower()
                    await _rerun_error_probe(client, probe_id, cfg, secrets)
                elif tid == "INF-BURST-5":
                    async def _one(i: int) -> dict[str, Any]:
                        st = time.perf_counter()
                        r = await client.responses.create(
                            model="moss",
                            instructions=GROUNDING_INSTRUCTIONS,
                            input=f"Request {i}: What error code indicates insufficient PoE wattage?",
                            indexes=[cfg["index_name"]],
                            cache=False,
                        )
                        return {
                            "i": i,
                            "ok": "ERR-102-PWR" in r.output_text,
                            "ms": round((time.perf_counter() - st) * 1000.0, 2),
                        }

                    burst_res = await asyncio.gather(*(_one(i) for i in range(1, 6)))
                    append_jsonl(
                        INFERENCE_LOG,
                        {
                            "test_group": "async_burst_5",
                            "wall_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                            "results": burst_res,
                        },
                        secrets,
                    )
                elif tid in task_map:
                    await _run_single_case(client, task_map[tid], secrets)
                elif tid == "T4_cancel_lifecycle":
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
                    append_jsonl(
                        TASKS_LOG,
                        {
                            "test_group": "lifecycle_cancel",
                            "case_id": "T4_cancel_lifecycle",
                            "tier": 4,
                            "wall_seconds": round(time.perf_counter() - t0, 2),
                            "created_status": created.status,
                            "live_url_present": live_url_present,
                            "cancel_ack_status": cancel_ack.status,
                            "cancel_ack_requested": cancel_ack.cancel_requested,
                            **extract_task_summary(final_task),
                        },
                        secrets,
                    )
                elif tid == "T4_parallel_2":
                    await run_parallel_probe(client, secrets)
                elif tid == "T4_min_runtime_floor":
                    try:
                        await client.tasks.run(
                            goal="Check min runtime validation.",
                            environment={"type": "browser", "start_url": "https://example.com/"},
                            limits={"max_runtime_seconds": 45, "max_cost_usd": 0.10},
                        )
                    except InferenceError as exc:
                        append_jsonl(
                            TASKS_LOG,
                            {
                                "test_group": "task_run",
                                "case_id": "T4_min_runtime_floor",
                                "tier": 4,
                                "wall_seconds": round(time.perf_counter() - t0, 2),
                                "sdk_exception": True,
                                "error_type": exc.type,
                                "status": exc.status,
                                "code": exc.code,
                                "task_id": exc.task_id,
                                "message": exc.message,
                            },
                            secrets,
                        )
                elif tid == "DEMO-01":
                    import json as _json
                    d_t0 = time.perf_counter()
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
                    task_s = time.perf_counter() - d_t0
                    live_fact = task.result.output if task.result else {}
                    d_t1 = time.perf_counter()
                    resp = await client.responses.create(
                        model="moss",
                        instructions=(
                            "Combine the live observation in the prompt with exact facts from the retrieved "
                            "Kestrel Systems index. Be concise and accurate."
                        ),
                        input=(
                            f"Live SDK check from PyPI (`moss`): {_json.dumps(live_fact)}.\n\n"
                            "Using our Kestrel Systems internal knowledge base, write a concise 4-bullet "
                            "engineering & support readiness brief covering: "
                            "1) live moss package vs firmware v4.18.2-rc3, 2) TLS 1.0/1.1 deprecation deadline, "
                            "3) BUG-884 workaround, 4) escalation code for a 5+ room outage."
                        ),
                        indexes=[cfg["index_name"]],
                        cache=False,
                    )
                    inf_s = time.perf_counter() - d_t1
                    append_jsonl(
                        DEMO_LOG,
                        {
                            "task_seconds": round(task_s, 2),
                            "inference_seconds": round(inf_s, 2),
                            "task": extract_task_summary(task),
                            "inference": extract_response_summary(resp),
                        },
                        secrets,
                    )
                else:
                    outcomes.append({"id": tid, "ok": False, "error": f"Unknown runnable test id: {tid}"})
                    continue

                outcomes.append({"id": tid, "ok": True, "seconds": round(time.perf_counter() - t0, 2)})
            except Exception as exc:
                outcomes.append({"id": tid, "ok": False, "error": str(exc), "seconds": round(time.perf_counter() - t0, 2)})

    return outcomes
