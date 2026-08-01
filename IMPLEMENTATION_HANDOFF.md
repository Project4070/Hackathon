# Implementation Handoff

Status: ready to begin implementation  
Updated: 2026-08-01  
Deadline: 2026-08-02 08:00 KST  
Team: three developers using GitHub

## 1. Start Here

A new development session should read these files in order:

1. `AGENTS.md` — non-negotiable product, safety, crawler, and engineering rules.
2. `IMPLEMENTATION_HANDOFF.md` — current decisions and repository state.
3. `ARCHITECTURE_WORKFLOW.md` — the live tool/data flow and full Mermaid diagram.
4. `PLANNING_INTAKE_CONTRACT.md` — exact Steps 1–4 / Steps 5–10 contract.
5. `PRD.md` — complete requirements and acceptance scenarios.
6. `WORK_ALLOCATION.md` or `WORK_ALLOCATION_KO.md` — team ownership.
7. `Config_Temp.md` — calculator constants that must remain compatible.

`SCRATCHPAD.md`, `SCRATCHPAD_KO.md`, and `scratch.md` are historical design notes. They are not authoritative when they conflict with the files above.

## 2. Product in One Sentence

Convert a natural-language description of a group meal into a validated, restaurant-specific, whole-unit ordering plan, using AI for semantic interpretation and deterministic code for arithmetic, safety, budget, and final validation.

The hackathon subject is the visible AI-agent workflow, not a delivery marketplace. The MVP supports chicken and pizza, uses crawler-backed restaurant/menu data, and must visibly replan when a restaurant or other material input changes.

## 3. Frozen Boundary

The upstream teammate owns Steps 1–4:

`raw text/voice -> preflight -> Interpreter Agent -> MealRequestCandidateV2 -> deterministic validator -> PlanningIntakeV2 | clarification_required | request_rejected`

The current developer owns Steps 5–10 and consumes only:

`PlanningJobV2 = PlanningIntakeV2 + PlannerRuntimePolicyV2 + PlannerExecutionContextV2`

Do not make the downstream planner accept a loose dictionary, raw prose, the teammate's original aggregate-demographics payload, or a non-ready outcome.

Key contract decisions:

- UTF-8 JSON, `snake_case`, schema `2.0`, vocabulary `1.0`.
- Monetary values are integer minor units; KRW 250000 means ₩250,000.
- Percent-style configuration is integer basis points; 10000 equals 100%.
- Serving values crossing boundaries are integer milli-servings; 1000 equals one serving.
- Participant cohorts are mutually exclusive and sum to `party.total_count`.
- Hard restrictions and soft preferences are separate types.
- Runtime policy, crawler limits, ranking weights, timestamps, resolved coordinates, and cache IDs are application-owned, not model-owned.
- Full raw input stays in request storage. Only bounded evidence snippets cross the planner boundary.

## 4. Runtime Architecture

The Main Planner Agent receives a lightweight `PlannerViewV2` and orchestrates these stages:

1. `build_serving_input(case_id)` — adapt the validated profile into calculator cohorts.
2. `calculate_serving_requirement(case_id or serving_calculation_input_id)` — deterministic group demand and three strategy targets.
3. `search_menu_candidates(case_id)` — query the reviewed restaurant snapshot/cache, optionally request a bounded refresh.
4. `enrich_menu_semantics(case_id, candidate_set_id)` — agent-as-tool only for menu records without a reusable enrichment.
5. `apply_hard_eligibility(case_id, menu_set_id)` — deterministic allergy, diet, explicit exclusion, availability, and delivery filtering.
6. `generate_budget_combinations(case_id, eligible_set_id, serving_requirement_id)` — bounded integer search under budget and sale-unit rules.
7. `score_soft_preferences(case_id, combination_set_id)` — bounded semantic rewards/penalties and reason codes; no hard exclusion.
8. `rank_and_validate_plans(case_id, scored_set_id)` — deterministic final hard checks and ranking.
9. `get_plan_for_presentation(case_id, plan_ids)` — return only one recommendation and two alternatives for explanation.
10. The Main Planner Agent explains the selected order, evidence, uncertainty, and alternatives without inventing facts.

Large objects live in server-side stores. Tool calls pass `case_id` plus an artifact ID only when multiple versions or branches can exist. The detailed reason for each argument is documented in `ARCHITECTURE_WORKFLOW.md`.

## 5. Existing Calculator Compatibility

Do not rewrite the teammate's serving calculator. Put a versioned adapter in front of it.

Stable aliases:

| Contract value | Calculator value |
| --- | --- |
| `very_light` | `very_low` |
| `light` | `low` |
| `normal` | `normal` |
| `large` | `high` |
| `very_large` | `very_high` |
| `late_night` | `late_night_snack` |
| `minimize_shortage` | `avoid_shortage` |

The calculator owns all `Decimal` factors, mutually exclusive adjustment checks, double-count warnings, per-person caps, and the maximum total margin. `Config_Temp.md` records the exact values and loader rules.

One integration decision must be settled with the upstream teammate before relying on adjustment factors: the contract's coarse `activity_level` and `recent_meal_status` do not preserve all calculator codes such as `after_long_activity`, `ate_1_to_2_hours_ago`, and `just_ate`. Until a coordinated schema/adapter decision is made, only apply an adjustment when the validated fields and evidence unambiguously support the exact calculator code. Otherwise apply no adjustment and expose an assumption/warning. Never reinterpret free text inside deterministic calculator code.

## 6. Restaurant Cache

The Restaurant Snapshot Cache stores the last successful normalized crawl result, not user requests or final plans. It contains restaurant/branch identity, location, public menu text, prices, sale units, sizes/weights/piece counts when explicit, availability, source URL, crawl timestamp, completeness, normalized semantic fields, inference status, confidence, model/prompt version, and content hash.

Runtime behavior:

- Query the cache first.
- Suggested freshness window: 24 hours.
- Refresh only within crawler bounds.
- If refresh fails, use the last successful record only when present and label it stale.
- If no usable cache exists, return `data_unavailable`.
- Never infer allergy safety, price, portion, availability, or restaurant identity from an LLM guess.

## 7. Repository State

- Product requirements: `PRD.md`, with Korean companion `PRD_KO.md`.
- Team assignments: `WORK_ALLOCATION.md`, `WORK_ALLOCATION_KO.md`.
- Boundary contract: `PLANNING_INTAKE_CONTRACT.md` (revised hybrid v2; proposed for teammate approval).
- Calculator constants: `Config_Temp.md`.
- Crawler reference code: `CRAWLER_EXAMPLE.py`.
- Architecture document: `ARCHITECTURE_WORKFLOW.md`.
- Interactive diagram source: `workflow-site/`.
- Diagram data source: `workflow-site/public/data/workflow.json`.
- Public diagram: <https://group-food-agent-workflow.thetired3080.chatgpt.site/>

The diagram website is a separate nested Git repository used only as an architecture viewer. Its renderer reads the JSON dataset at runtime. Node descriptions are intentionally not hard-coded in the TSX component. Hover previews a node; click or Enter pins the explanation.

## 8. First Implementation Slice

Build a vertical slice before expanding scope:

1. Create shared Pydantic models/enums and generate JSON Schema from them.
2. Add one golden `PlanningJobV2` fixture for the canonical 15-person Korean request.
3. Implement the calculator adapter and deterministic serving calculation tests.
4. Add a reviewed restaurant snapshot fixture with at least one chicken and one pizza restaurant.
5. Implement eligibility, bounded integer combination generation, and final validation.
6. Put each stage behind a narrow tool interface returning artifact IDs.
7. Wire the OpenAI Agents SDK orchestrator and stream stage/tool events to the UI.
8. Demonstrate the initial result and restaurant-unavailable replanning.

Avoid building production accounts, real payment/order placement, broad cuisine coverage, or a large marketplace UI.

## 9. Minimum Tests Before Demo

- Ten natural-language examples already discussed, including snack/full-meal, appetite distributions, budget, vegetarian, seafood exclusion, spice dislike, and no-leftover-storage cases.
- Group counts must sum exactly; overlap ambiguity must ask for clarification.
- `1000 kg`, invalid/huge group sizes, non-finite/negative budgets, invented food names, meaningless text, oversized text, and prompt injection must terminate safely before expensive tools.
- A restricted diner always has sufficient eligible food or the outcome is `no_valid_plan`.
- Unknown allergen information is never displayed as safe.
- The same demand produces different quantities when restaurant serving evidence differs.
- Restaurant unavailability reruns affected stages rather than copying quantities.
- Stale/partial/missing restaurant data produces the defined controlled outcome.
- Every recommendation passes deterministic quantity, eligibility, budget, delivery, and sale-unit checks.

## 10. Open Decisions That Must Not Be Guessed

- Final shared Pydantic package path and ownership.
- Exact adapter representation for calculator-specific serving adjustments.
- Canonical crawl source and canonical location/restaurant snapshot.
- Concrete artifact/store implementation (in-memory is acceptable for the hackathon).
- Exact OpenAI model selection and cost/latency limits.
- Which developer owns UI event-stream rendering versus backend trace emission.

Make these decisions in small coordinated commits. A contract or vocabulary change requires both sides to update the shared schema and golden fixtures together.

## 11. Definition of Done

A judge can enter free-form Korean text, observe structured interpretation and explicit tool stages, receive a reproducible restaurant-specific order plan with three strategies, see provenance and validation, force a restaurant change, and observe a recalculated valid plan. The system remains controlled and non-hallucinatory under absurd or hostile input and still works from prepared fixtures if live crawling or an OpenAI call fails.
