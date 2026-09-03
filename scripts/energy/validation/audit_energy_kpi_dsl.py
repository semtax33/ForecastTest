from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.energy.parsing.company_kpi import (
    ENERGY_KPI_RULES,
    extract_filing_metrics,
)


DEFAULT_SNAPSHOT = (
    PROJECT_ROOT / "data-lake/bronze/snapshots/phase2_4_company_kpi"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "output/platform_architecture_v2"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit Energy KPI DSL migration")
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def _documents(snapshot: Path, group: pd.DataFrame) -> list[dict[str, str]]:
    result = []
    for row in group.itertuples(index=False):
        path = snapshot / "raw" / str(row.ticker) / Path(str(row.local_path)).name
        if not path.exists():
            raise FileNotFoundError(path)
        result.append(
            {
                "html": path.read_text(encoding="utf-8", errors="ignore"),
                "source_url": str(row.source_url),
                "description": str(row.description),
                "local_path": str(path),
                "sha256": str(row.sha256),
            }
        )
    return result


def rebuild(snapshot: Path) -> pd.DataFrame:
    manifest = pd.read_csv(snapshot / "source_manifest.csv")
    alternatives: dict[tuple[str, str], list[tuple[pd.Timestamp, list[dict[str, object]]]]] = {}
    for (ticker, accession), group in manifest.groupby(
        ["ticker", "accession"], sort=False
    ):
        first = group.iloc[0]
        filing = {
            "report_quarter": str(first["report_quarter"]),
            "filingDate": str(first["filing_date"]),
            "acceptanceDateTime": first["acceptance_datetime_utc"],
            "accessionNumber": str(accession),
        }
        extracted = extract_filing_metrics(
            str(ticker), filing, _documents(snapshot, group)
        )
        key = str(ticker), str(first["report_quarter"])
        alternatives.setdefault(key, []).append(
            (pd.Timestamp(first["filing_date"]), extracted)
        )
    selected: list[dict[str, object]] = []
    for filings in alternatives.values():
        _, rows = sorted(filings, key=lambda item: (-len(item[1]), item[0]))[0]
        selected.extend(rows)
    return pd.DataFrame(selected)


def compare(snapshot: Path, actual: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    expected = pd.read_csv(snapshot / "company_kpi_quarterly.csv")
    key = ["ticker", "report_quarter", "metric_id", "accession"]
    comparison = expected[key + ["metric_value"]].rename(
        columns={"metric_value": "expected_value"}
    ).merge(
        actual[key + ["metric_value", "parser_rule_id", "parser_rule_sha256"]].rename(
            columns={"metric_value": "actual_value"}
        ),
        on=key,
        how="outer",
        indicator=True,
    )
    comparison["absolute_delta"] = (
        comparison["actual_value"] - comparison["expected_value"]
    ).abs()
    comparison["key_match"] = comparison["_merge"].eq("both")
    comparison["value_match"] = comparison["absolute_delta"].le(1e-9)
    summary = {
        "dsl_rule_count": len(ENERGY_KPI_RULES),
        "ticker_count": len({rule.entities[0] for rule in ENERGY_KPI_RULES}),
        "expected_rows": len(expected),
        "actual_rows": len(actual),
        "key_mismatches": int((~comparison["key_match"]).sum()),
        "value_mismatches": int(
            (comparison["key_match"] & ~comparison["value_match"]).sum()
        ),
        "maximum_absolute_delta": float(
            comparison.loc[comparison["key_match"], "absolute_delta"].max()
        ),
        "all_rules_hashed": bool(
            actual["parser_rule_sha256"].str.fullmatch(r"[0-9a-f]{64}").all()
        ),
        "migration_gate_passed": bool(
            comparison["key_match"].all()
            and comparison["value_match"].fillna(False).all()
        ),
    }
    return comparison, summary


def main() -> int:
    args = _arguments()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    actual = rebuild(args.snapshot.resolve())
    comparison, summary = compare(args.snapshot.resolve(), actual)
    actual.to_csv(output / "energy_kpi_dsl_rebuilt.csv", index=False)
    comparison.to_csv(output / "energy_kpi_dsl_migration.csv", index=False)
    (output / "energy_kpi_dsl_migration.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["migration_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
