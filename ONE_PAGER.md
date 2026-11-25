# Moss Inference — Work Sample One-Pager

**Repo:** https://github.com/VarshilPorecha/moss-inference-eval

I evaluated Moss Portal (`portal.usemoss.dev/inference`), the Inference API, and the Tasks API (`moss` Python SDK `v1.26.0`) using a 10-PDF synthetic knowledge base (`fixtures/synthetic_kb/`) and a 4-tier automated test suite (`src/eval_inference.py`, `src/eval_tasks.py`, `src/demo_research_agent.py`), with raw logs committed under `logs/`. Total Tasks spend across all runs was under `$1.00`.

---

## 1. Portal (`portal.usemoss.dev/inference`)
- **Liked:** Fast time-to-aha-moment. Step 4 pre-seeds 50 sample docs and lets you run a `1.0 ms` in-browser search immediately, Step 5 supports drag-and-drop PDF/DOCX uploads (up to 20 files, 50 MB each), and Step 6 pre-fills `MOSS_PROJECT_ID`, a one-time `MOSS_PROJECT_KEY`, and your new index name (`"Company factuals"`).
- **Didn't like:** Entering through `portal.usemoss.dev/inference` puts you into a 6-step retrieval-only wizard (`MossClient.query`) with zero mention of `MossInference`, `tasks.run`, available models, or the `$10` credit balance. There is no clear "Skip to dashboard" button for API-first users, no index-build progress/chunking visibility (`"still building... within a few minutes"`), Step 6 outputs bash `export` commands that break on Windows PowerShell, and **2FA accepts an invalid phone number format and still shows `"OTP sent"`** instead of validating upfront.
- **What I'd improve once I join:** Add strict E.164 phone validation before 2FA OTP dispatch, create an Inference-specific onboarding path (or "Skip to Inference Playground" button), show live index-build progress with chunk count/OCR status, and expose a copy-ready PowerShell/env block plus live credit meter right on the final step.

## 2. Inference API (`responses.create` on `moss/fastlane-1`)
- **Liked:** Clean OpenAI Responses API parity (`output_text`, function tool calls, multi-turn `input`), fast warm streaming (**p50 TTFT `147.4 ms`**, **p50 total `632.4 ms`**, `5/5` exact stream-to-final text parity), dramatic response caching (**`396.7 ms` -> `57.6 ms`**), and reliable missing-fact abstention (`3/3` unindexed queries refused).
- **Didn't like / where it slipped:**
  - **Cold start + grounding overhead:** First streaming call hit `1977.7 ms` TTFT (`2411.6 ms` total), and uncached grounded calls had a **`+556.8 ms` median latency delta** over ungrounded calls.
  - **Multi-doc & multi-question recall:** Grounding hit `6/8` exact matches (`0/8` ungrounded), missing cross-doc/multi-part questions (`G4` pulled `$149` from Doc 03 but missed `$349` MSRP in Doc 05; the combined demo missed `ESC-KST-ENT1` in Doc 08 when 4 questions were asked at once). Also observed small `fastlane-1` fact slips (`G3` wrote `"5 GHz"` overlap instead of `"2.4 GHz"`; `G6` misquoted `"Nov 1 – Dec 24"` as `"Nov – Dec 1"`).
  - **Edge-case errors:** Passing `input=""` returned `200 completed` and hallucinated about an image (`87` input tokens) instead of rejecting empty input; passing a nonexistent index returned **`403 permission_error`** (`"index outside this project"`) instead of `404`.
- **What I'd improve once I join:** Reject empty `input` with `400`, return `404` for nonexistent indexes within the caller's project, and add optional query decomposition / multi-query retrieval or expose `top_k`/chunk citations in `Response` so multi-doc answers are inspectable.

## 3. Tasks API (`client.tasks.run` / `create` / `cancel` / `trace`)
- **What I tested:** 13 end-to-end runs across 4 tiers (`books.toscrape.com`, `quotes.toscrape.com` static + `/js/`, `pypi.org/project/moss/`, `httpbin.org/json`, `example.com`), plus `tasks.trace`, `tasks.files.list`, `cancel`, and parallel execution.
- **Liked:** Tiers 1–3 passed **6/6** (`23.8–38.5 s`, `$0.060–$0.081`/task, `100%` schema-valid, including JS-rendered pages and live PyPI metadata). On an impossible `< £1` goal, it honestly returned `found: false` instead of hallucinating. `tasks.trace` and `tasks.files` give rich step screenshots and timeline data.
- **Didn't like / where I broke it:**
  1. **Invalid `output_schema` still returned `status="completed"`:** In `T4_missing_required_isbn`, the page had no ISBN, `verification.passed` was `False` (`$.isbn_13: expected string`), yet `task.status` stayed `"completed"` (`error=None`). Callers checking only `status == "completed"` silently accept invalid outputs.
  2. **Minimum `max_runtime_seconds` floor & undocumented `400`:** Passing `max_runtime_seconds: 45` failed with `400: must be a number from 60 to 7200`—not documented in `TaskLimitsParam` docstrings.
  3. **Slow `cancel()` stop & missing `live_url`:** Calling `cancel()` 3s after `create(live_view=True)` returned `live_url=None`, took **~19s** to reach `cancelled`, executed 3 steps (`5` model calls), and billed `$0.0462`.
  4. **Budget cap overshoot & SDK cost mismatch:** `max_cost_usd=0.02` aborted quickly (`7.8s`, `budget_exceeded`), overshooting slightly (`$0.0248`, `0` files saved). Also, `TaskUsage.cost_usd` reports `model_usd` only, omitting `browser_usd` (`raw.cost.total_usd`).
  5. **Parallel variance:** Two identical concurrent `example.com` tasks succeeded, but took `50.08s` vs. `20.48s`.
