from __future__ import annotations

import pytest

from group_food_agent.planner_agent import build_main_planner_agent, run_agent_plan
from group_food_agent.planner_models import PlannerAgentFinalV1
from group_food_agent.service import PlanningService
from group_food_agent.demo_cli import build_canonical_job
from types import SimpleNamespace


def test_main_planner_is_real_agents_sdk_agent_with_typed_tools():
    agent = build_main_planner_agent()

    assert agent.__class__.__module__.startswith("agents")
    assert agent.model == "gpt-5.6-sol"
    assert agent.output_type.__name__ == "PlannerAgentFinalV1"
    assert [tool.name for tool in agent.tools] == [
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
    for tool in agent.tools:
        assert tool.params_json_schema["additionalProperties"] is False


@pytest.mark.asyncio
async def test_live_runner_requires_key_before_network(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        await run_agent_plan(PlanningService(), "case-does-not-matter")


@pytest.mark.asyncio
async def test_sdk_runner_resolves_only_the_trusted_terminal_artifact(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    service = PlanningService()
    job = build_canonical_job()
    service.create_case(job)
    offline = service.plan_case(job.intake.case_id)
    assert offline.display_artifact_id is not None
    captured = {}

    async def fake_runner(agent, prompt, context, max_turns, run_config):
        captured["prompt"] = prompt
        captured["run_config"] = run_config
        return SimpleNamespace(
            final_output=PlannerAgentFinalV1(
                case_id=job.intake.case_id,
                display_artifact_id=offline.display_artifact_id,
                failure_artifact_id=None,
                summary="Deterministic tools produced a hard-valid balanced plan.",
                recommendation_explanation="The balanced target passed all hard checks.",
                tradeoff_explanation="The other two plans trade lower leftovers against lower shortage risk.",
                uncertainty_explanation="The restaurant data is a reviewed synthetic fixture, not live data.",
            )
        )

    result = await run_agent_plan(service, job.intake.case_id, runner=fake_runner)

    assert result.display_artifact_id == offline.display_artifact_id
    assert result.agent_explanation is not None
    assert "PlannerViewV2=" in captured["prompt"]
    assert captured["run_config"].trace_include_sensitive_data is False
    assert captured["run_config"].group_id == job.intake.case_id
    assert captured["run_config"].trace_metadata["logical_trace_id"] == "trace-canonical-15"
