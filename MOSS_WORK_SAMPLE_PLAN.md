# Moss Inference Work Sample — Execution Plan

> **Objective:** Evaluate **Moss Inference** (Portal, Inference API, Tasks API) systematically, find where it shines and where it breaks, publish reproducible code + logs on GitHub, and distill findings into a crisp **1-page memo**.
> **Budget Constraint:** $10.00 sign-up credits (target total spend ~$4–$7 so we have headroom for re-runs without waiting on top-ups).

---

## 1. What We Will Build

Instead of ad-hoc one-off scripts, we will build a lightweight, reproducible **Evaluation & Stress-Test Suite** plus a **Minimal End-to-End Demo** in this repository:

```text
moss-inference-eval/
├── README.md                     # Setup, how to reproduce, summary of findings
├── ONE_PAGER.md                  # Final 1-page plain-English memo (exported to PDF for email)
├── .env.example                  # MOSS_PROJECT_ID, MOSS_PROJECT_KEY, MOSS_INFERENCE_URL
├── requirements.txt              # moss, pydantic, jsonschema, rich, python-dotenv, httpx
├── fixtures/
│   └── synthetic_kb/             # 5-10 private/fictional docs to test true RAG grounding
├── notes/
│   └── portal_audit.md           # Timestamped UX & DX notes from portal.usemoss.dev/inference
├── src/
│   ├── common.py                 # Client init, JSONL logger, cost/credit tracker, schema validator
│   ├── eval_inference.py         # Inference API functional, streaming, grounding & stress tests
│   ├── eval_tasks.py             # Tasks API tiered benchmark + "break-it" adversarial tests
│   ├── demo_research_agent.py    # Mini app: Tasks API gathers live web data -> Moss index -> Inference API Q&A
│   └── summarize_results.py      # Parses logs/*.jsonl into Markdown tables & failure taxonomy
└── logs/                         # Committed raw JSONL outputs (secrets scrubbed) as proof of runs
    ├── inference_runs.jsonl
    └── tasks_runs.jsonl
```

### Why this structure works for a hiring review
1. **Proof of work:** Every claim in the 1-pager maps directly to a script in `src/` and raw run records in `logs/`.
2. **Product + systems thinking:** `demo_research_agent.py` shows we understand how Moss's retrieval indexes, Inference API, and Tasks API compose into a real product—not just isolated API calls.
3. **Budget safety:** Each run logs latency, token counts, and reported cost so we don't accidentally drain the $10 credit in an infinite retry loop.

---

## 2. Prerequisites (Before Writing Any Code)

### A. Account & Portal Setup
1. Sign up strictly via **`https://portal.usemoss.dev/inference`** (so Inference + Tasks access and the $10 sign-up credits activate properly).
2. Capture **first-impression UX notes** immediately during onboarding (broken links, confusing labels, latency, docs clarity—these are gold for Section 1 of the one-pager).
3. Create a project and copy `MOSS_PROJECT_ID` and `MOSS_PROJECT_KEY`.
4. Check in the Portal:
   - Available models / whether BYOK (OpenAI/Anthropic/Google keys) is required or Moss-hosted models are included with credits.
   - How to create and populate a Moss search index (via Portal UI vs. SDK).
   - Rate limits, max task timeout/step limits, and where usage/credit burn is displayed.

### B. Local Dev Environment
1. **Python 3.11+** (or Node.js 20+ if also spot-checking `@moss-js/moss` / `@moss-dev/moss-web` SDK parity).
2. **Install & Inspect the SDK:**
   - Install `moss` in a local `.venv`.
   - Inspect the exact installed SDK signatures (`MossInference`, `client.responses.create`, `client.tasks.run`, polling/cancel methods, error classes) before coding tests, since SDK docs and releases can drift.
3. **Git & GitHub:**
   - Initialize repo with `.gitignore` excluding `.env` and `.venv/`.
   - Confirm no API keys or PII are ever logged to `logs/*.jsonl`.

### C. Test Fixtures
1. **Synthetic Knowledge Base (`fixtures/synthetic_kb/`):**
   - Create short docs with **invented facts** (e.g., fictional company policies, release dates, error codes like `ERR-MOSS-9042`) that *cannot* exist in any LLM's pretraining data. This guarantees our grounding test proves Moss index retrieval works.
2. **Stable Public Web Targets (for Tasks API):**
   - Pick deterministic, non-login, non-CAPTCHA public pages (e.g., `books.toscrape.com`, `quotes.toscrape.com`, Hacker News, Wikipedia, public GitHub repo pages, and a static/JS test page) so failures reflect the Tasks API rather than third-party anti-bot walls.

---

## 3. Tests We Will Conduct

### Part 1: Portal Audit (`portal.usemoss.dev/inference`)
- **Onboarding & Key Management:** Signup flow, time-to-first-API-call, key scoping/rotation, `.env` copy ergonomics.
- **Playground / Sandbox (if present):** Can we test Inference and Tasks directly in the UI before writing code?
- **Observability & Debugging:** After running API calls and failed Tasks, inspect the Portal:
  - Are request logs, TTFT/latency, token counts, and credit deductions visible in near real-time?
  - For Tasks API runs, can we see step-by-step browser actions, screenshots/DOM state, and exact failure reasons?
- **Docs-to-Portal Alignment:** Do Portal code snippets match the current SDK signatures?

### Part 2: Inference API Tests (`src/eval_inference.py`)
1. **Basic Completion & Responses API Parity:**
   - Standard `responses.create(instructions=..., input=...)`.
   - Test available models, parameter support (`temperature`, `max_output_tokens`, structured outputs if supported).
2. **Streaming (`stream=True`):**
   - Verify chunk/delta ordering (`event.delta`), completion event, and exact parity between concatenated streamed text and non-streamed `output_text`.
3. **Moss Index Grounding (RAG):**
   - Query facts present *only* in `synthetic_kb` with `indexes=[...]` vs. without `indexes`.
   - Query facts *absent* from the index to test hallucination resistance / refusal behavior.
   - Compare latency overhead of grounded vs. ungrounded calls.
4. **Error Handling & Concurrency:**
   - Invalid project key, nonexistent index name, empty `input`, oversized input.
   - Small async burst (e.g., 5–10 concurrent calls) to inspect rate-limit headers (`429`), retryability, and exception clarity.

### Part 3: Tasks API Tests & "Break-It" Suite (`src/eval_tasks.py`)

We will test in **4 escalating tiers**, checking credit balance after each tier:

- **Tier 1 — Happy Path (Single-Page Structured Extraction):**
  - Extract a list of items (title, price, availability) from a clean catalog page using a strict `output_schema`.
  - Verify exact field match against ground truth scraped deterministically.
- **Tier 2 — Multi-Step Navigation & Filtering:**
  - Start on a landing/search page, navigate through a category/filter or pagination (page 1 -> page 2), and extract aggregated results.
- **Tier 3 — Dynamic UI / JS-Rendered Content:**
  - Pages with client-side JS rendering, tabs, accordions, or dismissible popups/banners.
- **Tier 4 — Adversarial / "Break-It" Probes (Crucial for the prompt):**
  1. **Impossible / Nonexistent Goal:** Ask the agent to find an item that does not exist on the target site (e.g., `"Find a laptop under $1"`). *Check: Does it terminate cleanly and report not found, loop until timeout, or hallucinate an answer?*
  2. **Missing Schema Fields:** Request an `output_schema` field that isn't on the page (e.g., `sku_barcode` when none exists). *Check: Does schema validation fail, return `null`, or fabricate values?*
  3. **Complex / Deeply Nested `output_schema`:** Nested objects + arrays + enums + numeric constraints. *Check: Where does schema enforcement break?*
  4. **Broken / Edge `start_url`:** 404 page, non-HTML endpoint (JSON/PDF), malformed URL, slow-loading page. *Check: Error payload quality and whether credits are still charged.*
  5. **Non-Blocking Lifecycle & Cancellation (if supported):** Trigger background task, poll status transitions, cancel mid-execution, verify final status and billing stop.
  6. **Parallel Tasks:** Launch 3 tasks concurrently via `asyncio.gather`. *Check: Session concurrency limits, queueing latency, or silent drops.*

### Part 4: Mini Composed App (`src/demo_research_agent.py`)
- **Flow:** Given a topic/URL (e.g., compare pricing/features across 2 public dev-tool pages), **Tasks API** extracts structured specs -> saves into a **Moss index** -> **Inference API** runs grounded streaming Q&A over the newly collected data.
- **Purpose:** Tests whether Tasks API output flows cleanly into Moss's retrieval + Inference pipeline and uncovers friction points between the two APIs.

---

## 4. Benchmarks & Evaluation Criteria

To objectively classify features as **Working**, **Broken**, or **Needs Improvement**, we will measure:

### A. Inference API Benchmarks
| Metric | How We Measure | Working / Good | Needs Improvement | Broken / Bug |
| :--- | :--- | :--- | :--- | :--- |
| **TTFT (Streaming)** | Time from request send to first `event.delta` (10 runs) | p50 < 800 ms, p95 < 1.5 s | p50 1–2 s or high jitter | Timeout, buffered all-at-once, or > 3 s |
| **Grounding Latency Delta** | `latency(with indexes) - latency(without indexes)` | Minimal overhead (< 100 ms e2e) | 200–800 ms overhead | Retrieval fails silently or > 1 s overhead |
| **Grounding Accuracy** | % of `synthetic_kb` questions answered accurately | 100% factual on indexed facts | Misses facts without tuning | Hallucinates or ignores `indexes` |
| **Abstention Accuracy** | % of unindexed questions correctly refused | Refuses / states unknown | Hedged partial hallucination | Invents confident fake answer |
| **Error Ergonomics** | Inspect exception type, HTTP code, message on bad input | Actionable message + clean code | Generic `500` or vague text | Unhandled crash / silent fallback |

### B. Tasks API Benchmarks
| Metric | How We Measure | Working / Good | Needs Improvement | Broken / Bug |
| :--- | :--- | :--- | :--- | :--- |
| **Task Completion Rate (TCR)** | `completed` & factually verified / total runs per tier | >= 90% T1, >= 75% T2–T3 | 50–75% or flaky across retries | < 50% or deterministic failures |
| **Schema Adherence** | % of `output` payloads passing `pydantic`/`jsonschema` | 100% strict match | Missing optionals / wrong types | Invalid JSON or ignores schema |
| **Wall-Clock Duration** | p50 / p95 seconds from `tasks.run` start to return | Predictable (< 30–60 s for T1–T2) | Slow (> 90 s) for simple pages | Hangs indefinitely / hits hard timeout |
| **Cost per Task** | Sum of `cost` / tokens + browser session duration | Transparent & < $0.10–$0.25/run | High burn on simple pages | Runaway loop draining credits on failure |
| **Graceful Failure** | Behavior on 404, impossible goal, missing data | Fast fail + clear `task.error` | Slow fail with vague error | Fabricates data to satisfy schema or hangs |

---

## 5. Step-by-Step Execution Order

1. **Step 1 — Portal Signup & Audit:** Sign up at `https://portal.usemoss.dev/inference`, grab credentials, document Portal UX immediately in `notes/portal_audit.md`.
2. **Step 2 — SDK Inspection:** Install `moss` locally, inspect actual classes/methods/types, verify exact `Inference` & `Tasks` signatures.
3. **Step 3 — Inference API Suite:** Run `eval_inference.py` (target spend: ~$0.50–$1.00).
4. **Step 4 — Tasks API Suite:** Run `eval_tasks.py` Tier 1 -> Tier 4 one tier at a time, verifying credit balance after each tier (target spend: ~$3.00–$5.00).
5. **Step 5 — Mini Demo + Aggregation:** Build & run `demo_research_agent.py` (~$0.50), then run `summarize_results.py` to generate exact metrics tables from `logs/*.jsonl`.
6. **Step 6 — Polish Repo & Write One-Pager:** Scrub any sensitive tokens, push to GitHub, write `ONE_PAGER.md` (strictly <= 1 page when exported, plain language, concrete numbers + repo link), and send email.
