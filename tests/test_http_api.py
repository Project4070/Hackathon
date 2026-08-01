from group_food_agent.http_api import ApiFailure, geocode, restaurants


def _params(delivery: str = "0") -> dict[str, list[str]]:
    return {
        "lat": ["37.502104"],
        "lng": ["127.025869"],
        "limit": ["10"],
        "radius": ["1000"],
        "delivery": [delivery],
        "fresh": ["0"],
    }


def test_geocode_returns_documented_demo_coordinates():
    result = geocode("신논현역")

    assert result.status == "resolved"
    assert result.latitude == 37.502104
    assert result.longitude == 127.025869
    assert "fresh_live_provider_confirmation" in result.unavailable_fields


def test_restaurants_returns_browser_observed_records_when_delivery_is_disabled():
    result = restaurants(_params("0"))

    assert result.status == "ok"
    assert len(result.restaurants) == 2
    assert result.restaurants[0].name == "춘천한옥집"
    assert result.restaurants[0].quantityReview["rank"] == 3
    assert "menu.estimatedServings" in result.unavailableFields


def test_restaurants_does_not_claim_delivery_from_a_false_naver_order_flag():
    result = restaurants(_params("1"))

    assert result.status == "no_candidates"
    assert result.restaurants == []
    assert any("isDelivery" in warning for warning in result.warnings)


def test_restaurants_rejects_invalid_radius():
    params = _params()
    params["radius"] = ["50"]

    result = restaurants(params)

    assert isinstance(result, ApiFailure)
    assert result.status == "invalid"
    assert result.problematicField == "radius"
