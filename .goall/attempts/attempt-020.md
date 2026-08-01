# Attempt 020

- `attempt_id`: `020`
- `prompt_version`: `absurd-mass-v1`
- `prompt_hash`: `sha256:7ebfca5b64ff2368d1b762fda4ab0539dc505fb88a84ee7468cba678e082157e`
- `input_fixture_or_mode`: `live CLI; absurd physical-quantity holdout`
- `model`: `gpt-5.6-luna` configured effective model; no model call required
- `api_key_used`: `false` for execution; preflight blocked before Interpreter
- `execution_command`: `.venv\\Scripts\\group-food-agent.exe <redacted absurd-mass holdout> --trace-file .traces\\goall-attempt-020.jsonl`
- `exit_code`: `1` (shell wrapper reported nonzero)
- `terminal_outcome`: `request_rejected` at G1 preflight
- `failed_stage_and_tool`: `preflight; no tool`
- `error_type`: `unsupported_physical_quantity`
- `corrective_action`: `check the number and unit, then state a value within the supported range`
- `trace_file`: `C:\\Hackathon\\.traces\\goall-attempt-020.jsonl`
- `trace_summary`: `5 events; preflight blocked; outcome blocked; tool events 0; sensitive payload export false`
- `test_result`: `baseline full suite: 71 passed; no code or prompt source changed`
- `next_minimal_change`: `stop at 020 and wait for owner review`

## Gate status

| Gate | Status | Evidence / boundary |
|---|---|---|
| G1 | pass as rejection | literal `1000 kg` preserved and blocked with smallest corrective action |
| G2-G7 | not_run | blocked before interpretation and planning |
| G8 | pass as explicit rejection | no order was generated |
| G9 | partial | CLI payload and trace path emitted; exact result hash remains absent |

## Interpretation

The absurd quantity did not reach the model, calculator, restaurant lookup, or combinatorial search. No extreme order was generated. This is the final attempt in the requested 016–020 window.
