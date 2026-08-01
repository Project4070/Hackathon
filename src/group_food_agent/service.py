"""Application service that exposes each observable planner stage as a narrow tool."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import Callable

from .contracts import (
    BudgetMaximumSource,
    PlanningIntakeV2,
    ResolvedBudgetType,
    ResolvedBudgetV2,
    ValidatedMealProfileV2,
)
from .planner_contracts import PlanningJobV2
from .planner_models import (
    ArtifactResult,
    CandidateMenuSetV1,
    CombinationSetV1,
    DisplayPlanV1,
    EligibleMenuSetV1,
    FeedbackAdjustmentV1,
    MealFeedbackV1,
    NormalizedMenuSetV1,
    PlanningFailureV1,
    PlannerAgentFinalV1,
    RankedPlanSetV1,
    RestaurantSourceV1,
    ScoredCombinationSetV1,
    ServingCalculationInputV1,
    ServingRequirementV1,
    ToolEventV1,
)
from .planning import (
    generate_budget_combinations,
    get_plan_for_presentation,
    rank_and_validate_plans,
    score_soft_preferences,
)
from .restaurant import (
    apply_hard_eligibility,
    enrich_menu_semantics,
    load_restaurant_source,
    search_menu_candidates,
)
from .serving import build_serving_input, calculate_serving_requirement
from .stores import (
    ArtifactStore,
    Clock,
    EvidenceStore,
    PlanningCaseStore,
    PolicyRegistry,
    ToolEventStore,
    system_clock,
)
from .tracing import JsonlTraceWriter, deterministic_tool_span


@dataclass(frozen=True)
class PlanRunResult:
    display: DisplayPlanV1 | None
    failure: PlanningFailureV1 | None
    display_artifact_id: str | None
    failure_artifact_id: str | None
    agent_explanation: PlannerAgentFinalV1 | None = None


class PlanningService:
    """Own deterministic state and emit raw tool-call/tool-result events."""

    def __init__(
        self,
        *,
        clock: Clock = system_clock,
        restaurant_source: RestaurantSourceV1 | None = None,
        load_default_source: bool = True,
        trace_writer: JsonlTraceWriter | None = None,
    ) -> None:
        self.clock = clock
        self.artifacts = ArtifactStore(clock)
        self.cases = PlanningCaseStore()
        self.restaurant_source = restaurant_source or (
            load_restaurant_source() if load_default_source else None
        )
        self.evidence = EvidenceStore()
        self.policies = PolicyRegistry()
        self.events = ToolEventStore()
        self.trace_writer = trace_writer
        self._event_sequence = 0
        self._last_failed_call_ids: dict[tuple[str, str], str] = {}
        if self.restaurant_source is not None:
            for restaurant in self.restaurant_source.restaurants:
                for item in restaurant.menu_items:
                    self.evidence.put(item.serving_evidence.evidence_id, item.serving_evidence)

    def attach_trace_writer(self, trace_writer: JsonlTraceWriter) -> None:
        """Attach the per-run local trace before a planning case is executed."""

        self.trace_writer = trace_writer

    def create_case(self, job: PlanningJobV2) -> None:
        self.cases.create(job)

    def planner_view(self, case_id: str):
        from .planner_contracts import PlannerViewV2

        job = self.cases.get(case_id).job
        intake = job.intake
        policy = job.runtime_policy
        return PlannerViewV2(
            case_id=case_id,
            profile_revision=intake.profile_revision,
            participant_count=intake.profile.party.total_count,
            location_query=job.execution_context.resolved_location.query,
            requested_category_codes=[
                term.code for term in intake.profile.food_scope.requested_categories
            ],
            hard_requirement_ids=[
                requirement.requirement_id for requirement in intake.profile.hard_requirements
            ],
            risk_preference=intake.profile.quantity_preference.primary_objective.value,
            maximum_budget_minor=intake.profile.budget.maximum_amount_minor,
            policy_ids=[
                policy.serving_policy.serving_policy_id,
                policy.serving_policy.quantity_policy_id,
                policy.budget_policy.policy_id,
                policy.restaurant_search.policy_id,
                policy.menu_filter.policy_id,
                policy.combination.policy_id,
                policy.ranking.policy_id,
            ],
        )

    def _event(
        self,
        case_id: str,
        stage: int,
        tool_name: str,
        event_type: str,
        summary: str,
        *,
        call_id: str | None = None,
        input_ids: list[str] | None = None,
        output_ids: list[str] | None = None,
        duration_ms: int | None = None,
        error_type: str | None = None,
    ) -> ToolEventV1:
        state = self.cases.get(case_id)
        self._event_sequence += 1
        event_id = f"event:{case_id}:{self._event_sequence}"
        event = ToolEventV1(
            event_id=event_id,
            event_type=event_type,
            call_id=call_id or event_id,
            trace_id=state.job.execution_context.trace_id,
            case_id=case_id,
            profile_revision=state.job.intake.profile_revision,
            stage=stage,
            tool_name=tool_name,
            occurred_at=self.clock(),
            input_artifact_ids=input_ids or [],
            output_artifact_ids=output_ids or [],
            duration_ms=duration_ms,
            error_type=error_type,
            summary=summary,
        )
        self.events.append(event)
        if self.trace_writer is not None:
            self.trace_writer.write_tool_event(event)
        return event

    def _run_stage(
        self,
        case_id: str,
        stage: int,
        tool_name: str,
        artifact_type: str,
        operation: Callable[[], object],
        summary: Callable[[object], str],
        *,
        input_ids: list[str] | None = None,
    ) -> ArtifactResult:
        started_at = perf_counter()
        call_event = self._event(
            case_id,
            stage,
            tool_name,
            "tool_call",
            f"{tool_name} called with validated case/artifact identifiers",
            input_ids=input_ids,
        )
        state = self.cases.get(case_id)
        try:
            with deterministic_tool_span(
                case_id=case_id,
                stage=stage,
                tool_name=tool_name,
                call_id=call_event.call_id,
                input_artifact_ids=input_ids or [],
            ):
                payload = operation()
                if not hasattr(payload, "model_dump_json"):
                    raise TypeError(f"{tool_name} returned a non-contract payload")
                ref = self.artifacts.put(
                    case_id,
                    state.job.intake.profile_revision,
                    artifact_type,
                    payload,  # type: ignore[arg-type]
                )
                result_summary = summary(payload)
        except Exception as exc:
            duration_ms = max(0, round((perf_counter() - started_at) * 1000))
            self._last_failed_call_ids[(case_id, tool_name)] = call_event.call_id
            self._event(
                case_id,
                stage,
                tool_name,
                "tool_error",
                f"{tool_name} failed with {type(exc).__name__}",
                call_id=call_event.call_id,
                input_ids=input_ids,
                duration_ms=duration_ms,
                error_type=type(exc).__name__,
            )
            raise
        duration_ms = max(0, round((perf_counter() - started_at) * 1000))
        self._event(
            case_id,
            stage,
            tool_name,
            "tool_result",
            result_summary,
            call_id=call_event.call_id,
            input_ids=input_ids,
            output_ids=[ref.artifact_id],
            duration_ms=duration_ms,
        )
        return ArtifactResult(ref=ref, summary=result_summary)

    def build_serving_input(self, case_id: str) -> ArtifactResult:
        state = self.cases.get(case_id)
        return self._run_stage(
            case_id,
            4,
            "build_serving_input",
            "serving_input",
            lambda: build_serving_input(
                state.job.intake,
                demand_multiplier_basis_points=state.demand_multiplier_basis_points,
            ),
            lambda value: f"adapted {len(value.groups)} participant groups to serving policy",  # type: ignore[attr-defined]
        )

    def calculate_serving_requirement(self, case_id: str, serving_input_id: str) -> ArtifactResult:
        def operation() -> object:
            self.artifacts.assert_same_revision(serving_input_id)
            serving_input = self.artifacts.get(serving_input_id, ServingCalculationInputV1)
            return calculate_serving_requirement(serving_input)  # type: ignore[arg-type]

        return self._run_stage(
            case_id,
            4,
            "calculate_serving_requirement",
            "serving_requirement",
            operation,
            lambda value: (
                f"calculated {value.equivalent_group_servings_milli / 1000:.3f} equivalent servings "  # type: ignore[attr-defined]
                f"for {value.attendance_count} attendees"  # type: ignore[attr-defined]
            ),
            input_ids=[serving_input_id],
        )

    def search_menu_candidates(self, case_id: str) -> ArtifactResult:
        state = self.cases.get(case_id)
        job = state.job

        def operation() -> object:
            if self.restaurant_source is None:
                raise LookupError("restaurant source unavailable")
            return search_menu_candidates(
                job.intake,
                self.restaurant_source,
                now=self.clock(),
                restaurant_limit=job.runtime_policy.restaurant_search.restaurant_limit,
                unavailable_restaurant_ids=state.unavailable_restaurant_ids,
                unavailable_menu_item_ids=state.unavailable_menu_item_ids,
            )

        return self._run_stage(
            case_id,
            5,
            "search_menu_candidates",
            "candidate_menu_set",
            operation,
            lambda value: (
                f"direct source lookup returned {len(value.restaurants)} restaurants; "  # type: ignore[attr-defined]
                f"freshness={value.freshness.value}, data_mode={value.data_mode.value}"  # type: ignore[attr-defined]
            ),
        )

    def enrich_menu_semantics(self, case_id: str, candidate_menu_set_id: str) -> ArtifactResult:
        def operation() -> object:
            candidates = self.artifacts.get(candidate_menu_set_id, CandidateMenuSetV1)
            return enrich_menu_semantics(
                candidates, candidate_menu_set_id=candidate_menu_set_id  # type: ignore[arg-type]
            )

        return self._run_stage(
            case_id,
            6,
            "enrich_menu_semantics",
            "normalized_menu_set",
            operation,
            lambda value: (
                f"validated source-backed semantic provenance; "
                f"model calls={value.model_enrichments}"  # type: ignore[attr-defined]
            ),
            input_ids=[candidate_menu_set_id],
        )

    def apply_hard_eligibility(self, case_id: str, normalized_menu_set_id: str) -> ArtifactResult:
        state = self.cases.get(case_id)

        def operation() -> object:
            normalized = self.artifacts.get(normalized_menu_set_id, NormalizedMenuSetV1)
            return apply_hard_eligibility(
                state.job.intake,
                normalized,  # type: ignore[arg-type]
                normalized_menu_set_id=normalized_menu_set_id,
            )

        return self._run_stage(
            case_id,
            8,
            "apply_hard_eligibility",
            "eligible_menu_set",
            operation,
            lambda value: (
                f"evaluated hard eligibility for {len(value.restaurants)} restaurants; "  # type: ignore[attr-defined]
                f"fully excluded items={value.excluded_item_count}"  # type: ignore[attr-defined]
            ),
            input_ids=[normalized_menu_set_id],
        )

    def generate_budget_combinations(
        self,
        case_id: str,
        eligible_menu_set_id: str,
        serving_requirement_id: str,
    ) -> ArtifactResult:
        state = self.cases.get(case_id)

        def operation() -> object:
            self.artifacts.assert_same_revision(eligible_menu_set_id, serving_requirement_id)
            eligible = self.artifacts.get(eligible_menu_set_id, EligibleMenuSetV1)
            serving = self.artifacts.get(serving_requirement_id, ServingRequirementV1)
            return generate_budget_combinations(
                state.job.intake,
                eligible,  # type: ignore[arg-type]
                serving,  # type: ignore[arg-type]
                eligible_menu_set_id=eligible_menu_set_id,
                serving_requirement_id=serving_requirement_id,
                policy=state.job.runtime_policy,
                menu_serving_multipliers_basis_points=state.menu_serving_multipliers_basis_points,
            )

        return self._run_stage(
            case_id,
            9,
            "generate_budget_combinations",
            "combination_set",
            operation,
            lambda value: (
                f"bounded integer search evaluated {value.evaluated_count} combinations and retained "  # type: ignore[attr-defined]
                f"{len(value.combinations)} hard-valid combinations"  # type: ignore[attr-defined]
            ),
            input_ids=[eligible_menu_set_id, serving_requirement_id],
        )

    def score_soft_preferences(
        self,
        case_id: str,
        combination_set_id: str,
        eligible_menu_set_id: str,
    ) -> ArtifactResult:
        state = self.cases.get(case_id)

        def operation() -> object:
            self.artifacts.assert_same_revision(combination_set_id, eligible_menu_set_id)
            combinations = self.artifacts.get(combination_set_id, CombinationSetV1)
            eligible = self.artifacts.get(eligible_menu_set_id, EligibleMenuSetV1)
            return score_soft_preferences(
                state.job.intake,
                combinations,  # type: ignore[arg-type]
                eligible,  # type: ignore[arg-type]
                combination_set_id=combination_set_id,
                policy=state.job.runtime_policy,
            )

        return self._run_stage(
            case_id,
            9,
            "score_soft_preferences",
            "scored_combination_set",
            operation,
            lambda value: f"scored {len(value.scored_combinations)} combinations with bounded policy weights",  # type: ignore[attr-defined]
            input_ids=[combination_set_id, eligible_menu_set_id],
        )

    def rank_and_validate_plans(self, case_id: str, scored_combination_set_id: str) -> ArtifactResult:
        state = self.cases.get(case_id)

        def operation() -> object:
            scored = self.artifacts.get(scored_combination_set_id, ScoredCombinationSetV1)
            return rank_and_validate_plans(
                state.job.intake,
                scored,  # type: ignore[arg-type]
                scored_combination_set_id=scored_combination_set_id,
            )

        return self._run_stage(
            case_id,
            10,
            "rank_and_validate_plans",
            "ranked_plan_set",
            operation,
            lambda value: (
                f"selected three hard-valid strategies; recommended={value.recommended_strategy.value}"  # type: ignore[attr-defined]
            ),
            input_ids=[scored_combination_set_id],
        )

    def get_plan_for_presentation(
        self,
        case_id: str,
        ranked_plan_set_id: str,
        serving_requirement_id: str,
        candidate_menu_set_id: str,
    ) -> ArtifactResult:
        state = self.cases.get(case_id)

        def operation() -> object:
            self.artifacts.assert_same_revision(
                ranked_plan_set_id, serving_requirement_id, candidate_menu_set_id
            )
            ranked = self.artifacts.get(ranked_plan_set_id, RankedPlanSetV1)
            serving = self.artifacts.get(serving_requirement_id, ServingRequirementV1)
            candidates = self.artifacts.get(candidate_menu_set_id, CandidateMenuSetV1)
            if self.restaurant_source is None:
                raise LookupError("restaurant source unavailable")
            return get_plan_for_presentation(
                state.job.intake,
                serving,  # type: ignore[arg-type]
                ranked,  # type: ignore[arg-type]
                self.restaurant_source,
                freshness=candidates.freshness,  # type: ignore[attr-defined]
                data_mode=candidates.data_mode,  # type: ignore[attr-defined]
                source_warnings=candidates.warnings,  # type: ignore[attr-defined]
            )

        return self._run_stage(
            case_id,
            11,
            "get_plan_for_presentation",
            "display_plan",
            operation,
            lambda value: (
                f"prepared judge-readable plan for {value.restaurant.name} with "  # type: ignore[attr-defined]
                f"{len(value.recommended_plan.combination.lines)} order lines"  # type: ignore[attr-defined]
            ),
            input_ids=[ranked_plan_set_id, serving_requirement_id, candidate_menu_set_id],
        )

    def _failure(self, case_id: str, status: str, reason: str) -> PlanRunResult:
        state = self.cases.get(case_id)
        corrective_action = (
            "Provide source-backed restaurant, menu, price, and practical-serving data for the requested category and location."
        )
        failure = PlanningFailureV1(
            case_id=case_id,
            profile_revision=state.job.intake.profile_revision,
            status=status,
            problematic_field="/planning",
            received_value="validated planning job and direct restaurant source state",
            reason=reason[:500],
            corrective_action=corrective_action,
            compromises=[
                "increase the budget ceiling",
                "confirm a different restaurant",
                "provide verified dietary/allergen data for another item",
            ],
        )
        ref = self.artifacts.put(
            case_id, state.job.intake.profile_revision, "planning_failure", failure
        )
        return PlanRunResult(
            display=None,
            failure=failure,
            display_artifact_id=None,
            failure_artifact_id=ref.artifact_id,
        )

    def controlled_tool_failure(
        self,
        case_id: str,
        *,
        stage: int,
        tool_name: str,
        status: str,
        reason: str,
        input_ids: list[str] | None = None,
    ) -> ArtifactResult:
        """Turn an expected no-data/no-plan branch into a terminal artifact."""

        run_result = self._failure(case_id, status, reason)
        assert run_result.failure is not None and run_result.failure_artifact_id is not None
        ref = self.artifacts.ref(run_result.failure_artifact_id)
        summary = f"terminal {status}: {reason}"[:500]
        self._event(
            case_id,
            stage,
            tool_name,
            "tool_result",
            summary,
            call_id=self._last_failed_call_ids.pop((case_id, tool_name), None),
            input_ids=input_ids,
            output_ids=[ref.artifact_id],
        )
        return ArtifactResult(ref=ref, summary=summary)

    def plan_case(self, case_id: str) -> PlanRunResult:
        """Offline deterministic coordinator using the same functions exposed as SDK tools."""

        try:
            serving_input = self.build_serving_input(case_id)
            serving = self.calculate_serving_requirement(case_id, serving_input.ref.artifact_id)
            candidates = self.search_menu_candidates(case_id)
            normalized = self.enrich_menu_semantics(case_id, candidates.ref.artifact_id)
            eligible = self.apply_hard_eligibility(case_id, normalized.ref.artifact_id)
            combinations = self.generate_budget_combinations(
                case_id, eligible.ref.artifact_id, serving.ref.artifact_id
            )
            scored = self.score_soft_preferences(
                case_id, combinations.ref.artifact_id, eligible.ref.artifact_id
            )
            ranked = self.rank_and_validate_plans(case_id, scored.ref.artifact_id)
            display_ref = self.get_plan_for_presentation(
                case_id,
                ranked.ref.artifact_id,
                serving.ref.artifact_id,
                candidates.ref.artifact_id,
            )
            display = self.artifacts.get(display_ref.ref.artifact_id, DisplayPlanV1)
            return PlanRunResult(
                display=display,  # type: ignore[arg-type]
                failure=None,
                display_artifact_id=display_ref.ref.artifact_id,
                failure_artifact_id=None,
            )
        except LookupError as exc:
            reason = str(exc)
            status = (
                "data_unavailable"
                if "source" in reason or "source-backed" in reason
                else "no_valid_plan"
            )
            return self._failure(case_id, status, reason)

    def _replan_from_stage_five(self, case_id: str) -> PlanRunResult:
        serving_ref = self.artifacts.latest_ref(case_id, "serving_requirement")
        if serving_ref is None:
            return self.plan_case(case_id)
        try:
            candidates = self.search_menu_candidates(case_id)
            normalized = self.enrich_menu_semantics(case_id, candidates.ref.artifact_id)
            eligible = self.apply_hard_eligibility(case_id, normalized.ref.artifact_id)
            combinations = self.generate_budget_combinations(
                case_id, eligible.ref.artifact_id, serving_ref.artifact_id
            )
            scored = self.score_soft_preferences(
                case_id, combinations.ref.artifact_id, eligible.ref.artifact_id
            )
            ranked = self.rank_and_validate_plans(case_id, scored.ref.artifact_id)
            display_ref = self.get_plan_for_presentation(
                case_id,
                ranked.ref.artifact_id,
                serving_ref.artifact_id,
                candidates.ref.artifact_id,
            )
            display = self.artifacts.get(display_ref.ref.artifact_id, DisplayPlanV1)
            return PlanRunResult(display, None, display_ref.ref.artifact_id, None)  # type: ignore[arg-type]
        except LookupError as exc:
            reason = str(exc)
            status = "data_unavailable" if "source" in reason else "no_valid_plan"
            return self._failure(case_id, status, reason)

    def replan_restaurant_unavailable(self, case_id: str, restaurant_id: str) -> PlanRunResult:
        """Rerun from stage 5; serving demand is reused, not copied between restaurants."""

        state = self.cases.get(case_id)
        if self.restaurant_source is None:
            raise LookupError("restaurant source unavailable")
        if restaurant_id not in {
            restaurant.restaurant_id for restaurant in self.restaurant_source.restaurants
        }:
            raise KeyError(f"unknown restaurant id: {restaurant_id}")
        state.unavailable_restaurant_ids.add(restaurant_id)
        return self._replan_from_stage_five(case_id)

    def replan_menu_unavailable(self, case_id: str, menu_item_id: str) -> PlanRunResult:
        state = self.cases.get(case_id)
        if self.restaurant_source is None:
            raise LookupError("restaurant source unavailable")
        if menu_item_id not in {
            item.menu_item_id
            for restaurant in self.restaurant_source.restaurants
            for item in restaurant.menu_items
        }:
            raise KeyError(f"unknown menu item id: {menu_item_id}")
        state.unavailable_menu_item_ids.add(menu_item_id)
        return self._replan_from_stage_five(case_id)

    def record_feedback(self, feedback: MealFeedbackV1) -> FeedbackAdjustmentV1:
        state = self.cases.get(feedback.case_id)
        previous = state.demand_multiplier_basis_points
        if feedback.outcome == "shortage":
            updated = min(12_500, previous + 500)
            reason = "reported shortage increases future equivalent-demand estimate by 5%"
        elif feedback.outcome == "leftovers" and feedback.leftover_servings_milli >= 1_000:
            updated = max(7_500, previous - 300)
            reason = "reported material leftovers reduce future equivalent-demand estimate by 3%"
        else:
            updated = previous
            reason = "outcome did not cross a configured adjustment threshold"
        menu_changes: dict[str, int] = {}
        if feedback.delivered_portions_smaller_than_expected:
            for item_id in feedback.affected_menu_item_ids:
                current = state.menu_serving_multipliers_basis_points.get(item_id, 10_000)
                changed = max(7_500, current - 500)
                state.menu_serving_multipliers_basis_points[item_id] = changed
                menu_changes[item_id] = changed
        state.demand_multiplier_basis_points = updated
        state.feedback.append(feedback)
        adjustment = FeedbackAdjustmentV1(
            case_id=feedback.case_id,
            previous_demand_multiplier_basis_points=previous,
            new_demand_multiplier_basis_points=updated,
            menu_serving_multiplier_changes_basis_points=menu_changes,
            observation=(
                f"outcome={feedback.outcome}; leftover={feedback.leftover_servings_milli} milli-servings; "
                f"actual_attendance={feedback.actual_attendance}"
            ),
            reason=reason,
        )
        state.feedback_adjustments.append(adjustment)
        return adjustment

    def replan_after_feedback(self, feedback: MealFeedbackV1) -> tuple[FeedbackAdjustmentV1, PlanRunResult]:
        adjustment = self.record_feedback(feedback)
        return adjustment, self.plan_case(feedback.case_id)

    def replan_budget(self, case_id: str, maximum_amount_minor: int) -> PlanRunResult:
        if maximum_amount_minor < 0:
            raise ValueError("budget maximum cannot be negative")
        state = self.cases.get(case_id)
        old_job = state.job
        old_intake = old_job.intake
        budget = ResolvedBudgetV2(
            budget_type=ResolvedBudgetType.HARD_MAXIMUM,
            currency="KRW",
            target_amount_minor=None,
            maximum_amount_minor=maximum_amount_minor,
            maximum_source=BudgetMaximumSource.EXPLICIT,
            cost_scope=old_intake.profile.budget.cost_scope,
        )
        profile_data = old_intake.profile.model_dump()
        profile_data["budget"] = budget.model_dump()
        profile = ValidatedMealProfileV2.model_validate(profile_data)
        intake_data = old_intake.model_dump()
        intake_data.update(
            {
                "profile_revision": old_intake.profile_revision + 1,
                "validated_at": self.clock(),
                "profile": profile.model_dump(),
            }
        )
        intake = PlanningIntakeV2.model_validate(intake_data)
        context = old_job.execution_context.model_copy(
            update={
                "requested_at": self.clock(),
                "trace_id": f"{old_job.execution_context.trace_id}:budget-r{intake.profile_revision}",
            }
        )
        job = PlanningJobV2(
            intake=intake,
            runtime_policy=old_job.runtime_policy,
            execution_context=context,
        )
        self.cases.upsert_revision(job)
        return self.plan_case(case_id)

    def replan_participant_group_count(
        self, case_id: str, group_id: str, new_count: int
    ) -> PlanRunResult:
        """Apply a structured attendance change and rerun under a new profile revision."""

        if not 1 <= new_count <= 100:
            raise ValueError("participant group count must remain between 1 and 100")
        state = self.cases.get(case_id)
        old_job = state.job
        old_intake = old_job.intake
        found = False
        groups = []
        for group in old_intake.profile.party.groups:
            if group.group_id == group_id:
                group = group.model_copy(update={"count": new_count})
                found = True
            groups.append(group)
        if not found:
            raise KeyError(f"unknown participant group: {group_id}")
        total_count = sum(group.count for group in groups)
        if total_count > 100:
            raise ValueError("updated participant total exceeds the supported maximum of 100")
        party = old_intake.profile.party.model_copy(
            update={"total_count": total_count, "groups": groups}
        )
        profile_data = old_intake.profile.model_dump()
        profile_data["party"] = party.model_dump()
        profile = ValidatedMealProfileV2.model_validate(profile_data)
        intake_data = old_intake.model_dump()
        intake_data.update(
            {
                "profile_revision": old_intake.profile_revision + 1,
                "validated_at": self.clock(),
                "profile": profile.model_dump(),
            }
        )
        intake = PlanningIntakeV2.model_validate(intake_data)
        context = old_job.execution_context.model_copy(
            update={
                "requested_at": self.clock(),
                "trace_id": f"{old_job.execution_context.trace_id}:party-r{intake.profile_revision}",
            }
        )
        self.cases.upsert_revision(
            PlanningJobV2(
                intake=intake,
                runtime_policy=old_job.runtime_policy,
                execution_context=context,
            )
        )
        return self.plan_case(case_id)
