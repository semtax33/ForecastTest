from __future__ import annotations

import csv
import hashlib
import mmap
from pathlib import Path

import numpy as np
import pandas as pd


FACT_ROUTES: dict[str, tuple[str, ...]] = {
    "acquiree_net_income_since_close_usd": (
        "BusinessCombinationProFormaInformationEarningsOrLossOfAcquireeSinceAcquisitionDateActual",
    ),
    "acquiree_revenue_since_close_usd": (
        "BusinessCombinationProFormaInformationRevenueOfAcquireeSinceAcquisitionDateActual",
    ),
    "total_consideration_usd": (
        "BusinessCombinationConsiderationTransferred1",
    ),
    "equity_consideration_usd": (
        "BusinessCombinationConsiderationTransferredEquityInterestsIssuedAndIssuable",
    ),
    "recognized_net_assets_usd": (
        "BusinessCombinationRecognizedIdentifiableAssetsAcquiredAndLiabilitiesAssumedNet",
    ),
    "assumed_long_term_debt_usd": (
        "BusinessCombinationRecognizedIdentifiableAssetsAcquiredAndLiabilitiesAssumedNoncurrentLiabilitiesLongTermDebt",
    ),
    "cash_acquired_usd": (
        "BusinessCombinationRecognizedIdentifiableAssetsAcquiredAndLiabilitiesAssumedCashAndEquivalents",
        "CashAcquiredFromAcquisition",
    ),
    "asset_acquisition_ppe_usd": (
        "BusinessCombinationRecognizedIdentifiableAssetsAcquiredAndLiabilitiesAssumedPropertyPlantAndEquipment",
    ),
    "net_cash_paid_usd": (
        "PaymentsToAcquireBusinessesNetOfCashAcquired",
    ),
}
TRANSACTION_COST_ROUTE = ("BusinessCombinationAcquisitionRelatedCosts",)


def _record_hash(record: dict[str, str]) -> str:
    payload = "\t".join(f"{key}={record.get(key, '')}" for key in sorted(record))
    return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()


def _adsh_records(path: Path, adsh: str) -> list[dict[str, str]]:
    with path.open("rb") as handle:
        header = handle.readline().decode("utf-8-sig").rstrip("\r\n").split("\t")
        with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
            needle = b"\n" + adsh.encode("ascii") + b"\t"
            position = 0
            records: list[dict[str, str]] = []
            while True:
                found = mapped.find(needle, position)
                if found < 0:
                    break
                start = found + 1
                end = mapped.find(b"\n", start)
                if end < 0:
                    end = len(mapped)
                decoded = mapped[start:end].decode("utf-8", errors="replace")
                values = next(csv.reader([decoded], delimiter="\t", quotechar='"'))
                if len(values) == len(header):
                    records.append(dict(zip(header, values)))
                position = end
    return records


def _select_numeric_fact(
    records: list[dict[str, str]],
    tags: tuple[str, ...],
    *,
    dimension_hash: str,
) -> tuple[float, str, str]:
    candidates = [
        record
        for record in records
        if record.get("tag") in tags
        and record.get("dimh") == dimension_hash
        and record.get("uom") == "USD"
        and record.get("iprx") == "0"
    ]
    if not candidates:
        return np.nan, "", ""
    candidates.sort(
        key=lambda row: (
            int(float(row.get("qtrs") or 0)),
            int(float(row.get("ddate") or 0)),
        ),
        reverse=True,
    )
    selected = candidates[0]
    return (
        float(selected["value"]),
        str(selected["tag"]),
        _record_hash(selected),
    )


def _select_text_record(
    records: list[dict[str, str]], tag: str
) -> tuple[str, str]:
    candidates = [
        record
        for record in records
        if record.get("tag") == tag and record.get("lang") == "en-US"
    ]
    if not candidates:
        return "", ""
    candidates.sort(
        key=lambda row: (
            int(float(row.get("qtrs") or 0)),
            int(float(row.get("ddate") or 0)),
        ),
        reverse=True,
    )
    selected = candidates[0]
    return str(selected.get("value", "")), _record_hash(selected)


def build_mna_event_evidence(
    *, registry_path: Path, fnsd_root: Path
) -> pd.DataFrame:
    registry = pd.read_csv(registry_path, dtype={"adsh": str})
    rows: list[dict[str, object]] = []
    cache: dict[tuple[Path, str], list[dict[str, str]]] = {}
    for event in registry.to_dict("records"):
        folder = fnsd_root / str(event["fnsd_folder"])
        adsh = str(event["adsh"])
        sub = pd.read_csv(folder / "sub.tsv", sep="\t", low_memory=False)
        filing = sub.loc[sub["adsh"].astype(str).eq(adsh)]
        if len(filing) != 1:
            raise ValueError(f"Expected one FNSD submission for {adsh}, found {len(filing)}")
        filing_row = filing.iloc[0]
        if str(filing_row["form"]) != "10-K":
            raise ValueError(f"M&A source must be a 10-K: {adsh}")
        if int(float(filing_row["fy"])) != int(event["fiscal_year"]):
            raise ValueError(f"Fiscal-year mismatch for {adsh}")

        num_path = folder / "num.tsv"
        txt_path = folder / "txt.tsv"
        numeric_key = (num_path, adsh)
        text_key = (txt_path, adsh)
        if numeric_key not in cache:
            cache[numeric_key] = _adsh_records(num_path, adsh)
        if text_key not in cache:
            cache[text_key] = _adsh_records(txt_path, adsh)
        numeric = cache[numeric_key]
        text_records = cache[text_key]
        output: dict[str, object] = dict(event)
        evidence_hashes: list[str] = []
        for output_name, tags in FACT_ROUTES.items():
            value, source_tag, record_hash = _select_numeric_fact(
                numeric,
                tags,
                dimension_hash=str(event["event_dimh"]),
            )
            output[output_name] = value
            output[f"{output_name}_source_tag"] = source_tag
            output[f"{output_name}_record_sha256"] = record_hash
            if record_hash:
                evidence_hashes.append(record_hash)
        transaction_cost, transaction_tag, transaction_hash = _select_numeric_fact(
            numeric,
            TRANSACTION_COST_ROUTE,
            dimension_hash=str(event["transaction_cost_dimh"]),
        )
        output["acquisition_related_cost_usd"] = transaction_cost
        output["acquisition_related_cost_usd_source_tag"] = transaction_tag
        output["acquisition_related_cost_usd_record_sha256"] = transaction_hash
        if transaction_hash:
            evidence_hashes.append(transaction_hash)

        disclosure, disclosure_hash = _select_text_record(
            text_records, str(event["classification_text_tag"])
        )
        phrase = str(event["classification_phrase"]).casefold()
        output["classification_phrase_proven"] = phrase in disclosure.casefold()
        output["classification_disclosure_record_sha256"] = disclosure_hash
        output["classification_disclosure_excerpt"] = next(
            (
                sentence.strip()
                for sentence in disclosure.replace("\n", " ").split(".")
                if phrase in sentence.casefold()
            ),
            "",
        )
        if disclosure_hash:
            evidence_hashes.append(disclosure_hash)
        output["filing_date"] = pd.to_datetime(
            str(int(float(filing_row["filed"])))
        ).date().isoformat()
        output["source_form"] = str(filing_row["form"])
        output["source_num_path"] = str(num_path)
        output["source_txt_path"] = str(txt_path)
        output["source_evidence_bundle_sha256"] = hashlib.sha256(
            "|".join(sorted(evidence_hashes)).encode("ascii")
        ).hexdigest()
        output["point_in_time_proven"] = (
            pd.Timestamp(output["filing_date"])
            >= pd.Timestamp(str(event["event_close_date"]))
        )
        output["research_only"] = True
        rows.append(output)
    return pd.DataFrame(rows).sort_values(["fiscal_year", "ticker"]).reset_index(drop=True)
