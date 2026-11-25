# Moss Inference Evaluation — Automated Summary

## 1. Inference API Metrics

| Metric | Result |
| :--- | :--- |
| Streaming TTFT (uncached, n=5) | p50=147.4 ms, p95=1977.7 ms |
| Streaming Total Latency (n=5) | p50=632.4 ms, p95=2411.6 ms |
| Stream vs. Final Text Parity | 5/5 |
| Cache Check (pass 1 vs. pass 2) | 396.65 ms -> 57.58 ms |
| Synthetic KB Grounding Accuracy | 6/8 (vs. 0/8 ungrounded) |
| Grounding Latency Delta (median) | +556.8 ms |
| Missing-Fact Abstention Rate | 3/3 |

### Inference Error & Edge Probes

- `nonexistent_index`: raised=True status=403 type=permission_error msg=X-Moss-Indexes names an index outside this project
- `empty_input`: raised=False status=completed type=None msg=None
- `invalid_model_no_byok`: raised=True status=400 type=invalid_request_error msg=Model gpt-4o-mini runs on your own openai key. Send the key in the X-Moss-Provider-Key header, or send model moss/fastlane-1.
- `invalid_key`: raised=True status=401 type=authentication_error msg=The project credentials were rejected

## 2. Tasks API Metrics

**Total Logged Tasks Spend (model_usd):** $0.8922

| Case ID | Tier | Status | Wall (s) | Cost ($) | GW Verif | Local Schema | Error |
| :--- | :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `T1_books_top5` | 1 | completed | 27.93 | 0.0614 | True | True | - |
| `T1_quotes_top5` | 1 | completed | 26.75 | 0.0635 | True | True | - |
| `T2_books_science_extremes` | 2 | completed | 30.87 | 0.0685 | True | True | - |
| `T2_quotes_page2_life` | 2 | completed | 38.45 | 0.0809 | True | True | - |
| `T3_js_rendered_quotes` | 3 | completed | 23.82 | 0.0598 | True | True | - |
| `T3_pypi_moss_metadata` | 3 | completed | 33.51 | 0.0737 | True | True | - |
| `T4_impossible_price_goal` | 4 | completed | 35.66 | 0.0697 | True | True | - |
| `T4_missing_required_isbn` | 4 | completed | 29.85 | 0.0644 | False | False | - |
| `T4_strict_nested_enum` | 4 | completed | 19.68 | 0.0585 | True | True | - |
| `T4_broken_404_url` | 4 | 400 | 0.35 | - | None | None | invalid_request_error |
| `T4_non_html_json_url` | 4 | 400 | 0.35 | - | None | None | invalid_request_error |
| `T4_broken_404_url` | 4 | completed | 18.41 | 0.0528 | True | True | - |
| `T4_non_html_json_url` | 4 | completed | 19.61 | 0.0542 | True | True | - |
| `T4_budget_limit_probe` | 4 | failed | 7.82 | 0.0248 | None | False | budget_exceeded |

### Tasks Lifecycle & Parallel Probes

- `T4_cancel_lifecycle`: {"timestamp_utc": "2026-11-25T14:42:23.319091+00:00", "test_group": "lifecycle_cancel", "case_id": "T4_cancel_lifecycle", "tier": 4, "wall_seconds": 20.6, "created_status": "queued", "live_url_present": false, "cancel_ack_status": "running", "cancel_ack_reques
- `T4_parallel_2`: {"timestamp_utc": "2026-11-25T14:42:23.890017+00:00", "test_group": "parallel_tasks", "case_id": "T4_parallel_2", "tier": 4, "wall_seconds": 0.57, "results": [{"idx": 1, "error": "limits.max_runtime_seconds must be a number from 60 to 7200", "type": "invalid_r
- `T4_parallel_2`: {"timestamp_utc": "2026-11-25T14:45:05.799433+00:00", "test_group": "parallel_tasks", "case_id": "T4_parallel_2", "tier": 4, "wall_seconds": 50.08, "results": [{"idx": 1, "status": "completed", "wall_s": 50.08, "cost_usd": 0.057199}, {"idx": 2, "status": "comp

## 3. Combined Demo Run

- Tasks duration: 29.31s | Inference duration: 3.03s
