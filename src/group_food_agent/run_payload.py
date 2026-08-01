"""Shared serialization for CLI and browser application runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .application import GroupFoodAgentRun


def build_run_payload(
    run: GroupFoodAgentRun,
    *,
    public: bool = False,
    additions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the stable run envelope used by the CLI and web UI.

    Public responses retain correlation identifiers but never expose a local
    filesystem path. The trace file itself is not downloadable.
    """

    trace_file = run.local_trace_file
    if public and trace_file:
        trace_file = Path(trace_file).name
    payload: dict[str, Any] = {
        "mode": run.mode,
        "execution": run.diagnostics(),
        "boundary_outcome": run.boundary_outcome.model_dump(mode="json"),
        "plan_result": (
            run.plan_result.display.model_dump(mode="json")
            if run.plan_result and run.plan_result.display
            else run.plan_result.failure.model_dump(mode="json")
            if run.plan_result and run.plan_result.failure
            else None
        ),
        "agent_explanation": (
            run.plan_result.agent_explanation.model_dump(mode="json")
            if run.plan_result and run.plan_result.agent_explanation
            else None
        ),
        "pipeline_events": [event.model_dump(mode="json") for event in run.pipeline_events],
        "tool_events": [event.model_dump(mode="json") for event in run.tool_events],
        "trace": {
            "logical_trace_id": run.logical_trace_id,
            "sdk_trace_id": run.sdk_trace_id,
            "local_trace_file": trace_file,
            "sensitive_payloads_exported": False,
        },
    }
    if additions:
        payload.update(additions)
    return payload
