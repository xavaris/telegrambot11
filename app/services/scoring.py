from __future__ import annotations

from app.models import Offer


def calculate_offer_score(offer: Offer, reference_prices: dict[str, float]) -> float:
    if offer.price <= 0:
        return 0.0

    model = (offer.model or "").lower()
    reference = reference_prices.get(model)
    if not reference or reference <= 0:
        return 0.0

    return round((reference - offer.price) / reference, 4)
