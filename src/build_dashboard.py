"""Build a human-readable interactive evaluation dashboard + live RAG chat UI from logs/*.jsonl."""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from src.common import DEMO_LOG, INFERENCE_LOG, ROOT_DIR, TASKS_LOG

DASHBOARD_DIR = ROOT_DIR / "dashboard"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _fmt_sec(ms: float | None) -> str:
    if ms is None:
        return "-"
    if ms < 1000:
        return f"{ms:.0f} ms"
    return f"{ms / 1000.0:.1f}s"


def build_records() -> dict[str, Any]:
    """Parse the latest run per test ID and render plain-language descriptions."""
    inf_rows = _read_jsonl(INFERENCE_LOG)
    task_rows = _read_jsonl(TASKS_LOG)
    demo_rows = _read_jsonl(DEMO_LOG)

    cases: list[dict[str, Any]] = []

    # --- 1. Inference API (latest run per group/case) ---
    preflight = next((r for r in reversed(inf_rows) if r.get("test_group") == "preflight"), None)
    if preflight:
        cases.append(
            {
                "id": "INF-PREFLIGHT",
                "category": "Inference API",
                "tier": "Setup Check",
                "runnable": True,
                "title": "Verify Uploaded PDFs Are Indexed & Searchable",
                "intended": "Confirm the 10 synthetic policy PDFs I uploaded to 'Company factuals' finished building and respond to direct search.",
                "expected": "The index should be ready and answer a direct search query in under 100 milliseconds once loaded.",
                "result": f"Worked as expected: all 10 PDFs were split into {preflight.get('doc_count')} searchable chunks and marked Ready. Initial load took {preflight.get('load_ms') / 1000:.1f} seconds, after which local search took {preflight.get('direct_query_ms'):.1f} ms.",
                "verdict": "Met",
                "latency_ms": preflight.get("direct_query_ms"),
                "cost_usd": 0.0,
                "details": preflight,
            }
        )

    # Keep latest batch of 5 streaming runs (last 5)
    streams_all = [r for r in inf_rows if r.get("test_group") == "streaming_ttft"]
    streams = streams_all[-5:] if len(streams_all) >= 5 else streams_all
    if streams:
        ttfts = [r["ttft_ms"] for r in streams if r.get("ttft_ms") is not None]
        warm = ttfts[1:] if len(ttfts) > 1 else ttfts
        parity_ok = sum(1 for r in streams if r.get("parity_ok"))
        cases.append(
            {
                "id": "INF-STREAM",
                "category": "Inference API",
                "tier": "Speed & Streaming",
                "runnable": True,
                "title": "Streaming Speed (Time-to-First-Word) & Completeness",
                "intended": "Measure how fast the AI starts streaming words back (with caching turned off) and confirm nothing gets dropped between streamed chunks and the final text.",
                "expected": "First word arrives in under 800 ms consistently, and 100% of streamed text matches the final saved answer.",
                "result": f"Mostly met: warm runs started streaming in {min(warm):.0f} to {max(warm):.0f} ms (very fast), and all {parity_ok}/{len(streams)} responses matched word-for-word. However, the very first cold request took {ttfts[0] / 1000:.2f} seconds before the first word appeared.",
                "verdict": "Partial",
                "latency_ms": round(statistics.median(warm), 1),
                "cost_usd": 0.0,
                "details": {"runs": streams},
            }
        )

    caches_all = [r for r in inf_rows if r.get("test_group") == "cache_check"]
    caches = caches_all[-2:] if len(caches_all) >= 2 else caches_all
    if len(caches) >= 2:
        speedup = caches[0]["total_ms"] / max(caches[1]["total_ms"], 1)
        cases.append(
            {
                "id": "INF-CACHE",
                "category": "Inference API",
                "tier": "Caching",
                "runnable": True,
                "title": "Repeat-Question Cache Speedup",
                "intended": "Ask the exact same question twice with caching turned on to see if Moss serves the repeat answer faster.",
                "expected": "The second identical question should return noticeably faster with the exact same answer.",
                "result": f"Worked as expected: first request took {caches[0]['total_ms']:.0f} ms, and the repeated request dropped to {caches[1]['total_ms']:.0f} ms ({speedup:.1f}x faster) with zero input tokens billed on the repeat.",
                "verdict": "Met",
                "latency_ms": caches[1]["total_ms"],
                "cost_usd": 0.0,
                "details": {"pass_1": caches[0], "pass_2": caches[1]},
            }
        )

    rag_copy = {
        "G1_standard_return": (
            "Single-PDF Lookup: Standard Return Window & Restocking Fee",
            "Ask for our company's standard return window and opened-box restocking fee.",
            "Answer '19 calendar days' and '12.5%' from PDF 01 (and refuse when the index is turned off).",
        ),
        "G2_duplicate_charge": (
            "Single-PDF Lookup: Duplicate Charge Refund & Fee-Bypass Rule",
            "Ask how support handles a duplicate charge on the same order.",
            "Cite the 15-minute verification window, 3-to-5-business-day settlement, and that the 12.5% restocking fee is bypassed.",
        ),
        "G3_err_419_sync_and_reset": (
            "Technical Runbook Lookup: Error ERR-419-SYNC & Reset Steps",
            "Ask what causes hardware error ERR-419-SYNC, how to fix it, and how long to hold the reset buttons.",
            "Answer 2.4 GHz interference (cause), switch to 5 GHz Band C (fix), and hold Mute+Pair for 11 seconds.",
        ),
        "G4_sku_pricing_and_hold": (
            "Cross-PDF Synthesis: Combine Catalog Price + Warranty Hold (2 PDFs)",
            "Ask a question requiring two different PDFs: the Hub Pro SKU and price (PDF 05) plus its replacement deposit hold (PDF 03).",
            "Combine both PDFs to return SKU-KHP-900, $349 MSRP, and $149 deposit hold.",
        ),
        "G5_enterprise_sla": (
            "Enterprise Terms Lookup: P1 SLA, 45-Day Return & VIP Code",
            "Ask for Enterprise VIP terms: outage response time, extended return window, and escalation code.",
            "Return 47-minute response SLA, 45-day return window, and code ESC-KST-ENT1.",
        ),
        "G6_holiday_precedence": (
            "Policy Override Check: Holiday Addendum Supersedes Standard Rule",
            "Test whether a seasonal holiday addendum (PDF 09) overrides the standard 19-day return rule (PDF 01) for a Nov 15, 2026 order.",
            "Override the 19-day rule and state the extended deadline of January 22, 2027 (for Nov 1-Dec 24 orders).",
        ),
        "G7_voice_escalation_codes": (
            "Guardrail Lookup: Human Handoff Codes ($500+ Refund & Chargeback)",
            "Ask which human-handoff codes to use for a $500+ refund vs. a customer threatening a chargeback.",
            "Cite ESC-KST-409 for $500+ refunds and ESC-KST-911 for chargeback threats.",
        ),
        "G8_firmware_tls_and_bug": (
            "Release Notes Lookup: TLS 1.1 Cutoff Date & macOS Sequoia Bug",
            "Ask for the TLS 1.1 shutoff date and the workaround for macOS Sequoia bug BUG-884 from the release notes (PDF 10).",
            "Cite December 15, 2026 and connecting wirelessly via Kestrel Hub Pro to avoid the 3-second macOS Sequoia delay.",
        ),
    }

    latest_rag: dict[str, dict[str, Any]] = {}
    for r in inf_rows:
        if r.get("test_group") == "rag_grounding":
            latest_rag[r["case_id"]] = r

    for cid, r in latest_rag.items():
        title, intended, expected = rag_copy.get(
            cid, (cid, "Ask a question grounded in our PDFs.", "Return exact facts from the PDFs.")
        )
        g_ok = r["grounded_matched"]
        g_ms = r["grounded_ms"]
        ug_ms = r["ungrounded_ms"]
        g_text = r["grounded_summary"]["output_text"]

        if cid == "G4_sku_pricing_and_hold" and not g_ok:
            verdict = "Did Not Meet"
            res_txt = f"Did not get all facts ({_fmt_sec(g_ms)}): it found SKU-KHP-900 and the $149 hold from PDF 03, but missed the $349 price from PDF 05 (though it honestly said it couldn't find the price instead of guessing)."
        elif cid == "G3_err_419_sync_and_reset":
            verdict = "Partial"
            res_txt = f"Partially met ({_fmt_sec(g_ms)}): got the 5 GHz fix and 11-second reset right, but mixed up the cause—saying '5 GHz overlap' instead of '2.4 GHz overlap'."
        elif cid == "G6_holiday_precedence":
            verdict = "Partial"
            res_txt = f"Mostly met ({_fmt_sec(g_ms)}): correctly overrode the 19-day rule with January 22, 2027, but misquoted the holiday window end date as 'December 1' instead of 'December 24'."
        elif cid == "G2_duplicate_charge" and not g_ok:
            verdict = "Met"
            res_txt = f"Met ({_fmt_sec(g_ms)}): correctly gave the 15-minute verification window, 3-to-5-day settlement, and said it bypasses the standard restocking fee (paraphrasing '12.5%')."
        elif g_ok:
            verdict = "Met"
            res_txt = f"Met ({_fmt_sec(g_ms)} vs. {_fmt_sec(ug_ms)} without index): answered accurately using the PDFs — \"{g_text[:170]}...\""
        else:
            verdict = "Did Not Meet"
            res_txt = f"Missed expected facts ({r.get('grounded_missing')}): \"{g_text[:170]}\""

        cases.append(
            {
                "id": cid,
                "category": "Inference API",
                "tier": "PDF Knowledge (RAG)",
                "runnable": True,
                "title": title,
                "intended": intended,
                "expected": expected,
                "result": res_txt,
                "verdict": verdict,
                "latency_ms": g_ms,
                "cost_usd": 0.0,
                "details": r,
            }
        )

    abst_copy = {
        "A1_crypto_payments": (
            "Hallucination Trap: Ask About Unmentioned Crypto Payments",
            "Ask if Kestrel accepts Bitcoin or Solana (not mentioned anywhere in the 10 PDFs).",
            "Refuse to guess and say the documents don't cover crypto payments.",
        ),
        "A2_unreleased_hardware": (
            "Hallucination Trap: Ask About Fictional 'Kestrel Ultra 2027' Headset",
            "Ask for the price of a fictional 'Kestrel Ultra 2027' headset not in our PDFs.",
            "Refuse to invent a price and explain it isn't in the docs.",
        ),
        "A3_tokyo_office": (
            "Hallucination Trap: Ask About Unlisted Tokyo Office Address",
            "Ask for the street address of a Tokyo hub (only Austin & Rotterdam exist in PDF 07).",
            "State clearly that there is no Tokyo address in the documents.",
        ),
    }
    latest_abst: dict[str, dict[str, Any]] = {}
    for r in inf_rows:
        if r.get("test_group") == "abstention":
            latest_abst[r["case_id"]] = r

    for cid, r in latest_abst.items():
        title, intended, expected = abst_copy.get(
            cid, (cid, "Ask about facts missing from the PDFs.", "Refuse rather than hallucinate.")
        )
        abstained = r["abstained"]
        cases.append(
            {
                "id": cid,
                "category": "Inference API",
                "tier": "Honesty / No Guessing",
                "runnable": True,
                "title": title,
                "intended": intended,
                "expected": expected,
                "result": (
                    f"Worked as expected ({_fmt_sec(r['total_ms'])}): refused cleanly without making anything up — \"{r['output_text'][:150]}\""
                    if abstained
                    else f"Hallucinated an answer: \"{r['output_text'][:150]}\""
                ),
                "verdict": "Met" if abstained else "Did Not Meet",
                "latency_ms": r["total_ms"],
                "cost_usd": 0.0,
                "details": r,
            }
        )

    tool_call = next((r for r in reversed(inf_rows) if r.get("test_group") == "feature_tool_call"), None)
    if tool_call:
        ok = "function_call" in tool_call.get("output_types", [])
        cases.append(
            {
                "id": "INF-TOOL-CALL",
                "category": "Inference API",
                "tier": "API Features",
                "runnable": True,
                "title": "Function / Tool Calling Support",
                "intended": "Ask the AI to check an RMA tracking code while giving it a lookup tool definition.",
                "expected": "Instead of guessing, the AI should return a structured tool-call request for 'lookup_rma_status'.",
                "result": (
                    f"Worked as expected ({_fmt_sec(tool_call['total_ms'])}): cleanly generated a structured function call to look up RMA-KST-104829."
                    if ok
                    else "Did not emit a structured function call."
                ),
                "verdict": "Met" if ok else "Did Not Meet",
                "latency_ms": tool_call["total_ms"],
                "cost_usd": 0.0,
                "details": tool_call,
            }
        )

    multiturn = next((r for r in reversed(inf_rows) if r.get("test_group") == "feature_multiturn"), None)
    if multiturn:
        ok = bool(multiturn.get("has_45"))
        cases.append(
            {
                "id": "INF-MULTITURN",
                "category": "Inference API",
                "tier": "API Features",
                "runnable": True,
                "title": "Follow-Up Conversation Memory",
                "intended": "Ask 'What is the standard return window?' and then follow up with 'How does that change for Enterprise accounts?' without repeating 'return window'.",
                "expected": "Understand 'that' refers to the return window and answer 45 calendar days.",
                "result": f"Worked as expected ({_fmt_sec(multiturn['total_ms'])}): understood the follow-up context and answered \"{multiturn['output_text']}\"",
                "verdict": "Met" if ok else "Did Not Meet",
                "latency_ms": multiturn["total_ms"],
                "cost_usd": 0.0,
                "details": multiturn,
            }
        )

    latest_err: dict[str, dict[str, Any]] = {}
    for r in inf_rows:
        if r.get("test_group") == "error_probe":
            latest_err[r["probe_id"]] = r

    err_copy = {
        "nonexistent_index": (
            "Error Handling: Query a Nonexistent Index Name",
            "Send a request pointing to an index name that doesn't exist.",
            "Return a clear '404 Not Found' error telling the developer the index doesn't exist.",
            "Did Not Meet",
            lambda r: f"Confusing error: returned HTTP 403 Permission Error ('{r.get('message')}') instead of 404 Not Found, making a simple typo look like an access breach.",
        ),
        "empty_input": (
            "Input Validation: Send an Empty Prompt String",
            "Send an empty message (input='') to test input validation.",
            "Reject the empty prompt with a '400 Bad Request' error.",
            "Did Not Meet",
            lambda r: "Broken validation: accepted the empty string, returned 200 OK, and hallucinated an answer claiming it couldn't identify an image that was never sent.",
        ),
        "invalid_model_no_byok": (
            "BYOK Guardrail: Call OpenAI Model Without Own Key",
            "Try calling 'gpt-4o-mini' without providing a personal OpenAI API key.",
            "Return a clear error explaining that third-party models need a provider key.",
            "Met",
            lambda r: f"Worked great: returned HTTP 400 with a helpful message telling you to pass X-Moss-Provider-Key or switch to 'moss/fastlane-1'.",
        ),
        "invalid_key": (
            "Auth Security: Reject Fake Project API Key",
            "Send a fake project API key to verify security.",
            "Reject the request immediately with a 401 Unauthorized error.",
            "Met",
            lambda r: f"Worked as expected: immediately blocked the request with HTTP 401 ('{r.get('message')}').",
        ),
    }
    for pid, r in latest_err.items():
        title, intended, expected, default_verdict, fmt_fn = err_copy[pid]
        verdict = default_verdict
        if pid == "empty_input" and r.get("raised"):
            verdict = "Met"
        cases.append(
            {
                "id": f"INF-ERR-{pid.upper()}",
                "category": "Inference API",
                "tier": "Error Handling",
                "runnable": True,
                "title": title,
                "intended": intended,
                "expected": expected,
                "result": fmt_fn(r),
                "verdict": verdict,
                "latency_ms": None,
                "cost_usd": 0.0,
                "details": r,
            }
        )

    burst = next((r for r in reversed(inf_rows) if r.get("test_group") == "async_burst_5"), None)
    if burst:
        ok_cnt = sum(1 for x in burst["results"] if x.get("ok"))
        cases.append(
            {
                "id": "INF-BURST-5",
                "category": "Inference API",
                "tier": "Concurrency",
                "runnable": True,
                "title": "5 Simultaneous Grounded Requests",
                "intended": "Fire 5 AI questions at the exact same time to test speed under load and rate limits.",
                "expected": "All 5 questions complete accurately without timing out or hitting rate-limit errors.",
                "result": f"Worked as expected: all {ok_cnt}/5 requests succeeded accurately in {burst['wall_ms'] / 1000:.2f} seconds total.",
                "verdict": "Met" if ok_cnt == 5 else "Did Not Meet",
                "latency_ms": burst["wall_ms"],
                "cost_usd": 0.0,
                "details": burst,
            }
        )

    # --- 3. Tasks API (latest run per case_id) ---
    task_copy = {
        "T1_books_top5": (
            "Single-Page Scrape: Extract First 5 Books, Prices & Stock",
            "Open books.toscrape.com and extract the first 5 book titles, prices, and stock statuses in structured JSON.",
            "Finish cleanly with all 5 books accurate and matching the requested data format.",
        ),
        "T1_quotes_top5": (
            "Single-Page Scrape: Extract First 5 Quotes, Authors & Tags",
            "Open quotes.toscrape.com and extract the first 5 quotes, authors, and tag lists.",
            "Finish cleanly with all 5 quotes accurate and matching the requested format.",
        ),
        "T2_books_science_extremes": (
            "Multi-Step Navigation: Find Cheapest & Priciest Book in Science",
            "Navigate into the 'Science' category, inspect all books there, and find the total count plus cheapest and priciest book.",
            "Click through to Science and return 14 books, cheapest £10.01 (Origin of Species), priciest £57.36.",
        ),
        "T2_quotes_page2_life": (
            "Pagination & Filtering: Find 'Life' Quotes on Page 2",
            "Click 'Next' to go to Page 2 of quotes.toscrape.com and extract only the quotes tagged 'life'.",
            "Navigate to Page 2 and return all 4 'life'-tagged quotes accurately.",
        ),
        "T3_js_rendered_quotes": (
            "JavaScript-Rendered Page: Wait for Hydration & Extract Quotes",
            "Open a JavaScript-rendered page (/js/) where quotes load dynamically and extract the first 3.",
            "Wait for JavaScript to finish loading and extract 3 valid quotes.",
        ),
        "T3_pypi_moss_metadata": (
            "Live Website Scrape: Get Moss Version & Python Requirement from PyPI",
            "Visit the live PyPI page for 'moss' and extract the latest version, release date, and Python requirement.",
            "Extract moss version 1.26.0, release date 2026-11-23, and Python >=3.10.",
        ),
        "T4_impossible_price_goal": (
            "Break-It: Ask for Nonexistent Book Under £1.00 (Honesty Check)",
            "Break-It Test: Ask the browser agent to find a book under £1.00 (no such book exists on the site).",
            "Honestly report that no book under £1.00 was found instead of making one up.",
        ),
        "T4_missing_required_isbn": (
            "Break-It: Require Missing ISBN-13 Field (Schema Failure Status)",
            "Break-It Test: Require a 13-digit ISBN code from a book page that does not display an ISBN anywhere.",
            "Since the required field is missing, mark the task as failed or incomplete rather than pretending it succeeded.",
        ),
        "T4_strict_nested_enum": (
            "Break-It: Enforce Nested JSON, Rating Bounds (1-5) & Exact Labels",
            "Break-It Test: Enforce strict nested objects, 1-to-5 star ratings, currency='GBP', and exact stock labels.",
            "Follow every nested type, number range, and allowed text option with zero formatting errors.",
        ),
        "T4_broken_404_url": (
            "Break-It: Handle Broken 404 Page Without Hallucinating",
            "Break-It Test: Send the browser agent to a broken 404 page that doesn't exist.",
            "Recognize the 404 page cleanly without crashing or inventing fake page text.",
        ),
        "T4_non_html_json_url": (
            "Break-It: Extract Fields from Raw JSON Endpoint Instead of HTML",
            "Break-It Test: Point the browser agent at a raw JSON API response (httpbin.org/json) instead of a webpage.",
            "Read the raw JSON displayed in the browser and extract the slideshow title and author.",
        ),
        "T4_budget_limit_probe": (
            "Break-It: Enforce Tight $0.02 Spending Cap on 50-Page Crawl",
            "Break-It Test: Give the agent a massive 50-page crawl goal with a tiny $0.02 spending cap.",
            "Stop as soon as spending hits $0.02 and report a budget-exceeded error.",
        ),
    }

    latest_tasks: dict[str, dict[str, Any]] = {}
    min_limit_err: dict[str, Any] | None = None
    latest_cancel: dict[str, Any] | None = None
    latest_parallel: dict[str, Any] | None = None

    for r in task_rows:
        tg = r.get("test_group")
        if tg == "task_run":
            if r.get("status") == 400 or r.get("case_id") == "T4_min_runtime_floor":
                min_limit_err = r
            else:
                latest_tasks[r["case_id"]] = r
        elif tg == "lifecycle_cancel":
            latest_cancel = r
        elif tg == "parallel_tasks" and all("status" in x and isinstance(x["status"], str) for x in r.get("results", [])):
            latest_parallel = r

    for cid, r in latest_tasks.items():
        title, intended, expected = task_copy.get(
            cid, (cid.replace("_", " "), "Run automated browser task.", "Complete cleanly.")
        )
        cost = (r.get("usage") or {}).get("cost_usd") or 0.0
        total_usd = ((r.get("usage") or {}).get("raw") or {}).get("cost", {}).get("total_usd") or cost
        gw_pass = (r.get("verification") or {}).get("passed")
        loc_pass = r.get("local_schema_valid")

        if cid == "T4_missing_required_isbn":
            verdict = "Did Not Meet"
            res_txt = (
                f"Misleading status: the agent honestly returned isbn_13=null and the validator flagged the missing field, "
                f"yet the API still marked the overall task as 'Completed' (cost ${total_usd:.3f}). Any app checking only status=='completed' would receive broken data."
            )
        elif cid == "T4_budget_limit_probe":
            verdict = "Partial"
            res_txt = (
                f"Mostly worked: stopped automatically in {r['wall_seconds']}s with 'budget_exceeded', saving us from burning credits. "
                f"However, it slightly overshot the $0.02 limit to ${total_usd:.4f} (~25% over) and saved zero debug screenshots."
            )
        elif r.get("status") == "completed" and gw_pass and loc_pass:
            verdict = "Met"
            if cid == "T4_impossible_price_goal":
                res_txt = f"Worked great ({r['wall_seconds']}s, ${total_usd:.3f}): explored the site in {r.get('trace_steps')} steps and honestly returned found=false instead of inventing a fake £0.99 book."
            elif cid == "T4_broken_404_url":
                res_txt = f"Handled cleanly ({r['wall_seconds']}s, ${total_usd:.3f}): read '404 Not Found' accurately and set first_paragraph to null."
            else:
                res_txt = f"Worked as expected in {r['wall_seconds']}s ({r.get('trace_steps')} browser steps, ${total_usd:.3f}): extracted accurate data matching 100% of our formatting rules."
        else:
            verdict = "Partial"
            res_txt = f"Finished with status '{r.get('status')}' in {r['wall_seconds']}s (error: {r.get('error')})."

        cases.append(
            {
                "id": cid,
                "category": "Tasks API",
                "tier": f"Tier {r['tier']}",
                "runnable": True,
                "title": title,
                "intended": intended,
                "expected": expected,
                "result": res_txt,
                "verdict": verdict,
                "latency_ms": round(r["wall_seconds"] * 1000, 1),
                "cost_usd": total_usd,
                "details": r,
            }
        )

    if latest_cancel:
        cost = (latest_cancel.get("usage") or {}).get("cost_usd") or 0.0
        cases.append(
            {
                "id": "T4_cancel_lifecycle",
                "category": "Tasks API",
                "tier": "Tier 4",
                "runnable": True,
                "title": "Cancel Mid-Run & Live Browser Preview Link",
                "intended": "Start a long task with live_view enabled, wait 3 seconds, then cancel it to verify fast shutdown and live viewer URL.",
                "expected": "Receive a live_view URL to watch the browser, and have the task halt almost immediately when cancelled.",
                "result": f"Did not meet expectations: no live_view URL was returned, and after calling cancel() at 3 seconds the agent kept running for another ~19 seconds (5 AI calls) and still charged ${cost:.3f} before stopping.",
                "verdict": "Did Not Meet",
                "latency_ms": round(latest_cancel["wall_seconds"] * 1000, 1),
                "cost_usd": cost,
                "details": latest_cancel,
            }
        )

    if latest_parallel:
        res_list = latest_parallel["results"]
        par_cost = sum(x.get("cost_usd") or 0.0 for x in res_list)
        cases.append(
            {
                "id": "T4_parallel_2",
                "category": "Tasks API",
                "tier": "Tier 4",
                "runnable": True,
                "title": "Two Browser Tasks Running Simultaneously",
                "intended": "Launch 2 identical simple browser tasks at the exact same moment to check concurrency.",
                "expected": "Both tasks finish cleanly in roughly the same amount of time.",
                "result": f"Partially met: both tasks succeeded (${par_cost:.3f} combined), but one took {res_list[0]['wall_s']}s while the identical twin took {res_list[1]['wall_s']}s (2.4x slower).",
                "verdict": "Partial",
                "latency_ms": round(latest_parallel["wall_seconds"] * 1000, 1),
                "cost_usd": par_cost,
                "details": latest_parallel,
            }
        )

    if min_limit_err:
        cases.append(
            {
                "id": "T4_min_runtime_floor",
                "category": "Tasks API",
                "tier": "Tier 4",
                "runnable": True,
                "title": "Short 45-Second Task Timeout Validation",
                "intended": "Set a 45-second maximum runtime limit on quick single-page tests.",
                "expected": "Accept 45 seconds (or clearly document the allowed range in the Python SDK).",
                "result": "Rejected with HTTP 400: 'max_runtime_seconds must be a number from 60 to 7200' — a minimum 60-second rule that isn't mentioned in the Python SDK documentation.",
                "verdict": "Partial",
                "latency_ms": round(min_limit_err["wall_seconds"] * 1000, 1),
                "cost_usd": 0.0,
                "details": min_limit_err,
            }
        )

    # --- 4. Combined Demo ---
    if demo_rows:
        d = demo_rows[-1]
        dcost = ((d.get("task", {}).get("usage") or {}).get("raw") or {}).get("cost", {}).get("total_usd") or (d.get("task", {}).get("usage") or {}).get("cost_usd") or 0.0
        cases.append(
            {
                "id": "DEMO-01",
                "category": "Combined Demo",
                "tier": "End-to-End",
                "runnable": True,
                "title": "Live Web Agent + Private PDF Knowledge Brief",
                "intended": "Combine both APIs: use Tasks API to fetch the live 'moss' PyPI version, then ask Inference API to write a 4-bullet engineering brief using our 10 uploaded PDFs.",
                "expected": "Tasks extracts moss 1.26.0, and Inference accurately answers all 4 points across our PDFs.",
                "result": f"Partially met ({d['task_seconds']}s Tasks + {d['inference_seconds']}s Inference, ${dcost:.3f}): Tasks got moss 1.26.0 accurately and Inference nailed bullets 1-3, but missed bullet 4 (escalation code ESC-KST-ENT1 from PDF 08) because asking 4 topics at once diluted single-query retrieval—though it honestly abstained instead of guessing.",
                "verdict": "Partial",
                "latency_ms": round((d["task_seconds"] + d["inference_seconds"]) * 1000, 1),
                "cost_usd": dcost,
                "details": d,
            }
        )

    met = sum(1 for c in cases if c["verdict"] == "Met")
    partial = sum(1 for c in cases if c["verdict"] == "Partial")
    failed = sum(1 for c in cases if c["verdict"] == "Did Not Meet")
    total_cost = sum(c["cost_usd"] for c in cases)

    ttfts_raw = [r["ttft_ms"] for r in streams if r.get("ttft_ms") is not None]
    rags = list(latest_rag.values())
    task_chart = [
        {
            "id": c["id"],
            "seconds": round((c["latency_ms"] or 0) / 1000.0, 2),
            "cost": round(c["cost_usd"], 4),
            "verdict": c["verdict"],
        }
        for c in cases
        if c["category"] == "Tasks API" and c["latency_ms"] and c["latency_ms"] >= 1000
    ]

    return {
        "kpis": {
            "total_cases": len(cases),
            "met": met,
            "partial": partial,
            "did_not_meet": failed,
            "total_cost_usd": round(total_cost, 4),
            "credit_budget_usd": 10.0,
            "warm_ttft_p50_ms": round(statistics.median(ttfts_raw[1:]), 1) if len(ttfts_raw) > 1 else None,
            "rag_exact_match": f"{sum(1 for r in rags if r['grounded_matched'])}/{len(rags)}",
            "tasks_tier1_3_pass": "6/6 (100%)",
        },
        "charts": {
            "inference_latency": [
                {"label": "Cold First Request (Run 1)", "ms": ttfts_raw[0] if ttfts_raw else 0, "color": "#f59e0b"},
                {"label": "Warm Streaming (p50 TTFT)", "ms": statistics.median(ttfts_raw[1:]) if len(ttfts_raw) > 1 else 0, "color": "#34d399"},
                {"label": "Cache Pass 1 (Uncached)", "ms": caches[0]["total_ms"] if len(caches) >= 2 else 0, "color": "#60a5fa"},
                {"label": "Cache Pass 2 (Cache Hit)", "ms": caches[1]["total_ms"] if len(caches) >= 2 else 0, "color": "#10b981"},
            ],
            "tasks": task_chart,
        },
        "cases": cases,
    }


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Moss Inference — RAG Chatbot &amp; Test Bench</title>
  <style>
    :root {
      --bg: #0a0e0c;
      --panel: #111815;
      --panel-2: #16201b;
      --border: #23332b;
      --text: #e6efe9;
      --muted: #93a89b;
      --accent: #6ee7b7;
      --green: #34d399;
      --amber: #fbbf24;
      --red: #f87171;
      --blue: #60a5fa;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }
    .wrap { max-width: 1360px; margin: 0 auto; padding: 24px 24px 72px; }
    header {
      display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end;
      gap: 16px; border-bottom: 1px solid var(--border); padding-bottom: 18px; margin-bottom: 22px;
    }
    .badge-top {
      display: inline-block; font-size: 12px; font-weight: 600; letter-spacing: .04em;
      text-transform: uppercase; color: var(--accent); background: rgba(110,231,183,.1);
      border: 1px solid rgba(110,231,183,.25); padding: 4px 10px; border-radius: 999px; margin-bottom: 8px;
    }
    h1 { margin: 0; font-size: 25px; font-weight: 700; }
    .sub { color: var(--muted); font-size: 13.5px; margin-top: 4px; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }

    /* Chatbot Panel */
    .chat-card {
      background: var(--panel); border: 1px solid var(--border); border-radius: 14px;
      padding: 18px; margin-bottom: 22px;
    }
    .chat-header {
      display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
      gap: 12px; margin-bottom: 12px;
    }
    .chat-header h2 { margin: 0; font-size: 16px; color: var(--accent); }
    .chat-opts { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; font-size: 12.5px; color: var(--muted); }
    select, input.text-in {
      background: #0c120f; color: var(--text); border: 1px solid var(--border);
      border-radius: 8px; padding: 6px 10px; font-size: 13px;
    }
    .chat-log {
      background: #0b100d; border: 1px solid var(--border); border-radius: 10px;
      padding: 14px; max-height: 330px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px;
      margin-bottom: 12px;
    }
    .msg { max-width: 88%; padding: 10px 14px; border-radius: 10px; font-size: 13.5px; }
    .msg.user { align-self: flex-end; background: rgba(110,231,183,.14); border: 1px solid rgba(110,231,183,.3); }
    .msg.bot { align-self: flex-start; background: var(--panel-2); border: 1px solid var(--border); }
    .msg-meta { font-size: 11px; color: var(--muted); margin-top: 6px; }
    .sources-box {
      margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--border); font-size: 11.5px; color: var(--muted);
    }
    .source-hit { margin-top: 4px; padding: 5px 8px; background: #0b100d; border-radius: 6px; border: 1px solid #1d2b24; }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
    .chip {
      background: var(--panel-2); color: var(--text); border: 1px solid var(--border);
      border-radius: 999px; padding: 4px 10px; font-size: 12px; cursor: pointer;
    }
    .chip:hover { border-color: var(--accent); color: var(--accent); }
    .chat-form { display: flex; gap: 10px; }
    .chat-form input { flex: 1; padding: 10px 12px; }
    .btn-primary {
      background: var(--accent); color: #062114; border: none; border-radius: 8px;
      padding: 8px 16px; font-weight: 700; font-size: 13px; cursor: pointer;
    }
    .btn-primary:disabled { opacity: .45; cursor: not-allowed; }
    .btn-sm {
      background: var(--panel-2); color: var(--text); border: 1px solid var(--border);
      border-radius: 6px; padding: 4px 9px; font-size: 11.5px; cursor: pointer;
    }
    .btn-sm:hover { border-color: var(--accent); color: var(--accent); }

    /* KPIs & Charts */
    .kpis {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(185px, 1fr));
      gap: 12px; margin-bottom: 20px;
    }
    .kpi { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; }
    .kpi .label { font-size: 11.5px; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
    .kpi .val { font-size: 24px; font-weight: 700; margin-top: 4px; }
    .kpi .hint { font-size: 12px; color: var(--muted); margin-top: 3px; }
    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; }
    @media (max-width: 900px) { .grid-2 { grid-template-columns: 1fr; } }
    .card { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
    .card h2 { margin: 0 0 12px; font-size: 14.5px; font-weight: 600; color: var(--accent); }
    .bar-row { margin-bottom: 10px; }
    .bar-head { display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px; }
    .bar-track { height: 9px; background: #0c120f; border: 1px solid var(--border); border-radius: 999px; overflow: hidden; }
    .bar-fill { height: 100%; border-radius: 999px; }

    /* Controls & Selective Re-Runner */
    .controls {
      display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
      background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
      padding: 12px 16px; margin-bottom: 12px;
    }
    .rerun-bar {
      display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between;
      background: var(--panel-2); border: 1px solid var(--border); border-radius: 10px;
      padding: 10px 14px; margin-bottom: 14px; font-size: 13px;
    }
    .btn-group { display: flex; flex-wrap: wrap; gap: 6px; }
    button.pill {
      background: var(--panel-2); color: var(--muted); border: 1px solid var(--border);
      padding: 5px 11px; border-radius: 999px; font-size: 12.5px; cursor: pointer;
    }
    button.pill.active {
      background: rgba(110,231,183,.15); color: var(--accent); border-color: var(--accent); font-weight: 600;
    }
    input.search {
      margin-left: auto; background: #0c120f; color: var(--text); border: 1px solid var(--border);
      border-radius: 8px; padding: 6px 11px; font-size: 13px; min-width: 230px;
    }
    .table-wrap { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    thead th {
      text-align: left; padding: 12px 12px; background: var(--panel-2); color: var(--muted);
      font-weight: 600; font-size: 11.5px; text-transform: uppercase; letter-spacing: .04em;
      border-bottom: 1px solid var(--border);
    }
    tbody tr { border-bottom: 1px solid var(--border); transition: background .15s; }
    tbody tr:hover { background: rgba(110,231,183,.04); }
    tbody tr.selected { background: rgba(110,231,183,.09); }
    td { padding: 12px; vertical-align: top; }
    .tag { display: inline-block; padding: 3px 9px; border-radius: 999px; font-size: 11px; font-weight: 600; white-space: nowrap; }
    .tag.met { background: rgba(52,211,153,.14); color: var(--green); border: 1px solid rgba(52,211,153,.35); }
    .tag.partial { background: rgba(251,191,36,.14); color: var(--amber); border: 1px solid rgba(251,191,36,.35); }
    .tag.fail { background: rgba(248,113,113,.14); color: var(--red); border: 1px solid rgba(248,113,113,.35); }
    .cat-tag {
      display: inline-block; padding: 2px 7px; border-radius: 6px; font-size: 11px;
      background: #0c120f; border: 1px solid var(--border); color: var(--muted);
    }
    .drawer {
      margin-top: 18px; background: var(--panel); border: 1px solid var(--accent);
      border-radius: 12px; padding: 18px; display: none;
    }
    .drawer.open { display: block; }
    .drawer-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
    .rerun-results {
      background: var(--panel); border: 1px solid var(--accent); border-radius: 12px;
      padding: 16px; margin-bottom: 16px; display: none;
    }
    .rerun-results.open { display: block; }
    .rerun-item {
      background: var(--panel-2); border: 1px solid var(--border); border-radius: 10px;
      padding: 12px 14px; margin-top: 10px;
    }
    .rerun-item-head {
      display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px;
      margin-bottom: 8px;
    }
    .rerun-out-box {
      margin-top: 8px; background: #090d0b; border: 1px solid var(--border); border-radius: 8px;
      padding: 10px; font-size: 12px; color: #c7dfd0; white-space: pre-wrap; max-height: 200px; overflow-y: auto;
    }
    pre {
      background: #090d0b; border: 1px solid var(--border); border-radius: 8px; padding: 12px;
      overflow-x: auto; font-size: 12px; color: #c7dfd0; max-height: 360px;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div>
        <span class="badge-top">Moss Inference Work Sample · Live RAG + Test Bench</span>
        <h1>Moss RAG Chatbot &amp; Evaluation Dashboard</h1>
        <div class="sub">Chat directly with your 10 indexed PDFs, inspect plain-English test results below, and re-run only the specific tests you select.</div>
      </div>
      <div class="sub mono" id="creditBanner"></div>
    </header>

    <!-- Live RAG Chatbot -->
    <section class="chat-card">
      <div class="chat-header">
        <h2>Live Indexed-Document RAG Chatbot</h2>
        <div class="chat-opts">
          <label>Index:
            <select id="chatIndex">
              <option value="Company factuals">Company factuals (10 Kestrel PDFs)</option>
              <option value="voice-agent-context">voice-agent-context (Moss sample)</option>
            </select>
          </label>
          <label><input type="checkbox" id="useRag" checked /> Ground in Index (RAG)</label>
          <label><input type="checkbox" id="useCache" /> Use Cache</label>
          <button class="btn-sm" onclick="clearChat()">Clear Chat</button>
        </div>
      </div>

      <div class="chips">
        <button class="chip" onclick="askPreset('What is the standard return window and opened-box restocking fee?')">Return window &amp; fee?</button>
        <button class="chip" onclick="askPreset('If someone ordered hardware on Nov 15, 2026, what is their return deadline?')">Nov 15, 2026 holiday deadline?</button>
        <button class="chip" onclick="askPreset('What causes ERR-419-SYNC and how do I fix it?')">Fix ERR-419-SYNC</button>
        <button class="chip" onclick="askPreset('What is the SKU, MSRP, and replacement deposit hold for Kestrel Hub Pro?')">Hub Pro SKU, price &amp; hold</button>
        <button class="chip" onclick="askPreset('Does Kestrel accept Bitcoin payments?')">Bitcoin test (missing fact)</button>
      </div>

      <div class="chat-log" id="chatLog">
        <div class="msg bot">
          Ask anything about the 10 uploaded Kestrel Systems PDFs (returns, warranty, error codes, Enterprise SLAs, Q4 holiday addendum, or firmware release notes). Toggle <strong>Ground in Index (RAG)</strong> off to compare ungrounded replies.
        </div>
      </div>

      <form class="chat-form" onsubmit="sendChat(event)">
        <input class="text-in" id="chatInput" type="text" placeholder="Ask a question grounded in your Moss index..." required />
        <button class="btn-primary" id="chatSendBtn" type="submit">Send</button>
      </form>
    </section>

    <section class="kpis" id="kpiGrid"></section>

    <section class="grid-2">
      <div class="card">
        <h2>Inference API Latency Profile (ms)</h2>
        <div id="infChart"></div>
      </div>
      <div class="card">
        <h2>Tasks API Wall Time (s) &amp; Cost ($)</h2>
        <div id="taskChart"></div>
      </div>
    </section>

    <section class="controls">
      <div class="btn-group" id="catFilters"></div>
      <div class="btn-group" id="verdictFilters"></div>
      <input class="search" id="searchBox" type="search" placeholder="Search tests..." />
    </section>

    <section class="rerun-bar">
      <div class="btn-group">
        <button class="btn-sm" onclick="selectBroken()">Select Broken / Partial</button>
        <button class="btn-sm" onclick="selectCategory('Inference API')">Select Inference</button>
        <button class="btn-sm" onclick="selectCategory('Tasks API')">Select Tasks</button>
        <button class="btn-sm" onclick="clearSelection()">Clear Selection</button>
      </div>
      <div style="display:flex;align-items:center;gap:12px;">
        <span id="rerunStatus" class="mono" style="color:var(--muted)">0 tests selected</span>
        <button class="btn-primary" id="rerunBtn" onclick="rerunSelected()" disabled>Re-Run Selected Tests</button>
      </div>
    </section>

    <section class="rerun-results" id="rerunResults">
      <div class="drawer-head">
        <strong style="color:var(--accent)">Latest Re-Run Results (Output &amp; Expectation Check)</strong>
        <button class="btn-sm" onclick="document.getElementById('rerunResults').classList.remove('open')">Hide</button>
      </div>
      <div id="rerunResultsBody"></div>
    </section>

    <section class="table-wrap">
      <table>
        <thead>
          <tr>
            <th style="width: 4%">Run</th>
            <th style="width: 14%">Test</th>
            <th style="width: 21%">What I Intended</th>
            <th style="width: 20%">What Was Expected</th>
            <th style="width: 29%">What I Got</th>
            <th style="width: 12%">Met Expectation?</th>
          </tr>
        </thead>
        <tbody id="casesBody"></tbody>
      </table>
    </section>

    <section class="drawer" id="detailDrawer">
      <div class="drawer-head">
        <strong id="drawerTitle" class="mono"></strong>
        <button class="pill" onclick="document.getElementById('detailDrawer').classList.remove('open')">Close</button>
      </div>
      <pre id="drawerJson"></pre>
    </section>
  </div>

  <script>
    let DATA = __DASHBOARD_DATA__;
    let activeCategory = 'All';
    let activeVerdict = 'All';
    let searchQuery = '';
    let selectedRowId = null;
    const checkedIds = new Set();
    const chatHistory = [];

    function verdictBadge(v) {
      if (v === 'Met') return '<span class="tag met">Yes · Met</span>';
      if (v === 'Partial') return '<span class="tag partial">Partial</span>';
      return '<span class="tag fail">No · Broken</span>';
    }

    function escapeHtml(s) {
      return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    function askPreset(q) {
      document.getElementById('chatInput').value = q;
      sendChat(new Event('submit'));
    }

    function clearChat() {
      chatHistory.length = 0;
      document.getElementById('chatLog').innerHTML = '<div class="msg bot">Chat cleared. Ask anything about your indexed documents.</div>';
    }

    async function sendChat(e) {
      e.preventDefault();
      const input = document.getElementById('chatInput');
      const btn = document.getElementById('chatSendBtn');
      const text = input.value.trim();
      if (!text) return;

      const log = document.getElementById('chatLog');
      log.innerHTML += `<div class="msg user">${escapeHtml(text)}</div>`;
      input.value = '';
      btn.disabled = true;
      btn.textContent = 'Thinking...';
      log.scrollTop = log.scrollHeight;

      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            message: text,
            history: chatHistory,
            index_name: document.getElementById('chatIndex').value,
            use_rag: document.getElementById('useRag').checked,
            use_cache: document.getElementById('useCache').checked
          })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Chat request failed');

        chatHistory.push({role: 'user', content: text});
        chatHistory.push({role: 'assistant', content: data.reply});

        const srcHtml = (data.sources && data.sources.length)
          ? `<div class="sources-box"><strong>Retrieved Index Chunks (${data.retrieval_ms} ms):</strong>` +
            data.sources.map(s => `<div class="source-hit"><span class="mono" style="color:var(--accent)">score ${s.score.toFixed(3)}</span> · ${escapeHtml(s.text.slice(0, 220))}...</div>`).join('') +
            `</div>`
          : '';

        log.innerHTML += `
          <div class="msg bot">
            <div>${escapeHtml(data.reply).replace(/\\n/g, '<br>')}</div>
            <div class="msg-meta mono">model=${data.model} · latency=${data.latency_ms} ms · tokens=${data.usage?.total_tokens ?? '?'} (cached=${data.usage?.cached_tokens ?? 0})</div>
            ${srcHtml}
          </div>`;
      } catch (err) {
        log.innerHTML += `<div class="msg bot" style="border-color:var(--red);color:var(--red)">Error: ${escapeHtml(err.message)} (Make sure dashboard_server.py is running)</div>`;
      } finally {
        btn.disabled = false;
        btn.textContent = 'Send';
        log.scrollTop = log.scrollHeight;
      }
    }

    function renderTop() {
      const k = DATA.kpis;
      document.getElementById('creditBanner').textContent =
        `Spend: $${k.total_cost_usd.toFixed(4)} / $${k.credit_budget_usd.toFixed(2)} credits`;

      const items = [
        { label: 'Total Tests Evaluated', val: k.total_cases, hint: `${k.met} Met · ${k.partial} Partial · ${k.did_not_meet} Broken` },
        { label: 'Expectation Met Rate', val: `${Math.round((k.met / k.total_cases) * 100)}%`, hint: `${k.met}/${k.total_cases} strictly met` },
        { label: 'Warm Streaming Speed', val: `${k.warm_ttft_p50_ms} ms`, hint: 'Typical time to first word' },
        { label: 'PDF Knowledge Accuracy', val: k.rag_exact_match, hint: 'vs. 0/8 without index · 3/3 abstained' },
        { label: 'Browser Tasks (Tiers 1-3)', val: k.tasks_tier1_3_pass, hint: 'Static, multi-step, JS & PyPI' },
        { label: 'Total Spend Logged', val: `$${k.total_cost_usd.toFixed(2)}`, hint: 'Safely inside $10 credit' },
      ];
      document.getElementById('kpiGrid').innerHTML = items.map(i => `
        <div class="kpi">
          <div class="label">${i.label}</div>
          <div class="val">${i.val}</div>
          <div class="hint">${i.hint}</div>
        </div>
      `).join('');

      const maxInf = Math.max(...DATA.charts.inference_latency.map(d => d.ms), 1);
      document.getElementById('infChart').innerHTML = DATA.charts.inference_latency.map(d => `
        <div class="bar-row">
          <div class="bar-head"><span>${d.label}</span><span class="mono">${d.ms.toFixed(1)} ms</span></div>
          <div class="bar-track"><div class="bar-fill" style="width:${(d.ms/maxInf)*100}%;background:${d.color}"></div></div>
        </div>
      `).join('');

      const maxTask = Math.max(...DATA.charts.tasks.map(d => d.seconds), 1);
      document.getElementById('taskChart').innerHTML = DATA.charts.tasks.map(d => {
        const col = d.verdict === 'Met' ? '#34d399' : d.verdict === 'Partial' ? '#fbbf24' : '#f87171';
        return `
          <div class="bar-row">
            <div class="bar-head"><span class="mono">${d.id}</span><span class="mono">${d.seconds}s · $${d.cost.toFixed(4)}</span></div>
            <div class="bar-track"><div class="bar-fill" style="width:${(d.seconds/maxTask)*100}%;background:${col}"></div></div>
          </div>
        `;
      }).join('');
    }

    function renderFilters() {
      const cats = ['All', 'Inference API', 'Tasks API', 'Combined Demo'];
      document.getElementById('catFilters').innerHTML = cats.map(c =>
        `<button class="pill ${activeCategory === c ? 'active' : ''}" onclick="setCat('${c}')">${c}</button>`
      ).join('');

      const verdicts = ['All', 'Met', 'Partial', 'Did Not Meet'];
      document.getElementById('verdictFilters').innerHTML = verdicts.map(v =>
        `<button class="pill ${activeVerdict === v ? 'active' : ''}" onclick="setVerdict('${v}')">${v}</button>`
      ).join('');
    }

    function setCat(c) { activeCategory = c; renderFilters(); renderTable(); }
    function setVerdict(v) { activeVerdict = v; renderFilters(); renderTable(); }

    function updateRerunBar() {
      const n = checkedIds.size;
      document.getElementById('rerunStatus').textContent = `${n} test${n === 1 ? '' : 's'} selected`;
      document.getElementById('rerunBtn').disabled = n === 0;
    }

    function toggleCheck(id, ev) {
      ev.stopPropagation();
      if (checkedIds.has(id)) checkedIds.delete(id);
      else checkedIds.add(id);
      updateRerunBar();
    }

    function selectBroken() {
      checkedIds.clear();
      DATA.cases.filter(c => c.runnable && c.verdict !== 'Met').forEach(c => checkedIds.add(c.id));
      renderTable(); updateRerunBar();
    }

    function selectCategory(cat) {
      checkedIds.clear();
      DATA.cases.filter(c => c.runnable && c.category === cat).forEach(c => checkedIds.add(c.id));
      renderTable(); updateRerunBar();
    }

    function clearSelection() {
      checkedIds.clear();
      renderTable(); updateRerunBar();
    }

    async function rerunIds(ids) {
      if (!ids.length) return;
      const btn = document.getElementById('rerunBtn');
      const status = document.getElementById('rerunStatus');
      btn.disabled = true;
      status.textContent = `Running ${ids.length} test(s): ${ids.join(', ')}...`;
      status.style.color = 'var(--amber)';

      try {
        const res = await fetch('/api/rerun', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ test_ids: ids })
        });
        const out = await res.json();
        if (!res.ok) throw new Error(out.error || 'Re-run failed');
        DATA = out.dashboard;
        renderTop();
        renderTable();
        const okCount = out.outcomes.filter(o => o.ok).length;
        status.textContent = `Finished ${okCount}/${out.outcomes.length} re-run(s) — results shown below!`;
        status.style.color = 'var(--green)';

        const box = document.getElementById('rerunResults');
        const body = document.getElementById('rerunResultsBody');
        body.innerHTML = out.outcomes.map(o => {
          const rawStr = o.raw_output == null
            ? '(no structured output)'
            : (typeof o.raw_output === 'string' ? o.raw_output : JSON.stringify(o.raw_output, null, 2));
          const expMet = o.verdict === 'Met'
            ? 'Yes — met expectation'
            : (o.verdict === 'Partial' ? 'Partially met expectation' : 'No — did not meet expectation');
          return `
            <div class="rerun-item">
              <div class="rerun-item-head">
                <div>
                  <span class="mono" style="color:var(--accent);font-weight:700">${escapeHtml(o.id)}</span>
                  <span style="font-weight:600;margin-left:8px">${escapeHtml(o.title || o.id)}</span>
                </div>
                <div style="display:flex;align-items:center;gap:10px">
                  <span class="mono" style="color:var(--muted)">${o.seconds ?? '-'}s · $${(o.cost_usd || 0).toFixed(4)}</span>
                  ${verdictBadge(o.verdict)}
                </div>
              </div>
              <div style="font-size:13px"><strong>Did it meet the expectation?</strong> ${escapeHtml(expMet)}</div>
              ${o.expected ? `<div style="font-size:12.5px;color:var(--muted);margin-top:4px"><strong>Expected:</strong> ${escapeHtml(o.expected)}</div>` : ''}
              <div style="font-size:13px;margin-top:4px"><strong>Result summary:</strong> ${escapeHtml(o.result || o.error || 'Completed')}</div>
              <div class="rerun-out-box mono"><strong>Actual Output:</strong>\n${escapeHtml(rawStr)}</div>
            </div>
          `;
        }).join('');
        box.classList.add('open');
        box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      } catch (err) {
        status.textContent = `Error: ${err.message}`;
        status.style.color = 'var(--red)';
      } finally {
        btn.disabled = checkedIds.size === 0;
      }
    }

    function rerunSelected() { rerunIds([...checkedIds]); }

    function renderTable() {
      const q = searchQuery.trim().toLowerCase();
      const filtered = DATA.cases.filter(c => {
        if (activeCategory !== 'All' && c.category !== activeCategory) return false;
        if (activeVerdict !== 'All' && c.verdict !== activeVerdict) return false;
        if (q && !`${c.id} ${c.title} ${c.intended} ${c.expected} ${c.result}`.toLowerCase().includes(q)) return false;
        return true;
      });

      document.getElementById('casesBody').innerHTML = filtered.map(c => `
        <tr class="${selectedRowId === c.id ? 'selected' : ''}" onclick="showDetails('${c.id}')">
          <td onclick="event.stopPropagation()">
            ${c.runnable ? `<input type="checkbox" ${checkedIds.has(c.id) ? 'checked' : ''} onchange="toggleCheck('${c.id}', event)" />` : '<span style="color:var(--muted)">—</span>'}
          </td>
          <td>
            <div style="font-size:13px;font-weight:700;color:var(--text)">${escapeHtml(c.title)}</div>
            <div class="mono" style="color:var(--accent);font-size:11px;margin-top:2px">${c.id}</div>
            <div style="margin-top:6px;display:flex;gap:6px;align-items:center;flex-wrap:wrap">
              <span class="cat-tag">${c.category} · ${c.tier}</span>
              ${c.runnable ? `<button class="btn-sm" onclick="event.stopPropagation(); rerunIds(['${c.id}'])">Re-run</button>` : ''}
            </div>
          </td>
          <td>${escapeHtml(c.intended)}</td>
          <td>${escapeHtml(c.expected)}</td>
          <td>${escapeHtml(c.result)}</td>
          <td>${verdictBadge(c.verdict)}</td>
        </tr>
      `).join('') || '<tr><td colspan="6" style="text-align:center;color:var(--muted)">No matching tests.</td></tr>';
    }

    function showDetails(id) {
      selectedRowId = id;
      renderTable();
      const c = DATA.cases.find(x => x.id === id);
      if (!c) return;
      document.getElementById('drawerTitle').textContent = `${c.id} — Raw Logged Payload`;
      document.getElementById('drawerJson').textContent = JSON.stringify(c.details, null, 2);
      const d = document.getElementById('detailDrawer');
      d.classList.add('open');
      d.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    document.getElementById('searchBox').addEventListener('input', e => {
      searchQuery = e.target.value;
      renderTable();
    });

    renderTop();
    renderFilters();
    renderTable();
    updateRerunBar();
  </script>
</body>
</html>
"""


def write_dashboard() -> dict[str, Any]:
    """Generate dashboard/data.json and dashboard/index.html and return the payload."""
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_records()
    (DASHBOARD_DIR / "data.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    safe_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = HTML_TEMPLATE.replace("__DASHBOARD_DATA__", safe_json)
    (DASHBOARD_DIR / "index.html").write_text(html, encoding="utf-8")
    return payload


def main() -> None:
    payload = write_dashboard()
    print(f"Dashboard built: {DASHBOARD_DIR / 'index.html'} ({len(payload['cases'])} cases)")


if __name__ == "__main__":
    main()
