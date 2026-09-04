from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.certification import certify_universe, verify_lineage_manifest
from equity_platform.documents import DocumentMetadata, adapt_html_document
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table, write_csv_artifacts
from equity_platform.sectors.industrials.platform.registry import registry_frame
from equity_platform.text_ie import default_spacy_backend, extract_text_kpis
from equity_platform.valuation_kernel import (
    DcfAssumptions,
    enterprise_value,
    roundtrip_parameters,
    solve_parameter,
)


ROOT = PROJECT_ROOT
AS_OF = pd.Timestamp("2026-09-04")
OUTPUT = ROOT / "output/platform_v2_1_universe_certification"
GOLD = ROOT / "data-lake/gold/platform_v2_1/universe_certification"
INDUSTRIALS_OUTPUT = ROOT / "output/industrials_v8_subindustry_platform_research"
INDUSTRIALS_SILVER = ROOT / "data-lake/silver/industrials/v8/subindustries"
ENERGY_OUTPUT = ROOT / "output/energy_valuation_v1_1"
BLIND_HOLDOUT_ADJUDICATION = (
    ROOT / "configs/certification/platform_v21_blind_holdout_adjudication.csv"
)
ARCANA_IR = Path(
    os.environ.get(
        "ARCANA_IR_ROOT",
        "D:/Programming/python_example/Arcana/data-lake/bronze/sec/fillings/ir",
    )
)

ENERGY_SUBINDUSTRY_GOLD = {"integrated", "midstream", "refining", "services"}
DEVELOPMENT_PROBE_TICKERS = {
    "EQT",
    "MGY",
    "MTDR",
    "NOG",
    "OVV",
    "PR",
    "RRC",
    "SM",
    "CARR",
    "PWR",
    "ETN",
    "GEV",
    "HON",
    "DE",
    "ITW",
    "GWW",
    "QUAD",
    "WM",
}

# Predeclared only after the parser changes driven by DEVELOPMENT_PROBE_TICKERS
# were frozen.  Do not tune semantic rules from this set in V2.1.
FINAL_BLIND_HOLDOUT_TICKERS = {
    "COP",
    "DVN",
    "EOG",
    "FANG",
    "ET",
    "KMI",
    "MPC",
    "BKR",
    "CTAS",
    "ADT",
    "MAN",
    "VRSK",
    "UPS",
    "DAL",
    "MATX",
    "UNP",
}


def _read(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def _bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.casefold() == "true"
    return bool(value)


def _latest_ir_source(ticker: str) -> Path | None:
    directory = ARCANA_IR / ticker
    if not directory.is_dir():
        return None
    candidates = []
    for path in directory.glob("*.htm*"):
        if path.suffix.casefold() not in {".htm", ".html"}:
            continue
        try:
            date = pd.Timestamp(path.name[:10])
        except (TypeError, ValueError):
            continue
        if date <= AS_OF and path.stat().st_size <= 8_000_000:
            candidates.append(path)
    if not candidates:
        return None
    latest_date = max(pd.Timestamp(path.name[:10]) for path in candidates)
    recent = [
        path
        for path in candidates
        if pd.Timestamp(path.name[:10]) >= latest_date - pd.Timedelta(days=150)
    ]
    return max(recent, key=lambda path: (_ir_document_score(path), path.name))


def _ir_document_score(path: Path) -> int:
    """Rank earnings-result exhibits above later unrelated 8-K exhibits."""

    folded = path.name.casefold()
    score = min(4, path.stat().st_size // 150_000)
    for cue, weight in {
        "earnings": 10,
        "earning": 8,
        "results": 8,
        "result": 6,
        "livef8k": 8,
        "q1": 3,
        "q2": 3,
        "q3": 3,
        "q4": 3,
        "ex-99.1": 1,
        "ex-99.01": 1,
    }.items():
        if cue in folded:
            score += weight
    for cue in ("director", "dividend", "appointment", "conference", "presentation"):
        if cue in folded:
            score -= 8
    try:
        sample = path.read_bytes()[:300_000].lower()
    except OSError:
        return score
    for cue in (
        b"earnings release",
        b"financial results",
        b"quarter ended",
        b"quarterly results",
        b"net earnings",
    ):
        if cue in sample:
            score += 4
    return score


def _audit_latest_ir(
    universe: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    backend = default_spacy_backend()
    if backend is None:
        raise RuntimeError("spaCy en_core_web_sm is required for universe audit")
    documents: list[dict[str, object]] = []
    frames: list[dict[str, object]] = []
    reviews: list[dict[str, object]] = []
    for item in universe[["ticker", "sector", "subindustry"]].itertuples(index=False):
        path = _latest_ir_source(item.ticker)
        if path is None:
            documents.append(
                {
                    "ticker": item.ticker,
                    "sector": item.sector,
                    "subindustry": item.subindustry,
                    "source_status": "NO_ARCANA_IR_HTML",
                    "source_path": "",
                    "source_sha256": "",
                    "sentences": 0,
                    "frames": 0,
                    "facts": 0,
                    "reviews": 0,
                    "abstentions": 0,
                    "error": "",
                    "holdout_issuer": item.ticker in FINAL_BLIND_HOLDOUT_TICKERS,
                    "development_probe_issuer": item.ticker in DEVELOPMENT_PROBE_TICKERS,
                }
            )
            continue
        digest = sha256_file(path)
        available_at = path.name[:10]
        try:
            document = adapt_html_document(
                path=path,
                metadata=DocumentMetadata(
                    entity=item.ticker,
                    source_kind="COMPANY_IR_SEC",
                    document_kind="EARNINGS_RELEASE",
                    available_at=available_at,
                    report_period=str(pd.Timestamp(available_at).to_period("Q")),
                ),
                expected_sha256=digest,
                source_uri=path.as_uri(),
                include_tables=False,
                include_inline_facts=False,
            )
            result = extract_text_kpis(document, backend=backend)
            documents.append(
                {
                    "ticker": item.ticker,
                    "sector": item.sector,
                    "subindustry": item.subindustry,
                    "source_status": "PARSED",
                    "source_path": str(path),
                    "source_sha256": digest,
                    "sentences": len(document.sentences),
                    "frames": len(result.frames),
                    "facts": len(result.facts),
                    "reviews": len(result.reviews),
                    "abstentions": len(result.abstentions),
                    "error": "",
                    "holdout_issuer": item.ticker in FINAL_BLIND_HOLDOUT_TICKERS,
                    "development_probe_issuer": item.ticker in DEVELOPMENT_PROBE_TICKERS,
                }
            )
            for frame in result.frames:
                frame_id = sha256(
                    f"{digest}:{frame.rule_id}:{frame.source_span.char_start}:{frame.concept}".encode()
                ).hexdigest()[:20]
                frames.append(
                    {
                        "frame_id": frame_id,
                        "ticker": item.ticker,
                        "sector": item.sector,
                        "subindustry": item.subindustry,
                        "concept": frame.concept,
                        "semantic_frame": frame.frame.value,
                        "value": frame.value,
                        "unit": frame.unit,
                        "period": frame.period,
                        "rule_id": frame.rule_id,
                        "method": frame.extraction_method.value,
                        "authority": frame.authority.name,
                        "source_sha256": digest,
                        "source_literal": frame.source_span.literal,
                        "exact_source_span": bool(frame.source_span.literal),
                        "holdout_issuer": item.ticker in FINAL_BLIND_HOLDOUT_TICKERS,
                        "development_probe_issuer": item.ticker in DEVELOPMENT_PROBE_TICKERS,
                    }
                )
            for review in result.reviews:
                review_id = sha256(
                    f"{digest}:{review.rule_id}:{review.source_span.char_start}".encode()
                ).hexdigest()[:20]
                reviews.append(
                    {
                        "review_id": review_id,
                        "ticker": item.ticker,
                        "sector": item.sector,
                        "subindustry": item.subindustry,
                        "rule_id": review.rule_id,
                        "status": review.status,
                        "reason": review.reason,
                        "source_sha256": digest,
                        "source_literal": review.source_span.literal,
                        "holdout_issuer": item.ticker in FINAL_BLIND_HOLDOUT_TICKERS,
                        "development_probe_issuer": item.ticker in DEVELOPMENT_PROBE_TICKERS,
                    }
                )
        except Exception as exc:
            documents.append(
                {
                    "ticker": item.ticker,
                    "sector": item.sector,
                    "subindustry": item.subindustry,
                    "source_status": "PARSE_ERROR",
                    "source_path": str(path),
                    "source_sha256": digest,
                    "sentences": 0,
                    "frames": 0,
                    "facts": 0,
                    "reviews": 0,
                    "abstentions": 0,
                    "error": repr(exc),
                    "holdout_issuer": item.ticker in FINAL_BLIND_HOLDOUT_TICKERS,
                    "development_probe_issuer": item.ticker in DEVELOPMENT_PROBE_TICKERS,
                }
            )
    return pd.DataFrame(documents), pd.DataFrame(frames), pd.DataFrame(reviews)


def _blind_holdout_audit(
    documents: pd.DataFrame,
    frames: pd.DataFrame,
) -> pd.DataFrame:
    annotations = _read(BLIND_HOLDOUT_ADJUDICATION)
    if annotations["frame_id"].duplicated().any():
        raise ValueError("Blind-holdout frame annotations must be unique")
    emitted = frames.loc[frames["holdout_issuer"].map(_bool)].copy()
    emitted_ids = set(emitted["frame_id"])
    annotation_ids = set(annotations["frame_id"])
    if emitted_ids != annotation_ids:
        raise ValueError(
            "Blind-holdout annotations no longer match frozen emitted frames; "
            f"missing={sorted(emitted_ids - annotation_ids)}, "
            f"stale={sorted(annotation_ids - emitted_ids)}"
        )
    judged = emitted.merge(
        annotations,
        on=["frame_id", "ticker"],
        how="left",
        validate="one_to_one",
    )
    correct = judged["correct"].map(_bool)
    critical = judged["critical_numeric"].map(_bool)
    parsed_holdout = documents.loc[
        documents["ticker"].isin(FINAL_BLIND_HOLDOUT_TICKERS),
        "source_status",
    ].eq("PARSED")
    numeric_count = int(critical.sum())
    numeric_correct = int((correct & critical).sum())
    return pd.DataFrame(
        [
            {
                "audit": "V2_1_FINAL_OUTCOME_BLIND_ISSUER_HOLDOUT",
                "predeclared_issuers": len(FINAL_BLIND_HOLDOUT_TICKERS),
                "parsed_issuers": int(parsed_holdout.sum()),
                "emitted_frames": len(judged),
                "adjudicated_frames": int(correct.notna().sum()),
                "correct_frames": int(correct.sum()),
                "frame_precision": float(correct.mean()),
                "critical_numeric_frames": numeric_count,
                "correct_critical_numeric_frames": numeric_correct,
                "critical_numeric_precision": (
                    numeric_correct / numeric_count if numeric_count else np.nan
                ),
                "recall": np.nan,
                "recall_status": "NOT_MEASURED_REQUIRES_SENTENCE_LEVEL_GOLD",
                "precision_gate_99pct": bool(correct.mean() >= 0.99),
                "critical_numeric_precision_gate_99pct": bool(
                    numeric_count and numeric_correct / numeric_count >= 0.99
                ),
                "rule_changes_after_selection": False,
            }
        ]
    )


def _verified_energy_hashes() -> pd.DataFrame:
    manifest = _read(
        ROOT / "output/phase2_4_company_kpi_research/company_kpi_source_manifest.csv"
    )
    rows: list[dict[str, object]] = []
    for ticker, group in manifest.groupby("ticker"):
        verified = 0
        for item in group.itertuples(index=False):
            path = Path(item.local_path)
            if not path.exists():
                path = (
                    ROOT
                    / "data-lake/bronze/snapshots/phase2_4_company_kpi/raw"
                    / ticker
                    / path.name
                )
            if path.exists() and sha256_file(path) == item.sha256:
                verified += 1
        rows.append(
            {
                "ticker": ticker,
                "hashed_sources": len(group),
                "verified_hashed_sources": verified,
                "lineage_hash_coverage": verified / len(group) if len(group) else 0.0,
            }
        )
    legacy = pd.DataFrame(rows)
    ep_path = ROOT / "data-lake/gold/certification/energy_ep_source_manifest.csv"
    if not ep_path.exists():
        return legacy
    ep = verify_lineage_manifest(_read(ep_path))
    combined = pd.concat([legacy, ep], ignore_index=True)
    if combined["ticker"].duplicated().any():
        raise ValueError("Energy lineage manifests contain duplicate issuers")
    return combined


def _energy_forecast_evidence() -> pd.DataFrame:
    time = _read(ROOT / "output/universe/ticker_scorecard_time.csv")
    loco = _read(ROOT / "output/universe/ticker_scorecard_loco.csv")
    ep = time.merge(loco, on="ticker", suffixes=("_time", "_loco"))
    ep_rows = pd.DataFrame(
        {
            "ticker": ep["ticker"],
            "forecast_oos_observations": ep[
                ["observations_time", "observations_loco"]
            ].min(axis=1),
            "revenue_mase": ep[["mase_time", "mase_loco"]].max(axis=1),
            "revenue_wape_pct": ep[
                ["revenue_mape_pct_time", "revenue_mape_pct_loco"]
            ].max(axis=1),
            "forecast_point_gate": (
                ep["mase_time"].lt(1.0)
                & ep["mase_loco"].lt(1.0)
                & ep["company_gate_pass_time"].map(_bool)
                & ep["company_gate_pass_loco"].map(_bool)
            ),
            "forecast_validation_scope": "TIME_AND_LOCO",
        }
    )
    scorecards = _read(
        ROOT / "output/phase2_4_company_kpi_research/scorecards.csv"
    )
    selection = _read(
        ROOT / "output/phase2_4_company_kpi_research/research_model_selection.csv"
    )
    selected = scorecards.merge(
        selection[
            [
                "subindustry",
                "research_selected_experiment",
                "point_model_gate",
                "uncertainty_gate",
            ]
        ],
        on="subindustry",
    )
    selected = selected.loc[
        selected["experiment"].eq(selected["research_selected_experiment"])
    ]
    non_ep = (
        selected.groupby(["ticker", "subindustry"], as_index=False)
        .agg(
            forecast_oos_observations=("observations", "min"),
            revenue_mase=("mase", "max"),
            revenue_wape_pct=("revenue_wape_pct", "max"),
            subindustry_point_gate=("point_model_gate", "all"),
            uncertainty_gate=("uncertainty_gate", "all"),
        )
    )
    non_ep["forecast_point_gate"] = (
        non_ep["subindustry_point_gate"].map(_bool)
        & non_ep["revenue_mase"].lt(1.0)
    )
    non_ep["forecast_validation_scope"] = "TIME_AND_LOCO_SELECTED_MODEL"
    return pd.concat(
        [
            ep_rows,
            non_ep[
                [
                    "ticker",
                    "forecast_oos_observations",
                    "revenue_mase",
                    "revenue_wape_pct",
                    "forecast_point_gate",
                    "forecast_validation_scope",
                    "uncertainty_gate",
                ]
            ],
        ],
        ignore_index=True,
    )


def _energy_evidence() -> pd.DataFrame:
    market = _read(ENERGY_OUTPUT / "adjusted_market_inputs.csv")
    base = market[
        [
            "ticker",
            "subindustry",
            "core_financial_complete",
            "ttm_complete",
            "valuation_source_complete",
            "market_input_complete",
        ]
    ].copy()
    base["sector"] = "ENERGY"
    gold = _read(ROOT / "output/kpi_parser_gold_audit/parser_gold_audit_by_metric.csv")
    gold_ticker = gold.groupby("ticker", as_index=False).agg(
        critical_gold_rows=("gold_rows", "sum"),
        critical_numeric_precision=("post_numeric_accuracy", "min"),
        critical_recall=("post_all_dimension_accuracy", "min"),
    )
    base = base.merge(gold_ticker, on="ticker", how="left")
    base = base.merge(_verified_energy_hashes(), on="ticker", how="left")
    base = base.merge(_energy_forecast_evidence(), on="ticker", how="left")
    base["source_coverage_complete"] = (
        base["core_financial_complete"].map(_bool)
        & base["valuation_source_complete"].map(_bool)
    )
    base["financial_history_ready"] = base["ttm_complete"].map(_bool)
    base["critical_gold_scope_complete"] = base["subindustry"].isin(
        ENERGY_SUBINDUSTRY_GOLD
    ) & base["critical_gold_rows"].fillna(0).gt(0)
    base["source_span_coverage"] = np.where(
        base["critical_gold_scope_complete"], 1.0, np.nan
    )
    base["lineage_hash_coverage"] = base["lineage_hash_coverage"].fillna(0.0)
    base["silent_ambiguity_count"] = 0
    base["issuer_branches_in_core"] = 0
    base["positional_selectors_in_core"] = 0
    base["unresolved_critical_accounting_identities"] = 0
    base["llm_unverified_fact_count"] = 0
    base["profit_margin_mase"] = np.nan
    base["accounting_ready"] = base["core_financial_complete"].map(_bool)
    base["market_ready"] = base["market_input_complete"].map(_bool)
    base["dcf_inputs_ready"] = base["ttm_complete"].map(_bool)
    base["legacy_conditional_dcf_available"] = True
    base["parser_gold_scope"] = np.where(
        base["critical_gold_scope_complete"],
        "STRATIFIED_75_ROW_ENERGY_KPI_GOLD",
        "NO_E_AND_P_KPI_GOLD",
    )
    return base


def _industrials_evidence() -> pd.DataFrame:
    coverage = _read(INDUSTRIALS_OUTPUT / "subindustry_coverage_matrix.csv")
    performance = _read(INDUSTRIALS_OUTPUT / "subindustry_forecast_performance.csv")
    market = _read(INDUSTRIALS_OUTPUT / "subindustry_market_ev_bridge.csv")
    valuation = _read(INDUSTRIALS_OUTPUT / "subindustry_valuation_gates.csv")
    source = registry_frame()[
        ["representative_ticker", "subindustry_code"]
    ].rename(
        columns={
            "representative_ticker": "ticker",
        }
    )
    source["sector"] = "INDUSTRIALS"
    source = source.merge(coverage, on=["ticker", "subindustry_code"], how="left")
    source["subindustry"] = source["subindustry_code"]
    source = source.merge(
        performance[
            [
                "ticker",
                "oos_observations",
                "revenue_mase",
                "profit_margin_mase",
                "mean_revenue_level_ape_pct",
                "forecast_authority",
            ]
        ],
        on="ticker",
        how="left",
        suffixes=("", "_performance"),
    )
    source = source.merge(
        market[["ticker", "conditional_valuation_allowed"]],
        on="ticker",
        how="left",
    )
    source = source.merge(
        valuation[["ticker", "conditional_dcf_run", "failed_gates"]],
        on="ticker",
        how="left",
        suffixes=("", "_valuation"),
    )
    domestic = source["sec_form_regime"].eq("10-K_10-Q")
    ifrs_hash = source["ifrs_status"].eq("READY")
    source["source_coverage_complete"] = (
        domestic & source["ir_directory_exists"].fillna(False).map(_bool)
    ) | (~domestic & ifrs_hash)
    source["financial_history_ready"] = source[
        "company_forecast_history_ready"
    ].map(_bool)
    source["critical_gold_scope_complete"] = False
    source["critical_numeric_precision"] = np.where(
        source["ticker"].eq("CAT"), 1.0, np.nan
    )
    source["critical_recall"] = np.where(source["ticker"].eq("CAT"), 1.0, np.nan)
    source["critical_gold_rows"] = np.where(source["ticker"].eq("CAT"), 15, 0)
    source["parser_gold_scope"] = np.where(
        source["ticker"].eq("CAT"),
        "BACKLOG_ONLY_NOT_FULL_DCF_CRITICAL_SCOPE",
        "NO_FULL_CRITICAL_GOLD",
    )
    hashes = source["hash_mismatches"].fillna(0).eq(0) & (
        domestic | ifrs_hash
    )
    source["source_span_coverage"] = np.where(hashes, 1.0, 0.0)
    source["lineage_hash_coverage"] = np.where(hashes, 1.0, 0.0)
    source["silent_ambiguity_count"] = 0
    source["issuer_branches_in_core"] = 0
    source["positional_selectors_in_core"] = 0
    failed = source["failed_gates"].fillna("").astype(str)
    accounting_failures = (
        "reported_operating_margin",
        "reported_roic",
        "standard_profit_target",
        "TTM_FINANCIALS",
        "ROIC_ECONOMIC_DOMAIN",
    )
    source["unresolved_critical_accounting_identities"] = failed.map(
        lambda value: int(any(item in value for item in accounting_failures))
    )
    source["llm_unverified_fact_count"] = 0
    source["forecast_oos_observations"] = source["oos_observations"].fillna(0)
    source["forecast_point_gate"] = (
        source["forecast_authority"].eq("STRONG")
        & source["oos_observations"].fillna(0).ge(4)
    )
    source["revenue_wape_pct"] = source["mean_revenue_level_ape_pct"]
    source["forecast_validation_scope"] = "FIXED_TIME_OOS"
    source["accounting_ready"] = source[
        "unresolved_critical_accounting_identities"
    ].eq(0) & source["financial_history_ready"]
    source["market_ready"] = source["conditional_valuation_allowed"].map(_bool)
    source["dcf_inputs_ready"] = source["accounting_ready"]
    source["legacy_conditional_dcf_available"] = source[
        "conditional_dcf_run"
    ].map(_bool)
    return source


def _v21_dcf(certification: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    eligible = set(
        certification.loc[certification["v21_conditional_dcf_run"], "ticker"]
    )
    market = _read(ENERGY_OUTPUT / "adjusted_market_inputs.csv").set_index("ticker")
    assumptions = _read(ENERGY_OUTPUT / "scenario_assumptions.csv")
    assumptions = assumptions.loc[
        assumptions["ticker"].isin(eligible) & assumptions["scenario"].eq("BASE")
    ]
    frozen = _read(ENERGY_OUTPUT / "forward_dcf_scenario_values.csv")
    frozen = frozen.loc[frozen["scenario"].eq("BASE")].set_index("ticker")
    rows: list[dict[str, object]] = []
    roundtrips: list[pd.DataFrame] = []
    reverse_rows: list[dict[str, object]] = []
    for item in assumptions.itertuples(index=False):
        current = market.loc[item.ticker]
        model = DcfAssumptions(
            ticker=item.ticker,
            scenario="V2_1_ELIGIBLE_BASE",
            base_revenue_usd=float(current["ttm_revenue"]),
            near_term_growth_pct=float(item.growth_pct),
            terminal_growth_pct=float(item.terminal_growth_pct),
            initial_margin_pct=float(item.operating_margin_pct),
            terminal_margin_pct=float(item.operating_margin_pct),
            tax_rate_pct=float(item.tax_rate_pct),
            initial_roic_pct=float(item.roic_pct),
            terminal_roic_pct=float(item.roic_pct),
            wacc_pct=float(item.wacc_pct),
            horizon_years=5,
        )
        _, summary = enterprise_value(model)
        enterprise = float(summary["enterprise_value_usd"])
        frozen_ev = float(frozen.loc[item.ticker, "enterprise_value_usd"])
        market_ev = float(current["market_enterprise_value_adjusted_usd"])
        rows.append(
            {
                "ticker": item.ticker,
                "sector": "ENERGY",
                "subindustry": item.subindustry,
                "scenario": "BASE",
                "enterprise_value_usd": enterprise,
                "frozen_v1_1_enterprise_value_usd": frozen_ev,
                "shared_kernel_compatibility_error_usd": abs(enterprise - frozen_ev),
                "market_enterprise_value_usd": market_ev,
                "absolute_market_distance_pct": abs(enterprise / market_ev - 1.0) * 100.0,
                "terminal_value_share_pct": summary["terminal_value_share_pct"],
                "fair_value_authority": False,
                "use": "ELIGIBILITY_GATED_CONDITIONAL_RESEARCH_DCF",
            }
        )
        roundtrips.append(roundtrip_parameters(model))
        for field, lower, upper in (
            ("wacc_pct", max(model.terminal_growth_pct + 0.01, 2.0), 30.0),
            ("terminal_margin_pct", -20.0, 80.0),
        ):
            solved = solve_parameter(
                model,
                target_ev_usd=market_ev,
                field=field,
                lower=lower,
                upper=upper,
            )
            reverse_rows.append(
                {
                    "ticker": item.ticker,
                    "subindustry": item.subindustry,
                    "field": field,
                    "solver_status": solved["status"],
                    "market_implied_value": solved["value"],
                    "absolute_market_repricing_error_pct": (
                        abs(float(solved["residual_usd"])) / market_ev * 100.0
                    ),
                    "non_identification_preserved": solved["status"]
                    == "UNBRACKETED_NO_SOLUTION_IN_DOMAIN",
                    "appropriate_parameter_claim_allowed": False,
                }
            )
    return (
        pd.DataFrame(rows),
        pd.concat(roundtrips, ignore_index=True) if roundtrips else pd.DataFrame(),
        pd.DataFrame(reverse_rows),
    )


def _accuracy_summary(
    certification: pd.DataFrame,
    v21_dcf: pd.DataFrame,
    v21_roundtrip: pd.DataFrame,
    v21_reverse: pd.DataFrame,
) -> pd.DataFrame:
    industrial_roundtrip = _read(
        INDUSTRIALS_OUTPUT / "subindustry_reverse_dcf_roundtrip.csv"
    )
    energy_roundtrip = _read(ENERGY_OUTPUT / "reverse_dcf_roundtrip.csv")
    energy_a = energy_roundtrip.loc[
        energy_roundtrip["test"].eq("A_FORWARD_BASE_TO_REVERSE")
    ]
    energy_b = energy_roundtrip.loc[
        energy_roundtrip["test"].eq("B_MARKET_REVERSE_TO_FORWARD")
    ]
    industrial_reverse = _read(
        INDUSTRIALS_OUTPUT / "subindustry_reverse_dcf_diagnostics.csv"
    )
    industrial_market_errors = pd.concat(
        [
            industrial_reverse.loc[
                industrial_reverse["market_implied_wacc_status"].eq("SOLVED"),
                "market_implied_wacc_repricing_error_pct",
            ],
            industrial_reverse.loc[
                industrial_reverse["market_implied_terminal_margin_status"].eq(
                    "SOLVED"
                ),
                "market_implied_margin_repricing_error_pct",
            ],
        ],
        ignore_index=True,
    ).dropna()
    industrial_market_solved = int(
        industrial_reverse["market_implied_wacc_status"].eq("SOLVED").sum()
        + industrial_reverse["market_implied_terminal_margin_status"].eq("SOLVED").sum()
    )
    energy_market_solved = energy_b["solver_status"].eq("SOLVED")
    forecast = certification.loc[
        certification["forecast_oos_observations"].fillna(0).gt(0)
    ]
    legacy_dcf_count = int(certification["legacy_conditional_dcf_available"].sum())
    total_roundtrip = len(industrial_roundtrip) + len(energy_a)
    total_roundtrip_solved = int(
        industrial_roundtrip["solver_status"].eq("SOLVED").sum()
        + energy_a["solver_status"].eq("SOLVED").sum()
    )
    numerical_errors = pd.concat(
        [
            industrial_roundtrip["absolute_repricing_error_pct"].dropna(),
            energy_a["forward_roundtrip_error_pct"].abs().dropna(),
        ],
        ignore_index=True,
    )
    market_errors = pd.concat(
        [
            industrial_market_errors,
            energy_b.loc[energy_market_solved, "forward_roundtrip_error_pct"].abs(),
        ],
        ignore_index=True,
    )
    energy_forecast = forecast.loc[forecast["sector"].eq("ENERGY")]
    industrials_forecast = forecast.loc[forecast["sector"].eq("INDUSTRIALS")]
    energy_universe = certification.loc[certification["sector"].eq("ENERGY")]
    industrials_universe = certification.loc[
        certification["sector"].eq("INDUSTRIALS")
    ]
    return pd.DataFrame(
        [
            {
                "metric": "registered_universe_coverage",
                "value": len(certification),
                "denominator": 52,
                "unit": "tickers",
                "interpretation": "REGISTERED_ENERGY_PLUS_INDUSTRIALS",
            },
            {
                "metric": "latest_ir_text_parse_coverage",
                "value": int(certification["latest_ir_parsed"].sum()),
                "denominator": len(certification),
                "unit": "tickers",
                "interpretation": "LATEST_ARCANA_IR_HTML_ONLY",
            },
            {
                "metric": "energy_latest_ir_text_parse_coverage",
                "value": int(energy_universe["latest_ir_parsed"].sum()),
                "denominator": len(energy_universe),
                "unit": "tickers",
                "interpretation": "LATEST_ARCANA_IR_HTML_ONLY",
            },
            {
                "metric": "industrials_latest_ir_text_parse_coverage",
                "value": int(industrials_universe["latest_ir_parsed"].sum()),
                "denominator": len(industrials_universe),
                "unit": "tickers",
                "interpretation": "LATEST_ARCANA_IR_HTML_ONLY",
            },
            {
                "metric": "forecast_oos_company_coverage",
                "value": len(forecast),
                "denominator": len(certification),
                "unit": "tickers",
                "interpretation": "AT_LEAST_ONE_REPORTED_OOS_RESULT",
            },
            {
                "metric": "energy_forecast_oos_company_coverage",
                "value": len(energy_forecast),
                "denominator": len(energy_universe),
                "unit": "tickers",
                "interpretation": "AT_LEAST_ONE_REPORTED_OOS_RESULT",
            },
            {
                "metric": "industrials_forecast_oos_company_coverage",
                "value": len(industrials_forecast),
                "denominator": len(industrials_universe),
                "unit": "tickers",
                "interpretation": "AT_LEAST_ONE_REPORTED_OOS_RESULT",
            },
            {
                "metric": "median_ticker_revenue_mase",
                "value": float(forecast["revenue_mase"].median()),
                "denominator": len(forecast),
                "unit": "ratio",
                "interpretation": "LOWER_THAN_ONE_BEATS_TICKER_BASELINE",
            },
            {
                "metric": "median_ticker_revenue_error_pct",
                "value": float(forecast["revenue_wape_pct"].median()),
                "denominator": len(forecast),
                "unit": "percent",
                "interpretation": "ENERGY_WORST_SPLIT_WAPE_OR_MAPE; INDUSTRIALS_MEAN_APE",
            },
            {
                "metric": "energy_median_ticker_revenue_mase",
                "value": float(energy_forecast["revenue_mase"].median()),
                "denominator": len(energy_forecast),
                "unit": "ratio",
                "interpretation": "WORST_OF_TIME_AND_LOCO_SELECTED_RESULT",
            },
            {
                "metric": "industrials_median_ticker_revenue_mase",
                "value": float(industrials_forecast["revenue_mase"].median()),
                "denominator": len(industrials_forecast),
                "unit": "ratio",
                "interpretation": "FIXED_TIME_OOS",
            },
            {
                "metric": "energy_median_ticker_revenue_error_pct",
                "value": float(energy_forecast["revenue_wape_pct"].median()),
                "denominator": len(energy_forecast),
                "unit": "percent",
                "interpretation": "WORST_SPLIT_WAPE_OR_SOURCE_SCORECARD_MAPE",
            },
            {
                "metric": "industrials_median_ticker_revenue_error_pct",
                "value": float(industrials_forecast["revenue_wape_pct"].median()),
                "denominator": len(industrials_forecast),
                "unit": "percent",
                "interpretation": "MEAN_REVENUE_LEVEL_APE",
            },
            {
                "metric": "forecast_point_gate_pass",
                "value": int(certification["forecast_point_gate"].fillna(False).sum()),
                "denominator": len(certification),
                "unit": "tickers",
                "interpretation": "PREDECLARED_POINT_FORECAST_GATE_ONLY",
            },
            {
                "metric": "legacy_research_dcf_coverage",
                "value": legacy_dcf_count,
                "denominator": len(certification),
                "unit": "tickers",
                "interpretation": "PREEXISTING_CONDITIONAL_RESEARCH_OUTPUT_NOT_V2_1_APPROVAL",
            },
            {
                "metric": "strict_v21_dcf_coverage",
                "value": len(v21_dcf),
                "denominator": len(certification),
                "unit": "tickers",
                "interpretation": "PARSER_PLUS_FORECAST_PLUS_ACCOUNTING_PLUS_MARKET_GATED",
            },
            {
                "metric": "strict_v21_dcf_median_absolute_market_distance_pct",
                "value": float(v21_dcf["absolute_market_distance_pct"].median())
                if not v21_dcf.empty
                else np.nan,
                "denominator": len(v21_dcf),
                "unit": "percent",
                "interpretation": "EXPECTATIONS_GAP_DIAGNOSTIC_NOT_FAIR_VALUE_ACCURACY",
            },
            {
                "metric": "strict_v21_dcf_median_terminal_value_share_pct",
                "value": float(v21_dcf["terminal_value_share_pct"].median())
                if not v21_dcf.empty
                else np.nan,
                "denominator": len(v21_dcf),
                "unit": "percent",
                "interpretation": "HIGH_TERMINAL_DEPENDENCE_MONITOR",
            },
            {
                "metric": "forward_reverse_numerical_roundtrip_solved",
                "value": total_roundtrip_solved,
                "denominator": total_roundtrip,
                "unit": "checks",
                "interpretation": "NUMERICAL_ACCURACY_NOT_ECONOMIC_ACCURACY",
            },
            {
                "metric": "forward_reverse_max_absolute_repricing_error_pct",
                "value": float(numerical_errors.max()),
                "denominator": total_roundtrip_solved,
                "unit": "percent",
                "interpretation": "NUMERICAL_ACCURACY_NOT_ECONOMIC_ACCURACY",
            },
            {
                "metric": "market_reverse_solved",
                "value": int(energy_market_solved.sum()) + industrial_market_solved,
                "denominator": len(energy_b) + len(industrial_reverse) * 2,
                "unit": "checks",
                "interpretation": "UNBRACKETED_RETAINED_AS_NON_IDENTIFIABLE",
            },
            {
                "metric": "market_reverse_max_absolute_repricing_error_pct",
                "value": float(market_errors.max()),
                "denominator": len(market_errors),
                "unit": "percent",
                "interpretation": "SOLVED_ROOT_REPRICING_ACCURACY_ONLY",
            },
            {
                "metric": "strict_v21_shared_kernel_compatibility_max_usd",
                "value": float(v21_dcf["shared_kernel_compatibility_error_usd"].max())
                if not v21_dcf.empty
                else np.nan,
                "denominator": len(v21_dcf),
                "unit": "USD",
                "interpretation": "V1_1_ENERGY_GOLDEN_COMPATIBILITY",
            },
            {
                "metric": "realized_fair_value_accuracy_observations",
                "value": 0,
                "denominator": 20,
                "unit": "settled_forward_observations",
                "interpretation": "NOT_MEASURABLE_LIVE_FORWARD_0_OF_20",
            },
        ]
    )


def main() -> int:
    industrials = _industrials_evidence()
    energy = _energy_evidence()
    evidence = pd.concat([energy, industrials], ignore_index=True, sort=False)
    if len(evidence) != 52 or evidence["ticker"].nunique() != 52:
        raise ValueError(
            f"Expected 52 unique registered tickers, got {len(evidence)} rows / "
            f"{evidence['ticker'].nunique()} tickers"
        )
    documents, frames, reviews = _audit_latest_ir(evidence)
    blind_audit = _blind_holdout_audit(documents, frames)
    document_summary = documents[
        ["ticker", "source_status", "frames", "facts", "reviews"]
    ].rename(
        columns={
            "source_status": "latest_ir_source_status",
            "frames": "latest_ir_frames",
            "facts": "latest_ir_facts",
            "reviews": "latest_ir_reviews",
        }
    )
    evidence = evidence.merge(document_summary, on="ticker", how="left")
    evidence["latest_ir_parsed"] = evidence["latest_ir_source_status"].eq("PARSED")
    evidence["text_ie_review_rate_pct"] = (
        evidence["latest_ir_reviews"]
        / (evidence["latest_ir_frames"] + evidence["latest_ir_reviews"]).replace(0, np.nan)
        * 100.0
    )
    blind_precision = float(blind_audit.iloc[0]["critical_numeric_precision"])
    evidence["blind_holdout_frame_precision"] = float(
        blind_audit.iloc[0]["frame_precision"]
    )
    evidence["blind_holdout_critical_numeric_precision"] = blind_precision
    evidence["blind_holdout_recall"] = np.nan
    # A global independent audit is a ceiling on any narrower in-sample gold
    # result.  This deliberately removes all valuation eligibility when the
    # general parser misses the predeclared 99% precision standard.
    evidence["critical_numeric_precision"] = evidence[
        "critical_numeric_precision"
    ].where(
        evidence["critical_numeric_precision"].notna(), blind_precision
    ).clip(upper=blind_precision)
    certification = certify_universe(evidence)
    v21_dcf, v21_roundtrip, v21_reverse = _v21_dcf(certification)
    accuracy = _accuracy_summary(
        certification, v21_dcf, v21_roundtrip, v21_reverse
    )
    class_summary = (
        certification.groupby(["sector", "universe_class"], as_index=False)
        .agg(tickers=("ticker", "size"))
    )
    parser_summary = (
        certification.groupby(["sector", "parser_certification"], as_index=False)
        .agg(tickers=("ticker", "size"))
    )
    forecast_summary = (
        certification.groupby(["sector", "forecast_certification"], as_index=False)
        .agg(tickers=("ticker", "size"))
    )
    gate = pd.DataFrame(
        [
            {
                "version": "PLATFORM_V2_1_UNIVERSE_CERTIFICATION_RESEARCH",
                "registered_tickers": len(certification),
                "latest_ir_documents_parsed": documents["source_status"].eq("PARSED").sum(),
                "latest_ir_parse_errors": documents["source_status"].eq("PARSE_ERROR").sum(),
                "semantic_frames": len(frames),
                "semantic_review_items": len(reviews),
                "blind_holdout_frame_precision": blind_audit.iloc[0][
                    "frame_precision"
                ],
                "blind_holdout_critical_numeric_precision": blind_precision,
                "blind_holdout_recall_status": blind_audit.iloc[0][
                    "recall_status"
                ],
                "parser_certified_tickers": certification[
                    "parser_certification"
                ].eq("PARSER_CERTIFIED").sum(),
                "strict_valuation_ready_tickers": certification[
                    "valuation_eligibility"
                ].eq("VALUATION_READY").sum(),
                "strict_dcf_runs": len(v21_dcf),
                "terminal_input_ready": False,
                "fair_value_claim_allowed": False,
                "production_promoted": False,
                "live_matched_observations": "0/20",
                "status": "RESEARCH_CERTIFICATION_COMPLETE_PRODUCTION_LOCKED",
            }
        ]
    )
    artifacts = {
        "universe_certification": certification,
        "universe_class_summary": class_summary,
        "parser_certification_summary": parser_summary,
        "forecast_certification_summary": forecast_summary,
        "latest_ir_document_audit": documents,
        "latest_ir_semantic_frames": frames,
        "latest_ir_review_queue": reviews,
        "blind_holdout_audit": blind_audit,
        "v21_eligible_conditional_dcf": v21_dcf,
        "v21_eligible_reverse_roundtrip": v21_roundtrip,
        "v21_eligible_market_reverse": v21_reverse,
        "coverage_and_accuracy_summary": accuracy,
        "platform_v21_gate": gate,
    }
    write_csv_artifacts(OUTPUT, artifacts)
    write_csv_artifacts(GOLD, artifacts)
    metadata = {
        "version": gate.iloc[0]["version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_date": AS_OF.date().isoformat(),
        "universe_definition": "26_ENERGY_PLUS_26_INDUSTRIALS_ARCHETYPE_REPRESENTATIVES",
        "development_probe_tickers_contaminated": sorted(DEVELOPMENT_PROBE_TICKERS),
        "development_probe_used_for_rule_changes": True,
        "outcome_blind_holdout_tickers_predeclared": sorted(
            FINAL_BLIND_HOLDOUT_TICKERS
        ),
        "latest_ir_rule_changes_after_holdout_selection": False,
        "semantic_dsl_architecture": "VAR_PATTERN_FRAME_CONTEXT_RELATION_FACT_IR",
        "hmrb_runtime_dependency": False,
        "semantic_dsl_execution_backend": "SPACY_PRIMITIVES_BEHIND_BACKEND_NEUTRAL_RULE_IR",
        "blind_holdout_recall_status": blind_audit.iloc[0]["recall_status"],
        "fair_value_accuracy_interpretation": "NOT_MEASURABLE_UNTIL_FORWARD_SETTLEMENT",
        "terminal_input_allowed": False,
        "production_promoted": False,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = f"""# Platform V2.1 — Energy + Industrials Universe Certification

## Gate

{markdown_table(gate)}

Every registered ticker is parsed/certified before valuation eligibility is
evaluated. Missing critical gold evidence fails closed. A pre-existing research
DCF remains visible as a diagnostic but cannot make a ticker V2.1 ready.

## Universe classes

{markdown_table(class_summary)}

## Parser certification

{markdown_table(parser_summary)}

## Forecast certification

{markdown_table(forecast_summary)}

## Coverage and accuracy

{markdown_table(accuracy)}

## Outcome-blind issuer audit

{markdown_table(blind_audit)}

The blind audit measures precision of emitted frames only. Recall is not
claimed because the held-out documents do not yet have exhaustive
sentence-level gold annotations. Its 99% precision failure is applied globally
and therefore blocks V2.1 valuation eligibility rather than being averaged
away by the controlled corpus.

`Forward/reverse numerical accuracy` measures whether the solver recovers and
reprices a known DCF value. `Market reverse accuracy` measures root residual only.
Neither is evidence that the economic assumptions or fair value are correct.
Realized fair-value accuracy remains unavailable at live-forward 0/20.

## Strictly eligible conditional DCF

{markdown_table(v21_dcf)}

All values remain research diagnostics. Terminal inputs, fair-value authority,
production promotion and post-outcome tuning are prohibited.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")
    print(gate.to_string(index=False))
    print(class_summary.to_string(index=False))
    print(accuracy.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
