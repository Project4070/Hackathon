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
    SemanticTermV2,
    UnresolvedIssueKind,
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

    repaired_span = _whitespace_insensitive_span(raw_text, evidence.source_text)
    if repaired_span is not None:
        start, end = repaired_span
        return evidence.model_copy(
            update={
                "source_text": raw_text[start:end],
                "start_offset": start,
                "end_offset": end,
            }
        )

    # The caller discards an unrepairable citation. A missing material citation
    # is reconstructed from literal structured terms where possible or remains
    # a deterministic material-evidence blocker.
    return evidence.model_copy(update={"start_offset": None, "end_offset": None})


def _whitespace_insensitive_span(raw_text: str, phrase: str) -> tuple[int, int] | None:
    """Return one exact raw span when the only difference is whitespace."""

    compact_phrase = "".join(character for character in phrase if not character.isspace())
    if not compact_phrase:
        return None

    compact_raw: list[str] = []
    raw_indexes: list[int] = []
    for index, character in enumerate(raw_text):
        if not character.isspace():
            compact_raw.append(character)
            raw_indexes.append(index)

    compact_text = "".join(compact_raw)
    starts = _all_occurrences(compact_text, compact_phrase)
    if len(starts) != 1:
        return None
    compact_start = starts[0]
    compact_end = compact_start + len(compact_phrase) - 1
    return raw_indexes[compact_start], raw_indexes[compact_end] + 1


def _unique_id(existing: set[str], base: str) -> str:
    if base not in existing:
        existing.add(base)
        return base
    suffix = 2
    while f"{base}_{suffix}" in existing:
        suffix += 1
    value = f"{base}_{suffix}"
    existing.add(value)
    return value


def _default_group_id(candidate: MealRequestCandidateV2) -> str:
    existing = {group.group_id for group in candidate.party.groups}
    base = "group_default_remaining"
    if base not in existing:
        return base
    suffix = 2
    while f"{base}_{suffix}" in existing:
        suffix += 1
    return f"{base}_{suffix}"


def _exact_term_source(term: SemanticTermV2, raw_text: str) -> str | None:
    for phrase in (term.label, term.code):
        if phrase in raw_text:
            return phrase
    return None


def _append_explicit_evidence(
    evidence: list[EvidenceV2],
    existing_ids: set[str],
    *,
    base_id: str,
    field_path: str,
    source_text: str,
    raw_text: str,
    note: str,
) -> None:
    starts = _all_occurrences(raw_text, source_text)
    start = starts[0] if len(starts) == 1 else None
    evidence.append(
        EvidenceV2(
            evidence_id=_unique_id(existing_ids, base_id),
            field_path=field_path,
            source_text=source_text,
            status=EvidenceStatus.EXPLICIT,
            confidence=1.0,
            start_offset=start,
            end_offset=start + len(source_text) if start is not None else None,
            note=note,
        )
    )


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

    normalized_evidence = [
        _normalize_evidence_span(item, raw_text) for item in candidate.evidence
    ]
    evidence = [
        item
        for item in normalized_evidence
        if item.source_text is None or item.source_text in raw_text
    ]
    party = candidate.party
    defaulted_group_index: int | None = None
    completed_partial_groups = False
    if not party.groups:
        defaulted_group_index = 0
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
    else:
        group_sum = sum(group.count for group in party.groups)
        if (
            all(group.count > 0 for group in party.groups)
            and 0 < group_sum < party.total_count
        ):
            defaulted_group_index = len(party.groups)
            completed_partial_groups = True
            party = party.model_copy(
                update={
                    "groups": [
                        *party.groups,
                        ParticipantGroupV2(
                            group_id=_default_group_id(candidate),
                            display_label="Remaining attendees (default appetite)",
                            count=party.total_count - group_sum,
                            attendance_status=AttendanceStatus.CONFIRMED,
                            appetite=AppetiteProfileV2(
                                band=AppetiteBand.NORMAL,
                                stated_servings_milli=None,
                            ),
                            activity_level=ActivityLevel.UNKNOWN,
                            recent_meal_status=RecentMealStatus.UNKNOWN,
                        ),
                    ]
                }
            )

    existing_ids = {item.evidence_id for item in evidence}
    if defaulted_group_index is not None:
        defaulted_group = party.groups[defaulted_group_index]
        evidence.append(
            EvidenceV2(
                evidence_id=_unique_id(existing_ids, "default_party_group"),
                field_path=f"/party/groups/{defaulted_group_index}",
                source_text=None,
                status=EvidenceStatus.DEFAULTED,
                confidence=1.0,
                start_offset=None,
                end_offset=None,
                note=(
                    "Application-owned normal-appetite cohort for "
                    f"{defaulted_group.count} attendees not assigned to an explicit appetite group."
                ),
            )
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
                evidence_id=_unique_id(existing_ids, "default_party_group"),
                field_path="/party/groups",
                source_text=None,
                status=EvidenceStatus.DEFAULTED,
                confidence=1.0,
                start_offset=None,
                end_offset=None,
                note="Application-owned normal-appetite cohort derived from total participant count.",
            )
        )

    has_category_evidence = any(
        item.field_path == "/food_scope/requested_categories"
        or item.field_path.startswith("/food_scope/requested_categories/")
        for item in evidence
    )
    if not has_category_evidence:
        for index, term in enumerate(candidate.food_scope.requested_categories):
            source_text = _exact_term_source(term, raw_text)
            if source_text is None:
                continue
            _append_explicit_evidence(
                evidence,
                existing_ids,
                base_id=f"repaired_food_category_{index + 1}",
                field_path=f"/food_scope/requested_categories/{index}",
                source_text=source_text,
                raw_text=raw_text,
                note="Application reconstructed literal category evidence from the extracted term.",
            )

    unresolved_issues = candidate.unresolved_issues
    if completed_partial_groups:
        unresolved_issues = [
            issue
            for issue in unresolved_issues
            if not (
                issue.kind is not UnresolvedIssueKind.UNSUPPORTED
                and issue.field_path is not None
                and (
                    issue.field_path == "/party"
                    or issue.field_path.startswith("/party/")
                )
            )
        ]

    return candidate.model_copy(
        update={
            "party": party,
            "evidence": evidence,
            "unresolved_issues": unresolved_issues,
        }
    )
