# Planning Intake Contract v1.0

Status: proposed for team approval  
Boundary: deterministic profile validator (producer) to Meal Planner Agent (consumer)  
JSON convention: camelCase, UTF-8  
Contract version: 1.0  
Vocabulary version: 1.0

## 1. Purpose and boundary

This is the shared interface between:

- Steps 1–4: accept free text, interpret it, validate it, and decide whether planning may begin.
- Steps 5–10: search restaurant data, match preferences, filter items, calculate plans, validate plans, and present the result.

The boundary has three possible outcomes:

| Type | status value | Meaning | May enter Step 5? |
| --- | --- | --- | --- |
| ReadyForPlanningV1 | ready_for_planning | The profile satisfies every admission invariant. | Yes |
| ClarificationRequiredV1 | clarification_required | User clarification is required. | No |
| RequestRejectedV1 | request_rejected | The request is invalid or unsupported. | No |

The planner entry point accepts only ReadyForPlanningV1. It must not accept a generic dictionary or the three-way outcome union.

## 2. Compatibility rules

1. JSON field names use the exact camelCase spelling in this document.
2. Every object rejects unknown fields. Pydantic implementations should use extra="forbid".
3. Ready objects are immutable after validation. Pydantic implementations should use frozen=True.
4. Required fields are always present. Unknown optional scalar values are null; empty collections are arrays, not null.
5. Numbers must be finite. NaN and positive or negative infinity are forbidden.
6. Money is an integer in the smallest supported currency unit. In KRW, 250000 means ₩250,000.
7. Timestamps use RFC 3339 and include a timezone, such as 2026-08-01T14:30:00+09:00.
8. IDs are opaque strings. Never parse business meaning from an ID.
9. Enum values are exact lowercase snake_case strings, except currency codes.
10. Field paths use JSON Pointer, such as /profile/party/totalCount.
11. Array order has no meaning unless explicitly documented.
12. Unsupported contract or vocabulary versions are rejected explicitly.
13. A new required field, removed field, changed meaning, or narrowed allowed value requires a contract-version change.
14. A new normalized semantic code requires a shared vocabulary update.
15. The Pydantic model or JSON Schema is the machine source of truth. Do not keep two hand-written implementations.

## 3. Primitive and shared types

### Identifier

A non-empty opaque string unique within its scope.

Examples: req_01, profile_01, group_large.

### Timestamp

A timezone-aware RFC 3339 string.

### Confidence

A finite number from 0.0 through 1.0.

Confidence can support clarification, display, and soft ranking. It cannot independently establish price, availability, identity, serving quantity, or allergy safety.

### FieldPath

A JSON Pointer identifying the relevant contract field.

### SemanticTermV1

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| namespace | SemanticNamespace | Yes | Vocabulary family. |
| code | string | Yes | Stable lowercase code from vocabularyVersion. |
| label | string | Yes | Human-readable display label; not a machine identifier. |

Example:

~~~json
{
  "namespace": "allergen",
  "code": "peanut",
  "label": "Peanut"
}
~~~

### EvidenceV1

Connects a structured value to the original user wording or a disclosed default.

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| evidenceId | Identifier | Yes | Unique within the profile. |
| fieldPath | FieldPath | Yes | Field supported by this evidence. |
| sourceText | string or null | Yes | Exact relevant phrase. Null only for a source-free default. |
| status | EvidenceStatus | Yes | How the value was obtained. |
| confidence | Confidence | Yes | Extraction confidence. |
| startOffset | integer or null | Yes | Zero-based start character offset in stored raw input. |
| endOffset | integer or null | Yes | Exclusive end character offset. |
| note | string or null | Yes | Explanation for an inference or default. |

EvidenceStatus conflicted is allowed in diagnostics but forbidden for any material field in ReadyForPlanningV1.

### ContractIssueV1

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| code | string | Yes | Stable machine-readable issue code. |
| severity | IssueSeverity | Yes | warning, blocking, or fatal. |
| fieldPath | FieldPath or null | Yes | Relevant field, if available. |
| message | string | Yes | Readable explanation. |
| evidenceIds | Identifier[] | Yes | Related evidence; empty when unavailable. |

### AssumptionV1

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| code | string | Yes | Stable assumption code. |
| fieldPath | FieldPath | Yes | Field receiving the default. |
| appliedValue | string | Yes | Canonical string form of the applied value. |
| reason | string | Yes | Why the default was allowed. |
| evidenceIds | Identifier[] | Yes | Normally empty for a pure default. |

## 4. ReadyForPlanningV1

This is the only top-level type accepted by Step 5.

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| status | literal ready_for_planning | Yes | Outcome discriminator. |
| contractVersion | literal 1.0 | Yes | Structure version. |
| vocabularyVersion | literal 1.0 | Yes | Semantic-code version. |
| requestId | Identifier | Yes | Original request correlation ID. |
| profileId | Identifier | Yes | Stable profile identity. |
| profileRevision | integer | Yes | Positive revision beginning at 1. |
| validatedAt | Timestamp | Yes | Admission time. |
| profile | ValidatedMealProfileV1 | Yes | Immutable planner input. |
| validationReceipt | ValidationReceiptV1 | Yes | Checks, warnings, and assumptions. |

## 5. ValidatedMealProfileV1

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| locale | LocaleCode | Yes | Primary language of the request. |
| party | PartyV1 | Yes | Participant count and calculation groups. |
| mealContext | MealContextV1 | Yes | Time and shared appetite context. |
| location | LocationV1 | Yes | Restaurant search/delivery area. |
| budget | BudgetV1 or null | Yes | Maximum budget; null means no ceiling was provided. |
| hardRequirements | HardRequirementV1[] | Yes | Mandatory eligibility rules. |
| preferences | PreferenceV1[] | Yes | Soft ranking signals. |
| restaurantPreferences | RestaurantPreferencesV1 | Yes | Named restaurant preferences and exclusions. |
| orderingPolicy | OrderingPolicyV1 | Yes | Category scope and optimization policy. |
| restrictionDisclosure | RestrictionDisclosureV1 | Yes | Whether restrictions were reported. |
| contextNotes | string[] | Yes | Preserved context for explanation or semantic matching. |
| evidence | EvidenceV1[] | Yes | Evidence registry. |

The complete raw paragraph is deliberately excluded. It stays stored under requestId. Exact relevant phrases cross in EvidenceV1 and PreferenceV1 so the planner does not redo interpretation.

## 6. Party types

### PartyV1

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| totalCount | integer | Yes | Total people; MVP range 1–100. |
| groups | ParticipantGroupV1[] | Yes | Non-empty mutually exclusive groups. Counts sum to totalCount. |

### ParticipantGroupV1

Every person belongs to exactly one group. Split groups whenever appetite, attendance, or applicable hard requirements differ materially.

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| groupId | Identifier | Yes | Unique participant-group ID. |
| displayLabel | string or null | Yes | Optional UI label. |
| count | integer | Yes | Positive people count. |
| attendanceStatus | AttendanceStatus | Yes | Expected attendance state. |
| appetite | AppetiteProfileV1 | Yes | Appetite input. |
| recentMealStatus | RecentMealStatus | Yes | Group-specific recent meal state. |
| activityLevel | ActivityLevel | Yes | Group-specific pre-meal activity. |

If two hard requirements may refer to the same person and the overlap changes eligibility, Step 4 must resolve the overlap or request clarification. Step 5 never guesses.

### AppetiteProfileV1

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| band | AppetiteBand | Yes | Normalized qualitative appetite. |
| statedServings | number or null | Yes | Explicit servings per person, from 0 through 10. |

When statedServings exists, the quantity engine applies the PRD evidence-priority rules rather than multiplying both the band and explicit estimate.

## 7. Meal and order context

### MealContextV1

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| mealType | MealType | Yes | Normalized meal type. |
| occasion | OccasionType | Yes | Event context. |
| desiredDeliveryAt | Timestamp or null | Yes | Delivery/eating deadline. |
| eventStartsAt | Timestamp or null | Yes | Event start, if separately known. |
| durationMinutes | integer or null | Yes | Positive duration. |
| sharedRecentMealStatus | RecentMealStatus | Yes | Default recent-meal status. |
| sharedActivityLevel | ActivityLevel | Yes | Default activity level. |
| isOnlySubstantialMeal | boolean or null | Yes | Whether this is the only substantial meal during a long event. |

Group-specific values override shared values.

### LocationV1

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| query | string | Yes | Non-empty search or delivery-area text. |
| latitude | number or null | Yes | WGS84 latitude from -90 through 90. |
| longitude | number or null | Yes | WGS84 longitude from -180 through 180. |

Coordinates can be null when geocoding belongs to Step 6. The query must still be usable.

### BudgetV1

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| currency | CurrencyCode | Yes | KRW in v1. |
| maximumAmount | integer | Yes | Positive hard ceiling. |
| isHardLimit | literal true | Yes | A high budget is never a spending target. |

No budget is budget: null, not zero.

### RestaurantPreferencesV1

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| preferredNames | string[] | Yes | Soft named-restaurant preferences. |
| excludedNames | string[] | Yes | Hard name exclusions. |

Names are user strings, not verified restaurant identities. Step 6 resolves them.

### OrderingPolicyV1

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| allowedFoodCategories | SemanticTermV1[] | Yes | Non-empty search scope; namespace must be food_category. |
| excludedFoodCategories | SemanticTermV1[] | Yes | Categories the planner cannot use. |
| riskPreference | RiskPreference | Yes | Leftover-versus-shortage objective. |
| allowMultipleRestaurants | boolean | Yes | Whether plans may combine restaurants. |
| maximumRestaurantCount | integer | Yes | Positive maximum; 1 when multiple restaurants are disallowed. |
| deliveryFeeSensitivity | DeliveryFeeSensitivity | Yes | Soft fee preference. |
| maximumDeliveryFee | integer or null | Yes | Explicit hard fee ceiling in budget currency. |

Allowed categories define search scope, not allergy safety.

## 8. Restrictions and preferences

### HardRequirementV1

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| requirementId | Identifier | Yes | Unique requirement ID. |
| kind | HardRequirementKind | Yes | Kind of mandatory rule. |
| affectedGroupIds | Identifier[] | Yes | Non-empty protected groups. |
| terms | SemanticTermV1[] | Yes | Non-empty supported terms. |
| sourceText | string | Yes | Exact relevant wording. |

Hard requirements are enforced by deterministic eligibility logic using explicit or otherwise verified menu data. Model inference never establishes safety.

### PreferenceV1

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| preferenceId | Identifier | Yes | Unique preference ID. |
| targetKind | PreferenceTargetKind | Yes | Preference subject. |
| polarity | PreferencePolarity | Yes | prefer or avoid. |
| strength | PreferenceStrength | Yes | Soft ranking strength. |
| affectedGroupIds | Identifier[] | Yes | Empty means the whole party. |
| terms | SemanticTermV1[] | Yes | Zero or more normalized terms. |
| freeText | string | Yes | Exact phrase for semantic matching. |

Preferences are never hard safety rules. A peanut allergy is a hard requirement; disliking peanuts is a preference.

### RestrictionDisclosureV1

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| status | RestrictionDisclosureStatus | Yes | reported, none_reported, or not_provided. |

none_reported means the user explicitly reported none. not_provided means the topic was absent. Neither verifies that food is allergen-free.

## 9. ValidationReceiptV1

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| validatorVersion | string | Yes | Producer rule/implementation version. |
| blockingIssues | ContractIssueV1[] | Yes | Always empty in ReadyForPlanningV1. |
| warnings | ContractIssueV1[] | Yes | Non-blocking issues the planner must respect or disclose. |
| assumptions | AssumptionV1[] | Yes | Defaults applied before admission. |
| checkedInvariants | string[] | Yes | Stable codes for checks that ran. |

Required v1 checked-invariant codes:

- total_count_in_supported_range
- participant_groups_non_empty
- participant_group_counts_match_total
- participant_groups_mutually_exclusive
- hard_requirement_groups_exist
- hard_requirement_terms_supported
- blocking_conflicts_absent
- budget_is_null_or_positive_finite_ceiling
- location_is_usable
- food_scope_is_supported
- timestamps_are_timezone_aware
- material_fields_have_evidence_or_disclosed_defaults

## 10. Enum glossary

| Enum | Allowed values |
| --- | --- |
| ContractStatus | ready_for_planning, clarification_required, request_rejected |
| LocaleCode | ko, en, mixed, unknown |
| EvidenceStatus | explicit, inferred, defaulted, conflicted |
| IssueSeverity | warning, blocking, fatal |
| AttendanceStatus | confirmed, expected, uncertain, late |
| AppetiteBand | very_light, light, normal, large, very_large, custom |
| RecentMealStatus | not_recent, light_meal_recently, full_meal_recently, unknown |
| ActivityLevel | none, light, moderate, heavy, unknown |
| MealType | breakfast, lunch, dinner, late_night, snack, other |
| OccasionType | ordinary, meeting, workshop, party, sports, school_event, other |
| CurrencyCode | KRW |
| RiskPreference | minimize_leftovers, balanced, minimize_shortage |
| DeliveryFeeSensitivity | ignore, prefer_low |
| HardRequirementKind | allergy, diet, food_exclusion, religious_rule, spice_limit |
| PreferenceTargetKind | food_category, dish, ingredient, flavor, texture, spice, restaurant, variety, other |
| PreferencePolarity | prefer, avoid |
| PreferenceStrength | weak, normal, strong |
| RestrictionDisclosureStatus | reported, none_reported, not_provided |
| SemanticNamespace | allergen, diet, ingredient, food_category, spice, dish, flavor, restaurant_feature, other |

## 11. Vocabulary v1.0

Maintain semantic codes in one shared registry. The following minimum codes support the canonical MVP; this is not a claim about a jurisdiction's complete allergen list.

| Namespace | Minimum v1 codes |
| --- | --- |
| food_category | chicken, pizza |
| allergen | peanut, tree_nut, milk, egg, wheat, soy, fish, shellfish, sesame |
| diet | vegetarian, vegan, pescatarian, no_pork, halal, kosher |
| spice | not_spicy, mild, medium, hot, very_hot |

Ingredient, dish, and flavor codes may be added only through the shared registry. An unknown hard-requirement code causes profile_contract_error; it is never ignored.

## 12. Admission invariants

Before emitting ReadyForPlanningV1, Step 4 guarantees:

1. totalCount is an integer from 1 through 100.
2. Every group count is positive.
3. Groups are mutually exclusive and counts sum exactly to totalCount.
4. Every affectedGroupId exists.
5. A person with multiple material restrictions belongs to a group covered by all of them.
6. Every hard requirement has at least one affected group and supported term.
7. No material field remains conflicted.
8. statedServings is null or finite from 0 through 10.
9. Budget is null or a positive finite ceiling.
10. Location query is usable.
11. Allowed food categories are non-empty and consumer-supported.
12. Allowed and excluded categories do not overlap.
13. Timestamps have timezones.
14. blockingIssues is empty.
15. Defaults appear in assumptions/evidence rather than as explicit user facts.
16. Material invented or unsupported foods have already caused clarification or rejection.
17. Missing restriction information is disclosed and never converted into verified safety.

## 13. Producer and consumer guarantees

### Producer: Steps 1–4

- Emits a schema-valid payload.
- Runs all admission invariants.
- Separates hard requirements from preferences.
- Normalizes numbers and units.
- Leaves no blocking ambiguity.
- Increments profileRevision after a user change.
- Never mutates an admitted revision.

### Consumer: Steps 5–10

- Rejects unsupported versions.
- Treats the profile as immutable.
- Does not reinterpret headcount, budget, or hard requirements.
- Never weakens a hard rule to find a plan.
- Does not treat unknown allergen data as safe.
- Uses model-derived menu semantics only for soft matching unless verified data supports a hard rule.
- Returns no_valid_plan when valid requirements cannot be satisfied by available menus.
- Returns profile_contract_error when a producer invariant is broken.

## 14. ReadyForPlanningV1 template

Store this valid JSON as the first golden integration fixture.

~~~json
{
  "status": "ready_for_planning",
  "contractVersion": "1.0",
  "vocabularyVersion": "1.0",
  "requestId": "req_demo_001",
  "profileId": "profile_demo_001",
  "profileRevision": 1,
  "validatedAt": "2026-08-01T14:30:00+09:00",
  "profile": {
    "locale": "en",
    "party": {
      "totalCount": 15,
      "groups": [
        {
          "groupId": "group_large",
          "displayLabel": "Large eaters",
          "count": 4,
          "attendanceStatus": "confirmed",
          "appetite": {
            "band": "large",
            "statedServings": null
          },
          "recentMealStatus": "not_recent",
          "activityLevel": "heavy"
        },
        {
          "groupId": "group_vegetarian",
          "displayLabel": "Vegetarian participants",
          "count": 2,
          "attendanceStatus": "confirmed",
          "appetite": {
            "band": "normal",
            "statedServings": null
          },
          "recentMealStatus": "not_recent",
          "activityLevel": "heavy"
        },
        {
          "groupId": "group_peanut",
          "displayLabel": "Participant with peanut allergy",
          "count": 1,
          "attendanceStatus": "confirmed",
          "appetite": {
            "band": "normal",
            "statedServings": null
          },
          "recentMealStatus": "not_recent",
          "activityLevel": "heavy"
        },
        {
          "groupId": "group_regular",
          "displayLabel": "Other participants",
          "count": 8,
          "attendanceStatus": "confirmed",
          "appetite": {
            "band": "normal",
            "statedServings": null
          },
          "recentMealStatus": "not_recent",
          "activityLevel": "heavy"
        }
      ]
    },
    "mealContext": {
      "mealType": "dinner",
      "occasion": "sports",
      "desiredDeliveryAt": null,
      "eventStartsAt": null,
      "durationMinutes": null,
      "sharedRecentMealStatus": "not_recent",
      "sharedActivityLevel": "heavy",
      "isOnlySubstantialMeal": null
    },
    "location": {
      "query": "Sinchon, Seoul",
      "latitude": null,
      "longitude": null
    },
    "budget": {
      "currency": "KRW",
      "maximumAmount": 250000,
      "isHardLimit": true
    },
    "hardRequirements": [
      {
        "requirementId": "requirement_vegetarian",
        "kind": "diet",
        "affectedGroupIds": ["group_vegetarian"],
        "terms": [
          {
            "namespace": "diet",
            "code": "vegetarian",
            "label": "Vegetarian"
          }
        ],
        "sourceText": "Two people are vegetarian"
      },
      {
        "requirementId": "requirement_peanut",
        "kind": "allergy",
        "affectedGroupIds": ["group_peanut"],
        "terms": [
          {
            "namespace": "allergen",
            "code": "peanut",
            "label": "Peanut"
          }
        ],
        "sourceText": "One person has a peanut allergy"
      }
    ],
    "preferences": [
      {
        "preferenceId": "preference_spice",
        "targetKind": "spice",
        "polarity": "avoid",
        "strength": "strong",
        "affectedGroupIds": [],
        "terms": [
          {
            "namespace": "spice",
            "code": "very_hot",
            "label": "Very hot"
          }
        ],
        "freeText": "Nothing extremely spicy"
      }
    ],
    "restaurantPreferences": {
      "preferredNames": [],
      "excludedNames": []
    },
    "orderingPolicy": {
      "allowedFoodCategories": [
        {
          "namespace": "food_category",
          "code": "chicken",
          "label": "Chicken"
        },
        {
          "namespace": "food_category",
          "code": "pizza",
          "label": "Pizza"
        }
      ],
      "excludedFoodCategories": [],
      "riskPreference": "minimize_shortage",
      "allowMultipleRestaurants": true,
      "maximumRestaurantCount": 2,
      "deliveryFeeSensitivity": "prefer_low",
      "maximumDeliveryFee": null
    },
    "restrictionDisclosure": {
      "status": "reported"
    },
    "contextNotes": [
      "The group will eat after a sports event."
    ],
    "evidence": [
      {
        "evidenceId": "evidence_total",
        "fieldPath": "/profile/party/totalCount",
        "sourceText": "We have 15 people",
        "status": "explicit",
        "confidence": 1.0,
        "startOffset": null,
        "endOffset": null,
        "note": null
      },
      {
        "evidenceId": "evidence_appetite",
        "fieldPath": "/profile/party/groups",
        "sourceText": "Four eat a lot and everyone else eats normally",
        "status": "explicit",
        "confidence": 0.99,
        "startOffset": null,
        "endOffset": null,
        "note": null
      },
      {
        "evidenceId": "evidence_context",
        "fieldPath": "/profile/mealContext",
        "sourceText": "They just finished a sports event and nobody has eaten recently",
        "status": "explicit",
        "confidence": 0.98,
        "startOffset": null,
        "endOffset": null,
        "note": null
      },
      {
        "evidenceId": "evidence_location",
        "fieldPath": "/profile/location/query",
        "sourceText": "near Sinchon",
        "status": "explicit",
        "confidence": 0.99,
        "startOffset": null,
        "endOffset": null,
        "note": null
      },
      {
        "evidenceId": "evidence_budget",
        "fieldPath": "/profile/budget/maximumAmount",
        "sourceText": "under 250,000 won",
        "status": "explicit",
        "confidence": 1.0,
        "startOffset": null,
        "endOffset": null,
        "note": null
      },
      {
        "evidenceId": "evidence_vegetarian",
        "fieldPath": "/profile/hardRequirements/0",
        "sourceText": "Two people are vegetarian",
        "status": "explicit",
        "confidence": 1.0,
        "startOffset": null,
        "endOffset": null,
        "note": null
      },
      {
        "evidenceId": "evidence_peanut",
        "fieldPath": "/profile/hardRequirements/1",
        "sourceText": "One person has a peanut allergy",
        "status": "explicit",
        "confidence": 1.0,
        "startOffset": null,
        "endOffset": null,
        "note": null
      },
      {
        "evidenceId": "evidence_food_scope",
        "fieldPath": "/profile/orderingPolicy/allowedFoodCategories",
        "sourceText": "We want chicken and pizza",
        "status": "explicit",
        "confidence": 1.0,
        "startOffset": null,
        "endOffset": null,
        "note": null
      },
      {
        "evidenceId": "evidence_risk",
        "fieldPath": "/profile/orderingPolicy/riskPreference",
        "sourceText": "It is more important not to run out of food",
        "status": "explicit",
        "confidence": 0.99,
        "startOffset": null,
        "endOffset": null,
        "note": null
      }
    ]
  },
  "validationReceipt": {
    "validatorVersion": "1.0",
    "blockingIssues": [],
    "warnings": [
      {
        "code": "restaurant_allergen_data_may_be_incomplete",
        "severity": "warning",
        "fieldPath": "/profile/hardRequirements/1",
        "message": "Only sufficiently verified peanut-compatible items may cover the protected group.",
        "evidenceIds": ["evidence_peanut"]
      }
    ],
    "assumptions": [],
    "checkedInvariants": [
      "total_count_in_supported_range",
      "participant_groups_non_empty",
      "participant_group_counts_match_total",
      "participant_groups_mutually_exclusive",
      "hard_requirement_groups_exist",
      "hard_requirement_terms_supported",
      "blocking_conflicts_absent",
      "budget_is_null_or_positive_finite_ceiling",
      "location_is_usable",
      "food_scope_is_supported",
      "timestamps_are_timezone_aware",
      "material_fields_have_evidence_or_disclosed_defaults"
    ]
  }
}
~~~

## 15. Non-ready templates

These belong to the validation layer but never enter the planner.

### ClarificationRequiredV1

| Field | Type | Required |
| --- | --- | --- |
| status | literal clarification_required | Yes |
| contractVersion | literal 1.0 | Yes |
| vocabularyVersion | literal 1.0 | Yes |
| requestId | Identifier | Yes |
| profileId | Identifier | Yes |
| profileRevision | integer | Yes |
| issues | ContractIssueV1[] | Yes, non-empty |
| questions | string[] | Yes, non-empty |

~~~json
{
  "status": "clarification_required",
  "contractVersion": "1.0",
  "vocabularyVersion": "1.0",
  "requestId": "req_demo_002",
  "profileId": "profile_demo_002",
  "profileRevision": 1,
  "issues": [
    {
      "code": "allergy_overlap_unclear",
      "severity": "blocking",
      "fieldPath": null,
      "message": "It is unclear whether the vegetarian participant and peanut-allergic participant are the same person.",
      "evidenceIds": []
    }
  ],
  "questions": [
    "Is the participant with the peanut allergy also one of the vegetarian participants?"
  ]
}
~~~

### RequestRejectedV1

| Field | Type | Required |
| --- | --- | --- |
| status | literal request_rejected | Yes |
| contractVersion | literal 1.0 | Yes |
| vocabularyVersion | literal 1.0 | Yes |
| requestId | Identifier | Yes |
| reasonCode | string | Yes |
| issues | ContractIssueV1[] | Yes, non-empty |

~~~json
{
  "status": "request_rejected",
  "contractVersion": "1.0",
  "vocabularyVersion": "1.0",
  "requestId": "req_demo_003",
  "reasonCode": "unsupported_physical_quantity",
  "issues": [
    {
      "code": "servings_per_person_out_of_range",
      "severity": "fatal",
      "fieldPath": "/candidateProfile/party/groups/0/appetite/statedServings",
      "message": "The stated quantity is outside the automatic-planning range.",
      "evidenceIds": ["evidence_absurd_quantity"]
    }
  ]
}
~~~

## 16. Consumer outcome distinction

| Outcome | Meaning |
| --- | --- |
| no_valid_plan | Profile is valid, but available restaurant/menu data cannot satisfy it. |
| data_unavailable | Required restaurant data could not be obtained or reused safely. |
| profile_contract_error | Producer payload violates the schema or declared invariants. |
| unsupported_contract_version | Consumer does not support contractVersion. |
| unsupported_vocabulary_version | Consumer does not support vocabularyVersion. |

## 17. Integration checklist

1. Both teammates approve this document and vocabulary.
2. Create one shared Pydantic model or JSON Schema.
3. Generate/import types; never copy them into two modules.
4. Store the ready template as a golden fixture.
5. Producer test: Steps 1–4 emit the fixture shape.
6. Consumer test: Step 5 accepts it unchanged.
7. Reject unknown fields.
8. Prove non-ready outcomes cannot call the planner.
9. Reject group counts that do not sum to totalCount.
10. Reject unknown hard-requirement codes.
11. Add contractVersion and vocabularyVersion to traces and errors.
12. Require a coordinated pull request for contract changes.

Recommended entry point:

~~~python
async def plan_order(
    intake: ReadyForPlanningV1,
    dependencies: PlannerDependencies,
) -> PlanningOutcomeV1:
    ...
~~~
