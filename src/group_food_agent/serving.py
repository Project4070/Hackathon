"""G4 intake adapter and deterministic equivalent-serving calculator."""

from __future__ import annotations

import json
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from .contracts import AppetiteBand, MealType, PlanningIntakeV2, RiskPreference
from .planner_models import (
    GroupDemandV1,
    PlanStrategy,
    ServingCalculationInputV1,
    ServingGroupInputV1,
    ServingRequirementV1,
    StrategyTargetV1,
)


APPETITE_ALIASES = {
    AppetiteBand.VERY_LIGHT: "very_low",
    AppetiteBand.LIGHT: "low",
    AppetiteBand.NORMAL: "normal",
    AppetiteBand.LARGE: "high",
    AppetiteBand.VERY_LARGE: "very_high",
}
MEAL_CONTEXT_ALIASES = {
    MealType.BREAKFAST: "breakfast",
    MealType.LUNCH: "lunch",
    MealType.DINNER: "dinner",
    MealType.LATE_NIGHT: "late_night_snack",
    MealType.SNACK: "snack",
}
RISK_TO_STRATEGY = {
    RiskPreference.MINIMIZE_LEFTOVERS: PlanStrategy.LEFTOVER_MINIMIZING,
    RiskPreference.BALANCED: PlanStrategy.BALANCED,
    RiskPreference.MINIMIZE_SHORTAGE: PlanStrategy.SHORTAGE_MINIMIZING,
}


def default_serving_policy_path() -> Path:
    return Path(__file__).resolve().parents[2] / "fixtures" / "policies" / "serving_policy_kr_v1.json"


def load_serving_policy(path: Path | None = None) -> dict[str, Any]:
    policy_path = path or default_serving_policy_path()
    with policy_path.open("r", encoding="utf-8") as handle:
        policy = json.load(handle)
    required = {
        "policy_id",
        "quantity_policy_id",
        "appetite_factors_milli",
        "meal_context_factors_milli",
        "safety_margins_basis_points",
        "per_person_caps_milli",
        "maximum_total_margin_basis_points",
    }
    missing = required - policy.keys()
    if missing:
        raise ValueError(f"serving policy missing keys: {sorted(missing)}")
    if policy["maximum_total_margin_basis_points"] > 1_500:
        raise ValueError("serving policy margin cap exceeds supported maximum")
    return policy


def build_serving_input(
    intake: PlanningIntakeV2,
    *,
    demand_multiplier_basis_points: int = 10_000,
    policy: dict[str, Any] | None = None,
) -> ServingCalculationInputV1:
    """Translate the intake vocabulary without semantic reinterpretation."""

    config = policy or load_serving_policy()
    protected_group_ids = {
        group_id
        for requirement in intake.profile.hard_requirements
        for group_id in requirement.affected_group_ids
    }
    warnings: list[str] = []
    meal_code = MEAL_CONTEXT_ALIASES.get(intake.profile.occasion.meal_type)
    if meal_code is None:
        meal_code = "dinner"
        warnings.append(
            f"unsupported meal type {intake.profile.occasion.meal_type.value!r}; "
            "used neutral dinner factor and retained a warning"
        )

    groups: list[ServingGroupInputV1] = []
    for group in intake.profile.party.groups:
        if group.appetite.band is AppetiteBand.CUSTOM:
            if group.appetite.stated_servings_milli is None:
                raise ValueError(f"custom appetite group {group.group_id} has no stated serving value")
            appetite_code = "custom"
            appetite_factor = group.appetite.stated_servings_milli
        else:
            appetite_code = APPETITE_ALIASES[group.appetite.band]
            appetite_factor = config["appetite_factors_milli"][appetite_code]

        adjustment_codes: list[str] = []
        if group.activity_level.value not in {"none", "unknown"}:
            warnings.append(
                f"group {group.group_id}: activity value {group.activity_level.value!r} is not an "
                "unambiguous serving-policy adjustment; no adjustment applied"
            )
        if group.recent_meal_status.value not in {"not_recent", "unknown"}:
            warnings.append(
                f"group {group.group_id}: recent-meal value {group.recent_meal_status.value!r} lacks "
                "an exact time band; no adjustment applied"
            )

        groups.append(
            ServingGroupInputV1(
                group_id=group.group_id,
                count=group.count,
                appetite_code=appetite_code,
                appetite_factor_milli=appetite_factor,
                meal_context_code=meal_code,
                meal_context_factor_milli=config["meal_context_factors_milli"][meal_code],
                adjustment_codes=adjustment_codes,
                protected=group.group_id in protected_group_ids,
            )
        )

    return ServingCalculationInputV1(
        case_id=intake.case_id,
        profile_revision=intake.profile_revision,
        serving_policy_id=config["policy_id"],
        quantity_policy_id=config["quantity_policy_id"],
        groups=groups,
        strategy=intake.profile.quantity_preference.primary_objective,
        feedback_demand_multiplier_basis_points=demand_multiplier_basis_points,
        warnings=warnings,
    )


def _milli_product(*values: int) -> Decimal:
    result = Decimal(1)
    for value in values:
        result *= Decimal(value) / Decimal(1_000)
    return result * Decimal(1_000)


def calculate_serving_requirement(
    serving_input: ServingCalculationInputV1,
    *,
    policy: dict[str, Any] | None = None,
) -> ServingRequirementV1:
    """Calculate demand using Decimal and emit integer milli-servings."""

    config = policy or load_serving_policy()
    if serving_input.serving_policy_id != config["policy_id"]:
        raise ValueError("serving input references an unknown policy version")

    group_demands: list[GroupDemandV1] = []
    total = 0
    protected_total = 0
    for group in serving_input.groups:
        per_person = _milli_product(
            group.appetite_factor_milli,
            group.meal_context_factor_milli,
            serving_input.feedback_demand_multiplier_basis_points // 10,
        )
        # _milli_product consumes factors on a 1000 scale. Convert the feedback
        # multiplier from basis points (10000 == 1.0) to that scale first.
        cap = Decimal(config["per_person_caps_milli"][group.meal_context_code])
        per_person = min(per_person, cap).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        group_total = (per_person * Decimal(group.count)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        per_person_int = int(per_person)
        group_total_int = int(group_total)
        total += group_total_int
        if group.protected:
            protected_total += group_total_int
        group_demands.append(
            GroupDemandV1(
                group_id=group.group_id,
                participant_count=group.count,
                per_person_servings_milli=per_person_int,
                total_servings_milli=group_total_int,
                protected=group.protected,
                applied_factor_codes=[group.appetite_code, group.meal_context_code],
            )
        )

    targets: list[StrategyTargetV1] = []
    for strategy in PlanStrategy:
        margin = min(
            config["safety_margins_basis_points"][strategy.value],
            config["maximum_total_margin_basis_points"],
        )
        target = (
            Decimal(total) * (Decimal(10_000 + margin) / Decimal(10_000))
        ).quantize(Decimal("1"), rounding=ROUND_CEILING)
        targets.append(
            StrategyTargetV1(
                strategy=strategy,
                safety_margin_basis_points=margin,
                target_servings_milli=int(target),
            )
        )

    return ServingRequirementV1(
        case_id=serving_input.case_id,
        profile_revision=serving_input.profile_revision,
        attendance_count=sum(group.count for group in serving_input.groups),
        equivalent_group_servings_milli=total,
        protected_demand_milli=protected_total,
        group_demands=group_demands,
        strategy_targets=targets,
        serving_policy_id=serving_input.serving_policy_id,
        warnings=serving_input.warnings,
    )
