from __future__ import annotations

import json
from pathlib import Path

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.aerospace_defense.hii.selection import (
    select_third_company,
    selection_metadata,
)


ARCANA_IR = Path("D:/Programming/python_example/Arcana/data-lake/bronze/sec/fillings/ir")
OUTPUT = PROJECT_ROOT / "output/industrials_v5_hii_third_company_research"


def main() -> int:
    audit, selected = select_third_company(
        PROJECT_ROOT / "configs/industrials_v5_ad_third_company_candidates.csv",
        ARCANA_IR,
    )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    audit.to_csv(OUTPUT / "ad_third_company_selection_audit.csv", index=False)
    selected.to_csv(OUTPUT / "ad_third_company_selected.csv", index=False)
    payload = selection_metadata(selected)
    (OUTPUT / "ad_third_company_selection_metadata.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if selected.iloc[0]["ticker"] == "HII" else 2


if __name__ == "__main__":
    raise SystemExit(main())
