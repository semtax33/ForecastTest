from __future__ import annotations

import re

from .model import QuantityKind, QuantityMention


NUMBER = r"-?\d[\d,]*(?:\.\d+)?"
MONEY = re.compile(
    rf"(?P<raw>\$\s*(?P<number>{NUMBER})\s*(?P<scale>billion|million|bn|mm|b|m)?)",
    re.IGNORECASE,
)
PRICE = re.compile(
    rf"(?P<raw>\$\s*(?P<number>{NUMBER})\s*(?:per|/)\s*(?P<unit>mcf|mmcf|mcfe|boe|bbl|barrel|gallon))",
    re.IGNORECASE,
)
PERCENT = re.compile(rf"(?P<raw>(?P<number>{NUMBER})\s*%)", re.IGNORECASE)
BASIS_POINTS = re.compile(
    rf"(?P<raw>(?P<number>{NUMBER})\s*(?:basis\s+points?|bps?|bp))",
    re.IGNORECASE,
)
RATE = re.compile(rf"(?P<raw>(?P<number>{NUMBER})\s*x\b)", re.IGNORECASE)
COUNT = re.compile(
    rf"(?P<raw>(?P<number>{NUMBER})\s*(?P<scale>billion|million|thousand)?\s*(?P<unit>aircraft|units?|rigs?|wells?|boe(?:/d)?|mboe(?:/d)?|mcf(?:/d)?|mmcf(?:e)?(?:/d)?|bcfe|barrels?|bpd|mbpd|dth))",
    re.IGNORECASE,
)
# A filing year is commonly followed by sentence punctuation (``2026.``).
# Decimal protection belongs to numeric-quantity parsing, not to the year
# boundary: requiring non-digits is sufficient and does not drop that case.
YEAR = re.compile(r"(?<!\d)(?P<year>20\d{2})(?!\d)")

SCALES = {
    "": 1.0,
    "b": 1e9,
    "bn": 1e9,
    "billion": 1e9,
    "m": 1e6,
    "mm": 1e6,
    "million": 1e6,
}


def _number(raw: str) -> float:
    return float(raw.replace(",", ""))


def extract_quantities(text: str) -> tuple[QuantityMention, ...]:
    mentions: list[QuantityMention] = []
    occupied: list[tuple[int, int]] = []

    def add(pattern: re.Pattern[str], kind: QuantityKind, unit: str) -> None:
        for match in pattern.finditer(text):
            if any(match.start() < end and start < match.end() for start, end in occupied):
                continue
            value = _number(match.group("number"))
            resolved_unit = unit
            if kind is QuantityKind.MONEY:
                scale = str(match.groupdict().get("scale") or "").casefold()
                value *= SCALES[scale]
                resolved_unit = "USD"
            elif kind is QuantityKind.COUNT:
                scale = str(match.groupdict().get("scale") or "").casefold()
                value *= {
                    "": 1.0,
                    "thousand": 1e3,
                    "million": 1e6,
                    "billion": 1e9,
                }[scale]
                resolved_unit = str(match.group("unit")).upper().replace("/", "_PER_")
            elif kind is QuantityKind.PRICE:
                resolved_unit = f"USD_PER_{str(match.group('unit')).upper()}"
            mentions.append(
                QuantityMention(
                    kind=kind,
                    value=value,
                    unit=resolved_unit,
                    raw=match.group("raw"),
                    char_start=match.start(),
                    char_end=match.end(),
                )
            )
            occupied.append((match.start(), match.end()))

    add(PRICE, QuantityKind.PRICE, "USD_PER_UNIT")
    add(MONEY, QuantityKind.MONEY, "USD")
    add(BASIS_POINTS, QuantityKind.BASIS_POINTS, "BASIS_POINTS")
    add(PERCENT, QuantityKind.PERCENT, "PERCENT")
    add(RATE, QuantityKind.RATE, "X")
    add(COUNT, QuantityKind.COUNT, "COUNT")
    return tuple(sorted(mentions, key=lambda item: item.char_start))


def extract_years(text: str) -> tuple[tuple[int, int, int], ...]:
    return tuple(
        (int(match.group("year")), match.start(), match.end())
        for match in YEAR.finditer(text)
    )
