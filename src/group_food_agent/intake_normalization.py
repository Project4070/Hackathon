"""Deterministic cleanup between model extraction and admission validation."""

from __future__ import annotations

from .contracts import (
    ActivityLevel,
    AppetiteBand,
    AppetiteProfileV2,
    AttendanceStatus,
    EvidenceStatus,
    EvidenceV2,
    MealRequestCandidateV2,
    ParticipantGroupV2,
    RecentMealStatus,
)


def _all_occurrences(raw_text: str, phrase: str) -> list[int]:
    starts: list[int] = []
    offset = 0
    while True:
        start = raw_text.find(phrase, offset)
        if start < 0:
            return starts
        starts.append(start)
        offset = start + 1


def _normalize_evidence_span(evidence: EvidenceV2, raw_text: str) -> EvidenceV2:
    """Derive exact Unicode-code-point offsets instead of trusting model math."""

    if evidence.source_text is None:
        return evidence.model_copy(update={"start_offset": None, "end_offset": None})

    starts = _all_occurrences(raw_text, evidence.source_text)
    if len(starts) == 1:
        start = starts[0]
        return evidence.model_copy(
            update={"start_offset": start, "end_offset": start + len(evidence.source_text)}
        )

    if (
        evidence.start_offset is not None
        and evidence.end_offset is not None
        and raw_text[evidence.start_offset : evidence.end_offset] == evidence.source_text
    ):
        return evidence

    # Ambiguous or absent text remains validator-visible without fabricated span
    # precision. The validator separately rejects source text absent from input.
    return evidence.model_copy(update={"start_offset": None, "end_offset": None})


def _default_group_evidence_id(candidate: MealRequestCandidateV2) -> str:
    existing = {evidence.evidence_id for evidence in candidate.evidence}
    base = "default_party_group"
    if base not in existing:
        return base
    suffix = 2
    while f"{base}_{suffix}" in existing:
        suffix += 1
    return f"{base}_{suffix}"


def _is_default_compatible_group(group: ParticipantGroupV2, total_count: int) -> bool:
    return (
        group.count == total_count
        and group.appetite.band is AppetiteBand.NORMAL
        and group.appetite.stated_servings_milli is None
        and group.activity_level is ActivityLevel.UNKNOWN
        and group.recent_meal_status is RecentMealStatus.UNKNOWN
        and group.attendance_status in {AttendanceStatus.CONFIRMED, AttendanceStatus.EXPECTED}
    )


def normalize_candidate_for_validation(
    candidate: MealRequestCandidateV2,
    raw_text: str,
) -> MealRequestCandidateV2:
    """Normalize spans and disclose application-owned default group derivation."""

    evidence = [_normalize_evidence_span(item, raw_text) for item in candidate.evidence]
    party = candidate.party
    if not party.groups:
        party = party.model_copy(
            update={
                "groups": [
                    ParticipantGroupV2(
                        group_id="group_default",
                        display_label="All attendees (default appetite)",
                        count=party.total_count,
                        attendance_status=AttendanceStatus.CONFIRMED,
                        appetite=AppetiteProfileV2(
                            band=AppetiteBand.NORMAL,
                            stated_servings_milli=None,
                        ),
                        activity_level=ActivityLevel.UNKNOWN,
                        recent_meal_status=RecentMealStatus.UNKNOWN,
                    )
                ]
            }
        )

    has_group_evidence = any(
        item.field_path == "/party/groups" or item.field_path.startswith("/party/groups/")
        for item in evidence
    )
    if (
        not has_group_evidence
        and len(party.groups) == 1
        and _is_default_compatible_group(party.groups[0], party.total_count)
    ):
        evidence.append(
            EvidenceV2(
                evidence_id=_default_group_evidence_id(candidate),
                field_path="/party/groups",
                source_text=None,
                status=EvidenceStatus.DEFAULTED,
                confidence=1.0,
                start_offset=None,
                end_offset=None,
                note="Application-owned normal-appetite cohort derived from total participant count.",
            )
        )

    return candidate.model_copy(update={"party": party, "evidence": evidence})
