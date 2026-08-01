"""Three-stage adapter from Naver Place facts to the final planner contract.

The adapter deliberately keeps source identity, location membership, and
planner readiness separate.  A public Place page can identify a restaurant
without providing enough verified information for quantity planning.  Such a
record remains useful for discovery, but cannot be converted into the legacy
``RestaurantV1`` calculator input until the missing facts are supplied.
"""

from __future__ import annotations

import hashlib
import math
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from .contracts import ContractModel, Identifier
from .planner_models import (
    AvailabilityStatus,
    ConfidenceLabel,
    MenuItemV1,
    RestaurantV1,
    SemanticFieldStatus,
    SemanticProvenanceV1,
    ServingEvidenceV1,
    SpiceLevel,
    VegetarianStatus,
)


ShortText = Annotated[str, StringConstraints(min_length=1, max_length=500)]
MoneyMinorNullable = Annotated[int, Field(strict=True, ge=0, le=10_000_000_000)] | None


class PlannerStatus(StrEnum):
    READY = "ready"
    INSUFFICIENT_DATA = "insufficient_data"


class IssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class PlannerDataIssueV1(ContractModel):
    code: Annotated[str, StringConstraints(min_length=1, max_length=80, pattern=r"^[a-z0-9_]+$")]
    field_path: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    severity: IssueSeverity
    reason: ShortText
    corrective_action: ShortText


class NaverOrderFactsV1(ContractModel):
    is_delivery: bool = False
    is_pickup: bool = False


class NaverQuantityReviewFactsV1(ContractModel):
    source_review_count: Annotated[int, Field(strict=True, ge=0)]
    total_vote_count: Annotated[int, Field(strict=True, ge=0)] | None = None
    keyword_review_count: Annotated[int, Field(strict=True, ge=0)] | None = None
    participant_count: Annotated[int, Field(strict=True, ge=0)] | None = None
    keyword: ShortText
    keyword_code: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    selected_count: Annotated[int, Field(strict=True, ge=0)] | None = None
    rank: Annotated[int, Field(strict=True, ge=1)] | None = None
    previous_rank: Annotated[int, Field(strict=True, ge=1)] | None = None


class NaverMenuFactsV1(ContractModel):
    source_menu_id: Identifier
    name: ShortText
    price_minor: MoneyMinorNullable = None
    price_text: Annotated[str, StringConstraints(max_length=100)] | None = None
    description: Annotated[str, StringConstraints(max_length=500)] = ""
    recommended: bool = False
    images: Annotated[list[str], Field(max_length=10)] = []


class NaverPlaceFactsV1(ContractModel):
    """Validated, source-shaped facts accepted by the adapter."""

    source_restaurant_id: Identifier
    name: ShortText
    category: ShortText
    longitude: float = Field(allow_inf_nan=False, ge=-180, le=180)
    latitude: float = Field(allow_inf_nan=False, ge=-90, le=90)
    road_address: Annotated[str, StringConstraints(max_length=300)] = ""
    address: Annotated[str, StringConstraints(max_length=300)] = ""
    branch: Annotated[str, StringConstraints(max_length=200)] | None = None
    source_url: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    total_review_count: Annotated[int, Field(strict=True, ge=0)] | None = None
    naver_order: NaverOrderFactsV1 = NaverOrderFactsV1()
    quantity_review: NaverQuantityReviewFactsV1 | None = None
    menus: Annotated[list[NaverMenuFactsV1], Field(max_length=100)] = []
    observed_at: AwareDatetime
    data_mode: Annotated[str, StringConstraints(min_length=1, max_length=80)]

    @model_validator(mode="after")
    def has_address_or_branch(self) -> "NaverPlaceFactsV1":
        if not (self.road_address or self.address):
            raise ValueError("Naver place must contain road_address or address")
        return self


class PlannerSourceProvenanceV1(ContractModel):
    source_system: Literal["naver_place"] = "naver_place"
    source_restaurant_id: Identifier
    source_url: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    observed_at: AwareDatetime
    parser_version: Identifier
    data_mode: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    completeness: Literal["complete", "partial"]
    warnings: Annotated[list[str], Field(max_length=64)] = []


class PlannerLocationJoinV1(ContractModel):
    """The candidate edge between one requested location and one place."""

    location_id: Identifier
    candidate_id: Identifier
    request_latitude: float = Field(allow_inf_nan=False, ge=-90, le=90)
    request_longitude: float = Field(allow_inf_nan=False, ge=-180, le=180)
    place_latitude: float = Field(allow_inf_nan=False, ge=-90, le=90)
    place_longitude: float = Field(allow_inf_nan=False, ge=-180, le=180)
    distance_meters: Annotated[int, Field(strict=True, ge=0)]
    radius_meters: Annotated[int, Field(strict=True, ge=1, le=100_000)]
    within_radius: bool


class QuantityReviewEvidenceV1(ContractModel):
    keyword: ShortText
    keyword_code: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    threshold: Annotated[int, Field(strict=True, ge=0)] = 50
    eligible: bool
    status: Literal["available", "below_threshold"]
    source_review_count: Annotated[int, Field(strict=True, ge=0)]
    rank: Annotated[int, Field(strict=True, ge=1)] | None = None
    previous_rank: Annotated[int, Field(strict=True, ge=1)] | None = None
    selected_count: Annotated[int, Field(strict=True, ge=0)] | None = None
    participant_count: Annotated[int, Field(strict=True, ge=0)] | None = None
    response_rate_percent: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    total_vote_count: Annotated[int, Field(strict=True, ge=0)] | None = None
    keyword_review_count: Annotated[int, Field(strict=True, ge=0)] | None = None


class DeliveryCapabilityV1(ContractModel):
    confirmed: bool
    provider: Literal["naver-order"] = "naver-order"
    pickup_available: bool
    target_address_status: Literal["verified", "unknown", "not_requested"]


class PlannerMenuItemV1(ContractModel):
    menu_item_id: Identifier
    source_menu_id: Identifier
    restaurant_id: Identifier
    name: ShortText
    original_text: ShortText
    price_minor: MoneyMinorNullable = None
    price_text: Annotated[str, StringConstraints(max_length=100)] | None = None
    sale_unit: Annotated[str, StringConstraints(min_length=1, max_length=100)] | None = None
    category_code: Annotated[str, StringConstraints(min_length=1, max_length=80, pattern=r"^[a-z0-9_]+$")] = "unknown"
    piece_count: Annotated[int, Field(strict=True, ge=1, le=1_000)] | None = None
    pizza_diameter_cm_milli: Annotated[int, Field(strict=True, ge=0)] | None = None
    slice_count: Annotated[int, Field(strict=True, ge=1, le=1_000)] | None = None
    vegetarian_status: VegetarianStatus = VegetarianStatus.UNKNOWN
    verified_free_allergens: Annotated[list[str], Field(max_length=64)] = []
    allergen_tags: Annotated[list[str], Field(max_length=64)] = []
    spice_level: SpiceLevel = SpiceLevel.UNKNOWN
    availability: AvailabilityStatus = AvailabilityStatus.UNKNOWN
    serving_evidence: ServingEvidenceV1 | None = None
    semantic_provenance: SemanticProvenanceV1
    inferred_tags: Annotated[list[str], Field(max_length=64)] = []
    issues: Annotated[list[PlannerDataIssueV1], Field(max_length=32)] = []

    def to_menu_item_v1(self) -> MenuItemV1:
        if self.issues:
            raise ValueError(f"menu {self.menu_item_id} is not planner-ready")
        if self.price_minor is None or self.sale_unit is None or self.serving_evidence is None:
            raise ValueError(f"menu {self.menu_item_id} is missing calculator fields")
        return MenuItemV1(
            menu_item_id=self.menu_item_id,
            restaurant_id=self.restaurant_id,
            name=self.name,
            original_text=self.original_text,
            category_code=self.category_code,
            price_minor=self.price_minor,
            sale_unit=self.sale_unit,
            piece_count=self.piece_count,
            pizza_diameter_cm_milli=self.pizza_diameter_cm_milli,
            slice_count=self.slice_count,
            vegetarian_status=self.vegetarian_status,
            verified_free_allergens=self.verified_free_allergens,
            allergen_tags=self.allergen_tags,
            spice_level=self.spice_level,
            availability=self.availability,
            serving_evidence=self.serving_evidence,
            semantic_provenance=self.semantic_provenance,
            inferred_tags=self.inferred_tags,
        )


class PlannerRestaurantV1(ContractModel):
    """The only Naver-derived object allowed to cross into the planner."""

    schema_name: Literal["planner_restaurant"] = "planner_restaurant"
    schema_version: Literal["1.0"] = "1.0"
    restaurant_id: Identifier
    source_restaurant_id: Identifier
    source_system: Literal["naver_place"] = "naver_place"
    name: ShortText
    category: ShortText
    branch: Annotated[str, StringConstraints(min_length=1, max_length=200)] | None = None
    address: Annotated[str, StringConstraints(min_length=1, max_length=300)] | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    source_url: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    naver_map_url: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    distance_meters: Annotated[int, Field(strict=True, ge=0)]
    location_join: PlannerLocationJoinV1
    review_count: Annotated[int, Field(strict=True, ge=0)] | None = None
    quantity_review: QuantityReviewEvidenceV1 | None = None
    delivery: DeliveryCapabilityV1
    delivery_queries: Annotated[list[str], Field(max_length=50)] = []
    minimum_order_minor: MoneyMinorNullable = None
    delivery_fee_minor: MoneyMinorNullable = None
    service_fee_minor: MoneyMinorNullable = None
    estimated_delivery_minutes: Annotated[int, Field(strict=True, ge=1, le=600)] | None = None
    availability: AvailabilityStatus = AvailabilityStatus.UNKNOWN
    menu_items: Annotated[list[PlannerMenuItemV1], Field(min_length=1, max_length=100)]
    planning_status: PlannerStatus
    issues: Annotated[list[PlannerDataIssueV1], Field(max_length=64)] = []
    provenance: PlannerSourceProvenanceV1

    @property
    def planner_ready(self) -> bool:
        return self.planning_status is PlannerStatus.READY

    def to_restaurant_v1(self) -> RestaurantV1:
        if not self.planner_ready:
            raise ValueError(f"restaurant {self.restaurant_id} is not planner-ready")
        if self.branch is None or self.address is None or self.latitude is None or self.longitude is None:
            raise ValueError("planner-ready restaurant is missing identity/location fields")
        if self.minimum_order_minor is None or self.delivery_fee_minor is None or self.service_fee_minor is None:
            raise ValueError("planner-ready restaurant is missing fee fields")
        if self.estimated_delivery_minutes is None:
            raise ValueError("planner-ready restaurant is missing delivery estimate")
        if self.issues or any(item.issues for item in self.menu_items):
            raise ValueError("planner-ready restaurant contains unresolved issues")
        return RestaurantV1(
            restaurant_id=self.restaurant_id,
            source_restaurant_id=self.source_restaurant_id,
            name=self.name,
            branch=self.branch,
            address=self.address,
            latitude=self.latitude,
            longitude=self.longitude,
            source_url=self.source_url,
            delivery_queries=self.delivery_queries,
            minimum_order_minor=self.minimum_order_minor,
            delivery_fee_minor=self.delivery_fee_minor,
            service_fee_minor=self.service_fee_minor,
            estimated_delivery_minutes=self.estimated_delivery_minutes,
            availability=self.availability,
            menu_items=[item.to_menu_item_v1() for item in self.menu_items],
        )


def _haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6_371_000.0
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _issue(code: str, field_path: str, reason: str, corrective_action: str, *, severity: IssueSeverity = IssueSeverity.ERROR) -> PlannerDataIssueV1:
    return PlannerDataIssueV1(
        code=code,
        field_path=field_path,
        severity=severity,
        reason=reason,
        corrective_action=corrective_action,
    )


def _category_code(category: str, menu_name: str) -> str:
    text = f"{category} {menu_name}".casefold()
    if any(token in text for token in ("치킨", "닭강정", "chicken")):
        return "chicken"
    if any(token in text for token in ("피자", "pizza")):
        return "pizza"
    return "unknown"


def _semantic_provenance(text: str, source_url: str, observed_at: datetime) -> SemanticProvenanceV1:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return SemanticProvenanceV1(
        source_text=text,
        source_url=source_url,
        status=SemanticFieldStatus.EXPLICIT,
        confidence=ConfidenceLabel.LOW,
        model=None,
        prompt_version=None,
        source_content_hash=digest,
        enriched_at=observed_at,
    )


def _quantity_review(raw: dict[str, Any] | None) -> QuantityReviewEvidenceV1 | None:
    if raw is None:
        return None
    def value(camel: str, snake: str) -> Any:
        return raw.get(camel, raw.get(snake))

    source_count = int(value("sourceReviewCount", "source_review_count"))
    participant_value = value("participantCount", "participant_count")
    selected_value = value("selectedCount", "selected_count")
    participant_count = int(participant_value) if participant_value is not None else None
    selected_count = int(selected_value) if selected_value is not None else None
    return QuantityReviewEvidenceV1(
        keyword=str(value("keyword", "keyword")),
        keyword_code=str(value("keywordCode", "keyword_code")),
        eligible=source_count >= 50,
        status="available" if source_count >= 50 else "below_threshold",
        source_review_count=source_count,
        rank=int(value("rank", "rank")) if value("rank", "rank") is not None else None,
        previous_rank=int(value("previousRank", "previous_rank")) if value("previousRank", "previous_rank") is not None else None,
        selected_count=selected_count,
        participant_count=participant_count,
        response_rate_percent=(round(selected_count / participant_count * 100, 1) if participant_count else None),
        total_vote_count=int(value("totalVoteCount", "total_vote_count")) if value("totalVoteCount", "total_vote_count") is not None else None,
        keyword_review_count=int(value("keywordReviewCount", "keyword_review_count")) if value("keywordReviewCount", "keyword_review_count") is not None else None,
    )


def build_planner_restaurant_from_naver(
    raw: NaverPlaceFactsV1 | dict[str, Any],
    *,
    location_id: str,
    location_query: str,
    request_latitude: float,
    request_longitude: float,
    radius_meters: int = 5_000,
    parser_version: str = "naver-place-adapter-v1",
    delivery_required: bool = True,
    delivery_queries: list[str] | None = None,
    minimum_order_minor: int | None = None,
    delivery_fee_minor: int | None = None,
    service_fee_minor: int | None = None,
    estimated_delivery_minutes: int | None = None,
    serving_evidence_by_menu_id: dict[str, ServingEvidenceV1] | None = None,
    sale_unit_by_menu_id: dict[str, str] | None = None,
) -> PlannerRestaurantV1:
    """Convert one Naver record through identity, location, then readiness.

    Optional planner facts are explicit enrichment inputs.  They are never
    guessed from a menu name, photo, review keyword, or the Naver delivery
    capability flag.
    """

    place = raw if isinstance(raw, NaverPlaceFactsV1) else NaverPlaceFactsV1.model_validate(
        {
            "source_restaurant_id": raw["id"],
            "name": raw["name"],
            "category": raw["category"],
            "longitude": raw["x"],
            "latitude": raw["y"],
            "road_address": raw.get("roadAddress") or "",
            "address": raw.get("address") or "",
            "branch": raw.get("branch"),
            "source_url": raw["source_url"],
            "total_review_count": raw.get("totalReviewCount"),
            "naver_order": {
                "is_delivery": bool(raw.get("naverOrder", {}).get("isDelivery", False)),
                "is_pickup": bool(raw.get("naverOrder", {}).get("isPickup", False)),
            },
            "quantity_review": (
                {
                    "source_review_count": raw["quantityReview"]["sourceReviewCount"],
                    "total_vote_count": raw["quantityReview"].get("totalVoteCount"),
                    "keyword_review_count": raw["quantityReview"].get("keywordReviewCount"),
                    "participant_count": raw["quantityReview"].get("participantCount"),
                    "keyword": raw["quantityReview"]["keyword"],
                    "keyword_code": raw["quantityReview"]["keywordCode"],
                    "selected_count": raw["quantityReview"].get("selectedCount"),
                    "rank": raw["quantityReview"].get("rank"),
                    "previous_rank": raw["quantityReview"].get("previousRank"),
                }
                if raw.get("quantityReview")
                else None
            ),
            "menus": [
                {
                    "source_menu_id": menu["id"],
                    "name": menu["name"],
                    "price_minor": menu.get("price"),
                    "price_text": menu.get("priceText"),
                    "description": menu.get("description") or "",
                    "recommended": bool(menu.get("recommended", False)),
                    "images": menu.get("images", []),
                }
                for menu in raw.get("menus", [])
            ],
            "observed_at": raw.get("observed_at", datetime.now().astimezone()),
            "data_mode": raw.get("data_mode", "browser_observed_fixture"),
        }
    )
    restaurant_id = f"restaurant:naver:{place.source_restaurant_id}"
    candidate_id = f"candidate:{location_id}:{restaurant_id}"
    distance_meters = round(_haversine_meters(request_latitude, request_longitude, place.latitude, place.longitude))
    location_join = PlannerLocationJoinV1(
        location_id=location_id,
        candidate_id=candidate_id,
        request_latitude=request_latitude,
        request_longitude=request_longitude,
        place_latitude=place.latitude,
        place_longitude=place.longitude,
        distance_meters=distance_meters,
        radius_meters=radius_meters,
        within_radius=distance_meters <= radius_meters,
    )

    shared_evidence = serving_evidence_by_menu_id or {}
    shared_sale_units = sale_unit_by_menu_id or {}
    menu_items: list[PlannerMenuItemV1] = []
    restaurant_issues: list[PlannerDataIssueV1] = []
    if not location_join.within_radius:
        restaurant_issues.append(_issue("outside_radius", "/location_join/distance_meters", "장소가 요청 반경 밖입니다.", "radius를 늘리거나 다른 위치를 입력하세요."))
    if place.branch is None:
        restaurant_issues.append(_issue("missing_branch", "/branch", "지점명이 공개 상태에서 확인되지 않았습니다.", "지점명을 source 데이터 또는 운영 보강 데이터로 확인하세요."))
    if delivery_required and not place.naver_order.is_delivery:
        restaurant_issues.append(_issue("delivery_not_confirmed", "/delivery/confirmed", "네이버 주문의 배달 가능 확인값이 false입니다.", "배달 가능한 지점을 선택하거나 delivery 요구를 해제하세요."))
    if not delivery_queries:
        restaurant_issues.append(_issue("delivery_coverage_unknown", "/delivery/target_address_status", "대상 주소에 대한 배달 권역은 장소 capability만으로 확인할 수 없습니다.", "주소별 배달 권역 확인 결과를 별도 source로 제공하세요."))
    if not delivery_queries:
        restaurant_issues.append(_issue("missing_delivery_query", "/delivery_queries", "플래너의 기존 delivery contract에는 대상 위치 query가 필요합니다.", "위치 query를 planner 보강 데이터로 제공하세요."))
    if minimum_order_minor is None:
        restaurant_issues.append(_issue("missing_minimum_order", "/minimum_order_minor", "최소주문금액이 네이버 공개 상태에서 확인되지 않았습니다.", "최소주문금액을 명시한 보강 데이터를 제공하세요."))
    if delivery_fee_minor is None:
        restaurant_issues.append(_issue("missing_delivery_fee", "/delivery_fee_minor", "배달비가 확인되지 않았습니다.", "배달비를 명시한 보강 데이터를 제공하세요."))
    if service_fee_minor is None:
        restaurant_issues.append(_issue("missing_service_fee", "/service_fee_minor", "서비스 수수료가 확인되지 않았습니다.", "서비스 수수료를 명시한 보강 데이터를 제공하세요."))
    if estimated_delivery_minutes is None:
        restaurant_issues.append(_issue("missing_delivery_eta", "/estimated_delivery_minutes", "도착 예상 시간이 확인되지 않았습니다.", "도착 예상 시간을 별도 delivery source로 제공하세요."))
    if _category_code(place.category, "") == "unknown":
        restaurant_issues.append(_issue("unsupported_category", "/category", "현재 planner MVP는 chicken/pizza만 지원합니다.", "지원 카테고리의 지점을 선택하세요."))
    if not place.menus:
        restaurant_issues.append(_issue("missing_menu", "/menu_items", "메뉴가 확인되지 않았습니다.", "메뉴 상세 페이지를 다시 수집하세요."))

    for menu in place.menus:
        original_text = " - ".join(part for part in (menu.name, menu.description) if part)
        item_issues: list[PlannerDataIssueV1] = []
        if menu.price_minor is None:
            item_issues.append(_issue("missing_price", "/menu_items/price_minor", "가격이 확인되지 않았습니다.", "가격이 명시된 메뉴 데이터를 제공하세요."))
        if menu.source_menu_id not in shared_evidence:
            item_issues.append(_issue("missing_serving_evidence", "/menu_items/serving_evidence", "실용 제공량은 공개 메뉴 가격만으로 산출할 수 없습니다.", "공식 중량, 판매 단위 또는 검토된 serving evidence를 제공하세요."))
        if menu.source_menu_id not in shared_sale_units:
            item_issues.append(_issue("missing_sale_unit", "/menu_items/sale_unit", "메뉴 가격의 판매 단위가 확인되지 않았습니다.", "1인분, 판, 조각 등 명시된 판매 단위를 제공하세요."))
        if _category_code(place.category, menu.name) == "unknown":
            item_issues.append(_issue("unsupported_menu_category", "/menu_items/category_code", "메뉴가 chicken/pizza comparable family로 확인되지 않았습니다.", "메뉴 카테고리를 명시적으로 매핑하고 확인하세요."))
        if item_issues:
            restaurant_issues.extend(
                _issue(issue.code, f"/menu_items/{menu.source_menu_id}{issue.field_path}", issue.reason, issue.corrective_action, severity=issue.severity)
                for issue in item_issues
            )
        menu_items.append(
            PlannerMenuItemV1(
                menu_item_id=f"menu:naver:{place.source_restaurant_id}:{menu.source_menu_id}",
                source_menu_id=menu.source_menu_id,
                restaurant_id=restaurant_id,
                name=menu.name,
                original_text=original_text,
                price_minor=menu.price_minor,
                price_text=menu.price_text,
                sale_unit=shared_sale_units.get(menu.source_menu_id),
                category_code=_category_code(place.category, menu.name),
                availability=AvailabilityStatus.UNKNOWN,
                serving_evidence=shared_evidence.get(menu.source_menu_id),
                semantic_provenance=_semantic_provenance(original_text, place.source_url, place.observed_at),
                issues=item_issues,
            )
        )

    status = PlannerStatus.READY if not any(issue.severity is IssueSeverity.ERROR for issue in restaurant_issues) else PlannerStatus.INSUFFICIENT_DATA
    return PlannerRestaurantV1(
        restaurant_id=restaurant_id,
        source_restaurant_id=place.source_restaurant_id,
        name=place.name,
        category=place.category,
        branch=place.branch,
        address=place.road_address or place.address,
        latitude=place.latitude,
        longitude=place.longitude,
        source_url=place.source_url,
        naver_map_url=f"https://map.naver.com/p/entry/place/{place.source_restaurant_id}",
        distance_meters=distance_meters,
        location_join=location_join,
        review_count=place.total_review_count,
        quantity_review=_quantity_review(place.quantity_review.model_dump(by_alias=False) if place.quantity_review else None),
        delivery=DeliveryCapabilityV1(
            confirmed=place.naver_order.is_delivery,
            pickup_available=place.naver_order.is_pickup,
            target_address_status=("verified" if delivery_queries else ("unknown" if delivery_required else "not_requested")),
        ),
        delivery_queries=delivery_queries or [],
        minimum_order_minor=minimum_order_minor,
        delivery_fee_minor=delivery_fee_minor,
        service_fee_minor=service_fee_minor,
        estimated_delivery_minutes=estimated_delivery_minutes,
        availability=AvailabilityStatus.UNKNOWN,
        menu_items=menu_items,
        planning_status=status,
        issues=restaurant_issues,
        provenance=PlannerSourceProvenanceV1(
            source_restaurant_id=place.source_restaurant_id,
            source_url=place.source_url,
            observed_at=place.observed_at,
            parser_version=parser_version,
            data_mode=place.data_mode,
            completeness="complete",
        ),
    )


def promote_ready_restaurants(
    restaurants: list[PlannerRestaurantV1],
) -> list[RestaurantV1]:
    """Cross the compatibility boundary into the existing deterministic planner.

    This is intentionally fail-closed: a mixed list is not silently shortened,
    because dropping an insufficient restaurant would make comparison results
    look complete when they are not.
    """

    not_ready = [restaurant.restaurant_id for restaurant in restaurants if not restaurant.planner_ready]
    if not_ready:
        raise ValueError(f"planner input contains insufficient restaurants: {', '.join(not_ready)}")
    return [restaurant.to_restaurant_v1() for restaurant in restaurants]
