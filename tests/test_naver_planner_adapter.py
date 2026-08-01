from copy import deepcopy
from datetime import datetime, timezone

import pytest

from group_food_agent.http_api import _load_fixture
from group_food_agent.naver_planner_adapter import (
    PlannerStatus,
    build_planner_restaurant_from_naver,
)
from group_food_agent.planner_models import ConfidenceLabel, ServingEvidenceV1


def _build(raw: dict, **kwargs):
    return build_planner_restaurant_from_naver(
        raw,
        location_id="location:demo",
        location_query="신논현역",
        request_latitude=37.502104,
        request_longitude=127.025869,
        **kwargs,
    )


def test_naver_sample_has_stable_identity_location_join_and_explicit_blockers():
    raw = _load_fixture()["restaurants"][0]

    result = _build(raw, delivery_required=False)

    assert result.restaurant_id == "restaurant:naver:37021055"
    assert result.menu_items[0].menu_item_id == "menu:naver:37021055:37021055_0"
    assert result.location_join.candidate_id == "candidate:location:demo:restaurant:naver:37021055"
    assert result.location_join.distance_meters == 180
    assert result.planning_status is PlannerStatus.INSUFFICIENT_DATA
    assert "missing_serving_evidence" in {issue.code for issue in result.issues}
    assert result.quantity_review is not None
    assert result.quantity_review.rank == 3


def test_only_explicit_enrichment_can_make_record_convertible_to_existing_planner():
    raw = deepcopy(_load_fixture()["restaurants"][0])
    raw["category"] = "치킨"
    raw["branch"] = "강남점"
    raw["naverOrder"] = {"isDelivery": True, "isPickup": True}
    evidence = {
        menu["id"]: ServingEvidenceV1(
            evidence_id=f"evidence:{menu['id']}",
            source_url=raw["source_url"],
            source_text="공식 판매 단위 1인분",
            practical_servings_min_milli=1_000,
            practical_servings_max_milli=1_000,
            selected_servings_milli=1_000,
            confidence=ConfidenceLabel.MEDIUM,
            observation_count=1,
            reviewed=True,
        )
        for menu in raw["menus"]
    }

    result = _build(
        raw,
        delivery_required=True,
        delivery_queries=["신논현역"],
        minimum_order_minor=0,
        delivery_fee_minor=0,
        service_fee_minor=0,
        estimated_delivery_minutes=30,
        serving_evidence_by_menu_id=evidence,
        sale_unit_by_menu_id={menu["id"]: "1인분" for menu in raw["menus"]},
    )

    assert result.planning_status is PlannerStatus.READY
    converted = result.to_restaurant_v1()
    assert converted.restaurant_id == result.restaurant_id
    assert converted.menu_items[0].serving_evidence.selected_servings_milli == 1_000


def test_insufficient_record_cannot_enter_calculator():
    raw = _load_fixture()["restaurants"][0]
    result = _build(raw, delivery_required=False)

    with pytest.raises(ValueError, match="not planner-ready"):
        result.to_restaurant_v1()
