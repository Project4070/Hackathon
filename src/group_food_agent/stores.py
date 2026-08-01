"""Narrow in-memory G7 stores used by the demo and deterministic tests.

The interfaces intentionally keep payloads separate from model prompts.  A
production database/cache can replace these classes without changing tool
schemas.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, TypeVar

from pydantic import BaseModel

from .contracts import PlanningIntakeV2
from .planner_contracts import PlannerRuntimePolicyV2, PlanningJobV2, default_runtime_policy
from .planner_models import (
    ArtifactRef,
    FeedbackAdjustmentV1,
    MealFeedbackV1,
    RestaurantSnapshotV1,
    ToolEventV1,
)


PayloadT = TypeVar("PayloadT", bound=BaseModel)
Clock = Callable[[], datetime]


def system_clock() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ArtifactRecord:
    ref: ArtifactRef
    payload: BaseModel


class ArtifactStore:
    """Append-only artifact store with revision-aware reads."""

    def __init__(self, clock: Clock = system_clock) -> None:
        self._clock = clock
        self._records: dict[str, ArtifactRecord] = {}
        self._case_artifacts: dict[str, list[str]] = defaultdict(list)

    def put(self, case_id: str, profile_revision: int, artifact_type: str, payload: PayloadT) -> ArtifactRef:
        serialized = payload.model_dump_json(exclude_none=False)
        digest = sha256(serialized.encode("utf-8")).hexdigest()[:12]
        ordinal = len(self._case_artifacts[case_id]) + 1
        artifact_id = f"{artifact_type}:{case_id}:r{profile_revision}:{ordinal}:{digest}"
        ref = ArtifactRef(
            case_id=case_id,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            profile_revision=profile_revision,
            created_at=self._clock(),
        )
        self._records[artifact_id] = ArtifactRecord(ref=ref, payload=payload)
        self._case_artifacts[case_id].append(artifact_id)
        return ref

    def get(self, artifact_id: str, expected_type: type[PayloadT] | None = None) -> PayloadT | BaseModel:
        try:
            record = self._records[artifact_id]
        except KeyError as exc:
            raise KeyError(f"unknown artifact id: {artifact_id}") from exc
        if expected_type is not None and not isinstance(record.payload, expected_type):
            raise TypeError(
                f"artifact {artifact_id} contains {type(record.payload).__name__}, "
                f"expected {expected_type.__name__}"
            )
        return record.payload

    def ref(self, artifact_id: str) -> ArtifactRef:
        return self._records[artifact_id].ref

    def latest_ref(self, case_id: str, artifact_type: str) -> ArtifactRef | None:
        for artifact_id in reversed(self._case_artifacts.get(case_id, [])):
            ref = self._records[artifact_id].ref
            if ref.artifact_type == artifact_type:
                return ref
        return None

    def assert_same_revision(self, *artifact_ids: str) -> int:
        revisions = {self.ref(artifact_id).profile_revision for artifact_id in artifact_ids}
        if len(revisions) != 1:
            raise ValueError("artifacts from different profile revisions cannot be combined")
        return revisions.pop()

    def refs_for_case(self, case_id: str) -> list[ArtifactRef]:
        return [self._records[artifact_id].ref for artifact_id in self._case_artifacts.get(case_id, [])]


@dataclass
class PlanningCaseState:
    job: PlanningJobV2
    unavailable_restaurant_ids: set[str] = field(default_factory=set)
    unavailable_menu_item_ids: set[str] = field(default_factory=set)
    demand_multiplier_basis_points: int = 10_000
    menu_serving_multipliers_basis_points: dict[str, int] = field(default_factory=dict)
    feedback: list[MealFeedbackV1] = field(default_factory=list)
    feedback_adjustments: list[FeedbackAdjustmentV1] = field(default_factory=list)


class PlanningCaseStore:
    def __init__(self) -> None:
        self._cases: dict[str, PlanningCaseState] = {}

    def create(self, job: PlanningJobV2) -> PlanningCaseState:
        case_id = job.intake.case_id
        if case_id in self._cases:
            raise ValueError(f"case already exists: {case_id}")
        state = PlanningCaseState(job=job)
        self._cases[case_id] = state
        return state

    def upsert_revision(self, job: PlanningJobV2) -> PlanningCaseState:
        case_id = job.intake.case_id
        existing = self._cases.get(case_id)
        if existing is None:
            return self.create(job)
        if job.intake.profile_revision <= existing.job.intake.profile_revision:
            raise ValueError("new planning job must have a greater profile revision")
        existing.job = job
        return existing

    def get(self, case_id: str) -> PlanningCaseState:
        try:
            return self._cases[case_id]
        except KeyError as exc:
            raise KeyError(f"unknown planning case: {case_id}") from exc


class RestaurantSnapshotCache:
    """Last-successful normalized snapshots keyed by immutable snapshot id."""

    def __init__(self) -> None:
        self._snapshots: dict[str, RestaurantSnapshotV1] = {}
        self._latest_id: str | None = None

    def put(self, snapshot: RestaurantSnapshotV1) -> None:
        self._snapshots[snapshot.snapshot_id] = snapshot
        if self._latest_id is None or snapshot.crawled_at >= self._snapshots[self._latest_id].crawled_at:
            self._latest_id = snapshot.snapshot_id

    def get(self, snapshot_id: str) -> RestaurantSnapshotV1:
        try:
            return self._snapshots[snapshot_id]
        except KeyError as exc:
            raise KeyError(f"restaurant snapshot unavailable: {snapshot_id}") from exc

    def latest(self) -> RestaurantSnapshotV1:
        if self._latest_id is None:
            raise LookupError("no usable restaurant snapshot exists")
        return self._snapshots[self._latest_id]


class EvidenceStore:
    def __init__(self) -> None:
        self._evidence: dict[str, BaseModel] = {}

    def put(self, evidence_id: str, evidence: BaseModel) -> None:
        if evidence_id in self._evidence and self._evidence[evidence_id] != evidence:
            raise ValueError(f"evidence id collision: {evidence_id}")
        self._evidence[evidence_id] = evidence

    def get(self, evidence_id: str) -> BaseModel:
        return self._evidence[evidence_id]


class PolicyRegistry:
    def __init__(self, default_policy: PlannerRuntimePolicyV2 | None = None) -> None:
        self._default = default_policy or default_runtime_policy()
        self._policies: dict[str, Any] = {
            self._default.serving_policy.serving_policy_id: self._default.serving_policy,
            self._default.serving_policy.quantity_policy_id: self._default.serving_policy,
            self._default.budget_policy.policy_id: self._default.budget_policy,
            self._default.restaurant_search.policy_id: self._default.restaurant_search,
            self._default.menu_filter.policy_id: self._default.menu_filter,
            self._default.combination.policy_id: self._default.combination,
            self._default.ranking.policy_id: self._default.ranking,
        }

    @property
    def default(self) -> PlannerRuntimePolicyV2:
        return self._default

    def get(self, policy_id: str) -> Any:
        try:
            return self._policies[policy_id]
        except KeyError as exc:
            raise KeyError(f"unknown policy id: {policy_id}") from exc


class ToolEventStore:
    def __init__(self) -> None:
        self._events: dict[str, list[ToolEventV1]] = defaultdict(list)

    def append(self, event: ToolEventV1) -> None:
        self._events[event.case_id].append(event)

    def for_case(self, case_id: str) -> list[ToolEventV1]:
        return list(self._events.get(case_id, []))


def job_from_intake(
    intake: PlanningIntakeV2,
    *,
    requested_at: datetime,
    trace_id: str,
    snapshot_id: str | None,
    policy: PlannerRuntimePolicyV2 | None = None,
) -> PlanningJobV2:
    """Create a planning job without reinterpreting the validated profile."""

    from .planner_contracts import PlannerExecutionContextV2, ResolvedLocationV2

    location = intake.profile.location_requirement
    return PlanningJobV2(
        intake=intake,
        runtime_policy=policy or default_runtime_policy(),
        execution_context=PlannerExecutionContextV2(
            requested_at=requested_at,
            resolved_location=ResolvedLocationV2(
                source=location.source,
                query=location.query,
                latitude=location.latitude,
                longitude=location.longitude,
            ),
            restaurant_snapshot_id=snapshot_id,
            trace_id=trace_id,
        ),
    )
