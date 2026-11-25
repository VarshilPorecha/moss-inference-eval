"""Generate Moss_Inference_Project_Report.pdf from live logs and project findings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pypdf import PdfReader

from src.build_dashboard import build_records, write_dashboard
from src.common import ROOT_DIR


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _norm(text: str) -> str:
    return (
        text.replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u2022", "-")
        .replace("\u00b7", "|")
        .replace("\u00a3", "GBP ")
        .encode("latin-1", errors="replace")
        .decode("latin-1")
    )


def _wrap(text: str, max_chars: int) -> list[str]:
    words = _norm(text).split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = words[0]
    for w in words[1:]:
        if len(cur) + 1 + len(w) <= max_chars:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


class ReportPDFBuilder:
    def __init__(self) -> None:
        self.page_w = 612
        self.page_h = 792
        self.margin_x = 48
        self.top_y = 744
        self.bottom_y = 54
        self.pages: list[list[str]] = [[]]
        self.y = self.top_y

    def _new_page(self) -> None:
        self.pages.append([])
        self.y = self.top_y

    def ensure(self, height: float) -> None:
        if self.y - height < self.bottom_y:
            self._new_page()

    def _draw_text(
        self,
        text: str,
        font: str,
        size: float,
        x: float,
        y: float,
        rgb: tuple[float, float, float] = (0.10, 0.12, 0.11),
    ) -> None:
        r, g, b = rgb
        self.pages[-1].append(
            f"{r:.2f} {g:.2f} {b:.2f} rg BT /{font} {size} Tf 1 0 0 1 {x:.1f} {y:.1f} Tm ({_pdf_escape(_norm(text))}) Tj ET 0 0 0 rg"
        )

    def add_banner(self, title: str, subtitle: str) -> None:
        self.pages[-1].append(
            f"0.07 0.25 0.18 rg {self.margin_x} {self.y - 54:.1f} {self.page_w - 2*self.margin_x} 66 re f"
        )
        self._draw_text(title, "F2", 16, self.margin_x + 14, self.y - 14, (0.92, 0.99, 0.95))
        self._draw_text(subtitle, "F1", 9.5, self.margin_x + 14, self.y - 34, (0.72, 0.93, 0.82))
        self.y -= 74

    def add_heading(self, text: str) -> None:
        self.ensure(38)
        self.y -= 6
        self._draw_text(text, "F2", 12.5, self.margin_x, self.y, (0.07, 0.34, 0.23))
        self.y -= 6
        self.pages[-1].append(
            f"0.75 0.85 0.80 RG 0.8 w {self.margin_x} {self.y:.1f} m {self.page_w - self.margin_x} {self.y:.1f} l S 0 0 0 RG"
        )
        self.y -= 14

    def add_subheading(self, text: str, rgb: tuple[float, float, float] = (0.12, 0.16, 0.14)) -> None:
        self.ensure(24)
        self._draw_text(text, "F2", 10.5, self.margin_x, self.y, rgb)
        self.y -= 14

    def add_para(self, text: str, indent: float = 0.0, size: float = 9.5) -> None:
        max_chars = int(94 - indent / 4.5)
        for line in _wrap(text, max_chars):
            self.ensure(15)
            self._draw_text(line, "F1", size, self.margin_x + indent, self.y)
            self.y -= 13
        self.y -= 4

    def add_bullet(self, label: str, text: str, indent: float = 10.0) -> None:
        combined = f"{label}: {text}" if label else text
        max_chars = int(90 - indent / 4.5)
        lines = _wrap(combined, max_chars)
        for idx, line in enumerate(lines):
            self.ensure(14)
            prefix = "- " if idx == 0 else "  "
            self._draw_text(prefix + line, "F1", 9.2, self.margin_x + indent, self.y)
            self.y -= 12.5
        self.y -= 2.5

    def add_case_block(self, case: dict[str, Any]) -> None:
        verdict = case["verdict"]
        v_rgb = (0.07, 0.45, 0.25) if verdict == "Met" else (0.65, 0.40, 0.02) if verdict == "Partial" else (0.70, 0.14, 0.14)
        self.ensure(62)
        header = f"[{verdict.upper()}] {case['id']} ({case['category']} - {case['tier']}): {case['title']}"
        for hline in _wrap(header, 88):
            self.ensure(14)
            self._draw_text(hline, "F2", 9.5, self.margin_x, self.y, v_rgb)
            self.y -= 12.5
        self.add_bullet("Intended", case["intended"], indent=10)
        self.add_bullet("Expected", case["expected"], indent=10)
        self.add_bullet("Result", case["result"], indent=10)
        self.y -= 3

    def save(self, output_path: Path) -> None:
        total = len(self.pages)
        for idx, ops in enumerate(self.pages, start=1):
            footer = f"Moss Inference Evaluation & Project Report  |  Varshil  |  Page {idx} of {total}"
            ops.append(
                f"0.45 0.50 0.48 rg BT /F1 8 Tf 1 0 0 1 {self.margin_x:.1f} 30.0 Tm ({_pdf_escape(_norm(footer))}) Tj ET 0 0 0 rg"
            )

        objects: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>"]
        page_ids = [5 + i * 2 for i in range(total)]
        kids = " ".join(f"{pid} 0 R" for pid in page_ids)
        objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {total} >>".encode("ascii"))
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")

        for ops in self.pages:
            cid = len(objects) + 2
            stream = "\n".join(ops).encode("latin-1", errors="replace")
            objects.append(
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {self.page_w} {self.page_h}] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {cid} 0 R >>".encode("ascii")
            )
            objects.append(
                f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream"
            )

        chunks = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
        offsets = [0]
        for i, body in enumerate(objects, start=1):
            offsets.append(sum(len(c) for c in chunks))
            chunks.append(f"{i} 0 obj\n".encode("ascii") + body + b"\nendobj\n")

        xref_off = sum(len(c) for c in chunks)
        xref = [f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"]
        for off in offsets[1:]:
            xref.append(f"{off:010d} 00000 n \n")
        trailer = f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_off}\n%%EOF\n"
        chunks.append("".join(xref).encode("ascii") + trailer.encode("ascii"))
        output_path.write_bytes(b"".join(chunks))


def generate_pdf() -> Path:
    data = build_records()
    k = data["kpis"]
    pdf = ReportPDFBuilder()

    pdf.add_banner(
        "Moss Inference Work Sample - Complete Project & Evaluation Report",
        f"Portal Audit | Inference API | Tasks API | Live RAG Chatbot | Total Cases: {k['total_cases']} | Spend: ${k['total_cost_usd']:.4f} / $10.00",
    )

    # 1. What We Built & Tried First
    pdf.add_heading("1. What We Built and What We Tried First")
    pdf.add_para(
        "This project evaluates Moss Inference across its entire developer surface: the web Portal (portal.usemoss.dev/inference), the Inference API, and the Tasks API, using the Python SDK (moss v1.26.0). Rather than running ad-hoc manual prompts, we built a reproducible test suite, raw JSONL audit logs, an end-to-end combined agent demo, a live indexed-document RAG chatbot, and an interactive evaluation dashboard."
    )
    pdf.add_bullet(
        "Step 1 - Portal Onboarding & 2FA Audit",
        "Walked through the 6-step onboarding flow, tested the pre-seeded 50-doc sample index ('voice-agent-context'), noted UX gaps during 2FA phone setup, and captured screenshots in notes/portal_onboarding_ux.pdf.",
    )
    pdf.add_bullet(
        "Step 2 - 10 Synthetic Knowledge-Base PDFs",
        "Created 10 realistic customer-support and hardware PDFs for a fictional company (Kestrel Systems, Inc.) inside fixtures/synthetic_kb/ and uploaded them into Moss index 'Company factuals' (chunked into 18 searchable documents).",
    )
    pdf.add_bullet(
        "Step 3 - Automated Evaluation Suites",
        "Built src/eval_inference.py (streaming TTFT, caching, RAG grounding, abstention, tool calling, multi-turn, error probes, concurrency) and src/eval_tasks.py (4 escalating browser tiers + break-it probes).",
    )
    pdf.add_bullet(
        "Step 4 - Combined Demo, Chatbot & Dashboard",
        "Built src/demo_research_agent.py (combining Tasks API + Moss Index + Inference API), plus src/dashboard_server.py and src/build_dashboard.py providing a live RAG chatbot and selective test re-runner.",
    )

    # 2. What Are Inference API & Tasks API?
    pdf.add_heading("2. What Are the Inference API and Tasks API?")
    pdf.add_bullet(
        "Moss Retrieval (MossClient)",
        "Moss's core semantic/hybrid search runtime. You upload documents (PDFs/DOCX/URLs) into an index, load the index into memory (load_index), and perform fast sub-50ms local similarity lookups (client.query).",
    )
    pdf.add_bullet(
        "Inference API (client.responses.create)",
        "An OpenAI Responses-compatible LLM gateway (https://inference.moss.dev/v1, default model moss/fastlane-1) that automatically retrieves relevant facts from your specified Moss indexes (indexes=[...]) and injects them into the model prompt before streaming or returning a reply. Supports tool calls, multi-turn conversations, reply caching (cache=True), and BYOK vendor models.",
    )
    pdf.add_bullet(
        "Tasks API (client.tasks.run / create / cancel / trace)",
        "An autonomous cloud browser agent runtime. Instead of writing fragile CSS/Playwright selectors, you give a plain-English goal, a starting URL (environment={'type': 'browser', 'start_url': ...}), an optional JSON output_schema, and runtime/cost limits. A remote browser executes multi-step clicks, JS waits, and extraction, then returns structured JSON, gateway schema verification, token/browser cost, step traces, and screenshots.",
    )

    # 3. End-to-End Pipeline Architecture
    pdf.add_heading("3. How the Entire Project Pipeline Works")
    pdf.add_para(
        "1) Knowledge Ingestion: 10 synthetic PDFs -> uploaded via Portal into index 'Company factuals' (18 indexed chunks) -> queried locally via MossClient or remotely via MossInference."
    )
    pdf.add_para(
        "2) Evaluation Execution: Python async scripts (eval_inference.py, eval_tasks.py, demo_research_agent.py) load credentials from .env, execute controlled tests against inference.moss.dev/v1, cross-check Tasks outputs locally using JSON Schema Draft7Validator, and append scrubbed telemetry to logs/*.jsonl."
    )
    pdf.add_para(
        "3) Interactive Dashboard & RAG Chatbot: src/build_dashboard.py aggregates the latest run per test ID into plain-language summaries (dashboard/index.html). src/dashboard_server.py serves the UI at localhost:8765, routes live user chat messages to MossClient.query (chunk preview) + MossInference.responses.create (/api/chat), and allows re-running any chosen subset of tests via src/test_runner.py (/api/rerun)."
    )

    # 4. How Tests Were Conducted
    pdf.add_heading("4. How Tests Were Conducted (Methodology & Guardrails)")
    pdf.add_bullet(
        "Preventing LLM Memorization",
        "We used fictional numbers (19-day return window, 12.5% fee, ERR-419-SYNC, 47-min P1 SLA, ESC-KST-409) absent from LLM training data, and ran every RAG prompt both ungrounded (retrieve=False) and grounded (indexes=['Company factuals']) to prove retrieval.",
    )
    pdf.add_bullet(
        "True Latency Measurement",
        "Streaming TTFT and RAG runs explicitly set cache=False so cached hits didn't mask real latency; caching was benchmarked separately with cache=True.",
    )
    pdf.add_bullet(
        "Budget & Timeout Protection",
        f"Every browser task enforced explicit limits (max_cost_usd $0.10-$0.35, max_runtime_seconds 60-120s). Total logged spend across all {k['total_cases']} evaluated cases was ${k['total_cost_usd']:.4f} out of the $10.00 credit.",
    )

    # 5. Summary & Full Test-by-Test Results
    pdf.add_heading("5. Tests Conducted & Pass/Fail Results")
    pdf.add_para(
        f"Overall Scorecard: {k['total_cases']} total cases evaluated | Met Expectation: {k['met']} | Partially Met: {k['partial']} | Failed / Broken: {k['did_not_meet']} | Warm Streaming TTFT p50: {k['warm_ttft_p50_ms']} ms | Synthetic KB Grounding: {k['rag_exact_match']} (vs. 0/8 ungrounded) | Tasks Tiers 1-3: {k['tasks_tier1_3_pass']}."
    )
    for case in data["cases"]:
        pdf.add_case_block(case)

    # 6. Challenges, Failed Tests, Real-World Impact & Fixes
    pdf.add_heading("6. Challenges, Real-World Impact & Recommended Fixes")

    findings = [
        (
            "1. Portal 2FA Accepts Invalid Phone Format & Says 'OTP Sent' (PORTAL-03)",
            "During 2FA setup, entering a malformed phone number still displays 'OTP sent' without rejecting the invalid format.",
            "Real-World Impact: Users never receive verification codes and get locked out; attackers or buggy clients can trigger wasted SMS carrier requests.",
            "Fix: Validate phone numbers against strict E.164 rules on both frontend form submit and backend /otp endpoint before sending SMS; return a clear 400 validation error.",
        ),
        (
            "2. Inference/Tasks & Credits Hidden in /inference Onboarding (PORTAL-02)",
            "Signing up via portal.usemoss.dev/inference runs a 6-step retrieval-only wizard without introducing Inference API, Tasks API, models, or the $10 credit balance; Step 6 emits bash 'export' commands on Windows.",
            "Real-World Impact: Developers evaluating Inference/Tasks feel lost during onboarding and Windows users hit copy-paste friction.",
            "Fix: Route /inference signups to an Inference/Tasks quickstart with a Skip-to-Dashboard option, live indexing progress, credit meter, and OS-tabbed env snippets (Bash + PowerShell).",
        ),
        (
            "3. Empty Input Returns 200 OK & Hallucinates About an Image (INF-ERR-EMPTY_INPUT)",
            "Calling responses.create(model='moss', input='') did not raise 400; it completed and replied 'Based on the image provided, I cannot determine...'.",
            "Real-World Impact: Production chatbots receiving an accidental blank string return bizarre hallucinated text to end users instead of catching a client bug.",
            "Fix: Enforce non-empty input validation at the API gateway and return 400 invalid_request_error immediately.",
        ),
        (
            "4. Nonexistent Index Returns 403 Instead of 404 (INF-ERR-NONEXISTENT_INDEX)",
            "Passing an unknown index name returned HTTP 403 permission_error ('index outside this project').",
            "Real-World Impact: Developers debugging a simple typo waste time troubleshooting IAM/project credentials instead of fixing the index name.",
            "Fix: Distinguish missing indexes from cross-project unauthorized indexes and return 404 not_found_error.",
        ),
        (
            "5. Multi-Doc / Multi-Part Recall Dilution & Small-Model Slips (G4, G3, G6, DEMO-01)",
            "Single-query retrieval missed secondary PDF chunks when a prompt spanned multiple documents (G4 missed $349 MSRP in PDF 05; DEMO-01 missed ESC-KST-ENT1 in PDF 08), and moss/fastlane-1 slipped on two details (5 GHz vs 2.4 GHz; Dec 1 vs Dec 24).",
            "Real-World Impact: Complex customer-support queries requiring policy overrides or multi-doc synthesis can omit critical rules or misstate numbers.",
            "Fix: Support optional query decomposition / multi-query retrieval, expose retrieved chunk citations in Response, and allow higher-accuracy model tiers for complex synthesis.",
        ),
        (
            "6. Tasks API Marks Failed Schema Validation as status='completed' (T4_missing_required_isbn)",
            "When a required field (isbn_13) did not exist on the page, verification.passed was False, yet task.status remained 'completed' with error=None.",
            "Real-World Impact: Downstream pipelines checking only task.status == 'completed' silently ingest null or broken records into databases.",
            "Fix: Introduce a distinct status (e.g., 'completed_invalid' or 'failed' with error.code='schema_validation_failed') or add strict_schema=True enforcement.",
        ),
        (
            "7. Slow Task Cancellation (~19s Lag) & Missing live_url (T4_cancel_lifecycle)",
            "Calling cancel() 3s after task creation still ran 5 model calls for ~19s ($0.0462 billed), and live_view=True returned live_url=None.",
            "Real-World Impact: Users aborting runaway jobs still pay for ~20s of extra compute, and operators cannot watch live browser runs for debugging.",
            "Fix: Check an immediate cancellation token between browser actions and populate live_url as soon as the browser session allocates.",
        ),
        (
            "8. Budget Cap Overshoot, Missing Trace Files & SDK Cost Mismatch (T4_budget_limit_probe)",
            "A $0.02 cap aborted cleanly (budget_exceeded) but overshot to $0.0248 (~25%) and saved 0 screenshots; also TaskUsage.cost_usd drops browser_usd found in raw.cost.total_usd.",
            "Real-World Impact: Unexpected billing drift on tight budgets, no visual debugging artifacts on failed runs, and inaccurate cost telemetry in user dashboards.",
            "Fix: Perform pre-call cost reservation before each model turn, flush captured screenshots on abort, and expose total_cost_usd on TaskUsage.",
        ),
        (
            "9. Undocumented 60s Runtime Floor & Parallel Latency Variance (T4_min_runtime_floor, T4_parallel_2)",
            "max_runtime_seconds=45 triggered a 400 error (must be 60..7200), undocumented in SDK docstrings; twin concurrent tasks showed 2.4x variance (50.08s vs 20.48s).",
            "Real-World Impact: Unexpected 400 errors in production integrations and unpredictable tail latency under concurrent workloads.",
            "Fix: Document min/max bounds in TaskLimitsParam (or validate client-side) and maintain pre-warmed browser pools to smooth cold-start queue jitter.",
        ),
    ]

    for title, what, impact, fix in findings:
        pdf.add_subheading(title, (0.55, 0.14, 0.14))
        pdf.add_bullet("Observed Issue", what, indent=8)
        pdf.add_bullet("Real-World Impact", impact.replace("Real-World Impact: ", ""), indent=8)
        pdf.add_bullet("How to Fix", fix.replace("Fix: ", ""), indent=8)
        pdf.y -= 3

    out_path = ROOT_DIR / "Moss_Inference_Project_Report.pdf"
    pdf.save(out_path)
    return out_path


def main() -> None:
    write_dashboard()
    out = generate_pdf()
    reader = PdfReader(str(out))
    total_chars = sum(len(p.extract_text() or "") for p in reader.pages)
    size_kb = out.stat().st_size / 1024.0
    print(f"Generated {out} ({len(reader.pages)} pages, {size_kb:.1f} KB, {total_chars} extracted chars)")


if __name__ == "__main__":
    main()
