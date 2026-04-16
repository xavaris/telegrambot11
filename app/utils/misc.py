from __future__ import annotations

import html
import re
from typing import Optional


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = html.unescape(value)
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalize_price(price_text: str | None) -> float:
    if not price_text:
        return 0.0
    text = clean_text(price_text).lower()
    text = text.replace("zł", "").replace("pln", "")
    text = text.replace(",", ".")
    text = re.sub(r"[^0-9.]", "", text)
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def absolute_url(base: str, href: str | None) -> str:
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return f"{base.rstrip('/')}/{href.lstrip('/')}"