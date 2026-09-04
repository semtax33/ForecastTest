from __future__ import annotations

from dataclasses import dataclass
import re

from equity_platform.ir import ClaimType

from .model import ConceptMention, FactTier, QuantityKind


@dataclass(frozen=True)
class ConceptDefinition:
    concept: str
    aliases: tuple[str, ...]
    quantity_kinds: tuple[QuantityKind, ...]
    claim_type: ClaimType
    tier: FactTier = FactTier.CRITICAL


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
        "GROSS_MARGIN",
        ("gross profit margin", "gross margin"),
        (QuantityKind.PERCENT, QuantityKind.BASIS_POINTS),
        ClaimType.GUIDANCE,
    ),
    ConceptDefinition(
        "ADJUSTED_EBITDA_MARGIN",
        (
            "adjusted ebitda margin",
            "segment ebitda margin",
            "ebitda margin",
        ),
        (QuantityKind.PERCENT, QuantityKind.BASIS_POINTS),
        ClaimType.GUIDANCE,
    ),
    ConceptDefinition(
        "OPERATING_MARGIN",
        ("operating earnings margin", "operating margin", "segment margin"),
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
        "OPERATING_INCOME",
        ("segment operating income", "operating income", "operating profit"),
        (QuantityKind.MONEY,),
        ClaimType.GUIDANCE,
    ),
    ConceptDefinition(
        "EBIT",
        ("earnings before interest and taxes", "ebit"),
        (QuantityKind.MONEY,),
        ClaimType.GUIDANCE,
    ),
    ConceptDefinition(
        "NET_DEBT_TO_ADJUSTED_EBITDA",
        (
            "net debt-to-adjusted ebitda",
            "net debt to adjusted ebitda",
            "net debt-to-ebitda",
        ),
        (QuantityKind.RATE,),
        ClaimType.CAPITAL_ALLOCATION,
    ),
    ConceptDefinition(
        "DEBT",
        ("total debt", "long-term debt", "net debt"),
        (QuantityKind.MONEY,),
        ClaimType.CAPITAL_ALLOCATION,
    ),
    ConceptDefinition(
        "CASH",
        ("cash and cash equivalents", "cash balance"),
        (QuantityKind.MONEY,),
        ClaimType.CAPITAL_ALLOCATION,
    ),
    ConceptDefinition(
        "SHARES",
        ("common shares outstanding", "shares outstanding"),
        (QuantityKind.COUNT,),
        ClaimType.CAPITAL_ALLOCATION,
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
        FactTier.NARRATIVE,
    ),
    ConceptDefinition(
        "PRICE_REALIZATION",
        ("price realization", "higher pricing", "lower pricing", "pricing"),
        (QuantityKind.PERCENT, QuantityKind.PRICE),
        ClaimType.PRICE_ACTION,
        FactTier.NARRATIVE,
    ),
    ConceptDefinition(
        "ACTIVITY_VOLUME",
        ("sales volumes", "shipment volumes", "volume growth", "volumes", "volume"),
        # Activity anchors can be physical counts/changes or monetary flows
        # (for example asset-manager net inflows).  The semantic rule must
        # still bind the amount to an explicit activity noun.
        (QuantityKind.PERCENT, QuantityKind.COUNT, QuantityKind.MONEY),
        ClaimType.OPERATIONAL_EVENT,
        FactTier.NARRATIVE,
    ),
    ConceptDefinition(
        "CUSTOMER_DEMAND",
        ("customer demand", "end-market demand", "market demand", "demand"),
        (),
        ClaimType.CUSTOMER_DEMAND,
        FactTier.NARRATIVE,
    ),
    ConceptDefinition(
        "INPUT_COST_PRESSURE",
        ("raw material costs", "input costs", "labor costs", "cost inflation"),
        (),
        ClaimType.COST_PRESSURE,
        FactTier.NARRATIVE,
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


# Alias-level context constraints keep broad vocabulary reusable without
# granting a domain concept to every lexical occurrence.  These are data-only
# guards, not issuer callbacks: the same constraint applies to every company.
ALIAS_REQUIREMENTS = {
    ("DELIVERIES", "delivered"): re.compile(
        r"\s+(?:approximately\s+|about\s+)?\d[\d,.]*\s+(?:aircraft|units?)\b",
        re.IGNORECASE,
    ),
}

ALIAS_FOLLOWING_EXCLUSIONS = {
    ("PRODUCTION", "production"): re.compile(
        r"\s+(?:costs?|expenses?|ramp(?:-up|s)?|contracts?)\b",
        re.IGNORECASE,
    ),
}

ALIAS_PRECEDING_EXCLUSIONS = {
    # In E&P disclosures, "turned to sales" means a well began producing;
    # it is not a revenue mention.
    ("REVENUE", "sales"): re.compile(r"turned\s+to\s*$", re.IGNORECASE),
}


def definition_for(concept: str) -> ConceptDefinition:
    for definition in CONCEPTS:
        if definition.concept == concept:
            return definition
    raise KeyError(f"Unknown KPI concept: {concept}")


def tier_for_concept(concept: str) -> FactTier:
    return definition_for(concept).tier


def find_concepts(text: str) -> tuple[ConceptMention, ...]:
    candidates: list[ConceptMention] = []
    for definition in CONCEPTS:
        for alias in definition.aliases:
            pattern = re.compile(
                rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])",
                re.IGNORECASE,
            )
            for match in pattern.finditer(text):
                key = (definition.concept, alias.casefold())
                requirement = ALIAS_REQUIREMENTS.get(key)
                if requirement is not None and requirement.match(text, match.end()) is None:
                    continue
                exclusion = ALIAS_FOLLOWING_EXCLUSIONS.get(key)
                if exclusion is not None and exclusion.match(text, match.end()) is not None:
                    continue
                preceding_exclusion = ALIAS_PRECEDING_EXCLUSIONS.get(key)
                if (
                    preceding_exclusion is not None
                    and preceding_exclusion.search(text[max(0, match.start() - 32) : match.start()])
                    is not None
                ):
                    continue
                candidates.append(
                    ConceptMention(
                        definition.concept,
                        match.group(0),
                        match.start(),
                        match.end(),
                    )
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
