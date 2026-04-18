from __future__ import annotations

import re

from app.config import Settings
from app.models import Offer
from app.utils.iphone_parser import parse_model


ACCESSORY_KEYWORDS = [
    "etui", "case", "maska", "pokrowiec", "cover", "obudowa",
    "plecki", "futerał", "futeral", "bumper", "silikon", "silicone",
    "szkło", "szklo", "szkło hartowane", "folia", "ochronne",
    "ładowarka", "ladowarka", "kabel", "przewód", "przewod", "adapter",
    "uchwyt", "mag safe", "magsafe", "powerbank", "ring", "strap",
    "pudełko", "pudelko", "karton", "box", "opakowanie",
    "obiektyw", "lens", "filtr", "filter", "nd", "uv", "cpl",
    "moment", "quick lock", "quick-lock", "gimbal", "tripod", "statyw",
    "selfie stick", "kijek", "mikrofon", "microphone", "light", "lampa",
    "stabilizator", "osłona aparatu", "oslona aparatu", "camera protector",
]

PARTS_KEYWORDS = [
    "na części", "na czesci", "części", "czesci", "część", "czesc",
    "wyświetlacz", "wyswietlacz", "ekran", "lcd", "oled", "bateria",
    "taśma", "tasma", "face id", "trup", "dawca", "płyta", "plyta",
    "obiektyw", "szybka", "klapka", "tył", "tyl", "ramka", "gniazdo",
]

BAD_PHONE_CONTEXT = [
    "do iphone",
    "za iphone",
    "for iphone",
    "iphone case",
    "case iphone",
    "etui iphone",
    "maska iphone",
    "pokrowiec iphone",
    "iphone 15/16 pro",
    "iphone 15 16 pro",
    "iphone 15/16",
]

NON_PHONE_PRODUCT_KEYWORDS = [
    "filtr moment",
    "quick lock",
    "variable nd",
    "powerbank",
    "ładowarka indukcyjna",
    "ladowarka indukcyjna",
    "airpods",
    "apple watch",
    "watch strap",
    "pasek",
]

SUSPICIOUS_ONLY_ACCESSORY_TITLES = [
    r"^\s*(etui|case|maska|pokrowiec|cover|obudowa|plecki|filtr|obiektyw|lens)\b",
]

VERY_BAD_VINTED_DESC = [
    "aliexpress",
    "shein",
    "bershka",
    "h&m",
    "zara",
]


def is_location_preferred(location: str, settings: Settings) -> bool:
    loc = (location or "").lower()
    if not loc:
        return False

    if any(city in loc for city in settings.preferred_locations_list):
        return True

    if any(region in loc for region in settings.preferred_regions_list):
        return True

    return False


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split()).strip()


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _matches_any_pattern(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def looks_like_accessory_or_part(offer: Offer) -> bool:
    title = _normalize(offer.title or "")
    desc = _normalize(offer.description or "")
    url = _normalize(offer.url or "")
    blob = f"{title} {desc} {url}".strip()

    parsed_title_model = parse_model(title)

    if _contains_any(blob, ACCESSORY_KEYWORDS):
        return True

    if _contains_any(blob, PARTS_KEYWORDS):
        return True

    if _contains_any(blob, BAD_PHONE_CONTEXT):
        return True

    if _contains_any(blob, NON_PHONE_PRODUCT_KEYWORDS):
        return True

    if _matches_any_pattern(title, SUSPICIOUS_ONLY_ACCESSORY_TITLES):
        return True

    if _contains_any(desc, VERY_BAD_VINTED_DESC) and not parsed_title_model:
        return True

    if offer.price and offer.price < 500:
        if _contains_any(blob, ACCESSORY_KEYWORDS):
            return True
        if _contains_any(blob, BAD_PHONE_CONTEXT):
            return True

    if parsed_title_model and (
        _contains_any(blob, ACCESSORY_KEYWORDS)
        or _contains_any(blob, BAD_PHONE_CONTEXT)
        or _contains_any(blob, NON_PHONE_PRODUCT_KEYWORDS)
    ):
        return True

    return False


def looks_like_real_phone_offer(offer: Offer) -> bool:
    title = _normalize(offer.title or "")
    desc = _normalize(offer.description or "")
    url = _normalize(offer.url or "")
    blob = f"{title} {desc} {url}".strip()

    parsed_title_model = parse_model(title)
    parsed_offer_model = (offer.model or "").strip().lower()

    if not parsed_title_model and not parsed_offer_model:
        return False

    if _contains_any(blob, ACCESSORY_KEYWORDS):
        return False
    if _contains_any(blob, BAD_PHONE_CONTEXT):
        return False
    if _contains_any(blob, PARTS_KEYWORDS):
        return False
    if _contains_any(blob, NON_PHONE_PRODUCT_KEYWORDS):
        return False

    return True


def offer_passes_basic_filters(offer: Offer, settings: Settings) -> bool:
    blob = _normalize(f"{offer.title} {offer.description} {offer.url}")

    if looks_like_accessory_or_part(offer):
        return False

    if not looks_like_real_phone_offer(offer):
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
