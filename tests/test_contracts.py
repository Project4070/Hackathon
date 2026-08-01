from pathlib import Path

import pytest
from pydantic import ValidationError

from group_food_agent.contracts import EvidenceStatus, MealRequestCandidateV2, PlanningIntakeV2
from group_food_agent.schemas import generate_schemas
from group_food_agent.validation import ValidationContextV2, validate_planning_profile


def test_unknown_fields_are_forbidden(canonical_candidate: MealRequestCandidateV2) -> None:
    payload = canonical_candidate.model_dump(mode="json")
    payload["model_owned_policy"] = {"safety_margin": 99}
    with pytest.raises(ValidationError):
        MealRequestCandidateV2.model_validate(payload)


def test_evidence_status_cannot_misrepresent_source_text(
    canonical_candidate: MealRequestCandidateV2,
) -> None:
    payload = canonical_candidate.evidence[0].model_dump(mode="json")
    payload["status"] = EvidenceStatus.DEFAULTED
    with pytest.raises(ValidationError):
        type(canonical_candidate.evidence[0]).model_validate(payload)


def test_ready_intake_is_frozen(canonical_candidate: MealRequestCandidateV2, canonical_raw_text: str) -> None:
    outcome = validate_planning_profile(
        canonical_candidate,
        ValidationContextV2(request_id="req_test", case_id="case_test"),
        raw_text=canonical_raw_text,
    )
    assert isinstance(outcome, PlanningIntakeV2)
    with pytest.raises(ValidationError):
        outcome.profile_revision = 2


def test_schema_generation_uses_pydantic_source_of_truth(tmp_path: Path) -> None:
    paths = generate_schemas(tmp_path)
    assert len(paths) == 29
    filenames = {path.name for path in paths}
    assert {
        "planning_job_v2.schema.json",
        "display_plan_v1.schema.json",
        "tool_event_v1.schema.json",
        "raw_crawl_batch_v1.schema.json",
        "menu_semantic_candidate_v1.schema.json",
        "planner_view_v2.schema.json",
        "planner_agent_final_v1.schema.json",
        "presentation_tool_result_v1.schema.json",
        "planner_restaurant_v1.schema.json",
        "multimodal_meal_request_candidate_v1.schema.json",
        "scene_analysis_v1.schema.json",
        "existing_food_credit_v1.schema.json",
        "multimodal_context_v1.schema.json",
        "team_history_context_v1.schema.json",
    } <= filenames
    candidate_schema = (tmp_path / "meal_request_candidate_v2.schema.json").read_text(encoding="utf-8")
    assert '"additionalProperties": false' in candidate_schema
    assert '"MealRequestCandidateV2"' in candidate_schema
