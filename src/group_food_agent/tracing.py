"""Privacy-conscious trace correlation for SDK and deterministic stages.

The OpenAI Agents SDK remains the source of model/tool spans for live runs.
This module adds a small append-only JSONL trace for deterministic preprocessing,
validation, and planner stages so one case can be debugged without logging the
meal request or model payloads locally.
"""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from threading import Lock
from typing import Any, Iterator, Mapping
from uuid import uuid4


TRACE_SCHEMA_VERSION = "1.0"
_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|authorization|credential|password|secret|token|raw[_-]?text|"
    r"source[_-]?text|visible[_-]?text|prompt|model[_-]?(?:input|output))",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")


@dataclass(frozen=True)
class TraceCorrelation:
    """Identifiers shared by local records and the Agents SDK trace."""

    logical_trace_id: str
    sdk_trace_id: str
    request_id: str
    case_id: str


def new_trace_correlation(
    request_id: str,
    case_id: str,
    *,
    logical_trace_id: str | None = None,
) -> TraceCorrelation:
    """Create one per-run correlation without embedding raw user text."""

    suffix = uuid4().hex[:12]
    logical = logical_trace_id or f"trace:{case_id[:72]}:{suffix}"
    if len(logical) > 128:
        logical = f"trace:group-food:{sha256(logical.encode('utf-8')).hexdigest()[:32]}"
    return TraceCorrelation(
        logical_trace_id=logical,
        sdk_trace_id=f"trace_{uuid4().hex}",
        request_id=request_id,
        case_id=case_id,
    )


def sdk_trace_id_from_logical(logical_trace_id: str) -> str:
    """Return an SDK-valid deterministic ID for independently invoked runs."""

    return f"trace_{sha256(logical_trace_id.encode('utf-8')).hexdigest()[:32]}"


def _safe_value(value: Any, *, key: str = "") -> Any:
    if _SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, str):
        return _SECRET_VALUE.sub("[REDACTED_SECRET]", value)[:500]
    if isinstance(value, Mapping):
        return {str(k): _safe_value(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_value(item, key=key) for item in value[:100]]
    return str(value)[:500]


class JsonlTraceWriter:
    """Thread-safe append-only trace writer with conservative redaction."""

    def __init__(self, path: str | Path, correlation: TraceCorrelation) -> None:
        self.path = Path(path).resolve()
        self.correlation = correlation
        self._lock = Lock()
        self._sequence = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        *,
        source: str,
        event_type: str,
        stage: str | int | None = None,
        name: str | None = None,
        status: str | None = None,
        occurred_at: datetime | None = None,
        duration_ms: int | None = None,
        correlation_id: str | None = None,
        profile_revision: int | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self._sequence += 1
            record = {
                "trace_schema_version": TRACE_SCHEMA_VERSION,
                "sequence": self._sequence,
                "occurred_at": (occurred_at or datetime.now(timezone.utc)).astimezone(
                    timezone.utc
                ).isoformat(),
                "source": source,
                "event_type": event_type,
                "status": status,
                "stage": stage,
                "name": name,
                "logical_trace_id": self.correlation.logical_trace_id,
                "sdk_trace_id": self.correlation.sdk_trace_id,
                "request_id": self.correlation.request_id,
                "case_id": self.correlation.case_id,
                "profile_revision": profile_revision,
                "correlation_id": correlation_id,
                "duration_ms": duration_ms,
                "data": _safe_value(dict(data or {})),
            }
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
                handle.write("\n")

    def write_pipeline_event(self, event: Any) -> None:
        self.write(
            source="input_pipeline",
            event_type=str(event.event_type.value),
            stage=str(event.stage.value),
            name=str(event.stage.value),
            status=_pipeline_status(str(event.event_type.value)),
            occurred_at=event.occurred_at,
            data=event.detail,
        )

    def write_tool_event(self, event: Any) -> None:
        self.write(
            source="deterministic_tool",
            event_type=str(event.event_type),
            stage=event.stage,
            name=event.tool_name,
            status={
                "tool_call": "started",
                "tool_result": "completed",
                "tool_error": "failed",
            }.get(str(event.event_type)),
            occurred_at=event.occurred_at,
            duration_ms=event.duration_ms,
            correlation_id=event.call_id,
            profile_revision=event.profile_revision,
            data={
                "event_id": event.event_id,
                "input_artifact_ids": event.input_artifact_ids,
                "output_artifact_ids": event.output_artifact_ids,
                "summary": event.summary,
                "error_type": event.error_type,
            },
        )


def _pipeline_status(event_type: str) -> str:
    if event_type.endswith("_started"):
        return "started"
    if event_type.endswith("_completed"):
        return "completed"
    if event_type.endswith("_blocked") or event_type.endswith("_failed"):
        return "failed"
    return "observed"


def build_agents_run_config(
    correlation: TraceCorrelation,
    *,
    workflow_name: str,
    use_explicit_trace_id: bool = False,
) -> Any:
    """Build a RunConfig that never exports sensitive model/tool payloads."""

    from agents import RunConfig

    return RunConfig(
        workflow_name=workflow_name,
        trace_id=correlation.sdk_trace_id if use_explicit_trace_id else None,
        group_id=correlation.case_id,
        trace_include_sensitive_data=False,
        trace_metadata={
            "logical_trace_id": correlation.logical_trace_id,
            "request_id": correlation.request_id,
            "case_id": correlation.case_id,
            "trace_schema_version": TRACE_SCHEMA_VERSION,
        },
    )


@contextmanager
def agents_trace_scope(
    correlation: TraceCorrelation,
    *,
    enabled: bool,
) -> Iterator[None]:
    """Group separate Interpreter and Main Planner runs into one SDK trace."""

    if not enabled:
        with nullcontext():
            yield
        return
    from agents import trace

    with trace(
        "group_food_quantity_agent",
        trace_id=correlation.sdk_trace_id,
        group_id=correlation.case_id,
        metadata={
            "logical_trace_id": correlation.logical_trace_id,
            "request_id": correlation.request_id,
            "case_id": correlation.case_id,
            "trace_schema_version": TRACE_SCHEMA_VERSION,
        },
    ):
        yield


def deterministic_tool_span(
    *,
    case_id: str,
    stage: int,
    tool_name: str,
    call_id: str,
    input_artifact_ids: list[str],
) -> Any:
    """Create an SDK custom span only when a live SDK trace is active."""

    try:
        from agents import custom_span, get_current_trace

        if get_current_trace() is not None:
            return custom_span(
                f"deterministic.{tool_name}",
                data={
                    "case_id": case_id,
                    "stage": stage,
                    "call_id": call_id,
                    "input_artifact_ids": input_artifact_ids,
                },
            )
    except ImportError:  # pragma: no cover - dependency is required by the project
        pass
    return nullcontext()


def summarize_trace(path: str | Path) -> dict[str, Any]:
    """Read a local trace into a concise failure/latency debugging summary."""

    records = [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    failures = [record for record in records if record.get("status") == "failed"]
    completed_tools = [
        record
        for record in records
        if record.get("source") == "deterministic_tool"
        and record.get("event_type") == "tool_result"
    ]
    slowest = sorted(
        completed_tools,
        key=lambda record: record.get("duration_ms") or -1,
        reverse=True,
    )[:5]
    return {
        "trace_file": str(Path(path).resolve()),
        "record_count": len(records),
        "logical_trace_id": records[0].get("logical_trace_id") if records else None,
        "sdk_trace_id": records[0].get("sdk_trace_id") if records else None,
        "sources": sorted({record.get("source") for record in records}),
        "failure_count": len(failures),
        "failures": [
            {
                "sequence": record.get("sequence"),
                "stage": record.get("stage"),
                "name": record.get("name"),
                "event_type": record.get("event_type"),
                "error_type": record.get("data", {}).get("error_type"),
            }
            for record in failures
        ],
        "slowest_completed_tools": [
            {
                "stage": record.get("stage"),
                "name": record.get("name"),
                "duration_ms": record.get("duration_ms"),
            }
            for record in slowest
        ],
    }
