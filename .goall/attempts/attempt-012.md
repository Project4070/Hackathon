# Attempt 012

- `attempt_id`: `012`
- `prompt_version`: `canonical_15_request_fixture_v1`
- `prompt_hash`: `sha256:B5B722B8AF45A3999C74632CBECE33BF9A3840BF103F60114770A858F884B009`
- `input_fixture_or_mode`: `offline canonical; restaurant-unavailable replan`
- `model`: `fixture_interpreter; deterministic planner; no model call`
- `api_key_used`: `false`
- `execution_command`: `.venv\\Scripts\\group-food-demo.exe --replan-unavailable --trace-file .traces\\goall-attempt-012.jsonl`
- `exit_code`: `0`
- `terminal_outcome`: `succeeded` (fixture-scoped replan)
- `failed_stage_and_tool`: `none`
- `error_type`: `none`
- `corrective_action`: `none`
- `trace_file`: `C:\\Hackathon\\.traces\\goall-attempt-012.jsonl`
- `cli_payload`: `.goall\\attempts\\attempt-012-cli.json`
- `test_result`: `initial Alpha: 2x roast chicken + 2x 32cm pizza, 17.000 servings, KRW 99,000; replan Beta: 1x boneless chicken + 4x cheese pizza + 1x veggie pizza, 18.000 servings, KRW 109,500`
- `next_minimal_change`: `run shortage feedback and verify demand/serving estimates change`

## Gate status

| Gate | Status |
|---|---|
| G1 | pass (fixture) |
| G2 | pass (fixture) |
| G3 | pass |
| G4 | pass |
| G5 | pass for replacement snapshot lookup |
| G6 | pass |
| G7 | pass |
| G8 | pass for both initial and replacement plan |
| G9 | pass for CLI payload + local trace path presence; exact result hash is not yet implemented |

## Interpretation

The replacement quantity is recalculated from Beta's smaller practical servings and is not copied from Alpha. This is deterministic fixture evidence, not live restaurant evidence.
