"""Strict contracts for the validated planning handoff (G2) and runtime policy.

The intake profile is immutable.  Runtime search/ranking policy and execution
metadata are attached in :class:`PlanningJobV2` so deterministic tools never
need to recover configuration from prompt prose.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from .contracts import ContractModel, Identifier, LocationSource, PlanningIntakeV2


PolicyId = Annotated[
    str,
    StringConstraints(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"),
]
BasisPoints = Annotated[int, Field(strict=True, ge=0, le=10_000)]


class UnknownIngredientPolicy(StrEnum):
    KEEP_WITH_PENALTY = "keep_with_penalty"
    EXCLUDE = "exclude"


class HardConstraintUnknownPolicy(StrEnum):
    EXCLUDE = "exclude"


class MenuEvaluationMode(StrEnum):
    INDIVIDUAL_MENU = "individual_menu"


class RankingMetric(StrEnum):
    CONSTRAINT_SATISFACTION = "constraint_satisfaction"
    SERVING_FIT = "serving_fit"
    MENU_DIVERSITY = "menu_diversity"
    BUDGET_EFFICIENCY = "budget_efficiency"
    ORDER_SIMPLICITY = "order_simplicity"
    DELIVERY_FIT = "delivery_fit"


class ServingPolicyRefV2(ContractModel):
    serving_policy_id: PolicyId
    quantity_policy_id: PolicyId


class BudgetPolicyV2(ContractModel):
    policy_id: PolicyId
    approximate_tolerance_basis_points: BasisPoints


class RestaurantSearchPolicyV2(ContractModel):
    policy_id: PolicyId
    restaurant_limit: Annotated[int, Field(strict=True, ge=1, le=10)]
    delivery_required: bool
    allow_bounded_refresh: bool
    maximum_cache_age_seconds: Annotated[int, Field(strict=True, ge=0, le=604_800)]


class MenuFilterPolicyV2(ContractModel):
    policy_id: PolicyId
    evaluation_mode: MenuEvaluationMode
    unknown_ingredient_policy: UnknownIngredientPolicy
    hard_constraint_unknown_policy: HardConstraintUnknownPolicy
    eligibility_output_schema: Annotated[str, StringConstraints(min_length=1, max_length=100)]


class CombinationPolicyV2(ContractModel):
    policy_id: PolicyId
    allow_duplicate_menu_items: bool
    maximum_distinct_items: Annotated[int, Field(strict=True, ge=1, le=20)] | None
    maximum_total_quantity: Annotated[int, Field(strict=True, ge=1, le=100)] | None


class RankingObjectiveV2(ContractModel):
    metric: RankingMetric
    weight_basis_points: BasisPoints


class DiversityPolicyV2(ContractModel):
    category_balance: bool
    avoid_single_item_dominance: bool
    duplicate_penalty_basis_points: BasisPoints


class RankingPolicyV2(ContractModel):
    policy_id: PolicyId
    objectives: Annotated[list[RankingObjectiveV2], Field(min_length=1, max_length=16)]
    diversity: DiversityPolicyV2

    @model_validator(mode="after")
    def weights_are_complete_and_unique(self) -> "RankingPolicyV2":
        metrics = [objective.metric for objective in self.objectives]
        if len(metrics) != len(set(metrics)):
            raise ValueError("ranking objective metrics must be unique")
        if sum(objective.weight_basis_points for objective in self.objectives) != 10_000:
            raise ValueError("ranking objective weights must sum to 10000 basis points")
        return self


class PlannerRuntimePolicyV2(ContractModel):
    serving_policy: ServingPolicyRefV2
    budget_policy: BudgetPolicyV2
    restaurant_search: RestaurantSearchPolicyV2
    menu_filter: MenuFilterPolicyV2
    combination: CombinationPolicyV2
    ranking: RankingPolicyV2


class ResolvedLocationV2(ContractModel):
    source: LocationSource
    query: Annotated[str, StringConstraints(min_length=1, max_length=300)] | None
    latitude: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)] | None
    longitude: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)] | None

    @model_validator(mode="after")
    def location_is_usable(self) -> "ResolvedLocationV2":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must both be present or both be null")
        if self.query is None and self.latitude is None:
            raise ValueError("resolved location needs a query or coordinate pair")
        return self


class PlannerExecutionContextV2(ContractModel):
    requested_at: AwareDatetime
    resolved_location: ResolvedLocationV2
    restaurant_snapshot_id: Identifier | None
    trace_id: Identifier


class PlanningJobV2(ContractModel):
    """The only accepted input to the G3 main planner agent."""

    schema_name: Literal["planning_job"] = "planning_job"
    schema_version: Literal["2.0"] = "2.0"
    vocabulary_version: Literal["1.0"] = "1.0"
    intake: PlanningIntakeV2
    runtime_policy: PlannerRuntimePolicyV2
    execution_context: PlannerExecutionContextV2

    @model_validator(mode="after")
    def context_matches_intake(self) -> "PlanningJobV2":
        expected = self.intake.profile.location_requirement
        resolved = self.execution_context.resolved_location
        if expected.delivery_required and not self.runtime_policy.restaurant_search.delivery_required:
            raise ValueError("runtime restaurant policy cannot disable required delivery")
        if expected.query and resolved.query != expected.query:
            raise ValueError("resolved location query must match validated intake")
        if expected.latitude is not None and (
            resolved.latitude != expected.latitude or resolved.longitude != expected.longitude
        ):
            raise ValueError("resolved coordinates must match validated intake")
        return self


class PlannerViewV2(ContractModel):
    """Small, non-prose view supplied to the main orchestration agent."""

    case_id: Identifier
    profile_revision: Annotated[int, Field(strict=True, ge=1)]
    participant_count: Annotated[int, Field(strict=True, ge=1, le=100)]
    location_query: Annotated[str, StringConstraints(min_length=1, max_length=300)] | None
    requested_category_codes: Annotated[list[str], Field(min_length=1, max_length=16)]
    hard_requirement_ids: Annotated[list[Identifier], Field(max_length=100)]
    risk_preference: Annotated[str, StringConstraints(min_length=1, max_length=50)]
    maximum_budget_minor: Annotated[int, Field(strict=True, ge=0)] | None
    snapshot_id: Identifier | None
    policy_ids: Annotated[list[PolicyId], Field(min_length=6, max_length=8)]


def default_runtime_policy() -> PlannerRuntimePolicyV2:
    """Return the documented, versioned hackathon defaults."""

    return PlannerRuntimePolicyV2(
        serving_policy=ServingPolicyRefV2(
            serving_policy_id="serving-policy-kr-v1",
            quantity_policy_id="quantity-policy-v1",
        ),
        budget_policy=BudgetPolicyV2(
            policy_id="budget-policy-v1",
            approximate_tolerance_basis_points=1_000,
        ),
        restaurant_search=RestaurantSearchPolicyV2(
            policy_id="restaurant-search-v1",
            restaurant_limit=10,
            delivery_required=True,
            allow_bounded_refresh=True,
            maximum_cache_age_seconds=86_400,
        ),
        menu_filter=MenuFilterPolicyV2(
            policy_id="menu-filter-v1",
            evaluation_mode=MenuEvaluationMode.INDIVIDUAL_MENU,
            unknown_ingredient_policy=UnknownIngredientPolicy.KEEP_WITH_PENALTY,
            hard_constraint_unknown_policy=HardConstraintUnknownPolicy.EXCLUDE,
            eligibility_output_schema="eligible-menu-set-v1",
        ),
        combination=CombinationPolicyV2(
            policy_id="combination-policy-v1",
            allow_duplicate_menu_items=True,
            maximum_distinct_items=4,
            maximum_total_quantity=20,
        ),
        ranking=RankingPolicyV2(
            policy_id="ranking-policy-v1",
            objectives=[
                RankingObjectiveV2(
                    metric=RankingMetric.CONSTRAINT_SATISFACTION,
                    weight_basis_points=4_000,
                ),
                RankingObjectiveV2(metric=RankingMetric.SERVING_FIT, weight_basis_points=2_500),
                RankingObjectiveV2(metric=RankingMetric.MENU_DIVERSITY, weight_basis_points=2_000),
                RankingObjectiveV2(metric=RankingMetric.BUDGET_EFFICIENCY, weight_basis_points=1_500),
            ],
            diversity=DiversityPolicyV2(
                category_balance=True,
                avoid_single_item_dominance=True,
                duplicate_penalty_basis_points=500,
            ),
        ),
    )
