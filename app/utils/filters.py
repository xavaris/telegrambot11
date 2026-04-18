from __future__ import annotations

import re

from app.config import Settings
from app.models import Offer


ACCESSORY_KEYWORDS = [
    "plecki", "etui", "case", "pokrowiec", "obudowa", "szkło", "szklo",
    "szkło hartowane", "folia", "ładowarka", "ladowarka", "kabel",
    "przewód", "przewod", "adapter", "airpods", "słuchawki", "sluchawki",
    "uchwyt", "magsafe", "mag safe", "silikon", "cover", "powerbank",
    "pudełko", "pudelko", "karton", "szybka", "bumper", "futerał",
    "futeral", "screen protector", "glass", "szkielko", "car charger",
    "kabel usb", "ładowanie", "ladowanie", "ładowarka magsafe",
]

PARTS_KEYWORDS = [
    "na części", "na czesci", "części", "czesci", "część", "czesc",
    "wyświetlacz", "wyswietlacz", "ekran", "bateria", "taśma", "tasma",
    "face id", "trup", "dawca", "płyta", "plyta", "obiektyw", "szkiełko aparatu",
    "glass only", "back glass", "housing", "ramka", "motherboard"
]

BUNDLE_ONLY_KEYWORDS = [
    "sam karton", "samo pudełko", "samo pudelko", "bez telefonu",
    "bez iphone", "same akcesoria", "samo etui", "same etui",
]

NON_PHONE_ELECTRONICS = [
    "ipad", "macbook", "imac", "apple watch", "watch", "airtag", "tv",
    "telewizor", "monitor", "router", "głośnik", "glosnik", "drukarka",
    "samsung", "xiaomi", "huawei", "ps5", "playstation", "xbox", "switch"
]

PRICE_TOO_LOW_ACCESSORY_THRESHOLD = 250


def is_location_preferred(location: str, settings: Settings) -> bool:
    loc = (location or "").lower()
    if not loc:
        return False

    if any(city in loc for city in settings.preferred_locations_list):
        return True

    if any(region in loc for region in settings.preferred_regions_list):
        return True

    return False


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _has_phone_context(text: str) -> bool:
    return bool(re.search(r"\biphone\b", text))


def looks_like_accessory_or_part(offer: Offer) -> bool:
    title = (offer.title or "").lower().strip()
    desc = (offer.description or "").lower().strip()
    blob = f"{title} {desc}".strip()

    if not offer.model:
        return True

    if not _has_phone_context(blob):
        return True

    if "do iphone" in title or "for iphone" in title:
        return True

    if _contains_any(title, ACCESSORY_KEYWORDS):
        return True

    if _contains_any(title, PARTS_KEYWORDS):
        return True

    if _contains_any(blob, BUNDLE_ONLY_KEYWORDS):
        return True

    if _contains_any(title, NON_PHONE_ELECTRONICS):
        return True

    if offer.price and offer.price < PRICE_TOO_LOW_ACCESSORY_THRESHOLD:
        if _contains_any(blob, ACCESSORY_KEYWORDS) or _contains_any(blob, PARTS_KEYWORDS):
            return True

    return False


def is_likely_real_phone_offer(offer: Offer, settings: Settings) -> bool:
    title = (offer.title or "").lower().strip()
    desc = (offer.description or "").lower().strip()
    blob = f"{title} {desc}".strip()

    if not offer.model:
        return False

    if settings.STRICT_REQUIRE_IPHONE_IN_TITLE and "iphone" not in title:
        # wyjątek: niektóre oferty mają model bez słowa iphone w tytule, ale opis/details je zawiera
        if not re.search(r"\biphone\b", desc):
            return False

    if not re.search(r"\biphone\b", blob):
        return False

    # jeśli model jest np. iphone 12, ale oferta wygląda jak akcesorium "etui do iphone 12"
    if re.search(r"\b(do|for)\s+iphone\b", title) and not re.search(r"\bsprzedam\b|\btelefon\b|\bsmartfon\b", blob):
        return False

    return True


def offer_passes_basic_filters(offer: Offer, settings: Settings) -> bool:
    blob = f"{offer.title} {offer.description}".lower()

    if looks_like_accessory_or_part(offer):
        return False

    if not is_likely_real_phone_offer(offer, settings):
        return False

    if settings.only_models_list and (offer.model or "").lower() not in settings.only_models_list:
        return False

    if any(keyword in blob for keyword in settings.excluded_keywords_list):
        return False

    if offer.price < settings.MIN_PRICE:
        return False

    if offer.price > settings.MAX_PRICE:
        return False

    model_cap = settings.max_price_by_model.get((offer.model or "").lower())
    if model_cap is not None and offer.price > model_cap:
        return False

    return True
