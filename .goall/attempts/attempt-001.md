# Attempt 001

- `attempt_id`: `001`
- `prompt_version`: `canonical_15_request_fixture_v1`
- `prompt_hash`: `sha256:B5B722B8AF45A3999C74632CBECE33BF9A3840BF103F60114770A858F884B009`
- `input_fixture_or_mode`: `fixtures/canonical_15_request.txt; --offline-canonical`
- `model`: `fixture_interpreter; deterministic_planner; no model call`
- `api_key_used`: `false`
- `execution_command`: `.venv\\Scripts\\group-food-agent.exe --offline-canonical --trace-file .traces\\goall-attempt-001.jsonl`
- `exit_code`: `0`
- `terminal_outcome`: `succeeded` (fixture-scoped; not live)
- `failed_stage_and_tool`: `none`
- `error_type`: `none`
- `corrective_action`: `none for fixture path; run live process-level key test before claiming live success`
- `trace_file`: `C:\\Hackathon\\.traces\\goall-attempt-001.jsonl`
- `test_result`: `pre-run full suite: 60 passed; canonical run: exit 0`
- `next_minimal_change`: `preserve CLI result and a trace summary in one machine-readable audit artifact so G9 can be checked`

## Gate status

| Gate | Status | Evidence / boundary |
|---|---|---|
| G1 Raw input preflight | pass | trace sequence 2-3 |
| G2 Interpreter structured output | pass | fixture candidate; no live model |
| G3 Deterministic profile validation | pass | `ready_for_planning` |
| G4 Serving input/calculation | pass | stage 4 call/result pairs |
| G5 Restaurant/menu snapshot or gateway | pass | stage 5 cache lookup against reviewed snapshot |
| G6 Semantic enrichment and hard eligibility | pass | stages 6 and 8 call/result pairs |
| G7 Budget combination/ranking/final validation | pass | stages 9 and 10 call/result pairs |
| G8 Final plan or explicit blocked result | pass | stage 11 presentation result; CLI exit 0 |
| G9 Trace and CLI/UI consistency | blocked | trace carries artifact summaries, but this run did not persist a machine-readable CLI payload for exact comparison |

## Interpretation

This is deterministic fixture evidence only. It does not establish that a natural-language prompt reaches G2 with the configured live model, and it does not establish live restaurant data. The first concrete system improvement target is G9 audit correlation, followed by live-key/environment separation.
