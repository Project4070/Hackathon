"""Strict, versioned Steps 1–4 contracts.

The language model may produce only :class:`MealRequestCandidateV2`.  Ready and
non-ready planning-intake outcomes are constructed by deterministic code.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, TypeAlias

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)


Identifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"),
]
FieldPath = Annotated[
    str,
    StringConstraints(min_length=1, max_length=256, pattern=r"^/.*"),
]
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=500)]
DisplayText = Annotated[str, StringConstraints(min_length=1, max_length=160)]
SafeInt = Annotated[int, Field(strict=True, ge=-1_000_000_000_000_000, le=1_000_000_000_000_000)]
SafeCount = Annotated[int, Field(strict=True, ge=-1_000_000, le=1_000_000)]
Confidence = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
Coordinate = Annotated[float, Field(allow_inf_nan=False)]


class ContractModel(BaseModel):
    """Base model shared by all external boundary objects."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
        allow_inf_nan=False,
    )


class LocaleCode(StrEnum):
    KO = "ko"
    EN = "en"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class MealType(StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    LATE_NIGHT = "late_night"
    SNACK = "snack"
    OTHER = "other"


class ServiceStyle(StrEnum):
    FULL_MEAL = "full_meal"
    LIGHT_MEAL = "light_meal"
    SNACK = "snack"
    SHARED_TASTING = "shared_tasting"
    OTHER = "other"


class ActivityContext(StrEnum):
    ORDINARY = "ordinary"
    CLUB_MEAL = "club_meal"
    MEETING = "meeting"
    WORKSHOP = "workshop"
    PARTY = "party"
    SPORTS_EVENT = "sports_event"
    SCHOOL_EVENT = "school_event"
    OTHER = "other"


class FoodRole(StrEnum):
    PRIMARY_MEAL = "primary_meal"
    SUPPLEMENTARY_MEAL = "supplementary_meal"
    SNACK = "snack"
    TASTING = "tasting"
    OTHER = "other"


class LeftoverStorage(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class AttendanceStatus(StrEnum):
    CONFIRMED = "confirmed"
    EXPECTED = "expected"
    UNCERTAIN = "uncertain"
    LATE = "late"


class AppetiteBand(StrEnum):
    VERY_LIGHT = "very_light"
    LIGHT = "light"
    NORMAL = "normal"
    LARGE = "large"
    VERY_LARGE = "very_large"
    CUSTOM = "custom"


class ActivityLevel(StrEnum):
    NONE = "none"
    LIGHT = "light"
    MODERATE = "moderate"
    HEAVY = "heavy"
    UNKNOWN = "unknown"


class RecentMealStatus(StrEnum):
    NOT_RECENT = "not_recent"
    LIGHT_MEAL_RECENTLY = "light_meal_recently"
    FULL_MEAL_RECENTLY = "full_meal_recently"
    UNKNOWN = "unknown"


class LocationSource(StrEnum):
    USER_TEXT = "user_text"
    BROWSER_GEOLOCATION = "browser_geolocation"
    REQUEST_CONTEXT = "request_context"
    APPLICATION_DEFAULT = "application_default"


class CategorySelection(StrEnum):
    INCLUDE_ALL = "include_all"
    ANY_OF = "any_of"
    PREFER_ALL = "prefer_all"


class RestaurantMixing(StrEnum):
    SINGLE_RESTAURANT_REQUIRED = "single_restaurant_required"
    SINGLE_RESTAURANT_PREFERRED = "single_restaurant_preferred"
    MULTIPLE_ALLOWED = "multiple_allowed"
    UNSPECIFIED = "unspecified"


class HardRequirementKind(StrEnum):
    ALLERGY = "allergy"
    DIET = "diet"
    FOOD_EXCLUSION = "food_exclusion"
    RELIGIOUS_RULE = "religious_rule"
    SPICE_LIMIT = "spice_limit"


class PreferenceTargetKind(StrEnum):
    FOOD_CATEGORY = "food_category"
    DISH = "dish"
    INGREDIENT = "ingredient"
    FLAVOR = "flavor"
    TEXTURE = "texture"
    SPICE = "spice"
    RESTAURANT = "restaurant"
    VARIETY = "variety"
    OTHER = "other"


class PreferencePolarity(StrEnum):
    PREFER = "prefer"
    AVOID = "avoid"


class PreferenceStrength(StrEnum):
    WEAK = "weak"
    NORMAL = "normal"
    STRONG = "strong"


class BudgetIntentType(StrEnum):
    NO_BUDGET = "no_budget"
    HARD_MAXIMUM = "hard_maximum"
    APPROXIMATE_TARGET = "approximate_target"


class ResolvedBudgetType(StrEnum):
    NO_BUDGET = "no_budget"
    HARD_MAXIMUM = "hard_maximum"
    APPROXIMATE_TARGET = "approximate_target"


class BudgetMaximumSource(StrEnum):
    NONE = "none"
    EXPLICIT = "explicit"
    POLICY_TOLERANCE = "policy_tolerance"
    # TEMPORARY HACKATHON DEFAULT: this source is replaceable/removable once
    # the product owner decides how an omitted budget should behave.
    POLICY_DEFAULT = "policy_default"


class RiskPreference(StrEnum):
    MINIMIZE_LEFTOVERS = "minimize_leftovers"
    BALANCED = "balanced"
    MINIMIZE_SHORTAGE = "minimize_shortage"


class ToleranceLevel(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class RestrictionDisclosureStatus(StrEnum):
    REPORTED = "reported"
    NONE_REPORTED = "none_reported"
    NOT_PROVIDED = "not_provided"


class UnresolvedIssueKind(StrEnum):
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    CONFLICTING = "conflicting"
    UNSUPPORTED = "unsupported"


class EvidenceStatus(StrEnum):
    EXPLICIT = "explicit"
    INFERRED = "inferred"
    DEFAULTED = "defaulted"
    CONFLICTED = "conflicted"


class IssueSeverity(StrEnum):
    WARNING = "warning"
    BLOCKING = "blocking"
    FATAL = "fatal"


class SemanticNamespace(StrEnum):
    ALLERGEN = "allergen"
    DIET = "diet"
    INGREDIENT = "ingredient"
    FOOD_CATEGORY = "food_category"
    SPICE = "spice"
    DISH = "dish"
    FLAVOR = "flavor"
    RESTAURANT_FEATURE = "restaurant_feature"
    OTHER = "other"


class OccasionCandidateV2(ContractModel):
    meal_type: MealType
    service_style: ServiceStyle
    activity_context: ActivityContext
    food_role: FoodRole
    leftover_storage: LeftoverStorage
    scheduled_at: AwareDatetime | None
    duration_minutes: Annotated[int, Field(strict=True, gt=0, le=10_080)] | None


class AppetiteProfileV2(ContractModel):
    band: AppetiteBand
    stated_servings_milli: Annotated[int, Field(strict=True, ge=0, le=10_000)] | None


class ParticipantGroupV2(ContractModel):
    group_id: Identifier
    display_label: DisplayText | None
    count: SafeCount
    attendance_status: AttendanceStatus
    appetite: AppetiteProfileV2
    activity_level: ActivityLevel
    recent_meal_status: RecentMealStatus


class PartyCandidateV2(ContractModel):
    total_count: SafeCount
    groups: Annotated[list[ParticipantGroupV2], Field(max_length=100)]


class LocationHintV2(ContractModel):
    source: LocationSource
    query: Annotated[str, StringConstraints(min_length=1, max_length=300)] | None
    latitude: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)] | None
    longitude: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)] | None

    @model_validator(mode="after")
    def coordinates_are_a_pair(self) -> LocationHintV2:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must both be present or both be null")
        return self


class SemanticTermV2(ContractModel):
    namespace: SemanticNamespace
    code: Annotated[str, StringConstraints(min_length=1, max_length=80, pattern=r"^[a-z0-9_]+$")]
    label: DisplayText


class FoodScopeV2(ContractModel):
    requested_categories: Annotated[list[SemanticTermV2], Field(max_length=16)]
    category_selection: CategorySelection
    excluded_categories: Annotated[list[SemanticTermV2], Field(max_length=16)]
    restaurant_mixing: RestaurantMixing


class HardRequirementV2(ContractModel):
    requirement_id: Identifier
    kind: HardRequirementKind
    affected_group_ids: Annotated[list[Identifier], Field(min_length=1, max_length=100)]
    terms: Annotated[list[SemanticTermV2], Field(min_length=1, max_length=32)]
    source_text: ShortText


class PreferenceV2(ContractModel):
    preference_id: Identifier
    target_kind: PreferenceTargetKind
    polarity: PreferencePolarity
    strength: PreferenceStrength
    affected_group_ids: Annotated[list[Identifier], Field(max_length=100)]
    terms: Annotated[list[SemanticTermV2], Field(max_length=32)]
    source_text: ShortText


class CostScopeCandidateV2(ContractModel):
    include_menu_price: bool | None
    include_delivery_fee: bool | None
    include_service_fee: bool | None
    include_discount: bool | None


class BudgetIntentV2(ContractModel):
    budget_type: BudgetIntentType
    currency: Literal["KRW"] | None
    target_amount_minor: SafeInt | None
    explicit_maximum_amount_minor: SafeInt | None
    cost_scope: CostScopeCandidateV2
    source_text: ShortText | None


class QuantityPreferenceCandidateV2(ContractModel):
    primary_objective: RiskPreference | None
    shortage_tolerance: ToleranceLevel | None
    leftover_tolerance: ToleranceLevel | None


class RestaurantPreferencesV2(ContractModel):
    preferred_names: Annotated[list[DisplayText], Field(max_length=20)]
    excluded_names: Annotated[list[DisplayText], Field(max_length=20)]


class RestrictionDisclosureV2(ContractModel):
    status: RestrictionDisclosureStatus


class EvidenceV2(ContractModel):
    evidence_id: Identifier
    field_path: FieldPath
    source_text: ShortText | None
    status: EvidenceStatus
    confidence: Confidence
    start_offset: Annotated[int, Field(strict=True, ge=0, le=5_000)] | None
    end_offset: Annotated[int, Field(strict=True, ge=0, le=5_000)] | None
    note: ShortText | None

    @model_validator(mode="after")
    def valid_offsets(self) -> EvidenceV2:
        if (self.start_offset is None) != (self.end_offset is None):
            raise ValueError("start_offset and end_offset must both be present or both be null")
        if self.start_offset is not None and self.end_offset <= self.start_offset:
            raise ValueError("end_offset must be greater than start_offset")
        if self.status is EvidenceStatus.DEFAULTED and self.source_text is not None:
            raise ValueError("defaulted evidence cannot claim user source text")
        if self.status in {EvidenceStatus.EXPLICIT, EvidenceStatus.CONFLICTED} and self.source_text is None:
            raise ValueError("explicit or conflicted evidence requires source_text")
        return self


class UnresolvedIssueV2(ContractModel):
    issue_id: Identifier
    kind: UnresolvedIssueKind
    field_path: FieldPath | None
    message: ShortText
    source_text: ShortText | None


class MealRequestCandidateV2(ContractModel):
    """The only model-owned structured output."""

    locale: LocaleCode
    occasion: OccasionCandidateV2
    party: PartyCandidateV2
    location_hint: LocationHintV2 | None
    food_scope: FoodScopeV2
    hard_requirements: Annotated[list[HardRequirementV2], Field(max_length=100)]
    preferences: Annotated[list[PreferenceV2], Field(max_length=100)]
    budget_intent: BudgetIntentV2
    quantity_preference: QuantityPreferenceCandidateV2
    restaurant_preferences: RestaurantPreferencesV2
    restriction_disclosure: RestrictionDisclosureV2
    context_notes: Annotated[list[ShortText], Field(max_length=32)]
    evidence: Annotated[list[EvidenceV2], Field(max_length=256)]
    unresolved_issues: Annotated[list[UnresolvedIssueV2], Field(max_length=64)]


class LocationRequirementV2(ContractModel):
    delivery_required: bool
    source: LocationSource
    query: Annotated[str, StringConstraints(min_length=1, max_length=300)] | None
    latitude: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)] | None
    longitude: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)] | None

    @model_validator(mode="after")
    def usable_location(self) -> LocationRequirementV2:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must both be present or both be null")
        if self.delivery_required and self.query is None and self.latitude is None:
            raise ValueError("delivery-required requests need a query or coordinates")
        return self


class CostScopeV2(ContractModel):
    include_menu_price: bool
    include_delivery_fee: bool
    include_service_fee: bool
    include_discount: bool


class ResolvedBudgetV2(ContractModel):
    budget_type: ResolvedBudgetType
    currency: Literal["KRW"] | None
    target_amount_minor: Annotated[int, Field(strict=True, ge=0)] | None
    maximum_amount_minor: Annotated[int, Field(strict=True, ge=0)] | None
    maximum_source: BudgetMaximumSource
    cost_scope: CostScopeV2

    @model_validator(mode="after")
    def consistent_budget(self) -> ResolvedBudgetV2:
        if self.budget_type is ResolvedBudgetType.NO_BUDGET:
            if (
                self.currency is not None
                or self.target_amount_minor is not None
                or self.maximum_amount_minor is not None
            ):
                raise ValueError("no_budget cannot contain currency or amounts")
            if self.maximum_source is not BudgetMaximumSource.NONE:
                raise ValueError("no_budget requires maximum_source=none")
        elif self.budget_type is ResolvedBudgetType.HARD_MAXIMUM:
            if self.currency != "KRW" or self.maximum_amount_minor is None:
                raise ValueError("hard_maximum requires KRW and a maximum")
            if self.maximum_source not in {
                BudgetMaximumSource.EXPLICIT,
                BudgetMaximumSource.POLICY_DEFAULT,
            }:
                raise ValueError("hard_maximum requires maximum_source=explicit or policy_default")
        else:
            if self.currency != "KRW" or self.target_amount_minor is None:
                raise ValueError("approximate_target requires KRW and a target")
            if self.maximum_amount_minor is None:
                raise ValueError("approximate_target requires a resolved maximum")
            if self.maximum_source is BudgetMaximumSource.NONE:
                raise ValueError("approximate_target requires a maximum source")
        return self


class QuantityPreferenceV2(ContractModel):
    primary_objective: RiskPreference
    shortage_tolerance: ToleranceLevel
    leftover_tolerance: ToleranceLevel


class ContractIssueV2(ContractModel):
    code: Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")]
    severity: IssueSeverity
    field_path: FieldPath | None
    message: ShortText
    evidence_ids: Annotated[list[Identifier], Field(max_length=64)]


class AssumptionV2(ContractModel):
    code: Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")]
    field_path: FieldPath
    applied_value: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    reason: ShortText
    evidence_ids: Annotated[list[Identifier], Field(max_length=64)]


class ValidationReceiptV2(ContractModel):
    validator_version: Annotated[str, StringConstraints(min_length=1, max_length=50)]
    blocking_issues: Annotated[list[ContractIssueV2], Field(max_length=64)]
    warnings: Annotated[list[ContractIssueV2], Field(max_length=64)]
    assumptions: Annotated[list[AssumptionV2], Field(max_length=64)]
    checked_invariants: Annotated[list[str], Field(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def ready_receipt_has_no_blockers(self) -> ValidationReceiptV2:
        if self.blocking_issues:
            raise ValueError("a ready validation receipt cannot contain blocking issues")
        return self


class ValidatedMealProfileV2(ContractModel):
    locale: LocaleCode
    occasion: OccasionCandidateV2
    party: PartyCandidateV2
    location_requirement: LocationRequirementV2
    food_scope: FoodScopeV2
    hard_requirements: list[HardRequirementV2]
    preferences: list[PreferenceV2]
    budget: ResolvedBudgetV2
    quantity_preference: QuantityPreferenceV2
    restaurant_preferences: RestaurantPreferencesV2
    restriction_disclosure: RestrictionDisclosureV2
    context_notes: list[ShortText]
    evidence: list[EvidenceV2]


class PlanningIntakeV2(ContractModel):
    schema_name: Literal["planning_intake"] = "planning_intake"
    schema_version: Literal["2.0"] = "2.0"
    vocabulary_version: Literal["1.0"] = "1.0"
    status: Literal["ready_for_planning"] = "ready_for_planning"
    request_id: Identifier
    case_id: Identifier
    profile_revision: Annotated[int, Field(strict=True, ge=1)]
    validated_at: AwareDatetime
    profile: ValidatedMealProfileV2
    validation_receipt: ValidationReceiptV2

    @model_validator(mode="after")
    def enforce_ready_invariants(self) -> PlanningIntakeV2:
        party = self.profile.party
        if not party.groups or any(group.count <= 0 for group in party.groups):
            raise ValueError("ready intake requires non-empty positive-count groups")
        if sum(group.count for group in party.groups) != party.total_count:
            raise ValueError("participant group counts must equal total_count")
        if not 1 <= party.total_count <= 100:
            raise ValueError("total_count is outside the supported range")
        if self.profile.food_scope.restaurant_mixing is RestaurantMixing.UNSPECIFIED:
            raise ValueError("restaurant_mixing must be resolved")
        return self


class ClarificationRequiredV2(ContractModel):
    schema_name: Literal["planning_intake"] = "planning_intake"
    schema_version: Literal["2.0"] = "2.0"
    vocabulary_version: Literal["1.0"] = "1.0"
    status: Literal["clarification_required"] = "clarification_required"
    request_id: Identifier
    case_id: Identifier
    profile_revision: Annotated[int, Field(strict=True, ge=1)]
    issues: Annotated[list[ContractIssueV2], Field(min_length=1, max_length=64)]
    questions: Annotated[list[ShortText], Field(min_length=1, max_length=3)]


class RequestRejectedV2(ContractModel):
    schema_name: Literal["planning_intake"] = "planning_intake"
    schema_version: Literal["2.0"] = "2.0"
    vocabulary_version: Literal["1.0"] = "1.0"
    status: Literal["request_rejected"] = "request_rejected"
    request_id: Identifier
    case_id: Identifier
    reason_code: Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")]
    issues: Annotated[list[ContractIssueV2], Field(min_length=1, max_length=64)]


PlanningBoundaryOutcomeV2: TypeAlias = Annotated[
    PlanningIntakeV2 | ClarificationRequiredV2 | RequestRejectedV2,
    Field(discriminator="status"),
]


def utc_now() -> datetime:
    """Return an aware UTC timestamp; exposed for dependency injection in tests."""

    from datetime import UTC

    return datetime.now(UTC)
