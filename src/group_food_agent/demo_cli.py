"""Rehearse the complete Group Food Quantity Agent with the canonical fixture."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
from uuid import uuid4

from .contracts import MealRequestCandidateV2, utc_now
from .config import load_project_dotenv
from .planner_agent import run_agent_plan
from .planner_models import MealFeedbackV1
from .service import PlanRunResult, PlanningService
from .stores import job_from_intake
from .tracing import (
    JsonlTraceWriter,
    agents_trace_scope,
    build_agents_run_config,
    new_trace_correlation,
)
from .validation import ValidationContextV2, validate_planning_profile


ROOT = Path(__file__).resolve().parents[2]


def build_canonical_job():
    candidate = MealRequestCandidateV2.model_validate_json(
        (ROOT / "fixtures" / "canonical_15_candidate.json").read_text(encoding="utf-8")
    )
    raw_text = (ROOT / "fixtures" / "canonical_15_request.txt").read_text(encoding="utf-8")
    intake = validate_planning_profile(
        candidate,
        ValidationContextV2(request_id="request-canonical-15", case_id="case-canonical-15"),
        raw_text=raw_text,
    )
    if intake.status != "ready_for_planning":
        raise RuntimeError(f"canonical fixture is not planning-ready: {intake.status}")
    now = utc_now()
    return job_from_intake(
        intake,
        requested_at=now,
        trace_id="trace-canonical-15",
    )


def _result_payload(result: PlanRunResult) -> dict:
    if result.display is not None:
        return result.display.model_dump(mode="json")
    assert result.failure is not None
    return result.failure.model_dump(mode="json")


async def _run(args: argparse.Namespace) -> int:
    job = build_canonical_job()
    correlation = new_trace_correlation(
        job.intake.request_id,
        job.intake.case_id,
        logical_trace_id=job.execution_context.trace_id,
    )
    trace_file = args.trace_file
    if args.trace and trace_file is None:
        trace_file = ROOT / ".traces" / f"canonical-{uuid4().hex[:8]}.jsonl"
    trace_writer = JsonlTraceWriter(trace_file, correlation) if args.trace else None
    service = PlanningService(trace_writer=trace_writer)
    service.create_case(job)
    with agents_trace_scope(correlation, enabled=args.live):
        if args.live:
            result = await run_agent_plan(
                service,
                job.intake.case_id,
                run_config=build_agents_run_config(
                    correlation,
                    workflow_name="group_food_quantity_planner",
                ),
            )
        else:
            result = service.plan_case(job.intake.case_id)
    if args.live:
        from agents import flush_traces

        flush_traces()

    history: list[dict] = [{"run": "initial", "result": _result_payload(result)}]
    if args.replan_unavailable and result.display:
        unavailable_id = result.display.restaurant.restaurant_id
        result = service.replan_restaurant_unavailable(job.intake.case_id, unavailable_id)
        history.append(
            {
                "run": "restaurant_unavailable_replan",
                "unavailable_restaurant_id": unavailable_id,
                "result": _result_payload(result),
            }
        )
    if args.feedback and result.display:
        feedback = MealFeedbackV1(
            case_id=job.intake.case_id,
            actual_attendance=result.display.group_analysis.actual_attendance,
            outcome=args.feedback,
            leftover_servings_milli=2_000 if args.feedback == "leftovers" else 0,
            affected_menu_item_ids=[
                line.menu_item_id for line in result.display.recommended_plan.combination.lines
            ],
            delivered_portions_smaller_than_expected=args.feedback == "shortage",
            note="Canonical demo feedback",
        )
        adjustment, result = service.replan_after_feedback(feedback)
        history.append(
            {
                "run": "feedback_replan",
                "adjustment": adjustment.model_dump(mode="json"),
                "result": _result_payload(result),
            }
        )

    tool_events = service.events.for_case(job.intake.case_id)
    errors = [event for event in tool_events if event.event_type == "tool_error"]
    blocker = errors[-1] if errors else None
    execution = {
        "status": "succeeded" if result.failure is None else "blocked",
        "blocked": result.failure is not None,
        "blocked_at": (
            {
                "source": "deterministic_gateway",
                "stage": blocker.stage,
                "tool_name": blocker.tool_name,
                "event_id": blocker.event_id,
                "call_id": blocker.call_id,
                "error_type": blocker.error_type,
            }
            if blocker is not None
            else None
        ),
        "reason": result.failure.reason if result.failure is not None else "plan_ready",
        "corrective_action": (
            result.failure.corrective_action if result.failure is not None else None
        ),
    }
    print(
        "[group-food-demo] "
        + ("BLOCKED: " + str(execution["reason"]) if execution["blocked"] else "SUCCEEDED"),
        file=sys.stderr,
    )
    output = {
        "mode": "live_agents_sdk" if args.live else "offline_deterministic",
        "execution": execution,
        "history": history,
        "trace": {
            "logical_trace_id": correlation.logical_trace_id,
            "sdk_trace_id": correlation.sdk_trace_id,
            "local_trace_file": str(trace_writer.path) if trace_writer is not None else None,
            "sensitive_payloads_exported": False,
        },
    }
    if args.events:
        output["tool_events"] = [
            event.model_dump(mode="json") for event in service.events.for_case(job.intake.case_id)
        ]
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if result.failure is None else 2


def main() -> None:
    load_project_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use the OpenAI Agents SDK planner (requires OPENAI_API_KEY)",
    )
    parser.add_argument(
        "--replan-unavailable",
        action="store_true",
        help="Mark the first selected restaurant unavailable and rerun from stage 5",
    )
    parser.add_argument("--feedback", choices=["shortage", "leftovers"])
    parser.add_argument("--events", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--trace",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write a privacy-conscious local JSONL trace (default: enabled)",
    )
    parser.add_argument("--trace-file", type=Path)
    args = parser.parse_args()
    try:
        code = asyncio.run(_run(args))
    except RuntimeError as exc:
        if "OPENAI_API_KEY" not in str(exc):
            raise
        parser.exit(3, f"configuration required: {exc}\n")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
