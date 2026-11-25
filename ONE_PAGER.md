# Moss Inference — Work Sample One-Pager

- **What I ran:** `37` automated test cases (`89` total API calls, `$1.1292` cumulative Tasks + Demo spend out of `$10.00` credits) + `3` Portal UX checks on **`moss` Python SDK `v1.26.0`**.
- **Links:** [GitHub Repo](https://github.com/VarshilPorecha/moss-inference-eval) · [Full 9-Page Report PDF](https://github.com/VarshilPorecha/moss-inference-eval/blob/main/Moss_Inference_Project_Report.pdf) · [Interactive Dashboard](https://github.com/VarshilPorecha/moss-inference-eval/tree/main/dashboard) *(note: live re-runs are locked on public Render hosting to protect credits)*.

---

## 1. Portal (`portal.usemoss.dev/inference`)
- **Liked:** Fast time-to-first-search—Step 4 seeds 50 sample docs (`voice-agent-context`) and runs an interactive `1.0 ms` browser search right inside onboarding, and Step 5 accepts drag-and-drop PDFs (`10` synthetic PDFs indexed as `18` chunks).
- **Disliked:**
  1. Signing up via `/inference` runs a 6-step retrieval-only wizard that hides Inference API, Tasks API, models, and the `$10` credit balance until *Go to dashboard*, and Step 6 emits bash `export` commands that fail on Windows PowerShell.
  2. **2FA phone bug (observed):** Entering a malformed phone number still displays `"OTP sent"` instead of rejecting the format upfront *(likely impact: users mistyping numbers may not receive codes and get stuck)*.
- **Improve:** Add an Inference/Tasks quickstart path with a PowerShell env tab, live index progress, and E.164 phone validation before OTP dispatch.

## 2. Inference API (`responses.create` on `moss/fastlane-1`)
*(Small sample sizes: `n=5` TTFT runs, `n=8` synthetic RAG questions, `n=3` abstention checks.)*
- **Liked:** Grounding clearly worked (**`6/8`** exact matches vs. **`0/8`** ungrounded), **`3/3`** unindexed questions abstained cleanly, warm streaming TTFT was ~`140 ms` (`140.1 ms` p50 across 4 warm runs; `960.6 ms`–`3454.0 ms` cold first runs), and BYOK `400` / invalid-key `401` errors were clear.
- **Disliked:**
  - **Latency vs. headline & grounded overhead:** Local `MossClient.query()` on our loaded 18-chunk index measured `19.2 ms` (`40.0 ms` on first cold run) vs. `1.0 ms` in the Portal playground and Moss's sub-10 ms headline. Grounded `responses.create` calls were also often slower than ungrounded calls (e.g., `G5`: `927 ms` grounded vs. `146 ms` ungrounded).
  - **Cache (`INF-CACHE`):** Caching saved token billing (`1,198 -> 0` input tokens on repeat), but showed no latency gain on warm repeat (`56.0 ms` vs. `54.4 ms`, `1.0x`), marked **Partial**.
  - **Edge cases & recall:** Empty `input=""` returned `200` with an image-related reply; a nonexistent index returned **`403 permission_error`** instead of `404`; multi-doc question `G4` missed `$349` MSRP in PDF 05 (`SKU-KHP-900` + `$149` came from PDF 03).
- **Improve:** Return `400` on empty input, `404` on unknown project indexes, and add retrieved chunk citations plus optional multi-query retrieval for cross-doc questions.

## 3. Tasks API (`client.tasks.run` / `create` / `cancel` / `trace`)
Tested 4 difficulty tiers (`Tiers 1–3` passed **`6/6`**, `23.8–38.5 s`, `$0.060–$0.081`/task, including JS-rendered pages and live PyPI metadata) plus adversarial break-it probes (`Tier 4`):
- **Biggest bug — failed schema check still returns `status="completed"` (`T4_missing_required_isbn`):** When `isbn_13` wasn't on the page, `verification.passed` was `False` (`$.isbn_13: expected string`), yet `task.status` stayed `"completed"` (`error=None`). Any pipeline checking only `status == "completed"` silently accepts invalid `null` data.
- **Slow `cancel()` & billing (`T4_cancel_lifecycle`):** Calling `cancel()` `3 s` after creation (`live_view=True`) returned `live_url=None`, took **~`19 s`** more to reach `cancelled` (`5` model calls), and billed **`$0.0462`** (`total_usd`).
- **Other break-it findings:** `max_cost_usd=0.02` (`T4_budget_limit_probe`) aborted with `budget_exceeded` in `7.8 s` but overshot by `25.5%` to **`$0.0251`** (`0` screenshots saved; `TaskUsage.cost_usd` reports `$0.0248` model-only and drops `browser_usd`); `max_runtime_seconds=45` hit an undocumented **`60–7200 s`** floor (`T4_min_runtime_floor`); and twin `example.com` tasks varied `2.4x` (`50.1 s` vs. `20.5 s` in `T4_parallel_2`).

## First Thing I'd Ship If I Joined
Enforce a distinct status (`failed` / `completed_invalid`) when `output_schema` verification fails in Tasks API alongside an immediate between-step cancellation check, then build the `/inference` onboarding quickstart.
