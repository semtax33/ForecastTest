from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import gzip
import json
import os
from pathlib import Path
import time
from urllib.request import Request, urlopen

from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT / "data-lake/bronze/industrials/v8/subindustries/ifrs"
TICKER_SOURCE = (
    PROJECT_ROOT
    / "data-lake/bronze/industrials/v8/subindustries/sec/company_tickers.json"
)
TICKERS = {"PAC": "airport_services", "FER": "highways_railtracks"}
FORMS = {"20-F", "6-K"}
START = "2021-01-01"
CUTOFF = "2026-09-04"


def _sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, target: Path, user_agent: str) -> None:
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=90) as response:
        body = response.read()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)
    time.sleep(0.13)


def _json(url: str, target: Path, user_agent: str) -> dict[str, object]:
    if not target.exists():
        _download(url, target, user_agent)
    body = target.read_bytes()
    if body.startswith(b"\x1f\x8b"):
        body = gzip.decompress(body)
        target.write_bytes(body)
    return json.loads(body.decode("utf-8"))


def main() -> int:
    user_agent = os.environ.get(
        "SEC_USER_AGENT",
        "ForecastTest Industrials IFRS research contact@example.com",
    )
    ticker_payload = json.loads(TICKER_SOURCE.read_text(encoding="utf-8"))
    lookup = {
        str(row["ticker"]).upper(): str(row["cik_str"]).zfill(10)
        for row in ticker_payload.values()
    }
    companies: list[dict[str, object]] = []
    all_filings: list[dict[str, object]] = []
    for ticker, subindustry in TICKERS.items():
        cik = lookup[ticker]
        company_root = ROOT / ticker.lower()
        submissions_path = company_root / "submissions.json"
        facts_path = company_root / "companyfacts.json"
        submissions = _json(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            submissions_path,
            user_agent,
        )
        _json(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
            facts_path,
            user_agent,
        )
        recent = submissions["filings"]["recent"]
        filings: list[dict[str, object]] = []
        for index, form in enumerate(recent["form"]):
            filing_date = recent["filingDate"][index]
            if form not in FORMS or not START <= filing_date <= CUTOFF:
                continue
            accession = recent["accessionNumber"][index]
            document = recent["primaryDocument"][index]
            source_url = (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                f"{accession.replace('-', '')}/{document}"
            )
            target = company_root / form / f"{filing_date}_{accession}_{document}"
            if not target.exists():
                _download(source_url, target, user_agent)
            row = {
                "subindustry_code": subindustry,
                "ticker": ticker,
                "cik": cik,
                "form": form,
                "filing_date": filing_date,
                "report_date": recent["reportDate"][index],
                "accession_number": accession,
                "primary_document": document,
                "source_url": source_url,
                "local_path": target.relative_to(PROJECT_ROOT).as_posix(),
                "sha256": _sha(target),
                "size_bytes": target.stat().st_size,
                "pdf_parsing_used": False,
            }
            filings.append(row)
            all_filings.append(row)
        manifest = {
            "subindustry_code": subindustry,
            "ticker": ticker,
            "cik": cik,
            "forms": sorted(FORMS),
            "start": START,
            "cutoff": CUTOFF,
            "submissions_path": submissions_path.relative_to(PROJECT_ROOT).as_posix(),
            "submissions_sha256": _sha(submissions_path),
            "companyfacts_path": facts_path.relative_to(PROJECT_ROOT).as_posix(),
            "companyfacts_sha256": _sha(facts_path),
            "filings": filings,
        }
        manifest_path = company_root / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        companies.append(
            {
                "subindustry_code": subindustry,
                "ticker": ticker,
                "cik": cik,
                "form_20f_count": sum(row["form"] == "20-F" for row in filings),
                "form_6k_count": sum(row["form"] == "6-K" for row in filings),
                "filing_count": len(filings),
                "manifest_path": manifest_path.relative_to(PROJECT_ROOT).as_posix(),
                "manifest_sha256": _sha(manifest_path),
                "status": "READY" if filings else "FAIL_CLOSED_NO_FILINGS",
            }
        )
        print(ticker, len(filings), flush=True)
    catalog = {
        "dataset": "INDUSTRIALS_V8_IFRS_20F_6K",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "start": START,
        "cutoff": CUTOFF,
        "companies": companies,
        "filings": all_filings,
    }
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "catalog_manifest.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"companies": companies, "filings": len(all_filings)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
