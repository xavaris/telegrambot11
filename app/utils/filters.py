from __future__ import annotations

from app.config import Settings
from app.models import Offer


ACCESSORY_KEYWORDS = [
    "plecki",
    "etui",
    "case",
    "pokrowiec",
    "obudowa",
    "szkło",
    "szklo",
    "szkło hartowane",
    "folia",
    "ładowarka",
    "ladowarka",
    "kabel",
    "przewód",
    "przewod",
    "adapter",
    "airpods",
    "słuchawki",
    "sluchawki",
    "uchwyt",
    "magsafe",
    "mag safe",
    "silikon",
    "cover",
    "powerbank",
    "box",
    "pudełko",
    "pudelko",
    "karton",
    "szybka",
    "ochrona ekranu",
    "ochrona obudowy",
    "bumper",
    "armor case",
    "wallet case",
    "futerał",
    "futeral",
]

PARTS_KEYWORDS = [
    "na części",
    "na czesci",
    "części",
    "czesci",
    "część",
    "czesc",
    "wyświetlacz",
    "wyswietlacz",
    "ekran",
    "bateria",
    "taśma",
    "tasma",
    "face id",
    "trup",
    "dawca",
    "płyta",
    "plyta",
]

PHONE_SALE_HINTS = [
    "sprzedam",
    "telefon",
    "iphone",
    "smartfon",
    "stan",
    "kondycja baterii",
    "battery health",
    "gb",
    "tb",
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
    """
    Odrzuca akcesoria i części, ale nie odrzuca normalnego telefonu tylko dlatego,
    że w opisie ktoś dopisał np. 'w zestawie ładowarka'.
    """
    title = (offer.title or "").lower().strip()
    desc = (offer.description or "").lower().strip()
    blob = f"{title} {desc}".strip()

    # Jeżeli nie rozpoznaliśmy modelu, to bardzo często nie jest to właściwy telefon.
    if not offer.model:
        return True

    # "do iphone" w tytule prawie zawsze oznacza akcesorium, nie telefon.
    if "do iphone" in title:
        return True

    # Jeśli tytuł wygląda jak akcesorium, odrzucamy od razu.
    if _contains_any(title, ACCESSORY_KEYWORDS):
        return True

    # Jeśli tytuł wygląda jak części / naprawa, odrzucamy.
    if _contains_any(title, PARTS_KEYWORDS):
        return True

    # Jeśli cena jest bardzo niska, a opis zawiera słowa akcesoryjne,
    # to to prawie na pewno nie jest telefon.
    if offer.price and offer.price < 300:
        if _contains_any(blob, ACCESSORY_KEYWORDS):
            return True

    # Jeśli cena jest bardzo niska, a nie ma żadnych sensownych oznak sprzedaży telefonu,
    # to też odrzucamy.
    if offer.price and offer.price < 500:
        if not _contains_any(blob, PHONE_SALE_HINTS):
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
