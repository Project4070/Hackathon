"""Deterministic Step-4 admission validator.

No model call occurs here.  This module owns supported ranges, known vocabulary,
contradictions, trusted defaults, and the readiness discriminator.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Iterable

from pydantic import AwareDatetime, Field

from .contracts import (
    AssumptionV2,
    AppetiteBand,
    BudgetIntentType,
    BudgetMaximumSource,
    ClarificationRequiredV2,
    ContractIssueV2,
    ContractModel,
    CostScopeV2,
    EvidenceStatus,
    FoodScopeV2,
    IssueSeverity,
    LocationRequirementV2,
    LocationSource,
    MealRequestCandidateV2,
    PlanningBoundaryOutcomeV2,
    PlanningIntakeV2,
    QuantityPreferenceV2,
    ResolvedBudgetType,
    ResolvedBudgetV2,
    RestaurantMixing,
    RestrictionDisclosureStatus,
    RiskPreference,
    SemanticNamespace,
    ToleranceLevel,
    UnresolvedIssueKind,
    ValidatedMealProfileV2,
    ValidationReceiptV2,
    RequestRejectedV2,
    utc_now,
)


VALIDATOR_VERSION = "planning_intake_validator_v2.0.0"

VOCABULARY_V1: dict[SemanticNamespace, frozenset[str]] = {
    SemanticNamespace.FOOD_CATEGORY: frozenset({"chicken", "pizza"}),
    SemanticNamespace.ALLERGEN: frozenset(
        {"peanut", "tree_nut", "milk", "egg", "wheat", "soy", "fish", "shellfish", "sesame"}
    ),
    SemanticNamespace.DIET: frozenset(
        {"vegetarian", "vegan", "pescatarian", "no_pork", "halal", "kosher"}
    ),
    SemanticNamespace.SPICE: frozenset({"not_spicy", "mild", "medium", "hot", "very_hot"}),
}

REQUIRED_INVARIANT_CODES = [
    "total_count_in_supported_range",
    "participant_groups_non_empty",
    "participant_group_counts_match_total",
    "participant_groups_mutually_exclusive",
    "hard_requirement_groups_exist",
    "hard_requirement_terms_preserved_for_planner_validation",
    "hard_and_soft_constraints_separated",
    "blocking_conflicts_absent",
    "explicit_servings_in_supported_range",
    "budget_resolved",
    "food_scope_term_namespaces_valid",
    "location_requirement_usable",
    "timestamps_timezone_aware",
    "material_fields_have_evidence_or_disclosed_defaults",
    "runtime_policy_not_model_owned",
    "cost_scope_resolved",
    "quantity_preference_resolved",
    "restaurant_mixing_resolved",
]


class AdmissionPolicyV2(ContractModel):
    minimum_group_size: int = Field(default=1, ge=1)
    maximum_group_size: int = Field(default=100, ge=1, le=10_000)
    maximum_budget_minor: int = Field(default=100_000_000, ge=1)
    # TEMPORARY HACKATHON DEFAULT: when the user omits a budget, apply this
    # per-person KRW ceiling. Remove or replace after product-owner review.
    temporary_default_budget_per_person_minor: int | None = Field(default=12_000, ge=0)
    approximate_tolerance_basis_points: int = Field(default=1_000, ge=0, le=10_000)
    delivery_required: bool = True
    default_include_menu_price: bool = True
    default_include_delivery_fee: bool = True
    default_include_service_fee: bool = True
    default_include_discount: bool = True
    default_risk_preference: RiskPreference = RiskPreference.BALANCED
    default_shortage_tolerance: ToleranceLevel = ToleranceLevel.NORMAL
    default_leftover_tolerance: ToleranceLevel = ToleranceLevel.NORMAL
    default_restaurant_mixing: RestaurantMixing = RestaurantMixing.SINGLE_RESTAURANT_PREFERRED


class ValidationContextV2(ContractModel):
    request_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    case_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    profile_revision: int = Field(default=1, strict=True, ge=1)
    validated_at: AwareDatetime = Field(default_factory=utc_now)
    default_location: LocationRequirementV2 | None = None


def _contract_issue(
    code: str,
    severity: IssueSeverity,
    field_path: str | None,
    message: str,
    evidence_ids: Iterable[str] = (),
) -> ContractIssueV2:
    return ContractIssueV2(
        code=code,
        severity=severity,
        field_path=field_path,
        message=message[:500],
        evidence_ids=list(dict.fromkeys(evidence_ids)),
    )


def _assumption(
    code: str,
    field_path: str,
    applied_value: object,
    reason: str,
) -> AssumptionV2:
    return AssumptionV2(
        code=code,
        field_path=field_path,
        applied_value=str(applied_value).lower() if isinstance(applied_value, bool) else str(applied_value),
        reason=reason,
        evidence_ids=[],
    )


def _duplicate_values(values: Iterable[str]) -> set[str]:
    counts = Counter(values)
    return {value for value, count in counts.items() if count > 1}


def _deduplicate_issues(issues: Iterable[ContractIssueV2]) -> list[ContractIssueV2]:
    """Preserve order while deduplicating models that contain list fields."""

    seen: set[str] = set()
    result: list[ContractIssueV2] = []
    for issue in issues:
        key = issue.model_dump_json()
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return result


def _resolve_location(
    candidate: MealRequestCandidateV2,
    context: ValidationContextV2,
    policy: AdmissionPolicyV2,
    blockers: list[ContractIssueV2],
    assumptions: list[AssumptionV2],
) -> LocationRequirementV2 | None:
    hint = candidate.location_hint
    if hint is not None and (hint.query is not None or hint.latitude is not None):
        return LocationRequirementV2(
            delivery_required=policy.delivery_required,
            source=hint.source,
            query=hint.query,
            latitude=hint.latitude,
            longitude=hint.longitude,
        )
    if context.default_location is not None:
        assumptions.append(
            _assumption(
                "location_from_request_context",
                "/profile/location_requirement",
                context.default_location.query or "coordinates",
                "No usable location was extracted from the text; trusted request context supplied it.",
            )
        )
        return context.default_location
    if policy.delivery_required:
        blockers.append(
            _contract_issue(
                "location_required",
                IssueSeverity.BLOCKING,
                "/candidate/location_hint",
                "Delivery comparison requires a location, but none was provided. Provide an area or address.",
            )
        )
        return None
    assumptions.append(
        _assumption(
            "delivery_not_required",
            "/profile/location_requirement/delivery_required",
            False,
            "Trusted policy does not require delivery validation.",
        )
    )
    return LocationRequirementV2(
        delivery_required=False,
        source=LocationSource.APPLICATION_DEFAULT,
        query=None,
        latitude=None,
        longitude=None,
    )


def _resolve_budget(
    candidate: MealRequestCandidateV2,
    total_count: int,
    policy: AdmissionPolicyV2,
    fatal: list[ContractIssueV2],
    blockers: list[ContractIssueV2],
    assumptions: list[AssumptionV2],
) -> ResolvedBudgetV2 | None:
    intent = candidate.budget_intent
    values = [value for value in (intent.target_amount_minor, intent.explicit_maximum_amount_minor) if value is not None]
    for value in values:
        if value < 0:
            fatal.append(
                _contract_issue(
                    "budget_negative",
                    IssueSeverity.FATAL,
                    "/candidate/budget_intent",
                    f"Received budget value {value}; negative budgets are invalid. Provide a non-negative KRW amount.",
                )
            )
        elif value > policy.maximum_budget_minor:
            fatal.append(
                _contract_issue(
                    "budget_out_of_range",
                    IssueSeverity.FATAL,
                    "/candidate/budget_intent",
                    f"Received budget value {value}; the configured ceiling is {policy.maximum_budget_minor} KRW. Confirm a smaller amount.",
                )
            )

    scope_values: dict[str, bool] = {}
    for field_name, default_value in (
        ("include_menu_price", policy.default_include_menu_price),
        ("include_delivery_fee", policy.default_include_delivery_fee),
        ("include_service_fee", policy.default_include_service_fee),
        ("include_discount", policy.default_include_discount),
    ):
        candidate_value = getattr(intent.cost_scope, field_name)
        resolved_value = default_value if candidate_value is None else candidate_value
        scope_values[field_name] = resolved_value
        if candidate_value is None:
            assumptions.append(
                _assumption(
                    f"cost_scope_{field_name}_defaulted",
                    f"/profile/budget/cost_scope/{field_name}",
                    resolved_value,
                    "The user did not state this cost-scope choice; trusted budget policy supplied it.",
                )
            )
    cost_scope = CostScopeV2(**scope_values)

    if fatal:
        return None

    if intent.budget_type is BudgetIntentType.NO_BUDGET:
        if intent.currency is not None or values:
            blockers.append(
                _contract_issue(
                    "budget_intent_conflict",
                    IssueSeverity.BLOCKING,
                    "/candidate/budget_intent",
                    "budget_type=no_budget conflicts with a supplied currency or amount. Confirm whether a budget applies.",
                )
            )
            return None
        if policy.temporary_default_budget_per_person_minor is None:
            return ResolvedBudgetV2(
                budget_type=ResolvedBudgetType.NO_BUDGET,
                currency=None,
                target_amount_minor=None,
                maximum_amount_minor=None,
                maximum_source=BudgetMaximumSource.NONE,
                cost_scope=cost_scope,
            )
        temporary_maximum = total_count * policy.temporary_default_budget_per_person_minor
        if temporary_maximum > policy.maximum_budget_minor:
            fatal.append(
                _contract_issue(
                    "temporary_default_budget_out_of_range",
                    IssueSeverity.FATAL,
                    "/candidate/budget_intent",
                    f"The temporary default budget produces {temporary_maximum} KRW, above the configured ceiling {policy.maximum_budget_minor} KRW.",
                )
            )
            return None
        assumptions.append(
            _assumption(
                "temporary_default_budget_per_person_applied",
                "/profile/budget/maximum_amount_minor",
                f"{policy.temporary_default_budget_per_person_minor} KRW/person x {total_count} people = {temporary_maximum} KRW",
                "TEMPORARY HACKATHON DEFAULT: the user omitted a budget, so a per-person ceiling was applied. This policy is subject to product-owner review.",
            )
        )
        return ResolvedBudgetV2(
            budget_type=ResolvedBudgetType.HARD_MAXIMUM,
            currency="KRW",
            target_amount_minor=None,
            maximum_amount_minor=temporary_maximum,
            maximum_source=BudgetMaximumSource.POLICY_DEFAULT,
            cost_scope=cost_scope,
        )

    if intent.currency != "KRW":
        blockers.append(
            _contract_issue(
                "budget_currency_required",
                IssueSeverity.BLOCKING,
                "/candidate/budget_intent/currency",
                "The MVP requires a KRW currency value when a budget amount is present.",
            )
        )
        return None

    if intent.budget_type is BudgetIntentType.HARD_MAXIMUM:
        maximum = intent.explicit_maximum_amount_minor
        if maximum is None:
            blockers.append(
                _contract_issue(
                    "budget_maximum_missing",
                    IssueSeverity.BLOCKING,
                    "/candidate/budget_intent/explicit_maximum_amount_minor",
                    "A hard budget maximum was stated without a usable amount. Provide the maximum KRW amount.",
                )
            )
            return None
        return ResolvedBudgetV2(
            budget_type=ResolvedBudgetType.HARD_MAXIMUM,
            currency="KRW",
            target_amount_minor=None,
            maximum_amount_minor=maximum,
            maximum_source=BudgetMaximumSource.EXPLICIT,
            cost_scope=cost_scope,
        )

    target = intent.target_amount_minor
    if target is None:
        blockers.append(
            _contract_issue(
                "budget_target_missing",
                IssueSeverity.BLOCKING,
                "/candidate/budget_intent/target_amount_minor",
                "An approximate budget was stated without a usable target amount. Provide the target KRW amount.",
            )
        )
        return None
    maximum = intent.explicit_maximum_amount_minor
    maximum_source = BudgetMaximumSource.EXPLICIT
    if maximum is None:
        numerator = target * (10_000 + policy.approximate_tolerance_basis_points)
        maximum = (numerator + 9_999) // 10_000
        maximum_source = BudgetMaximumSource.POLICY_TOLERANCE
        assumptions.append(
            _assumption(
                "approximate_budget_maximum_derived",
                "/profile/budget/maximum_amount_minor",
                maximum,
                "Trusted policy converted the approximate target into a hard ceiling.",
            )
        )
    elif maximum < target:
        blockers.append(
            _contract_issue(
                "budget_target_above_maximum",
                IssueSeverity.BLOCKING,
                "/candidate/budget_intent",
                f"The target budget {target} KRW exceeds the explicit maximum {maximum} KRW. Confirm the intended values.",
            )
        )
        return None
    return ResolvedBudgetV2(
        budget_type=ResolvedBudgetType.APPROXIMATE_TARGET,
        currency="KRW",
        target_amount_minor=target,
        maximum_amount_minor=maximum,
        maximum_source=maximum_source,
        cost_scope=cost_scope,
    )


def _resolve_quantity_preference(
    candidate: MealRequestCandidateV2,
    policy: AdmissionPolicyV2,
    assumptions: list[AssumptionV2],
) -> QuantityPreferenceV2:
    candidate_pref = candidate.quantity_preference
    values = {
        "primary_objective": candidate_pref.primary_objective or policy.default_risk_preference,
        "shortage_tolerance": candidate_pref.shortage_tolerance or policy.default_shortage_tolerance,
        "leftover_tolerance": candidate_pref.leftover_tolerance or policy.default_leftover_tolerance,
    }
    for name, candidate_value in (
        ("primary_objective", candidate_pref.primary_objective),
        ("shortage_tolerance", candidate_pref.shortage_tolerance),
        ("leftover_tolerance", candidate_pref.leftover_tolerance),
    ):
        if candidate_value is None:
            assumptions.append(
                _assumption(
                    f"quantity_preference_{name}_defaulted",
                    f"/profile/quantity_preference/{name}",
                    values[name].value,
                    "The user did not state this preference; trusted quantity policy supplied it.",
                )
            )
    return QuantityPreferenceV2(**values)


def _build_clarification_question(issues: list[ContractIssueV2]) -> str:
    actions: list[str] = []
    for issue in issues:
        if issue.code == "participant_group_counts_mismatch":
            actions.append("confirm the total participant count and mutually exclusive subgroup counts")
        elif issue.code == "location_required":
            actions.append("provide the delivery area or address")
        elif issue.code == "food_category_missing":
            actions.append("state the food category to plan")
        elif "budget" in issue.code:
            actions.append("confirm the KRW budget and whether it is a target or hard maximum")
        elif "evidence" in issue.code:
            actions.append("confirm the unsupported or conflicting extracted fact")
        elif "requirement" in issue.code or "group" in issue.code:
            actions.append("clarify which mutually exclusive participant group each restriction applies to")
        else:
            actions.append(issue.message)
    unique_actions = list(dict.fromkeys(actions))
    joined = "; ".join(unique_actions)
    question = f"Before planning, please {joined}."
    return question[:500]


def validate_planning_profile(
    candidate: MealRequestCandidateV2,
    context: ValidationContextV2,
    *,
    policy: AdmissionPolicyV2 | None = None,
    raw_text: str | None = None,
    upstream_warnings: Iterable[ContractIssueV2] = (),
) -> PlanningBoundaryOutcomeV2:
    """Return exactly one ready, clarification, or rejection boundary outcome."""

    policy = policy or AdmissionPolicyV2()
    fatal: list[ContractIssueV2] = []
    blockers: list[ContractIssueV2] = []
    warnings = list(upstream_warnings)
    assumptions: list[AssumptionV2] = []

    party = candidate.party
    if not policy.minimum_group_size <= party.total_count <= policy.maximum_group_size:
        fatal.append(
            _contract_issue(
                "group_size_out_of_range",
                IssueSeverity.FATAL,
                "/candidate/party/total_count",
                f"Received total_count={party.total_count}; supported whole-number range is {policy.minimum_group_size} through {policy.maximum_group_size}. Correct the count.",
            )
        )
    if not party.groups:
        blockers.append(
            _contract_issue(
                "participant_groups_empty",
                IssueSeverity.BLOCKING,
                "/candidate/party/groups",
                "No mutually exclusive participant groups were extracted. Provide an appetite distribution or confirm a group default.",
            )
        )
    if any(group.count <= 0 for group in party.groups):
        fatal.append(
            _contract_issue(
                "participant_group_count_invalid",
                IssueSeverity.FATAL,
                "/candidate/party/groups",
                "Every participant group count must be a positive whole number. Correct the invalid subgroup count.",
            )
        )
    group_sum = sum(group.count for group in party.groups)
    if party.groups and group_sum != party.total_count:
        blockers.append(
            _contract_issue(
                "participant_group_counts_mismatch",
                IssueSeverity.BLOCKING,
                "/candidate/party/groups",
                f"Received total_count={party.total_count}, but subgroup counts sum to {group_sum}. Confirm which value is correct.",
            )
        )
    duplicate_group_ids = _duplicate_values(group.group_id for group in party.groups)
    if duplicate_group_ids:
        blockers.append(
            _contract_issue(
                "participant_group_ids_duplicate",
                IssueSeverity.BLOCKING,
                "/candidate/party/groups",
                f"Participant group IDs are duplicated: {', '.join(sorted(duplicate_group_ids))}. Re-extract distinct groups.",
            )
        )
    for index, group in enumerate(party.groups):
        if group.appetite.band is AppetiteBand.CUSTOM and group.appetite.stated_servings_milli is None:
            blockers.append(
                _contract_issue(
                    "custom_appetite_value_missing",
                    IssueSeverity.BLOCKING,
                    f"/candidate/party/groups/{index}/appetite/stated_servings_milli",
                    "A custom appetite band requires an explicit value from 0 through 10,000 milli-servings.",
                )
            )

    requested_codes: set[str] = set()
    excluded_codes: set[str] = set()
    if not candidate.food_scope.requested_categories:
        blockers.append(
            _contract_issue(
                "food_category_missing",
                IssueSeverity.BLOCKING,
                "/candidate/food_scope/requested_categories",
                "No food category was provided. State the food category to plan.",
            )
        )
    for field_name, terms, destination in (
        ("requested_categories", candidate.food_scope.requested_categories, requested_codes),
        ("excluded_categories", candidate.food_scope.excluded_categories, excluded_codes),
    ):
        for term in terms:
            if term.namespace is not SemanticNamespace.FOOD_CATEGORY:
                fatal.append(
                    _contract_issue(
                        "food_category_namespace_invalid",
                        IssueSeverity.FATAL,
                        f"/candidate/food_scope/{field_name}",
                        f"Food category term '{term.label}' ({term.code}) must use the food_category namespace.",
                    )
                )
            destination.add(term.code)
    overlap = requested_codes & excluded_codes
    if overlap:
        blockers.append(
            _contract_issue(
                "food_category_conflict",
                IssueSeverity.BLOCKING,
                "/candidate/food_scope",
                f"The same categories are both requested and excluded: {', '.join(sorted(overlap))}. Confirm the intended scope.",
            )
        )

    group_ids = {group.group_id for group in party.groups}
    if candidate.location_hint is not None and candidate.location_hint.source is not LocationSource.USER_TEXT:
        blockers.append(
            _contract_issue(
                "location_source_not_model_owned",
                IssueSeverity.BLOCKING,
                "/candidate/location_hint/source",
                "The Interpreter Agent may extract only user_text locations. Trusted application location must be supplied through validation context.",
            )
        )
    requirement_ids = [item.requirement_id for item in candidate.hard_requirements]
    preference_ids = [item.preference_id for item in candidate.preferences]
    if _duplicate_values(requirement_ids):
        blockers.append(
            _contract_issue(
                "hard_requirement_ids_duplicate",
                IssueSeverity.BLOCKING,
                "/candidate/hard_requirements",
                "Hard-requirement IDs must be unique. Re-extract the duplicated restrictions.",
            )
        )
    if _duplicate_values(preference_ids):
        blockers.append(
            _contract_issue(
                "preference_ids_duplicate",
                IssueSeverity.BLOCKING,
                "/candidate/preferences",
                "Preference IDs must be unique. Re-extract the duplicated preferences.",
            )
        )
    for requirement in candidate.hard_requirements:
        unknown_groups = set(requirement.affected_group_ids) - group_ids
        if unknown_groups:
            blockers.append(
                _contract_issue(
                    "hard_requirement_group_unknown",
                    IssueSeverity.BLOCKING,
                    "/candidate/hard_requirements",
                    f"Restriction {requirement.requirement_id} references unknown group IDs: {', '.join(sorted(unknown_groups))}. Clarify the affected participants.",
                )
            )
        for term in requirement.terms:
            supported_codes = VOCABULARY_V1.get(term.namespace)
            if supported_codes is None or term.code not in supported_codes:
                warnings.append(
                    _contract_issue(
                        "hard_requirement_term_unresolved",
                        IssueSeverity.WARNING,
                        "/candidate/hard_requirements",
                        f"Hard restriction term '{term.label}' ({term.code}) is not in the intake vocabulary; planner eligibility will handle it conservatively.",
                    )
                )
    for preference in candidate.preferences:
        unknown_groups = set(preference.affected_group_ids) - group_ids
        if unknown_groups:
            blockers.append(
                _contract_issue(
                    "preference_group_unknown",
                    IssueSeverity.BLOCKING,
                    "/candidate/preferences",
                    f"Preference {preference.preference_id} references unknown group IDs: {', '.join(sorted(unknown_groups))}.",
                )
            )
        for term in preference.terms:
            supported_codes = VOCABULARY_V1.get(term.namespace)
            if supported_codes is None or term.code not in supported_codes:
                warnings.append(
                    _contract_issue(
                        "preference_term_unresolved",
                        IssueSeverity.WARNING,
                        "/candidate/preferences",
                        f"Preference term '{term.label}' ({term.code}) is not in the intake vocabulary; planner matching may ignore it.",
                    )
                )

    evidence_ids = [item.evidence_id for item in candidate.evidence]
    if _duplicate_values(evidence_ids):
        blockers.append(
            _contract_issue(
                "evidence_ids_duplicate",
                IssueSeverity.BLOCKING,
                "/candidate/evidence",
                "Evidence IDs must be unique; re-extract the duplicated evidence records.",
            )
        )
    if raw_text is not None:
        for evidence in candidate.evidence:
            if evidence.source_text is not None and evidence.source_text not in raw_text:
                blockers.append(
                    _contract_issue(
                        "evidence_source_not_found",
                        IssueSeverity.BLOCKING,
                        f"/candidate/evidence/{evidence.evidence_id}",
                        f"Evidence source text for {evidence.evidence_id} is not present verbatim in the request. Confirm the extracted fact.",
                        [evidence.evidence_id],
                    )
                )
            if evidence.start_offset is not None:
                literal = raw_text[evidence.start_offset : evidence.end_offset]
                if literal != evidence.source_text:
                    blockers.append(
                        _contract_issue(
                            "evidence_offset_mismatch",
                            IssueSeverity.BLOCKING,
                            f"/candidate/evidence/{evidence.evidence_id}",
                            f"Evidence offsets for {evidence.evidence_id} do not select its exact source text. Confirm the extraction.",
                            [evidence.evidence_id],
                        )
                    )
    material_paths = {"/party/total_count", "/party/groups", "/food_scope/requested_categories"}
    if candidate.budget_intent.budget_type is not BudgetIntentType.NO_BUDGET:
        material_paths.add("/budget_intent")
    if candidate.hard_requirements:
        material_paths.add("/hard_requirements")
    for material_path in sorted(material_paths):
        matches = [
            evidence
            for evidence in candidate.evidence
            if evidence.field_path == material_path or evidence.field_path.startswith(material_path + "/")
        ]
        if not matches:
            blockers.append(
                _contract_issue(
                    "material_evidence_missing",
                    IssueSeverity.BLOCKING,
                    f"/candidate{material_path}",
                    f"Material field {material_path} has no evidence record. Confirm the extracted fact.",
                )
            )
        elif any(evidence.status is EvidenceStatus.CONFLICTED for evidence in matches):
            blockers.append(
                _contract_issue(
                    "material_evidence_conflicted",
                    IssueSeverity.BLOCKING,
                    f"/candidate{material_path}",
                    f"Material field {material_path} remains conflicted. Confirm the correct value.",
                    [item.evidence_id for item in matches],
                )
            )

    for unresolved in candidate.unresolved_issues:
        if unresolved.field_path == "/location_hint" and context.default_location is not None:
            continue
        severity = IssueSeverity.FATAL if unresolved.kind is UnresolvedIssueKind.UNSUPPORTED else IssueSeverity.BLOCKING
        issue = _contract_issue(
            f"unresolved_{unresolved.kind.value}",
            severity,
            f"/candidate{unresolved.field_path}" if unresolved.field_path else "/candidate",
            unresolved.message,
        )
        (fatal if severity is IssueSeverity.FATAL else blockers).append(issue)

    location = _resolve_location(candidate, context, policy, blockers, assumptions)
    budget = _resolve_budget(candidate, party.total_count, policy, fatal, blockers, assumptions)
    quantity_preference = _resolve_quantity_preference(candidate, policy, assumptions)

    if candidate.restriction_disclosure.status is RestrictionDisclosureStatus.NOT_PROVIDED:
        warnings.append(
            _contract_issue(
                "restrictions_not_provided",
                IssueSeverity.WARNING,
                "/candidate/restriction_disclosure/status",
                "The user did not provide restriction information. This does not establish that any menu item is allergy-safe.",
            )
        )

    if fatal:
        return RequestRejectedV2(
            request_id=context.request_id,
            case_id=context.case_id,
            reason_code=fatal[0].code,
            issues=_deduplicate_issues(fatal),
        )
    if blockers:
        return ClarificationRequiredV2(
            request_id=context.request_id,
            case_id=context.case_id,
            profile_revision=context.profile_revision,
            issues=_deduplicate_issues(blockers),
            questions=[_build_clarification_question(blockers)],
        )

    assert location is not None and budget is not None
    food_scope: FoodScopeV2 = candidate.food_scope
    if food_scope.restaurant_mixing is RestaurantMixing.UNSPECIFIED:
        food_scope = food_scope.model_copy(update={"restaurant_mixing": policy.default_restaurant_mixing})
        assumptions.append(
            _assumption(
                "restaurant_mixing_defaulted",
                "/profile/food_scope/restaurant_mixing",
                policy.default_restaurant_mixing.value,
                "The user did not state restaurant mixing; trusted search policy supplied the default.",
            )
        )

    profile = ValidatedMealProfileV2(
        locale=candidate.locale,
        occasion=candidate.occasion,
        party=candidate.party,
        location_requirement=location,
        food_scope=food_scope,
        hard_requirements=candidate.hard_requirements,
        preferences=candidate.preferences,
        budget=budget,
        quantity_preference=quantity_preference,
        restaurant_preferences=candidate.restaurant_preferences,
        restriction_disclosure=candidate.restriction_disclosure,
        context_notes=candidate.context_notes,
        evidence=candidate.evidence,
    )
    return PlanningIntakeV2(
        request_id=context.request_id,
        case_id=context.case_id,
        profile_revision=context.profile_revision,
        validated_at=context.validated_at,
        profile=profile,
        validation_receipt=ValidationReceiptV2(
            validator_version=VALIDATOR_VERSION,
            blocking_issues=[],
            warnings=warnings,
            assumptions=assumptions,
            checked_invariants=REQUIRED_INVARIANT_CODES,
        ),
    )
