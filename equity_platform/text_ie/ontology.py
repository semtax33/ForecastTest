from __future__ import annotations

from dataclasses import dataclass
import re

from equity_platform.ir import ClaimType

from .model import ConceptMention, QuantityKind


@dataclass(frozen=True)
class ConceptDefinition:
    concept: str
    aliases: tuple[str, ...]
    quantity_kinds: tuple[QuantityKind, ...]
    claim_type: ClaimType


CONCEPTS = (
    ConceptDefinition(
        "FIRM_ORDER_BACKLOG",
        (
            "firm order backlog",
            "backlog believed to be firm",
            "firm backlog",
            "unfilled firm orders",
        ),
        (QuantityKind.MONEY,),
        ClaimType.CUSTOMER_DEMAND,
    ),
    ConceptDefinition(
        "FUNDED_BACKLOG",
        ("funded backlog",),
        (QuantityKind.MONEY,),
        ClaimType.CUSTOMER_DEMAND,
    ),
    ConceptDefinition(
        "BACKLOG",
        ("total backlog", "backlog", "unfilled orders"),
        (QuantityKind.MONEY,),
        ClaimType.CUSTOMER_DEMAND,
    ),
    ConceptDefinition(
        "ORDERS",
        ("firm orders", "new orders", "orders"),
        (QuantityKind.MONEY, QuantityKind.COUNT),
        ClaimType.CUSTOMER_DEMAND,
    ),
    ConceptDefinition(
        "REVENUE",
        ("segment revenue", "revenues", "revenue", "sales"),
        (QuantityKind.MONEY,),
        ClaimType.GUIDANCE,
    ),
    ConceptDefinition(
        "OPERATING_MARGIN",
        ("operating earnings margin", "operating margin", "segment margin", "margin"),
        (QuantityKind.PERCENT, QuantityKind.BASIS_POINTS),
        ClaimType.GUIDANCE,
    ),
    ConceptDefinition(
        "DELIVERIES",
        ("aircraft deliveries", "units delivered", "deliveries", "delivered"),
        (QuantityKind.COUNT,),
        ClaimType.OPERATIONAL_EVENT,
    ),
    ConceptDefinition(
        "BOOK_TO_BILL",
        ("book-to-bill ratio", "book-to-bill"),
        (QuantityKind.RATE,),
        ClaimType.CUSTOMER_DEMAND,
    ),
    ConceptDefinition(
        "PRODUCTION",
        ("oil-equivalent production", "production volumes", "production"),
        (QuantityKind.COUNT,),
        ClaimType.OPERATIONAL_EVENT,
    ),
    ConceptDefinition(
        "CAPEX",
        ("capital expenditures", "capital expenditure", "capex"),
        (QuantityKind.MONEY,),
        ClaimType.CAPITAL_ALLOCATION,
    ),
    ConceptDefinition(
        "ADJUSTED_EBITDA",
        ("segment adjusted ebitda", "adjusted ebitda"),
        (QuantityKind.MONEY,),
        ClaimType.GUIDANCE,
    ),
    ConceptDefinition(
        "REALIZED_PRICE",
        ("average realized price", "realized commodity price", "realized price"),
        (QuantityKind.PRICE,),
        ClaimType.PRICE_ACTION,
    ),
    ConceptDefinition(
        "THROUGHPUT",
        ("crude oil throughput", "refinery throughput", "throughput"),
        (QuantityKind.COUNT,),
        ClaimType.OPERATIONAL_EVENT,
    ),
    ConceptDefinition(
        "SUPPLY_CONSTRAINT",
        ("supply chain constraints", "supply constraints"),
        (),
        ClaimType.SUPPLY_CONSTRAINT,
    ),
)

SCOPE_ALIASES = {
    "marine systems": "MARINE_SYSTEMS",
    "aerospace": "AEROSPACE",
    "combat systems": "COMBAT_SYSTEMS",
    "technologies": "TECHNOLOGIES",
    "aeronautics": "AERONAUTICS",
    "missiles and fire control": "MISSILES_AND_FIRE_CONTROL",
    "rotary and mission systems": "ROTARY_AND_MISSION_SYSTEMS",
    "space": "SPACE",
    "upstream": "UPSTREAM",
    "downstream": "DOWNSTREAM",
    "chemicals": "CHEMICALS",
    "midstream": "MIDSTREAM",
}


def definition_for(concept: str) -> ConceptDefinition:
    for definition in CONCEPTS:
        if definition.concept == concept:
            return definition
    raise KeyError(f"Unknown KPI concept: {concept}")


def find_concepts(text: str) -> tuple[ConceptMention, ...]:
    candidates: list[ConceptMention] = []
    for definition in CONCEPTS:
        for alias in definition.aliases:
            pattern = re.compile(
                rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])",
                re.IGNORECASE,
            )
            candidates.extend(
                ConceptMention(definition.concept, match.group(0), match.start(), match.end())
                for match in pattern.finditer(text)
            )
    selected: list[ConceptMention] = []
    for mention in sorted(
        candidates,
        key=lambda item: (item.char_start, -(item.char_end - item.char_start)),
    ):
        if any(
            mention.char_start < prior.char_end and prior.char_start < mention.char_end
            for prior in selected
        ):
            continue
        selected.append(mention)
    concepts = {mention.concept for mention in selected}
    # A generic heading such as ``Order Backlog`` is often flattened into the
    # same block as a more precise phrase.  Preserve the most specific
    # economic concept rather than treating the heading as a second metric.
    if concepts & {"FIRM_ORDER_BACKLOG", "FUNDED_BACKLOG"}:
        selected = [mention for mention in selected if mention.concept != "BACKLOG"]
    return tuple(selected)


def resolve_scope(text: str, heading: str | None) -> str:
    folded = text.casefold()
    for alias, scope in SCOPE_ALIASES.items():
        if alias in folded:
            return scope
    heading_folded = (heading or "").casefold()
    for alias, scope in SCOPE_ALIASES.items():
        if alias in heading_folded:
            return scope
    return "CONSOLIDATED"
