from __future__ import annotations

from app.models import Offer


def calculate_offer_score(offer: Offer, reference_prices: dict[str, float]) -> float:
    """
    Score > 0 oznacza, że oferta jest tańsza od ceny referencyjnej.
    Im wyższy score, tym lepsza okazja.
    """
    if offer.price <= 0:
        return 0.0

    model = (offer.model or "").lower()
    reference = reference_prices.get(model)
    if not reference or reference <= 0:
        return 0.0

    score = (reference - offer.price) / reference

    # Delikatny bonus za preferowaną lokalizację będzie doklejany osobno.
    return round(score, 4)