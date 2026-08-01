# Attempt 017

- `attempt_id`: `017`
- `prompt_version`: `en-equivalent-holdout_v1`
- `prompt_hash`: `sha256:8e5c48ff598d28dbe63622e19f599c88a2147046dfa8a5687d8d567b2e005418`
- `input_fixture_or_mode`: `live CLI natural-language; English equivalent valid request`
- `model`: `gpt-5.6-luna` effective after CLI `.env` load
- `api_key_used`: `true` (presence only; value omitted)
- `execution_command`: `.venv\\Scripts\\group-food-agent.exe <redacted English holdout> --trace-file .traces\\goall-attempt-017.jsonl`
- `exit_code`: `1` (shell wrapper reported nonzero)
- `terminal_outcome`: `request_rejected` at input boundary
- `failed_stage_and_tool`: `interpreter_agent; no planning tool`
- `error_type`: `InterpreterRunError; provider response unavailable`
- `corrective_action`: `resolve live model/API response availability; do not change prompt`
- `trace_file`: `C:\\Hackathon\\.traces\\goall-attempt-017.jsonl`
- `trace_summary`: `7 events; preflight passed; Interpreter started then failed; tool events 0; sensitive payload export false`
- `test_result`: `baseline full suite: 71 passed; no code or prompt source changed`
- `next_minimal_change`: `none during this run; continue unchanged mixed-language holdout`

## Gate status

| Gate | Status | Evidence / boundary |
|---|---|---|
| G1 | pass | preflight passed with zero issues |
| G2 | blocked | live Interpreter failed after bounded retry |
| G3-G8 | not_run | blocked before validated intake and planner |
| G9 | partial | CLI payload and trace path emitted; exact result hash remains absent |

## Interpretation

The English equivalent produced the same failure boundary and no downstream tool call as attempt 016. The repeated boundary supports an external model-response classification rather than a Korean-only extraction issue.
