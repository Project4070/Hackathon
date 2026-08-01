"""Versioned artifacts emitted by deterministic planning stages G4--G7."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from .contracts import (
    ContractModel,
    HardRequirementKind,
    Identifier,
    PreferencePolarity,
    RiskPreference,
    SemanticNamespace,
)


NonNegativeMilli = Annotated[int, Field(strict=True, ge=0, le=10_000_000)]
MoneyMinor = Annotated[int, Field(strict=True, ge=0, le=10_000_000_000)]
ShortCode = Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")]


class ArtifactRef(ContractModel):
    case_id: Identifier
    artifact_type: ShortCode
    artifact_id: Identifier
    profile_revision: Annotated[int, Field(strict=True, ge=1)]
    created_at: AwareDatetime


class ArtifactResult(ContractModel):
    ref: ArtifactRef
    summary: Annotated[str, StringConstraints(min_length=1, max_length=500)]


class PlanStrategy(StrEnum):
    LEFTOVER_MINIMIZING = "leftover_minimizing"
    BALANCED = "balanced"
    SHORTAGE_MINIMIZING = "shortage_minimizing"


class ConfidenceLabel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FreshnessStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"


class CompletenessStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"


class DataMode(StrEnum):
    CRAWLER_LIVE = "crawler_live"
    CRAWLER_CACHE = "crawler_cache"
    STALE_CACHE = "stale_cache"
    SIMULATED_REVIEWED_FIXTURE = "simulated_reviewed_fixture"


class SemanticFieldStatus(StrEnum):
    EXPLICIT = "explicit"
    NORMALIZED = "normalized"
    INFERRED = "inferred"
    AMBIGUOUS = "ambiguous"


class AvailabilityStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class VegetarianStatus(StrEnum):
    EXPLICIT_YES = "explicit_yes"
    EXPLICIT_NO = "explicit_no"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class SpiceLevel(StrEnum):
    NONE = "none"
    MILD = "mild"
    MEDIUM = "medium"
    HOT = "hot"
    UNKNOWN = "unknown"


class ServingGroupInputV1(ContractModel):
    group_id: Identifier
    count: Annotated[int, Field(strict=True, ge=1, le=100)]
    appetite_code: ShortCode
    appetite_factor_milli: Annotated[int, Field(strict=True, ge=0, le=10_000)]
    meal_context_code: ShortCode
    meal_context_factor_milli: Annotated[int, Field(strict=True, ge=0, le=10_000)]
    adjustment_codes: Annotated[list[ShortCode], Field(max_length=8)]
    protected: bool


class ServingCalculationInputV1(ContractModel):
    schema_name: Literal["serving_calculation_input"] = "serving_calculation_input"
    schema_version: Literal["1.0"] = "1.0"
    case_id: Identifier
    profile_revision: Annotated[int, Field(strict=True, ge=1)]
    serving_policy_id: Identifier
    quantity_policy_id: Identifier
    groups: Annotated[list[ServingGroupInputV1], Field(min_length=1, max_length=100)]
    strategy: RiskPreference
    feedback_demand_multiplier_basis_points: Annotated[int, Field(strict=True, ge=7_500, le=12_500)]
    warnings: Annotated[list[str], Field(max_length=64)]


class GroupDemandV1(ContractModel):
    group_id: Identifier
    participant_count: Annotated[int, Field(strict=True, ge=1, le=100)]
    per_person_servings_milli: NonNegativeMilli
    total_servings_milli: NonNegativeMilli
    protected: bool
    applied_factor_codes: Annotated[list[ShortCode], Field(min_length=2, max_length=12)]


class StrategyTargetV1(ContractModel):
    strategy: PlanStrategy
    safety_margin_basis_points: Annotated[int, Field(strict=True, ge=0, le=1_500)]
    target_servings_milli: NonNegativeMilli


class ServingRequirementV1(ContractModel):
    schema_name: Literal["serving_requirement"] = "serving_requirement"
    schema_version: Literal["1.0"] = "1.0"
    case_id: Identifier
    profile_revision: Annotated[int, Field(strict=True, ge=1)]
    attendance_count: Annotated[int, Field(strict=True, ge=1, le=100)]
    equivalent_group_servings_milli: NonNegativeMilli
    protected_demand_milli: NonNegativeMilli
    group_demands: Annotated[list[GroupDemandV1], Field(min_length=1, max_length=100)]
    strategy_targets: Annotated[list[StrategyTargetV1], Field(min_length=3, max_length=3)]
    serving_policy_id: Identifier
    warnings: Annotated[list[str], Field(max_length=64)]

    def target_for(self, strategy: PlanStrategy) -> int:
        return next(target.target_servings_milli for target in self.strategy_targets if target.strategy is strategy)


class ServingEvidenceV1(ContractModel):
    evidence_id: Identifier
    source_url: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    source_text: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    practical_servings_min_milli: NonNegativeMilli
    practical_servings_max_milli: NonNegativeMilli
    selected_servings_milli: NonNegativeMilli
    confidence: ConfidenceLabel
    observation_count: Annotated[int, Field(strict=True, ge=0, le=1_000_000)]
    reviewed: bool

    @model_validator(mode="after")
    def selected_value_is_in_range(self) -> "ServingEvidenceV1":
        if not self.practical_servings_min_milli <= self.selected_servings_milli <= self.practical_servings_max_milli:
            raise ValueError("selected practical servings must be inside the evidence range")
        return self


class SemanticProvenanceV1(ContractModel):
    source_text: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    source_url: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    status: SemanticFieldStatus
    confidence: ConfidenceLabel
    model: Annotated[str, StringConstraints(min_length=1, max_length=100)] | None
    prompt_version: Annotated[str, StringConstraints(min_length=1, max_length=100)] | None
    source_content_hash: Annotated[str, StringConstraints(min_length=8, max_length=128)]
    enriched_at: AwareDatetime


class MenuItemV1(ContractModel):
    menu_item_id: Identifier
    restaurant_id: Identifier
    name: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    original_text: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    category_code: Annotated[str, StringConstraints(min_length=1, max_length=80, pattern=r"^[a-z0-9_]+$")]
    price_minor: MoneyMinor
    currency: Literal["KRW"] = "KRW"
    sale_unit: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    piece_count: Annotated[int, Field(strict=True, ge=1, le=1_000)] | None
    pizza_diameter_cm_milli: NonNegativeMilli | None
    slice_count: Annotated[int, Field(strict=True, ge=1, le=1_000)] | None
    vegetarian_status: VegetarianStatus
    verified_free_allergens: Annotated[list[ShortCode], Field(max_length=64)]
    allergen_tags: Annotated[list[ShortCode], Field(max_length=64)]
    spice_level: SpiceLevel
    availability: AvailabilityStatus
    serving_evidence: ServingEvidenceV1
    semantic_provenance: SemanticProvenanceV1
    inferred_tags: Annotated[list[ShortCode], Field(max_length=64)]


class RestaurantV1(ContractModel):
    restaurant_id: Identifier
    source_restaurant_id: Identifier
    name: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    branch: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    address: Annotated[str, StringConstraints(min_length=1, max_length=300)]
    latitude: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)] | None
    longitude: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)] | None
    source_url: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    delivery_queries: Annotated[list[str], Field(min_length=1, max_length=50)]
    minimum_order_minor: MoneyMinor
    delivery_fee_minor: MoneyMinor
    service_fee_minor: MoneyMinor
    estimated_delivery_minutes: Annotated[int, Field(strict=True, ge=1, le=600)]
    availability: AvailabilityStatus
    menu_items: Annotated[list[MenuItemV1], Field(min_length=1, max_length=100)]


class RestaurantSnapshotV1(ContractModel):
    schema_name: Literal["restaurant_snapshot"] = "restaurant_snapshot"
    schema_version: Literal["1.0"] = "1.0"
    snapshot_id: Identifier
    source_url: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    crawled_at: AwareDatetime
    parser_version: Identifier
    completeness: CompletenessStatus
    data_mode: DataMode
    reviewed: bool
    warnings: Annotated[list[str], Field(max_length=64)]
    restaurants: Annotated[list[RestaurantV1], Field(min_length=1, max_length=10)]


class CandidateMenuSetV1(ContractModel):
    schema_name: Literal["candidate_menu_set"] = "candidate_menu_set"
    schema_version: Literal["1.0"] = "1.0"
    case_id: Identifier
    profile_revision: Annotated[int, Field(strict=True, ge=1)]
    snapshot_id: Identifier
    freshness: FreshnessStatus
    completeness: CompletenessStatus
    data_mode: DataMode
    restaurants: Annotated[list[RestaurantV1], Field(min_length=1, max_length=10)]
    warnings: Annotated[list[str], Field(max_length=64)]


class NormalizedMenuSetV1(ContractModel):
    schema_name: Literal["normalized_menu_set"] = "normalized_menu_set"
    schema_version: Literal["1.0"] = "1.0"
    case_id: Identifier
    profile_revision: Annotated[int, Field(strict=True, ge=1)]
    candidate_menu_set_id: Identifier
    restaurants: Annotated[list[RestaurantV1], Field(min_length=1, max_length=10)]
    cache_hits: Annotated[int, Field(strict=True, ge=0)]
    model_enrichments: Annotated[int, Field(strict=True, ge=0)]
    warnings: Annotated[list[str], Field(max_length=64)]


class MenuEligibilityV1(ContractModel):
    menu_item_id: Identifier
    eligible_group_ids: Annotated[list[Identifier], Field(max_length=100)]
    excluded_group_ids: Annotated[list[Identifier], Field(max_length=100)]
    hard_exclusion_reasons: Annotated[list[str], Field(max_length=100)]
    preference_penalty_basis_points: Annotated[int, Field(strict=True, ge=0, le=10_000)]


class EligibleRestaurantV1(ContractModel):
    restaurant: RestaurantV1
    eligibility: Annotated[list[MenuEligibilityV1], Field(min_length=1, max_length=100)]


class EligibleMenuSetV1(ContractModel):
    schema_name: Literal["eligible_menu_set"] = "eligible_menu_set"
    schema_version: Literal["1.0"] = "1.0"
    case_id: Identifier
    profile_revision: Annotated[int, Field(strict=True, ge=1)]
    normalized_menu_set_id: Identifier
    restaurants: Annotated[list[EligibleRestaurantV1], Field(min_length=1, max_length=10)]
    excluded_item_count: Annotated[int, Field(strict=True, ge=0)]
    warnings: Annotated[list[str], Field(max_length=64)]


class CombinationLineV1(ContractModel):
    menu_item_id: Identifier
    quantity: Annotated[int, Field(strict=True, ge=1, le=100)]
    unit_servings_milli: NonNegativeMilli
    line_servings_milli: NonNegativeMilli
    unit_price_minor: MoneyMinor
    line_price_minor: MoneyMinor


class PlanValidationV1(ContractModel):
    hard_constraints_passed: bool
    group_coverage_passed: bool
    quantity_passed: bool
    budget_passed: bool
    delivery_passed: bool
    minimum_order_passed: bool
    category_coverage_passed: bool
    issues: Annotated[list[str], Field(max_length=64)]


class OrderCombinationV1(ContractModel):
    combination_id: Identifier
    strategy: PlanStrategy
    restaurant_id: Identifier
    lines: Annotated[list[CombinationLineV1], Field(min_length=1, max_length=20)]
    target_servings_milli: NonNegativeMilli
    total_servings_milli: NonNegativeMilli
    surplus_servings_milli: Annotated[int, Field(strict=True, ge=-10_000_000, le=10_000_000)]
    item_subtotal_minor: MoneyMinor
    fees_minor: MoneyMinor
    total_cost_minor: MoneyMinor
    budget_evaluated_cost_minor: MoneyMinor
    validation: PlanValidationV1


class CombinationSetV1(ContractModel):
    schema_name: Literal["combination_set"] = "combination_set"
    schema_version: Literal["1.0"] = "1.0"
    case_id: Identifier
    profile_revision: Annotated[int, Field(strict=True, ge=1)]
    eligible_menu_set_id: Identifier
    serving_requirement_id: Identifier
    combinations: Annotated[list[OrderCombinationV1], Field(max_length=10_000)]
    evaluated_count: Annotated[int, Field(strict=True, ge=0, le=1_000_000)]
    truncated: bool
    rejection_reasons: Annotated[list[str], Field(max_length=64)]


class MetricScoreV1(ContractModel):
    metric: ShortCode
    score_basis_points: Annotated[int, Field(strict=True, ge=0, le=10_000)]
    weighted_score: Annotated[int, Field(strict=True, ge=0, le=100_000_000)]
    reason: Annotated[str, StringConstraints(min_length=1, max_length=300)]


class ScoredCombinationV1(ContractModel):
    combination: OrderCombinationV1
    total_score: Annotated[int, Field(strict=True, ge=0, le=100_000_000)]
    metrics: Annotated[list[MetricScoreV1], Field(min_length=1, max_length=16)]
    soft_preference_reasons: Annotated[list[str], Field(max_length=64)]


class ScoredCombinationSetV1(ContractModel):
    schema_name: Literal["scored_combination_set"] = "scored_combination_set"
    schema_version: Literal["1.0"] = "1.0"
    case_id: Identifier
    profile_revision: Annotated[int, Field(strict=True, ge=1)]
    combination_set_id: Identifier
    scored_combinations: Annotated[list[ScoredCombinationV1], Field(max_length=10_000)]


class RankedPlanSetV1(ContractModel):
    schema_name: Literal["ranked_plan_set"] = "ranked_plan_set"
    schema_version: Literal["1.0"] = "1.0"
    case_id: Identifier
    profile_revision: Annotated[int, Field(strict=True, ge=1)]
    scored_combination_set_id: Identifier
    plans: Annotated[list[ScoredCombinationV1], Field(min_length=1, max_length=3)]
    recommended_strategy: PlanStrategy
    recommendation_reason: Annotated[str, StringConstraints(min_length=1, max_length=500)]


class GroupAnalysisV1(ContractModel):
    actual_attendance: Annotated[int, Field(strict=True, ge=1, le=100)]
    equivalent_group_servings_milli: NonNegativeMilli
    protected_demand_milli: NonNegativeMilli
    applied_safety_margin_basis_points: Annotated[int, Field(strict=True, ge=0, le=1_500)]
    target_servings_milli: NonNegativeMilli


class ExpectedOutcomeV1(ContractModel):
    shortage_risk: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    leftover_risk: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    expected_leftover_servings_milli: NonNegativeMilli
    confidence: ConfidenceLabel
    uncertainties: Annotated[list[str], Field(max_length=64)]


class AlternativePlanV1(ContractModel):
    plan: ScoredCombinationV1
    restaurant: RestaurantV1


class DisplayPlanV1(ContractModel):
    schema_name: Literal["display_plan"] = "display_plan"
    schema_version: Literal["1.0"] = "1.0"
    case_id: Identifier
    profile_revision: Annotated[int, Field(strict=True, ge=1)]
    status: Literal["plan_ready"] = "plan_ready"
    group_analysis: GroupAnalysisV1
    recommended_plan: ScoredCombinationV1
    alternatives: Annotated[list[AlternativePlanV1], Field(min_length=2, max_length=2)]
    restaurant: RestaurantV1
    snapshot_id: Identifier
    snapshot_crawled_at: AwareDatetime
    snapshot_parser_version: Identifier
    snapshot_completeness: CompletenessStatus
    freshness: FreshnessStatus
    data_mode: DataMode
    expected_outcome: ExpectedOutcomeV1
    calculation_basis: Annotated[list[str], Field(min_length=1, max_length=100)]
    assumptions: Annotated[list[str], Field(max_length=64)]


class PlanningFailureV1(ContractModel):
    schema_name: Literal["planning_failure"] = "planning_failure"
    schema_version: Literal["1.0"] = "1.0"
    case_id: Identifier
    profile_revision: Annotated[int, Field(strict=True, ge=1)]
    status: Literal["no_valid_plan", "data_unavailable", "unsupported", "profile_contract_error"]
    problematic_field: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    received_value: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    reason: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    corrective_action: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    compromises: Annotated[list[str], Field(max_length=10)]


class ToolEventV1(ContractModel):
    event_id: Identifier
    event_type: Literal["tool_call", "tool_result", "tool_error"]
    call_id: Identifier
    trace_id: Identifier
    case_id: Identifier
    profile_revision: Annotated[int, Field(strict=True, ge=1)]
    stage: Annotated[int, Field(strict=True, ge=2, le=13)]
    tool_name: Identifier
    occurred_at: AwareDatetime
    input_artifact_ids: Annotated[list[Identifier], Field(max_length=16)]
    output_artifact_ids: Annotated[list[Identifier], Field(max_length=16)]
    duration_ms: Annotated[int, Field(strict=True, ge=0, le=3_600_000)] | None = None
    error_type: Identifier | None = None
    summary: Annotated[str, StringConstraints(min_length=1, max_length=500)]


class PlannerAgentFinalV1(ContractModel):
    case_id: Identifier
    display_artifact_id: Identifier | None
    failure_artifact_id: Identifier | None
    summary: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    recommendation_explanation: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    tradeoff_explanation: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    uncertainty_explanation: Annotated[str, StringConstraints(min_length=1, max_length=500)]

    @model_validator(mode="after")
    def exactly_one_terminal_artifact(self) -> "PlannerAgentFinalV1":
        if (self.display_artifact_id is None) == (self.failure_artifact_id is None):
            raise ValueError("exactly one display or failure artifact id is required")
        return self


class PresentationToolResultV1(ContractModel):
    artifact: ArtifactResult
    display: DisplayPlanV1


class MealFeedbackV1(ContractModel):
    case_id: Identifier
    actual_attendance: Annotated[int, Field(strict=True, ge=0, le=100)]
    outcome: Literal["enough", "shortage", "leftovers"]
    leftover_servings_milli: NonNegativeMilli
    affected_menu_item_ids: Annotated[list[Identifier], Field(max_length=20)]
    delivered_portions_smaller_than_expected: bool
    note: Annotated[str, StringConstraints(max_length=500)]


class FeedbackAdjustmentV1(ContractModel):
    case_id: Identifier
    previous_demand_multiplier_basis_points: Annotated[int, Field(strict=True, ge=7_500, le=12_500)]
    new_demand_multiplier_basis_points: Annotated[int, Field(strict=True, ge=7_500, le=12_500)]
    menu_serving_multiplier_changes_basis_points: dict[Identifier, Annotated[int, Field(strict=True, ge=7_500, le=12_500)]]
    observation: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    reason: Annotated[str, StringConstraints(min_length=1, max_length=500)]


class RequirementCheckV1(ContractModel):
    requirement_id: Identifier
    kind: HardRequirementKind
    term_namespace: SemanticNamespace
    term_code: ShortCode
    affected_group_ids: Annotated[list[Identifier], Field(min_length=1, max_length=100)]


class PreferenceSignalV1(ContractModel):
    preference_id: Identifier
    polarity: PreferencePolarity
    term_code: ShortCode
    affected_group_ids: Annotated[list[Identifier], Field(max_length=100)]
    weight_basis_points: Annotated[int, Field(strict=True, ge=0, le=10_000)]
