from __future__ import annotations

import logging
import time
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from playwright.async_api import Browser, Page

from app.models import Offer
from app.scrapers.base import BaseScraper, OfferCallback
from app.utils.iphone_parser import parse_model, parse_storage, parse_color, parse_condition
from app.utils.misc import absolute_url, clean_text, normalize_price

logger = logging.getLogger(__name__)


class VintedScraper(BaseScraper):
    source_name = "vinted"

    def __init__(self, settings) -> None:
        super().__init__(settings)
        self.start_url = settings.VINTED_SEARCH_URL

    def _refresh_vinted_time(self, url: str) -> str:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        query["time"] = [str(int(time.time()))]
        new_query = urlencode(query, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    async def scrape(self, browser: Browser, on_offer: OfferCallback | None = None) -> list[Offer]:
        page = await self._new_page(browser)
        offers: list[Offer] = []

        if not self.start_url:
            logger.error("[vinted] Brak start_url")
            await self.close_page(page)
            return []

        try:
            start_url = self._refresh_vinted_time(self.start_url)
            logger.info("[vinted] start_url=%s", start_url)
            await self.goto(page, start_url)
            await page.wait_for_timeout(3000)

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

            for idx, url in enumerate(urls):
                detail_page = await self._new_page(browser)
                try:
                    await self.goto(detail_page, url)
                    await detail_page.wait_for_timeout(1500)
                    offer = await self._extract_detail_offer(detail_page, url)
                    if offer:
                        logger.info("[vinted] DETAIL #%s | model=%s | storage=%s | price=%s | title=%s", idx, offer.model, offer.storage, offer.price, offer.title)
                        await self.emit_offer(offer, offers, on_offer=on_offer)
                except Exception:
                    logger.exception("[vinted] Błąd podczas parsowania detail page: %s", url)
                finally:
                    await self.close_page(detail_page)

            logger.info("[vinted] Łącznie ofert po detail page: %s", len(offers))
            return offers
        finally:
            await self.close_page(page)

    async def _extract_detail_offer(self, page: Page, url: str) -> Offer | None:
        title = await self._extract_title(page)
        full_text = clean_text(await page.locator("body").inner_text())
        price = await self._extract_price(page)
        image_url = await self._extract_image(page)
        description = await self._extract_description(page)
        location = self._extract_location_from_text(full_text)
        details = await self._extract_details_map(page)

        detail_model = clean_text(details.get("model", ""))
        detail_storage = clean_text(details.get("pamięć", "")) or clean_text(details.get("pamiec", ""))
        detail_condition = clean_text(details.get("stan", ""))
        detail_color = clean_text(details.get("kolor", ""))
        detail_battery = clean_text(details.get("kondycja baterii", ""))
        detail_simlock = clean_text(details.get("blokada sim-lock", ""))
        detail_added = clean_text(details.get("dodane", ""))

        parse_blob = " ".join(x for x in [title, description, detail_model, detail_storage, detail_color, full_text[:1000]] if x)
        model = parse_model(parse_blob)
        storage = parse_storage(detail_storage) or parse_storage(parse_blob)
        condition = clean_text(detail_condition) or parse_condition(parse_blob)
        color = clean_text(detail_color) or parse_color(parse_blob)

        extra_lines: list[str] = []
        if detail_battery:
            extra_lines.append(f"Kondycja baterii: {detail_battery}")
        if detail_simlock:
            extra_lines.append(f"SIM-lock: {detail_simlock}")
        if detail_added:
            extra_lines.append(f"Dodane: {detail_added}")

        final_description = (description or "").strip()
        if extra_lines:
            extra_text = " | ".join(extra_lines)
            final_description = f"{final_description}\n{extra_text}".strip()

        if not title:
            return None

        return Offer(
            source=self.source_name,
            title=title,
            url=url,
            price=price,
            location=location,
            image_url=image_url,
            description=final_description[:700],
            condition=condition,
            model=model,
            storage=storage,
            color=color,
            raw_payload={"full_text": full_text[:2000], "details": details},
        )

    async def _extract_title(self, page: Page) -> str:
        selectors = ["h1", "[data-testid='item-page-title']", "div[class*='title']", "meta[property='og:title']"]
        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if not await loc.count():
                    continue
                value = clean_text(await loc.get_attribute("content")) if selector.startswith("meta") else clean_text(await loc.inner_text())
                if value:
                    return value
            except Exception:
                continue
        return ""

    async def _extract_price(self, page: Page) -> float:
        selectors = [
            "meta[property='product:price:amount']",
            "[data-testid='item-price']",
            "div[data-testid='price-block']",
            "div[class*='price']",
            "span[class*='price']",
        ]
        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if not await loc.count():
                    continue
                value = clean_text(await loc.get_attribute("content")) if selector.startswith("meta") else clean_text(await loc.inner_text())
                price = normalize_price(value, min_price=100, max_price=20000)
                if 100 <= price <= 20000:
                    return price
            except Exception:
                continue
        return 0.0

    async def _extract_image(self, page: Page) -> str:
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
                if any(part in lowered for part in ["avatar", "icon", "logo", "default", "profile", "user"]):
                    continue
                return src
        except Exception:
            pass
        return ""

    async def _extract_description(self, page: Page) -> str:
        selectors = [
            "[data-testid='item-description']",
            "div[class*='description']",
            "section p",
        ]
        bad_snippets = [
            "strona główna", "strona glowna", "przedmioty użytkownika", "przedmioty uzytkownika",
            "podobne rzeczy", "inne przedmioty", "ochronę kupujących", "ochrone kupujacych",
            "elektronika", "telefony komórkowe", "telefony komorkowe", "zobacz więcej", "zobacz wiecej",
        ]
        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if not await loc.count():
                    continue
                value = clean_text(await loc.inner_text())
                if not value or len(value) < 8:
                    continue
                lower_value = value.lower()
                if any(snippet in lower_value for snippet in bad_snippets):
                    continue
                # odrzuć typowe śmietniki z listą ubrań/rozmiarów
                if lower_value.count(" / ") >= 4 or lower_value.count(" xs ") >= 2:
                    continue
                if len(value) > 500:
                    value = value[:500].strip()
                return value
            except Exception:
                continue
        return ""

    async def _extract_details_map(self, page: Page) -> dict[str, str]:
        details: dict[str, str] = {}
        body_text = clean_text(await page.locator("body").inner_text())
        lines = [line.strip() for line in body_text.split("\n") if line.strip()]

        wanted_keys = {
            "marka",
            "model",
            "kondycja baterii",
            "pamięć",
            "pamiec",
            "stan",
            "blokada sim-lock",
            "kolor",
            "dodane",
        }

        for i in range(len(lines) - 1):
            key = lines[i].lower().strip().rstrip(":")
            value = lines[i + 1].strip()
            if key in wanted_keys and key not in details:
                details[key] = clean_text(value)

        return details

    def _extract_location_from_text(self, full_text: str) -> str:
        lowered = full_text.lower()
        cities = [
            "warszawa", "kraków", "krakow", "wrocław", "wroclaw", "poznań", "poznan", "gdańsk", "gdansk",
            "łódź", "lodz", "szczecin", "bydgoszcz", "lublin", "katowice", "gdynia", "sopot"
        ]
        for city in cities:
            if city in lowered:
                return city.title()
        return ""
