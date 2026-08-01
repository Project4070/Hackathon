import io
from datetime import UTC, datetime

import pytest
from PIL import Image
from starlette.testclient import TestClient

from group_food_agent.contracts import UnresolvedIssueKind, UnresolvedIssueV2
from group_food_agent.multimodal import (
    MultimodalContextV1,
    MultimodalMealRequestCandidateV1,
    ObservationEvidenceV1,
    ObservedFoodV1,
    SceneAnalysisV1,
    calculate_existing_food_credit,
    merge_multimodal_candidate,
    normalize_image,
)
from group_food_agent.intake_normalization import normalize_candidate_for_validation
from group_food_agent.web_app import app
from group_food_agent.validation import ValidationContextV2, validate_planning_profile


def _scene(food: ObservedFoodV1) -> SceneAnalysisV1:
    return SceneAnalysisV1(
        image_id="image:test",
        image_provided=True,
        visible_people=5,
        visible_people_confidence=0.95,
        visible_people_evidence=ObservationEvidenceV1(
            evidence_id="people:test",
            modality="image",
            status="inferred",
            confidence=0.95,
        ),
        additional_people=0,
        explicit_total_people=5,
        existing_food=[food],
        meal_context="dinner",
        meal_context_confidence=0.8,
        environment_label="meeting room",
        warnings=[],
    )


def _food(confidence: float = 0.9, *, category: str = "chicken") -> ObservedFoodV1:
    return ObservedFoodV1(
        observation_id="food:test",
        category_code=category,
        label="치킨",
        unit="whole",
        estimated_units_min=1,
        estimated_units_max=1,
        remaining_ratio_min=0.5,
        remaining_ratio_max=0.8,
        condition="partially_eaten",
        evidence=ObservationEvidenceV1(
            evidence_id="food-evidence:test",
            modality="image",
            status="inferred",
            confidence=confidence,
        ),
    )


def test_image_normalization_strips_to_bounded_jpeg_data_url():
    source = io.BytesIO()
    Image.new("RGB", (2200, 1200), "orange").save(source, format="PNG")

    normalized = normalize_image(source.getvalue())

    assert normalized.image_id.startswith("image:")
    assert normalized.media_type == "image/jpeg"
    assert normalized.width == 1600
    assert normalized.data_url.startswith("data:image/jpeg;base64,")


def test_image_normalization_rejects_oversized_and_unsupported_files():
    with pytest.raises(ValueError, match="8 MiB"):
        normalize_image(b"x" * (8 * 1024 * 1024 + 1))

    unsupported = io.BytesIO()
    Image.new("RGB", (20, 20), "orange").save(unsupported, format="GIF")
    with pytest.raises(ValueError, match="JPEG, PNG, or WebP"):
        normalize_image(unsupported.getvalue())


def test_existing_food_credit_uses_conservative_reviewed_lower_bound():
    credit = calculate_existing_food_credit(_scene(_food()))

    assert credit.total_credited_servings_milli == 1250
    assert credit.protected_demand_credit_milli == 0
    assert credit.lines[0].accepted is True
    assert credit.lines[0].reference_source_url


def test_low_confidence_existing_food_is_not_credited():
    credit = calculate_existing_food_credit(_scene(_food(0.61)))

    assert credit.total_credited_servings_milli == 0
    assert credit.lines[0].accepted is False


def test_unknown_existing_food_is_not_invented():
    credit = calculate_existing_food_credit(_scene(_food(category="unknown_food")))

    assert credit.total_credited_servings_milli == 0
    assert credit.lines[0].reference_source_url is None


def test_explicit_total_overrides_model_arithmetic_without_changing_protected_groups(canonical_candidate):
    scene = _scene(_food()).model_copy(update={
        "visible_people": 15,
        "additional_people": 2,
        "explicit_total_people": 17,
    })
    interpreted = MultimodalMealRequestCandidateV1(
        request_candidate=canonical_candidate,
        scene_analysis=scene,
        conflict_resolutions=[],
    )
    context = MultimodalContextV1(
        captured_at=datetime.now(UTC),
        timezone_offset_minutes=540,
        location_permission="unavailable",
    )
    protected_ids = {
        group_id
        for requirement in canonical_candidate.hard_requirements
        for group_id in requirement.affected_group_ids
    }
    protected_before = {
        group.group_id: group.count
        for group in canonical_candidate.party.groups
        if group.group_id in protected_ids
    }

    merged = merge_multimodal_candidate(interpreted, context)

    assert merged.party.total_count == 17
    assert sum(group.count for group in merged.party.groups) == 17
    assert {
        group.group_id: group.count
        for group in merged.party.groups
        if group.group_id in protected_ids
    } == protected_before
    assert not any(issue.issue_id == "scene_party_total_conflict" for issue in merged.unresolved_issues)


def test_medium_confidence_people_count_requires_confirmation(canonical_candidate):
    scene = _scene(_food()).model_copy(update={
        "visible_people": 15,
        "visible_people_confidence": 0.7,
        "additional_people": 0,
        "explicit_total_people": None,
    })
    interpreted = MultimodalMealRequestCandidateV1(
        request_candidate=canonical_candidate,
        scene_analysis=scene,
        conflict_resolutions=[],
    )
    context = MultimodalContextV1(
        captured_at=datetime.now(UTC),
        timezone_offset_minutes=540,
        location_permission="denied",
    )

    merged = merge_multimodal_candidate(interpreted, context)

    assert any(issue.issue_id == "scene_people_confirmation" for issue in merged.unresolved_issues)


def test_photo_total_gets_intake_evidence_when_model_omits_it(canonical_candidate, canonical_raw_text):
    candidate_without_total_evidence = canonical_candidate.model_copy(update={
        "evidence": [
            evidence
            for evidence in canonical_candidate.evidence
            if evidence.field_path != "/party/total_count"
        ]
    })
    scene = _scene(_food()).model_copy(update={
        "visible_people": 15,
        "additional_people": 0,
        "explicit_total_people": None,
    })
    interpreted = MultimodalMealRequestCandidateV1(
        request_candidate=candidate_without_total_evidence,
        scene_analysis=scene,
        conflict_resolutions=[],
    )
    context = MultimodalContextV1(
        captured_at=datetime.now(UTC),
        timezone_offset_minutes=540,
        location_permission="unavailable",
    )

    merged = merge_multimodal_candidate(interpreted, context, raw_notes=canonical_raw_text)
    total_evidence = [
        evidence for evidence in merged.evidence if evidence.field_path == "/party/total_count"
    ]
    outcome = validate_planning_profile(
        merged,
        ValidationContextV2(request_id="request-photo", case_id="case-photo"),
        raw_text=canonical_raw_text,
    )

    assert len(total_evidence) == 1
    assert total_evidence[0].status == "explicit"
    assert total_evidence[0].source_text == "15명"
    assert total_evidence[0].confidence == 1.0
    assert outcome.status == "ready_for_planning"


def test_explicit_total_bridge_uses_only_verbatim_user_evidence(canonical_candidate):
    notes = "사진에는 열다섯 명이지만 총 17명이 참석해요."
    scene = _scene(_food()).model_copy(update={
        "visible_people": 15,
        "additional_people": 2,
        "explicit_total_people": 17,
    })
    interpreted = MultimodalMealRequestCandidateV1(
        request_candidate=canonical_candidate.model_copy(update={
            "evidence": [
                evidence
                for evidence in canonical_candidate.evidence
                if evidence.field_path != "/party/total_count"
            ]
        }),
        scene_analysis=scene,
        conflict_resolutions=[{
            "field_path": "/party/total_count",
            "image_value": "15",
            "accepted_value": "17",
            "source_text": "총 17명이 참석해요",
            "reason": "explicit_total_overrode_derived_total",
        }],
    )
    context = MultimodalContextV1(
        captured_at=datetime.now(UTC),
        timezone_offset_minutes=540,
        location_permission="unavailable",
    )

    merged = merge_multimodal_candidate(interpreted, context, raw_notes=notes)
    total_evidence = next(
        evidence for evidence in merged.evidence if evidence.field_path == "/party/total_count"
    )

    assert total_evidence.status == "explicit"
    assert total_evidence.source_text == "총 17명이 참석해요"
    assert notes[total_evidence.start_offset:total_evidence.end_offset] == total_evidence.source_text


def test_unusable_photo_defaults_model_invented_appetite_and_asks_only_for_count(
    canonical_candidate,
    canonical_raw_text,
):
    groups = [
        group.model_copy(update={
            "appetite": group.appetite.model_copy(update={
                "band": "custom",
                "stated_servings_milli": None,
            })
        })
        for group in canonical_candidate.party.groups
    ]
    food_scope = canonical_candidate.food_scope.model_copy(update={
        "requested_categories": [],
    })
    candidate = canonical_candidate.model_copy(update={
        "party": canonical_candidate.party.model_copy(update={"groups": groups}),
        "food_scope": food_scope,
        "evidence": [
            evidence
            for evidence in canonical_candidate.evidence
            if evidence.field_path != "/party/total_count"
        ],
        "unresolved_issues": [
            UnresolvedIssueV2(
                issue_id="missing-food",
                kind=UnresolvedIssueKind.MISSING,
                field_path="/food_scope/requested_categories",
                message="요청한 음식 종류가 제공되지 않았습니다.",
                source_text=None,
            )
        ],
    })
    scene = _scene(_food()).model_copy(update={
        "visible_people": None,
        "visible_people_confidence": 0.0,
        "visible_people_evidence": None,
        "explicit_total_people": None,
    })
    interpreted = MultimodalMealRequestCandidateV1(
        request_candidate=candidate,
        scene_analysis=scene,
        conflict_resolutions=[],
    )
    context = MultimodalContextV1(
        captured_at=datetime.now(UTC),
        timezone_offset_minutes=540,
        location_permission="unavailable",
    )
    raw_text = canonical_raw_text.replace("동아리원 15명이", "동아리원 여러 명이").replace(
        "치킨과 피자를 모두 원합니다. ", ""
    )

    merged = merge_multimodal_candidate(interpreted, context, raw_notes=raw_text)
    normalized = normalize_candidate_for_validation(merged, raw_text)
    outcome = validate_planning_profile(
        normalized,
        ValidationContextV2(request_id="request-unusable", case_id="case-unusable"),
        raw_text=raw_text,
    )

    assert all(group.appetite.band == "normal" for group in normalized.party.groups)
    assert normalized.food_scope.requested_categories == []
    assert normalized.food_scope.category_selection == "any_of"
    assert [issue.issue_id for issue in normalized.unresolved_issues] == ["scene_people_unusable"]
    assert outcome.status == "clarification_required"
    assert all(issue.code != "custom_appetite_value_missing" for issue in outcome.issues)
    assert all(issue.code != "material_evidence_missing" for issue in outcome.issues)
    assert len(outcome.issues) == 1


def test_offline_web_run_exposes_scene_trace_and_sanitized_path():
    with TestClient(app) as client:
        response = client.post("/api/runs", data={"run_mode": "offline_canonical", "notes": ""})

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution"]["status"] == "succeeded"
    assert payload["scene_analysis"]["image_id"] == "image:offline-reviewed-fixture"
    assert payload["context_used"]["history"]["data_mode"] == "seeded_demo_history"
    assert payload["pipeline_events"][0]["stage"] == "multimodal_interpreter"
    assert "\\" not in payload["trace"]["local_trace_file"]


def test_web_rejects_empty_live_request():
    with TestClient(app) as client:
        response = client.post("/api/runs", json={"text": "", "run_mode": "live"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_input"


def test_web_rejects_declared_oversized_request_before_parsing():
    with TestClient(app) as client:
        response = client.post(
            "/api/runs",
            content=b"{}",
            headers={"content-type": "application/json", "content-length": str(10 * 1024 * 1024 + 1)},
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"


def test_web_rejects_malformed_json_and_corrupt_photo():
    with TestClient(app) as client:
        malformed = client.post("/api/runs", content=b"{", headers={"content-type": "application/json"})
        corrupt = client.post(
            "/api/runs",
            data={"notes": "20명 새우 주문", "run_mode": "live"},
            files={"photo": ("scene.jpg", b"not-an-image", "image/jpeg")},
        )

    assert malformed.status_code == 400
    assert malformed.json()["error"]["code"] == "invalid_request"
    assert corrupt.status_code == 400
    assert corrupt.json()["error"]["code"] == "invalid_input"


def test_security_headers_block_script_injection_surfaces():
    with TestClient(app) as client:
        response = client.get("/")

    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_frontend_never_uses_html_injection():
    script = (app.routes[1].endpoint.__globals__["STATIC_DIR"] / "app.js").read_text(encoding="utf-8")
    assert "innerHTML" not in script
