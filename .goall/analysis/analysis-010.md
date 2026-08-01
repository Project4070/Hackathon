# Analysis 010

## Evidence window

Attempts 006-010 plus the first five attempts. The full repository suite remains `60 passed` before any code change.

## Repeatedly failing gates

- G2/G3/G4-G8 are `not_run` for five valid/semantically meaningful live holdouts because the application checks `OPENAI_API_KEY` before creating the local trace and before invoking the Interpreter.
- G9 is repeatedly blocked for the same pre-trace failure. Invalid G1 cases (006-007) do produce traces and show no downstream tool events.

## Prompt versus system diagnosis

The blocker is definitively system/environmental: four language/normal valid prompts, unknown food, tiny budget, and missing location all terminate identically at configuration. Prompt variation has no observed effect. The absurd-value cases are different and healthy: they are rejected at G1 with explicit reason codes.

The current prompt contract is too ambitious to validate live without a key, but there is no evidence that adding more prose would fix the blocker. The correct action is to repair execution observability and provision the external dependency, not to broaden the prompt.

## Language and food overfit

No live language overfit evidence is available. Korean, English, and mixed input are indistinguishable under the blocker. The fixture itself is Korean-shaped and should not be used to claim bilingual coverage.

## Location, budget, allergy, and snapshot dependence

- Location missing: expected `clarification_required`, unverified live.
- Tiny budget: expected deterministic `no_valid_plan`, unverified live.
- Allergy/vegetarian: covered in canonical fixture and deterministic tests, not live natural-language.
- Snapshot: offline reviewed snapshot exists; live lookup is not tested. Missing snapshot gateway remains to be run next.

## Fixture-only versus live

The only end-to-end plan is fixture-only. The live path has zero successful model calls in this run. Existing `.env` key presence does not count as process-level readiness because the application intentionally reads only the process environment.

## Improvement candidates, prioritized

1. **Safety/observability:** move trace initialization and a redacted preflight/configuration event before the key check. Expected effect: all blockers get auditable G1/G2 boundary records. Regression risk: secret leakage if the redaction contract is not reused.
2. **Gate coverage:** add an offline text-harness mode that uses the real preflight and a declared fixture interpreter candidate; mark G2 as `simulated_structured_output`, never live. Expected effect: holdout validation can run without API. Regression risk: demo confusion between model and fixture.
3. **Outcome taxonomy:** map missing key to `external_dependency_blocked` in both JSON and diagnostics, not a generic exception. Expected effect: UI/trace agreement. Regression risk: callers depending on the current exit code/text.
4. **Korean/English/mixed:** once key exists, rerun the same three prompts unchanged; only then consider a minimal prompt change. Expected effect: unbiased language comparison. Regression risk: consuming budget without fixing key.
5. **G9:** persist `terminal_result_hash`, `display_artifact_id`/`failure_artifact_id`, and trace path in one audit object. Expected effect: exact CLI/trace reconciliation. Regression risk: schema/version maintenance.

## Next five attempts

- Attempt 011: offline canonical with missing snapshot ID; verify deterministic G5 block and controlled `data_unavailable`/gateway outcome.
- Attempt 012: offline restaurant-unavailable replan; verify replacement quantity is recalculated.
- Attempt 013: offline shortage feedback; verify stored multiplier/serving estimate changes later output.
- Attempt 014: full test + schema/pip checks after no code changes, then compare traces and CLI result fields.
- Attempt 015: if key remains unavailable, produce the required 15-attempt analysis with explicit external conditions; otherwise rerun the unchanged Korean or English prompt live.

## Reasons not to apply changes immediately

Do not synthesize a live success from the offline fixture, silently load `.env`, skip the Interpreter, or change the deterministic rules to make tiny budgets feasible. Those actions would corrupt the evidence boundary and risk unsafe ordering.
