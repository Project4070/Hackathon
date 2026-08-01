# Attempt 011

- `attempt_id`: `011`
- `prompt_version`: `canonical_15_request_fixture_v1`
- `prompt_hash`: `sha256:B5B722B8AF45A3999C74632CBECE33BF9A3840BF103F60114770A858F884B009`
- `input_fixture_or_mode`: `offline canonical; `--snapshot-id snapshot-does-not-exist``
- `model`: `fixture_interpreter; deterministic planner; no model call`
- `api_key_used`: `false`
- `execution_command`: `.venv\\Scripts\\group-food-agent.exe --offline-canonical --snapshot-id snapshot-does-not-exist --trace-file .traces\\goall-attempt-011.jsonl`
- `exit_code`: `2`
- `terminal_outcome`: `deterministic_gateway_blocked` (CLI reports generic blocked; taxonomy mismatch noted)
- `failed_stage_and_tool`: `G5/stage 5, search_menu_candidates`
- `error_type`: `KeyError`
- `corrective_action`: `use a usable reviewed snapshot ID or return a typed `data_unavailable`/gateway-blocked result instead of leaking `KeyError``
- `trace_file`: `C:\\Hackathon\\.traces\\goall-attempt-011.jsonl`
- `test_result`: `G1-G4 pass; G5 tool_error; no stages 6-11; exit 2`
- `next_minimal_change`: `run canonical restaurant-unavailable replan`

## Gate status

| Gate | Status |
|---|---|
| G1 | pass |
| G2 | pass (fixture) |
| G3 | pass |
| G4 | pass |
| G5 | fail/blocked |
| G6 | not_run |
| G7 | not_run |
| G8 | pass as explicit blocked terminal, but status taxonomy is generic |
| G9 | blocked: trace captures tool error, CLI output was not persisted for exact hash comparison |

## Interpretation

The deterministic gateway stops before enrichment and combination search. The raw exception classification is too weak for the required user-facing `data_unavailable` or `deterministic_gateway_blocked` outcome.
