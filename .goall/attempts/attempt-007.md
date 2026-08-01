# Attempt 007

- `attempt_id`: `007`
- `prompt_version`: `oversized-group-v1`
- `prompt_hash`: `sha256:911a26b0320a3818fd16299fea7bbef31df9963cbe8f6773c9d2017b777c1c58`
- `input_fixture_or_mode`: `live CLI; oversized group holdout`
- `model`: `gpt-5.6-sol` configured default; no model call
- `api_key_used`: `false`
- `execution_command`: `.venv\\Scripts\\group-food-agent.exe <redacted prompt> --trace-file .traces\\goall-attempt-007.jsonl`
- `exit_code`: `2`
- `terminal_outcome`: `request_rejected`
- `failed_stage_and_tool`: `G1 preflight; no tool`
- `error_type`: `group_size_out_of_range`
- `corrective_action`: `use an integer group size from 1 through 100 or split the event into supported plans`
- `trace_file`: `C:\\Hackathon\\.traces\\goall-attempt-007.jsonl`
- `test_result`: `trace: G1 stage_blocked, G8 outcome stage_blocked, 0 tool events`
- `next_minimal_change`: `test an unknown food name; do not invent a menu match`

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
| G9 | pass for terminal status/trace agreement |

## Interpretation

The out-of-range group size is rejected before participant expansion or combinatorial planning.
