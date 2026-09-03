from __future__ import annotations

from pathlib import Path
import re

from lxml import html
import numpy as np
import pandas as pd


SEGMENT_LABELS = {
    "Aeronautics": "aeronautics",
    "Missiles and Fire Control": "missiles_fire_control",
    "Rotary and Mission Systems": "rotary_mission_systems",
    "Space": "space",
}
_METRIC = re.compile(
    r"^(?:(?:first|second|third|fourth) quarter 20\d{2}\s+)?"
    r"(?:(?:Aeronautics|MFC|RMS|Space).{0,4})?\s*"
    r"(?:net\s+)?(sales|operating profit)",
    re.IGNORECASE,
)
_MONEY = re.compile(r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(million|billion)", re.IGNORECASE)
_TOTAL_DELTA = re.compile(
    r"(?:sales|operating profit).*?\b(increased|decreased)\s+"
    r"(?:by\s+)?(?:approximately\s+|about\s+)?"
    r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(million|billion)",
    re.IGNORECASE,
)
_DIRECTION = re.compile(
    r"\b(higher|increased|increase|lower|decreased|decrease|"
    r"favorable|unfavorable|loss|losses)\b",
    re.IGNORECASE,
)


PROGRAM_BUCKETS = {
    "aero_f35_sales_delta_usd": ("f-35", "f?35"),
    "aero_f16_sales_delta_usd": ("f-16", "f?16"),
    "aero_c130_sales_delta_usd": ("c-130", "c?130"),
    "aero_classified_sales_delta_usd": ("classified",),
    "rms_sikorsky_sales_delta_usd": ("sikorsky", "black hawk", "seahawk", "ch-53"),
    "rms_iwss_sales_delta_usd": (
        "integrated warfare systems",
        "iwss",
        "sems",
        "mission integrated command",
        "mic2",
    ),
    "rms_tls_sales_delta_usd": ("training and logistics", "tls"),
    "rms_c6isr_sales_delta_usd": ("c6isr",),
    "space_strategic_sales_delta_usd": ("strategic and missile defense", "ngi", "fleet ballistic"),
    "space_national_security_sales_delta_usd": ("national security space", "classified"),
    "space_commercial_civil_sales_delta_usd": ("commercial civil space", "orion"),
}


def _normalize(value: str) -> str:
    text = value.replace("\xa0", " ").replace("’", "'").replace("‘", "'")
    text = re.sub(r"[‐‑‒–—−]", "-", text)
    text = " ".join(text.split())
    return re.sub(r"^S\s+ales\b", "Sales", text, flags=re.IGNORECASE)


def _money_value(match: re.Match[str]) -> float:
    multiplier = 1e9 if match.group(2).lower() == "billion" else 1e6
    return float(match.group(1)) * multiplier


def _total_span(text: str) -> tuple[int, int] | None:
    match = _TOTAL_DELTA.search(text)
    return match.span(2) if match else None


def _signed_amount_near_keywords(text: str, keywords: tuple[str, ...]) -> float:
    lowered = text.lower()
    total = _total_span(text)
    candidates: list[tuple[int, float]] = []
    for money in _MONEY.finditer(text):
        if total and total[0] <= money.start(1) <= total[1]:
            continue
        left = max(0, money.start() - 150)
        right = min(len(text), money.end() + 190)
        window = lowered[left:right]
        positions = [window.find(keyword) for keyword in keywords if window.find(keyword) >= 0]
        if not positions:
            continue
        money_position = money.start() - left
        program_distance = min(abs(position - money_position) for position in positions)
        directional: list[tuple[int, str]] = []
        for direction in _DIRECTION.finditer(window):
            distance = abs(direction.start() - money_position)
            if distance <= 100:
                directional.append((distance, direction.group(1).lower()))
        if not directional:
            continue
        direction = min(directional, key=lambda item: item[0])[1]
        sign = -1.0 if direction in {"lower", "decreased", "decrease", "unfavorable", "loss", "losses"} else 1.0
        candidates.append((program_distance, sign * _money_value(money)))
    return min(candidates, key=lambda item: item[0])[1] if candidates else np.nan


def _metric_paragraphs(source: pd.Series) -> list[dict[str, object]]:
    tree = html.fromstring(Path(str(source["source_path"])).read_bytes())
    segment: str | None = None
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, object]] = []
    for node in tree.xpath("//div[not(.//div)]"):
        text = _normalize(" ".join(node.itertext()))
        if text in SEGMENT_LABELS:
            segment = SEGMENT_LABELS[text]
            continue
        if segment is None or not 50 <= len(text) <= 2_500:
            continue
        match = _METRIC.match(text)
        if not match or not any(token in text.lower() for token in ("compared to", "comparable to", "comparable with")):
            continue
        metric = match.group(1).lower().replace(" ", "_")
        if (segment, metric) in seen:
            continue
        seen.add((segment, metric))
        rows.append(
            {
                "period": source["period"],
                "segment": segment,
                "metric": metric,
                "narrative_text": text,
                "filing_date": source["filing_date"],
                "source_url": source["source_url"],
                "source_sha256": source["actual_sha256"],
                "historical_pit_evidence": True,
            }
        )
    return rows


def _program_attributions(paragraphs: pd.DataFrame) -> pd.DataFrame:
    bucket_prefix = {
        "aeronautics": "aero_",
        "rotary_mission_systems": "rms_",
        "space": "space_",
    }
    rows: list[dict[str, object]] = []
    for (period, segment), group in paragraphs.groupby(["period", "segment"]):
        sales = group.loc[group["metric"].eq("sales")]
        profit = group.loc[group["metric"].eq("operating_profit")]
        sales_text = str(sales.iloc[0]["narrative_text"]) if len(sales) == 1 else ""
        profit_text = str(profit.iloc[0]["narrative_text"]) if len(profit) == 1 else ""
        row: dict[str, object] = {
            "period": period,
            "segment": segment,
            "sales_narrative_available": bool(sales_text),
            "operating_profit_narrative_available": bool(profit_text),
            "filing_date": group.iloc[0]["filing_date"],
            "source_url": group.iloc[0]["source_url"],
            "source_sha256": group.iloc[0]["source_sha256"],
        }
        for column, keywords in PROGRAM_BUCKETS.items():
            row[column] = (
                _signed_amount_near_keywords(sales_text, keywords)
                if column.startswith(bucket_prefix.get(segment, "NO_MATCH_"))
                else np.nan
            )
        if segment == "space":
            row["space_profit_booking_adjustment_delta_usd"] = _signed_amount_near_keywords(
                profit_text, ("profit booking rate adjustment", "profit rate adjustment")
            )
            row["space_equity_earnings_delta_usd"] = _signed_amount_near_keywords(
                profit_text, ("equity earnings", "equity losses", "ula")
            )
            row["space_sales_volume_profit_delta_usd"] = _signed_amount_near_keywords(
                profit_text, ("sales volume", "higher volume", "lower volume")
            )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["period", "segment"]).reset_index(drop=True)


def _backlog_horizon(sec_inventory: pd.DataFrame) -> pd.DataFrame:
    pattern = re.compile(
        r"recognize approximately\s+(\d+)%.*?next 12 months.*?"
        r"(?:a total of\s+)?approximately\s+(\d+)%.*?next 24 months",
        re.IGNORECASE,
    )
    rows: list[dict[str, object]] = []
    for _, source in sec_inventory.loc[sec_inventory["form"].eq("10-K")].iterrows():
        tree = html.fromstring(Path(str(source["resolved_path"])).read_bytes())
        text = _normalize(" ".join(tree.itertext()))
        match = pattern.search(text)
        rows.append(
            {
                "fiscal_year": int(str(source["report_date"])[:4]),
                "filing_date": source["filing_date"],
                "backlog_expected_within_12m_pct": float(match.group(1)) if match else np.nan,
                "backlog_expected_within_24m_pct": float(match.group(2)) if match else np.nan,
                "program_level_backlog_amount_disclosed": False,
                "authority": "COMPANY_WIDE_CONVERSION_HORIZON_NOT_PROGRAM_BACKLOG",
                "source_url": source["source_url"],
                "source_sha256": source["sha256"],
            }
        )
    return pd.DataFrame(rows).sort_values("fiscal_year").reset_index(drop=True)


def _sec_10q_program_crosscheck(
    attributions: pd.DataFrame,
    sec_inventory: pd.DataFrame,
) -> pd.DataFrame:
    columns = {
        "aero_f35_sales_delta_usd": PROGRAM_BUCKETS["aero_f35_sales_delta_usd"],
        "aero_classified_sales_delta_usd": PROGRAM_BUCKETS["aero_classified_sales_delta_usd"],
        "rms_sikorsky_sales_delta_usd": PROGRAM_BUCKETS["rms_sikorsky_sales_delta_usd"],
        "space_profit_booking_adjustment_delta_usd": (
            "profit booking rate adjustment",
            "profit rate adjustment",
        ),
        "space_equity_earnings_delta_usd": ("equity earnings", "equity losses", "ula"),
    }
    indexed = attributions.set_index(["period", "segment"])
    rows: list[dict[str, object]] = []
    for _, source in sec_inventory.loc[sec_inventory["form"].eq("10-Q")].iterrows():
        report_date = pd.Timestamp(source["report_date"])
        quarter = {3: 1, 6: 2, 9: 3, 12: 4}[report_date.month]
        period = f"{report_date.year}Q{quarter}"
        text = _normalize(" ".join(html.fromstring(Path(str(source["resolved_path"])).read_bytes()).itertext())).lower()
        money = [
            (
                match.start(),
                _money_value(match),
            )
            for match in _MONEY.finditer(text)
        ]
        for segment in ("aeronautics", "rotary_mission_systems", "space"):
            if (period, segment) not in indexed.index:
                continue
            attribution = indexed.loc[(period, segment)]
            for metric, keywords in columns.items():
                value = attribution[metric]
                if pd.isna(value):
                    continue
                matches = [
                    position
                    for position, disclosed in money
                    if abs(abs(float(value)) - disclosed) <= 1.0
                    and any(
                        keyword in text[max(0, position - 250) : position + 350]
                        for keyword in keywords
                    )
                ]
                rows.append(
                    {
                        "period": period,
                        "segment": segment,
                        "metric": metric,
                        "ir_value_usd": value,
                        "sec_matching_amount_keyword_windows": len(matches),
                        "sec_10q_crosscheck_pass": bool(matches),
                        "sec_filing_date": source["filing_date"],
                        "sec_source_url": source["source_url"],
                        "sec_source_sha256": source["sha256"],
                    }
                )
    return pd.DataFrame(rows).sort_values(["period", "segment", "metric"]).reset_index(drop=True)


def build_lmt_program_conversion_evidence(
    *,
    ir_inventory: pd.DataFrame,
    sec_inventory: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    selected = ir_inventory.loc[
        ir_inventory["model_use"].eq("QUARTERLY_EARNINGS_RELEASE")
        & ir_inventory["hash_match"].astype(bool)
    ].sort_values("period")
    paragraphs = pd.DataFrame(
        [row for _, source in selected.iterrows() for row in _metric_paragraphs(source)]
    )
    attributions = _program_attributions(paragraphs)
    horizon = _backlog_horizon(sec_inventory)
    sec_crosscheck = _sec_10q_program_crosscheck(attributions, sec_inventory)
    expected_paragraphs = len(selected) * len(SEGMENT_LABELS) * 2
    summary = pd.DataFrame(
        [
            {
                "ir_releases_audited": len(selected),
                "expected_segment_metric_narratives": expected_paragraphs,
                "parsed_segment_metric_narratives": len(paragraphs),
                "segment_metric_narrative_coverage_pct": len(paragraphs) / expected_paragraphs * 100.0,
                "rms_sikorsky_attribution_periods": int(
                    attributions["rms_sikorsky_sales_delta_usd"].notna().sum()
                ),
                "aero_f35_attribution_periods": int(
                    attributions["aero_f35_sales_delta_usd"].notna().sum()
                ),
                "space_profit_booking_attribution_periods": int(
                    attributions["space_profit_booking_adjustment_delta_usd"].notna().sum()
                ),
                "space_equity_earnings_attribution_periods": int(
                    attributions["space_equity_earnings_delta_usd"].notna().sum()
                ),
                "annual_backlog_horizon_filings": len(horizon),
                "annual_backlog_horizon_coverage_pct": horizon[
                    ["backlog_expected_within_12m_pct", "backlog_expected_within_24m_pct"]
                ].notna().all(axis=1).mean()
                * 100.0,
                "program_level_backlog_amount_coverage_pct": 0.0,
                "program_level_backlog_fail_closed": True,
                "sec_10q_program_amount_cells": len(sec_crosscheck),
                "sec_10q_program_amount_identity_pass_cells": int(
                    sec_crosscheck["sec_10q_crosscheck_pass"].sum()
                ),
                "sec_10q_program_amount_identity_pct": float(
                    sec_crosscheck["sec_10q_crosscheck_pass"].mean() * 100.0
                ),
                "evidence_gate_pass": bool(
                    len(paragraphs) >= expected_paragraphs - 12
                    and len(horizon) == 6
                    and horizon["backlog_expected_within_12m_pct"].notna().all()
                    and len(sec_crosscheck) > 0
                    and sec_crosscheck["sec_10q_crosscheck_pass"].all()
                ),
                "pdf_parsing_used": False,
            }
        ]
    )
    return {
        "lmt_v31_segment_metric_narratives": paragraphs,
        "lmt_v31_program_attribution_history": attributions,
        "lmt_v31_backlog_conversion_horizon": horizon,
        "lmt_v31_sec_10q_program_crosscheck": sec_crosscheck,
        "lmt_v31_program_evidence_summary": summary,
    }
