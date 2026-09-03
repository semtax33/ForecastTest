from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import time
from urllib.request import Request, urlopen

from equity_platform.paths import PROJECT_ROOT


CIK_PADDED = "0000026172"
CIK_ARCHIVE = "26172"
START_DATE = "2021-01-01"
CUTOFF_DATE = "2026-09-03"
FORMS = {"10-K", "10-Q"}
ROOT = PROJECT_ROOT / "data-lake/bronze/industrials/v2/sec/cmi"
SUBMISSIONS_URL = f"https://data.sec.gov/submissions/CIK{CIK_PADDED}.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, target: Path, user_agent: str) -> None:
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=60) as response:
        payload = response.read()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    time.sleep(0.15)


def main() -> int:
    user_agent = os.environ.get(
        "SEC_USER_AGENT",
        "ForecastTest CMI portability research contact@example.com",
    )
    submissions_path = ROOT / "submissions" / f"CIK{CIK_PADDED}.json"
    _download(SUBMISSIONS_URL, submissions_path, user_agent)
    payload = json.loads(submissions_path.read_text(encoding="utf-8"))
    recent = payload["filings"]["recent"]
    rows: list[dict[str, object]] = []
    for index, form in enumerate(recent["form"]):
        filing_date = recent["filingDate"][index]
        if form not in FORMS or not (START_DATE <= filing_date <= CUTOFF_DATE):
            continue
        accession = recent["accessionNumber"][index]
        document = recent["primaryDocument"][index]
        report_date = recent["reportDate"][index]
        source_url = (
            f"https://www.sec.gov/Archives/edgar/data/{CIK_ARCHIVE}/"
            f"{accession.replace('-', '')}/{document}"
        )
        local_path = ROOT / form / f"{filing_date}_{accession}_{document}"
        if not local_path.exists():
            _download(source_url, local_path, user_agent)
        rows.append(
            {
                "ticker": "CMI",
                "cik": CIK_PADDED,
                "form": form,
                "filing_date": filing_date,
                "report_date": report_date,
                "accession_number": accession,
                "primary_document": document,
                "source_url": source_url,
                "local_path": local_path.relative_to(PROJECT_ROOT).as_posix(),
                "sha256": _sha256(local_path),
                "size_bytes": local_path.stat().st_size,
                "content_type": "text/html",
                "pdf_parsing_used": False,
            }
        )
    rows.sort(key=lambda row: (str(row["filing_date"]), str(row["form"])))
    manifest = {
        "dataset": "CMI_PERIODIC_FILINGS_INDUSTRIALS_V2",
        "source_authority": "SEC_EDGAR",
        "submissions_url": SUBMISSIONS_URL,
        "start_date": START_DATE,
        "cutoff_date": CUTOFF_DATE,
        "forms": sorted(FORMS),
        "filing_count": len(rows),
        "form_counts": {
            form: sum(row["form"] == form for row in rows)
            for form in sorted(FORMS)
        },
        "pdf_parsing_used": False,
        "files": rows,
    }
    target = ROOT / "manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "manifest": str(target),
                "filing_count": len(rows),
                "form_counts": manifest["form_counts"],
            },
            indent=2,
        )
    )
    return 0 if len(rows) == 23 else 2


if __name__ == "__main__":
    raise SystemExit(main())
