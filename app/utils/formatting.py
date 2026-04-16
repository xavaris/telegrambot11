from __future__ import annotations

import html

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.constants import PLATFORM_NAMES
from app.models import Offer
from app.utils.filters import is_location_preferred
from app.config import Settings


def build_offer_caption(offer: Offer, settings: Settings) -> str:
    preferred_badge = " ✅ preferowana lokalizacja" if is_location_preferred(offer.location, settings) else ""

    parts = [
        "📱 <b>iPhone Flipper Bot — okazja</b>",
        "",
        f"<b>Model:</b> {html.escape(offer.model or 'Nie rozpoznano')}",
        f"<b>Pojemność:</b> {html.escape(offer.storage or 'Brak danych')}",
        f"<b>Kolor:</b> {html.escape(offer.color or 'Brak danych')}",
        f"<b>Cena:</b> <b>{offer.price:.0f} {html.escape(offer.currency)}</b>",
    ]

    if offer.market_baseline > 0:
        if offer.market_scope == "model+storage":
            scope_label = f"{offer.model} {offer.storage}".strip()
        else:
            scope_label = offer.model

        parts.append(
            f"<b>Score okazji:</b> {offer.score:.1%} "
            f"(mediana {html.escape(scope_label)} z {offer.market_sample_size} ofert: "
            f"{offer.market_baseline:.0f} {html.escape(offer.currency)})"
        )
    else:
        parts.append(f"<b>Score okazji:</b> {offer.score:.1%}")

    parts.extend([
        f"<b>Lokalizacja:</b> {html.escape(offer.location or 'Brak danych')}{preferred_badge}",
        f"<b>Platforma:</b> {html.escape(PLATFORM_NAMES.get(offer.source, offer.source))}",
        f"<b>Stan:</b> {html.escape(offer.condition or 'Brak danych')}",
        "",
        f"<b>Tytuł:</b> {html.escape(offer.title or 'Brak danych')}",
    ])

    clean_description = (offer.description or "").strip()
    if clean_description:
        parts.extend([
            "",
            f"<b>Opis:</b> {html.escape(clean_description[:350])}",
        ])

    parts.extend([
        "",
        f"<b>Link:</b> {html.escape(offer.url)}",
    ])

    return "\n".join(parts)


def build_offer_keyboard(offer: Offer) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Otwórz ogłoszenie", url=offer.url)]
        ]
    )