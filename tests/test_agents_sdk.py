from types import SimpleNamespace

from agents import Agent, AgentOutputSchema

from group_food_agent.contracts import MealRequestCandidateV2
from group_food_agent.interpreter import MealRequestInterpreter, build_interpreter_agent


def test_interpreter_is_an_openai_agents_sdk_agent() -> None:
    agent = build_interpreter_agent("gpt-5.6-sol")
    assert isinstance(agent, Agent)
    assert agent.output_type is MealRequestCandidateV2
    assert agent.model == "gpt-5.6-sol"
    output_schema = AgentOutputSchema(MealRequestCandidateV2)
    assert output_schema.is_strict_json_schema()
    assert output_schema.json_schema()["additionalProperties"] is False


async def test_interpreter_has_one_bounded_retry(canonical_candidate: MealRequestCandidateV2) -> None:
    calls = 0
    captured_run_config = None

    async def fake_runner(agent, raw_text, **kwargs):
        nonlocal calls, captured_run_config
        calls += 1
        captured_run_config = kwargs["run_config"]
        if calls == 1:
            raise RuntimeError("temporary structured-output failure")
        return SimpleNamespace(final_output=canonical_candidate)

    interpreter = MealRequestInterpreter(runner=fake_runner, maximum_attempts=2)
    result = await interpreter.interpret("Pizza dinner for 15 people")
    assert result == canonical_candidate
    assert calls == 2
    assert captured_run_config.trace_include_sensitive_data is False
    assert captured_run_config.workflow_name == "group_food_request_interpreter"
