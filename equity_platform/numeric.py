from __future__ import annotations

from math import isfinite
import re


MISSING_NUMBER_TOKENS = frozenset(
    {"", "nan", "none", "null", "—", "–", "-", "nm", "n/m"}
)


def parse_numeric_token(
    value: object,
    *,
    scale: int = 0,
    sign: str | None = None,
) -> float | None:
    """Parse filing numeric tokens without issuer-specific callbacks."""

    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()
    if text.casefold() in MISSING_NUMBER_TOKENS:
        return None
    parenthetical = text.startswith("(") and text.endswith(")")
    cleaned = re.sub(
        r"[^0-9.eE+\-]", "", text.replace(",", "").replace("$", "").strip("()")
    )
    if not cleaned:
        return None
    try:
        parsed = float(cleaned)
    except ValueError:
        return None
    if not isfinite(parsed):
        return None
    if parenthetical or sign == "-":
        parsed = -abs(parsed)
    return parsed * (10.0**scale)
