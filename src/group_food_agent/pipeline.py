"""Observable Steps 1–4 intake pipeline."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import AwareDatetime, Field

from .contracts import (
    ContractIssueV2,
    ContractModel,
    IssueSeverity,
    MealRequestCandidateV2,
    PlanningBoundaryOutcomeV2,
    RequestRejectedV2,
    utc_now,
)
from .preflight import (
    PreflightStatus,
    RawInputIssue,
    RawInputLimits,
    preflight_raw_input,
)
from .intake_normalization import normalize_candidate_for_validation
from .validation import (
    AdmissionPolicyV2,
    ValidationContextV2,
    validate_planning_profile,
)


class PipelineStage(StrEnum):
    RAW_INPUT = "raw_input"
    PREFLIGHT = "preflight"
    INTERPRETER_AGENT = "interpreter_agent"
    DETERMINISTIC_VALIDATION = "deterministic_validation"
    OUTCOME = "outcome"


class PipelineEventType(StrEnum):
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"
    STAGE_BLOCKED = "stage_blocked"
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"


class PipelineEvent(ContractModel):
    event_type: PipelineEventType
    stage: PipelineStage
    occurred_at: AwareDatetime = Field(default_factory=utc_now)
    request_id: str = Field(min_length=1, max_length=128)
    case_id: str = Field(min_length=1, max_length=128)
    schema_version: str = "2.0"
    vocabulary_version: str = "1.0"
    detail: dict[str, str | int | bool | None] = Field(default_factory=dict)


EventSink = Callable[[PipelineEvent], None | Awaitable[None]]


class InterpreterProtocol(Protocol):
    async def interpret(self, raw_text: str) -> MealRequestCandidateV2: ...


async def _emit(sink: EventSink | None, event: PipelineEvent) -> None:
    if sink is None:
        return
    result = sink(event)
    if inspect.isawaitable(result):
        await result


def _preflight_issue_to_contract(issue: RawInputIssue) -> ContractIssueV2:
    return ContractIssueV2(
        code=issue.code,
        severity=issue.severity,
        field_path=issue.field_path,
        message=(
            f"Received '{issue.received_value}'. {issue.reason} "
            f"Smallest corrective action: {issue.corrective_action}"
        )[:500],
        evidence_ids=[],
    )


async def process_meal_request(
    raw_text: str,
    context: ValidationContextV2,
    *,
    interpreter: InterpreterProtocol | None = None,
    admission_policy: AdmissionPolicyV2 | None = None,
    input_limits: RawInputLimits | None = None,
    event_sink: EventSink | None = None,
) -> PlanningBoundaryOutcomeV2:
    """Run the complete input/preprocessing boundary.

    Invalid raw input stops before the Agents SDK is instantiated. Valid raw
    input runs the typed Interpreter Agent exactly once at this pipeline layer;
    the interpreter itself owns one bounded SDK retry.
    """

    await _emit(
        event_sink,
        PipelineEvent(
            event_type=PipelineEventType.STAGE_STARTED,
            stage=PipelineStage.RAW_INPUT,
            request_id=context.request_id,
            case_id=context.case_id,
            detail={"input_length": len(raw_text) if isinstance(raw_text, str) else 0},
        ),
    )
    preflight = preflight_raw_input(raw_text, input_limits)
    await _emit(
        event_sink,
        PipelineEvent(
            event_type=(
                PipelineEventType.STAGE_BLOCKED
                if preflight.status is PreflightStatus.REJECTED
                else PipelineEventType.STAGE_COMPLETED
            ),
            stage=PipelineStage.PREFLIGHT,
            request_id=context.request_id,
            case_id=context.case_id,
            detail={"status": preflight.status.value, "issue_count": len(preflight.issues)},
        ),
    )
    if preflight.status is PreflightStatus.REJECTED:
        contract_issues = [_preflight_issue_to_contract(issue) for issue in preflight.issues]
        fatal_issues = [issue for issue in contract_issues if issue.severity is IssueSeverity.FATAL]
        outcome = RequestRejectedV2(
            request_id=context.request_id,
            case_id=context.case_id,
            reason_code=(fatal_issues or contract_issues)[0].code,
            issues=contract_issues,
        )
        await _emit(
            event_sink,
            PipelineEvent(
                event_type=PipelineEventType.STAGE_BLOCKED,
                stage=PipelineStage.OUTCOME,
                request_id=context.request_id,
                case_id=context.case_id,
                detail={"status": outcome.status, "reason_code": outcome.reason_code},
            ),
        )
        return outcome

    if interpreter is None:
        from .interpreter import MealRequestInterpreter

        interpreter = MealRequestInterpreter()

    await _emit(
        event_sink,
        PipelineEvent(
            event_type=PipelineEventType.AGENT_STARTED,
            stage=PipelineStage.INTERPRETER_AGENT,
            request_id=context.request_id,
            case_id=context.case_id,
            detail={"sdk": "openai_agents", "output_type": "MealRequestCandidateV2"},
        ),
    )
    try:
        candidate = await interpreter.interpret(raw_text)
    except Exception as exc:
        await _emit(
            event_sink,
            PipelineEvent(
                event_type=PipelineEventType.AGENT_FAILED,
                stage=PipelineStage.INTERPRETER_AGENT,
                request_id=context.request_id,
                case_id=context.case_id,
                detail={"error_type": type(exc).__name__},
            ),
        )
        outcome = RequestRejectedV2(
            request_id=context.request_id,
            case_id=context.case_id,
            reason_code="interpreter_failure",
            issues=[
                ContractIssueV2(
                    code="interpreter_failure",
                    severity=IssueSeverity.FATAL,
                    field_path="/candidate",
                    message="The Interpreter Agent failed after its bounded retry. Retry the original request; no planning tools were called.",
                    evidence_ids=[],
                )
            ],
        )
        await _emit(
            event_sink,
            PipelineEvent(
                event_type=PipelineEventType.STAGE_BLOCKED,
                stage=PipelineStage.OUTCOME,
                request_id=context.request_id,
                case_id=context.case_id,
                detail={"status": outcome.status, "reason_code": outcome.reason_code},
            ),
        )
        return outcome
    await _emit(
        event_sink,
        PipelineEvent(
            event_type=PipelineEventType.AGENT_COMPLETED,
            stage=PipelineStage.INTERPRETER_AGENT,
            request_id=context.request_id,
            case_id=context.case_id,
            detail={
                "sdk": "openai_agents",
                "candidate_type": type(candidate).__name__,
                "unresolved_issue_count": len(candidate.unresolved_issues),
            },
        ),
    )

    candidate = normalize_candidate_for_validation(candidate, raw_text)

    upstream_warnings = [
        _preflight_issue_to_contract(issue)
        for issue in preflight.issues
        if issue.severity is IssueSeverity.WARNING
    ]
    await _emit(
        event_sink,
        PipelineEvent(
            event_type=PipelineEventType.STAGE_STARTED,
            stage=PipelineStage.DETERMINISTIC_VALIDATION,
            request_id=context.request_id,
            case_id=context.case_id,
            detail={"validator": "planning_intake_validator_v2.0.0"},
        ),
    )
    outcome = validate_planning_profile(
        candidate,
        context,
        policy=admission_policy,
        raw_text=raw_text,
        upstream_warnings=upstream_warnings,
    )
    await _emit(
        event_sink,
        PipelineEvent(
            event_type=(
                PipelineEventType.STAGE_COMPLETED
                if outcome.status == "ready_for_planning"
                else PipelineEventType.STAGE_BLOCKED
            ),
            stage=PipelineStage.DETERMINISTIC_VALIDATION,
            request_id=context.request_id,
            case_id=context.case_id,
            detail={"status": outcome.status},
        ),
    )
    await _emit(
        event_sink,
        PipelineEvent(
            event_type=(
                PipelineEventType.STAGE_COMPLETED
                if outcome.status == "ready_for_planning"
                else PipelineEventType.STAGE_BLOCKED
            ),
            stage=PipelineStage.OUTCOME,
            request_id=context.request_id,
            case_id=context.case_id,
            detail={"status": outcome.status},
        ),
    )
    return outcome
