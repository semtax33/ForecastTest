from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from equity_platform.documents import DocumentMetadata, adapt_html_document
from equity_platform.experiments import ExperimentRunner, ExperimentSpec
from equity_platform.governance import PolicyPurpose, evaluate_authority
from equity_platform.ir import (
    AuthorityLevel,
    CausalEdgeIR,
    Direction,
    EconomicNodeIR,
    EconomicGraphIR,
    EvidenceClaimIR,
    EvidenceStatus,
    FactOrigin,
    IdentificationStatus,
    LagSpec,
    MagnitudeSpec,
    RelationType,
    ResearchGraphIR,
    RoicKind,
    ScenarioClass,
    ScenarioIR,
    SensorIR,
    SensorTransform,
    ExpectationsGapIR,
    IdentificationState,
    ExtractionMethod,
    SourceRef,
    SourceSpan,
    ClaimStatus,
    ClaimType,
)
from equity_platform.parsing import (
    DslCompileError,
    compile_rule_file,
    compile_rules,
    execute_rule,
    parse_numeric_token,
)
from equity_platform.valuation import DcfAssumptions as LegacyDcfAssumptions
from equity_platform.valuation import enterprise_value as legacy_enterprise_value
from equity_platform.valuation_kernel import DcfAssumptions as KernelDcfAssumptions
from equity_platform.valuation_kernel import enterprise_value as kernel_enterprise_value
from equity_platform.sectors.industrials.platform import build_industrials_bls_sensor_ir


ROOT = Path(__file__).resolve().parents[1]
PAC_RULES = ROOT / "configs/parser_rules/industrials/pac.arc"
CAT_RULES = ROOT / "configs/parser_rules/industrials/cat.arc"


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_parser_dsl_compiles_to_typed_rule_ir() -> None:
    rules = compile_rule_file(PAC_RULES)
    assert [rule.rule_id for rule in rules] == [
        "airport.monthly_terminal_passengers",
        "airport.ifric12_concession_capex",
    ]
    assert len({rule.source_sha256 for rule in rules}) == 1
    assert len(rules[0].source_sha256) == 64
    cat_rules = compile_rule_file(CAT_RULES)
    assert len(cat_rules) == 7
    assert {rule.selector.value for rule in cat_rules} == {"TEXT"}


def test_parser_dsl_rejects_arbitrary_operations_and_location_selectors() -> None:
    for forbidden in ("python", "network", "table_index"):
        text = f'''rule "bad" {{
          version = 1
          source = "SEC_6K"
          document = "OPERATING_RELEASE"
          selector = "TABLE"
          period_mode = "REPORT_PERIOD"
          combine = "UNIQUE"
          metric = "X"
          scope = "CONSOLIDATED"
          unit = "USD"
          {forbidden} = "anything"
        }}'''
        with pytest.raises(DslCompileError, match="forbidden DSL key"):
            compile_rules(text)


def test_table_rule_uses_semantics_not_ytd_or_table_position(tmp_path: Path) -> None:
    html = """
    <html><body>
      <h1>Issuer Reports a Passenger Traffic Increase in July 2025 of 3%</h1>
      <table><tr><td>noise</td></tr></table>
      <table>
        <tr><th>Airport</th><th>Jul-25</th><th>Jan - Jul 25</th></tr>
        <tr><td>Total</td><td>900.0</td><td>6300.0</td></tr>
      </table>
      <table>
        <tr><th>Airport</th><th>Jul-25</th><th>Jan - Jul 25</th></tr>
        <tr><td>Total</td><td>600.0</td><td>4200.0</td></tr>
      </table>
      <table>
        <tr><th>Airport</th><th>Jul-25</th><th>Jan - Jul 25</th></tr>
        <tr><td>Total</td><td>1500.0</td><td>10500.0</td></tr>
      </table>
    </body></html>
    """
    path = tmp_path / "release.htm"
    path.write_text(html, encoding="utf-8")
    document = adapt_html_document(
        path=path,
        metadata=DocumentMetadata(
            entity="PAC",
            source_kind="SEC_6K",
            document_kind="OPERATING_RELEASE",
            available_at="2025-08-05",
        ),
        expected_sha256=_sha(path),
        source_uri="https://example.test/release",
        include_tables=True,
        include_inline_facts=False,
    )
    rule = compile_rule_file(PAC_RULES)[0]
    result = execute_rule(document, rule)
    assert result.status == "EMITTED"
    assert result.fact is not None
    assert result.fact.value == 1500.0
    assert result.fact.period == "2025-07"
    assert result.fact.lineage.match_trace["resolved_table_indices"] == [1, 2, 3]
    assert result.fact.lineage.capture_trace["candidate_values"] == [900.0, 600.0, 1500.0]


def test_text_rule_emits_typed_fact_with_source_span(tmp_path: Path) -> None:
    html = """
    <html><body>The dollar amount of backlog believed to be firm was approximately
    $14.2 billion at December 31, 2025 and $13.7 billion at December 31, 2024</body></html>
    """
    path = tmp_path / "cat-10k.htm"
    path.write_text(html, encoding="utf-8")
    document = adapt_html_document(
        path=path,
        metadata=DocumentMetadata(
            entity="CAT",
            source_kind="SEC_10K",
            document_kind="ANNUAL_REPORT",
            available_at="2026-02-10",
            report_period="2025",
        ),
        expected_sha256=_sha(path),
        source_uri="https://example.test/cat-10k",
        include_tables=False,
        include_inline_facts=False,
    )
    result = execute_rule(document, compile_rule_file(CAT_RULES)[0])
    assert result.status == "EMITTED"
    assert result.fact is not None
    assert result.fact.value == 14.2
    assert result.fact.period == "2025"
    match = result.fact.lineage.match_trace["matches"][0]
    assert match["character_end"] > match["character_start"]
    assert "$14.2 billion" in match["source_excerpt"]


def test_authority_and_ir_types_fail_closed() -> None:
    diagnostic = evaluate_authority(
        actual=AuthorityLevel.RESEARCH_DIAGNOSTIC,
        purpose=PolicyPurpose.TERMINAL,
    )
    assert not diagnostic.allowed
    assert diagnostic.required is AuthorityLevel.TERMINAL_INPUT

    common = dict(
        node_id="x.roic",
        entity="X",
        concept="ROIC",
        scope="CONSOLIDATED",
        period="FY2026",
        unit="PCT",
        value=12.0,
        origin=FactOrigin.FORECAST,
        relation=RelationType.STATISTICAL,
        evidence=EvidenceStatus.DIAGNOSTIC,
        authority=AuthorityLevel.RESEARCH_DIAGNOSTIC,
    )
    with pytest.raises(ValueError, match="explicit RoicKind"):
        EconomicNodeIR(**common)
    assert EconomicNodeIR(**common, roic_kind=RoicKind.FORWARD).roic_kind is RoicKind.FORWARD


def test_evidence_cannot_jump_to_valuation_and_causal_lag_is_ordered() -> None:
    source = SourceRef(
        source_type="SEC_10Q",
        uri="https://example.test/10q",
        local_path="bronze/example.htm",
        sha256="0" * 64,
        available_at="2026-05-01",
    )
    with pytest.raises(ValueError, match="cannot directly receive valuation"):
        EvidenceClaimIR(
            claim_id="claim-1",
            entity="X",
            scope="SEGMENT",
            period="2026Q1",
            claim_type=ClaimType.CAUSAL_MECHANISM,
            subject="PRODUCTIVITY",
            predicate="IMPROVING",
            direction="POSITIVE",
            source=source,
            source_span=SourceSpan("MD&A", 1, 10, "improved"),
            status=ClaimStatus.VERIFIED,
            authority=AuthorityLevel.VALUATION_INPUT,
        )

    with pytest.raises(ValueError, match="explicit verifier"):
        EvidenceClaimIR(
            claim_id="claim-llm",
            entity="X",
            scope="CONSOLIDATED",
            period="2026Q1",
            claim_type=ClaimType.GUIDANCE,
            subject="REVENUE",
            predicate="INCREASES",
            direction="POSITIVE",
            source=source,
            source_span=SourceSpan("GUIDANCE", 1, 10, "increases"),
            status=ClaimStatus.VERIFIED,
            authority=AuthorityLevel.RESEARCH_EVIDENCE,
            extraction_method=ExtractionMethod.LLM,
        )
    with pytest.raises(ValueError, match="ordered"):
        CausalEdgeIR(
            edge_id="edge-1",
            cause="WAGES_t",
            effect="MARGIN_t1",
            direction=Direction.NEGATIVE,
            mechanism="UNIT_LABOR_COST",
            path=("C.LABOR",),
            lag=LagSpec(2, 1, 3, "QUARTER"),
            magnitude=MagnitudeSpec("PASS_THROUGH", None, None, None),
            regime="FIXED_PRICE",
            confounders=("MIX",),
            identification=IdentificationStatus.HYPOTHESIZED,
            supporting_evidence=(),
            contradicting_evidence=(),
            falsifiers=(),
            authority=AuthorityLevel.RESEARCH_DIAGNOSTIC,
        )


def test_legacy_dcf_facade_is_a_golden_adapter_over_shared_kernel() -> None:
    legacy = LegacyDcfAssumptions(
        base_revenue_usd=100.0,
        near_term_growth_pct=4.0,
        operating_margin_pct=15.0,
        tax_rate_pct=21.0,
        roic_pct=12.0,
        wacc_pct=9.0,
        terminal_growth_pct=2.0,
    )
    legacy_rows, legacy_value = legacy_enterprise_value(legacy)
    kernel = KernelDcfAssumptions(
        ticker="GOLDEN",
        scenario="GOLDEN",
        base_revenue_usd=100.0,
        near_term_growth_pct=4.0,
        terminal_growth_pct=2.0,
        initial_margin_pct=15.0,
        terminal_margin_pct=15.0,
        tax_rate_pct=21.0,
        initial_roic_pct=12.0,
        terminal_roic_pct=12.0,
        wacc_pct=9.0,
    )
    kernel_rows, kernel_summary = kernel_enterprise_value(kernel)

    assert legacy_value == kernel_summary["enterprise_value_usd"]
    assert legacy_value == 146.14593650528587
    assert legacy_rows[0]["reinvestment_rate"] == 4.0 / 12.0
    assert legacy_rows[-1]["terminal_reinvestment_rate"] == 2.0 / 12.0
    assert legacy_rows[0]["revenue_usd"] == kernel_rows.iloc[0]["revenue_usd"]
    assert "terminal_value_usd" not in legacy_rows[0]
    assert "terminal_value_usd" in legacy_rows[-1]


def test_experiment_runner_validates_identity_and_records_stage_lineage(
    tmp_path: Path,
) -> None:
    config = tmp_path / "experiment.toml"
    config.write_text(
        'experiment_id = "test.example"\nversion = "V1"\n', encoding="utf-8"
    )
    runner = ExperimentRunner(
        root=tmp_path,
        spec=ExperimentSpec(
            experiment_id="test.example",
            version="V1",
            config_path=Path("experiment.toml"),
            output_path=Path("output/test"),
        ),
    )
    result = runner.stage(
        "facts",
        lambda: {"facts": pytest.importorskip("pandas").DataFrame([{"x": 1}])},
        consumes=("raw_document",),
    )
    assert result["facts"].iloc[0]["x"] == 1
    record = runner.ledger().iloc[0]
    assert record["experiment_id"] == "test.example"
    assert record["consumes"] == "raw_document"
    assert record["produces"] == "facts"

    with pytest.raises(ValueError, match="Experiment id mismatch"):
        ExperimentRunner(
            root=tmp_path,
            spec=ExperimentSpec(
                experiment_id="wrong",
                version="V1",
                config_path=Path("experiment.toml"),
                output_path=Path("output/test"),
            ),
        )


@pytest.mark.parametrize(
    ("token", "scale", "expected"),
    [
        ("$1,234.5", 0, 1234.5),
        ("(42)", 0, -42.0),
        ("12.5%", 0, 12.5),
        ("3.2", 6, 3_200_000.0),
        ("NM", 0, None),
        ("—", 0, None),
    ],
)
def test_numeric_token_parser_is_shared_and_deterministic(
    token: str, scale: int, expected: float | None
) -> None:
    assert parse_numeric_token(token, scale=scale) == expected


def test_sensor_scenario_and_graph_ir_keep_authority_and_references_explicit() -> None:
    sensors = build_industrials_bls_sensor_ir()
    assert sensors
    assert {sensor.role.value for sensor in sensors} == {"P", "C"}
    assert all(isinstance(sensor, SensorIR) for sensor in sensors)
    assert all(sensor.transform is SensorTransform.YOY_PCT for sensor in sensors)

    nodes = (
        EconomicNodeIR(
            node_id="model.ev",
            entity="X",
            concept="ENTERPRISE_VALUE",
            scope="CONSOLIDATED",
            period="2026-09-04",
            unit="USD",
            value=120.0,
            origin=FactOrigin.FORECAST,
            relation=RelationType.STRUCTURAL,
            evidence=EvidenceStatus.DIAGNOSTIC,
            authority=AuthorityLevel.RESEARCH_DIAGNOSTIC,
        ),
        EconomicNodeIR(
            node_id="market.ev",
            entity="X",
            concept="ENTERPRISE_VALUE",
            scope="CONSOLIDATED",
            period="2026-09-04",
            unit="USD",
            value=100.0,
            origin=FactOrigin.MARKET_IMPLIED,
            relation=RelationType.MARKET_IMPLIED,
            evidence=EvidenceStatus.HISTORICAL,
            authority=AuthorityLevel.RESEARCH_EVIDENCE,
        ),
    )
    graph = ResearchGraphIR(
        facts=(),
        sensors=sensors,
        evidence_claims=(),
        causal_edges=(),
        economic_graph=EconomicGraphIR(nodes=nodes, edges=()),
        scenarios=(
            ScenarioIR(
                scenario_id="probable.base",
                scenario_class=ScenarioClass.PROBABLE,
                assumption_nodes=("model.ev",),
                evidence_claims=(),
                probability_weight=0.5,
                authority=AuthorityLevel.RESEARCH_DIAGNOSTIC,
            ),
        ),
        expectations_gaps=(
            ExpectationsGapIR(
                gap_id="x.ev.gap",
                model_node="model.ev",
                market_implied_node="market.ev",
                metric="EV_GAP_PCT",
                value=20.0,
                identification=IdentificationState.CONDITIONAL,
                authority=AuthorityLevel.RESEARCH_DIAGNOSTIC,
            ),
        ),
    )
    graph.validate()
    with pytest.raises(ValueError, match="cannot carry a value"):
        ExpectationsGapIR(
            gap_id="bad",
            model_node="model.ev",
            market_implied_node="market.ev",
            metric="EV_GAP_PCT",
            value=20.0,
            identification=IdentificationState.UNIDENTIFIABLE,
            authority=AuthorityLevel.RESEARCH_DIAGNOSTIC,
        )


def test_gd_entrypoint_is_thin_and_valuation_no_longer_depends_on_hii() -> None:
    entrypoint = (ROOT / "scripts/industrials/valuation_v6_gd.py").read_text(
        encoding="utf-8"
    )
    valuation = (
        ROOT
        / "equity_platform/sectors/industrials/aerospace_defense/gd_v6/valuation.py"
    ).read_text(encoding="utf-8")
    assert len(entrypoint.splitlines()) <= 5
    assert "gd_v6.experiment import main" in entrypoint
    assert "hii_v52" not in valuation
    assert "equity_platform.valuation_kernel" in valuation
