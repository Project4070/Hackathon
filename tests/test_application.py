from __future__ import annotations

import pytest

from group_food_agent.application import run_group_food_agent
from group_food_agent.contracts import (
    MealRequestCandidateV2,
    SemanticNamespace,
    SemanticTermV2,
    UnresolvedIssueKind,
    UnresolvedIssueV2,
)
from group_food_agent.service import PlanningService
from group_food_agent.validation import ValidationContextV2


class FixedInterpreter:
    def __init__(self, candidate):
        self.candidate = candidate
        self.calls = 0

    async def interpret(self, raw_text):
        self.calls += 1
        return self.candidate


@pytest.mark.asyncio
async def test_complete_application_runs_intake_then_all_planner_tools(
    canonical_candidate, canonical_raw_text
):
    interpreter = FixedInterpreter(canonical_candidate)
    run = await run_group_food_agent(
        canonical_raw_text,
        ValidationContextV2(request_id="request-app", case_id="case-app"),
        interpreter=interpreter,
        live_planner=False,
    )

    assert interpreter.calls == 1
    assert run.boundary_outcome.status == "ready_for_planning"
    assert run.plan_result is not None and run.plan_result.display is not None
    assert run.plan_result.display.status == "plan_ready"
    assert len(run.pipeline_events) == 7
    assert len(run.tool_events) == 18
    assert run.mode == "offline_deterministic_rehearsal"
    assert run.diagnostics()["status"] == "succeeded"
    assert run.diagnostics()["blocked"] is False


@pytest.mark.asyncio
async def test_complete_application_stops_unreadable_input_before_agents_or_tools():
    interpreter = FixedInterpreter(None)
    raw = "shrimp\x00"
    run = await run_group_food_agent(
        raw,
        ValidationContextV2(request_id="request-hostile", case_id="case-hostile"),
        interpreter=interpreter,
        live_planner=False,
    )

    assert run.boundary_outcome.status == "request_rejected"
    assert interpreter.calls == 0
    assert run.plan_result is None
    assert run.tool_events == []


@pytest.mark.asyncio
async def test_live_application_reports_missing_api_key_as_configuration(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        await run_group_food_agent(
            "Pizza for 10 people in Sinchon",
            ValidationContextV2(request_id="request-key", case_id="case-key"),
        )


@pytest.mark.asyncio
async def test_readable_text_is_not_semantically_rejected_before_key_check(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        await run_group_food_agent(
            "shrimp",
            ValidationContextV2(request_id="request-shrimp-key", case_id="case-shrimp-key"),
            live_planner=True,
        )


@pytest.mark.asyncio
async def test_deterministic_gateway_block_is_printable_and_structured(
    canonical_candidate, canonical_raw_text
):
    run = await run_group_food_agent(
        canonical_raw_text,
        ValidationContextV2(request_id="request-gateway", case_id="case-gateway"),
        interpreter=FixedInterpreter(canonical_candidate),
        service=PlanningService(load_default_source=False),
        live_planner=False,
    )

    diagnostics = run.diagnostics()
    assert diagnostics["status"] == "blocked"
    assert diagnostics["blocked"] is True
    assert diagnostics["blocked_at"]["source"] == "deterministic_gateway"
    assert diagnostics["blocked_at"]["tool_name"] == "search_menu_candidates"
    assert diagnostics["blocked_at"]["error_type"] == "LookupError"


@pytest.mark.asyncio
async def test_boundary_diagnostics_preserve_validation_reason_and_stage(
    canonical_candidate, canonical_raw_text
):
    invalid_candidate = canonical_candidate.model_copy(
        update={
            "unresolved_issues": [
                UnresolvedIssueV2(
                    issue_id="unsupported-input",
                    kind=UnresolvedIssueKind.UNSUPPORTED,
                    field_path="/food_scope",
                    message="unsupported input for regression diagnostics",
                    source_text="unsupported input",
                )
            ],
        }
    )
    run = await run_group_food_agent(
        canonical_raw_text,
        ValidationContextV2(request_id="request-diagnostics", case_id="case-diagnostics"),
        interpreter=FixedInterpreter(invalid_candidate),
        live_planner=False,
    )

    diagnostics = run.diagnostics()

    assert diagnostics["status"] == "blocked"
    assert diagnostics["reason"] == "unresolved_unsupported"
    assert diagnostics["blocked_at"]["stage"] == "deterministic_validation"


@pytest.mark.asyncio
async def test_unlisted_food_category_does_not_gate_direct_source_lookup(
    canonical_candidate, canonical_raw_text
):
    rice = SemanticTermV2(
        namespace=SemanticNamespace.FOOD_CATEGORY,
        code="rice",
        label="rice",
    )
    food_scope = canonical_candidate.food_scope.model_copy(update={"requested_categories": [rice]})
    candidate = canonical_candidate.model_copy(update={"food_scope": food_scope})

    run = await run_group_food_agent(
        canonical_raw_text,
        ValidationContextV2(request_id="request-rice", case_id="case-rice"),
        interpreter=FixedInterpreter(candidate),
        live_planner=False,
    )

    assert run.boundary_outcome.status == "ready_for_planning"
    assert run.plan_result is not None and run.plan_result.display is not None
    assert run.plan_result.failure is None
    assert any(
        "requested category and delivery location did not filter" in warning
        for warning in run.plan_result.display.expected_outcome.uncertainties
    )
    assert any(event.tool_name == "build_serving_input" for event in run.tool_events)
    assert any(event.tool_name == "search_menu_candidates" for event in run.tool_events)


@pytest.mark.asyncio
async def test_missing_food_category_does_not_block_planning(
    canonical_candidate, canonical_raw_text
):
    food_scope = canonical_candidate.food_scope.model_copy(update={"requested_categories": []})
    evidence = [
        item
        for item in canonical_candidate.evidence
        if not item.field_path.startswith("/food_scope/requested_categories")
    ]
    candidate = canonical_candidate.model_copy(
        update={
            "food_scope": food_scope,
            "evidence": evidence,
            "unresolved_issues": [
                UnresolvedIssueV2(
                    issue_id="missing-food-category",
                    kind=UnresolvedIssueKind.MISSING,
                    field_path="/food_scope/requested_categories",
                    message="요청한 음식 종류가 제공되지 않았습니다.",
                    source_text=None,
                )
            ],
        }
    )

    run = await run_group_food_agent(
        canonical_raw_text,
        ValidationContextV2(request_id="request-no-category", case_id="case-no-category"),
        interpreter=FixedInterpreter(candidate),
        live_planner=False,
    )

    assert run.boundary_outcome.status == "ready_for_planning"
    assert run.plan_result is not None and run.plan_result.display is not None
    assert run.diagnostics()["blocked"] is False
    assert run.boundary_outcome.profile.food_scope.category_selection.value == "any_of"
    search_event = next(
        event
        for event in run.tool_events
        if event.tool_name == "search_menu_candidates" and "returned" in event.summary
    )
    assert "returned 4 restaurants" in search_event.summary


@pytest.mark.asyncio
async def test_unlisted_allergen_reaches_planner_without_becoming_safe(
    canonical_candidate, canonical_raw_text
):
    shrimp = SemanticTermV2(
        namespace=SemanticNamespace.ALLERGEN,
        code="shrimp",
        label="shrimp",
    )
    requirement = canonical_candidate.hard_requirements[1].model_copy(update={"terms": [shrimp]})
    candidate = canonical_candidate.model_copy(
        update={
            "hard_requirements": [canonical_candidate.hard_requirements[0], requirement],
        }
    )

    run = await run_group_food_agent(
        canonical_raw_text,
        ValidationContextV2(request_id="request-shrimp", case_id="case-shrimp"),
        interpreter=FixedInterpreter(candidate),
        live_planner=False,
    )

    assert run.boundary_outcome.status == "ready_for_planning"
    assert run.plan_result is not None and run.plan_result.failure is not None
    assert run.plan_result.failure.status == "no_valid_plan"
    assert any(event.tool_name == "apply_hard_eligibility" for event in run.tool_events)


@pytest.mark.asyncio
async def test_terse_korean_shrimp_request_runs_end_to_end(canonical_candidate):
    raw = "먹고 싶은 거:shrimp 인원:20명 예산:20만원 장소:신논현역"
    payload = canonical_candidate.model_dump(mode="json")
    payload.update(
        {
            "occasion": {
                "meal_type": "other",
                "service_style": "other",
                "activity_context": "other",
                "food_role": "other",
                "leftover_storage": "unknown",
                "scheduled_at": None,
                "duration_minutes": None,
            },
            "party": {
                "total_count": 20,
                "groups": [
                    {
                        "group_id": "group_default",
                        "display_label": "all attendees",
                        "count": 20,
                        "attendance_status": "confirmed",
                        "appetite": {"band": "normal", "stated_servings_milli": None},
                        "activity_level": "unknown",
                        "recent_meal_status": "unknown",
                    }
                ],
            },
            "location_hint": {
                "source": "user_text",
                "query": "신논현역",
                "latitude": None,
                "longitude": None,
            },
            "food_scope": {
                "requested_categories": [
                    {"namespace": "food_category", "code": "shrimp", "label": "shrimp"}
                ],
                "category_selection": "include_all",
                "excluded_categories": [],
                "restaurant_mixing": "unspecified",
            },
            "hard_requirements": [],
            "preferences": [],
            "budget_intent": {
                "budget_type": "approximate_target",
                "currency": "KRW",
                "target_amount_minor": 200000,
                "explicit_maximum_amount_minor": None,
                "cost_scope": {
                    "include_menu_price": None,
                    "include_delivery_fee": None,
                    "include_service_fee": None,
                    "include_discount": None,
                },
                "source_text": "20만원",
            },
            "restriction_disclosure": {"status": "not_provided"},
            "evidence": [
                {
                    "evidence_id": "e1",
                    "field_path": "/party/total_count",
                    "source_text": "20명",
                    "status": "explicit",
                    "confidence": 1.0,
                    "start_offset": 0,
                    "end_offset": 3,
                    "note": None,
                },
                {
                    "evidence_id": "e2",
                    "field_path": "/food_scope/requested_categories",
                    "source_text": "shrimp",
                    "status": "explicit",
                    "confidence": 1.0,
                    "start_offset": 0,
                    "end_offset": 6,
                    "note": None,
                },
                {
                    "evidence_id": "e3",
                    "field_path": "/budget_intent/target_amount_minor",
                    "source_text": "20만원",
                    "status": "explicit",
                    "confidence": 1.0,
                    "start_offset": 0,
                    "end_offset": 5,
                    "note": None,
                },
                {
                    "evidence_id": "e4",
                    "field_path": "/location_hint/query",
                    "source_text": "신논현역",
                    "status": "explicit",
                    "confidence": 1.0,
                    "start_offset": 0,
                    "end_offset": 4,
                    "note": None,
                },
            ],
            "unresolved_issues": [],
        }
    )
    candidate = MealRequestCandidateV2.model_validate(payload)

    run = await run_group_food_agent(
        raw,
        ValidationContextV2(request_id="request-shrimp-e2e", case_id="case-shrimp-e2e"),
        interpreter=FixedInterpreter(candidate),
        live_planner=False,
    )

    assert run.boundary_outcome.status == "ready_for_planning"
    assert run.plan_result is not None and run.plan_result.display is not None
    assert run.plan_result.display.recommended_plan.combination.total_cost_minor <= 220000
    assert run.plan_result.failure is None
    assert any(
        "requested category and delivery location did not filter" in warning
        for warning in run.plan_result.display.expected_outcome.uncertainties
    )
    assumption_codes = {
        assumption.code for assumption in run.boundary_outcome.validation_receipt.assumptions
    }
    assert "default_participant_group_applied" in assumption_codes
    assert "default_meal_context_applied" in assumption_codes
