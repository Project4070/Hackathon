# Group Food Quantity Agent

This repository implements an observable, demo-ready agent that turns one
natural-language group-meal description into a validated, restaurant-specific,
whole-unit order. The MVP supports chicken and pizza.

The OpenAI Agents SDK is used for semantic interpretation and orchestration.
Deterministic code owns input safety, serving arithmetic, allergy/dietary
eligibility, integer quantity search, budget validation, and final plan checks.

## Runtime flow

```text
raw text
  -> bounded preflight
  -> Agents SDK Interpreter Agent -> MealRequestCandidateV2
  -> deterministic validator -> PlanningIntakeV2
  -> PlanningJobV2 + policy/context
  -> Agents SDK Main Planner Agent
       -> typed serving, cache, eligibility, search, ranking, presentation tools
  -> DisplayPlanV1 (recommendation + two alternatives)
```

The Main Planner Agent receives only a `case_id` and artifact IDs. It cannot
invent prices, menus, portions, or allergy safety, and it does not perform the
calculation itself. Correlated `tool_call`, `tool_result`, and `tool_error`
events are retained for the demo trace.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

For a live CLI run, `.env` is loaded automatically without overriding an
explicit process environment value. Library functions do not load `.env`
implicitly:

```powershell
$env:OPENAI_API_KEY = "..."
group-food-agent "연세대학교에서 15명이 저녁을 먹습니다. 치킨과 피자를 원하고 예산은 25만원입니다."
```

Set `GROUP_FOOD_SKIP_DOTENV=1` when a CLI process must ignore the local file.

Do not put a real key in `.env.example` or source control. Model overrides are
`GROUP_FOOD_INTERPRETER_MODEL`, `GROUP_FOOD_PLANNER_MODEL`, and
`GROUP_FOOD_SEMANTIC_MODEL`; all currently default to `gpt-5.6-sol`.

Temporary hackathon budget policy: if the user omits a budget, validation
currently applies a hard ceiling of KRW 12,000 per attending person. This is
recorded as a policy assumption and is subject to change.

There is no `gpt-5.6-nano` model ID. OpenAI documents `gpt-5.6-luna` as the
cost-sensitive GPT-5.6 model that roughly corresponds to the earlier nano tier.
Use the three environment variables above to opt into it after validating the
structured-output and tool-calling quality for this workflow.

## Tracing and debugging

Both runnable CLIs write a unique JSONL trace under `.traces/` by default. The
trace correlates the input pipeline and deterministic tool stages with the same
logical and SDK trace IDs, records stage durations and artifact IDs, and records
a terminal `tool_error` if a deterministic operation raises.

```powershell
group-food-agent --offline-canonical
group-food-demo --replan-unavailable
group-food-trace .traces\<trace-file>.jsonl
```

`--smoke-success` is an explicit alias for the canonical successful rehearsal.
To rehearse a temporary deterministic-gateway block while keeping the same
validated input, pass a missing snapshot ID:

```powershell
group-food-agent --smoke-success --snapshot-id snapshot-does-not-exist
```

That command exits with code `2`, prints `BLOCKED at
deterministic_gateway/search_menu_candidates`, and includes the reason and
corrective action in the JSON payload. A successful rehearsal prints
`SUCCEEDED` and exits with code `0`.

Use `--trace-file <path>` to choose a path or `--no-trace` to disable the local
file. Live Interpreter and Main Planner runs are grouped into one OpenAI Agents
SDK trace. `RunConfig(trace_include_sensitive_data=False)` is enforced, so model
inputs/outputs and tool payloads are excluded from the SDK export. The local
JSONL also does not store the raw meal request and redacts secret-looking values.
See the [official Agents SDK tracing guidance](https://developers.openai.com/cookbook/examples/partners/schemaflow_design_guide/schemaflow_cookbook#1-environment-setup).

## Pipeline role and input contract

The pipeline has deliberately separated responsibilities:

1. Preflight verifies only that input is bounded, nonempty, readable text. It
   does not classify meal intent, food categories, numbers, or instruction-like
   content.
2. The Interpreter Agent maps natural language to `MealRequestCandidateV2`.
   It preserves evidence and uncertainty but does not calculate quantities or
   invent menu facts.
3. Deterministic validation resolves meal intent, supported vocabulary,
   participant groups, location, restrictions, numeric ranges, budget, and risk
   preference. It returns a ready intake, clarification, or explicit rejection
   before restaurant or calculation tools run.
4. The Main Planner Agent orchestrates typed tools. Deterministic code then
   owns servings, dietary eligibility, restaurant-specific serving evidence,
   integer quantities, budget checks, alternatives, and presentation.
5. The terminal result is either a judge-readable plan or a structured blocked
   outcome. No blocked case is converted into a guessed order.

A prompt that supplies the material fields for the current MVP looks like this:

> 신촌에서 2026년 8월 10일 오후 6시에 15명이 저녁 식사를 하려고 합니다. 서로 다른 사람으로 많이 먹는 사람 4명, 보통 식사량 6명, 적게 먹는 사람 3명, 채식주의자 1명, 땅콩 알레르기가 있는 사람 1명입니다. 치킨과 피자를 모두 원하고, 매운 음식은 피해주세요. 예산은 배달비와 수수료를 포함해 최대 25만원입니다. 남는 음식과 부족한 음식의 균형을 우선하고, 배달 가능한 식당과 메뉴의 실제 가격·알레르기 정보·제공량 근거를 확인해 몇 개를 주문해야 하는지 계산해주세요.

This is an extraction prompt, not a command to the model to do arithmetic. The
agent should still ask for clarification when location, attendance, category,
budget, or a mandatory restriction is missing or contradictory.

## Offline verified demo

The complete prepared path works without a network call or key:

```powershell
group-food-agent --offline-canonical
group-food-demo --replan-unavailable --feedback shortage
```

The restaurant snapshot is a synthetic, manually reviewed crawler-style
fixture. Every displayed plan labels it `simulated_reviewed_fixture`; it must not
be presented as live pricing or availability.

## Tests and schemas

```powershell
python -m pytest
group-food-schemas --output schemas
python -m pip check
```

Important fixtures:

- `fixtures/canonical_planning_job_v2.json`: golden validated 15-person job.
- `fixtures/restaurant_snapshot_sinchon_v1.json`: three reviewed restaurant
  branches with source, freshness, explicit dietary/allergen evidence, and
  practical serving ranges.
- `fixtures/policies/serving_policy_kr_v1.json`: versioned Decimal-compatible
  appetite, context, cap, and safety-margin policy.

The bounded crawler, semantic-enrichment agent, cache, stores, calculator,
replanning, feedback, end-to-end application entry point, and adversarial tests
are all under `src/group_food_agent` and `tests`.

## Naver Place HTTP adapter demo

The Naver Place adapter is deliberately separate from the planner snapshot. It
returns the fields observed in the public Place HTML plus explicit
`availableFields` and `unavailableFields`. Missing servings, sale units,
allergens, delivery fees, minimum order, and delivery time are not invented.

Run the local endpoint in one terminal:

```powershell
.venv\Scripts\uvicorn.exe --app-dir src group_food_agent.http_api:app --host 127.0.0.1 --port 3000
```

Then query it from another terminal:

```powershell
Invoke-RestMethod 'http://127.0.0.1:3000/api/geocode?q=신논현역'
Invoke-RestMethod 'http://127.0.0.1:3000/api/restaurants?lat=37.502104&lng=127.025869&limit=10&radius=1000&delivery=0&fresh=0'
```

The checked browser-observed fixture returns two records for `delivery=0`.
The same location returns `status=no_candidates` for `delivery=1` because the
observed records have `naverOrder.isDelivery=false`; this is an intentional
conservative result, not a guessed delivery plan. `fresh=1` is recorded in the
response but currently falls back to the reviewed fixture when live refresh is
unavailable.
