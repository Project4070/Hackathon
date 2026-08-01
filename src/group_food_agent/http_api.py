"""Small HTTP adapter for the browser-observed Naver Place contract.

This is intentionally separate from the planner contracts.  Naver exposes
place/menu facts, but not enough verified information to build a safe order in
all cases.  The endpoint therefore returns explicit available/unavailable
field lists and never fills missing serving, allergy, fee, or delivery facts.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel, ConfigDict, Field

from .naver_planner_adapter import PlannerRestaurantV1, build_planner_restaurant_from_naver


DEMO_GEOCODES: dict[str, dict[str, Any]] = {
    # Coordinates supplied in the migration document.
    "신논현역": {
        "latitude": 37.502104,
        "longitude": 127.025869,
        "source": "documented_demo_coordinate",
    },
    "신촌": {
        "latitude": 37.5596,
        "longitude": 126.9370,
        "source": "reviewed_planner_fixture",
    },
}


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GeocodeResult(ApiModel):
    schema_name: str = "geocode_result"
    schema_version: str = "1.0"
    status: str
    query: str
    latitude: float | None = None
    longitude: float | None = None
    source: str | None = None
    data_mode: str
    available_fields: list[str] = Field(default_factory=list)
    unavailable_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RestaurantResult(ApiModel):
    id: str
    name: str
    category: str
    latitude: float
    longitude: float
    distanceMeters: int
    address: str | None
    phone: str | None
    naverMapUrl: str
    reviewCount: int | None
    delivery: dict[str, Any]
    quantityReview: dict[str, Any] | None
    menus: list[dict[str, Any]]
    menuStatus: str
    sourceUrl: str
    availableFields: list[str]
    unavailableFields: list[str]


class RestaurantsResult(ApiModel):
    schema_name: str = "restaurants_result"
    schema_version: str = "1.0"
    status: str
    query: str
    latitude: float
    longitude: float
    radiusMeters: int
    limit: int
    deliveryRequired: bool
    freshnessRequested: bool
    dataMode: str
    sourceSnapshot: str
    sourceCrawledAt: str
    availableFields: list[str]
    unavailableFields: list[str]
    warnings: list[str]
    restaurants: list[RestaurantResult]
    plannerRestaurants: list[PlannerRestaurantV1]


class ApiFailure(ApiModel):
    schema_name: str = "api_failure"
    schema_version: str = "1.0"
    status: str
    problematicField: str
    receivedValue: str
    reason: str
    correctiveAction: str


def _fixture_path() -> Path:
    return Path(__file__).resolve().parents[2] / "fixtures" / "naver_place_browser_sample_v1.json"


def _load_fixture() -> dict[str, Any]:
    with _fixture_path().open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _normal_key(value: str) -> str:
    return re.sub(r"\s+", "", value.casefold())


def _haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6_371_000.0
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _query_matches(record: dict[str, Any], query: str) -> bool:
    if query in {"맛집", "배달"}:
        return True
    haystack = " ".join(
        [
            str(record.get("name", "")),
            str(record.get("category", "")),
            *(str(menu.get("name", "")) for menu in record.get("menus", [])),
        ]
    )
    return _normal_key(query) in _normal_key(haystack)


def _quantity_review(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    participant_count = int(raw["participantCount"])
    selected_count = int(raw["selectedCount"])
    response_rate = round(selected_count / participant_count * 100, 1) if participant_count else None
    return {
        "keyword": raw["keyword"],
        "keywordCode": raw["keywordCode"],
        "threshold": 50,
        "eligible": int(raw["sourceReviewCount"]) >= 50,
        "status": "available" if int(raw["sourceReviewCount"]) >= 50 else "below_threshold",
        "sourceReviewCount": int(raw["sourceReviewCount"]),
        "rank": int(raw["rank"]),
        "previousRank": raw.get("previousRank"),
        "selectedCount": selected_count,
        "participantCount": participant_count,
        "responseRatePercent": response_rate,
        "totalVoteCount": int(raw["totalVoteCount"]),
        "keywordReviewCount": int(raw["keywordReviewCount"]),
    }


def _normalize_restaurant(raw: dict[str, Any], lat: float, lng: float) -> RestaurantResult:
    distance = round(_haversine_meters(lat, lng, float(raw["y"]), float(raw["x"])))
    menus: list[dict[str, Any]] = []
    for menu in raw.get("menus", []):
        menus.append(
            {
                "id": str(menu["id"]),
                "name": menu["name"],
                "price": menu.get("price"),
                "priceText": menu.get("priceText"),
                "description": menu.get("description") or "",
                "recommended": bool(menu.get("recommended", False)),
                "images": list(menu.get("images", [])),
                "estimatedServings": None,
                "unavailableFields": [
                    "estimatedServings",
                    "pieceCount",
                    "pizzaDiameterCm",
                    "sliceCount",
                    "vegetarianStatus",
                    "allergenTags",
                    "spiceLevel",
                    "availability",
                    "saleUnit",
                ],
            }
        )
    delivery = raw.get("naverOrder", {})
    return RestaurantResult(
        id=str(raw["id"]),
        name=raw["name"],
        category=raw["category"],
        latitude=float(raw["y"]),
        longitude=float(raw["x"]),
        distanceMeters=distance,
        address=raw.get("roadAddress") or raw.get("address"),
        phone=raw.get("virtualPhone") or raw.get("phone"),
        naverMapUrl=f"https://map.naver.com/p/entry/place/{raw['id']}",
        reviewCount=int(raw["totalReviewCount"]) if raw.get("totalReviewCount") is not None else None,
        delivery={
            "confirmed": bool(delivery.get("isDelivery", False)),
            "provider": "naver-order",
            "pickupAvailable": bool(delivery.get("isPickup", False)),
        },
        quantityReview=_quantity_review(raw.get("quantityReview")),
        menus=menus,
        menuStatus="available" if menus else "unavailable",
        sourceUrl=raw["source_url"],
        availableFields=[
            "id",
            "name",
            "category",
            "x",
            "y",
            "distance",
            "roadAddress",
            "address",
            "virtualPhone",
            "phone",
            "totalReviewCount",
            "naverOrder.isDelivery",
            "naverOrder.isPickup",
            "menu.id",
            "menu.name",
            "menu.price",
            "menu.priceText",
            "menu.description",
            "menu.recommended",
            "menu.images",
        ],
        unavailableFields=[
            "branch",
            "minimumOrder",
            "deliveryFee",
            "estimatedDeliveryMinutes",
            "deliveryCoverageForTargetAddress",
            "menu.estimatedServings",
            "menu.saleUnit",
            "menu.pieceCount",
            "menu.pizzaDiameterCm",
            "menu.sliceCount",
            "menu.vegetarianStatus",
            "menu.allergenTags",
            "menu.spiceLevel",
            "menu.availability",
        ],
    )


def _parse_bool(query: dict[str, list[str]], key: str, default: bool) -> bool:
    value = query.get(key, ["1" if default else "0"])[0]
    if value not in {"0", "1"}:
        raise ValueError(f"{key} must be 0 or 1")
    return value == "1"


def _parse_float(query: dict[str, list[str]], key: str) -> float:
    value = query.get(key, [""])[0]
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"{key} must be finite")
    return parsed


def geocode(query: str) -> GeocodeResult | ApiFailure:
    clean = query.strip()
    if not clean:
        return ApiFailure(
            status="invalid",
            problematicField="q",
            receivedValue=query,
            reason="검색어가 비어 있습니다.",
            correctiveAction="주소 또는 장소명을 입력하세요.",
        )
    match = DEMO_GEOCODES.get(clean)
    if match is None:
        return ApiFailure(
            status="data_unavailable",
            problematicField="q",
            receivedValue=clean,
            reason="현재 실행 경로에는 이 장소의 지오코딩 결과가 없습니다.",
            correctiveAction="신논현역 또는 신촌을 사용하거나 실제 geocoder adapter를 연결하세요.",
        )
    return GeocodeResult(
        status="resolved",
        query=clean,
        latitude=match["latitude"],
        longitude=match["longitude"],
        source=match["source"],
        data_mode="configured_demo_fixture",
        available_fields=["query", "latitude", "longitude"],
        unavailable_fields=["delivery_area", "address_precision", "fresh_live_provider_confirmation"],
        warnings=["이 응답은 현재 실행 가능한 데모 지오코드 fixture이며 실시간 geocoder 호출이 아닙니다."],
    )


def restaurants(params: dict[str, list[str]]) -> RestaurantsResult | ApiFailure:
    try:
        lat = _parse_float(params, "lat")
        lng = _parse_float(params, "lng")
        limit = int(params.get("limit", ["10"])[0])
        radius = int(params.get("radius", ["1000"])[0])
        delivery = _parse_bool(params, "delivery", True)
        fresh = _parse_bool(params, "fresh", False)
    except (KeyError, TypeError, ValueError) as exc:
        return ApiFailure(
            status="invalid",
            problematicField="query",
            receivedValue=json.dumps(params, ensure_ascii=False),
            reason=str(exc),
            correctiveAction="lat/lng를 넣고 limit은 1~20, radius는 100~5000, delivery/fresh는 0 또는 1로 보내세요.",
        )
    if not (-90 <= lat <= 90):
        return ApiFailure(status="invalid", problematicField="lat", receivedValue=str(lat), reason="위도 범위를 벗어났습니다.", correctiveAction="-90~90 범위의 위도를 입력하세요.")
    if not (-180 <= lng <= 180):
        return ApiFailure(status="invalid", problematicField="lng", receivedValue=str(lng), reason="경도 범위를 벗어났습니다.", correctiveAction="-180~180 범위의 경도를 입력하세요.")
    if not 1 <= limit <= 20:
        return ApiFailure(status="invalid", problematicField="limit", receivedValue=str(limit), reason="limit은 1~20이어야 합니다.", correctiveAction="limit을 1~20으로 수정하세요.")
    if not 100 <= radius <= 5000:
        return ApiFailure(status="invalid", problematicField="radius", receivedValue=str(radius), reason="radius는 100~5000이어야 합니다.", correctiveAction="radius를 100~5000으로 수정하세요.")

    query = params.get("q", ["맛집"])[0].strip() or "맛집"
    fixture = _load_fixture()
    candidates: list[RestaurantResult] = []
    for raw in fixture["restaurants"]:
        item = _normalize_restaurant(raw, lat, lng)
        if item.distanceMeters > radius:
            continue
        if delivery and not item.delivery["confirmed"]:
            continue
        if not _query_matches(raw, query):
            continue
        candidates.append(item)
    candidates.sort(key=lambda item: (item.distanceMeters, item.id))
    selected = candidates[:limit]
    selected_ids = {item.id for item in selected}
    planner_restaurants = [
        build_planner_restaurant_from_naver(
            raw,
            location_id="location:request",
            location_query=query,
            request_latitude=lat,
            request_longitude=lng,
            radius_meters=radius,
            delivery_required=delivery,
        )
        for raw in fixture["restaurants"]
        if str(raw["id"]) in selected_ids
    ]
    status = "ok" if selected else "no_candidates"
    warnings = [fixture["warning"]]
    if fresh:
        warnings.append("fresh=1은 live refresh 요청으로 기록되지만, 현재는 browser-observed fixture fallback을 사용했습니다.")
    if delivery and not selected:
        warnings.append("확인된 스냅샷의 naverOrder.isDelivery가 모두 false라 delivery=1 후보가 없습니다.")
    return RestaurantsResult(
        status=status,
        query=query,
        latitude=lat,
        longitude=lng,
        radiusMeters=radius,
        limit=limit,
        deliveryRequired=delivery,
        freshnessRequested=fresh,
        dataMode=fixture["data_mode"],
        sourceSnapshot=fixture["source_url"],
        sourceCrawledAt=fixture["observed_at"],
        availableFields=[
            "id",
            "name",
            "category",
            "x",
            "y",
            "distance",
            "roadAddress",
            "address",
            "virtualPhone",
            "phone",
            "totalReviewCount",
            "naverOrder.isDelivery",
            "naverOrder.isPickup",
            "menu.id",
            "menu.name",
            "menu.price",
            "menu.priceText",
            "menu.description",
            "menu.recommended",
            "menu.images",
            "VisitorReviewStatsResult.analysis.votedKeyword",
        ],
        unavailableFields=[
            "branch",
            "minimumOrder",
            "deliveryFee",
            "estimatedDeliveryMinutes",
            "deliveryCoverageForTargetAddress",
            "menu.estimatedServings",
            "menu.saleUnit",
            "menu.pieceCount",
            "menu.pizzaDiameterCm",
            "menu.sliceCount",
            "menu.vegetarianStatus",
            "menu.allergenTags",
            "menu.spiceLevel",
            "menu.availability",
        ],
        warnings=warnings,
        restaurants=selected,
        plannerRestaurants=planner_restaurants,
    )


def _json_bytes(value: BaseModel) -> bytes:
    return json.dumps(value.model_dump(mode="json"), ensure_ascii=False).encode("utf-8")


async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    if scope.get("type") != "http":
        return
    method = scope.get("method", "GET")
    path = scope.get("path", "")
    if method != "GET":
        payload: BaseModel = ApiFailure(status="unsupported", problematicField="method", receivedValue=method, reason="GET만 지원합니다.", correctiveAction="GET으로 재시도하세요.")
        status_code = 405
    else:
        query = parse_qs(scope.get("query_string", b"").decode("utf-8"), keep_blank_values=True)
        if path == "/health":
            payload = GeocodeResult(status="ok", query="health", data_mode="local", available_fields=["status"], unavailable_fields=[])
            status_code = 200
        elif path == "/api/geocode":
            payload = geocode(query.get("q", [""])[0])
            status_code = 200 if not isinstance(payload, ApiFailure) else 400
        elif path == "/api/restaurants":
            payload = restaurants(query)
            status_code = 200 if not isinstance(payload, ApiFailure) else 400
        else:
            payload = ApiFailure(status="not_found", problematicField="path", receivedValue=path, reason="지원하지 않는 endpoint입니다.", correctiveAction="/health, /api/geocode, /api/restaurants 중 하나를 사용하세요.")
            status_code = 404
    body = _json_bytes(payload)
    await send({"type": "http.response.start", "status": status_code, "headers": [[b"content-type", b"application/json; charset=utf-8"], [b"content-length", str(len(body)).encode("ascii")]]})
    await send({"type": "http.response.body", "body": body})


def main() -> None:
    import uvicorn

    uvicorn.run("group_food_agent.http_api:app", host="127.0.0.1", port=3000, reload=False)


if __name__ == "__main__":
    main()
