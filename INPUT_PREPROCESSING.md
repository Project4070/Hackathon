# Input and Preprocessing Implementation

This slice implements the frozen Steps 1–4 boundary from
`PLANNING_INTAKE_CONTRACT.md`.

## Runtime flow

1. `preflight_raw_input` verifies only that input is bounded, nonempty, readable
   text. It checks type, length, and unreadable control characters, and never
   truncates, executes, clamps, rewrites, or semantically classifies input.
2. `MealRequestInterpreter` constructs an OpenAI Agents SDK `Agent` with
   `MealRequestCandidateV2` as `output_type`. The SDK therefore enforces the
   Pydantic schema instead of relying on a JSON example in a prompt.
3. `validate_planning_profile` deterministically checks meal intent, mutually
   exclusive cohort totals, IDs, vocabulary, evidence, restriction references,
   location, numeric ranges, budgets, and readiness. It supplies only documented
   application defaults and blocks invalid cases before planning tools run.
4. The boundary returns exactly one of `PlanningIntakeV2`,
   `ClarificationRequiredV2`, or `RequestRejectedV2`.

The Interpreter Agent has no tools. It cannot search restaurants or calculate
quantities. Those actions are deliberately unavailable until the deterministic
admission gate returns `ready_for_planning`.

## Observable events

`process_meal_request` accepts a synchronous or asynchronous event sink and
emits schema-versioned events for preflight, the Agents SDK run, deterministic
validation, and blocking outcomes. Agent events include the SDK name and typed
output name but never the API key, system prompt, or complete raw request.

## Configuration boundaries

- `GROUP_FOOD_INTERPRETER_MODEL` changes the Interpreter model; the default is
  `gpt-5.6-sol`.
- `RawInputLimits` owns cheap untrusted-input bounds.
- `AdmissionPolicyV2` owns deterministic defaults and supported admission
  ranges.
- `ValidationContextV2` owns request/case IDs, revision, admission time, and an
  optional trusted request-context location.

No policy or runtime field is included in the model-owned candidate.

## Artifacts and verification

- Canonical Korean fixture: `fixtures/canonical_15_request.txt` and
  `fixtures/canonical_15_candidate.json`.
- Generated schemas: `schemas/*.schema.json`.
- Offline test suite: `python -m pytest`.
- Live demo: `group-food-intake "..." --location "..."` with
  `OPENAI_API_KEY` configured.

The tests use a fake interpreter for deterministic pipeline coverage and also
instantiate the real OpenAI Agents SDK `Agent` to verify its strict structured
output schema without making a billable API call.
