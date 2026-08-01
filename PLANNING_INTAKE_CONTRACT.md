# Planning Intake Contract v2.0 — Revised Hybrid

Status: proposed for team approval
Boundary: Steps 1–4 to Steps 5–10
JSON convention: snake_case, UTF-8
Schema version: 2.0
Vocabulary version: 1.0

Implementation overview: [ARCHITECTURE_WORKFLOW.md](ARCHITECTURE_WORKFLOW.md)
New-session handoff: [IMPLEMENTATION_HANDOFF.md](IMPLEMENTATION_HANDOFF.md)

## 1. Decision

This contract combines:

- The teammate proposal's snake_case naming, integer money, cost scope, policy IDs, milli-serving outputs, and basis-point configuration.
- The earlier contract's readiness discriminator, mutually exclusive participant groups, typed hard requirements and soft preferences, evidence, validation receipt, and strict admission invariants.

Neither earlier proposal should be implemented unchanged.

The system is divided into three contracts with different owners:

| Layer | Type | Owner | Purpose |
| --- | --- | --- | --- |
| A | MealRequestCandidateV2 | Pre-Step-5 language agent | Semantic extraction from user text |
| B | PlanningIntakeV2 | Deterministic Step-4 validator | Admitted, immutable planner input |
| C | PlanningJobV2 | Application code | Intake plus trusted runtime policy and execution context |

The Step-5 planner accepts PlanningJobV2. The language agent produces only MealRequestCandidateV2.

## 2. Data flow and trust boundary

~~~text
Raw user text
  -> basic input check
  -> MealRequestCandidateV2               model-owned semantic extraction
  -> deterministic validation
       -> ClarificationRequiredV2
       -> RequestRejectedV2
       -> PlanningIntakeV2                 admitted user facts
  -> application assembly
       + PlannerRuntimePolicyV2            trusted configuration
       + PlannerExecutionContextV2         runtime facts
  -> PlanningJobV2
  -> Step-5 Meal Planner Agent
~~~

Calculated serving requirements are not part of MealRequestCandidateV2 or PlanningIntakeV2. Steps 5–10 calculate them and place them in planning state or output.

Ranking weights, crawler limits, unknown-menu policies, numerical safety margins, and combination limits are not model output. They belong to PlannerRuntimePolicyV2.

Current time, resolved coordinates, trace ID, and restaurant snapshot ID are not model output. They belong to PlannerExecutionContextV2.

## 3. Compatibility rules

1. Every runtime payload is a UTF-8 JSON object.
2. Field names use the exact snake_case spelling in this document.
3. Every object rejects unknown fields. Pydantic implementations use extra="forbid".
4. PlanningIntakeV2 is immutable after validation. Pydantic implementations use frozen=True.
5. Required fields are always present. Unknown optional scalars are null; collections use empty arrays.
6. Numbers are finite. NaN and positive or negative infinity are forbidden.
7. Money is an integer in the currency's smallest supported unit. For KRW, 250000 means ₩250,000.
8. Basis points are integers. 10000 basis points equal 100%.
9. Milli-servings are integers. 1000 milli-servings equal one standard serving.
10. Timestamps use RFC 3339 and include a timezone offset.
11. IDs are opaque strings. Consumers never extract meaning from them.
12. Enum values are exact lowercase snake_case strings except currency codes.
13. Field paths use JSON Pointer, for example /profile/party/total_count.
14. Unsupported schema or vocabulary versions fail explicitly.
15. Removing a field, changing its meaning, adding a required field, or narrowing allowed values requires a schema-version change.
16. New semantic codes require a shared vocabulary update.
17. The shared Pydantic model or generated JSON Schema is the machine source of truth. This Markdown file explains that source.

## 4. Layer A — MealRequestCandidateV2

This is the only structure produced by the pre-Step-5 language agent.

The application supplies request IDs and source text to the run. The agent does not echo the complete raw input and does not generate runtime policy fields.

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| locale | LocaleCode | Yes | Primary language of the request. |
| occasion | OccasionCandidateV2 | Yes | Meal and event context. |
| party | PartyCandidateV2 | Yes | Total count and mutually exclusive groups. |
| location_hint | LocationHintV2 or null | Yes | Location extracted from user language, if any. |
| food_scope | FoodScopeV2 | Yes | Requested and excluded food categories. |
| hard_requirements | HardRequirementV2[] | Yes | Mandatory participant eligibility rules. |
| preferences | PreferenceV2[] | Yes | Soft ranking signals. |
| budget_intent | BudgetIntentV2 | Yes | User-expressed budget meaning. |
| quantity_preference | QuantityPreferenceCandidateV2 | Yes | User preference about shortage and leftovers; nullable fields mean unstated. |
| restaurant_preferences | RestaurantPreferencesV2 | Yes | Named restaurant wishes and exclusions. |
| restriction_disclosure | RestrictionDisclosureV2 | Yes | Whether restrictions were reported. |
| context_notes | string[] | Yes | Relevant free-form context not represented elsewhere. |
| evidence | EvidenceV2[] | Yes | Traceability for material extraction. |
| unresolved_issues | UnresolvedIssueV2[] | Yes | Missing, ambiguous, conflicting, or unsupported facts. |

### 4.1 OccasionCandidateV2

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| meal_type | MealType | Yes | Normalized meal time/type. |
| service_style | ServiceStyle | Yes | Full meal, light meal, snack, or other. |
| activity_context | ActivityContext | Yes | Event-level context. |
| food_role | FoodRole | Yes | Whether food is primary or supplementary. |
| leftover_storage | LeftoverStorage | Yes | Whether leftovers can be stored. |
| scheduled_at | Timestamp or null | Yes | Desired eating/delivery time from user text. |
| duration_minutes | integer or null | Yes | Positive event duration. |

### 4.2 PartyCandidateV2

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| total_count | integer | Yes | Total people; candidate must be an integer. |
| groups | ParticipantGroupV2[] | Yes | Mutually exclusive groups whose counts should sum to total_count. |

Demographic sex counts are intentionally excluded. The quantity engine does not use gender as an appetite proxy.

### 4.3 ParticipantGroupV2

Every person belongs to exactly one group. Split groups whenever appetite, attendance, activity, recent-meal status, or applicable hard requirements differ materially.

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| group_id | Identifier | Yes | Unique group ID within the profile. |
| display_label | string or null | Yes | Optional UI label. |
| count | integer | Yes | People in the group. |
| attendance_status | AttendanceStatus | Yes | Expected attendance state. |
| appetite | AppetiteProfileV2 | Yes | Qualitative or explicit appetite. |
| activity_level | ActivityLevel | Yes | Group-specific pre-meal activity. |
| recent_meal_status | RecentMealStatus | Yes | Group-specific recent eating. |

If it is unclear whether two hard restrictions apply to the same participant and the overlap changes eligibility, the agent records an unresolved issue. It does not invent an overlap.

### 4.4 AppetiteProfileV2

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| band | AppetiteBand | Yes | Normalized appetite band. |
| stated_servings_milli | integer or null | Yes | Explicit servings per person in milli-servings, from 0 through 10000. |

Steps 1–4 normalize an explicit quantity into milli-servings but do not calculate total required servings.

### 4.5 LocationHintV2

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| source | LocationSource | Yes | Where the hint came from. |
| query | string or null | Yes | User-readable area text. |
| latitude | number or null | Yes | WGS84 latitude. |
| longitude | number or null | Yes | WGS84 longitude. |

This is a hint, not necessarily the resolved search location. Application code resolves it with request context before Step 5.

### 4.6 FoodScopeV2

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| requested_categories | SemanticTermV2[] | Yes | Requested food categories. |
| category_selection | CategorySelection | Yes | Whether all or any requested categories are required/preferred. |
| excluded_categories | SemanticTermV2[] | Yes | Categories the planner may not use. |
| restaurant_mixing | RestaurantMixing | Yes | Single-restaurant versus multi-restaurant preference. |

Category selection semantics:

| Value | Meaning |
| --- | --- |
| include_all | At least one eligible item from every requested category is a hard order constraint. |
| any_of | At least one requested category must appear. |
| prefer_all | Cover all when feasible, but category diversity is soft. |

### 4.7 HardRequirementV2

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| requirement_id | Identifier | Yes | Unique requirement ID. |
| kind | HardRequirementKind | Yes | Allergy, diet, exclusion, religious rule, or spice limit. |
| affected_group_ids | Identifier[] | Yes | Non-empty protected groups. |
| terms | SemanticTermV2[] | Yes | Non-empty normalized terms. |
| source_text | string | Yes | Exact relevant user wording. |

Hard requirements are enforced by deterministic eligibility rules. Model inference never establishes allergy safety.

### 4.8 PreferenceV2

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| preference_id | Identifier | Yes | Unique preference ID. |
| target_kind | PreferenceTargetKind | Yes | Preference subject. |
| polarity | PreferencePolarity | Yes | Prefer or avoid. |
| strength | PreferenceStrength | Yes | Soft ranking strength. |
| affected_group_ids | Identifier[] | Yes | Empty means the entire party. |
| terms | SemanticTermV2[] | Yes | Zero or more normalized terms. |
| source_text | string | Yes | Exact phrase for semantic matching. |

Preferences never directly exclude a menu item. They create a bounded ranking reward or penalty. A medical allergy belongs in HardRequirementV2, not PreferenceV2.

### 4.9 BudgetIntentV2

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| budget_type | BudgetIntentType | Yes | No budget, hard maximum, or approximate target. |
| currency | CurrencyCode or null | Yes | KRW when an amount exists. |
| target_amount_minor | integer or null | Yes | Soft target amount. |
| explicit_maximum_amount_minor | integer or null | Yes | User-stated hard maximum. |
| cost_scope | CostScopeCandidateV2 | Yes | Which cost components the user explicitly addressed. |
| source_text | string or null | Yes | Exact budget wording. |

Rules:

- no_budget requires both amounts and currency to be null.
- hard_maximum requires explicit_maximum_amount_minor.
- approximate_target requires target_amount_minor.
- An approximate target may have an explicit maximum, but the language agent never invents one.

### 4.10 CostScopeCandidateV2

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| include_menu_price | boolean or null | Yes | Whether the user explicitly included menu subtotal. |
| include_delivery_fee | boolean or null | Yes | Whether the user explicitly included delivery fees. |
| include_service_fee | boolean or null | Yes | Whether the user explicitly included service/platform fees. |
| include_discount | boolean or null | Yes | Whether the user explicitly allowed confirmed discounts. |

Null means unstated, not false. The deterministic validator resolves every null using trusted policy and discloses the result as an assumption.

### 4.11 QuantityPreferenceCandidateV2

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| primary_objective | RiskPreference or null | Yes | Main leftover/shortage objective, when stated. |
| shortage_tolerance | ToleranceLevel or null | Yes | User's qualitative shortage tolerance. |
| leftover_tolerance | ToleranceLevel or null | Yes | User's qualitative leftover tolerance. |

There is no numerical safety margin here. PlannerRuntimePolicyV2 maps these qualitative values to deterministic margins.

### 4.12 RestaurantPreferencesV2

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| preferred_names | string[] | Yes | Soft restaurant-name preferences. |
| excluded_names | string[] | Yes | Hard user-stated restaurant exclusions. |

Names are user strings, not verified branch identities.

### 4.13 RestrictionDisclosureV2

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| status | RestrictionDisclosureStatus | Yes | reported, none_reported, or not_provided. |

none_reported means the user explicitly reported none. not_provided means restrictions were not discussed. Neither proves restaurant food is allergen-free.

### 4.14 UnresolvedIssueV2

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| issue_id | Identifier | Yes | Unique candidate issue ID. |
| kind | UnresolvedIssueKind | Yes | Missing, ambiguous, conflicting, or unsupported. |
| field_path | FieldPath or null | Yes | Candidate field involved. |
| message | string | Yes | What remains unresolved. |
| source_text | string or null | Yes | Relevant phrase. |

The language agent identifies unresolved issues, but the deterministic validator decides whether each is blocking.

## 5. Layer B — PlanningIntakeV2

PlanningIntakeV2 is the deterministic Step-4 boundary output. It is created by validating and normalizing MealRequestCandidateV2 together with trusted request context.

### 5.1 Top-level fields

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| schema_name | literal planning_intake | Yes | Schema identity. |
| schema_version | literal 2.0 | Yes | Structural version. |
| vocabulary_version | literal 1.0 | Yes | Semantic-code registry version. |
| status | literal ready_for_planning | Yes | Admission discriminator. |
| request_id | Identifier | Yes | Request correlation ID. |
| case_id | Identifier | Yes | Stable meal-planning case ID. |
| profile_revision | integer | Yes | Positive revision, starting at 1. |
| validated_at | Timestamp | Yes | Admission timestamp. |
| profile | ValidatedMealProfileV2 | Yes | Immutable validated user facts. |
| validation_receipt | ValidationReceiptV2 | Yes | Checks, warnings, and assumptions. |

Only this ready variant enters PlanningJobV2. ClarificationRequiredV2 and RequestRejectedV2 are separate terminal boundary types.

### 5.2 ValidatedMealProfileV2

This type contains the same user-meaning fields as MealRequestCandidateV2 with these changes:

- location_hint becomes validated location_requirement.
- budget_intent becomes resolved budget.
- unresolved_issues are removed after classification.
- invalid or unsupported semantic terms are rejected.
- approved defaults appear in validation_receipt.

| Field | Type | Required |
| --- | --- | --- |
| locale | LocaleCode | Yes |
| occasion | OccasionCandidateV2 | Yes |
| party | PartyCandidateV2 | Yes |
| location_requirement | LocationRequirementV2 | Yes |
| food_scope | FoodScopeV2 | Yes |
| hard_requirements | HardRequirementV2[] | Yes |
| preferences | PreferenceV2[] | Yes |
| budget | ResolvedBudgetV2 | Yes |
| quantity_preference | QuantityPreferenceV2 | Yes |
| restaurant_preferences | RestaurantPreferencesV2 | Yes |
| restriction_disclosure | RestrictionDisclosureV2 | Yes |
| context_notes | string[] | Yes |
| evidence | EvidenceV2[] | Yes |

### 5.3 LocationRequirementV2

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| delivery_required | boolean | Yes | Whether restaurant delivery relevance must be checked. |
| source | LocationSource | Yes | Origin of the accepted location. |
| query | string or null | Yes | Accepted location text. |
| latitude | number or null | Yes | Accepted latitude. |
| longitude | number or null | Yes | Accepted longitude. |

When delivery_required is true, either a usable query or a complete coordinate pair must exist. Final resolved coordinates may still be supplied in PlannerExecutionContextV2.

### 5.4 ResolvedBudgetV2

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| budget_type | ResolvedBudgetType | Yes | No budget, hard maximum, or approximate target. |
| currency | CurrencyCode or null | Yes | KRW when amounts exist. |
| target_amount_minor | integer or null | Yes | Soft target used in ranking. |
| maximum_amount_minor | integer or null | Yes | Deterministic hard ceiling. |
| maximum_source | BudgetMaximumSource | Yes | How the ceiling was obtained. |
| cost_scope | CostScopeV2 | Yes | Included cost components. |

Rules:

- no_budget has null target and maximum with maximum_source none, unless the
  temporary hackathon default budget policy is enabled by the validator.
- hard_maximum has a positive maximum with maximum_source explicit or
  policy_default.
- approximate_target has a positive target and a positive maximum.
- If the user gave no explicit approximate maximum, the validator applies the configured tolerance and records maximum_source policy_tolerance plus an assumption.
- TEMPORARY HACKATHON DEFAULT: when the user omits a budget and the validator
  policy enables it, the planner receives a hard maximum of
  `temporary_default_budget_per_person_minor * party.total_count`, currently
  `12,000 KRW/person`. This value is replaceable and must not be treated as a
  permanent product rule.
- A high maximum is a ceiling, never a spending target.

### 5.5 CostScopeV2

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| include_menu_price | boolean | Yes | Include menu subtotal. |
| include_delivery_fee | boolean | Yes | Include delivery fee. |
| include_service_fee | boolean | Yes | Include service/platform fee. |
| include_discount | boolean | Yes | Allow only confirmed discounts to reduce cost. |

### 5.6 QuantityPreferenceV2

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| primary_objective | RiskPreference | Yes | Resolved optimization objective. |
| shortage_tolerance | ToleranceLevel | Yes | Resolved shortage tolerance. |
| leftover_tolerance | ToleranceLevel | Yes | Resolved leftover tolerance. |

### 5.7 ValidationReceiptV2

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| validator_version | string | Yes | Validator implementation/rule version. |
| blocking_issues | ContractIssueV2[] | Yes | Always empty for ready_for_planning. |
| warnings | ContractIssueV2[] | Yes | Non-blocking issues Step 5 must respect or disclose. |
| assumptions | AssumptionV2[] | Yes | Defaults approved by deterministic validation. |
| checked_invariants | string[] | Yes | Stable codes for checks that ran. |

### 5.8 ClarificationRequiredV2

| Field | Type | Required |
| --- | --- | --- |
| schema_name | literal planning_intake | Yes |
| schema_version | literal 2.0 | Yes |
| vocabulary_version | literal 1.0 | Yes |
| status | literal clarification_required | Yes |
| request_id | Identifier | Yes |
| case_id | Identifier | Yes |
| profile_revision | integer | Yes |
| issues | ContractIssueV2[] | Yes, non-empty |
| questions | string[] | Yes, non-empty |

### 5.9 RequestRejectedV2

| Field | Type | Required |
| --- | --- | --- |
| schema_name | literal planning_intake | Yes |
| schema_version | literal 2.0 | Yes |
| vocabulary_version | literal 1.0 | Yes |
| status | literal request_rejected | Yes |
| request_id | Identifier | Yes |
| case_id | Identifier | Yes |
| reason_code | string | Yes |
| issues | ContractIssueV2[] | Yes, non-empty |

## 6. Layer C — PlanningJobV2

PlanningJobV2 is assembled by application code after PlanningIntakeV2 succeeds. It is the exact Step-5 entry type.

| Field | Type | Required | Owner |
| --- | --- | --- | --- |
| schema_name | literal planning_job | Yes | Application |
| schema_version | literal 2.0 | Yes | Application |
| vocabulary_version | literal 1.0 | Yes | Application |
| intake | PlanningIntakeV2 | Yes | Steps 1–4 |
| runtime_policy | PlannerRuntimePolicyV2 | Yes | Trusted application configuration |
| execution_context | PlannerExecutionContextV2 | Yes | Application/runtime |

Recommended entry point:

~~~python
async def plan_order(
    job: PlanningJobV2,
    dependencies: PlannerDependencies,
) -> PlanningOutcomeV2:
    ...
~~~

### 6.1 PlannerRuntimePolicyV2

This object is never generated by the language agent.

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| serving_policy | ServingPolicyRefV2 | Yes | Deterministic serving and quantity policy IDs. |
| budget_policy | BudgetPolicyV2 | Yes | Approximate-budget resolution policy. |
| restaurant_search | RestaurantSearchPolicyV2 | Yes | Search limits and delivery requirement. |
| menu_filter | MenuFilterPolicyV2 | Yes | Unknown-data and hard-constraint rules. |
| combination | CombinationPolicyV2 | Yes | Optimizer bounds. |
| ranking | RankingPolicyV2 | Yes | Deterministic ranking configuration. |

### 6.2 ServingPolicyRefV2

| Field | Type | Required |
| --- | --- | --- |
| serving_policy_id | string | Yes |
| quantity_policy_id | string | Yes |

The referenced policies own appetite factors, context modifiers, evidence priority, and risk-to-safety-margin mappings.

### 6.3 BudgetPolicyV2

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| policy_id | string | Yes | Versioned policy identity. |
| approximate_tolerance_basis_points | integer | Yes | Allowed increase used to derive an approximate hard ceiling. |

This value is deterministic configuration, not a model judgment.

### 6.4 RestaurantSearchPolicyV2

| Field | Type | Required |
| --- | --- | --- |
| policy_id | string | Yes |
| restaurant_limit | integer | Yes; 1–10 for MVP |
| delivery_required | boolean | Yes |
| allow_bounded_refresh | boolean | Yes |
| maximum_cache_age_seconds | integer | Yes; non-negative |

### 6.5 MenuFilterPolicyV2

| Field | Type | Required |
| --- | --- | --- |
| policy_id | string | Yes |
| evaluation_mode | literal individual_menu | Yes |
| unknown_ingredient_policy | UnknownIngredientPolicy | Yes |
| hard_constraint_unknown_policy | literal exclude | Yes |
| eligibility_output_schema | string | Yes |

Unknown semantic or ingredient data can remain for soft ranking, but an item with unknown data relevant to a hard allergy or diet is excluded from covering the affected group.

### 6.6 CombinationPolicyV2

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| policy_id | string | Yes | Policy identity. |
| allow_duplicate_menu_items | boolean | Yes | Whether multiple units of one item are allowed. |
| maximum_distinct_items | integer or null | Yes | Optimizer bound. |
| maximum_total_quantity | integer or null | Yes | Whole-sale-unit bound. |

Minimum category coverage is derived from profile.food_scope.category_selection:

- include_all derives minimum one eligible item from each requested category.
- any_of derives minimum one eligible requested category.
- prefer_all creates a ranking objective rather than a hard minimum.

### 6.7 RankingPolicyV2

| Field | Type | Required |
| --- | --- | --- |
| policy_id | string | Yes |
| objectives | RankingObjectiveV2[] | Yes, non-empty |
| diversity | DiversityPolicyV2 | Yes |

Every objective weight is an integer from 0 through 10000 and all weights sum exactly to 10000.

### 6.8 RankingObjectiveV2

| Field | Type | Required |
| --- | --- | --- |
| metric | RankingMetric | Yes |
| weight_basis_points | integer | Yes |

### 6.9 DiversityPolicyV2

| Field | Type | Required |
| --- | --- | --- |
| category_balance | boolean | Yes |
| avoid_single_item_dominance | boolean | Yes |
| duplicate_penalty_basis_points | integer | Yes; 0–10000 |

### 6.10 PlannerExecutionContextV2

This object contains observed runtime facts, not user-language interpretation.

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| requested_at | Timestamp | Yes | Actual planning start time. |
| resolved_location | ResolvedLocationV2 | Yes | Runtime search location. |
| restaurant_snapshot_id | string or null | Yes | Selected cache/snapshot identity. |
| trace_id | string | Yes | End-to-end trace correlation ID. |

### 6.11 ResolvedLocationV2

| Field | Type | Required |
| --- | --- | --- |
| source | LocationSource | Yes |
| query | string | Yes |
| latitude | number or null | Yes |
| longitude | number or null | Yes |

When runtime restaurant search requires coordinates, both latitude and longitude must be present.

## 7. Shared support types

### 7.1 SemanticTermV2

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| namespace | SemanticNamespace | Yes | Vocabulary family. |
| code | string | Yes | Stable code from vocabulary_version. |
| label | string | Yes | Display label; never used as identity. |

### 7.2 EvidenceV2

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| evidence_id | Identifier | Yes | Unique within the profile. |
| field_path | FieldPath | Yes | Field supported by the evidence. |
| source_text | string or null | Yes | Exact relevant phrase; null only for a default. |
| status | EvidenceStatus | Yes | explicit, inferred, defaulted, or conflicted. |
| confidence | number | Yes; 0.0–1.0 | Extraction confidence. |
| start_offset | integer or null | Yes | Zero-based raw-input start offset. |
| end_offset | integer or null | Yes | Exclusive end offset. |
| note | string or null | Yes | Inference/default explanation. |

Confidence never independently establishes price, identity, availability, serving quantity, or allergy safety.

### 7.3 ContractIssueV2

| Field | Type | Required |
| --- | --- | --- |
| code | string | Yes |
| severity | IssueSeverity | Yes |
| field_path | FieldPath or null | Yes |
| message | string | Yes |
| evidence_ids | Identifier[] | Yes |

### 7.4 AssumptionV2

| Field | Type | Required |
| --- | --- | --- |
| code | string | Yes |
| field_path | FieldPath | Yes |
| applied_value | string | Yes |
| reason | string | Yes |
| evidence_ids | Identifier[] | Yes |

## 8. Enum glossary

| Enum | Allowed values |
| --- | --- |
| IntakeStatus | ready_for_planning, clarification_required, request_rejected |
| LocaleCode | ko, en, mixed, unknown |
| MealType | breakfast, lunch, dinner, late_night, snack, other |
| ServiceStyle | full_meal, light_meal, snack, shared_tasting, other |
| ActivityContext | ordinary, club_meal, meeting, workshop, party, sports_event, school_event, other |
| FoodRole | primary_meal, supplementary_meal, snack, tasting, other |
| LeftoverStorage | available, unavailable, unknown |
| AttendanceStatus | confirmed, expected, uncertain, late |
| AppetiteBand | very_light, light, normal, large, very_large, custom |
| ActivityLevel | none, light, moderate, heavy, unknown |
| RecentMealStatus | not_recent, light_meal_recently, full_meal_recently, unknown |
| LocationSource | user_text, browser_geolocation, request_context, application_default |
| CategorySelection | include_all, any_of, prefer_all |
| RestaurantMixing | single_restaurant_required, single_restaurant_preferred, multiple_allowed, unspecified |
| HardRequirementKind | allergy, diet, food_exclusion, religious_rule, spice_limit |
| PreferenceTargetKind | food_category, dish, ingredient, flavor, texture, spice, restaurant, variety, other |
| PreferencePolarity | prefer, avoid |
| PreferenceStrength | weak, normal, strong |
| BudgetIntentType | no_budget, hard_maximum, approximate_target |
| ResolvedBudgetType | no_budget, hard_maximum, approximate_target |
| BudgetMaximumSource | none, explicit, policy_tolerance |
| CurrencyCode | KRW |
| RiskPreference | minimize_leftovers, balanced, minimize_shortage |
| ToleranceLevel | low, normal, high |
| RestrictionDisclosureStatus | reported, none_reported, not_provided |
| UnresolvedIssueKind | missing, ambiguous, conflicting, unsupported |
| EvidenceStatus | explicit, inferred, defaulted, conflicted |
| IssueSeverity | warning, blocking, fatal |
| SemanticNamespace | allergen, diet, ingredient, food_category, spice, dish, flavor, restaurant_feature, other |
| UnknownIngredientPolicy | keep_with_penalty, exclude |
| RankingMetric | constraint_satisfaction, serving_fit, menu_diversity, budget_efficiency, order_simplicity, delivery_fit |

## 9. Known vocabulary v1.0 and open semantic terms

Semantic codes live in one shared registry. The following are known v1.0 codes
used for deterministic matching and warnings:

| Namespace | Codes |
| --- | --- |
| food_category | chicken, pizza |
| allergen | peanut, tree_nut, milk, egg, wheat, soy, fish, shellfish, sesame |
| diet | vegetarian, vegan, pescatarian, no_pork, halal, kosher |
| spice | not_spicy, mild, medium, hot, very_hot |

This list is an MVP interoperability registry, not a complete legal allergen list.

The intake boundary is open-set for semantically valid food, ingredient, dish,
flavor, and allergen terms. Unknown terms preserve their literal label/code and
are passed to the planner for conservative eligibility or capability handling;
they are never silently ignored, invented, or fuzzy-merged. The current
restaurant snapshot planner has adapters for chicken and pizza, so an accepted
category without an adapter produces a structured `unsupported` planning
failure after the planner starts.

## 10. Deterministic admission invariants

Before emitting PlanningIntakeV2 with ready_for_planning, Step 4 guarantees:

1. total_count is an integer from 1 through 100.
2. Participant groups are non-empty.
3. Every group count is positive.
4. Groups are mutually exclusive and counts sum exactly to total_count.
5. Every affected_group_id exists.
6. A participant with multiple hard restrictions belongs to a group covered by all applicable requirements.
7. Every hard requirement has at least one affected group and terms with valid semantic namespaces; unknown terms remain explicit for downstream conservative validation.
8. Hard requirements and soft preferences are separate.
9. No material field remains conflicted.
10. stated_servings_milli is null or from 0 through 10000.
11. Budget is fully resolved according to ResolvedBudgetV2 rules.
12. Allowed and excluded food categories do not overlap.
13. requested_categories is non-empty and each term uses the food_category namespace.
14. A delivery-required request has a usable location requirement.
15. Timestamps include timezones.
16. blocking_issues is empty.
17. Approved defaults appear in validation_receipt.assumptions.
18. Material invented, absurd, or unsupported facts are preserved and produce a structured unresolved, unsupported, or no-valid-plan outcome; no external food fact is invented.
19. Missing restriction information remains disclosed and never becomes verified safety.
20. The candidate contains no runtime policy or calculated serving requirement.
21. Candidate null cost-scope fields are resolved to booleans before Step 5.
22. Candidate null quantity preferences are resolved and disclosed before Step 5.
23. restaurant_mixing is not unspecified in the ready profile.

Required checked_invariants codes:

- total_count_in_supported_range
- participant_groups_non_empty
- participant_group_counts_match_total
- participant_groups_mutually_exclusive
- hard_requirement_groups_exist
- hard_requirement_terms_preserved_for_planner_validation
- hard_and_soft_constraints_separated
- blocking_conflicts_absent
- explicit_servings_in_supported_range
- budget_resolved
- food_scope_term_namespaces_valid
- location_requirement_usable
- timestamps_timezone_aware
- material_fields_have_evidence_or_disclosed_defaults
- runtime_policy_not_model_owned
- cost_scope_resolved
- quantity_preference_resolved
- restaurant_mixing_resolved

## 11. Ownership guarantees

### Pre-Step-5 language agent

- Produces only MealRequestCandidateV2.
- Extracts semantic meaning and preserves source evidence.
- Does not calculate total servings, costs, rankings, or order combinations.
- Does not choose policy IDs, search limits, safety margins, or ranking weights.
- Does not silently repair absurd, conflicting, or unsupported facts.
- Does not echo the entire raw user input.

### Deterministic Step-4 validator

- Applies range, consistency, overlap, unit, vocabulary, and readiness checks.
- Classifies unresolved issues as blocking or non-blocking.
- Applies only documented defaults.
- Resolves approximate-budget ceilings using trusted policy.
- Produces PlanningIntakeV2, ClarificationRequiredV2, or RequestRejectedV2.

### Application assembler

- Supplies PlannerRuntimePolicyV2 and PlannerExecutionContextV2.
- Resolves runtime location and time.
- Selects a restaurant snapshot or permits a bounded refresh.
- Creates PlanningJobV2 without asking the model to regenerate validated fields.

### Step-5 planner

- Accepts only PlanningJobV2.
- Treats intake.profile as immutable.
- Never weakens hard requirements.
- Uses runtime policy rather than inventing parameters.
- Returns no_valid_plan when valid user requirements cannot be satisfied.
- Returns profile_contract_error when the producer breaks this contract.

## 12. MealRequestCandidateV2 template

This is the structured output schema/example for the pre-Step-5 language agent. The Agents SDK should enforce its Pydantic output type; the system prompt explains the semantic rules.

~~~json
{
  "locale": "ko",
  "occasion": {
    "meal_type": "dinner",
    "service_style": "full_meal",
    "activity_context": "club_meal",
    "food_role": "primary_meal",
    "leftover_storage": "available",
    "scheduled_at": null,
    "duration_minutes": null
  },
  "party": {
    "total_count": 15,
    "groups": [
      {
        "group_id": "group_large",
        "display_label": "많이 먹는 사람",
        "count": 4,
        "attendance_status": "confirmed",
        "appetite": {
          "band": "large",
          "stated_servings_milli": null
        },
        "activity_level": "unknown",
        "recent_meal_status": "unknown"
      },
      {
        "group_id": "group_regular",
        "display_label": "보통으로 먹는 사람",
        "count": 8,
        "attendance_status": "confirmed",
        "appetite": {
          "band": "normal",
          "stated_servings_milli": null
        },
        "activity_level": "unknown",
        "recent_meal_status": "unknown"
      },
      {
        "group_id": "group_small",
        "display_label": "적게 먹는 사람",
        "count": 3,
        "attendance_status": "confirmed",
        "appetite": {
          "band": "light",
          "stated_servings_milli": null
        },
        "activity_level": "unknown",
        "recent_meal_status": "unknown"
      }
    ]
  },
  "location_hint": null,
  "food_scope": {
    "requested_categories": [
      {
        "namespace": "food_category",
        "code": "chicken",
        "label": "치킨"
      },
      {
        "namespace": "food_category",
        "code": "pizza",
        "label": "피자"
      }
    ],
    "category_selection": "include_all",
    "excluded_categories": [],
    "restaurant_mixing": "unspecified"
  },
  "hard_requirements": [],
  "preferences": [
    {
      "preference_id": "preference_spicy",
      "target_kind": "spice",
      "polarity": "avoid",
      "strength": "strong",
      "affected_group_ids": [],
      "terms": [
        {
          "namespace": "spice",
          "code": "hot",
          "label": "매운 음식"
        }
      ],
      "source_text": "매운 음식은 피하고 싶어."
    }
  ],
  "budget_intent": {
    "budget_type": "approximate_target",
    "currency": "KRW",
    "target_amount_minor": 250000,
    "explicit_maximum_amount_minor": null,
    "cost_scope": {
      "include_menu_price": null,
      "include_delivery_fee": null,
      "include_service_fee": null,
      "include_discount": null
    },
    "source_text": "예산은 25만원 정도야."
  },
  "quantity_preference": {
    "primary_objective": null,
    "shortage_tolerance": null,
    "leftover_tolerance": null
  },
  "restaurant_preferences": {
    "preferred_names": [],
    "excluded_names": []
  },
  "restriction_disclosure": {
    "status": "not_provided"
  },
  "context_notes": [],
  "evidence": [
    {
      "evidence_id": "evidence_total",
      "field_path": "/party/total_count",
      "source_text": "동아리원 15명",
      "status": "explicit",
      "confidence": 1.0,
      "start_offset": null,
      "end_offset": null,
      "note": null
    },
    {
      "evidence_id": "evidence_appetite",
      "field_path": "/party/groups",
      "source_text": "많이 먹는 사람 4명, 보통 8명, 적게 먹는 사람 3명",
      "status": "explicit",
      "confidence": 0.99,
      "start_offset": null,
      "end_offset": null,
      "note": null
    },
    {
      "evidence_id": "evidence_meal_type",
      "field_path": "/occasion/meal_type",
      "source_text": "저녁으로",
      "status": "explicit",
      "confidence": 1.0,
      "start_offset": null,
      "end_offset": null,
      "note": null
    },
    {
      "evidence_id": "evidence_categories",
      "field_path": "/food_scope/requested_categories",
      "source_text": "치킨이랑 피자",
      "status": "explicit",
      "confidence": 1.0,
      "start_offset": null,
      "end_offset": null,
      "note": null
    },
    {
      "evidence_id": "evidence_budget",
      "field_path": "/budget_intent/target_amount_minor",
      "source_text": "예산은 25만원 정도",
      "status": "explicit",
      "confidence": 0.99,
      "start_offset": null,
      "end_offset": null,
      "note": null
    }
  ],
  "unresolved_issues": [
    {
      "issue_id": "issue_location",
      "kind": "missing",
      "field_path": "/location_hint",
      "message": "사용자 텍스트에 위치가 없습니다. 요청 컨텍스트에서 위치를 제공해야 합니다.",
      "source_text": null
    }
  ]
}
~~~

## 13. Complete PlanningJobV2 template

This valid JSON is the golden fixture for the Step-5 planner. The intake is validator-owned; runtime_policy and execution_context are application-owned.

~~~json
{
  "schema_name": "planning_job",
  "schema_version": "2.0",
  "vocabulary_version": "1.0",
  "intake": {
    "schema_name": "planning_intake",
    "schema_version": "2.0",
    "vocabulary_version": "1.0",
    "status": "ready_for_planning",
    "request_id": "req_20260801_001",
    "case_id": "case_001",
    "profile_revision": 1,
    "validated_at": "2026-08-01T14:30:00+09:00",
    "profile": {
      "locale": "ko",
      "occasion": {
        "meal_type": "dinner",
        "service_style": "full_meal",
        "activity_context": "club_meal",
        "food_role": "primary_meal",
        "leftover_storage": "available",
        "scheduled_at": null,
        "duration_minutes": null
      },
      "party": {
        "total_count": 15,
        "groups": [
          {
            "group_id": "group_large",
            "display_label": "많이 먹는 사람",
            "count": 4,
            "attendance_status": "confirmed",
            "appetite": {
              "band": "large",
              "stated_servings_milli": null
            },
            "activity_level": "unknown",
            "recent_meal_status": "unknown"
          },
          {
            "group_id": "group_regular",
            "display_label": "보통으로 먹는 사람",
            "count": 8,
            "attendance_status": "confirmed",
            "appetite": {
              "band": "normal",
              "stated_servings_milli": null
            },
            "activity_level": "unknown",
            "recent_meal_status": "unknown"
          },
          {
            "group_id": "group_small",
            "display_label": "적게 먹는 사람",
            "count": 3,
            "attendance_status": "confirmed",
            "appetite": {
              "band": "light",
              "stated_servings_milli": null
            },
            "activity_level": "unknown",
            "recent_meal_status": "unknown"
          }
        ]
      },
      "location_requirement": {
        "delivery_required": true,
        "source": "request_context",
        "query": "Sinchon, Seoul",
        "latitude": 37.5596,
        "longitude": 126.9423
      },
      "food_scope": {
        "requested_categories": [
          {
            "namespace": "food_category",
            "code": "chicken",
            "label": "치킨"
          },
          {
            "namespace": "food_category",
            "code": "pizza",
            "label": "피자"
          }
        ],
        "category_selection": "include_all",
        "excluded_categories": [],
        "restaurant_mixing": "single_restaurant_preferred"
      },
      "hard_requirements": [],
      "preferences": [
        {
          "preference_id": "preference_spicy",
          "target_kind": "spice",
          "polarity": "avoid",
          "strength": "strong",
          "affected_group_ids": [],
          "terms": [
            {
              "namespace": "spice",
              "code": "hot",
              "label": "매운 음식"
            }
          ],
          "source_text": "매운 음식은 피하고 싶어."
        }
      ],
      "budget": {
        "budget_type": "approximate_target",
        "currency": "KRW",
        "target_amount_minor": 250000,
        "maximum_amount_minor": 275000,
        "maximum_source": "policy_tolerance",
        "cost_scope": {
          "include_menu_price": true,
          "include_delivery_fee": true,
          "include_service_fee": true,
          "include_discount": false
        }
      },
      "quantity_preference": {
        "primary_objective": "balanced",
        "shortage_tolerance": "normal",
        "leftover_tolerance": "normal"
      },
      "restaurant_preferences": {
        "preferred_names": [],
        "excluded_names": []
      },
      "restriction_disclosure": {
        "status": "not_provided"
      },
      "context_notes": [],
      "evidence": [
        {
          "evidence_id": "evidence_total",
          "field_path": "/profile/party/total_count",
          "source_text": "동아리원 15명",
          "status": "explicit",
          "confidence": 1.0,
          "start_offset": null,
          "end_offset": null,
          "note": null
        },
        {
          "evidence_id": "evidence_appetite",
          "field_path": "/profile/party/groups",
          "source_text": "많이 먹는 사람 4명, 보통 8명, 적게 먹는 사람 3명",
          "status": "explicit",
          "confidence": 0.99,
          "start_offset": null,
          "end_offset": null,
          "note": null
        },
        {
          "evidence_id": "evidence_meal_type",
          "field_path": "/profile/occasion/meal_type",
          "source_text": "저녁으로",
          "status": "explicit",
          "confidence": 1.0,
          "start_offset": null,
          "end_offset": null,
          "note": null
        },
        {
          "evidence_id": "evidence_categories",
          "field_path": "/profile/food_scope/requested_categories",
          "source_text": "치킨이랑 피자",
          "status": "explicit",
          "confidence": 1.0,
          "start_offset": null,
          "end_offset": null,
          "note": null
        },
        {
          "evidence_id": "evidence_budget",
          "field_path": "/profile/budget/target_amount_minor",
          "source_text": "예산은 25만원 정도",
          "status": "explicit",
          "confidence": 0.99,
          "start_offset": null,
          "end_offset": null,
          "note": null
        }
      ]
    },
    "validation_receipt": {
      "validator_version": "validator-2.0",
      "blocking_issues": [],
      "warnings": [
        {
          "code": "restriction_information_not_provided",
          "severity": "warning",
          "field_path": "/profile/restriction_disclosure/status",
          "message": "No dietary or allergy information was provided; this is not verified allergen safety.",
          "evidence_ids": []
        }
      ],
      "assumptions": [
        {
          "code": "approximate_budget_tolerance_applied",
          "field_path": "/profile/budget/maximum_amount_minor",
          "applied_value": "275000",
          "reason": "The configured 10% tolerance was applied to the approximate ₩250,000 target.",
          "evidence_ids": ["evidence_budget"]
        },
        {
          "code": "default_cost_scope_applied",
          "field_path": "/profile/budget/cost_scope",
          "applied_value": "menu_price=true,delivery_fee=true,service_fee=true,discount=false",
          "reason": "The user did not define which charges or discounts the approximate budget included.",
          "evidence_ids": ["evidence_budget"]
        },
        {
          "code": "default_quantity_preference_balanced",
          "field_path": "/profile/quantity_preference",
          "applied_value": "balanced,normal,normal",
          "reason": "The user did not state a shortage-versus-leftover preference.",
          "evidence_ids": []
        },
        {
          "code": "default_restaurant_mixing_preference",
          "field_path": "/profile/food_scope/restaurant_mixing",
          "applied_value": "single_restaurant_preferred",
          "reason": "The user did not state whether combining restaurants was acceptable.",
          "evidence_ids": []
        }
      ],
      "checked_invariants": [
        "total_count_in_supported_range",
        "participant_groups_non_empty",
        "participant_group_counts_match_total",
        "participant_groups_mutually_exclusive",
        "hard_requirement_groups_exist",
        "hard_requirement_terms_supported",
        "hard_and_soft_constraints_separated",
        "blocking_conflicts_absent",
        "explicit_servings_in_supported_range",
        "budget_resolved",
        "food_scope_supported",
        "location_requirement_usable",
        "timestamps_timezone_aware",
        "material_fields_have_evidence_or_disclosed_defaults",
        "runtime_policy_not_model_owned",
        "cost_scope_resolved",
        "quantity_preference_resolved",
        "restaurant_mixing_resolved"
      ]
    }
  },
  "runtime_policy": {
    "serving_policy": {
      "serving_policy_id": "serving-policy-kr-v1",
      "quantity_policy_id": "quantity-policy-v1"
    },
    "budget_policy": {
      "policy_id": "budget-policy-v1",
      "approximate_tolerance_basis_points": 1000
    },
    "restaurant_search": {
      "policy_id": "restaurant-search-v1",
      "restaurant_limit": 10,
      "delivery_required": true,
      "allow_bounded_refresh": true,
      "maximum_cache_age_seconds": 86400
    },
    "menu_filter": {
      "policy_id": "menu-filter-v1",
      "evaluation_mode": "individual_menu",
      "unknown_ingredient_policy": "keep_with_penalty",
      "hard_constraint_unknown_policy": "exclude",
      "eligibility_output_schema": "menu-eligibility-v1"
    },
    "combination": {
      "policy_id": "combination-policy-v1",
      "allow_duplicate_menu_items": true,
      "maximum_distinct_items": null,
      "maximum_total_quantity": null
    },
    "ranking": {
      "policy_id": "combination-ranking-v1",
      "objectives": [
        {
          "metric": "constraint_satisfaction",
          "weight_basis_points": 4000
        },
        {
          "metric": "serving_fit",
          "weight_basis_points": 2500
        },
        {
          "metric": "menu_diversity",
          "weight_basis_points": 2000
        },
        {
          "metric": "budget_efficiency",
          "weight_basis_points": 1500
        }
      ],
      "diversity": {
        "category_balance": true,
        "avoid_single_item_dominance": true,
        "duplicate_penalty_basis_points": 1000
      }
    }
  },
  "execution_context": {
    "requested_at": "2026-08-01T14:30:01+09:00",
    "resolved_location": {
      "source": "request_context",
      "query": "Sinchon, Seoul",
      "latitude": 37.5596,
      "longitude": 126.9423
    },
    "restaurant_snapshot_id": "snapshot_sinchon_20260801",
    "trace_id": "trace_req_20260801_001"
  }
}
~~~

## 14. Non-ready boundary templates

### 14.1 ClarificationRequiredV2

~~~json
{
  "schema_name": "planning_intake",
  "schema_version": "2.0",
  "vocabulary_version": "1.0",
  "status": "clarification_required",
  "request_id": "req_20260801_002",
  "case_id": "case_002",
  "profile_revision": 1,
  "issues": [
    {
      "code": "restriction_overlap_unclear",
      "severity": "blocking",
      "field_path": "/candidate/hard_requirements",
      "message": "It is unclear whether the vegetarian participant and peanut-allergic participant are the same person.",
      "evidence_ids": []
    }
  ],
  "questions": [
    "Is the participant with the peanut allergy also one of the vegetarian participants?"
  ]
}
~~~

### 14.2 RequestRejectedV2

~~~json
{
  "schema_name": "planning_intake",
  "schema_version": "2.0",
  "vocabulary_version": "1.0",
  "status": "request_rejected",
  "request_id": "req_20260801_003",
  "case_id": "case_003",
  "reason_code": "unsupported_physical_quantity",
  "issues": [
    {
      "code": "stated_servings_out_of_range",
      "severity": "fatal",
      "field_path": "/candidate/party/groups/0/appetite/stated_servings_milli",
      "message": "The stated quantity is outside the supported automatic-planning range.",
      "evidence_ids": ["evidence_absurd_quantity"]
    }
  ]
}
~~~

## 15. Step-5 outcomes

The planner distinguishes:

| Outcome | Meaning |
| --- | --- |
| plan_ready | At least one independently validated plan exists. |
| no_valid_plan | The intake is valid, but available menu data cannot satisfy it. |
| data_unavailable | Restaurant data cannot be obtained or safely reused. |
| profile_contract_error | Intake violates the schema or its declared invariants. |
| unsupported_schema_version | The planner does not support schema_version. |
| unsupported_vocabulary_version | The planner does not support vocabulary_version. |

The planner never turns a contract error into a recommendation.

## 16. Migration from the teammate proposal

| Teammate field | Revised action |
| --- | --- |
| schema_version, request_id, case_id | Keep in PlanningIntakeV2/application wrapper. |
| source.text | Remove from Step-5 payload; keep in request storage. Preserve only evidence snippets. |
| source.locale | Move to profile.locale using the shared enum. |
| occasion | Keep with controlled enums and duration_minutes. |
| party.demographics | Remove. |
| party.appetite and party.activity aggregate counts | Replace with mutually exclusive participant groups. |
| serving_requirement | Remove from intake; Steps 5–10 produce it. |
| food_scope | Keep with SemanticTermV2 categories. |
| constraints | Split into hard_requirements and preferences. |
| constraint.menu_application | Remove; deterministic logic derives behavior from hard versus soft type. |
| budget | Split into BudgetIntentV2 and ResolvedBudgetV2. |
| quantity_policy.safety_margin_basis_points | Move to referenced deterministic quantity policy. |
| restaurant_search.location | Split into candidate location_hint, validated location_requirement, and runtime resolved_location. |
| restaurant_search limits and requested_at | Move to runtime policy and execution context. |
| menu_filter_policy | Move to PlannerRuntimePolicyV2. |
| combination_policy | Move to PlannerRuntimePolicyV2; derive category coverage from FoodScopeV2. |
| ranking_policy | Move to PlannerRuntimePolicyV2. |
| assumptions and warnings | Replace with typed validation_receipt objects. |
| unresolved_fields | Replace with UnresolvedIssueV2, then deterministically classify into blocking issues, warnings, or assumptions. |

## 17. Agents SDK integration rule

The pre-Step-5 language agent must be configured with MealRequestCandidateV2 as its structured output type. Do not depend on a JSON example pasted into the system prompt as the only enforcement.

The system prompt should describe:

- The meaning of every semantic field.
- How to create mutually exclusive groups.
- How to distinguish hard requirements from soft preferences.
- How to preserve evidence.
- When to emit an unresolved issue.
- Which fields the agent is forbidden to calculate or configure.

The shared Pydantic/JSON Schema enforces:

- Exact field names and types.
- Required/null rules.
- Enum values.
- Rejection of unknown fields.
- Numeric bounds.

Application code, not the model, adds request identifiers, schema metadata, validator receipt, runtime policy, and execution context.

## 18. Integration checklist

Before implementing independently:

1. Both teammates approve this document.
2. Agree that external JSON uses snake_case.
3. Create one shared Python package for all contract models and enums.
4. Generate JSON Schema from the shared Pydantic models.
5. Store the MealRequestCandidateV2 example as the extraction golden fixture.
6. Store the PlanningJobV2 example as the planner golden fixture.
7. Producer test: the extraction agent output validates as MealRequestCandidateV2.
8. Validator test: candidate plus trusted context becomes exactly one boundary outcome.
9. Consumer test: Step 5 accepts the PlanningJobV2 fixture unchanged.
10. Negative test: unknown fields fail.
11. Negative test: aggregate group counts that do not sum to total_count fail.
12. Negative test: an unknown hard semantic code fails.
13. Negative test: a non-ready intake cannot construct PlanningJobV2.
14. Negative test: ranking weights that do not sum to 10000 fail.
15. Negative test: approximate budget without a resolved maximum cannot enter Step 5.
16. Put schema_version and vocabulary_version in every trace and error.
17. Require a coordinated pull request for contract or vocabulary changes.

## 19. Existing Serving Calculator Compatibility

The downstream implementation retains the existing cohort calculator behind a deterministic `build_serving_input` adapter. The intake contract does not adopt the calculator's internal names directly.

Stable aliases are:

| Contract vocabulary | Calculator vocabulary |
| --- | --- |
| `very_light` | `very_low` |
| `light` | `low` |
| `normal` | `normal` |
| `large` | `high` |
| `very_large` | `very_high` |
| `late_night` | `late_night_snack` |
| `minimize_shortage` | `avoid_shortage` |

The adapter records its version, applied aliases, accepted/skipped adjustments, warnings, and assumptions. It produces a calculator-only `ServingCalculationInputV1` and never mutates the immutable `PlanningIntakeV2`.

The calculator supports more precise adjustment codes than the current contract's coarse `activity_level` and `recent_meal_status`. Until the team coordinates an explicit contract extension or lossless mapping, the adapter applies a calculator adjustment only when validated fields plus preserved evidence unambiguously support that exact code. Otherwise it applies no adjustment and records the uncertainty. Deterministic code must not redo free-text interpretation.

Exact constants and JSON loading rules are recorded in `Config_Temp.md`. The end-to-end artifact and tool flow is recorded in `ARCHITECTURE_WORKFLOW.md`.
