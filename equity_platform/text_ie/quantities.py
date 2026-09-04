from __future__ import annotations

from dataclasses import replace
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
PERCENT = re.compile(
    rf"(?P<raw>(?P<number>{NUMBER})\s*(?:%|percent\b|per\s+cent\b))",
    re.IGNORECASE,
)
BASIS_POINTS = re.compile(
    rf"(?P<raw>(?P<number>{NUMBER})\s*(?:basis\s+points?|bps?|bp))",
    re.IGNORECASE,
)
RATE = re.compile(rf"(?P<raw>(?P<number>{NUMBER})\s*(?:x\b|times?\b))", re.IGNORECASE)
COUNT = re.compile(
    rf"(?P<raw>(?P<number>{NUMBER})\s*(?P<scale>billion|million|thousand)?\s*(?P<unit>aircraft|units?|rigs?|wells?|boe(?:/d|\s+per\s+day)?|mboe(?:/d|\s+per\s+day)?|mcf(?:/d|\s+per\s+day)?|mmcf(?:e)?(?:/d|\s+per\s+day)?|bcfe(?:/d|\s+per\s+day)?|barrels?(?:/d|\s+per\s+day)?|bpd|mbpd|dth))",
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


def _count_unit(raw: str) -> str:
    unit = re.sub(r"\s+", "_", raw.strip().upper())
    unit = unit.replace("/D", "_PER_D").replace("_PER_DAY", "_PER_D")
    return unit


def _inherit_range_units(
    text: str,
    mentions: list[QuantityMention],
) -> list[QuantityMention]:
    """Normalize abbreviated ranges such as ``$410 to $440 million``.

    Filings routinely put the scale/unit only on the second endpoint.  The
    inherited value is accepted only across a bounded range connector and for
    the same quantity kind; no cross-sentence or issuer-specific inference is
    performed.
    """

    ordered = sorted(mentions, key=lambda item: item.char_start)
    for index in range(1, len(ordered)):
        left, right = ordered[index - 1], ordered[index]
        connector = text[left.char_end : right.char_start]
        if left.kind is not right.kind or not re.fullmatch(
            r"\s*(?:to|through|and|[-–—])\s*", connector, re.IGNORECASE
        ):
            continue
        if left.kind is QuantityKind.MONEY and left.value < 1e6 <= right.value:
            right_number = _number(re.search(NUMBER, right.raw).group(0))
            if right_number:
                ordered[index - 1] = replace(
                    left,
                    value=left.value * (right.value / right_number),
                )

    # The second dollar sign is also often elided: ``$34-35 billion``.
    # Create the missing endpoint and propagate the terminal scale to both.
    money_additions: list[QuantityMention] = []
    for index, left in enumerate(tuple(ordered)):
        if left.kind is not QuantityKind.MONEY or left.value >= 1e6:
            continue
        suffix = text[left.char_end : min(len(text), left.char_end + 64)]
        match = re.match(
            rf"\s*(?:to|through|[-–—])\s*(?P<number>{NUMBER})\s*"
            r"(?P<scale>billion|million|bn|mm|b|m)\b",
            suffix,
            re.IGNORECASE,
        )
        if match is None:
            continue
        scale = SCALES[match.group("scale").casefold()]
        start = left.char_end + match.start("number")
        end = left.char_end + match.end("scale")
        if any(start < item.char_end and item.char_start < end for item in ordered):
            continue
        ordered[index] = replace(left, value=left.value * scale)
        money_additions.append(
            QuantityMention(
                kind=QuantityKind.MONEY,
                value=_number(match.group("number")) * scale,
                unit="USD",
                raw=text[start:end],
                char_start=start,
                char_end=end,
            )
        )

    # Count ranges often omit the entire first unit: ``2.35 to 2.40 Bcfe/d``.
    additions: list[QuantityMention] = []
    for right in ordered:
        if right.kind is not QuantityKind.COUNT:
            continue
        prefix_start = max(0, right.char_start - 48)
        prefix = text[prefix_start : right.char_start]
        match = re.search(
            rf"(?P<number>{NUMBER})\s*(?:to|through|[-–—])\s*$",
            prefix,
            re.IGNORECASE,
        )
        if match is None:
            continue
        start = prefix_start + match.start("number")
        end = prefix_start + match.end("number")
        if any(start < item.char_end and item.char_start < end for item in ordered):
            continue
        raw_number = _number(match.group("number"))
        right_number_match = re.search(NUMBER, right.raw)
        if right_number_match is None:
            continue
        right_number = _number(right_number_match.group(0))
        scale = right.value / right_number if right_number else 1.0
        additions.append(
            QuantityMention(
                kind=QuantityKind.COUNT,
                value=raw_number * scale,
                unit=right.unit,
                raw=match.group("number"),
                char_start=start,
                char_end=end,
            )
        )
    return sorted(
        [*ordered, *money_additions, *additions],
        key=lambda item: item.char_start,
    )


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
                resolved_unit = _count_unit(str(match.group("unit")))
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
    return tuple(_inherit_range_units(text, mentions))


def extract_years(text: str) -> tuple[tuple[int, int, int], ...]:
    return tuple(
        (int(match.group("year")), match.start(), match.end())
        for match in YEAR.finditer(text)
    )
