from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import gzip
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.platform.registry import (
    INDUSTRIALS_SUBINDUSTRIES,
)


ROOT = PROJECT_ROOT / "data-lake/bronze/industrials/v8/subindustries/sec"
CUTOFF = "2026-09-04"
START = "2021-01-01"
FORMS = {"10-K", "10-Q"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, target: Path, user_agent: str) -> None:
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=90) as response:
        payload = response.read()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    time.sleep(0.13)


def _json(url: str, target: Path, user_agent: str) -> dict[str, object]:
    if not target.exists():
        _download(url, target, user_agent)
    raw = target.read_bytes()
    if raw.startswith(b"\x1f\x8b"):
        raw = gzip.decompress(raw)
        target.write_bytes(raw)
    return json.loads(raw.decode("utf-8"))


def main() -> int:
    user_agent = os.environ.get(
        "SEC_USER_AGENT",
        "ForecastTest Industrials subindustry research contact@example.com",
    )
    ticker_path = ROOT / "company_tickers.json"
    tickers = _json(
        "https://www.sec.gov/files/company_tickers.json", ticker_path, user_agent
    )
    lookup = {
        str(row["ticker"]).upper(): str(row["cik_str"]).zfill(10)
        for row in tickers.values()
    }
    profiles = [
        profile
        for profile in INDUSTRIALS_SUBINDUSTRIES
        if profile.sec_form_regime == "10-K_10-Q"
    ]
    company_rows: list[dict[str, object]] = []
    filing_rows: list[dict[str, object]] = []
    for profile in profiles:
        ticker = profile.representative_ticker
        company_root = ROOT / ticker.lower()
        cik = lookup.get(ticker)
        if not cik:
            company_rows.append(
                {
                    "subindustry_code": profile.code,
                    "ticker": ticker,
                    "status": "FAIL_CLOSED_TICKER_NOT_IN_SEC_MAP",
                    "error": "",
                }
            )
            continue
        try:
            submissions_path = company_root / "submissions.json"
            companyfacts_path = company_root / "companyfacts.json"
            submissions = _json(
                f"https://data.sec.gov/submissions/CIK{cik}.json",
                submissions_path,
                user_agent,
            )
            _json(
                f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
                companyfacts_path,
                user_agent,
            )
            recent = submissions["filings"]["recent"]
            company_filings: list[dict[str, object]] = []
            for index, form in enumerate(recent["form"]):
                filing_date = recent["filingDate"][index]
                if form not in FORMS or not (START <= filing_date <= CUTOFF):
                    continue
                accession = recent["accessionNumber"][index]
                document = recent["primaryDocument"][index]
                cik_archive = str(int(cik))
                url = (
                    f"https://www.sec.gov/Archives/edgar/data/{cik_archive}/"
                    f"{accession.replace('-', '')}/{document}"
                )
                target = company_root / form / f"{filing_date}_{accession}_{document}"
                if not target.exists():
                    _download(url, target, user_agent)
                row = {
                    "subindustry_code": profile.code,
                    "ticker": ticker,
                    "cik": cik,
                    "form": form,
                    "filing_date": filing_date,
                    "report_date": recent["reportDate"][index],
                    "accession_number": accession,
                    "primary_document": document,
                    "source_url": url,
                    "local_path": target.relative_to(PROJECT_ROOT).as_posix(),
                    "sha256": _sha256(target),
                    "size_bytes": target.stat().st_size,
                    "pdf_parsing_used": False,
                }
                company_filings.append(row)
                filing_rows.append(row)
            manifest = {
                "subindustry_code": profile.code,
                "ticker": ticker,
                "cik": cik,
                "cutoff": CUTOFF,
                "start": START,
                "forms": sorted(FORMS),
                "submissions_path": submissions_path.relative_to(PROJECT_ROOT).as_posix(),
                "submissions_sha256": _sha256(submissions_path),
                "companyfacts_path": companyfacts_path.relative_to(PROJECT_ROOT).as_posix(),
                "companyfacts_sha256": _sha256(companyfacts_path),
                "filings": company_filings,
            }
            manifest_path = company_root / "manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            company_rows.append(
                {
                    "subindustry_code": profile.code,
                    "ticker": ticker,
                    "cik": cik,
                    "form_10k_count": sum(
                        row["form"] == "10-K" for row in company_filings
                    ),
                    "form_10q_count": sum(
                        row["form"] == "10-Q" for row in company_filings
                    ),
                    "filing_count": len(company_filings),
                    "manifest_path": manifest_path.relative_to(PROJECT_ROOT).as_posix(),
                    "manifest_sha256": _sha256(manifest_path),
                    "status": "READY" if company_filings else "FAIL_CLOSED_NO_FILINGS",
                    "error": "",
                }
            )
            print(ticker, len(company_filings), "READY", flush=True)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            company_rows.append(
                {
                    "subindustry_code": profile.code,
                    "ticker": ticker,
                    "cik": cik,
                    "status": "FAIL_CLOSED_DOWNLOAD_ERROR",
                    "error": str(error),
                }
            )
            print(ticker, "ERROR", error, flush=True)
    catalog = {
        "dataset": "INDUSTRIALS_V8_SUBINDUSTRY_SEC_EDGAR",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "cutoff": CUTOFF,
        "start": START,
        "company_count": len(company_rows),
        "ready_companies": sum(row["status"] == "READY" for row in company_rows),
        "companies": company_rows,
        "filings": filing_rows,
        "company_tickers_path": ticker_path.relative_to(PROJECT_ROOT).as_posix(),
        "company_tickers_sha256": _sha256(ticker_path),
    }
    catalog_path = ROOT / "catalog_manifest.json"
    catalog_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "catalog": str(catalog_path),
                "companies": len(company_rows),
                "ready": catalog["ready_companies"],
                "filings": len(filing_rows),
            },
            indent=2,
        )
    )
    return 0 if catalog["ready_companies"] == len(profiles) else 2


if __name__ == "__main__":
    raise SystemExit(main())
