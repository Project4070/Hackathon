from __future__ import annotations

from datetime import datetime, timezone

from group_food_agent.contracts import (
    EvidenceStatus,
    EvidenceV2,
    HardRequirementKind,
    HardRequirementV2,
    MealRequestCandidateV2,
    PlanningIntakeV2,
    SemanticNamespace,
    SemanticTermV2,
    UnresolvedIssueKind,
    UnresolvedIssueV2,
)
from group_food_agent.intake_normalization import normalize_candidate_for_validation
from group_food_agent.service import PlanningService
from group_food_agent.stores import job_from_intake
from group_food_agent.validation import ValidationContextV2, validate_planning_profile


def test_partial_appetite_groups_and_missing_category_evidence_are_repaired(
    canonical_candidate: MealRequestCandidateV2,
) -> None:
    raw_text = (
        "오늘 동아리원 15명이 저녁으로 치킨이랑 피자를 먹을 거야. "
        "많이 먹는 사람은 4명, 적게 먹는 사람은 3명이야. "
        "예산은 25만 원 정도야. 매운 음식은 피하고 싶어. "
        "배달 장소는 강남역으로 부탁해."
    )
    large_group = canonical_candidate.party.groups[0].model_copy(
        update={"display_label": "많이 먹는 사람", "count": 4}
    )
    light_group = canonical_candidate.party.groups[2].model_copy(
        update={"display_label": "적게 먹는 사람", "count": 3}
    )
    party = canonical_candidate.party.model_copy(
        update={"total_count": 15, "groups": [large_group, light_group]}
    )
    food_scope = canonical_candidate.food_scope.model_copy(
        update={
            "requested_categories": [
                SemanticTermV2(
                    namespace=SemanticNamespace.FOOD_CATEGORY,
                    code="chicken",
                    label="치킨",
                ),
                SemanticTermV2(
                    namespace=SemanticNamespace.FOOD_CATEGORY,
                    code="pizza",
                    label="피자",
                ),
            ]
        }
    )
    budget = canonical_candidate.budget_intent.model_copy(
        update={"source_text": "예산은 25만 원 정도야"}
    )
    location = canonical_candidate.location_hint.model_copy(update={"query": "강남역"})
    spice_requirement = HardRequirementV2(
        requirement_id="hr_non_spicy",
        kind=HardRequirementKind.SPICE_LIMIT,
        affected_group_ids=[
            large_group.group_id,
            light_group.group_id,
            "group_default_remaining",
        ],
        terms=[
            SemanticTermV2(
                namespace=SemanticNamespace.SPICE,
                code="non_spicy",
                label="매운 음식",
            )
        ],
        source_text="매운 음식은 피하고 싶어",
    )
    evidence = [
        EvidenceV2(
            evidence_id="e_total",
            field_path="/party/total_count",
            source_text="15명",
            status=EvidenceStatus.EXPLICIT,
            confidence=1.0,
            start_offset=None,
            end_offset=None,
            note=None,
        ),
        EvidenceV2(
            evidence_id="e_groups",
            field_path="/party/groups",
            source_text="많이 먹는 사람은 4명, 적게 먹는 사람은 3명",
            status=EvidenceStatus.EXPLICIT,
            confidence=1.0,
            start_offset=None,
            end_offset=None,
            note=None,
        ),
        EvidenceV2(
            evidence_id="e_budget",
            field_path="/budget_intent",
            source_text="예산은 25만 원 정도야",
            status=EvidenceStatus.EXPLICIT,
            confidence=1.0,
            start_offset=None,
            end_offset=None,
            note=None,
        ),
        EvidenceV2(
            evidence_id="e_spice",
            field_path="/hard_requirements/hr_non_spicy",
            source_text="매운 음식은 피하고 싶어",
            status=EvidenceStatus.EXPLICIT,
            confidence=1.0,
            start_offset=None,
            end_offset=None,
            note=None,
        ),
    ]
    candidate = canonical_candidate.model_copy(
        update={
            "party": party,
            "location_hint": location,
            "food_scope": food_scope,
            "hard_requirements": [spice_requirement],
            "preferences": [],
            "budget_intent": budget,
            "evidence": evidence,
            "unresolved_issues": [
                UnresolvedIssueV2(
                    issue_id="missing-remainder",
                    kind=UnresolvedIssueKind.CONFLICTING,
                    field_path="/party/total_count",
                    message="The remaining eight appetites were not stated.",
                    source_text=None,
                )
            ],
        }
    )

    normalized = normalize_candidate_for_validation(candidate, raw_text)
    outcome = validate_planning_profile(
        normalized,
        ValidationContextV2(request_id="request-partial", case_id="case-partial"),
        raw_text=raw_text,
    )

    assert isinstance(outcome, PlanningIntakeV2)
    assert [group.count for group in outcome.profile.party.groups] == [4, 3, 8]
    assert normalized.unresolved_issues == []
    assert {
        item.source_text
        for item in normalized.evidence
        if item.field_path.startswith("/food_scope/requested_categories")
    } == {"치킨", "피자"}
    default_assumption = next(
        item
        for item in outcome.validation_receipt.assumptions
        if item.code == "default_participant_group_applied"
    )
    assert default_assumption.applied_value == "8 attendees at normal appetite"

    now = datetime(2026, 8, 2, tzinfo=timezone.utc)
    service = PlanningService(clock=lambda: now)
    service.create_case(job_from_intake(outcome, requested_at=now, trace_id="trace-partial"))
    plan = service.plan_case(outcome.case_id)

    assert plan.failure is None
    assert plan.display is not None and plan.display.status == "plan_ready"
    assert len(service.events.for_case(outcome.case_id)) == 18


def test_evidence_whitespace_is_repaired_to_the_literal_request(
    canonical_candidate: MealRequestCandidateV2,
) -> None:
    raw_text = "남자 9명, 여 자 6명"
    evidence = EvidenceV2(
        evidence_id="e_gender",
        field_path="/context_notes",
        source_text="여자 6명",
        status=EvidenceStatus.EXPLICIT,
        confidence=1.0,
        start_offset=None,
        end_offset=None,
        note=None,
    )
    candidate = canonical_candidate.model_copy(update={"evidence": [evidence]})

    normalized = normalize_candidate_for_validation(candidate, raw_text)
    repaired = next(item for item in normalized.evidence if item.evidence_id == "e_gender")

    assert repaired.source_text == "여 자 6명"
    assert raw_text[repaired.start_offset : repaired.end_offset] == "여 자 6명"
