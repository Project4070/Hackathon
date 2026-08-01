from __future__ import annotations

import pytest

from group_food_agent.application import run_group_food_agent
from group_food_agent.contracts import (
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
        service=PlanningService(load_default_snapshot=False),
        live_planner=False,
    )

    diagnostics = run.diagnostics()
    assert diagnostics["status"] == "blocked"
    assert diagnostics["blocked"] is True
    assert diagnostics["blocked_at"]["source"] == "deterministic_gateway"
    assert diagnostics["blocked_at"]["tool_name"] == "search_menu_candidates"
    assert diagnostics["blocked_at"]["error_type"] == "KeyError"


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
async def test_unlisted_food_category_runs_planner_and_returns_capability_failure(
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
    assert run.plan_result is not None and run.plan_result.failure is not None
    assert run.plan_result.failure.status == "unsupported"
    assert "rice" in run.plan_result.failure.reason
    assert any(event.tool_name == "build_serving_input" for event in run.tool_events)
    assert any(event.tool_name == "search_menu_candidates" for event in run.tool_events)


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
