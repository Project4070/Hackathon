# Attempt 013

- `attempt_id`: `013`
- `prompt_version`: `canonical_15_request_fixture_v1`
- `prompt_hash`: `sha256:B5B722B8AF45A3999C74632CBECE33BF9A3840BF103F60114770A858F884B009`
- `input_fixture_or_mode`: `offline canonical; post-meal shortage feedback`
- `model`: `fixture_interpreter; deterministic planner; no model call`
- `api_key_used`: `false`
- `execution_command`: `.venv\\Scripts\\group-food-demo.exe --feedback shortage --trace-file .traces\\goall-attempt-013.jsonl`
- `exit_code`: `0`
- `terminal_outcome`: `succeeded` (fixture-scoped feedback replan)
- `failed_stage_and_tool`: `none`
- `error_type`: `none`
- `corrective_action`: `none`
- `trace_file`: `C:\\Hackathon\\.traces\\goall-attempt-013.jsonl`
- `cli_payload`: `.goall\\attempts\\attempt-013-cli.json`
- `test_result`: `initial demand 15.450 / 17.000 servings; shortage feedback demand 16.224 / target 17.522, new demand multiplier 10,500 bp, affected menu serving multiplier 9,500 bp`
- `next_minimal_change`: `run full verification commands and inspect G9 consistency artifacts`

## Gate status

| Gate | Status |
|---|---|
| G1 | pass (fixture) |
| G2 | pass (fixture) |
| G3 | pass |
| G4 | pass; demand changes after feedback |
| G5 | pass |
| G6 | pass |
| G7 | pass |
| G8 | pass for initial and feedback-replanned plan |
| G9 | pass for CLI payload + local trace path presence; exact result hash remains absent |

## Interpretation

Feedback updates stored demand and menu serving coefficients and affects the subsequent plan. This is reproducible fixture evidence only.
