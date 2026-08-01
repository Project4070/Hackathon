"""Generate checked JSON Schema artifacts from the Pydantic source of truth."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import TypeAdapter

from .contracts import (
    ClarificationRequiredV2,
    MealRequestCandidateV2,
    PlanningBoundaryOutcomeV2,
    PlanningIntakeV2,
    RequestRejectedV2,
)
from .planner_contracts import PlannerViewV2, PlanningJobV2
from .planner_models import (
    CandidateMenuSetV1,
    CombinationSetV1,
    DisplayPlanV1,
    EligibleMenuSetV1,
    NormalizedMenuSetV1,
    PlanningFailureV1,
    PlannerAgentFinalV1,
    PresentationToolResultV1,
    RankedPlanSetV1,
    RestaurantSnapshotV1,
    ScoredCombinationSetV1,
    ServingCalculationInputV1,
    ServingRequirementV1,
    ToolEventV1,
)
from .crawler import RawCrawlBatchV1
from .semantic_agents import MenuSemanticCandidateV1
from .naver_planner_adapter import PlannerRestaurantV1


SCHEMA_TYPES = {
    "meal_request_candidate_v2.schema.json": MealRequestCandidateV2,
    "planning_intake_v2.schema.json": PlanningIntakeV2,
    "clarification_required_v2.schema.json": ClarificationRequiredV2,
    "request_rejected_v2.schema.json": RequestRejectedV2,
    "planning_job_v2.schema.json": PlanningJobV2,
    "serving_calculation_input_v1.schema.json": ServingCalculationInputV1,
    "serving_requirement_v1.schema.json": ServingRequirementV1,
    "restaurant_snapshot_v1.schema.json": RestaurantSnapshotV1,
    "candidate_menu_set_v1.schema.json": CandidateMenuSetV1,
    "normalized_menu_set_v1.schema.json": NormalizedMenuSetV1,
    "eligible_menu_set_v1.schema.json": EligibleMenuSetV1,
    "combination_set_v1.schema.json": CombinationSetV1,
    "scored_combination_set_v1.schema.json": ScoredCombinationSetV1,
    "ranked_plan_set_v1.schema.json": RankedPlanSetV1,
    "display_plan_v1.schema.json": DisplayPlanV1,
    "planning_failure_v1.schema.json": PlanningFailureV1,
    "tool_event_v1.schema.json": ToolEventV1,
    "raw_crawl_batch_v1.schema.json": RawCrawlBatchV1,
    "menu_semantic_candidate_v1.schema.json": MenuSemanticCandidateV1,
    "planner_view_v2.schema.json": PlannerViewV2,
    "planner_agent_final_v1.schema.json": PlannerAgentFinalV1,
    "presentation_tool_result_v1.schema.json": PresentationToolResultV1,
    "planner_restaurant_v1.schema.json": PlannerRestaurantV1,
}


def generate_schemas(output_directory: Path) -> list[Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, model_type in SCHEMA_TYPES.items():
        path = output_directory / filename
        path.write_text(
            json.dumps(model_type.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    boundary_path = output_directory / "planning_boundary_outcome_v2.schema.json"
    boundary_path.write_text(
        json.dumps(TypeAdapter(PlanningBoundaryOutcomeV2).json_schema(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    written.append(boundary_path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("schemas"))
    args = parser.parse_args()
    for path in generate_schemas(args.output):
        print(path)


if __name__ == "__main__":
    main()
