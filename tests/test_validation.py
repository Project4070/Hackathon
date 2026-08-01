from group_food_agent.contracts import (
    BudgetIntentType,
    BudgetMaximumSource,
    LocationRequirementV2,
    LocationSource,
    MealRequestCandidateV2,
    PlanningIntakeV2,
    SemanticNamespace,
    SemanticTermV2,
    ClarificationRequiredV2,
)
from group_food_agent.validation import ValidationContextV2, validate_planning_profile


def _validate(candidate: MealRequestCandidateV2, raw_text: str):
    return validate_planning_profile(
        candidate,
        ValidationContextV2(request_id="req_validation", case_id="case_validation"),
        raw_text=raw_text,
    )


def test_canonical_candidate_becomes_ready_intake(
    canonical_candidate: MealRequestCandidateV2,
    canonical_raw_text: str,
) -> None:
    outcome = _validate(canonical_candidate, canonical_raw_text)
    assert isinstance(outcome, PlanningIntakeV2)
    assert outcome.profile.party.total_count == 15
    assert outcome.profile.budget.maximum_amount_minor == 275_000
    assert outcome.profile.budget.maximum_source is BudgetMaximumSource.POLICY_TOLERANCE
    assert outcome.profile.food_scope.restaurant_mixing.value == "single_restaurant_preferred"
    assert not outcome.validation_receipt.blocking_issues


def test_mismatched_subgroup_total_requires_clarification(
    canonical_candidate: MealRequestCandidateV2,
    canonical_raw_text: str,
) -> None:
    changed_group = canonical_candidate.party.groups[0].model_copy(update={"count": 7})
    party = canonical_candidate.party.model_copy(
        update={"groups": [changed_group, *canonical_candidate.party.groups[1:]]}
    )
    outcome = _validate(canonical_candidate.model_copy(update={"party": party}), canonical_raw_text)
    assert isinstance(outcome, ClarificationRequiredV2)
    assert any(issue.code == "participant_group_counts_mismatch" for issue in outcome.issues)


def test_unlisted_food_category_is_admitted_without_inventing_a_match(
    canonical_candidate: MealRequestCandidateV2,
    canonical_raw_text: str,
) -> None:
    unknown = SemanticTermV2(
        namespace=SemanticNamespace.FOOD_CATEGORY,
        code="sdgfidfuweor",
        label="sdgfidfuweor",
    )
    food_scope = canonical_candidate.food_scope.model_copy(update={"requested_categories": [unknown]})
    outcome = _validate(canonical_candidate.model_copy(update={"food_scope": food_scope}), canonical_raw_text)
    assert isinstance(outcome, PlanningIntakeV2)
    assert outcome.profile.food_scope.requested_categories[0].code == "sdgfidfuweor"
    assert not outcome.validation_receipt.blocking_issues


def test_unknown_hard_restriction_code_is_admitted_for_conservative_planner_handling(
    canonical_candidate: MealRequestCandidateV2,
    canonical_raw_text: str,
) -> None:
    requirement = canonical_candidate.hard_requirements[1]
    unknown = SemanticTermV2(
        namespace=SemanticNamespace.ALLERGEN,
        code="dragon_dander",
        label="dragon dander",
    )
    changed = requirement.model_copy(update={"terms": [unknown]})
    candidate = canonical_candidate.model_copy(
        update={"hard_requirements": [canonical_candidate.hard_requirements[0], changed]}
    )
    outcome = _validate(candidate, canonical_raw_text)
    assert isinstance(outcome, PlanningIntakeV2)
    assert any(
        warning.code == "hard_requirement_term_unresolved"
        for warning in outcome.validation_receipt.warnings
    )


def test_missing_location_requires_one_bundled_followup(
    canonical_candidate: MealRequestCandidateV2,
    canonical_raw_text: str,
) -> None:
    outcome = _validate(canonical_candidate.model_copy(update={"location_hint": None}), canonical_raw_text)
    assert isinstance(outcome, ClarificationRequiredV2)
    assert len(outcome.questions) == 1
    assert any(issue.code == "location_required" for issue in outcome.issues)


def test_trusted_request_context_can_supply_missing_location(
    canonical_candidate: MealRequestCandidateV2,
    canonical_raw_text: str,
) -> None:
    candidate = canonical_candidate.model_copy(update={"location_hint": None})
    outcome = validate_planning_profile(
        candidate,
        ValidationContextV2(
            request_id="req_context_location",
            case_id="case_context_location",
            default_location=LocationRequirementV2(
                delivery_required=True,
                source=LocationSource.REQUEST_CONTEXT,
                query="서울 서대문구",
                latitude=None,
                longitude=None,
            ),
        ),
        raw_text=canonical_raw_text,
    )
    assert isinstance(outcome, PlanningIntakeV2)
    assert outcome.profile.location_requirement.source is LocationSource.REQUEST_CONTEXT
    assert any(
        assumption.code == "location_from_request_context"
        for assumption in outcome.validation_receipt.assumptions
    )


def test_fabricated_evidence_requires_clarification(
    canonical_candidate: MealRequestCandidateV2,
    canonical_raw_text: str,
) -> None:
    evidence = canonical_candidate.evidence[0].model_copy(update={"source_text": "not in the request"})
    candidate = canonical_candidate.model_copy(
        update={"evidence": [evidence, *canonical_candidate.evidence[1:]]}
    )
    outcome = _validate(candidate, canonical_raw_text)
    assert isinstance(outcome, ClarificationRequiredV2)
    assert any(issue.code == "evidence_source_not_found" for issue in outcome.issues)


def test_zero_budget_is_admitted_as_a_ceiling_not_a_quantity_target(
    canonical_candidate: MealRequestCandidateV2,
    canonical_raw_text: str,
) -> None:
    budget = canonical_candidate.budget_intent.model_copy(
        update={
            "budget_type": BudgetIntentType.HARD_MAXIMUM,
            "target_amount_minor": None,
            "explicit_maximum_amount_minor": 0,
            "source_text": "예산은 0원",
        }
    )
    evidence = canonical_candidate.evidence[-1].model_copy(update={"source_text": "예산은 0원"})
    raw_text = canonical_raw_text + " 예산은 0원"
    candidate = canonical_candidate.model_copy(
        update={"budget_intent": budget, "evidence": [*canonical_candidate.evidence[:-1], evidence]}
    )
    outcome = _validate(candidate, raw_text)
    assert isinstance(outcome, PlanningIntakeV2)
    assert outcome.profile.budget.maximum_amount_minor == 0


def test_omitted_budget_uses_temporary_per_person_ceiling(
    canonical_candidate: MealRequestCandidateV2,
    canonical_raw_text: str,
) -> None:
    candidate = canonical_candidate.model_copy(
        update={
            "budget_intent": canonical_candidate.budget_intent.model_copy(
                update={
                    "budget_type": BudgetIntentType.NO_BUDGET,
                    "currency": None,
                    "target_amount_minor": None,
                    "explicit_maximum_amount_minor": None,
                    "source_text": None,
                }
            )
        }
    )
    outcome = _validate(candidate, canonical_raw_text)
    assert isinstance(outcome, PlanningIntakeV2)
    assert outcome.profile.budget.maximum_amount_minor == 180_000
    assert outcome.profile.budget.maximum_source is BudgetMaximumSource.POLICY_DEFAULT
    assert any(
        assumption.code == "temporary_default_budget_per_person_applied"
        for assumption in outcome.validation_receipt.assumptions
    )
