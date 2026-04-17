from __future__ import annotations

from app.config import Settings
from app.models import Offer


ACCESSORY_KEYWORDS = [
    "plecki", "etui", "case", "pokrowiec", "obudowa", "szkło", "szklo",
    "szkło hartowane", "folia", "ładowarka", "ladowarka", "kabel",
    "przewód", "przewod", "adapter", "airpods", "słuchawki", "sluchawki",
    "uchwyt", "magsafe", "mag safe", "silikon", "cover", "powerbank",
    "box", "pudełko", "pudelko", "karton", "szybka", "bumper", "futerał",
    "futeral"
]

PARTS_KEYWORDS = [
    "na części", "na czesci", "części", "czesci", "część", "czesc",
    "wyświetlacz", "wyswietlacz", "ekran", "bateria", "taśma", "tasma",
    "face id", "trup", "dawca", "płyta", "plyta"
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


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def looks_like_accessory_or_part(offer: Offer) -> bool:
    title = (offer.title or "").lower().strip()
    desc = (offer.description or "").lower().strip()
    blob = f"{title} {desc}".strip()

    if not offer.model:
        return True

    if "do iphone" in title:
        return True

    if _contains_any(title, ACCESSORY_KEYWORDS):
        return True

    if _contains_any(title, PARTS_KEYWORDS):
        return True

    if offer.price and offer.price < 300:
        if _contains_any(blob, ACCESSORY_KEYWORDS):
            return True

    return False


def offer_passes_basic_filters(offer: Offer, settings: Settings) -> bool:
    blob = f"{offer.title} {offer.description}".lower()

    if looks_like_accessory_or_part(offer):
        return False

    if settings.only_models_list and offer.model.lower() not in settings.only_models_list:
        return False

    if any(keyword in blob for keyword in settings.excluded_keywords_list):
        return False

    if offer.price < settings.MIN_PRICE:
        return False

    if offer.price > settings.MAX_PRICE:
        return False

    model_cap = settings.max_price_by_model.get(offer.model.lower())
    if model_cap is not None and offer.price > model_cap:
        return False

    return Truefrom __future__ import annotations

from app.config import Settings
from app.models import Offer


ACCESSORY_KEYWORDS = [
    "plecki", "etui", "case", "pokrowiec", "obudowa", "szkło", "szklo",
    "szkło hartowane", "folia", "ładowarka", "ladowarka", "kabel",
    "przewód", "przewod", "adapter", "airpods", "słuchawki", "sluchawki",
    "uchwyt", "magsafe", "mag safe", "silikon", "cover", "powerbank",
    "box", "pudełko", "pudelko", "karton", "szybka", "bumper", "futerał",
    "futeral"
]

PARTS_KEYWORDS = [
    "na części", "na czesci", "części", "czesci", "część", "czesc",
    "wyświetlacz", "wyswietlacz", "ekran", "bateria", "taśma", "tasma",
    "face id", "trup", "dawca", "płyta", "plyta"
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


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def looks_like_accessory_or_part(offer: Offer) -> bool:
    title = (offer.title or "").lower().strip()
    desc = (offer.description or "").lower().strip()
    blob = f"{title} {desc}".strip()

    if not offer.model:
        return True

    if "do iphone" in title:
        return True

    if _contains_any(title, ACCESSORY_KEYWORDS):
        return True

    if _contains_any(title, PARTS_KEYWORDS):
        return True

    if offer.price and offer.price < 300:
        if _contains_any(blob, ACCESSORY_KEYWORDS):
            return True

    return False


def offer_passes_basic_filters(offer: Offer, settings: Settings) -> bool:
    blob = f"{offer.title} {offer.description}".lower()

    if looks_like_accessory_or_part(offer):
        return False

    if settings.only_models_list and offer.model.lower() not in settings.only_models_list:
        return False

    if any(keyword in blob for keyword in settings.excluded_keywords_list):
        return False

    if offer.price < settings.MIN_PRICE:
        return False

    if offer.price > settings.MAX_PRICE:
        return False

    model_cap = settings.max_price_by_model.get(offer.model.lower())
    if model_cap is not None and offer.price > model_cap:
        return False

    return True