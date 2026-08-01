"""G5 direct restaurant-source lookup, semantic validation, and eligibility."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path

from .contracts import (
    HardRequirementKind,
    PlanningIntakeV2,
    PreferencePolarity,
    PreferenceStrength,
    SemanticNamespace,
)
from .planner_models import (
    AvailabilityStatus,
    CandidateMenuSetV1,
    EligibleMenuSetV1,
    EligibleRestaurantV1,
    FreshnessStatus,
    MenuEligibilityV1,
    MenuItemV1,
    NormalizedMenuSetV1,
    RestaurantSourceV1,
    SpiceLevel,
    VegetarianStatus,
)

def default_source_path() -> Path:
    return Path(__file__).resolve().parents[2] / "fixtures" / "restaurant_source_v1.json"


def load_restaurant_source(path: Path | None = None) -> RestaurantSourceV1:
    with (path or default_source_path()).open("r", encoding="utf-8") as handle:
        return RestaurantSourceV1.model_validate(json.load(handle))


def sanitize_visible_text(value: str, *, maximum_length: int = 2_000) -> str:
    """Bound and de-markup untrusted visible menu text before model enrichment."""

    if len(value) > maximum_length:
        raise ValueError(f"visible source text exceeds {maximum_length} characters")
    without_blocks = re.sub(
        r"(?is)<(script|style|noscript|template)[^>]*>.*?</\1>", " ", value
    )
    without_tags = re.sub(r"(?s)<[^>]+>", " ", without_blocks)
    clean = html.unescape(without_tags)
    clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", clean)
    return re.sub(r"\s+", " ", clean).strip()


def source_content_hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def search_menu_candidates(
    intake: PlanningIntakeV2,
    source: RestaurantSourceV1,
    *,
    now: datetime,
    restaurant_limit: int,
    unavailable_restaurant_ids: set[str] | None = None,
    unavailable_menu_item_ids: set[str] | None = None,
) -> CandidateMenuSetV1:
    """Return bounded available records without category or location gating."""

    unavailable_restaurants = unavailable_restaurant_ids or set()
    unavailable_items = unavailable_menu_item_ids or set()
    excluded_restaurant_names = {
        name.casefold() for name in intake.profile.restaurant_preferences.excluded_names
    }
    restaurants = []
    for restaurant in source.restaurants:
        if restaurant.restaurant_id in unavailable_restaurants:
            continue
        if restaurant.name.casefold() in excluded_restaurant_names:
            continue
        if restaurant.availability is not AvailabilityStatus.AVAILABLE:
            continue
        scheduled_at = intake.profile.occasion.scheduled_at
        if scheduled_at is not None and now + timedelta(
            minutes=restaurant.estimated_delivery_minutes
        ) > scheduled_at:
            continue
        items = [
            item
            for item in restaurant.menu_items
            if item.menu_item_id not in unavailable_items
            and item.availability is AvailabilityStatus.AVAILABLE
        ]
        if items:
            restaurants.append(restaurant.model_copy(update={"menu_items": items}))
        if len(restaurants) >= restaurant_limit:
            break
    if not restaurants:
        raise LookupError("the configured direct source has no available restaurant/menu records")

    warnings = [
        *source.warnings,
        "restaurant data was read from the direct configured source; no cache was used",
        "owner override: requested category and delivery location did not filter source records",
    ]
    if source.completeness.value == "partial":
        warnings.append("restaurant source is partial; missing fields were not invented")
    return CandidateMenuSetV1(
        case_id=intake.case_id,
        profile_revision=intake.profile_revision,
        source_id=source.source_id,
        freshness=FreshnessStatus.FRESH,
        completeness=source.completeness,
        data_mode=source.data_mode,
        restaurants=restaurants,
        warnings=warnings,
    )


def enrich_menu_semantics(
    candidates: CandidateMenuSetV1,
    *,
    candidate_menu_set_id: str,
) -> NormalizedMenuSetV1:
    """Validate reviewed source semantics; never synthesize missing hard facts.

    Every source item already contains provenance-bearing normalized fields.
    """

    warnings = list(candidates.warnings)
    for restaurant in candidates.restaurants:
        for item in restaurant.menu_items:
            sanitize_visible_text(item.original_text)
            if not item.semantic_provenance.source_content_hash:
                raise ValueError(f"menu item {item.menu_item_id} lacks semantic provenance")
    return NormalizedMenuSetV1(
        case_id=candidates.case_id,
        profile_revision=candidates.profile_revision,
        candidate_menu_set_id=candidate_menu_set_id,
        restaurants=candidates.restaurants,
        model_enrichments=0,
        warnings=warnings,
    )


def _requirement_passes(item: MenuItemV1, kind: HardRequirementKind, namespace: SemanticNamespace, code: str) -> bool:
    if kind is HardRequirementKind.ALLERGY or namespace is SemanticNamespace.ALLERGEN:
        return code in item.verified_free_allergens
    if kind is HardRequirementKind.DIET or namespace is SemanticNamespace.DIET:
        if code == "vegetarian":
            return item.vegetarian_status is VegetarianStatus.EXPLICIT_YES
        return False
    if kind is HardRequirementKind.SPICE_LIMIT or namespace is SemanticNamespace.SPICE:
        if code in {"hot", "spicy", "non_spicy", "not_spicy"}:
            return item.spice_level not in {SpiceLevel.HOT, SpiceLevel.UNKNOWN}
        return False
    if kind is HardRequirementKind.FOOD_EXCLUSION:
        explicit_terms = {
            item.category_code,
            *item.allergen_tags,
            *item.inferred_tags,
        }
        return code not in explicit_terms
    # Unsupported/unknown hard semantics are conservative exclusions.
    return False


def _preference_matches(item: MenuItemV1, namespace: SemanticNamespace, code: str) -> bool:
    if namespace is SemanticNamespace.SPICE:
        return item.spice_level.value == code or (code == "spicy" and item.spice_level is SpiceLevel.HOT)
    if namespace is SemanticNamespace.FOOD_CATEGORY:
        return item.category_code == code
    return code in item.inferred_tags or code in item.allergen_tags


def apply_hard_eligibility(
    intake: PlanningIntakeV2,
    normalized: NormalizedMenuSetV1,
    *,
    normalized_menu_set_id: str,
) -> EligibleMenuSetV1:
    """Apply allergy/diet constraints using verified structured facts only."""

    all_group_ids = [group.group_id for group in intake.profile.party.groups]
    strength_penalty = {
        PreferenceStrength.WEAK: 750,
        PreferenceStrength.NORMAL: 1_500,
        PreferenceStrength.STRONG: 2_500,
    }
    restaurants: list[EligibleRestaurantV1] = []
    excluded_count = 0
    warnings = list(normalized.warnings)

    for restaurant in normalized.restaurants:
        eligibility_rows: list[MenuEligibilityV1] = []
        for item in restaurant.menu_items:
            excluded_groups: set[str] = set()
            reasons: list[str] = []
            for requirement in intake.profile.hard_requirements:
                for term in requirement.terms:
                    if not _requirement_passes(item, requirement.kind, term.namespace, term.code):
                        excluded_groups.update(requirement.affected_group_ids)
                        reasons.append(
                            f"{requirement.requirement_id}: no verified {term.code} eligibility evidence"
                        )
            penalty = 0
            for preference in intake.profile.preferences:
                affected = set(preference.affected_group_ids) or set(all_group_ids)
                if affected.isdisjoint(set(all_group_ids) - excluded_groups):
                    continue
                matches = any(
                    _preference_matches(item, term.namespace, term.code)
                    for term in preference.terms
                )
                if preference.polarity is PreferencePolarity.AVOID and matches:
                    penalty += strength_penalty[preference.strength]
                elif preference.polarity is PreferencePolarity.PREFER and not matches:
                    penalty += strength_penalty[preference.strength] // 2
            eligible_groups = [group_id for group_id in all_group_ids if group_id not in excluded_groups]
            if not eligible_groups:
                excluded_count += 1
            eligibility_rows.append(
                MenuEligibilityV1(
                    menu_item_id=item.menu_item_id,
                    eligible_group_ids=eligible_groups,
                    excluded_group_ids=sorted(excluded_groups),
                    hard_exclusion_reasons=sorted(set(reasons)),
                    preference_penalty_basis_points=min(10_000, penalty),
                )
            )
        restaurants.append(
            EligibleRestaurantV1(restaurant=restaurant, eligibility=eligibility_rows)
        )

    return EligibleMenuSetV1(
        case_id=intake.case_id,
        profile_revision=intake.profile_revision,
        normalized_menu_set_id=normalized_menu_set_id,
        restaurants=restaurants,
        excluded_item_count=excluded_count,
        warnings=warnings,
    )
