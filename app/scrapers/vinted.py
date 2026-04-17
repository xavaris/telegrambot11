from __future__ import annotations

import logging
import re

from playwright.async_api import Browser

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
            logger.info("[vinted] start_url=%s", self.start_url)
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

                    # spróbuj rozwinąć opis
                    await self._expand_description(detail_page)

                    title = await self._extract_title(detail_page)
                    full_text = clean_text(await detail_page.locator("body").inner_text())
                    price = await self._extract_price(detail_page)
                    image_url = await self._extract_image(detail_page)
                    description = await self._extract_description(detail_page)
                    location = self._extract_location_from_text(full_text)
                    details = await self._extract_details_map(detail_page)

                    detail_model = clean_text(details.get("model", ""))
                    detail_storage = clean_text(details.get("pamięć", "")) or clean_text(details.get("pamiec", ""))
                    detail_condition = clean_text(details.get("stan", ""))
                    detail_color = clean_text(details.get("kolor", ""))
                    detail_battery = clean_text(details.get("kondycja baterii", ""))
                    detail_simlock = clean_text(details.get("blokada sim-lock", ""))
                    detail_added = clean_text(details.get("dodane", ""))

                    model = parse_model(detail_model) or parse_model(title)
                    storage = parse_storage(detail_storage) or parse_storage(f"{title} {description}".strip())
                    condition = clean_text(detail_condition) or parse_condition(f"{title} {description}".strip())
                    color = clean_text(detail_color) or parse_color(f"{title} {description}".strip())

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
                            "full_text": full_text[:2000],
                            "details": details,
                        },
                    )

                    logger.info(
                        "[vinted] DETAIL #%s | model=%s | storage=%s | price=%s | title=%s | desc=%s",
                        idx,
                        model,
                        storage,
                        price,
                        title,
                        bool(final_description),
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

    async def _expand_description(self, page) -> None:
        possible_texts = [
            "więcej",
            "… więcej",
            "... więcej",
            "more",
            "show more",
        ]

        try:
            for text in possible_texts:
                locator = page.get_by_text(text, exact=False)
                count = await locator.count()
                if count:
                    for i in range(min(count, 3)):
                        try:
                            await locator.nth(i).click(timeout=1000)
                            await page.wait_for_timeout(500)
                            return
                        except Exception:
                            continue
        except Exception:
            pass

    async def _extract_title(self, page) -> str:
        selectors = [
            "h1",
            "[data-testid='item-page-title']",
            "meta[property='og:title']",
        ]

        for selector in selectors:
            try:
                if selector.startswith("meta"):
                    loc = page.locator(selector).first
                    if await loc.count():
                        value = clean_text(await loc.get_attribute("content"))
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

    async def _extract_price(self, page) -> float:
        selectors = [
            "[data-testid='item-price']",
            "meta[property='product:price:amount']",
            "span:has-text('zł')",
            "div:has-text('zł')",
        ]

        for selector in selectors:
            try:
                loc = page.locator(selector)
                count = await loc.count()
                for i in range(min(count, 5)):
                    if selector.startswith("meta"):
                        value = clean_text(await loc.nth(i).get_attribute("content"))
                    else:
                        value = clean_text(await loc.nth(i).inner_text())

                    price = normalize_price(value)
                    if 50 <= price <= 20000:
                        return price
            except Exception:
                continue

        return 0.0

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
        candidates: list[str] = []

        selectors = [
            "[data-testid='item-description']",
            "div[data-testid='item-description']",
            "section[data-testid='item-description']",
            "div[class*='details'] p",
            "div[class*='description'] p",
            "div[class*='description']",
            "aside p",
        ]

        for selector in selectors:
            try:
                loc = page.locator(selector)
                count = await loc.count()

                for i in range(min(count, 8)):
                    raw = clean_text(await loc.nth(i).inner_text())
                    value = self._sanitize_description(raw)
                    if value:
                        candidates.append(value)
            except Exception:
                continue

        # dodatkowy fallback: szukamy dłuższych bloków po prawej kolumnie
        try:
            right_blocks = page.locator("aside div, section div")
            count = await right_blocks.count()
            for i in range(min(count, 20)):
                raw = clean_text(await right_blocks.nth(i).inner_text())
                value = self._sanitize_description(raw)
                if value:
                    candidates.append(value)
        except Exception:
            pass

        if candidates:
            candidates = sorted(set(candidates), key=len, reverse=True)
            logger.info("[vinted] Wybrany opis: %s", candidates[0][:150])
            return candidates[0]

        return ""

    def _sanitize_description(self, text: str) -> str:
        text = clean_text(text)
        if not text:
            return ""

        lowered = text.lower()

        banned_phrases = [
            "rozwiń swój instagram",
            "rozwin swoj instagram",
            "super fani",
            "podobne rzeczy",
            "strona główna",
            "przedmioty użytkownika",
            "elektronika",
            "telefony komórkowe",
            "telefony komorkowe",
            "obserwuj",
            "kup teraz",
            "promuj",
            "katalog",
            "vinted",
            "przedmioty użytkownika",
            "sprawdź także",
            "sprawdz takze",
            "ochrona kupujących",
            "weryfikacja elektroniki",
            "zapytaj",
            "zaproponuj cenę",
            "zaproponuj cene",
            "wysyłka",
            "wysylka",
        ]

        if any(phrase in lowered for phrase in banned_phrases):
            return ""

        if len(text) < 20:
            return ""

        # opis nie powinien być samą listą parametrów
        param_keys = [
            "marka", "model", "pamięć", "pamiec", "stan", "kolor",
            "blokada sim-lock", "kondycja baterii", "dodane"
        ]
        if sum(1 for key in param_keys if key in lowered) >= 3:
            return ""

        # za dużo cyfr / za mało liter
        letters = sum(ch.isalpha() for ch in text)
        if letters < 15:
            return ""

        if re.search(r"\b(follow|instagram|fans|promo|shop now)\b", lowered):
            return ""

        if len(text) > 500:
            text = text[:500].strip()

        return text

    async def _extract_details_map(self, page) -> dict[str, str]:
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
