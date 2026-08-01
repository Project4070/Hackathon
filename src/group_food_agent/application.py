"""One end-to-end application entry point from raw text to ordering plan."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from .contracts import PlanningBoundaryOutcomeV2, PlanningIntakeV2, utc_now
from .pipeline import InterpreterProtocol, PipelineEvent, process_meal_request
from .preflight import PreflightStatus, preflight_raw_input
from .planner_agent import run_agent_plan
from .planner_models import ToolEventV1
from .service import PlanRunResult, PlanningService
from .stores import job_from_intake
from .tracing import (
    JsonlTraceWriter,
    TraceCorrelation,
    agents_trace_scope,
    build_agents_run_config,
    new_trace_correlation,
)
from .validation import AdmissionPolicyV2, ValidationContextV2


@dataclass(frozen=True)
class GroupFoodAgentRun:
    boundary_outcome: PlanningBoundaryOutcomeV2
    plan_result: PlanRunResult | None
    pipeline_events: list[PipelineEvent]
    tool_events: list[ToolEventV1]
    mode: str
    logical_trace_id: str
    sdk_trace_id: str
    local_trace_file: str | None

    def diagnostics(self) -> dict[str, object]:
        """Return a judge-readable success/block record for CLI and UI callers."""

        if self.plan_result is not None and self.plan_result.display is not None:
            return {
                "status": "succeeded",
                "blocked": False,
                "blocked_at": None,
                "reason": "validated plan and presentation artifact were produced",
                "corrective_action": None,
                "pipeline_event_count": len(self.pipeline_events),
                "tool_event_count": len(self.tool_events),
            }

        if self.plan_result is not None and self.plan_result.failure is not None:
            failure = self.plan_result.failure
            errors = [event for event in self.tool_events if event.event_type == "tool_error"]
            blocker = errors[-1] if errors else None
            return {
                "status": "blocked",
                "blocked": True,
                "blocked_at": {
                    "source": "deterministic_gateway",
                    "stage": blocker.stage if blocker else None,
                    "tool_name": blocker.tool_name if blocker else None,
                    "event_id": blocker.event_id if blocker else None,
                    "call_id": blocker.call_id if blocker else None,
                    "error_type": blocker.error_type if blocker else None,
                },
                "reason": failure.reason,
                "corrective_action": failure.corrective_action,
                "pipeline_event_count": len(self.pipeline_events),
                "tool_event_count": len(self.tool_events),
            }

        blocked_events = [
            event
            for event in self.pipeline_events
            if event.event_type.value in {"stage_blocked", "agent_failed"}
        ]
        non_terminal_blocked_events = [
            event for event in blocked_events if event.stage.value != "outcome"
        ]
        blocker = (
            non_terminal_blocked_events[-1]
            if non_terminal_blocked_events
            else blocked_events[-1]
            if blocked_events
            else None
        )
        reason_code = getattr(self.boundary_outcome, "reason_code", None)
        if not reason_code and blocker:
            reason_code = blocker.detail.get("reason_code")
        if not reason_code:
            reason_code = self.boundary_outcome.status
        return {
            "status": "blocked",
            "blocked": True,
            "blocked_at": {
                "source": "input_boundary",
                "stage": blocker.stage.value if blocker else None,
                "tool_name": None,
                "event_id": None,
                "call_id": None,
                "error_type": blocker.detail.get("error_type") if blocker else None,
            },
            "reason": reason_code,
            "corrective_action": "Resolve the reported input issue before planning tools are called.",
            "pipeline_event_count": len(self.pipeline_events),
            "tool_event_count": len(self.tool_events),
        }


async def run_group_food_agent(
    raw_text: str,
    context: ValidationContextV2,
    *,
    interpreter: InterpreterProtocol | None = None,
    admission_policy: AdmissionPolicyV2 | None = None,
    service: PlanningService | None = None,
    live_planner: bool = True,
    trace_file: str | Path | None = None,
) -> GroupFoodAgentRun:
    """Run preflight, Interpreter Agent, validation, and the full planner.

    ``live_planner=True`` uses the OpenAI Agents SDK main planner. Tests and the
    recorded demo can set it false while exercising the exact deterministic
    tools and artifacts that the live agent orchestrates.
    """

    preflight_status = preflight_raw_input(raw_text).status
    if (
        interpreter is None
        and not os.getenv("OPENAI_API_KEY")
        and preflight_status is not PreflightStatus.REJECTED
    ):
        raise RuntimeError(
            "OPENAI_API_KEY is required for the live Interpreter Agents SDK run. "
            "The canonical offline rehearsal does not require a key."
        )

    if (
        live_planner
        and preflight_status is not PreflightStatus.REJECTED
        and not os.getenv("OPENAI_API_KEY")
    ):
        raise RuntimeError(
            "OPENAI_API_KEY is required for the live Main Planner Agents SDK run. "
            "The canonical offline rehearsal does not require a key."
        )

    correlation = new_trace_correlation(context.request_id, context.case_id)
    trace_writer = JsonlTraceWriter(trace_file, correlation) if trace_file is not None else None
    if trace_writer is not None:
        trace_writer.write(
            source="application",
            event_type="run_started",
            name="group_food_quantity_agent",
            status="started",
            data={"input_length": len(raw_text), "live_planner": live_planner},
        )

    async def execute(correlation: TraceCorrelation) -> GroupFoodAgentRun:
        pipeline_events: list[PipelineEvent] = []

        def capture_pipeline_event(event: PipelineEvent) -> None:
            pipeline_events.append(event)
            if trace_writer is not None:
                trace_writer.write_pipeline_event(event)

        effective_interpreter = interpreter
        if effective_interpreter is None and preflight_status is not PreflightStatus.REJECTED:
            from .interpreter import MealRequestInterpreter

            effective_interpreter = MealRequestInterpreter(
                run_config=build_agents_run_config(
                    correlation,
                    workflow_name="group_food_request_interpreter",
                )
            )
        boundary = await process_meal_request(
            raw_text,
            context,
            interpreter=effective_interpreter,
            admission_policy=admission_policy,
            event_sink=capture_pipeline_event,
        )
        if not isinstance(boundary, PlanningIntakeV2):
            return GroupFoodAgentRun(
                boundary_outcome=boundary,
                plan_result=None,
                pipeline_events=pipeline_events,
                tool_events=[],
                mode="stopped_at_input_boundary",
                logical_trace_id=correlation.logical_trace_id,
                sdk_trace_id=correlation.sdk_trace_id,
                local_trace_file=str(trace_writer.path) if trace_writer is not None else None,
            )

        planner = service or PlanningService(trace_writer=trace_writer)
        if service is not None and trace_writer is not None:
            planner.attach_trace_writer(trace_writer)
        job = job_from_intake(
            boundary,
            requested_at=utc_now(),
            trace_id=correlation.logical_trace_id,
        )
        planner.create_case(job)
        if live_planner:
            result = await run_agent_plan(
                planner,
                boundary.case_id,
                run_config=build_agents_run_config(
                    correlation,
                    workflow_name="group_food_quantity_planner",
                ),
            )
            mode = "live_agents_sdk"
        else:
            result = planner.plan_case(boundary.case_id)
            mode = "offline_deterministic_rehearsal"
        return GroupFoodAgentRun(
            boundary_outcome=boundary,
            plan_result=result,
            pipeline_events=pipeline_events,
            tool_events=planner.events.for_case(boundary.case_id),
            mode=mode,
            logical_trace_id=correlation.logical_trace_id,
            sdk_trace_id=correlation.sdk_trace_id,
            local_trace_file=str(trace_writer.path) if trace_writer is not None else None,
        )

    sdk_tracing_enabled = preflight_status is not PreflightStatus.REJECTED and (
        interpreter is None or live_planner
    )
    try:
        with agents_trace_scope(correlation, enabled=sdk_tracing_enabled):
            run = await execute(correlation)
    except Exception as exc:
        if trace_writer is not None:
            trace_writer.write(
                source="application",
                event_type="run_failed",
                name="group_food_quantity_agent",
                status="failed",
                data={"error_type": type(exc).__name__},
            )
        raise
    if trace_writer is not None:
        trace_writer.write(
            source="application",
            event_type="run_completed",
            name="group_food_quantity_agent",
            status="completed",
            data={
                "mode": run.mode,
                "boundary_status": run.boundary_outcome.status,
                "planning_status": (
                    run.plan_result.failure.status
                    if run.plan_result and run.plan_result.failure
                    else "plan_ready"
                    if run.plan_result and run.plan_result.display
                    else None
                ),
            },
        )
    return run
