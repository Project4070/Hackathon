from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from group_food_agent.planner_models import MealFeedbackV1
from group_food_agent.planner_contracts import PlanningJobV2
from group_food_agent.service import PlanningService
from group_food_agent.stores import job_from_intake
from group_food_agent.validation import ValidationContextV2, validate_planning_profile


NOW = datetime(2026, 8, 2, 0, 30, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


def test_golden_planning_job_fixture_is_contract_valid():
    job = PlanningJobV2.model_validate_json(
        (ROOT / "fixtures" / "canonical_planning_job_v2.json").read_text(encoding="utf-8")
    )

    assert job.intake.status == "ready_for_planning"
    assert job.intake.profile.party.total_count == 15
    assert job.execution_context.resolved_location.query == "연세대학교 정문"


@pytest.fixture
def planning_service(canonical_candidate, canonical_raw_text):
    intake = validate_planning_profile(
        canonical_candidate,
        ValidationContextV2(request_id="request-plan", case_id="case-plan"),
        raw_text=canonical_raw_text,
    )
    assert intake.status == "ready_for_planning"
    job = job_from_intake(
        intake,
        requested_at=NOW,
        trace_id="trace-plan",
    )
    service = PlanningService(clock=lambda: NOW)
    service.create_case(job)
    return service


def test_canonical_plan_is_reproducible_and_hard_valid(planning_service):
    result = planning_service.plan_case("case-plan")

    assert result.failure is None
    display = result.display
    assert display is not None
    assert display.group_analysis.actual_attendance == 15
    assert display.group_analysis.equivalent_group_servings_milli == 15_450
    assert display.group_analysis.protected_demand_milli == 2_000
    assert display.group_analysis.target_servings_milli == 16_686
    assert display.recommended_plan.combination.validation.hard_constraints_passed
    assert display.recommended_plan.combination.total_cost_minor <= 275_000
    assert display.recommended_plan.combination.budget_evaluated_cost_minor == display.recommended_plan.combination.total_cost_minor
    assert {
        plan.combination.strategy.value
        for plan in [display.recommended_plan, *(alternative.plan for alternative in display.alternatives)]
    } == {
        "leftover_minimizing",
        "balanced",
        "shortage_minimizing",
    }
    assert display.data_mode.value == "simulated_reviewed_fixture"
    assert display.source_completeness.value == "complete"
    assert display.source_parser_version == "fixture-parser-v1"
    assert display.expected_outcome.uncertainties


def test_tool_events_show_the_real_stage_sequence(planning_service):
    planning_service.plan_case("case-plan")
    events = planning_service.events.for_case("case-plan")

    assert len(events) == 18
    assert [event.event_type for event in events[::2]] == ["tool_call"] * 9
    assert [event.event_type for event in events[1::2]] == ["tool_result"] * 9
    assert all(
        call.call_id == result.call_id and result.duration_ms is not None
        for call, result in zip(events[::2], events[1::2], strict=True)
    )
    assert [event.tool_name for event in events[::2]] == [
        "build_serving_input",
        "calculate_serving_requirement",
        "search_menu_candidates",
        "enrich_menu_semantics",
        "apply_hard_eligibility",
        "generate_budget_combinations",
        "score_soft_preferences",
        "rank_and_validate_plans",
        "get_plan_for_presentation",
    ]


def test_restaurant_unavailable_replans_from_stage_five_and_changes_units(planning_service):
    first = planning_service.plan_case("case-plan").display
    assert first is not None
    previous_event_count = len(planning_service.events.for_case("case-plan"))

    second = planning_service.replan_restaurant_unavailable(
        "case-plan", first.restaurant.restaurant_id
    ).display
    assert second is not None

    first_units = sum(line.quantity for line in first.recommended_plan.combination.lines)
    second_units = sum(line.quantity for line in second.recommended_plan.combination.lines)
    assert first.restaurant.restaurant_id != second.restaurant.restaurant_id
    assert first_units == 4
    assert second_units == 6
    new_events = planning_service.events.for_case("case-plan")[previous_event_count:]
    assert new_events[0].stage == 5
    assert all(event.stage >= 5 for event in new_events)


def test_menu_unavailable_replans_without_copying_old_lines(planning_service):
    first = planning_service.plan_case("case-plan").display
    assert first is not None
    unavailable_item = "alpha-cheese-pizza-32"

    replanned = planning_service.replan_menu_unavailable("case-plan", unavailable_item)

    assert replanned.display is not None
    new_item_ids = {
        line.menu_item_id for line in replanned.display.recommended_plan.combination.lines
    }
    assert unavailable_item not in new_item_ids
    assert replanned.display.restaurant.restaurant_id != first.restaurant.restaurant_id


def test_unknown_replan_targets_are_rejected(planning_service):
    planning_service.plan_case("case-plan")
    with pytest.raises(KeyError, match="unknown restaurant"):
        planning_service.replan_restaurant_unavailable("case-plan", "made-up-restaurant")
    with pytest.raises(KeyError, match="unknown menu"):
        planning_service.replan_menu_unavailable("case-plan", "made-up-menu")


def test_missing_restaurant_source_returns_data_unavailable(planning_service):
    job = planning_service.cases.get("case-plan").job
    empty = PlanningService(clock=lambda: NOW, load_default_source=False)
    empty.create_case(job)

    result = empty.plan_case("case-plan")

    assert result.display is None
    assert result.failure is not None
    assert result.failure.status == "data_unavailable"


def test_shortage_feedback_changes_later_demand(planning_service):
    first = planning_service.plan_case("case-plan").display
    assert first is not None
    feedback = MealFeedbackV1(
        case_id="case-plan",
        actual_attendance=15,
        outcome="shortage",
        leftover_servings_milli=0,
        affected_menu_item_ids=[line.menu_item_id for line in first.recommended_plan.combination.lines],
        delivered_portions_smaller_than_expected=True,
        note="portions were smaller and the group ran short",
    )

    adjustment, replanned = planning_service.replan_after_feedback(feedback)

    assert adjustment.previous_demand_multiplier_basis_points == 10_000
    assert adjustment.new_demand_multiplier_basis_points == 10_500
    assert adjustment.menu_serving_multiplier_changes_basis_points
    assert replanned.display is not None
    assert replanned.display.group_analysis.equivalent_group_servings_milli == 16_224
    assert replanned.display.group_analysis.equivalent_group_servings_milli > first.group_analysis.equivalent_group_servings_milli


def test_tiny_budget_returns_controlled_no_valid_plan(planning_service):
    result = planning_service.replan_budget("case-plan", 1_000)

    assert result.display is None
    assert result.failure is not None
    assert result.failure.status == "no_valid_plan"
    assert result.failure.corrective_action


def test_participant_change_creates_new_revision_and_recalculates(planning_service):
    first = planning_service.plan_case("case-plan").display
    assert first is not None

    changed = planning_service.replan_participant_group_count("case-plan", "group_large", 5)

    assert changed.display is not None
    assert changed.display.profile_revision == 2
    assert changed.display.group_analysis.actual_attendance == 16
    assert changed.display.group_analysis.equivalent_group_servings_milli == 16_750
    assert changed.display.group_analysis.equivalent_group_servings_milli > first.group_analysis.equivalent_group_servings_milli
