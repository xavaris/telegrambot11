from __future__ import annotations

import json
import logging
import re
import time
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

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

    async def scrape(
        self,
        browser: Browser,
        on_offer: OfferCallback | None = None,
    ) -> list[Offer]:
        page = await self._new_page(browser)
        offers: list[Offer] = []

        if not self.start_url:
            logger.error("[vinted] Brak start_url")
            await self.close_page(page)
            return []

        try:
            start_url = self._ensure_time_param(self.start_url)
            logger.info("[vinted] start_url=%s", start_url)

            await self.goto(page, start_url)
            await page.wait_for_timeout(3500)

            cards = page.locator("a[href*='/items/']")
            count = await cards.count()
            logger.info("[vinted] Liczba linków do ofert: %s", count)

            urls: list[str] = []
            for i in range(min(count, self.settings.MAX_OFFERS_PER_SOURCE)):
                try:
                    href = await cards.nth(i).get_attribute("href")
                    url = absolute_url("https://www.vinted.pl", href)
                    if url and "/items/" in url and url not in urls:
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
                    price = await self._extract_price(detail_page)
                    image_url = await self._extract_image(detail_page)
                    description = await self._extract_description(detail_page)
                    details = await self._extract_details_map(detail_page)

                    detail_model = clean_text(details.get("model", ""))
                    detail_storage = clean_text(details.get("pamięć", "")) or clean_text(details.get("pamiec", ""))
                    detail_condition = clean_text(details.get("stan", ""))
                    detail_color = clean_text(details.get("kolor", ""))
                    detail_battery = clean_text(details.get("kondycja baterii", ""))
                    detail_simlock = clean_text(details.get("blokada sim-lock", ""))
                    detail_added = clean_text(details.get("dodane", ""))
                    location = clean_text(details.get("lokalizacja", ""))

                    model_from_title = parse_model(title)
                    model_from_details = parse_model(detail_model)

                    model = model_from_details or model_from_title

                    if model_from_title and model_from_details and model_from_title != model_from_details:
                        model = model_from_title

                    storage = parse_storage(detail_storage)
                    condition = clean_text(detail_condition) or parse_condition(title)
                    color = clean_text(detail_color) or parse_color(title)

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
                        if final_description:
                            final_description = f"{final_description}\n{extra_text}"
                        else:
                            final_description = extra_text

                    offer = Offer(
                        source=self.source_name,
                        title=title or "Oferta z Vinted",
                        url=url,
                        price=price,
                        location=location,
                        image_url=image_url,
                        description=final_description,
                        condition=condition,
                        model=model,
                        storage=storage,
                        color=color,
                        raw_payload={
                            "details": details,
                        },
                    )

                    logger.info(
                        "[vinted] DETAIL #%s | model=%s | storage=%s | price=%s | title=%s",
                        idx,
                        model,
                        storage,
                        price,
                        title,
                    )

                    await self.emit_offer(offer, offers, on_offer=on_offer)

                except Exception:
                    logger.exception("[vinted] Błąd detail page: %s", url)
                finally:
                    await self.close_page(detail_page)

            logger.info("[vinted] Łącznie ofert po detail page: %s", len(offers))
            return offers

        finally:
            await self.close_page(page)

    def _ensure_time_param(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            query["time"] = [str(int(time.time()))]
            new_query = urlencode(query, doseq=True)
            return urlunparse(parsed._replace(query=new_query))
        except Exception:
            return url

    async def _extract_title(self, page: Page) -> str:
        selectors = [
            "h1",
            "[data-testid='item-page-title']",
            "meta[property='og:title']",
        ]

        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if not await loc.count():
                    continue

                if selector.startswith("meta"):
                    value = clean_text(await loc.get_attribute("content"))
                else:
                    value = clean_text(await loc.inner_text())

                if value and len(value) >= 3:
                    return value
            except Exception:
                continue

        return ""

    async def _extract_price(self, page: Page) -> float:
        # 1. Meta tag
        try:
            loc = page.locator("meta[property='product:price:amount']").first
            if await loc.count():
                raw = await loc.get_attribute("content")
                price = normalize_price(raw)
                if 100 <= price <= 15000:
                    return price
        except Exception:
            pass

        # 2. JSON-LD
        try:
            scripts = page.locator("script[type='application/ld+json']")
            count = await scripts.count()
            for i in range(count):
                raw_json = await scripts.nth(i).inner_text()
                if not raw_json:
                    continue

                try:
                    data = json.loads(raw_json)
                except Exception:
                    continue

                candidates = data if isinstance(data, list) else [data]
                for item in candidates:
                    if not isinstance(item, dict):
                        continue

                    offers = item.get("offers")
                    if isinstance(offers, dict):
                        raw_price = offers.get("price")
                        price = normalize_price(raw_price)
                        if 100 <= price <= 15000:
                            return price
        except Exception:
            pass

        # 3. Widoczne elementy ceny
        selectors = [
            "[data-testid='item-price']",
            "div[data-testid*='price']",
            "span[data-testid*='price']",
            "div[class*='price']",
            "span[class*='price']",
        ]

        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if not await loc.count():
                    continue

                raw = clean_text(await loc.inner_text())
                price = normalize_price(raw)
                if 100 <= price <= 15000:
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
                bad_parts = ["avatar", "icon", "logo", "default", "profile", "user"]
                if any(part in lowered for part in bad_parts):
                    continue

                return src
        except Exception:
            pass

        return ""

    async def _extract_description(self, page: Page) -> str:
        selectors = [
            "[data-testid='item-description']",
            "section[data-testid*='description']",
            "div[data-testid*='description']",
        ]

        bad_snippets = [
            "strona główna",
            "przedmioty użytkownika",
            "podobne rzeczy",
            "podobne przedmioty",
            "ochronę kupujących",
            "kup teraz",
            "zaproponuj cenę",
            "zapytaj",
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

                if len(value) < 5:
                    continue

                return value
            except Exception:
                continue

        return ""

    async def _extract_details_map(self, page: Page) -> dict[str, str]:
        details: dict[str, str] = {}

        label_variants = {
            "marka": ["Marka", "Brand"],
            "model": ["Model"],
            "kondycja baterii": ["Kondycja baterii", "Battery health"],
            "pamięć": ["Pamięć", "Pamiec", "Storage"],
            "stan": ["Stan", "Condition"],
            "blokada sim-lock": ["Blokada SIM-lock", "SIM lock"],
            "kolor": ["Kolor", "Color"],
            "dodane": ["Dodane", "Added"],
            "lokalizacja": ["Lokalizacja", "Location"],
        }

        lines: list[str] = []

        selectors = [
            "main",
            "[data-testid='item-page-details']",
            "aside",
        ]

        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if not await loc.count():
                    continue

                text = clean_text(await loc.inner_text())
                if not text:
                    continue

                parts = [clean_text(x) for x in re.split(r"\n+", text) if clean_text(x)]
                lines.extend(parts)
            except Exception:
                continue

        deduped_lines: list[str] = []
        seen: set[str] = set()
        for line in lines:
            key = line.lower().strip()
            if key not in seen:
                seen.add(key)
                deduped_lines.append(line)
        lines = deduped_lines

        for canonical_key, variants in label_variants.items():
            for i, line in enumerate(lines[:-1]):
                if line.strip() in variants:
                    value = clean_text(lines[i + 1])
                    if value and len(value) < 120:
                        details[canonical_key] = value
                        break

        return details
