"""Inference API evaluation suite: latency/TTFT, streaming parity, RAG grounding, errors, and burst."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from moss.inference import InferenceError
from rich.console import Console
from rich.table import Table

from src.common import (
    INFERENCE_LOG,
    append_jsonl,
    extract_response_summary,
    load_config,
    make_inference_client,
    make_moss_client,
)

console = Console()

GROUNDED_CASES = [
    {
        "id": "G1_standard_return",
        "prompt": "What is the standard hardware return window and the opened-box restocking fee at Kestrel Systems?",
        "expected_any": ["19"],
        "expected_all": ["12.5"],
    },
    {
        "id": "G2_duplicate_charge",
        "prompt": "How should Kestrel support handle a customer reporting a duplicate charge on the same order?",
        "expected_any": ["15-minute", "15 minute"],
        "expected_all": ["3 to 5", "12.5%"],
    },
    {
        "id": "G3_err_419_sync_and_reset",
        "prompt": "What causes ERR-419-SYNC, how do you fix it, and how many seconds do you hold Mute and Pair for a hard factory reset?",
        "expected_any": ["5 GHz", "5GHz"],
        "expected_all": ["11"],
    },
    {
        "id": "G4_sku_pricing_and_hold",
        "prompt": "What is the SKU, MSRP, and advance replacement authorization hold for the Kestrel Hub Pro?",
        "expected_any": ["SKU-KHP-900"],
        "expected_all": ["349", "149"],
    },
    {
        "id": "G5_enterprise_sla",
        "prompt": "For Kestrel Enterprise accounts, what is the P1 engineering response SLA, extended return window, and VIP escalation code?",
        "expected_any": ["47"],
        "expected_all": ["45", "ESC-KST-ENT1"],
    },
    {
        "id": "G6_holiday_precedence",
        "prompt": "If a retail customer bought hardware on November 15, 2026, what is their return deadline?",
        "expected_any": ["January 22, 2027", "Jan 22, 2027"],
        "expected_all": ["2027"],
    },
    {
        "id": "G7_voice_escalation_codes",
        "prompt": "What escalation code is used for a refund over $500, and what code is used if a caller mentions a chargeback?",
        "expected_any": ["ESC-KST-409"],
        "expected_all": ["ESC-KST-911"],
    },
    {
        "id": "G8_firmware_tls_and_bug",
        "prompt": "When is TLS 1.1 permanently disabled on kestrelcloud.net, and what is known issue BUG-884?",
        "expected_any": ["December 15, 2026", "Dec 15, 2026"],
        "expected_all": ["Sequoia"],
    },
]

ABSTENTION_CASES = [
    {
        "id": "A1_crypto_payments",
        "prompt": "Does Kestrel Systems accept Bitcoin or Solana for Cloud Voice Pro annual subscriptions? Only answer using retrieved policy documents.",
    },
    {
        "id": "A2_unreleased_hardware",
        "prompt": "What is the price and battery life of the Kestrel Ultra 2027 headset? Only answer using retrieved policy documents.",
    },
    {
        "id": "A3_tokyo_office",
        "prompt": "What is the exact street address of Kestrel Systems' Tokyo fulfillment hub? Only answer using retrieved policy documents.",
    },
]

GROUNDING_INSTRUCTIONS = (
    "You are a precise Kestrel Systems support assistant. Answer strictly from the retrieved "
    "documents. Quote exact numbers, dates, SKUs, and codes. If the answer is not in the "
    "retrieved documents, explicitly say you do not have that information."
)


def _check_keywords(text: str, expected_all: list[str], expected_any: list[str]) -> tuple[bool, list[str]]:
    lower = text.lower()
    missing = [k for k in expected_all if k.lower() not in lower]
    if expected_any and not any(k.lower() in lower for k in expected_any):
        missing.append(f"any_of({expected_any})")
    return len(missing) == 0, missing


def _looks_like_abstention(text: str) -> bool:
    lower = text.lower()
    cues = [
        "do not have",
        "don't have",
        "not mentioned",
        "not specified",
        "no information",
        "cannot find",
        "can't find",
        "not in the",
        "not provided",
        "no mention",
        "unable to verify",
        "doesn't mention",
        "does not mention",
    ]
    return any(c in lower for c in cues)


async def check_index_preflight(cfg: dict[str, str], secrets: list[str]) -> bool:
    """Verify the target Moss index exists and measure direct MossClient retrieval latency."""
    index_name = cfg["index_name"]
    async with make_moss_client(cfg) as mc:
        indexes = await mc.list_indexes()
        names = [idx.name for idx in indexes]
        console.print(f"[cyan]Available Moss indexes:[/cyan] {names}")
        if index_name not in names:
            console.print(f"[red]Target index '{index_name}' not found![/red]")
            append_jsonl(
                INFERENCE_LOG,
                {"test_group": "preflight", "ok": False, "available_indexes": names},
                secrets,
            )
            return False

        t0 = time.perf_counter()
        info = await mc.get_index(index_name)
        await mc.load_index(index_name)
        load_ms = (time.perf_counter() - t0) * 1000.0

        t1 = time.perf_counter()
        qres = await mc.query(index_name, "What is the standard return window?")
        query_ms = (time.perf_counter() - t1) * 1000.0

        console.print(
            f"[green]Index '{index_name}' ready[/green] "
            f"(docs={info.doc_count}, status={info.status}, load={load_ms:.1f}ms, local_query={query_ms:.2f}ms)"
        )
        append_jsonl(
            INFERENCE_LOG,
            {
                "test_group": "preflight",
                "ok": True,
                "index_name": index_name,
                "doc_count": info.doc_count,
                "index_status": str(info.status),
                "load_ms": round(load_ms, 2),
                "direct_query_ms": round(query_ms, 2),
                "top_hit_score": qres.docs[0].score if qres.docs else None,
            },
            secrets,
        )
        return True


async def run_streaming_and_cache_tests(cfg: dict[str, str], secrets: list[str]) -> None:
    """Measure uncached TTFT/latency, streaming vs non-streaming parity, and cache hit behavior."""
    index_name = cfg["index_name"]
    prompt = "Summarize Kestrel Systems' standard return window and restocking fee in two sentences."

    async with make_inference_client(cfg) as client:
        # 5 uncached streaming runs for TTFT distribution
        for run_idx in range(1, 6):
            t0 = time.perf_counter()
            ttft_ms: float | None = None
            deltas: list[str] = []
            event_types: list[str] = []
            stream = await client.responses.create(
                model="moss",
                instructions=GROUNDING_INSTRUCTIONS,
                input=prompt,
                indexes=[index_name],
                cache=False,
                stream=True,
            )
            async with stream:
                async for ev in stream:
                    event_types.append(ev.type)
                    if ev.delta is not None:
                        if ttft_ms is None:
                            ttft_ms = (time.perf_counter() - t0) * 1000.0
                        deltas.append(ev.delta)
                final_resp = await stream.get_final_response()
            total_ms = (time.perf_counter() - t0) * 1000.0
            streamed_text = "".join(deltas)
            parity_ok = streamed_text == final_resp.output_text

            append_jsonl(
                INFERENCE_LOG,
                {
                    "test_group": "streaming_ttft",
                    "run": run_idx,
                    "cache": False,
                    "ttft_ms": round(ttft_ms, 2) if ttft_ms is not None else None,
                    "total_ms": round(total_ms, 2),
                    "chunk_count": len(deltas),
                    "parity_ok": parity_ok,
                    "event_types_sample": event_types[:5],
                    **extract_response_summary(final_resp),
                },
                secrets,
            )
            console.print(
                f"  Stream run {run_idx}: TTFT={ttft_ms:.1f}ms, Total={total_ms:.1f}ms, "
                f"chunks={len(deltas)}, parity={parity_ok}"
            )

        # Cache test: two identical calls with cache=True
        for cache_pass in (1, 2):
            t0 = time.perf_counter()
            resp = await client.responses.create(
                model="moss",
                instructions=GROUNDING_INSTRUCTIONS,
                input="What is the exact SKU and MSRP of the Kestrel Acoustic Pod?",
                indexes=[index_name],
                cache=True,
                stream=False,
            )
            total_ms = (time.perf_counter() - t0) * 1000.0
            append_jsonl(
                INFERENCE_LOG,
                {
                    "test_group": "cache_check",
                    "pass": cache_pass,
                    "cache": True,
                    "total_ms": round(total_ms, 2),
                    **extract_response_summary(resp),
                },
                secrets,
            )
            console.print(f"  Cache pass {cache_pass}: Total={total_ms:.1f}ms")


async def run_grounding_and_abstention_tests(cfg: dict[str, str], secrets: list[str]) -> None:
    """Compare ungrounded vs grounded accuracy/latency and test abstention on missing facts."""
    index_name = cfg["index_name"]
    async with make_inference_client(cfg) as client:
        for case in GROUNDED_CASES:
            # Ungrounded baseline (retrieve=False)
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

            # Grounded with Moss index
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
            console.print(
                f"  [{case['id']}] grounded_ok={g_ok} (missing={g_missing}) | "
                f"ungrounded_ok={ug_ok} | grounded={grounded_ms:.0f}ms vs ungrounded={ungrounded_ms:.0f}ms"
            )

        for case in ABSTENTION_CASES:
            t0 = time.perf_counter()
            resp = await client.responses.create(
                model="moss",
                instructions=GROUNDING_INSTRUCTIONS,
                input=case["prompt"],
                indexes=[index_name],
                retrieve=True,
                cache=False,
            )
            total_ms = (time.perf_counter() - t0) * 1000.0
            abstained = _looks_like_abstention(resp.output_text)
            append_jsonl(
                INFERENCE_LOG,
                {
                    "test_group": "abstention",
                    "case_id": case["id"],
                    "prompt": case["prompt"],
                    "total_ms": round(total_ms, 2),
                    "abstained": abstained,
                    **extract_response_summary(resp),
                },
                secrets,
            )
            console.print(f"  [{case['id']}] abstained={abstained} | {total_ms:.0f}ms")


async def run_features_and_error_tests(cfg: dict[str, str], secrets: list[str]) -> None:
    """Test function calling, multi-turn conversation, bad inputs, nonexistent index, bad auth, and burst."""
    index_name = cfg["index_name"]
    async with make_inference_client(cfg) as client:
        # 1. Function tool calling test
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
        try:
            t0 = time.perf_counter()
            tool_resp = await client.responses.create(
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
                    **extract_response_summary(tool_resp),
                },
                secrets,
            )
            console.print(
                f"  [tool_call] output_types={[getattr(x, 'type', type(x).__name__) for x in tool_resp.output]}"
            )
        except InferenceError as exc:
            append_jsonl(
                INFERENCE_LOG,
                {
                    "test_group": "feature_tool_call",
                    "ok": False,
                    "error_type": exc.type,
                    "status": exc.status,
                    "code": exc.code,
                    "message": exc.message,
                },
                secrets,
            )
            console.print(f"  [tool_call] ERROR {exc.status} {exc.type}: {exc.message}")

        # 2. Multi-turn input items
        try:
            t0 = time.perf_counter()
            turn1 = await client.responses.create(
                model="moss",
                instructions=GROUNDING_INSTRUCTIONS,
                input="What is the standard return window in days?",
                indexes=[index_name],
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
                indexes=[index_name],
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
            console.print(f"  [multiturn] has_45={'45' in turn2.output_text}")
        except InferenceError as exc:
            append_jsonl(
                INFERENCE_LOG,
                {
                    "test_group": "feature_multiturn",
                    "ok": False,
                    "error_type": exc.type,
                    "status": exc.status,
                    "code": exc.code,
                    "message": exc.message,
                },
                secrets,
            )
            console.print(f"  [multiturn] ERROR {exc.status} {exc.type}: {exc.message}")

        # 3. Edge / Error probes
        error_probes: list[tuple[str, dict[str, Any]]] = [
            (
                "nonexistent_index",
                {"model": "moss", "input": "Hello", "indexes": ["index-does-not-exist-999"]},
            ),
            ("empty_input", {"model": "moss", "input": ""}),
            (
                "invalid_model_no_byok",
                {"model": "gpt-4o-mini", "input": "Hello"},
            ),
        ]
        for probe_id, kwargs in error_probes:
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
                console.print(f"  [error_probe:{probe_id}] DID NOT RAISE -> status={resp.status}")
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
                console.print(
                    f"  [error_probe:{probe_id}] raised status={exc.status} type={exc.type} code={exc.code}: {exc.message}"
                )

        # 4. Async burst (5 concurrent grounded calls)
        t0 = time.perf_counter()

        async def _one(i: int) -> dict[str, Any]:
            st = time.perf_counter()
            try:
                r = await client.responses.create(
                    model="moss",
                    instructions=GROUNDING_INSTRUCTIONS,
                    input=f"Request {i}: What error code indicates insufficient PoE wattage?",
                    indexes=[index_name],
                    cache=False,
                )
                return {
                    "i": i,
                    "ok": "ERR-102-PWR" in r.output_text,
                    "ms": round((time.perf_counter() - st) * 1000.0, 2),
                }
            except InferenceError as exc:
                return {
                    "i": i,
                    "ok": False,
                    "status": exc.status,
                    "error_type": exc.type,
                    "ms": round((time.perf_counter() - st) * 1000.0, 2),
                }

        burst_results = await asyncio.gather(*(_one(i) for i in range(1, 6)))
        burst_wall_ms = (time.perf_counter() - t0) * 1000.0
        append_jsonl(
            INFERENCE_LOG,
            {
                "test_group": "async_burst_5",
                "wall_ms": round(burst_wall_ms, 2),
                "results": burst_results,
            },
            secrets,
        )
        console.print(f"  [burst_5] wall={burst_wall_ms:.0f}ms results={burst_results}")

    # 5. Invalid credentials probe
    bad_client = make_inference_client(
        {**cfg, "project_key": "moss_invalid_key_000000000000"}, max_retries=0
    )
    async with bad_client:
        try:
            await bad_client.responses.create(model="moss", input="Hello")
            console.print("  [error_probe:invalid_key] DID NOT RAISE!")
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
            console.print(
                f"  [error_probe:invalid_key] raised status={exc.status} type={exc.type}: {exc.message}"
            )


async def main() -> None:
    cfg = load_config()
    secrets = [cfg["project_id"], cfg["project_key"]]

    console.rule("[bold green]Moss Inference API Evaluation Suite")
    ok = await check_index_preflight(cfg, secrets)
    if not ok:
        return

    console.rule("Streaming TTFT & Cache Checks")
    await run_streaming_and_cache_tests(cfg, secrets)

    console.rule("Synthetic KB RAG Grounding & Abstention")
    await run_grounding_and_abstention_tests(cfg, secrets)

    console.rule("Features, Error Probes & Async Burst")
    await run_features_and_error_tests(cfg, secrets)

    table = Table(title="Inference Suite Completed")
    table.add_column("Log Output")
    table.add_row(str(INFERENCE_LOG))
    console.print(table)


if __name__ == "__main__":
    asyncio.run(main())
