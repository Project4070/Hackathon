# Group Food Quantity Agent Implementation Audit

Audit date: 2026-08-02

## Completion status

The G2-G7 backend path is implemented:

1. Strict `PlanningJobV2` runtime contract, policy registry, case/artifact/evidence
   stores, and generated JSON Schemas.
2. Versioned serving adapter and `Decimal` calculation with appetite aliases,
   caps, safety margins, protected demand, and three targets.
3. Bounded crawler/source-adapter interface, reviewed snapshot cache, freshness,
   completeness, source, parser, and semantic provenance.
4. Deterministic hard allergy/diet eligibility and exact group-to-item capacity
   validation by max flow.
5. Bounded whole-sale-unit search, cost-scope budget checks, minimum order,
   delivery-area/time checks, semantic preference scoring, final validation, and
   one recommendation plus two named restaurant alternatives.
6. Restaurant/menu/participant/budget replanning and feedback-based demand/menu
   serving adjustments.
7. One end-to-end application entry point and raw pipeline/tool event streams.

## OpenAI Agents SDK use

- Installed package: `openai-agents==0.19.2`.
- Interpreter Agent: no tools; strict `MealRequestCandidateV2` structured output.
- Main Planner Agent: strict `PlannerAgentFinalV1`; orchestrates nine typed tools
  by `case_id` and artifact IDs.
- Menu Semantic Enrichment Agent: no tools; normalizes only sanitized uncached
  visible text, uses a hash/model/prompt-version cache, and cannot establish
  identity, price, availability, allergy safety, or practical serving quantity.
- Soft arithmetic, hard constraints, and whole-unit search stay outside the
  language model.
- The final presentation tool is the only tool that exposes the validated plan
  payload to the Main Planner for a grounded explanation.

## Verified offline run

Canonical 15-person result:

| Field | Result |
| --- | --- |
| Boundary | `ready_for_planning` |
| Attendance | 15 |
| Equivalent demand | 15.450 servings |
| Protected demand | 2.000 servings |
| Balanced target | 16.686 servings |
| Initial restaurant | Alpha Chicken & Pizza |
| Initial units | 4 |
| Initial practical servings | 17.000 |
| Initial total | KRW 99,000 |
| Hard validation | passed |
| Pipeline events | 7 |
| Tool events | 18 (9 call/result pairs) |

Replanning evidence:

| Run | Restaurant | Units | Demand | Target | Practical servings | Total |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Initial | Alpha Chicken & Pizza | 4 | 15.450 | 16.686 | 17.000 | KRW 99,000 |
| Alpha unavailable | Beta Oven | 6 | 15.450 | 16.686 | 18.000 | KRW 109,500 |
| Shortage feedback | Gamma Family Kitchen | 4 | 16.224 | 17.522 | 18.500 | KRW 123,000 |

The replacement quantity is recalculated from restaurant-specific serving
evidence; it is not copied from the first plan. Shortage feedback increases the
future demand multiplier from 10,000 to 10,500 basis points and lowers affected
menu serving estimates to 9,500 basis points.

## Verification commands

```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m pip check
.venv\Scripts\group-food-schemas.exe --output schemas
.venv\Scripts\group-food-agent.exe --offline-canonical
.venv\Scripts\group-food-demo.exe --replan-unavailable --feedback shortage
```

Latest result: 60 tests passed, 23 schemas generated, and no broken Python
requirements.

## Live-run gate

No key was present during this audit, so no billable OpenAI request was made.
The offline canonical path and all deterministic stages are verified. A live
natural-language run now requires only process-level configuration:

```powershell
$env:OPENAI_API_KEY = "your-key"
.venv\Scripts\group-food-agent.exe "<complete meal request>"
```

The prepared restaurant data remains explicitly labeled
`simulated_reviewed_fixture`; live crawling is optional and not a stage-demo
dependency. Payment and irreversible ordering remain outside MVP scope.
