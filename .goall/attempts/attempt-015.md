# Attempt 015

- `attempt_id`: `015`
- `prompt_version`: `canonical_15_request_fixture_v1`
- `prompt_hash`: `sha256:B5B722B8AF45A3999C74632CBECE33BF9A3840BF103F60114770A858F884B009`
- `input_fixture_or_mode`: `focused stale/partial/unavailable deterministic holdout tests; no new live prompt`
- `model`: `not_run`
- `api_key_used`: `false; process env remains absent`
- `execution_command`: `.venv\\Scripts\\python.exe -m pytest -q tests/test_serving_and_restaurant.py tests/test_crawler.py tests/test_planner_end_to_end.py`
- `exit_code`: `0`
- `terminal_outcome`: `succeeded` (focused deterministic/data holdouts)
- `failed_stage_and_tool`: `none`
- `error_type`: `none`
- `corrective_action`: `none for existing tests; live key/network still required`
- `trace_file`: `not applicable; no application run`
- `test_result`: `23 focused tests passed; process OPENAI_API_KEY present=false`
- `next_minimal_change`: `next /goall starts at attempt 016 after provisioning a process-level key or explicitly choosing an offline text harness`

## Gate status

| Gate | Status |
|---|---|
| G1-G8 | not_run in this test-only attempt; prior attempts provide evidence |
| G9 | not_run; test artifacts do not reconcile a CLI plan with a trace |

## Interpretation

Stale, partial, crawler-failure, missing-cache, and planner data-unavailable behaviors are covered by the focused deterministic suite, but no live natural-language request reached those stages in this run.
