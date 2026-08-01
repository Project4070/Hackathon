import asyncio
from playwright.async_api import async_playwright
from typing import List, Dict, Optional, Tuple
from storage_manager import RestaurantStorageManager
import os
import re

# 타임아웃 상수 (ms)
TIMEOUT = 10000


class NaverMapRestaurantCrawler:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.launch_options = self._get_launch_options()

    def _get_launch_options(self) -> dict:
        """브라우저 실행 옵션 반환"""
        return {
            "headless": self.headless,
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-web-security",
                "--disable-site-isolation-trials",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-gpu",
                "--disable-extensions",
                "--disable-default-apps",
                "--disable-sync",
                "--disable-translate",
                "--hide-scrollbars",
                "--metrics-recording-only",
                "--mute-audio",
                "--safebrowsing-disable-auto-update",
                "--ignore-certificate-errors",
                "--ignore-ssl-errors",
                "--ignore-certificate-errors-spki-list",
                "--disable-setuid-sandbox",
                "--window-size=1920,1080",
                "--start-maximized",
            ],
        }

    def _get_context_options(self) -> dict:
        """브라우저 컨텍스트 옵션 반환"""
        return {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "locale": "ko-KR",
            "timezone_id": "Asia/Seoul",
            "permissions": ["geolocation"],
            "geolocation": {"latitude": 37.5665, "longitude": 126.9780},
            "color_scheme": "light",
            "device_scale_factor": 1,
            "is_mobile": False,
            "has_touch": False,
            "extra_http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Cache-Control": "max-age=0",
                "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-User": "?1",
                "Sec-Fetch-Dest": "document",
                "Upgrade-Insecure-Requests": "1",
            },
        }

    async def _perform_search(self, page, search_query: str):
        """검색 수행"""
        await page.goto("https://httpbin.org/ip")
        await page.goto("https://map.naver.com/", wait_until="domcontentloaded")

        search_input = await page.wait_for_selector(
            "input.input_search", state="visible", timeout=TIMEOUT
        )
        await search_input.click()
        await search_input.fill(search_query)
        await search_input.press("Enter")

        await page.wait_for_selector(
            "iframe#searchIframe", state="visible", timeout=TIMEOUT
        )

    async def _get_search_frame(self, page):
        """검색 결과 iframe 가져오기"""
        iframe_element = await page.query_selector("iframe#searchIframe")
        return await iframe_element.content_frame()

    async def _scroll_to_load_all(self, frame):
        """모든 결과가 로드될 때까지 스크롤"""
        previous_count = 0
        no_change_count = 0
        max_no_change = 3

        while True:
            current_restaurants = await frame.query_selector_all("li.UEzoS")
            current_count = len(current_restaurants)

            if current_count == previous_count:
                no_change_count += 1
                if no_change_count >= max_no_change:
                    print("더 이상 로드할 데이터가 없습니다.")
                    break
            else:
                no_change_count = 0

            previous_count = current_count

            await frame.evaluate(
                """
                () => {
                    const scrollContainer = document.querySelector('.Ryr1F') || 
                                           document.querySelector('[role="main"]') || 
                                           document.body;
                    
                    if (scrollContainer) {
                        scrollContainer.scrollTop = scrollContainer.scrollHeight;
                    } else {
                        window.scrollTo(0, document.body.scrollHeight);
                    }
                }
            """
            )

            await asyncio.sleep(2)

    async def _extract_basic_info(self, restaurant):
        """식당 기본 정보 추출"""
        name_elem = await restaurant.query_selector("span.TYaxT")
        name = await name_elem.inner_text() if name_elem else "이름 없음"

        category_elem = await restaurant.query_selector("span.KCMnt")
        category = await category_elem.inner_text() if category_elem else ""

        return name, category

    async def _extract_place_id(self, restaurant, page):
        """place_id 추출"""
        link_elem = await restaurant.query_selector("a.place_bluelink")
        if not link_elem:
            return None

        await link_elem.click()
        await page.wait_for_url(lambda url: "/place/" in url, timeout=TIMEOUT)

        new_url = page.url
        match = re.search(r"/place/(\d+)", new_url)
        return match.group(1) if match else None

    async def _extract_address_info(self, place_id: str, context):
        """주소 및 좌표 정보 추출"""
        place_detail_url = f"https://pcmap.place.naver.com/place/{place_id}"
        detail_page = await context.new_page()

        address = None

        await detail_page.goto(place_detail_url)
        await detail_page.wait_for_selector("span.LDgIH", timeout=TIMEOUT)
        address_elem = await detail_page.query_selector("span.LDgIH")
        address = await address_elem.inner_text()
        await detail_page.close()

        return address

    async def _extract_restaurant_data(self, restaurants, frame, page, context):
        """식당 데이터 추출"""
        results = []

        for restaurant in restaurants:
            name, category = await self._extract_basic_info(restaurant)
            place_id = await self._extract_place_id(restaurant, page)

            address = None
            if place_id:
                address = await self._extract_address_info(place_id, context)

            results.append(
                {
                    "place_id": place_id,
                    "name": name,
                    "category": category,
                    "origin_address": address,
                }
            )

            await page.go_back()

        return results

    async def crawl_single_page(self, search_query: str) -> List[Dict]:
        """특정 페이지 하나만 크롤링"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(**self.launch_options)
            context = await browser.new_context(**self._get_context_options())
            page = await context.new_page()

            await page.route(
                "**/*.{png,jpg,jpeg,gif,svg,webp}", lambda route: route.abort()
            )

            results = []

            try:
                # 검색 수행
                await self._perform_search(page, search_query)

                # iframe 가져오기
                frame = await self._get_search_frame(page)
                if not frame:
                    return results

                # 모든 결과 로드
                await self._scroll_to_load_all(frame)
                await frame.wait_for_selector(
                    "li.UEzoS", state="visible", timeout=TIMEOUT
                )

                # 데이터 추출
                restaurants = await frame.query_selector_all("li.UEzoS")
                results = await self._extract_restaurant_data(
                    restaurants, frame, page, context
                )

                print(f"{len(restaurants)}개 수집")

            except Exception as e:
                print(f"크롤링 중 오류: {str(e)}")
            finally:
                await browser.close()

            return results


def merge_and_dedupe_results(
    all_results: List[List[Dict]], existing_place_ids: set
) -> List[Dict]:
    """결과 병합 및 중복 제거"""
    merged_results = []
    for page_results in all_results:
        merged_results.extend(page_results)

    return [
        item for item in merged_results if item["place_id"] not in existing_place_ids
    ]


def print_results_summary(results: List[Dict]):
    """결과 요약 출력"""
    print(f"\n총 {len(results)}개 신규 식당 수집")
    for i, restaurant in enumerate(results, 1):
        print(
            f"{i}. {restaurant['place_id']} [{restaurant['name']}] "
            f"[{restaurant['category']}] [{restaurant['page']}] "
            f"[origin_address: {restaurant['origin_address']}] "
            f"[address: {restaurant['address']}] "
            f"[latitude: {restaurant['latitude']}, longitude: {restaurant['longitude']}]"
        )


async def main():
    try:
        search_query = input(
            "식당 크롤링 할 위치를 입력하세요 (공덕역 식당 등등...) : "
        )
        print(f"search_query: {search_query}")

        # 크롤러 생성 및 실행
        crawler = NaverMapRestaurantCrawler(headless=False)
        all_results = await crawler.crawl_single_page(search_query)

        # 결과 처리
        print_results_summary(all_results)

    except Exception as e:
        print(f"프로그램 실행 중 오류 발생: {str(e)}")
        raise


if __name__ == "__main__":
    asyncio.run(main())