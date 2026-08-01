from group_food_agent.contracts import MealRequestCandidateV2, PlanningIntakeV2, RequestRejectedV2
from group_food_agent.pipeline import PipelineEvent, PipelineEventType, process_meal_request
from group_food_agent.validation import ValidationContextV2


class FakeInterpreter:
    def __init__(self, candidate: MealRequestCandidateV2) -> None:
        self.candidate = candidate
        self.calls = 0

    async def interpret(self, raw_text: str) -> MealRequestCandidateV2:
        self.calls += 1
        return self.candidate


async def test_valid_input_runs_typed_interpreter_then_validator(
    canonical_candidate: MealRequestCandidateV2,
    canonical_raw_text: str,
) -> None:
    interpreter = FakeInterpreter(canonical_candidate)
    events: list[PipelineEvent] = []
    outcome = await process_meal_request(
        canonical_raw_text,
        ValidationContextV2(request_id="req_pipeline", case_id="case_pipeline"),
        interpreter=interpreter,
        event_sink=events.append,
    )
    assert isinstance(outcome, PlanningIntakeV2)
    assert interpreter.calls == 1
    assert [event.event_type for event in events].count(PipelineEventType.AGENT_STARTED) == 1
    assert [event.event_type for event in events].count(PipelineEventType.AGENT_COMPLETED) == 1
    assert events[-1].stage.value == "outcome"
    assert events[-1].detail["status"] == "ready_for_planning"


async def test_unreadable_text_preflight_never_calls_interpreter(
    canonical_candidate: MealRequestCandidateV2,
) -> None:
    interpreter = FakeInterpreter(canonical_candidate)
    outcome = await process_meal_request(
        "shrimp\x00",
        ValidationContextV2(request_id="req_blocked", case_id="case_blocked"),
        interpreter=interpreter,
    )
    assert isinstance(outcome, RequestRejectedV2)
    assert outcome.reason_code == "unsupported_control_characters"
    assert interpreter.calls == 0
    assert "U+0000" in outcome.issues[0].message


async def test_readable_text_is_not_semantically_filtered_by_preflight(
    canonical_candidate: MealRequestCandidateV2,
) -> None:
    interpreter = FakeInterpreter(canonical_candidate)
    outcome = await process_meal_request(
        "shrimp",
        ValidationContextV2(request_id="req_shrimp", case_id="case_shrimp"),
        interpreter=interpreter,
    )
    assert interpreter.calls == 1
    assert outcome.status != "request_rejected"
