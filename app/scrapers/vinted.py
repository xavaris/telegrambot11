from __future__ import annotations

import logging

from playwright.async_api import Browser

from app.models import Offer
from app.scrapers.base import BaseScraper, OfferCallback
from app.utils.iphone_parser import parse_iphone_attributes
from app.utils.misc import absolute_url, clean_text, normalize_price

logger = logging.getLogger(__name__)


class VintedScraper(BaseScraper):
    source_name = "vinted"

    def __init__(self, settings) -> None:
        super().__init__(settings)
        self.start_url = settings.VINTED_SEARCH_URL

    async def scrape(
        self,
        browser: Browser,
        on_offer: OfferCallback | None = None,
    ) -> list[Offer]:
        page = await self._new_page(browser)
        offers: list[Offer] = []

        try:
            await self.goto(page, self.start_url)
            await page.wait_for_timeout(3500)

            cards = page.locator("a[href*='/items/']")
            count = await cards.count()
            logger.info("[vinted] Liczba linków do ofert: %s", count)

            urls: list[str] = []
            for i in range(min(count, self.settings.MAX_OFFERS_PER_SOURCE)):
                try:
                    href = await cards.nth(i).get_attribute("href")
                    url = absolute_url("https://www.vinted.pl", href)
                    if url and url not in urls:
                        urls.append(url)
                except Exception:
                    logger.exception("[vinted] Nie udało się pobrać href dla karty #%s", i)

            logger.info("[vinted] Unikalnych URL-i do sprawdzenia: %s", len(urls))

            for idx, url in enumerate(urls):
                detail_page = await self._new_page(browser)

                try:
                    await self.goto(detail_page, url)
                    await detail_page.wait_for_timeout(1800)

                    title = await self._extract_title(detail_page)
                    full_text = clean_text(await detail_page.locator("body").inner_text())
                    price = await self._extract_price(detail_page, full_text)
                    image_url = await self._extract_image(detail_page)
                    description = await self._extract_description(detail_page)
                    location = self._extract_location_from_text(full_text)

                    model, storage, color, condition = parse_iphone_attributes(
                        title,
                        description or full_text,
                    )

                    offer = Offer(
                        source=self.source_name,
                        title=title or "Oferta z Vinted",
                        url=url,
                        price=price,
                        location=location,
                        image_url=image_url,
                        description=description,
                        condition=condition,
                        model=model,
                        storage=storage,
                        color=color,
                        raw_payload={"full_text": full_text[:2000]},
                    )

                    logger.info(
                        "[vinted] DETAIL #%s | model=%s | price=%s | title=%s | image=%s",
                        idx,
                        model,
                        price,
                        title,
                        bool(image_url),
                    )

                    await self.emit_offer(offer, offers, on_offer=on_offer)

                except Exception:
                    logger.exception("[vinted] Błąd podczas parsowania detail page: %s", url)
                finally:
                    await self.close_page(detail_page)

            logger.info("[vinted] Łącznie ofert po detail page: %s", len(offers))
            return offers

        finally:
            await self.close_page(page)

    async def _extract_title(self, page) -> str:
        selectors = [
            "h1",
            "[data-testid='item-page-title']",
            "div[class*='title']",
            "meta[property='og:title']",
        ]

        for selector in selectors:
            try:
                if selector.startswith("meta"):
                    loc = page.locator(selector).first
                    if await loc.count():
                        value = (await loc.get_attribute("content") or "").strip()
                        value = clean_text(value)
                        if value:
                            return value
                else:
                    loc = page.locator(selector).first
                    if await loc.count():
                        value = clean_text(await loc.inner_text())
                        if value:
                            return value
            except Exception:
                continue

        return ""

    async def _extract_price(self, page, full_text: str) -> float:
        selectors = [
            "[data-testid='item-price']",
            "div[class*='price']",
            "span[class*='price']",
            "meta[property='product:price:amount']",
        ]

        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if await loc.count():
                    if selector.startswith("meta"):
                        value = clean_text(await loc.get_attribute("content"))
                    else:
                        value = clean_text(await loc.inner_text())

                    price = normalize_price(value)
                    if price > 0:
                        return price
            except Exception:
                continue

        return normalize_price(full_text)

    async def _extract_image(self, page) -> str:
        try:
            meta = page.locator("meta[property='og:image']").first
            if await meta.count():
                content = (await meta.get_attribute("content") or "").strip()
                if content.startswith("http://") or content.startswith("https://"):
                    return content
        except Exception:
            pass

        try:
            imgs = page.locator("img")
            img_count = await imgs.count()
            for i in range(min(img_count, 12)):
                src = (await imgs.nth(i).get_attribute("src") or "").strip()
                if not (src.startswith("http://") or src.startswith("https://")):
                    continue

                lowered = src.lower()
                bad_parts = ["avatar", "icon", "logo", "default", "profile", "user"]
                if any(part in lowered for part in bad_parts):
                    continue

                return src
        except Exception:
            pass

        return ""

    async def _extract_description(self, page) -> str:
        selectors = [
            "[data-testid='item-description']",
            "div[class*='description']",
            "section p",
            "section",
        ]

        bad_snippets = [
            "strona główna",
            "przedmioty użytkownika",
            "podobne rzeczy",
            "elektronika",
            "telefony komórkowe",
            "telefony komorkowe",
        ]

        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if not await loc.count():
                    continue

                value = clean_text(await loc.inner_text())
                if not value:
                    continue

                lower_value = value.lower()
                if any(snippet in lower_value for snippet in bad_snippets):
                    continue

                if len(value) > 500:
                    value = value[:500].strip()

                if len(value) < 10:
                    continue

                return value
            except Exception:
                continue

        return ""

    def _extract_location_from_text(self, full_text: str) -> str:
        lowered = full_text.lower()
        cities = [
            "warszawa",
            "kraków",
            "wrocław",
            "poznań",
            "gdańsk",
            "łódź",
            "szczecin",
            "bydgoszcz",
            "lublin",
            "katowice",
            "gdynia",
            "sopot",
        ]

        for city in cities:
            if city in lowered:
                return city.title()

        return ""
