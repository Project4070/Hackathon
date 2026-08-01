"""Typed OpenAI Agents SDK tools for the G3 main planner agent."""

from __future__ import annotations

from dataclasses import dataclass

from agents import RunContextWrapper, function_tool

from .planner_models import ArtifactResult, DisplayPlanV1, PresentationToolResultV1
from .service import PlanningService


@dataclass
class PlannerDependencies:
    """Local, trusted dependencies injected into an Agents SDK run."""

    service: PlanningService


@function_tool
def build_serving_input(
    context: RunContextWrapper[PlannerDependencies], case_id: str
) -> ArtifactResult:
    """Adapt the immutable planning intake to the configured serving vocabulary.

    Args:
        case_id: Existing validated planning case identifier.
    """

    return context.context.service.build_serving_input(case_id)


@function_tool
def calculate_serving_requirement(
    context: RunContextWrapper[PlannerDependencies], case_id: str, serving_input_id: str
) -> ArtifactResult:
    """Deterministically calculate group and protected serving demand.

    Args:
        case_id: Existing validated planning case identifier.
        serving_input_id: Artifact returned by build_serving_input.
    """

    return context.context.service.calculate_serving_requirement(case_id, serving_input_id)


@function_tool
def search_menu_candidates(
    context: RunContextWrapper[PlannerDependencies], case_id: str
) -> ArtifactResult:
    """Query the bounded restaurant snapshot cache for source-backed candidates.

    Args:
        case_id: Existing validated planning case identifier.
    """

    try:
        return context.context.service.search_menu_candidates(case_id)
    except LookupError as exc:
        reason = str(exc)
        status = "unsupported" if reason.startswith("planner capability unavailable") else "data_unavailable"
        return context.context.service.controlled_tool_failure(
            case_id,
            stage=5,
            tool_name="search_menu_candidates",
            status=status,
            reason=reason,
        )


@function_tool
def enrich_menu_semantics(
    context: RunContextWrapper[PlannerDependencies], case_id: str, candidate_menu_set_id: str
) -> ArtifactResult:
    """Validate cached semantic normalization and its source provenance.

    Args:
        case_id: Existing validated planning case identifier.
        candidate_menu_set_id: Artifact returned by search_menu_candidates.
    """

    return context.context.service.enrich_menu_semantics(case_id, candidate_menu_set_id)


@function_tool
def apply_hard_eligibility(
    context: RunContextWrapper[PlannerDependencies], case_id: str, normalized_menu_set_id: str
) -> ArtifactResult:
    """Apply deterministic allergy and dietary eligibility checks.

    Args:
        case_id: Existing validated planning case identifier.
        normalized_menu_set_id: Artifact returned by enrich_menu_semantics.
    """

    return context.context.service.apply_hard_eligibility(case_id, normalized_menu_set_id)


@function_tool
def generate_budget_combinations(
    context: RunContextWrapper[PlannerDependencies],
    case_id: str,
    eligible_menu_set_id: str,
    serving_requirement_id: str,
) -> ArtifactResult:
    """Run bounded whole-unit combination search and hard validation.

    Args:
        case_id: Existing validated planning case identifier.
        eligible_menu_set_id: Artifact returned by apply_hard_eligibility.
        serving_requirement_id: Artifact returned by calculate_serving_requirement.
    """

    return context.context.service.generate_budget_combinations(
        case_id, eligible_menu_set_id, serving_requirement_id
    )


@function_tool
def score_soft_preferences(
    context: RunContextWrapper[PlannerDependencies],
    case_id: str,
    combination_set_id: str,
    eligible_menu_set_id: str,
) -> ArtifactResult:
    """Score only soft preferences using bounded policy weights.

    Args:
        case_id: Existing validated planning case identifier.
        combination_set_id: Artifact returned by generate_budget_combinations.
        eligible_menu_set_id: Artifact returned by apply_hard_eligibility.
    """

    return context.context.service.score_soft_preferences(
        case_id, combination_set_id, eligible_menu_set_id
    )


@function_tool
def rank_and_validate_plans(
    context: RunContextWrapper[PlannerDependencies], case_id: str, scored_combination_set_id: str
) -> ArtifactResult:
    """Choose one hard-valid plan for each of the three quantity strategies.

    Args:
        case_id: Existing validated planning case identifier.
        scored_combination_set_id: Artifact returned by score_soft_preferences.
    """

    try:
        return context.context.service.rank_and_validate_plans(case_id, scored_combination_set_id)
    except LookupError as exc:
        return context.context.service.controlled_tool_failure(
            case_id,
            stage=10,
            tool_name="rank_and_validate_plans",
            status="no_valid_plan",
            reason=str(exc),
            input_ids=[scored_combination_set_id],
        )


@function_tool
def get_plan_for_presentation(
    context: RunContextWrapper[PlannerDependencies],
    case_id: str,
    ranked_plan_set_id: str,
    serving_requirement_id: str,
    candidate_menu_set_id: str,
) -> PresentationToolResultV1:
    """Build the final provenance-bearing judge-readable plan artifact.

    Args:
        case_id: Existing validated planning case identifier.
        ranked_plan_set_id: Artifact returned by rank_and_validate_plans.
        serving_requirement_id: Artifact returned by calculate_serving_requirement.
        candidate_menu_set_id: Artifact returned by search_menu_candidates.
    """

    artifact = context.context.service.get_plan_for_presentation(
        case_id, ranked_plan_set_id, serving_requirement_id, candidate_menu_set_id
    )
    display = context.context.service.artifacts.get(
        artifact.ref.artifact_id, DisplayPlanV1
    )
    return PresentationToolResultV1(artifact=artifact, display=display)  # type: ignore[arg-type]


MAIN_PLANNER_TOOLS = [
    build_serving_input,
    calculate_serving_requirement,
    search_menu_candidates,
    enrich_menu_semantics,
    apply_hard_eligibility,
    generate_budget_combinations,
    score_soft_preferences,
    rank_and_validate_plans,
    get_plan_for_presentation,
]
