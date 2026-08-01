# Attempt 006

- `attempt_id`: `006`
- `prompt_version`: `absurd-mass-v1`
- `prompt_hash`: `sha256:0c06cb46228cd39c5e0ca809f87ef52ee88971b0b0b96afe5f4526dfc860a554`
- `input_fixture_or_mode`: `live CLI; absurd physical quantity holdout`
- `model`: `gpt-5.6-sol` configured default; no model call
- `api_key_used`: `false`
- `execution_command`: `.venv\\Scripts\\group-food-agent.exe <redacted prompt> --trace-file .traces\\goall-attempt-006.jsonl`
- `exit_code`: `2`
- `terminal_outcome`: `request_rejected`
- `failed_stage_and_tool`: `G1 preflight; no tool`
- `error_type`: `unsupported_physical_quantity`
- `corrective_action`: `remove the 1000 kg statement and provide a plausible per-person serving amount`
- `trace_file`: `C:\\Hackathon\\.traces\\goall-attempt-006.jsonl`
- `test_result`: `trace: G1 stage_blocked, G8 outcome stage_blocked, 0 tool events`
- `next_minimal_change`: `test oversized group count; preserve literal-value rejection behavior`

## Gate status

| Gate | Status |
|---|---|
| G1 | pass as rejection |
| G2 | not_run |
| G3 | not_run |
| G4 | not_run |
| G5 | not_run |
| G6 | not_run |
| G7 | not_run |
| G8 | pass: explicit `request_rejected` |
| G9 | pass for terminal status/trace agreement; no UI payload involved |

## Interpretation

The literal extreme is blocked before model and calculator execution; no extreme order is generated.
