# Moss Inference Evaluation & Stress-Test Suite

Reproducible evaluation harness, adversarial "break-it" test suite, raw JSONL execution logs, and end-to-end showcase built for the **Moss Inference** technical work sample.

## What Is Included

```text
.
├── README.md                     # Project overview, setup, test plan, and reproduction steps
├── requirements.txt              # Python dependencies
├── .env.example                  # Required environment variables
├── render.yaml                   # Render Web Service blueprint
├── Procfile                      # Process start command
├── .python-version               # Pinned Python 3.12.8 for Render
├── fixtures/
│   └── synthetic_kb/             # 10 synthetic PDFs (Kestrel Systems KB) uploaded to Moss index
├── notes/
│   └── portal_audit.md           # UX/DX/2FA observations from portal.usemoss.dev/inference
├── dashboard/
│   ├── index.html                # Interactive RAG chatbot + plain-English test bench UI
│   └── data.json                 # Aggregated evaluation dataset
├── src/
│   ├── common.py                 # Client helpers, JSONL logger, cost tracker, schema validator
│   ├── eval_inference.py         # Inference API suite (streaming, RAG grounding, errors, burst)
│   ├── eval_tasks.py             # Tasks API tiered benchmark & adversarial break-it suite
│   ├── demo_research_agent.py    # Mini app combining Tasks API + Moss retrieval + Inference API
│   ├── summarize_results.py      # Aggregates logs/*.jsonl into Markdown metrics tables
│   ├── test_runner.py            # Selective test runner invoked by the interactive UI
│   ├── build_dashboard.py        # Generates dashboard/index.html & data.json from logs/*.jsonl
│   ├── dashboard_server.py       # Local/Render server for live RAG chat & guarded re-runs
│   └── generate_report_pdf.py    # Optional local PDF report generator
└── logs/
    ├── inference_runs.jsonl      # Raw Inference API run logs (secrets scrubbed)
    ├── tasks_runs.jsonl          # Raw Tasks API run logs (secrets scrubbed)
    ├── demo_runs.jsonl           # Combined demo run log (secrets scrubbed)
    └── summary_report.md         # Aggregated Markdown metrics report
```

## Prerequisites

- **Python 3.11+**
- A Moss Inference account created via `https://portal.usemoss.dev/inference`
- A populated Moss index (these tests target the 10 synthetic PDFs in `fixtures/synthetic_kb/` loaded into index `"Company factuals"`)

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env with your MOSS_PROJECT_ID and MOSS_PROJECT_KEY
```

## Test Plan & Benchmarks

### 1. Portal Audit (`notes/portal_audit.md`)
Tracks onboarding friction, index creation UX, SDK snippet accuracy, model/credit visibility, and task trace observability.

### 2. Inference API Evaluation (`src/eval_inference.py`)
- **Baseline & Parameter Parity:** Non-streaming `responses.create` calls.
- **Streaming Parity & TTFT:** Measures Time-to-First-Token (`p50`/`p95`) and compares streamed deltas against full `output_text`.
- **Synthetic RAG Grounding:** Queries facts unique to `fixtures/synthetic_kb/` (e.g., `19 calendar days`, `12.5%` restocking fee, `ERR-419-SYNC`, `47-minute` SLA, Q4 holiday addendum precedence) with and without `indexes`.
- **Abstention / Hallucination Control:** Queries facts intentionally absent from all 10 PDFs.
- **Error Handling & Concurrency:** Invalid key, nonexistent index, empty input, and async burst behavior.

### 3. Tasks API Functional & "Break-It" Suite (`src/eval_tasks.py`)
Runs 4 escalating tiers while logging duration, status, tokens, cost, and schema adherence:
- **Tier 1 (Happy Path):** Single-page structured extraction against strict `output_schema`.
- **Tier 2 (Multi-Step Navigation):** Landing page -> search/category/pagination -> extraction.
- **Tier 3 (Dynamic / JS UI):** Client-side rendered pages and interactive controls.
- **Tier 4 (Adversarial / Break-It):**
  - Unsatisfiable goal (verifies fail-fast vs. credit-burning loops)
  - Missing schema fields (checks `null` vs. fabricated values)
  - Deeply nested schema with enums & numeric bounds
  - Broken `start_url` (404 / non-HTML JSON endpoint)
  - Background run / cancellation / parallel tasks (within SDK capabilities)

### 4. End-to-End Demo (`src/demo_research_agent.py`)
Uses the **Tasks API** to gather live structured web information, grounds the **Inference API** with that context + the Moss KB index, and streams a concise recommendation.

## Running the Suite

```powershell
python -m src.eval_inference
python -m src.eval_tasks --tier 1
python -m src.eval_tasks --tier 2
python -m src.eval_tasks --tier 3
python -m src.eval_tasks --tier 4
python -m src.demo_research_agent
python -m src.summarize_results
python -m src.dashboard_server
```

## Deploying to Render

Includes `render.yaml`, `.python-version` (`3.12.8`), and `Procfile` for one-click or manual Render Web Service deployment:
- **Runtime:** Python 3
- **Build Command:** `pip install -r requirements.txt && python -m src.build_dashboard`
- **Start Command:** `python -m src.dashboard_server`
- **Health Check Path:** `/healthz`
- **Environment Variables:** `MOSS_PROJECT_ID`, `MOSS_PROJECT_KEY`, `MOSS_INFERENCE_URL=https://inference.moss.dev/v1`, `MOSS_INDEX_NAME=Company factuals`, `PYTHONUNBUFFERED=1`
