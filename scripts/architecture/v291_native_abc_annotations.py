from __future__ import annotations

import csv
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Iterable

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT


CANDIDATES = (
    PROJECT_ROOT
    / "output/platform_v2_9_1_staged_validation/native_abc_candidate_blocks.csv"
)
ANNOTATIONS = (
    PROJECT_ROOT
    / "data-lake/gold/parser/text_ie/v291_native_abc_stage_gold.jsonl"
)
SELECTION_SHA256 = "ca4432bb655fb48cf360b395c2067d9d18d04e1786d1702eee57cf3c9f360d2e"
ANNOTATION_SOURCE = "CODEX_MANUAL_TWO_PASS_RESEARCH_REVIEW_NOT_CERTIFICATION_ELIGIBLE"


EXPECTED_SELECTION_IDS = frozenset(
    """
    94c4776ebf0363e2d330 d202c287860fe0c6b7fe 873e794d23f4f3952522
    361d50151dae62bcdba5 56fb6b53703ca63b3af0 36deae42b30b90e50151
    e2d7cd562f50d8f08b9e 887934383e000180da2c 964c23dd7c924456c207
    04057545091bdd84bc23 21bd8d653271faeae104 218b071bc8f7a8d533af
    17cab2c6ff7339d13ee1 3ea4c290bb5cba65a151 fd155ec40de7f7c94b34
    db8fbac63d7d928cdc77 1cda1eaef821582012dc 0bd0a43b991e6a5bf721
    36bdd83410b4681e4bc4 cf2e35d17804b6e2b7c6 9173dc7deb05db8508da
    56f48a15537544c93e9d b55670e7e608942336a1 b11741e90c61391c16d3
    f2201097197ae986d5fd 1e55d8d4ea4310b8f20d f1b1bbc155ea38ee7c37
    1cfcc3ee53d14c06a00b 739e7c1af067b5b0f96c 8f24d54f9767e972f3a4
    bdb226a35c3d88a69d2b 96e8d699a90b0e0b8eb4 5a0706d8a264e016ee8a
    a148a87c11cc8a1ec915 a2a3f7b594c14be69fa5 a306a48b40353a91eb91
    2f656fc6344a4fe2f5b2 72b45d57448919f521b0 d69961549b68e6a784b8
    b534c0cb330096e0b41d 2a9b6cb50421894570aa 6399b7033e11db334427
    46b34c3b6825afc9b3cb 28d19d9b3a09a3230068 1493646160c4c5035939
    5f5109cc540b0a068f5a 36c9b5e84553c2bf4bce 4ecb9035b93a839a6d5e
    a8c3af4d16c674d462fb c2602dfde8cc5ec599da f30d136161ffd42c7501
    6f219b10a437c1ddba13 5b39406598599e0e9352 74604d94d1916b7eeb1f
    0d3f246119a07396973c 6571de631c5a69442d4b 2216edbda03a9ffdbfd2
    1442d5850c637422827f 830321b90f5cd78dac38 8217ae717d51a95fe443
    8c87a5ebefa7f5001e8e d7e02db08fcbf02dfe69 ce23be0baac59489e4a0
    8a83e79825b875b0655b f9f20add0a4d5344c693 d4fc35ae4e6a3d840306
    f5bbfe51e51cececafc9 45dc60979a527476c636 be6e05f8a7a5a27b3712
    1d420b8aded27c51678d ce560c58d2edf8b92220 d4e93dd5750fc5f414fe
    3e7369af5e2704e7891a a875082e5aa22223de3a 908a9fd64e639cb8f117
    2f151552521ecd0c492c 3c6ec44cda6c538e238b 2d26c8b48f7656828d8a
    3c792b1b28440e2b8d75 db0ff39af9edda03fc5d c40120352d8803cfd194
    2ef80c2463aad30691a2 a504798e5c209f1c440c 4df0fd50289f579fa9f3
    b959b87e2084e4ce05ca 9f6e86e8800e4009cbc1 ffb3604e8ec94bf9c211
    76143bad87e7dfb2cef8 8e6ed6fd3f297c02ed0b 22d1c35dcbf94afea737
    a8fa74e1f48716fd747a 838c54a11253f7c51786 8eec57dbbee16feb7306
    d9e8d76a41ee6e214fd0 036b471fef87987ba70d 8f0b8c55586ca6380aa9
    f751068118d43b1da995 45c353972e4f70363506 8f355136083964a7e5a3
    6936cbc5a59890d9f2c0 d38eb7fa488b69ad2a27 4df9d466fc4d6509e6f2
    3295421571ed8d57ceb4 6b02966fa09b723332ed c580f7f645bdcfb52675
    5d3d4f38509bf5ae450a fae95864d2dfc5ce428a 0f3d991523294dcfa77c
    5392604dc0b76bf0a193 2e210caa3d22eef5a6cf 210e90da3d0857665944
    7aeb7935d6981b9c2399 ba0d5c43220b06c8a1c4 4b9f1eae996b44229e4b
    1fffa5a44fb28f564942 efb7cccecf283b0e8dcf 877303c31f5e3a99c40e
    bdc14b1988d644ca92d9 eed948beee41e2f2ce8d c605c2a9f70de0a72f6e
    """.split()
)

TABLE_IDS = frozenset(
    {
        "04057545091bdd84bc23",
        "cf2e35d17804b6e2b7c6",
        "a2a3f7b594c14be69fa5",
        "74604d94d1916b7eeb1f",
        "1442d5850c637422827f",
        "a504798e5c209f1c440c",
        "838c54a11253f7c51786",
        "d9e8d76a41ee6e214fd0",
        "6936cbc5a59890d9f2c0",
        "4df9d466fc4d6509e6f2",
        "fae95864d2dfc5ce428a",
        "210e90da3d0857665944",
        "ba0d5c43220b06c8a1c4",
        "4b9f1eae996b44229e4b",
        "c605c2a9f70de0a72f6e",
    }
)

SUPPORTED_FACT_IDS = frozenset(
    {
        "94c4776ebf0363e2d330",
        "1442d5850c637422827f",
        "4df9d466fc4d6509e6f2",
        "ba0d5c43220b06c8a1c4",
        "877303c31f5e3a99c40e",
        "c605c2a9f70de0a72f6e",
    }
)

CONCEPT_ONLY_IDS = frozenset(
    {
        "887934383e000180da2c",
        "72b45d57448919f521b0",
        "d69961549b68e6a784b8",
        "9f6e86e8800e4009cbc1",
        "22d1c35dcbf94afea737",
        "d9e8d76a41ee6e214fd0",
        "2e210caa3d22eef5a6cf",
        "1fffa5a44fb28f564942",
        "bdc14b1988d644ca92d9",
        "eed948beee41e2f2ce8d",
    }
)

UNSUPPORTED_METRIC_IDS = frozenset(
    {
        "a2a3f7b594c14be69fa5",  # claims development
        "46b34c3b6825afc9b3cb",  # assets under management
        "6571de631c5a69442d4b",  # unfunded investment commitment
        "8217ae717d51a95fe443",  # compensation expense
        "3c792b1b28440e2b8d75",  # share repurchases, not shares outstanding
        "a504798e5c209f1c440c",  # insurance premiums and benefit ratios
        "838c54a11253f7c51786",  # equity-unit underwriting schedule
        "d9e8d76a41ee6e214fd0",  # FFO per share and third-party retailer sales
        "6936cbc5a59890d9f2c0",  # isolated debt-instrument table fragment
        "c580f7f645bdcfb52675",  # EPS
        "fae95864d2dfc5ce428a",  # make-whole share schedule
        "210e90da3d0857665944",  # property ownership/area fragment
        "4b9f1eae996b44229e4b",  # isolated debt-instrument table fragment
    }
)

# These rows contain direct accounting-policy/table evidence that the selected
# text itself identifies as a financial-statement note.  The broad selection
# candidate flag is deliberately not copied wholesale because it extends into
# later filing items for some issuers.
NOTE_IDS = frozenset(
    {
        "d202c287860fe0c6b7fe",
        "964c23dd7c924456c207",
        "04057545091bdd84bc23",
        "21bd8d653271faeae104",
        "17cab2c6ff7339d13ee1",
        "3ea4c290bb5cba65a151",
        "fd155ec40de7f7c94b34",
        "0bd0a43b991e6a5bf721",
        "36bdd83410b4681e4bc4",
        "cf2e35d17804b6e2b7c6",
        "1e55d8d4ea4310b8f20d",
        "f1b1bbc155ea38ee7c37",
        "bdb226a35c3d88a69d2b",
        "96e8d699a90b0e0b8eb4",
        "a2a3f7b594c14be69fa5",
        "2f656fc6344a4fe2f5b2",
        "72b45d57448919f521b0",
        "d69961549b68e6a784b8",
        "b534c0cb330096e0b41d",
        "2a9b6cb50421894570aa",
        "28d19d9b3a09a3230068",
        "1493646160c4c5035939",
        "5f5109cc540b0a068f5a",
        "36c9b5e84553c2bf4bce",
        "4ecb9035b93a839a6d5e",
        "c2602dfde8cc5ec599da",
        "f30d136161ffd42c7501",
        "5b39406598599e0e9352",
        "6571de631c5a69442d4b",
        "2216edbda03a9ffdbfd2",
        "1442d5850c637422827f",
    }
)


def _literal_span(
    text: str,
    literal: str,
    *,
    occurrence: int | None = None,
) -> tuple[int, int]:
    starts: list[int] = []
    cursor = 0
    while True:
        start = text.find(literal, cursor)
        if start < 0:
            break
        starts.append(start)
        cursor = start + 1
    if not starts:
        raise ValueError(f"literal not found: {literal!r}")
    if occurrence is None:
        if len(starts) != 1:
            raise ValueError(
                f"ambiguous literal {literal!r}; specify one of {len(starts)} occurrences"
            )
        occurrence = 0
    if occurrence < 0 or occurrence >= len(starts):
        raise ValueError(f"literal occurrence out of range: {literal!r} #{occurrence}")
    start = starts[occurrence]
    return start, start + len(literal)


@dataclass
class GraphBuilder:
    text: str
    quantities: list[dict[str, object]] = field(default_factory=list)
    concepts: list[dict[str, object]] = field(default_factory=list)
    candidate_edges: list[dict[str, str]] = field(default_factory=list)
    binding_edges: list[dict[str, str]] = field(default_factory=list)
    role_edges: list[dict[str, str]] = field(default_factory=list)
    frames: list[dict[str, object]] = field(default_factory=list)

    def concept(
        self,
        literal: str,
        concept: str,
        *,
        occurrence: int | None = None,
    ) -> str:
        start, end = _literal_span(self.text, literal, occurrence=occurrence)
        node_id = f"c{len(self.concepts) + 1}"
        self.concepts.append(
            {
                "node_id": node_id,
                "concept": concept,
                "char_start": start,
                "char_end": end,
            }
        )
        return node_id

    def quantity(
        self,
        literal: str,
        kind: str,
        value: float,
        *,
        occurrence: int | None = None,
    ) -> str:
        start, end = _literal_span(self.text, literal, occurrence=occurrence)
        return self.quantity_at(start, end, kind, value)

    def quantity_at(self, start: int, end: int, kind: str, value: float) -> str:
        node_id = f"q{len(self.quantities) + 1}"
        self.quantities.append(
            {
                "node_id": node_id,
                "kind": kind,
                "value": float(value),
                "char_start": start,
                "char_end": end,
            }
        )
        return node_id

    def bind(self, concept_id: str, quantity_id: str, role: str) -> None:
        pair = {"concept_id": concept_id, "quantity_id": quantity_id}
        self.candidate_edges.append(dict(pair))
        self.binding_edges.append(dict(pair))
        self.role_edges.append({**pair, "role": role})

    def frame(
        self,
        concept: str,
        semantic: str,
        value: float,
        **extra: object,
    ) -> None:
        self.frames.append(
            {
                "concept": concept,
                "frame": semantic,
                "value": float(value),
                "tier": "CRITICAL",
                **extra,
            }
        )


def _annotate_activity_levels(graph: GraphBuilder) -> None:
    served = graph.concept("served", "ACTIVITY_VOLUME")
    transported = graph.concept("transporting", "ACTIVITY_VOLUME")
    pairs = graph.quantity("20,000", "COUNT", 20_000.0)
    pounds = graph.quantity("1.0 billion", "COUNT", 1_000_000_000.0)
    graph.bind(served, pairs, "VALUE_CURRENT")
    graph.bind(transported, pounds, "VALUE_CURRENT")
    graph.frame("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 20_000.0)
    graph.frame("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 1_000_000_000.0)


def _annotate_cash_fair_value_table(graph: GraphBuilder) -> None:
    cash = graph.concept("Cash and cash equivalents", "CASH")
    specs = (
        ("$ 34,444", 0, 34_444.0, "VALUE_CURRENT"),
        ("$ 34,444", 1, 34_444.0, "VALUE_CURRENT"),
        ("$ 35,570", 0, 35_570.0, "VALUE_PRIOR"),
        ("$ 35,570", 1, 35_570.0, "VALUE_PRIOR"),
    )
    for literal, occurrence, value, role in specs:
        quantity = graph.quantity(
            literal,
            "MONEY",
            value,
            occurrence=occurrence,
        )
        graph.bind(cash, quantity, role)
    graph.frame("CASH", "COMPARATIVE", 34_444.0)
    graph.frame("PRIOR_YEAR_CASH", "COMPARATIVE", 35_570.0)


def _annotate_balance_sheet(graph: GraphBuilder) -> None:
    cash = graph.concept("Cash and cash equivalents", "CASH")
    debt = graph.concept("Total debt", "DEBT")
    net_debt = graph.concept(
        "Debt less cash, cash equivalents and marketable securities",
        "DEBT",
    )
    groups = (
        (
            cash,
            "CASH",
            ("$ 1,370", "$ 1,288", "$ 1,215"),
            (1_370_000_000.0, 1_288_000_000.0, 1_215_000_000.0),
        ),
        (
            debt,
            "DEBT",
            ("$ 7,857", "$ 7,988", "$ 8,758"),
            (7_857_000_000.0, 7_988_000_000.0, 8_758_000_000.0),
        ),
        (
            net_debt,
            "DEBT",
            ("$ 6,404", "$ 6,593", "$ 7,346"),
            (6_404_000_000.0, 6_593_000_000.0, 7_346_000_000.0),
        ),
    )
    for concept_id, concept, literals, values in groups:
        for index, (literal, value) in enumerate(zip(literals, values, strict=True)):
            quantity = graph.quantity(literal, "MONEY", value)
            graph.bind(
                concept_id,
                quantity,
                "VALUE_CURRENT" if index == 0 else "VALUE_PRIOR",
            )
            graph.frame(
                concept if index == 0 else f"PRIOR_YEAR_{concept}",
                "COMPARATIVE",
                value,
            )


def _annotate_capex_table(graph: GraphBuilder) -> None:
    header = graph.concept("CAPITAL EXPENDITURES", "CAPEX")
    operational = graph.concept("Operational capital expenditures", "CAPEX")
    current = graph.concept("Capital Expenditures", "CAPEX", occurrence=0)
    prior = graph.concept("Capital Expenditures", "CAPEX", occurrence=1)
    component_literals = (
        "$ 4,299", "$ 427", "$ 214",
        "135,146", "104,989", "51,826",
        "26,432", "1,358", "684",
        "165,877", "106,774", "52,724",
        "122,207", "56,604", "28,485",
        "65,978", "106,665", "41,966",
        "$ 354,062", "$ 270,043", "$ 123,175",
    )
    component_values = (
        4_299_000.0, 427_000.0, 214_000.0,
        135_146_000.0, 104_989_000.0, 51_826_000.0,
        26_432_000.0, 1_358_000.0, 684_000.0,
        165_877_000.0, 106_774_000.0, 52_724_000.0,
        122_207_000.0, 56_604_000.0, 28_485_000.0,
        65_978_000.0, 106_665_000.0, 41_966_000.0,
        354_062_000.0, 270_043_000.0, 123_175_000.0,
    )
    for index, (literal, value) in enumerate(
        zip(component_literals, component_values, strict=True)
    ):
        quantity = graph.quantity(literal, "MONEY", value)
        owner = operational if 15 <= index <= 17 else header
        graph.bind(owner, quantity, "VALUE_CURRENT")
        graph.frame("CAPEX", "ABSOLUTE_VALUE", value)
    period_groups = (
        (
            current,
            "CAPEX",
            ("$ 445,285", "$ 285,469", "$ 130,211"),
            (445_285_000.0, 285_469_000.0, 130_211_000.0),
            "VALUE_CURRENT",
        ),
        (
            prior,
            "PRIOR_YEAR_CAPEX",
            ("$ 474,225", "$ 251,013", "$ 120,364"),
            (474_225_000.0, 251_013_000.0, 120_364_000.0),
            "VALUE_PRIOR",
        ),
    )
    for concept_id, concept, literals, values, role in period_groups:
        for literal, value in zip(literals, values, strict=True):
            quantity = graph.quantity(literal, "MONEY", value)
            graph.bind(concept_id, quantity, role)
            graph.frame(concept, "COMPARATIVE", value)


def _annotate_acquisition_volume(graph: GraphBuilder) -> None:
    volume = graph.concept("volume", "ACTIVITY_VOLUME")
    for literal, value in (("0.6%", 0.6), ("0.1%", 0.1)):
        quantity = graph.quantity(literal, "PERCENT", value)
        graph.bind(volume, quantity, "DELTA")
        graph.frame("ACTIVITY_VOLUME", "CHANGE_BY", value)


def _row_value_spans(
    text: str,
    row_label: str,
    raw_values: Iterable[str],
) -> tuple[tuple[int, int], ...]:
    cursor = text.index(row_label) + len(row_label)
    output = []
    for raw in raw_values:
        start = text.find(raw, cursor)
        if start < 0:
            raise ValueError(f"table value {raw!r} not found after row {row_label!r}")
        end = start + len(raw)
        output.append((start, end))
        cursor = end
    return tuple(output)


def _annotate_sales_driver_table(graph: GraphBuilder) -> None:
    sales = graph.concept("SALES CHANGE", "REVENUE")
    pricing = graph.concept("Pricing", "PRICE_REALIZATION")
    reported_volume = graph.concept("Volume (1)", "ACTIVITY_VOLUME")
    organic_volume = graph.concept("Volume", "ACTIVITY_VOLUME", occurrence=1)
    owners = (sales, sales, reported_volume, organic_volume, pricing)
    concepts = (
        "REVENUE",
        "REVENUE",
        "ACTIVITY_VOLUME",
        "ACTIVITY_VOLUME",
        "PRICE_REALIZATION",
    )
    rows = (
        ("Total Company", ("6.6 %", "2.6 %", "1.0 %", "0.7 %", "1.9 %", "3.8 %"), (6.6, 2.6, 1.0, 0.7, 1.9)),
        ("North America (2)", ("(2.4) %", "(2.6) %", "(3.6) %", "(3.6) %", "0.9 %", "0.2 %"), (-2.4, -2.6, -3.6, -3.6, 0.9)),
        ("Latin America", ("14.3 %", "5.3 %", "2.3 %", "2.3 %", "3.1 %", "8.9 %"), (14.3, 5.3, 2.3, 2.3, 3.1)),
        ("Europe, Middle East & Africa (2)", ("7.5 %", "2.7 %", "2.7 %", "2.7 %", "— %", "4.9 %"), (7.5, 2.7, 2.7, 2.7, 0.0)),
        ("Asia Pacific (2)", ("6.9 %", "5.4 %", "4.3 %", "4.3 %", "1.1 %", "1.5 %"), (6.9, 5.4, 4.3, 4.3, 1.1)),
        ("Total CP Products", ("7.1 %", "2.8 %", "1.4 %", "1.4 %", "1.3 %", "4.4 %"), (7.1, 2.8, 1.4, 1.4, 1.3)),
        ("Hill’s Pet Nutrition", ("5.0 %", "2.1 %", "(0.5) %", "(1.8) %", "3.9 %", "1.7 %"), (5.0, 2.1, -0.5, -1.8, 3.9)),
        ("Emerging Markets (3)", ("11.0 %", "5.5 %", "3.2 %", "3.2 %", "2.3 %", "5.5 %"), (11.0, 5.5, 3.2, 3.2, 2.3)),
        ("Developed Markets", ("3.2 %", "0.4 %", "(0.7) %", "(1.3) %", "1.6 %", "2.3 %"), (3.2, 0.4, -0.7, -1.3, 1.6)),
    )
    for row_label, raw_values, values in rows:
        spans = _row_value_spans(graph.text, row_label, raw_values)
        for index, (start, end) in enumerate(spans[:5]):
            quantity = graph.quantity_at(start, end, "PERCENT", values[index])
            graph.bind(owners[index], quantity, "DELTA")
            graph.frame(concepts[index], "CHANGE_BY", values[index])


def _annotate_concept_only(candidate_id: str, graph: GraphBuilder) -> None:
    if candidate_id == "887934383e000180da2c":
        graph.concept("not delivered on schedule or in sufficient volumes", "SUPPLY_CONSTRAINT")
    elif candidate_id == "72b45d57448919f521b0":
        graph.concept("revenues", "REVENUE")
    elif candidate_id == "d69961549b68e6a784b8":
        graph.concept("Cash and cash equivalents", "CASH")
        graph.concept("cash equivalents", "CASH", occurrence=1)
    elif candidate_id == "9f6e86e8800e4009cbc1":
        graph.concept("adjusted operating income", "OPERATING_INCOME", occurrence=0)
        graph.concept("Adjusted operating income", "OPERATING_INCOME", occurrence=0)
        graph.concept("adjusted operating income", "OPERATING_INCOME", occurrence=1)
    elif candidate_id == "22d1c35dcbf94afea737":
        graph.concept("adjusted operating income", "OPERATING_INCOME")
    elif candidate_id == "d9e8d76a41ee6e214fd0":
        graph.concept("Capital Expenditures", "CAPEX")
    elif candidate_id == "2e210caa3d22eef5a6cf":
        graph.concept("sales", "REVENUE", occurrence=0)
        graph.concept("volume growth", "ACTIVITY_VOLUME")
        graph.concept("net selling price increases", "PRICE_REALIZATION")
        graph.concept("organic sales growth", "REVENUE")
        graph.concept("profit margin levels", "OPERATING_MARGIN")
    elif candidate_id == "1fffa5a44fb28f564942":
        graph.concept("Gross profit margin", "GROSS_MARGIN")
        graph.concept("operating profit", "OPERATING_INCOME", occurrence=0)
        graph.concept("operating profit margin", "OPERATING_MARGIN")
    elif candidate_id == "bdc14b1988d644ca92d9":
        graph.concept("net sales", "REVENUE")
        graph.concept("operating profit", "OPERATING_INCOME")
    elif candidate_id == "eed948beee41e2f2ce8d":
        graph.concept("shares outstanding", "SHARES")


def _graph_for(candidate_id: str, text: str) -> GraphBuilder:
    graph = GraphBuilder(text)
    if candidate_id == "94c4776ebf0363e2d330":
        _annotate_activity_levels(graph)
    elif candidate_id == "1442d5850c637422827f":
        _annotate_cash_fair_value_table(graph)
    elif candidate_id == "4df9d466fc4d6509e6f2":
        _annotate_balance_sheet(graph)
    elif candidate_id == "ba0d5c43220b06c8a1c4":
        _annotate_capex_table(graph)
    elif candidate_id == "877303c31f5e3a99c40e":
        _annotate_acquisition_volume(graph)
    elif candidate_id == "c605c2a9f70de0a72f6e":
        _annotate_sales_driver_table(graph)
    if candidate_id in CONCEPT_ONLY_IDS:
        _annotate_concept_only(candidate_id, graph)
    return graph


def _decision(candidate_id: str, source_kind: str) -> str:
    if source_kind == "INDUSTRY_DATA":
        return "PREDECLARED_INDUSTRY_NEGATIVE_CONTROL"
    if candidate_id in SUPPORTED_FACT_IDS:
        return "SUPPORTED_FACT_GRAPH"
    if candidate_id in UNSUPPORTED_METRIC_IDS:
        return "UNSUPPORTED_METRIC_ABSTAIN"
    if candidate_id in CONCEPT_ONLY_IDS:
        return "SUPPORTED_CONCEPT_WITHOUT_ELIGIBLE_QUANTITY"
    if candidate_id in TABLE_IDS:
        return "TABLE_ROUTE_WITHOUT_SUPPORTED_TARGET_FACT"
    return "REVIEWED_NO_SUPPORTED_ISSUER_FACT"


def _source_kind(row: dict[str, str]) -> str:
    candidate_id = row["candidate_id"]
    source_kind = row["source_kind"]
    if candidate_id in NOTE_IDS:
        if source_kind == "10-K":
            return "10-K_NOTE"
        if source_kind == "10-Q":
            return "10-Q_NOTE"
    return source_kind


def _document_period(row: dict[str, str]) -> str:
    # The canonical selection artifact intentionally retained the adapter's
    # release-quarter fallback.  Gold provenance separates that PIT release
    # date from the economic period stated by each filing/earnings supplement.
    periods = {
        ("AAL", "10-K"): "2025",
        ("AAL", "10-Q"): "2026Q2",
        ("AAME", "10-K"): "2024",
        ("AAME", "10-Q"): "2025Q3",
        ("AAMI", "10-K"): "2025",
        ("AAMI", "10-Q"): "2026Q2",
        ("CL", "IR"): "2026Q2",
        ("PRU", "IR"): "2026Q2",
        ("SPG", "IR"): "2026Q2",
        # DUK's selected source is an August 2026 financing document rather
        # than a quarterly earnings supplement.
        ("DUK", "IR"): "2026Q3",
    }
    return periods.get((row["entity"], row["source_kind"]), row["document_period"])


def build_annotations(
    candidates: Iterable[dict[str, str]],
) -> list[dict[str, object]]:
    candidate_rows = list(candidates)
    ids = [row["candidate_id"] for row in candidate_rows]
    observed = set(ids)
    if (
        len(ids) != 120
        or len(observed) != len(ids)
        or observed != EXPECTED_SELECTION_IDS
    ):
        missing = sorted(EXPECTED_SELECTION_IDS - observed)
        extra = sorted(observed - EXPECTED_SELECTION_IDS)
        raise ValueError(
            "selection coverage drift: "
            f"rows={len(ids)} unique={len(observed)} missing={missing} extra={extra}"
        )

    output: list[dict[str, object]] = []
    for row in candidate_rows:
        candidate_id = row["candidate_id"]
        graph = _graph_for(candidate_id, row["text"])
        route = (
            "TABLE_DSL"
            if candidate_id in TABLE_IDS
            else "TEXT_IE"
            if candidate_id in SUPPORTED_FACT_IDS
            else "NO_FACT"
        )
        output.append(
            {
                "example_id": candidate_id,
                "entity": row["entity"],
                "holdout_axis": row["axis"],
                "source_kind": _source_kind(row),
                "source_sha256": row["source_sha256"],
                "available_at": row["available_at"],
                "document_period": _document_period(row),
                "text": row["text"],
                "gold_route": route,
                "quantities": graph.quantities,
                "concepts": graph.concepts,
                "candidate_edges": graph.candidate_edges,
                "binding_edges": graph.binding_edges,
                "role_edges": graph.role_edges,
                "expected_frames": graph.frames,
                "annotation_source": ANNOTATION_SOURCE,
                "review_decision": _decision(candidate_id, row["source_kind"]),
                "annotation_note": (
                    "Frozen supported semantic ontology only; dates, page numbers, "
                    "durations, generic disclaimers, third-party KPIs and unsupported "
                    "metrics do not become issuer facts."
                ),
            }
        )
    return output


def write_annotations(rows: Iterable[dict[str, object]], path: Path) -> None:
    items = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in items
        ),
        encoding="utf-8",
    )


def main() -> int:
    if sha256_file(CANDIDATES) != SELECTION_SHA256:
        raise ValueError("frozen native A/B/C candidate selection hash changed")
    with CANDIDATES.open(encoding="utf-8-sig", newline="") as stream:
        rows = build_annotations(csv.DictReader(stream))
    write_annotations(rows, ANNOTATIONS)
    print(f"ANNOTATED={len(rows)}")
    print(f"EXPECTED_FRAMES={sum(len(row['expected_frames']) for row in rows)}")
    print(f"TABLE_BLOCKS={sum(row['gold_route'] == 'TABLE_DSL' for row in rows)}")
    print(f"ANNOTATION_SHA256={sha256_file(ANNOTATIONS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
