"""G6 bounded integer search, deterministic validation, ranking, and presentation."""

from __future__ import annotations

from collections import deque
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from hashlib import sha256
from itertools import product

from .contracts import PlanningIntakeV2, RiskPreference
from .planner_contracts import PlannerRuntimePolicyV2, RankingMetric
from .planner_models import (
    AlternativePlanV1,
    CombinationLineV1,
    CombinationSetV1,
    ConfidenceLabel,
    DisplayPlanV1,
    EligibleMenuSetV1,
    ExpectedOutcomeV1,
    GroupAnalysisV1,
    MetricScoreV1,
    OrderCombinationV1,
    PlanStrategy,
    PlanValidationV1,
    RankedPlanSetV1,
    RestaurantSourceV1,
    ScoredCombinationSetV1,
    ScoredCombinationV1,
    ServingRequirementV1,
    SpiceLevel,
)
from .serving import RISK_TO_STRATEGY


MAX_SEARCH_ITEMS_PER_RESTAURANT = 6
MAX_EVALUATIONS_PER_RESTAURANT_STRATEGY = 10_000


def pizza_area_scaled_servings(
    original_diameter_cm_milli: int,
    new_diameter_cm_milli: int,
    original_servings_milli: int,
) -> int:
    """Scale serving capacity by pizza area (diameter squared), never diameter alone."""

    if not 1_000 <= original_diameter_cm_milli <= 100_000:
        raise ValueError("original pizza diameter is outside the supported 1-100 cm range")
    if not 1_000 <= new_diameter_cm_milli <= 100_000:
        raise ValueError("new pizza diameter is outside the supported 1-100 cm range")
    if not 1 <= original_servings_milli <= 100_000:
        raise ValueError("original pizza servings are outside the supported range")
    ratio = Decimal(new_diameter_cm_milli) ** 2 / Decimal(original_diameter_cm_milli) ** 2
    return int(
        (Decimal(original_servings_milli) * ratio).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def _scaled_group_targets(requirement: ServingRequirementV1, target_milli: int) -> dict[str, int]:
    base = Decimal(requirement.equivalent_group_servings_milli)
    return {
        group.group_id: int(
            (Decimal(group.total_servings_milli) * Decimal(target_milli) / base).quantize(
                Decimal("1"), rounding=ROUND_CEILING
            )
        )
        for group in requirement.group_demands
    }


def _allocation_feasible(
    group_targets: dict[str, int],
    item_capacities: dict[str, int],
    eligibility: dict[str, set[str]],
) -> bool:
    """Exact max-flow coverage check for group-to-item capacity allocation."""

    source = "__source__"
    sink = "__sink__"
    capacity: dict[tuple[str, str], int] = {}
    adjacency: dict[str, set[str]] = {}

    def add_edge(left: str, right: str, amount: int) -> None:
        capacity[(left, right)] = amount
        capacity[(right, left)] = 0
        adjacency.setdefault(left, set()).add(right)
        adjacency.setdefault(right, set()).add(left)

    total_required = sum(group_targets.values())
    for group_id, demand in group_targets.items():
        add_edge(source, f"g:{group_id}", demand)
    for item_id, amount in item_capacities.items():
        add_edge(f"i:{item_id}", sink, amount)
        for group_id in eligibility[item_id]:
            if group_id in group_targets:
                add_edge(f"g:{group_id}", f"i:{item_id}", total_required)

    flow = 0
    while True:
        parent: dict[str, str | None] = {source: None}
        queue: deque[str] = deque([source])
        while queue and sink not in parent:
            node = queue.popleft()
            for neighbor in adjacency.get(node, set()):
                if neighbor not in parent and capacity[(node, neighbor)] > 0:
                    parent[neighbor] = node
                    queue.append(neighbor)
        if sink not in parent:
            break
        amount = total_required
        node = sink
        while parent[node] is not None:
            prior = parent[node]
            amount = min(amount, capacity[(prior, node)])
            node = prior
        node = sink
        while parent[node] is not None:
            prior = parent[node]
            capacity[(prior, node)] -= amount
            capacity[(node, prior)] += amount
            node = prior
        flow += amount
    return flow >= total_required


def _selected_unit_servings(base_milli: int, multiplier_basis_points: int) -> int:
    return int(
        (Decimal(base_milli) * Decimal(multiplier_basis_points) / Decimal(10_000)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def generate_budget_combinations(
    intake: PlanningIntakeV2,
    eligible: EligibleMenuSetV1,
    requirement: ServingRequirementV1,
    *,
    eligible_menu_set_id: str,
    serving_requirement_id: str,
    policy: PlannerRuntimePolicyV2,
    menu_serving_multipliers_basis_points: dict[str, int] | None = None,
    retained_limit: int = 2_000,
) -> CombinationSetV1:
    """Search nearby integer quantities and keep only hard-valid combinations."""

    multipliers = menu_serving_multipliers_basis_points or {}
    maximum_budget = intake.profile.budget.maximum_amount_minor
    maximum_total = policy.combination.maximum_total_quantity or 20
    maximum_distinct = policy.combination.maximum_distinct_items or 20
    evaluated = 0
    valid: list[OrderCombinationV1] = []
    rejection_counts: dict[str, int] = {}
    search_was_truncated = False

    for eligible_restaurant in eligible.restaurants:
        restaurant = eligible_restaurant.restaurant
        rows = {row.menu_item_id: row for row in eligible_restaurant.eligibility}
        all_items = [item for item in restaurant.menu_items if rows[item.menu_item_id].eligible_group_ids]
        # Keep the search dimensionality bounded, ordered by broad eligibility,
        # lower preference penalty, and price per source-backed serving.
        ordered = sorted(
            all_items,
            key=lambda item: (
                -len(rows[item.menu_item_id].eligible_group_ids),
                rows[item.menu_item_id].preference_penalty_basis_points,
                Decimal(item.price_minor)
                / Decimal(max(1, item.serving_evidence.selected_servings_milli)),
                item.menu_item_id,
            ),
        )
        items = list(ordered)
        if len(items) > MAX_SEARCH_ITEMS_PER_RESTAURANT:
            items = items[:MAX_SEARCH_ITEMS_PER_RESTAURANT]
            search_was_truncated = True
            rejection_counts["candidate_item_bound_applied"] = (
                rejection_counts.get("candidate_item_bound_applied", 0) + 1
            )
        if not items:
            rejection_counts["no_eligible_items"] = rejection_counts.get("no_eligible_items", 0) + 1
            continue
        unit_servings = {
            item.menu_item_id: _selected_unit_servings(
                item.serving_evidence.selected_servings_milli,
                multipliers.get(item.menu_item_id, 10_000),
            )
            for item in items
        }
        minimum_serving = max(1, min(unit_servings.values()))

        for strategy in PlanStrategy:
            target = requirement.target_for(strategy)
            group_targets = _scaled_group_targets(requirement, target)
            strategy_max_units = min(
                maximum_total,
                max(1, int((Decimal(target) / Decimal(minimum_serving)).to_integral_value(rounding=ROUND_CEILING)) + 2),
            )
            local_evaluated = 0
            for quantities in product(range(strategy_max_units + 1), repeat=len(items)):
                if local_evaluated >= MAX_EVALUATIONS_PER_RESTAURANT_STRATEGY:
                    search_was_truncated = True
                    rejection_counts["combination_evaluation_bound_applied"] = (
                        rejection_counts.get("combination_evaluation_bound_applied", 0) + 1
                    )
                    break
                if not any(quantities):
                    continue
                local_evaluated += 1
                evaluated += 1
                total_quantity = sum(quantities)
                distinct = sum(1 for quantity in quantities if quantity)
                if total_quantity > maximum_total or distinct > maximum_distinct:
                    continue
                capacities = {
                    item.menu_item_id: quantity * unit_servings[item.menu_item_id]
                    for item, quantity in zip(items, quantities, strict=True)
                    if quantity
                }
                total_servings = sum(capacities.values())
                if total_servings < sum(group_targets.values()):
                    continue
                item_eligibility = {
                    item_id: set(rows[item_id].eligible_group_ids) for item_id in capacities
                }
                group_pass = _allocation_feasible(group_targets, capacities, item_eligibility)
                if not group_pass:
                    continue
                subtotal = sum(
                    item.price_minor * quantity
                    for item, quantity in zip(items, quantities, strict=True)
                )
                fees = restaurant.delivery_fee_minor + restaurant.service_fee_minor
                total_cost = subtotal + fees
                cost_scope = intake.profile.budget.cost_scope
                budget_evaluated_cost = (
                    (subtotal if cost_scope.include_menu_price else 0)
                    + (restaurant.delivery_fee_minor if cost_scope.include_delivery_fee else 0)
                    + (restaurant.service_fee_minor if cost_scope.include_service_fee else 0)
                )
                minimum_pass = subtotal >= restaurant.minimum_order_minor
                budget_pass = maximum_budget is None or budget_evaluated_cost <= maximum_budget
                delivery_pass = restaurant.availability.value == "available"
                hard_pass = group_pass and minimum_pass and budget_pass and delivery_pass
                if not hard_pass:
                    reason = "budget" if not budget_pass else "minimum_or_delivery"
                    rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
                    continue
                lines = [
                    CombinationLineV1(
                        menu_item_id=item.menu_item_id,
                        quantity=quantity,
                        unit_servings_milli=unit_servings[item.menu_item_id],
                        line_servings_milli=quantity * unit_servings[item.menu_item_id],
                        unit_price_minor=item.price_minor,
                        line_price_minor=quantity * item.price_minor,
                    )
                    for item, quantity in zip(items, quantities, strict=True)
                    if quantity
                ]
                quantity_signature = "-".join(f"{line.menu_item_id}.{line.quantity}" for line in lines)
                combination_digest = sha256(
                    f"{restaurant.restaurant_id}|{strategy.value}|{quantity_signature}".encode("utf-8")
                ).hexdigest()[:20]
                valid.append(
                    OrderCombinationV1(
                        combination_id=f"combo:{combination_digest}",
                        strategy=strategy,
                        restaurant_id=restaurant.restaurant_id,
                        lines=lines,
                        target_servings_milli=target,
                        total_servings_milli=total_servings,
                        surplus_servings_milli=total_servings - target,
                        item_subtotal_minor=subtotal,
                        fees_minor=fees,
                        total_cost_minor=total_cost,
                        budget_evaluated_cost_minor=budget_evaluated_cost,
                        validation=PlanValidationV1(
                            hard_constraints_passed=True,
                            group_coverage_passed=True,
                            quantity_passed=True,
                            budget_passed=True,
                            delivery_passed=True,
                            minimum_order_passed=True,
                            category_coverage_passed=True,
                            issues=[],
                        ),
                    )
                )

    valid.sort(
        key=lambda combination: (
            combination.surplus_servings_milli,
            combination.total_cost_minor,
            len(combination.lines),
            combination.combination_id,
        )
    )
    truncated = search_was_truncated or len(valid) > retained_limit
    valid = valid[:retained_limit]
    rejection_reasons = [f"{reason}:{count}" for reason, count in sorted(rejection_counts.items())]
    if not valid and not rejection_reasons:
        rejection_reasons = ["no integer combination satisfied eligibility and quantity constraints"]
    return CombinationSetV1(
        case_id=intake.case_id,
        profile_revision=intake.profile_revision,
        eligible_menu_set_id=eligible_menu_set_id,
        serving_requirement_id=serving_requirement_id,
        combinations=valid,
        evaluated_count=evaluated,
        truncated=truncated,
        rejection_reasons=rejection_reasons,
    )


def _metric_scores(
    combination: OrderCombinationV1,
    intake: PlanningIntakeV2,
    policy: PlannerRuntimePolicyV2,
) -> list[MetricScoreV1]:
    objective_weights = {objective.metric: objective.weight_basis_points for objective in policy.ranking.objectives}
    target = max(1, combination.target_servings_milli)
    serving_fit = max(
        0,
        10_000 - min(10_000, combination.surplus_servings_milli * 10_000 // target),
    )
    categories = len(combination.lines)
    total = max(1, combination.total_servings_milli)
    dominance = max(line.line_servings_milli for line in combination.lines) * 10_000 // total
    diversity = 10_000 if categories >= 2 else 7_500
    if policy.ranking.diversity.avoid_single_item_dominance and dominance > 7_500:
        diversity = max(0, diversity - policy.ranking.diversity.duplicate_penalty_basis_points)
    maximum_budget = intake.profile.budget.maximum_amount_minor
    budget_efficiency = (
        5_000
        if maximum_budget is None
        else max(0, min(10_000, (maximum_budget - combination.budget_evaluated_cost_minor) * 10_000 // max(1, maximum_budget)))
    )
    values = {
        RankingMetric.CONSTRAINT_SATISFACTION: (10_000, "all deterministic hard constraints passed"),
        RankingMetric.SERVING_FIT: (serving_fit, "score decreases with avoidable whole-unit surplus"),
        RankingMetric.MENU_DIVERSITY: (diversity, "item concentration evaluated without category gating"),
        RankingMetric.BUDGET_EFFICIENCY: (budget_efficiency, "remaining room under the validated budget ceiling"),
        RankingMetric.ORDER_SIMPLICITY: (max(0, 10_000 - (len(combination.lines) - 1) * 1_000), "fewer distinct lines are simpler"),
        RankingMetric.DELIVERY_FIT: (10_000, "delivery constraint passed"),
    }
    return [
        MetricScoreV1(
            metric=metric.value,
            score_basis_points=values[metric][0],
            weighted_score=values[metric][0] * weight,
            reason=values[metric][1],
        )
        for metric, weight in objective_weights.items()
    ]


def score_soft_preferences(
    intake: PlanningIntakeV2,
    combinations: CombinationSetV1,
    eligible: EligibleMenuSetV1,
    *,
    combination_set_id: str,
    policy: PlannerRuntimePolicyV2,
) -> ScoredCombinationSetV1:
    penalty_by_item = {
        row.menu_item_id: row.preference_penalty_basis_points
        for restaurant in eligible.restaurants
        for row in restaurant.eligibility
    }
    restaurant_name_by_id = {
        restaurant.restaurant.restaurant_id: restaurant.restaurant.name
        for restaurant in eligible.restaurants
    }
    preferred_restaurant_names = {
        name.casefold() for name in intake.profile.restaurant_preferences.preferred_names
    }
    scored: list[ScoredCombinationV1] = []
    for combination in combinations.combinations:
        metrics = _metric_scores(combination, intake, policy)
        quantity = sum(line.quantity for line in combination.lines)
        average_penalty = sum(
            penalty_by_item[line.menu_item_id] * line.quantity for line in combination.lines
        ) // max(1, quantity)
        restaurant_name = restaurant_name_by_id[combination.restaurant_id]
        restaurant_bonus = (
            1_000 if restaurant_name.casefold() in preferred_restaurant_names else 0
        )
        total_score = max(
            0,
            min(
                100_000_000,
                sum(metric.weighted_score for metric in metrics)
                - average_penalty * 1_000
                + restaurant_bonus * 1_000,
            ),
        )
        reasons = []
        if average_penalty:
            reasons.append(f"semantic preference penalty: {average_penalty} basis points")
        else:
            reasons.append("no structured soft-preference conflict found")
        if restaurant_bonus:
            reasons.append(f"preferred restaurant match: {restaurant_name}")
        scored.append(
            ScoredCombinationV1(
                combination=combination,
                total_score=total_score,
                metrics=metrics,
                soft_preference_reasons=reasons,
            )
        )
    return ScoredCombinationSetV1(
        case_id=combinations.case_id,
        profile_revision=combinations.profile_revision,
        combination_set_id=combination_set_id,
        scored_combinations=scored,
    )


def rank_and_validate_plans(
    intake: PlanningIntakeV2,
    scored: ScoredCombinationSetV1,
    *,
    scored_combination_set_id: str,
) -> RankedPlanSetV1:
    plans: list[ScoredCombinationV1] = []
    for strategy in PlanStrategy:
        candidates = [
            candidate
            for candidate in scored.scored_combinations
            if candidate.combination.strategy is strategy
            and candidate.combination.validation.hard_constraints_passed
        ]
        if not candidates:
            raise LookupError(f"no valid {strategy.value} plan exists")
        candidates.sort(
            key=lambda candidate: (
                -candidate.total_score,
                candidate.combination.surplus_servings_milli,
                candidate.combination.total_cost_minor,
                candidate.combination.combination_id,
            )
        )
        plans.append(candidates[0])
    recommended = RISK_TO_STRATEGY[intake.profile.quantity_preference.primary_objective]
    reason = (
        f"Selected {recommended.value} because the validated organizer objective is "
        f"{intake.profile.quantity_preference.primary_objective.value}; all three alternatives pass hard constraints."
    )
    return RankedPlanSetV1(
        case_id=intake.case_id,
        profile_revision=intake.profile_revision,
        scored_combination_set_id=scored_combination_set_id,
        plans=plans,
        recommended_strategy=recommended,
        recommendation_reason=reason,
    )


def get_plan_for_presentation(
    intake: PlanningIntakeV2,
    requirement: ServingRequirementV1,
    ranked: RankedPlanSetV1,
    source: RestaurantSourceV1,
    *,
    freshness,
    data_mode,
    source_warnings: list[str] | None = None,
) -> DisplayPlanV1:
    recommended = next(
        plan for plan in ranked.plans if plan.combination.strategy is ranked.recommended_strategy
    )
    alternative_plans = [plan for plan in ranked.plans if plan is not recommended]
    alternatives = [
        AlternativePlanV1(
            plan=plan,
            restaurant=next(
                candidate
                for candidate in source.restaurants
                if candidate.restaurant_id == plan.combination.restaurant_id
            ),
        )
        for plan in alternative_plans
    ]
    restaurant = next(
        restaurant
        for restaurant in source.restaurants
        if restaurant.restaurant_id == recommended.combination.restaurant_id
    )
    target_row = next(
        target for target in requirement.strategy_targets if target.strategy is ranked.recommended_strategy
    )
    selected_item_ids = {line.menu_item_id for line in recommended.combination.lines}
    confidence_order = {ConfidenceLabel.HIGH: 2, ConfidenceLabel.MEDIUM: 1, ConfidenceLabel.LOW: 0}
    confidence = min(
        (
            item.serving_evidence.confidence
            for item in restaurant.menu_items
            if item.menu_item_id in selected_item_ids
        ),
        key=lambda label: confidence_order[label],
    )
    uncertainties = list(source_warnings if source_warnings is not None else source.warnings)
    if confidence is not ConfidenceLabel.HIGH:
        uncertainties.append("at least one selected item uses non-high-confidence practical serving evidence")
    risk_labels = {
        PlanStrategy.LEFTOVER_MINIMIZING: ("higher", "lower"),
        PlanStrategy.BALANCED: ("moderate", "moderate"),
        PlanStrategy.SHORTAGE_MINIMIZING: ("lower", "higher"),
    }
    shortage_risk, leftover_risk = risk_labels[ranked.recommended_strategy]
    calculation_basis = [
        f"{group.group_id}: {group.participant_count} people × {group.per_person_servings_milli / 1000:.3f} servings"
        for group in requirement.group_demands
    ]
    calculation_basis.extend(
        [
            f"equivalent group demand: {requirement.equivalent_group_servings_milli / 1000:.3f} servings",
            f"restaurant-specific whole-unit target: {recommended.combination.target_servings_milli / 1000:.3f} servings",
            ranked.recommendation_reason,
        ]
    )
    return DisplayPlanV1(
        case_id=intake.case_id,
        profile_revision=intake.profile_revision,
        group_analysis=GroupAnalysisV1(
            actual_attendance=requirement.attendance_count,
            equivalent_group_servings_milli=requirement.equivalent_group_servings_milli,
            protected_demand_milli=requirement.protected_demand_milli,
            applied_safety_margin_basis_points=target_row.safety_margin_basis_points,
            target_servings_milli=target_row.target_servings_milli,
        ),
        recommended_plan=recommended,
        alternatives=alternatives,
        restaurant=restaurant,
        source_id=source.source_id,
        source_observed_at=source.crawled_at,
        source_parser_version=source.parser_version,
        source_completeness=source.completeness,
        freshness=freshness,
        data_mode=data_mode,
        expected_outcome=ExpectedOutcomeV1(
            shortage_risk=shortage_risk,
            leftover_risk=leftover_risk,
            expected_leftover_servings_milli=max(0, recommended.combination.surplus_servings_milli),
            confidence=confidence,
            uncertainties=uncertainties,
        ),
        calculation_basis=calculation_basis,
        assumptions=[assumption.reason for assumption in intake.validation_receipt.assumptions],
    )
