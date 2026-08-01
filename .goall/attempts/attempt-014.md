# Attempt 014

- `attempt_id`: `014`
- `prompt_version`: `canonical_15_request_fixture_v1`
- `prompt_hash`: `sha256:B5B722B8AF45A3999C74632CBECE33BF9A3840BF103F60114770A858F884B009`
- `input_fixture_or_mode`: `verification mode; no new model or planner prompt`
- `model`: `not_run`
- `api_key_used`: `false`
- `execution_command`: `.venv\\Scripts\\python.exe -m pytest -q; .venv\\Scripts\\group-food-schemas.exe --output schemas; .venv\\Scripts\\python.exe -m pip check`
- `exit_code`: `0` for all corrected commands
- `terminal_outcome`: `succeeded` (verification-only)
- `failed_stage_and_tool`: `none; an initial shell path typo was corrected before recording the verification result`
- `error_type`: `none after correction`
- `corrective_action`: `none`
- `trace_file`: `not applicable; prior traces 001, 011, 012, 013 inspected`
- `test_result`: `60 passed; 23 schemas generated; pip check clean`
- `next_minimal_change`: `run the 15-attempt audit conclusion if key remains unavailable`

## Gate status

| Gate | Status |
|---|---|
| G1-G8 | not_run in this verification-only attempt; covered by prior records |
| G9 | pass for artifact existence/inspection only; exact CLI-vs-trace result hash is still not implemented |

## Interpretation

No code or prompt change was made, so the prior deterministic evidence remains reproducible and the full test baseline is intact.
