"""Bounded public-page crawler and raw structural extraction boundary.

The engine does not know delivery-platform selectors and never bypasses access
controls.  A narrow source adapter owns discovery/fetch/parsing for one permitted
public source.  Semantic normalization happens only after visible text has been
sanitized and bounded.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated, Protocol

from pydantic import AwareDatetime, Field, StringConstraints

from .contracts import ContractModel, Identifier
from .restaurant import sanitize_visible_text, source_content_hash
from .stores import Clock, system_clock


class CrawlerLimitsV1(ContractModel):
    maximum_pages: Annotated[int, Field(strict=True, ge=1, le=10)] = 10
    concurrency: Annotated[int, Field(strict=True, ge=1, le=3)] = 3
    page_timeout_seconds: Annotated[int, Field(strict=True, ge=1, le=10)] = 10
    retries: Annotated[int, Field(strict=True, ge=0, le=1)] = 1
    maximum_visible_text_chars: Annotated[int, Field(strict=True, ge=100, le=20_000)] = 5_000


class RawMenuRecordV1(ContractModel):
    source_menu_id: Identifier | None
    original_text: Annotated[str, StringConstraints(min_length=1, max_length=5_000)]
    explicit_name: Annotated[str, StringConstraints(min_length=1, max_length=300)] | None
    explicit_price_minor: Annotated[int, Field(strict=True, ge=0, le=10_000_000_000)] | None
    explicit_sale_unit: Annotated[str, StringConstraints(min_length=1, max_length=100)] | None


class RawRestaurantRecordV1(ContractModel):
    source_restaurant_id: Identifier
    source_url: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    name: Annotated[str, StringConstraints(min_length=1, max_length=300)]
    branch: Annotated[str, StringConstraints(min_length=1, max_length=300)]
    address: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    visible_text_hash: Annotated[str, StringConstraints(min_length=64, max_length=64)]
    menu_records: Annotated[list[RawMenuRecordV1], Field(min_length=1, max_length=100)]


class CrawlPageReceiptV1(ContractModel):
    source_url: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    status: Annotated[str, StringConstraints(pattern=r"^(success|timeout|fetch_error|parse_error)$")]
    attempt_count: Annotated[int, Field(strict=True, ge=1, le=2)]
    visible_text_hash: Annotated[str, StringConstraints(min_length=64, max_length=64)] | None
    warning: Annotated[str, StringConstraints(min_length=1, max_length=500)] | None


class RawCrawlBatchV1(ContractModel):
    schema_name: str = "raw_crawl_batch"
    schema_version: str = "1.0"
    location_query: Annotated[str, StringConstraints(min_length=1, max_length=300)]
    crawled_at: AwareDatetime
    parser_version: Identifier
    completeness: Annotated[str, StringConstraints(pattern=r"^(complete|partial)$")]
    records: Annotated[list[RawRestaurantRecordV1], Field(min_length=1, max_length=10)]
    page_receipts: Annotated[list[CrawlPageReceiptV1], Field(min_length=1, max_length=10)]
    warnings: Annotated[list[str], Field(max_length=64)]


class RestaurantSourceAdapter(Protocol):
    parser_version: str

    async def discover(self, location_query: str) -> list[str]: ...

    async def fetch_visible_page(self, source_url: str) -> str: ...

    def parse_visible_text(
        self, source_url: str, visible_text: str, content_hash: str
    ) -> RawRestaurantRecordV1: ...


class BoundedRestaurantCrawler:
    def __init__(
        self,
        adapter: RestaurantSourceAdapter,
        *,
        limits: CrawlerLimitsV1 | None = None,
        clock: Clock = system_clock,
    ) -> None:
        self.adapter = adapter
        self.limits = limits or CrawlerLimitsV1()
        self.clock = clock

    async def _crawl_one(
        self, source_url: str, semaphore: asyncio.Semaphore
    ) -> tuple[RawRestaurantRecordV1 | None, CrawlPageReceiptV1]:
        last_status = "fetch_error"
        last_warning = "fetch failed"
        async with semaphore:
            for attempt in range(1, self.limits.retries + 2):
                try:
                    raw = await asyncio.wait_for(
                        self.adapter.fetch_visible_page(source_url),
                        timeout=self.limits.page_timeout_seconds,
                    )
                    visible = sanitize_visible_text(
                        raw, maximum_length=self.limits.maximum_visible_text_chars
                    )
                    digest = source_content_hash(visible)
                    try:
                        record = self.adapter.parse_visible_text(source_url, visible, digest)
                    except Exception as exc:
                        return None, CrawlPageReceiptV1(
                            source_url=source_url,
                            status="parse_error",
                            attempt_count=attempt,
                            visible_text_hash=digest,
                            warning=f"parser rejected visible text: {type(exc).__name__}",
                        )
                    return record, CrawlPageReceiptV1(
                        source_url=source_url,
                        status="success",
                        attempt_count=attempt,
                        visible_text_hash=digest,
                        warning=None,
                    )
                except TimeoutError:
                    last_status = "timeout"
                    last_warning = "page timeout within configured bound"
                except Exception as exc:
                    last_status = "fetch_error"
                    last_warning = f"fetch failed: {type(exc).__name__}"
        return None, CrawlPageReceiptV1(
            source_url=source_url,
            status=last_status,
            attempt_count=self.limits.retries + 1,
            visible_text_hash=None,
            warning=last_warning,
        )

    async def crawl(self, location_query: str) -> RawCrawlBatchV1:
        if not location_query.strip():
            raise ValueError("crawler location query cannot be empty")
        discovered = await self.adapter.discover(location_query)
        warnings: list[str] = []
        if len(discovered) > self.limits.maximum_pages:
            warnings.append(
                f"discovery returned {len(discovered)} pages; bounded to {self.limits.maximum_pages}"
            )
        # Preserve source order while removing exact duplicate URLs.
        urls = list(dict.fromkeys(discovered))[: self.limits.maximum_pages]
        if not urls:
            raise LookupError("source discovery returned no permitted public pages")
        semaphore = asyncio.Semaphore(self.limits.concurrency)
        results = await asyncio.gather(*(self._crawl_one(url, semaphore) for url in urls))
        receipts = [receipt for _, receipt in results]
        records: list[RawRestaurantRecordV1] = []
        seen_branch_keys: set[tuple[str, str]] = set()
        for record, _ in results:
            if record is None:
                continue
            key = (record.source_restaurant_id, record.address.casefold())
            if key in seen_branch_keys:
                warnings.append(
                    f"deduplicated repeated record for source id {record.source_restaurant_id} at the same address"
                )
                continue
            seen_branch_keys.add(key)
            records.append(record)
        if not records:
            raise LookupError("crawl produced no usable structured restaurant records")
        completeness = "complete" if all(row.status == "success" for row in receipts) else "partial"
        return RawCrawlBatchV1(
            location_query=location_query,
            crawled_at=self.clock(),
            parser_version=self.adapter.parser_version,
            completeness=completeness,
            records=records,
            page_receipts=receipts,
            warnings=warnings,
        )


class FixtureSourceAdapter:
    """Saved-page adapter used for parser tests and the reliable demo path."""

    parser_version = "fixture-source-adapter-v1"

    def __init__(
        self,
        pages: dict[str, str | Exception],
        parser: Callable[[str, str, str], RawRestaurantRecordV1],
        *,
        discovered_urls: list[str] | None = None,
    ) -> None:
        self.pages = pages
        self.parser = parser
        self.discovered_urls = discovered_urls or list(pages)

    async def discover(self, location_query: str) -> list[str]:
        return list(self.discovered_urls)

    async def fetch_visible_page(self, source_url: str) -> str:
        value = self.pages[source_url]
        if isinstance(value, Exception):
            raise value
        return value

    def parse_visible_text(
        self, source_url: str, visible_text: str, content_hash: str
    ) -> RawRestaurantRecordV1:
        return self.parser(source_url, visible_text, content_hash)
