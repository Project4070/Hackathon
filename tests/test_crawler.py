from __future__ import annotations

from datetime import datetime, timezone

import pytest

from group_food_agent.crawler import (
    BoundedRestaurantCrawler,
    CrawlerLimitsV1,
    FixtureSourceAdapter,
    RawMenuRecordV1,
    RawRestaurantRecordV1,
)


NOW = datetime(2026, 8, 2, tzinfo=timezone.utc)


def _parser(url: str, text: str, digest: str) -> RawRestaurantRecordV1:
    if "BROKEN_SELECTOR" in text:
        raise ValueError("required restaurant name selector missing")
    source_id, address, menu = text.split("|")
    return RawRestaurantRecordV1(
        source_restaurant_id=source_id,
        source_url=url,
        name=f"Restaurant {source_id}",
        branch="Sinchon",
        address=address,
        visible_text_hash=digest,
        menu_records=[
            RawMenuRecordV1(
                source_menu_id=f"menu-{source_id}",
                original_text=menu,
                explicit_name=menu,
                explicit_price_minor=None,
                explicit_sale_unit=None,
            )
        ],
    )


@pytest.mark.asyncio
async def test_bounded_crawler_sanitizes_deduplicates_and_preserves_branches():
    pages = {
        "https://example.org/a": "<b>brand-a|address-one|Chicken 12 pieces</b>",
        "https://example.org/a-duplicate": "brand-a|address-one|Chicken 12 pieces",
        "https://example.org/a-other-branch": "brand-a|address-two|Pizza 32 cm",
    }
    crawler = BoundedRestaurantCrawler(
        FixtureSourceAdapter(pages, _parser), clock=lambda: NOW
    )

    batch = await crawler.crawl("Yonsei University")

    assert batch.completeness == "complete"
    assert len(batch.records) == 2
    assert {record.address for record in batch.records} == {"address-one", "address-two"}
    assert any("deduplicated" in warning for warning in batch.warnings)
    assert all(len(record.visible_text_hash) == 64 for record in batch.records)


@pytest.mark.asyncio
async def test_partial_crawl_records_selector_and_fetch_failures():
    pages = {
        "https://example.org/good": "brand-a|address-one|Chicken",
        "https://example.org/broken": "BROKEN_SELECTOR",
        "https://example.org/error": RuntimeError("network unavailable"),
    }
    crawler = BoundedRestaurantCrawler(
        FixtureSourceAdapter(pages, _parser),
        limits=CrawlerLimitsV1(retries=0),
        clock=lambda: NOW,
    )

    batch = await crawler.crawl("Yonsei University")

    assert batch.completeness == "partial"
    assert len(batch.records) == 1
    assert [receipt.status for receipt in batch.page_receipts] == [
        "success",
        "parse_error",
        "fetch_error",
    ]


@pytest.mark.asyncio
async def test_crawler_enforces_page_limit_and_one_location_query():
    pages = {
        f"https://example.org/{index}": f"brand-{index}|address-{index}|Pizza"
        for index in range(12)
    }
    crawler = BoundedRestaurantCrawler(
        FixtureSourceAdapter(pages, _parser),
        limits=CrawlerLimitsV1(maximum_pages=3),
        clock=lambda: NOW,
    )

    batch = await crawler.crawl("Yonsei University")

    assert len(batch.page_receipts) == 3
    assert len(batch.records) == 3
    assert any("bounded to 3" in warning for warning in batch.warnings)


@pytest.mark.asyncio
async def test_crawler_returns_data_unavailable_when_every_page_fails():
    crawler = BoundedRestaurantCrawler(
        FixtureSourceAdapter(
            {"https://example.org/error": RuntimeError("offline")}, _parser
        ),
        limits=CrawlerLimitsV1(retries=0),
        clock=lambda: NOW,
    )

    with pytest.raises(LookupError, match="no usable"):
        await crawler.crawl("Yonsei University")
