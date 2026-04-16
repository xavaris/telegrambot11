from __future__ import annotations

from app.config import Settings
from app.models import Offer


def is_location_preferred(location: str, settings: Settings) -> bool:
    loc = (location or "").lower()
    if not loc:
        return False

    if any(city in loc for city in settings.preferred_locations_list):
        return True

    if any(region in loc for region in settings.preferred_regions_list):
        return True

    return False


def offer_passes_basic_filters(offer: Offer, settings: Settings) -> bool:
    title_blob = f"{offer.title} {offer.description}".lower()

    if not offer.model:
        return False

    if settings.only_models_list and offer.model.lower() not in settings.only_models_list:
        return False

    if any(keyword in title_blob for keyword in settings.excluded_keywords_list):
        return False

    if offer.price < settings.MIN_PRICE:
        return False

    if offer.price > settings.MAX_PRICE:
        return False

    model_cap = settings.max_price_by_model.get(offer.model.lower())
    if model_cap is not None and offer.price > model_cap:
        return False

    return True