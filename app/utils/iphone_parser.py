
from __future__ import annotations

import re

from app.constants import COLOR_KEYWORDS, CONDITION_KEYWORDS, IPHONE_MODELS, STORAGE_PATTERNS
from app.utils.misc import clean_text


def parse_model(text: str) -> str:
    value = clean_text(text).lower()
    value = value.replace("apple ", "")
    value = value.replace("iphone’", "iphone ")
    value = value.replace("iphone`", "iphone ")

    for model in sorted(IPHONE_MODELS, key=len, reverse=True):
        if model in value:
            return model

    pattern = re.compile(
        r"\biphone\s*(11|12|13|14|15|16)\s*(pro max|pro|plus|mini)?\b",
        re.IGNORECASE,
    )
    match = pattern.search(value)
    if match:
        number = match.group(1)
        variant = (match.group(2) or "").strip().lower()
        return f"iphone {number} {variant}".strip()
    return ""


def parse_storage(text: str) -> str:
    value = clean_text(text).lower().replace(" ", "")
    for item in STORAGE_PATTERNS:
        if item in value:
            return item.upper()

    match = re.search(r"\b(64|128|256|512)\s*gb\b", value, re.IGNORECASE)
    if match:
        return f"{match.group(1)}GB"

    match = re.search(r"\b1\s*tb\b", value, re.IGNORECASE)
    if match:
        return "1TB"
    return ""


def parse_color(text: str) -> str:
    value = clean_text(text).lower()
    for color in sorted(COLOR_KEYWORDS, key=len, reverse=True):
        if color in value:
            return color.title()
    return ""


def parse_condition(text: str) -> str:
    value = clean_text(text).lower()
    for label, keywords in CONDITION_KEYWORDS.items():
        for keyword in keywords:
            if keyword in value:
                return label
    return ""
