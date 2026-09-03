# ============================================================
# ENERGY REVENUE NOWCAST V3
#
# Base:
#   ./data-lake/energy_v2_1_macro.csv
#   ./data-lake/energy_v2_1_panel.csv
#
# Adds:
#   SEC filing-level XBRL KPI extraction
#
# KPI:
#   - Total production
#   - Oil production
#   - NGL production
#   - Natural gas production
#   - Realized oil price
#   - Realized gas price
#
# Model:
#
#   Structural Revenue YoY
#       =
#       Estimated Realized Price YoY
#       +
#       Company Production YoY
#
#   Final V3
#       =
#       Structural Baseline
#       +
#       Ridge-predicted residual
#
# Required ENV:
#   EDGAR_IDENTITY
#
# Optional ENV:
#   DATA_LAKE_DIR=./data-lake
#   TICKERS=COP,EOG,FANG,DVN
#   AS_OF_DATE=2026-08-31
#   REFRESH_KPI=0
#   KPI_LOOKBACK_FILINGS=28
#   MIN_FEATURE_COVERAGE=0.40
#
# ============================================================


import os
import re
import json
import warnings
from pathlib import Path
from datetime import date

import numpy as np
import pandas as pd

from edgar import Company, set_identity

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
)


warnings.filterwarnings("ignore")


# ============================================================
# 0. CONFIG
# ============================================================

EDGAR_IDENTITY = os.getenv(
    "EDGAR_IDENTITY"
)

DATA_LAKE_DIR = Path(
    os.getenv(
        "DATA_LAKE_DIR",
        "./data-lake",
    )
)

TICKERS = [
    x.strip().upper()
    for x in os.getenv(
        "TICKERS",
        "COP,EOG,FANG,DVN",
    ).split(",")
    if x.strip()
]


AS_OF_DATE_ENV = os.getenv(
    "AS_OF_DATE"
)


REFRESH_KPI = (
    os.getenv(
        "REFRESH_KPI",
        "0",
    )
    .strip()
    .lower()
    in {
        "1",
        "true",
        "yes",
        "y",
    }
)


KPI_LOOKBACK_FILINGS = int(
    os.getenv(
        "KPI_LOOKBACK_FILINGS",
        "28",
    )
)


MIN_FEATURE_COVERAGE = float(
    os.getenv(
        "MIN_FEATURE_COVERAGE",
        "0.40",
    )
)


TEST_QUARTERS = int(
    os.getenv(
        "TEST_QUARTERS",
        "12",
    )
)


MIN_TRAIN_QUARTERS = int(
    os.getenv(
        "MIN_TRAIN_QUARTERS",
        "16",
    )
)


PREDICTION_MIN = float(
    os.getenv(
        "PREDICTION_MIN",
        "-100",
    )
)


PREDICTION_MAX = float(
    os.getenv(
        "PREDICTION_MAX",
        "150",
    )
)


RIDGE_ALPHAS = [
    0.1,
    0.3,
    1.0,
    3.0,
    10.0,
    30.0,
    100.0,
    300.0,
]


# ============================================================
# 1. BASIC CONFIG
# ============================================================

if not EDGAR_IDENTITY:

    raise ValueError(
        "EDGAR_IDENTITY 환경변수를 설정해줘.\n"
        "예: export EDGAR_IDENTITY="
        "\"Your Name you@example.com\""
    )


def resolve_as_of():

    if AS_OF_DATE_ENV:

        return (
            pd.Timestamp(
                AS_OF_DATE_ENV
            )
            .normalize()
        )

    return pd.Timestamp(
        date.today()
    )


AS_OF = resolve_as_of()


DATA_LAKE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


set_identity(
    EDGAR_IDENTITY
)


def lake_path(
    filename
):

    return (
        DATA_LAKE_DIR
        / filename
    )


print(
    "=" * 90
)

print(
    "ENERGY REVENUE NOWCAST V3"
)

print(
    "=" * 90
)

print(
    "AS OF      :",
    AS_OF.date()
)

print(
    "TICKERS    :",
    TICKERS
)

print(
    "DATA LAKE  :",
    DATA_LAKE_DIR.resolve()
)

print(
    "REFRESH KPI:",
    REFRESH_KPI
)


# ============================================================
# 2. LOAD V2.1 BASE
# ============================================================

MACRO_FILE = lake_path(
    "energy_v2_1_macro.csv"
)

PANEL_FILE = lake_path(
    "energy_v2_1_panel.csv"
)


if not MACRO_FILE.exists():

    raise FileNotFoundError(
        f"{MACRO_FILE} 없음.\n"
        "먼저 V2.1을 실행해줘."
    )


if not PANEL_FILE.exists():

    raise FileNotFoundError(
        f"{PANEL_FILE} 없음.\n"
        "먼저 V2.1을 실행해줘."
    )


macro = pd.read_csv(
    MACRO_FILE,
    index_col=0,
)


macro.index = pd.PeriodIndex(
    macro.index.astype(str),
    freq="Q",
)


panel_v21 = pd.read_csv(
    PANEL_FILE
)


panel_v21["quarter"] = (
    pd.PeriodIndex(
        panel_v21[
            "quarter"
        ].astype(str),
        freq="Q",
    )
)


panel_v21 = (
    panel_v21[
        panel_v21[
            "ticker"
        ].isin(
            TICKERS
        )
    ]
    .copy()
)


print(
    "\nV2.1 macro:",
    macro.shape
)

print(
    "V2.1 panel:",
    panel_v21.shape
)


# ============================================================
# 3. HELPERS
# ============================================================

def numeric(
    value
):

    if pd.isna(value):

        return np.nan

    if isinstance(
        value,
        (
            int,
            float,
            np.integer,
            np.floating,
        )
    ):

        return float(
            value
        )

    text = (
        str(value)
        .replace(",", "")
        .replace("$", "")
        .strip()
    )

    try:

        return float(
            text
        )

    except Exception:

        return np.nan


def log_growth(
    series,
    periods=4,
):

    s = pd.to_numeric(
        series,
        errors="coerce",
    )


    lagged = (
        s.shift(
            periods
        )
    )


    result = pd.Series(
        np.nan,
        index=s.index,
        dtype=float,
    )


    valid = (
        (s > 0)
        &
        (lagged > 0)
    )


    result.loc[
        valid
    ] = (
        np.log(
            s.loc[valid]
            /
            lagged.loc[valid]
        )
        * 100
    )


    return result


def normalize_text(
    value
):

    if pd.isna(value):

        return ""

    text = str(
        value
    ).lower()

    text = re.sub(
        r"[_:\-/]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return (
        text.strip()
    )


# ============================================================
# 4. KPI DEFINITIONS
#
# Each required_group:
# at least one regex must match.
#
# ============================================================

KPI_SPECS = {

    "total_production": {

        "required_groups": [

            [
                r"production",
            ],

            [
                r"\bboe\b",
                r"boed",
                r"mboe",
                r"barrel.*oil.*equivalent",
                r"equivalent.*production",
            ],
        ],

        "positive": [
            r"total",
            r"daily",
            r"average",
        ],

        "negative": [
            r"reserve",
            r"proved",
            r"undeveloped",
            r"inventory",
            r"forecast",
            r"guidance",
            r"cost",
            r"expense",
        ],

        "unit_regex": (
            r"boe|"
            r"barrel.*equivalent"
        ),
    },


    "oil_production": {

        "required_groups": [

            [
                r"production",
                r"produced",
            ],

            [
                r"\boil\b",
                r"crude",
                r"condensate",
            ],
        ],

        "positive": [
            r"daily",
            r"average",
            r"volume",
        ],

        "negative": [
            r"natural gas",
            r"\bngl\b",
            r"equivalent",
            r"reserve",
            r"proved",
            r"revenue",
            r"price",
            r"cost",
        ],

        "unit_regex": (
            r"bbl|"
            r"barrel"
        ),
    },


    "ngl_production": {

        "required_groups": [

            [
                r"production",
                r"produced",
            ],

            [
                r"\bngl\b",
                r"natural gas liquid",
            ],
        ],

        "positive": [
            r"daily",
            r"average",
            r"volume",
        ],

        "negative": [
            r"reserve",
            r"revenue",
            r"price",
            r"cost",
        ],

        "unit_regex": (
            r"bbl|"
            r"barrel"
        ),
    },


    "gas_production": {

        "required_groups": [

            [
                r"production",
                r"produced",
            ],

            [
                r"natural gas",
                r"\bgas\b",
            ],
        ],

        "positive": [
            r"daily",
            r"average",
            r"volume",
        ],

        "negative": [
            r"\bngl\b",
            r"liquid",
            r"\boil\b",
            r"equivalent",
            r"reserve",
            r"price",
            r"revenue",
        ],

        "unit_regex": (
            r"mcf|"
            r"mmcf|"
            r"bcf"
        ),
    },


    "realized_oil_price": {

        "required_groups": [

            [
                r"\boil\b",
                r"crude",
            ],

            [
                r"price",
                r"realized",
                r"realisation",
                r"realization",
            ],
        ],

        "positive": [
            r"average",
            r"sales",
            r"realized",
            r"excluding.*derivative",
            r"before.*hedg",
        ],

        "negative": [
            r"production",
            r"volume",
            r"reserve",
            r"derivative gain",
            r"derivative loss",
            r"settlement",
        ],

        "unit_regex": (
            r"usd.*bbl|"
            r"dollar.*barrel|"
            r"per.*barrel|"
            r"/bbl"
        ),
    },


    "realized_gas_price": {

        "required_groups": [

            [
                r"natural gas",
                r"\bgas\b",
            ],

            [
                r"price",
                r"realized",
                r"realisation",
                r"realization",
            ],
        ],

        "positive": [
            r"average",
            r"sales",
            r"realized",
            r"excluding.*derivative",
            r"before.*hedg",
        ],

        "negative": [
            r"\bngl\b",
            r"production",
            r"volume",
            r"reserve",
            r"derivative gain",
            r"derivative loss",
            r"settlement",
        ],

        "unit_regex": (
            r"usd.*mcf|"
            r"dollar.*mcf|"
            r"per.*mcf|"
            r"/mcf|"
            r"mmbtu"
        ),
    },
}


# ============================================================
# 5. KPI OVERRIDE FILE
#
# If automatic concept selection is wrong:
#
# edit:
# ./data-lake/energy_v3_kpi_overrides.json
#
# Example:
#
# {
#   "COP": {
#       "total_production": "cop:Production..."
#   }
# }
#
# ============================================================

OVERRIDE_FILE = lake_path(
    "energy_v3_kpi_overrides.json"
)


if not OVERRIDE_FILE.exists():

    empty_override = {
        ticker: {
            kpi: None
            for kpi in (
                KPI_SPECS.keys()
            )
        }
        for ticker in TICKERS
    }


    with open(
        OVERRIDE_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            empty_override,
            f,
            indent=2,
            ensure_ascii=False,
        )


with open(
    OVERRIDE_FILE,
    "r",
    encoding="utf-8",
) as f:

    KPI_OVERRIDES = (
        json.load(
            f
        )
    )


# ============================================================
# 6. FILING METADATA
# ============================================================

def get_filing_report_date(
    filing
):

    candidates = [

        getattr(
            filing,
            "report_date",
            None,
        ),

        getattr(
            filing,
            "reportDate",
            None,
        ),

        getattr(
            filing,
            "period_of_report",
            None,
        ),
    ]


    for value in candidates:

        if value is None:

            continue

        dt = pd.to_datetime(
            value,
            errors="coerce",
        )

        if pd.notna(dt):

            return dt


    return pd.NaT


# ============================================================
# 7. XBRL FACT DATAFRAME
# ============================================================

def get_xbrl_facts_dataframe(
    filing
):

    try:

        xbrl = (
            filing.xbrl()
        )

    except Exception:

        return pd.DataFrame()


    if xbrl is None:

        return pd.DataFrame()


    try:

        df = (
            xbrl
            .facts
            .query()
            .to_dataframe()
        )

    except Exception:

        try:

            df = (
                xbrl
                .facts
                .to_dataframe()
            )

        except Exception:

            return pd.DataFrame()


    if (
        df is None
        or df.empty
    ):

        return pd.DataFrame()


    return (
        df.copy()
    )


# ============================================================
# 8. PREPARE FACT DATA
# ============================================================

def prepare_fact_dataframe(
    df,
    filing,
):

    if df.empty:

        return df


    result = (
        df.copy()
    )


    if (
        "numeric_value"
        not in result.columns
    ):

        if "value" in result.columns:

            result[
                "numeric_value"
            ] = (
                result[
                    "value"
                ]
                .apply(
                    numeric
                )
            )

        else:

            return pd.DataFrame()


    result[
        "numeric_value"
    ] = (
        pd.to_numeric(
            result[
                "numeric_value"
            ],
            errors="coerce",
        )
    )


    for col in [
        "period_start",
        "period_end",
    ]:

        if col in result.columns:

            result[col] = (
                pd.to_datetime(
                    result[col],
                    errors="coerce",
                )
            )

        else:

            result[col] = (
                pd.NaT
            )


    report_date = (
        get_filing_report_date(
            filing
        )
    )


    result[
        "_report_date"
    ] = (
        report_date
    )


    result[
        "_period_days"
    ] = (
        (
            result[
                "period_end"
            ]
            -
            result[
                "period_start"
            ]
        )
        .dt.days
        + 1
    )


    result[
        "_end_distance"
    ] = (
        (
            result[
                "period_end"
            ]
            -
            report_date
        )
        .abs()
        .dt.days
    )


    label = (
        result[
            "label"
        ]
        if "label" in result.columns
        else ""
    )


    concept = (
        result[
            "concept"
        ]
        if "concept" in result.columns
        else ""
    )


    unit = (
        result[
            "unit"
        ]
        if "unit" in result.columns
        else ""
    )


    if isinstance(
        label,
        pd.Series,
    ):

        label_text = (
            label.fillna("")
            .astype(str)
        )

    else:

        label_text = pd.Series(
            "",
            index=result.index,
        )


    if isinstance(
        concept,
        pd.Series,
    ):

        concept_text = (
            concept.fillna("")
            .astype(str)
        )

    else:

        concept_text = pd.Series(
            "",
            index=result.index,
        )


    if isinstance(
        unit,
        pd.Series,
    ):

        unit_text = (
            unit.fillna("")
            .astype(str)
        )

    else:

        unit_text = pd.Series(
            "",
            index=result.index,
        )


    result[
        "_search_text"
    ] = (

        label_text
        + " "
        + concept_text
        + " "
        + unit_text

    ).map(
        normalize_text
    )


    result[
        "_label_text"
    ] = (
        label_text.map(
            normalize_text
        )
    )


    result[
        "_concept_text"
    ] = (
        concept_text.map(
            normalize_text
        )
    )


    result[
        "_unit_text"
    ] = (
        unit_text.map(
            normalize_text
        )
    )


    # --------------------------------------------------------
    # Prefer quarterly duration facts
    # --------------------------------------------------------

    result = result[
        result[
            "numeric_value"
        ].notna()
    ]


    result = result[
        result[
            "_period_days"
        ]
        .between(
            60,
            120,
            inclusive="both",
        )
    ]


    # Current period from filing
    if pd.notna(
        report_date
    ):

        result = result[
            result[
                "_end_distance"
            ]
            <= 10
        ]


    return result


# ============================================================
# 9. SCORE KPI CANDIDATE
# ============================================================

def score_candidate(
    row,
    spec,
):

    text = (
        row[
            "_search_text"
        ]
    )

    score = 0.0


    # --------------------------------------------------------
    # Required pattern groups
    # --------------------------------------------------------

    for group in (
        spec[
            "required_groups"
        ]
    ):

        matched = any(
            re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            )
            for pattern in group
        )


        if not matched:

            return None


        score += 35.0


    # --------------------------------------------------------
    # Positive clues
    # --------------------------------------------------------

    for pattern in (
        spec.get(
            "positive",
            []
        )
    ):

        if re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):

            score += 8.0


    # --------------------------------------------------------
    # Negative clues
    # --------------------------------------------------------

    for pattern in (
        spec.get(
            "negative",
            []
        )
    ):

        if re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):

            score -= 30.0


    # --------------------------------------------------------
    # Unit clue
    # --------------------------------------------------------

    unit_regex = (
        spec.get(
            "unit_regex"
        )
    )


    if unit_regex:

        if re.search(
            unit_regex,
            text,
            flags=re.IGNORECASE,
        ):

            score += 25.0


    # --------------------------------------------------------
    # Quarter length quality
    # --------------------------------------------------------

    days = (
        row[
            "_period_days"
        ]
    )


    if (
        pd.notna(days)
        and
        75 <= days <= 100
    ):

        score += 15.0


    # --------------------------------------------------------
    # Period end matches report
    # --------------------------------------------------------

    distance = (
        row[
            "_end_distance"
        ]
    )


    if (
        pd.notna(distance)
        and
        distance <= 3
    ):

        score += 10.0


    # --------------------------------------------------------
    # Prefer non-dimensional / consolidated
    # --------------------------------------------------------

    dimension_cols = [
        c
        for c in row.index
        if str(c).startswith(
            "dim_"
        )
    ]


    if dimension_cols:

        dimensional = any(
            pd.notna(
                row[c]
            )
            and
            str(
                row[c]
            ).strip()
            not in {
                "",
                "nan",
                "None",
            }
            for c in dimension_cols
        )


        if dimensional:

            score -= 15.0

        else:

            score += 10.0


    return score


# ============================================================
# 10. COLLECT KPI CANDIDATES
# ============================================================

def collect_filing_candidates(
    ticker
):

    print(
        f"\n{'=' * 80}"
    )

    print(
        f"SEC KPI SCAN: {ticker}"
    )

    print(
        "=" * 80
    )


    company = Company(
        ticker
    )


    filings = (
        company.get_filings(
            form=[
                "10-Q",
                "10-K",
            ]
        )
    )


    start_date = (
        AS_OF
        -
        pd.DateOffset(
            years=10
        )
    )


    filings = filings.filter(
        filing_date=(
            f"{start_date.date()}:"
            f"{AS_OF.date()}"
        )
    )


    try:

        filings = (
            filings.head(
                KPI_LOOKBACK_FILINGS
            )
        )

    except Exception:

        pass


    records = []


    count = 0


    for filing in filings:

        if count >= (
            KPI_LOOKBACK_FILINGS
        ):

            break


        filing_date = (
            pd.to_datetime(
                getattr(
                    filing,
                    "filing_date",
                    None,
                ),
                errors="coerce",
            )
        )


        if (
            pd.notna(filing_date)
            and
            filing_date > AS_OF
        ):

            continue


        report_date = (
            get_filing_report_date(
                filing
            )
        )


        if pd.isna(
            report_date
        ):

            continue


        quarter = (
            report_date
            .to_period("Q")
        )


        print(
            f"  {filing.form} "
            f"{report_date.date()}"
        )


        raw = (
            get_xbrl_facts_dataframe(
                filing
            )
        )


        prepared = (
            prepare_fact_dataframe(
                raw,
                filing,
            )
        )


        if prepared.empty:

            continue


        accession = str(
            getattr(
                filing,
                "accession_number",
                "",
            )
        )


        for kpi_name, spec in (
            KPI_SPECS.items()
        ):

            for _, row in (
                prepared.iterrows()
            ):

                score = (
                    score_candidate(
                        row,
                        spec,
                    )
                )


                if score is None:

                    continue


                if score < 50:

                    continue


                records.append(
                    {
                        "ticker":
                            ticker,

                        "quarter":
                            quarter,

                        "kpi":
                            kpi_name,

                        "score":
                            score,

                        "concept":
                            row.get(
                                "concept",
                                "",
                            ),

                        "label":
                            row.get(
                                "label",
                                "",
                            ),

                        "unit":
                            row.get(
                                "unit",
                                "",
                            ),

                        "numeric_value":
                            row[
                                "numeric_value"
                            ],

                        "period_start":
                            row[
                                "period_start"
                            ],

                        "period_end":
                            row[
                                "period_end"
                            ],

                        "period_days":
                            row[
                                "_period_days"
                            ],

                        "filing_date":
                            filing_date,

                        "accession":
                            accession,
                    }
                )


        count += 1


    result = (
        pd.DataFrame(
            records
        )
    )


    candidate_file = lake_path(
        f"energy_v3_kpi_candidates_"
        f"{ticker}.csv"
    )


    result.to_csv(
        candidate_file,
        index=False,
    )


    print(
        f"  💾 {candidate_file}"
    )


    return result


# ============================================================
# 11. STANDARDIZE PRODUCTION RATE
# ============================================================

def standardize_production_value(
    kpi,
    value,
    label,
    unit,
    period_days,
):

    if pd.isna(value):

        return np.nan


    text = normalize_text(
        f"{label} {unit}"
    )


    days = (
        float(period_days)
        if pd.notna(
            period_days
        )
        else 91.0
    )


    value = float(
        value
    )


    # ========================================================
    # TOTAL BOE
    # output = MBOE / day
    # ========================================================

    if kpi == (
        "total_production"
    ):

        if re.search(
            r"mboe.*(?:day|d\b)|"
            r"mboed|"
            r"thousand.*boe.*day",
            text,
        ):

            return value


        if re.search(
            r"mmboe.*(?:day|d\b)|"
            r"million.*boe.*day",
            text,
        ):

            return (
                value
                * 1000
            )


        if re.search(
            r"boe.*(?:day|d\b)",
            text,
        ):

            return (
                value
                / 1000
            )


        if re.search(
            r"mmboe|"
            r"million.*boe",
            text,
        ):

            return (
                value
                * 1000
                / days
            )


        if re.search(
            r"mboe|"
            r"thousand.*boe",
            text,
        ):

            return (
                value
                / days
            )


        if re.search(
            r"\bboe\b",
            text,
        ):

            return (
                value
                / 1000
                / days
            )


        return np.nan


    # ========================================================
    # OIL / NGL
    # output = thousand barrels / day
    # ========================================================

    if kpi in {
        "oil_production",
        "ngl_production",
    }:

        if re.search(
            r"mbbl.*(?:day|d\b)|"
            r"mbopd|"
            r"thousand.*barrel.*day",
            text,
        ):

            return value


        if re.search(
            r"mmbbl.*(?:day|d\b)|"
            r"million.*barrel.*day",
            text,
        ):

            return (
                value
                * 1000
            )


        if re.search(
            r"bbl.*(?:day|d\b)|"
            r"barrel.*day",
            text,
        ):

            return (
                value
                / 1000
            )


        if re.search(
            r"mmbbl|"
            r"million.*barrel",
            text,
        ):

            return (
                value
                * 1000
                / days
            )


        if re.search(
            r"mbbl|"
            r"thousand.*barrel",
            text,
        ):

            return (
                value
                / days
            )


        if re.search(
            r"\bbbl\b|"
            r"\bbarrels?\b",
            text,
        ):

            return (
                value
                / 1000
                / days
            )


        return np.nan


    # ========================================================
    # GAS
    #
    # output = MMcf / day
    # ========================================================

    if kpi == (
        "gas_production"
    ):

        if re.search(
            r"mmcf.*(?:day|d\b)|"
            r"million.*cubic.*feet.*day",
            text,
        ):

            return value


        if re.search(
            r"bcf.*(?:day|d\b)|"
            r"billion.*cubic.*feet.*day",
            text,
        ):

            return (
                value
                * 1000
            )


        if re.search(
            r"mcf.*(?:day|d\b)",
            text,
        ):

            return (
                value
                / 1000
            )


        if re.search(
            r"\bbcf\b|"
            r"billion.*cubic.*feet",
            text,
        ):

            return (
                value
                * 1000
                / days
            )


        if re.search(
            r"\bmmcf\b|"
            r"million.*cubic.*feet",
            text,
        ):

            return (
                value
                / days
            )


        if re.search(
            r"\bmcf\b",
            text,
        ):

            return (
                value
                / 1000
                / days
            )


        return np.nan


    # Prices do not need
    # rate conversion

    return value


# ============================================================
# 12. SELECT BEST KPI FACTS
# ============================================================

def select_best_kpis(
    ticker,
    candidates
):

    if candidates.empty:

        return (
            pd.DataFrame(),
            pd.DataFrame(),
        )


    work = (
        candidates.copy()
    )


    work[
        "quarter"
    ] = (
        pd.PeriodIndex(
            work[
                "quarter"
            ].astype(str),
            freq="Q",
        )
    )


    # --------------------------------------------------------
    # Concept frequency bonus
    #
    # Encourages tag continuity.
    # --------------------------------------------------------

    frequency = (
        work.groupby(
            [
                "kpi",
                "concept",
            ]
        )[
            "quarter"
        ]
        .nunique()
        .rename(
            "concept_frequency"
        )
        .reset_index()
    )


    work = (
        work.merge(
            frequency,
            on=[
                "kpi",
                "concept",
            ],
            how="left",
        )
    )


    work[
        "final_score"
    ] = (
        work["score"]
        +
        np.minimum(
            work[
                "concept_frequency"
            ],
            8,
        )
        * 6
    )


    selected_rows = []


    for kpi in (
        KPI_SPECS.keys()
    ):

        subset = (
            work[
                work[
                    "kpi"
                ]
                == kpi
            ]
            .copy()
        )


        if subset.empty:

            continue


        override = (
            KPI_OVERRIDES
            .get(
                ticker,
                {}
            )
            .get(
                kpi
            )
        )


        if override:

            override_subset = (
                subset[
                    subset[
                        "concept"
                    ]
                    .astype(str)
                    .eq(
                        override
                    )
                ]
            )


            if not (
                override_subset.empty
            ):

                subset = (
                    override_subset
                )


        for quarter, quarter_df in (
            subset.groupby(
                "quarter"
            )
        ):

            best = (
                quarter_df
                .sort_values(
                    [
                        "final_score",
                        "filing_date",
                    ],
                    ascending=[
                        False,
                        False,
                    ],
                )
                .iloc[0]
                .copy()
            )


            best[
                "quarter"
            ] = quarter


            selected_rows.append(
                best
            )


    selected = (
        pd.DataFrame(
            selected_rows
        )
    )


    if selected.empty:

        return (
            pd.DataFrame(),
            pd.DataFrame(),
        )


    # ========================================================
    # Convert to standard units
    # ========================================================

    selected[
        "standard_value"
    ] = selected.apply(
        lambda row:
            standardize_production_value(

                row["kpi"],

                row[
                    "numeric_value"
                ],

                row.get(
                    "label",
                    "",
                ),

                row.get(
                    "unit",
                    "",
                ),

                row.get(
                    "period_days",
                    91,
                ),
            ),
        axis=1,
    )


    # --------------------------------------------------------
    # Price:
    # numeric_value itself
    # --------------------------------------------------------

    price_mask = (
        selected[
            "kpi"
        ]
        .isin(
            [
                "realized_oil_price",
                "realized_gas_price",
            ]
        )
    )


    selected.loc[
        price_mask,
        "standard_value"
    ] = (
        selected.loc[
            price_mask,
            "numeric_value"
        ]
    )


    selected_file = lake_path(
        f"energy_v3_kpi_selected_"
        f"{ticker}.csv"
    )


    selected.to_csv(
        selected_file,
        index=False,
    )


    print(
        f"  💾 {selected_file}"
    )


    # ========================================================
    # Wide quarterly table
    # ========================================================

    raw_wide = (
        selected
        .pivot_table(
            index="quarter",
            columns="kpi",
            values="numeric_value",
            aggfunc="last",
        )
    )


    standard_wide = (
        selected
        .pivot_table(
            index="quarter",
            columns="kpi",
            values="standard_value",
            aggfunc="last",
        )
    )


    output = pd.DataFrame(
        index=(
            raw_wide.index
            .union(
                standard_wide.index
            )
            .sort_values()
        )
    )


    for col in (
        KPI_SPECS.keys()
    ):

        if col in (
            raw_wide.columns
        ):

            output[
                f"{col}_raw"
            ] = (
                raw_wide[col]
            )


        if col in (
            standard_wide.columns
        ):

            output[
                col
            ] = (
                standard_wide[col]
            )


    return (
        output,
        selected,
    )


# ============================================================
# 13. LOAD OR BUILD KPI
# ============================================================

def get_company_kpi(
    ticker
):

    cache_file = lake_path(
        f"energy_v3_kpi_"
        f"{ticker}.csv"
    )


    if (
        cache_file.exists()
        and
        not REFRESH_KPI
    ):

        print(
            f"\nLoading cached KPI: "
            f"{ticker}"
        )


        df = pd.read_csv(
            cache_file,
            index_col=0,
        )


        df.index = (
            pd.PeriodIndex(
                df.index.astype(str),
                freq="Q",
            )
        )


        return df


    candidates = (
        collect_filing_candidates(
            ticker
        )
    )


    kpi, _ = (
        select_best_kpis(
            ticker,
            candidates,
        )
    )


    kpi.to_csv(
        cache_file
    )


    print(
        f"  💾 {cache_file}"
    )


    return kpi


# ============================================================
# 14. BUILD ALL KPI DATA
# ============================================================

kpi_frames = {}


selection_summary = []


for ticker in TICKERS:

    try:

        kpi_frames[
            ticker
        ] = (
            get_company_kpi(
                ticker
            )
        )


    except Exception as exc:

        print(
            f"\n❌ KPI ERROR "
            f"{ticker}: {exc}"
        )


        kpi_frames[
            ticker
        ] = pd.DataFrame()


# ============================================================
# 15. KPI COVERAGE
# ============================================================

print(
    "\n"
    + "=" * 90
)

print(
    "KPI COVERAGE"
)

print(
    "=" * 90
)


for ticker, df in (
    kpi_frames.items()
):

    print(
        f"\n{ticker}"
    )


    if df.empty:

        print(
            "  NO KPI DATA"
        )

        continue


    for col in [

        "total_production",
        "oil_production",
        "ngl_production",
        "gas_production",
        "realized_oil_price",
        "realized_gas_price",

    ]:

        if col in (
            df.columns
        ):

            count = (
                df[col]
                .notna()
                .sum()
            )

        else:

            count = 0


        print(
            f"  {col:<25}: "
            f"{count}"
        )


# ============================================================
# 16. KPI FEATURE ENGINEERING
# ============================================================

def build_company_kpi_features(
    ticker,
    company_panel,
    kpi
):

    quarters = (
        company_panel[
            "quarter"
        ]
    )


    index = (
        pd.PeriodIndex(
            quarters,
            freq="Q",
        )
    )


    result = (
        company_panel.copy()
    )


    result.index = (
        index
    )


    if kpi.empty:

        for col in [

            "company_total_prod",
            "company_oil_prod",
            "company_ngl_prod",
            "company_gas_prod",

            "realized_oil_price",
            "realized_gas_price",

        ]:

            result[col] = (
                np.nan
            )

    else:

        # ----------------------------------------------------
        # Reindex quarterly
        #
        # ffill(limit=1):
        # if a 10-K lacks standalone Q4 KPI,
        # use most recent quarter for one quarter only.
        # ----------------------------------------------------

        kpi = (
            kpi.reindex(
                index
            )
        )


        def get_col(
            name
        ):

            if name in (
                kpi.columns
            ):

                return (
                    kpi[name]
                    .ffill(
                        limit=1
                    )
                )

            return pd.Series(
                np.nan,
                index=index,
            )


        result[
            "company_total_prod"
        ] = get_col(
            "total_production"
        )


        result[
            "company_oil_prod"
        ] = get_col(
            "oil_production"
        )


        result[
            "company_ngl_prod"
        ] = get_col(
            "ngl_production"
        )


        result[
            "company_gas_prod"
        ] = get_col(
            "gas_production"
        )


        result[
            "realized_oil_price"
        ] = get_col(
            "realized_oil_price"
        )


        result[
            "realized_gas_price"
        ] = get_col(
            "realized_gas_price"
        )


    # ========================================================
    # Total production fallback
    #
    # MBOE/d
    #
    # Gas:
    # 1 BOE ~= 6 Mcf
    #
    # MMcf/d / 6
    # = MBOE/d
    # ========================================================

    component_total = (

        result[
            "company_oil_prod"
        ].fillna(0)

        +

        result[
            "company_ngl_prod"
        ].fillna(0)

        +

        (
            result[
                "company_gas_prod"
            ].fillna(0)
            /
            6.0
        )
    )


    component_count = (

        result[
            [
                "company_oil_prod",
                "company_gas_prod",
            ]
        ]
        .notna()
        .sum(
            axis=1
        )
    )


    component_total.loc[
        component_count < 2
    ] = np.nan


    result[
        "company_total_prod"
    ] = (
        result[
            "company_total_prod"
        ]
        .combine_first(
            component_total
        )
    )


    # ========================================================
    # Production YoY
    # ========================================================

    result[
        "company_total_prod_yoy"
    ] = log_growth(
        result[
            "company_total_prod"
        ],
        4,
    )


    result[
        "company_oil_prod_yoy"
    ] = log_growth(
        result[
            "company_oil_prod"
        ],
        4,
    )


    result[
        "company_gas_prod_yoy"
    ] = log_growth(
        result[
            "company_gas_prod"
        ],
        4,
    )


    # ========================================================
    # Macro levels
    # ========================================================

    macro_aligned = (
        macro.reindex(
            index
        )
    )


    result[
        "wti_level"
    ] = (
        macro_aligned[
            "wti"
        ]
        if "wti"
        in macro_aligned.columns
        else np.nan
    )


    result[
        "henry_level"
    ] = (
        macro_aligned[
            "henry_hub"
        ]
        if "henry_hub"
        in macro_aligned.columns
        else np.nan
    )


    # ========================================================
    # Realization ratio
    #
    # Company realized price / benchmark
    #
    # Use prior quarter ratio to estimate
    # CURRENT quarter realized price.
    # ========================================================

    result[
        "oil_realization_ratio"
    ] = (
        result[
            "realized_oil_price"
        ]
        /
        result[
            "wti_level"
        ]
    )


    result[
        "gas_realization_ratio"
    ] = (
        result[
            "realized_gas_price"
        ]
        /
        result[
            "henry_level"
        ]
    )


    result[
        "oil_realization_ratio"
    ] = (
        result[
            "oil_realization_ratio"
        ]
        .replace(
            [
                np.inf,
                -np.inf,
            ],
            np.nan,
        )
        .clip(
            0.2,
            2.0,
        )
    )


    result[
        "gas_realization_ratio"
    ] = (
        result[
            "gas_realization_ratio"
        ]
        .replace(
            [
                np.inf,
                -np.inf,
            ],
            np.nan,
        )
        .clip(
            0.1,
            3.0,
        )
    )


    # ========================================================
    # Estimated current realized prices
    # ========================================================

    result[
        "est_realized_oil_price"
    ] = (

        result[
            "wti_level"
        ]

        *

        result[
            "oil_realization_ratio"
        ]
        .shift(1)
    )


    result[
        "est_realized_gas_price"
    ] = (

        result[
            "henry_level"
        ]

        *

        result[
            "gas_realization_ratio"
        ]
        .shift(1)
    )


    # ========================================================
    # Estimated realized-price YoY
    #
    # Current estimated price
    # versus
    # actual same quarter previous year
    # ========================================================

    previous_year_oil = (
        result[
            "realized_oil_price"
        ]
        .shift(4)
    )


    valid = (
        (
            result[
                "est_realized_oil_price"
            ]
            > 0
        )
        &
        (
            previous_year_oil
            > 0
        )
    )


    result[
        "est_realized_oil_yoy"
    ] = np.nan


    result.loc[
        valid,
        "est_realized_oil_yoy"
    ] = (
        np.log(
            result.loc[
                valid,
                "est_realized_oil_price"
            ]
            /
            previous_year_oil.loc[
                valid
            ]
        )
        * 100
    )


    previous_year_gas = (
        result[
            "realized_gas_price"
        ]
        .shift(4)
    )


    valid = (
        (
            result[
                "est_realized_gas_price"
            ]
            > 0
        )
        &
        (
            previous_year_gas
            > 0
        )
    )


    result[
        "est_realized_gas_yoy"
    ] = np.nan


    result.loc[
        valid,
        "est_realized_gas_yoy"
    ] = (
        np.log(
            result.loc[
                valid,
                "est_realized_gas_price"
            ]
            /
            previous_year_gas.loc[
                valid
            ]
        )
        * 100
    )


    # ========================================================
    # If company price KPI is missing,
    # fall back to benchmark YoY.
    # ========================================================

    result[
        "est_realized_oil_yoy"
    ] = (
        result[
            "est_realized_oil_yoy"
        ]
        .combine_first(
            result[
                "wti_yoy"
            ]
        )
    )


    result[
        "est_realized_gas_yoy"
    ] = (
        result[
            "est_realized_gas_yoy"
        ]
        .combine_first(
            result[
                "henry_yoy"
            ]
        )
    )


    # ========================================================
    # Product mix
    #
    # Previous-quarter production mix
    # is known at nowcast time.
    # ========================================================

    gas_boe = (
        result[
            "company_gas_prod"
        ]
        /
        6.0
    )


    denominator = (
        result[
            "company_total_prod"
        ]
    )


    result[
        "gas_boe_share"
    ] = (
        gas_boe
        /
        denominator
    )


    result[
        "gas_boe_share"
    ] = (
        result[
            "gas_boe_share"
        ]
        .replace(
            [
                np.inf,
                -np.inf,
            ],
            np.nan,
        )
        .clip(
            0,
            1,
        )
    )


    # Prior-quarter product mix

    result[
        "gas_boe_share_l1"
    ] = (
        result[
            "gas_boe_share"
        ]
        .shift(1)
    )


    # Company historical median fallback

    median_gas_share = (
        result[
            "gas_boe_share"
        ]
        .median(
            skipna=True
        )
    )


    if pd.isna(
        median_gas_share
    ):

        median_gas_share = 0.30


    result[
        "gas_boe_share_l1"
    ] = (
        result[
            "gas_boe_share_l1"
        ]
        .fillna(
            median_gas_share
        )
    )


    # ========================================================
    # Weighted realized-price growth
    #
    # NGL is treated as oil-like.
    # ========================================================

    result[
        "company_price_mix_yoy"
    ] = (

        (
            1.0
            -
            result[
                "gas_boe_share_l1"
            ]
        )
        *
        result[
            "est_realized_oil_yoy"
        ]

        +

        result[
            "gas_boe_share_l1"
        ]
        *
        result[
            "est_realized_gas_yoy"
        ]
    )


    # ========================================================
    # Production growth known at target time:
    #
    # previous quarter's YoY production growth
    # ========================================================

    result[
        "company_total_prod_yoy_l1"
    ] = (
        result[
            "company_total_prod_yoy"
        ]
        .shift(1)
        .clip(
            -60,
            100,
        )
    )


    result[
        "company_oil_prod_yoy_l1"
    ] = (
        result[
            "company_oil_prod_yoy"
        ]
        .shift(1)
        .clip(
            -60,
            100,
        )
    )


    result[
        "company_gas_prod_yoy_l1"
    ] = (
        result[
            "company_gas_prod_yoy"
        ]
        .shift(1)
        .clip(
            -60,
            100,
        )
    )


    # ========================================================
    # If company production missing:
    #
    # fall back to industry production
    # ========================================================

    industry_volume_proxy = (

        0.65
        *
        result[
            "crude_prod_yoy_l1"
        ]

        +

        0.35
        *
        result[
            "gas_prod_yoy_l1"
        ]
    )


    result[
        "company_volume_yoy_proxy"
    ] = (
        result[
            "company_total_prod_yoy_l1"
        ]
        .combine_first(
            industry_volume_proxy
        )
    )


    # ========================================================
    # ★ V3 Structural Revenue Baseline
    #
    # in log-growth:
    #
    # log Revenue growth
    # ≈
    # log Price growth
    # +
    # log Volume growth
    # ========================================================

    result[
        "structural_revenue_yoy"
    ] = (

        result[
            "company_price_mix_yoy"
        ]

        +

        result[
            "company_volume_yoy_proxy"
        ]
    )


    result[
        "structural_revenue_yoy"
    ] = (
        result[
            "structural_revenue_yoy"
        ]
        .clip(
            -100,
            150,
        )
    )


    # ========================================================
    # Lagged basis features
    # ========================================================

    result[
        "oil_basis_l1"
    ] = (
        (
            result[
                "oil_realization_ratio"
            ]
            .shift(1)
            -
            1
        )
        * 100
    )


    result[
        "gas_basis_l1"
    ] = (
        (
            result[
                "gas_realization_ratio"
            ]
            .shift(1)
            -
            1
        )
        * 100
    )


    result.index = (
        np.arange(
            len(result)
        )
    )


    return result


# ============================================================
# 17. MERGE V3 KPI INTO PANEL
# ============================================================

company_frames = []


for ticker in TICKERS:

    company_panel = (
        panel_v21[
            panel_v21[
                "ticker"
            ]
            == ticker
        ]
        .sort_values(
            "quarter"
        )
        .copy()
    )


    if company_panel.empty:

        continue


    kpi = (
        kpi_frames.get(
            ticker,
            pd.DataFrame(),
        )
    )


    company_v3 = (
        build_company_kpi_features(
            ticker,
            company_panel,
            kpi,
        )
    )


    company_frames.append(
        company_v3
    )


panel_v3 = (
    pd.concat(
        company_frames,
        axis=0,
        ignore_index=True,
    )
)


panel_v3[
    "quarter"
] = pd.PeriodIndex(
    panel_v3[
        "quarter"
    ].astype(str),
    freq="Q",
)


panel_v3 = (
    panel_v3
    .sort_values(
        [
            "quarter",
            "ticker",
        ]
    )
    .reset_index(
        drop=True
    )
)


PANEL_V3_FILE = lake_path(
    "energy_v3_panel.csv"
)


panel_v3.to_csv(
    PANEL_V3_FILE,
    index=False,
)


print(
    f"\n💾 {PANEL_V3_FILE}"
)


# ============================================================
# 18. V3 RESIDUAL FEATURES
#
# Baseline predicts the bulk of revenue.
# Ridge only predicts:
#
# actual revenue YoY
# -
# structural revenue YoY
#
# ============================================================

CANDIDATE_RESIDUAL_FEATURES = [

    # Company momentum
    "revenue_yoy_l1_clip",

    # Company real production
    "company_total_prod_yoy_l1",
    "company_oil_prod_yoy_l1",
    "company_gas_prod_yoy_l1",

    # Pricing differentials
    "oil_basis_l1",
    "gas_basis_l1",

    # Product mix
    "gas_boe_share_l1",

    # Macro residual information
    "wti_yoy",
    "henry_yoy",
    "bea_go_yoy_l1",

    # Financial controls
    "assets_yoy_l1_clip",
    "shares_yoy_l1_clip",
    "debt_yoy_l1_clip",

    # M&A interactions inherited from V2.1
    #
    # No raw ma_window / ma_event.
    "ma_assets_interaction",
    "ma_shares_interaction",
]


# ============================================================
# 19. TARGET RESIDUAL
# ============================================================

panel_v3[
    "structural_error"
] = (

    panel_v3[
        "revenue_yoy"
    ]

    -

    panel_v3[
        "structural_revenue_yoy"
    ]
)


# ============================================================
# 20. FEATURE COVERAGE
# ============================================================

coverage_records = []


for ticker in TICKERS:

    subset = (
        panel_v3[
            panel_v3[
                "ticker"
            ]
            == ticker
        ]
    )


    for feature in (
        CANDIDATE_RESIDUAL_FEATURES
    ):

        if feature in (
            subset.columns
        ):

            coverage = (
                subset[
                    feature
                ]
                .notna()
                .mean()
            )

        else:

            coverage = 0.0


        coverage_records.append(
            {
                "ticker":
                    ticker,

                "feature":
                    feature,

                "coverage":
                    coverage,
            }
        )


coverage_df = pd.DataFrame(
    coverage_records
)


coverage_file = lake_path(
    "energy_v3_feature_coverage.csv"
)


coverage_df.to_csv(
    coverage_file,
    index=False,
)


print(
    f"💾 {coverage_file}"
)


# ============================================================
# 21. SELECT FEATURES FROM TRAIN SET
# ============================================================

def select_features(
    train_df
):

    selected = []


    for feature in (
        CANDIDATE_RESIDUAL_FEATURES
    ):

        if feature not in (
            train_df.columns
        ):

            continue


        coverage = (
            train_df[
                feature
            ]
            .notna()
            .mean()
        )


        if (
            coverage
            <
            MIN_FEATURE_COVERAGE
        ):

            continue


        std = (
            train_df[
                feature
            ]
            .std(
                skipna=True
            )
        )


        if (
            pd.isna(std)
            or
            std < 1e-9
        ):

            continue


        selected.append(
            feature
        )


    return selected


# ============================================================
# 22. DESIGN MATRIX
# ============================================================

def make_design_matrix(
    df,
    features
):

    X = (
        df[
            features
        ]
        .copy()
    )


    # Company fixed effects

    for ticker in (
        TICKERS[1:]
    ):

        X[
            f"ticker_{ticker}"
        ] = (
            df[
                "ticker"
            ]
            .eq(
                ticker
            )
            .astype(float)
        )


    X = X.replace(
        [
            np.inf,
            -np.inf,
        ],
        np.nan,
    )


    return X


# ============================================================
# 23. FILL MISSING FROM TRAIN ONLY
# ============================================================

def fill_missing(
    train_x,
    test_x
):

    medians = (
        train_x
        .median(
            axis=0,
            skipna=True,
        )
        .fillna(0)
    )


    train_x = (
        train_x
        .fillna(
            medians
        )
    )


    test_x = (
        test_x
        .fillna(
            medians
        )
    )


    return (
        train_x,
        test_x,
        medians,
    )


# ============================================================
# 24. MODEL
# ============================================================

def build_model(
    alpha
):

    return Pipeline(
        [
            (
                "scale",
                StandardScaler(),
            ),

            (
                "ridge",
                Ridge(
                    alpha=alpha
                ),
            ),
        ]
    )


# ============================================================
# 25. ALPHA SELECTION
# ============================================================

def select_alpha(
    train_df,
    features
):

    quarters = sorted(
        train_df[
            "quarter"
        ]
        .unique()
    )


    if len(quarters) < 10:

        return 10.0


    validation_quarters = (
        quarters[
            -min(
                4,
                max(
                    1,
                    len(quarters)
                    - 6
                ),
            ):
        ]
    )


    best_alpha = 10.0
    best_mae = np.inf


    for alpha in (
        RIDGE_ALPHAS
    ):

        errors = []


        for q in (
            validation_quarters
        ):

            inner_train = (
                train_df[
                    train_df[
                        "quarter"
                    ]
                    < q
                ]
                .copy()
            )


            inner_test = (
                train_df[
                    train_df[
                        "quarter"
                    ]
                    == q
                ]
                .copy()
            )


            if (
                inner_train[
                    "quarter"
                ]
                .nunique()
                < 8
            ):

                continue


            if inner_test.empty:

                continue


            X_train = (
                make_design_matrix(
                    inner_train,
                    features,
                )
            )


            X_test = (
                make_design_matrix(
                    inner_test,
                    features,
                )
            )


            (
                X_train,
                X_test,
                _
            ) = (
                fill_missing(
                    X_train,
                    X_test,
                )
            )


            y_train = (
                inner_train[
                    "structural_error"
                ]
                .astype(float)
            )


            y_test_actual = (
                inner_test[
                    "revenue_yoy"
                ]
                .astype(float)
            )


            model = (
                build_model(
                    alpha
                )
            )


            model.fit(
                X_train,
                y_train,
            )


            residual_pred = (
                model.predict(
                    X_test
                )
            )


            final_pred = (

                inner_test[
                    "structural_revenue_yoy"
                ]
                .to_numpy(
                    dtype=float
                )

                +

                residual_pred
            )


            final_pred = (
                np.clip(
                    final_pred,
                    PREDICTION_MIN,
                    PREDICTION_MAX,
                )
            )


            error = (
                mean_absolute_error(
                    y_test_actual,
                    final_pred,
                )
            )


            errors.append(
                error
            )


        if not errors:

            continue


        avg_error = (
            np.mean(
                errors
            )
        )


        if avg_error < best_mae:

            best_mae = (
                avg_error
            )

            best_alpha = (
                alpha
            )


    return best_alpha


# ============================================================
# 26. WALK FORWARD
# ============================================================

def walk_forward(
    panel
):

    history = (
        panel[
            panel[
                "revenue_yoy"
            ].notna()
            &
            panel[
                "structural_revenue_yoy"
            ].notna()
        ]
        .copy()
    )


    quarters = sorted(
        history[
            "quarter"
        ]
        .unique()
    )


    if (
        len(quarters)
        <= MIN_TRAIN_QUARTERS
    ):

        raise ValueError(
            "V3 walk-forward history 부족"
        )


    start_test = max(
        MIN_TRAIN_QUARTERS,
        len(quarters)
        -
        TEST_QUARTERS,
    )


    test_quarters = (
        quarters[
            start_test:
        ]
    )


    records = []


    print(
        "\n"
        + "=" * 90
    )

    print(
        "V3 WALK-FORWARD VALIDATION"
    )

    print(
        "=" * 90
    )


    for q in (
        test_quarters
    ):

        train = (
            history[
                history[
                    "quarter"
                ]
                < q
            ]
            .copy()
        )


        test = (
            history[
                history[
                    "quarter"
                ]
                == q
            ]
            .copy()
        )


        if test.empty:

            continue


        features = (
            select_features(
                train
            )
        )


        if not features:

            raise ValueError(
                f"{q}: usable features 없음"
            )


        alpha = (
            select_alpha(
                train,
                features,
            )
        )


        X_train = (
            make_design_matrix(
                train,
                features,
            )
        )


        X_test = (
            make_design_matrix(
                test,
                features,
            )
        )


        (
            X_train,
            X_test,
            _
        ) = (
            fill_missing(
                X_train,
                X_test,
            )
        )


        y_train = (
            train[
                "structural_error"
            ]
            .astype(float)
        )


        model = (
            build_model(
                alpha
            )
        )


        model.fit(
            X_train,
            y_train,
        )


        residual_pred = (
            model.predict(
                X_test
            )
        )


        structural = (
            test[
                "structural_revenue_yoy"
            ]
            .to_numpy(
                dtype=float
            )
        )


        prediction = (
            structural
            +
            residual_pred
        )


        prediction = (
            np.clip(
                prediction,
                PREDICTION_MIN,
                PREDICTION_MAX,
            )
        )


        for (
            (_, row),
            structural_pred,
            final_pred,
            resid_pred
        ) in zip(

            test.iterrows(),

            structural,

            prediction,

            residual_pred,
        ):

            records.append(
                {
                    "quarter":
                        q,

                    "ticker":
                        row[
                            "ticker"
                        ],

                    "actual":
                        float(
                            row[
                                "revenue_yoy"
                            ]
                        ),

                    "naive":
                        0.0,

                    "structural":
                        float(
                            structural_pred
                        ),

                    "v3_predicted":
                        float(
                            final_pred
                        ),

                    "residual_adjustment":
                        float(
                            resid_pred
                        ),

                    "company_price_mix_yoy":
                        row[
                            "company_price_mix_yoy"
                        ],

                    "company_volume_yoy_proxy":
                        row[
                            "company_volume_yoy_proxy"
                        ],

                    "company_total_prod_yoy_l1":
                        row[
                            "company_total_prod_yoy_l1"
                        ],

                    "alpha":
                        alpha,

                    "feature_count":
                        len(
                            features
                        ),
                }
            )


    result = pd.DataFrame(
        records
    )


    if result.empty:

        raise ValueError(
            "V3 validation 결과 없음"
        )


    # ========================================================
    # Overall
    # ========================================================

    naive_mae = (
        mean_absolute_error(
            result[
                "actual"
            ],
            result[
                "naive"
            ],
        )
    )


    structural_mae = (
        mean_absolute_error(
            result[
                "actual"
            ],
            result[
                "structural"
            ],
        )
    )


    v3_mae = (
        mean_absolute_error(
            result[
                "actual"
            ],
            result[
                "v3_predicted"
            ],
        )
    )


    v3_rmse = (
        np.sqrt(
            mean_squared_error(
                result[
                    "actual"
                ],
                result[
                    "v3_predicted"
                ],
            )
        )
    )


    print(
        f"\nNaive MAE      : "
        f"{naive_mae:.2f} pp"
    )


    print(
        f"Structural MAE : "
        f"{structural_mae:.2f} pp"
    )


    print(
        f"V3 MAE         : "
        f"{v3_mae:.2f} pp"
    )


    print(
        f"V3 RMSE        : "
        f"{v3_rmse:.2f} pp"
    )


    print(
        f"Naive 개선     : "
        f"{((naive_mae - v3_mae) / naive_mae * 100):+.1f}%"
    )


    # ========================================================
    # By ticker
    # ========================================================

    metrics = []


    for ticker, group in (
        result.groupby(
            "ticker"
        )
    ):

        naive = (
            mean_absolute_error(
                group["actual"],
                group["naive"],
            )
        )


        structural_m = (
            mean_absolute_error(
                group["actual"],
                group["structural"],
            )
        )


        v3 = (
            mean_absolute_error(
                group["actual"],
                group["v3_predicted"],
            )
        )


        rmse = np.sqrt(
            mean_squared_error(
                group["actual"],
                group["v3_predicted"],
            )
        )


        metrics.append(
            {
                "ticker":
                    ticker,

                "Naive_MAE":
                    naive,

                "Structural_MAE":
                    structural_m,

                "V3_MAE":
                    v3,

                "V3_RMSE":
                    rmse,

                "improvement_pct":
                    (
                        (
                            naive
                            - v3
                        )
                        /
                        naive
                        * 100
                    ),
            }
        )


    metrics = (
        pd.DataFrame(
            metrics
        )
        .set_index(
            "ticker"
        )
    )


    print(
        "\n===== BY TICKER ====="
    )


    print(
        metrics.round(
            2
        )
    )


    print(
        "\n===== LAST VALIDATION ROWS ====="
    )


    print(
        result.tail(
            20
        )
        .round(2)
        .to_string(
            index=False
        )
    )


    validation_file = lake_path(
        "energy_v3_validation.csv"
    )


    metrics_file = lake_path(
        "energy_v3_metrics.csv"
    )


    result.to_csv(
        validation_file,
        index=False,
    )


    metrics.to_csv(
        metrics_file
    )


    print(
        f"\n💾 {validation_file}"
    )


    print(
        f"💾 {metrics_file}"
    )


    return (
        result,
        metrics,
    )


# ============================================================
# 27. FINAL MODEL
# ============================================================

def final_model_and_nowcast(
    panel
):

    history = (
        panel[
            panel[
                "revenue_yoy"
            ].notna()
            &
            panel[
                "structural_revenue_yoy"
            ].notna()
        ]
        .copy()
    )


    features = (
        select_features(
            history
        )
    )


    alpha = (
        select_alpha(
            history,
            features,
        )
    )


    print(
        "\nFinal features:"
    )


    for f in features:

        print(
            "  ",
            f
        )


    print(
        "\nFinal alpha:",
        alpha
    )


    X_train = (
        make_design_matrix(
            history,
            features,
        )
    )


    medians = (
        X_train
        .median(
            axis=0,
            skipna=True,
        )
        .fillna(0)
    )


    X_train = (
        X_train
        .fillna(
            medians
        )
    )


    y_train = (
        history[
            "structural_error"
        ]
        .astype(float)
    )


    model = (
        build_model(
            alpha
        )
    )


    model.fit(
        X_train,
        y_train,
    )


    # ========================================================
    # Nowcast rows
    # ========================================================

    rows = []


    for ticker in TICKERS:

        company = (
            panel[
                panel[
                    "ticker"
                ]
                == ticker
            ]
            .copy()
        )


        actual = (
            company[
                company[
                    "revenue"
                ]
                .notna()
            ]
        )


        if actual.empty:

            continue


        last_actual_q = (
            actual[
                "quarter"
            ]
            .max()
        )


        nowcast_q = (
            last_actual_q
            + 1
        )


        current = (
            company[
                company[
                    "quarter"
                ]
                == nowcast_q
            ]
        )


        if current.empty:

            print(
                f"⚠️ {ticker}: "
                f"{nowcast_q} row 없음"
            )

            continue


        row = (
            current.iloc[
                0
            ]
            .copy()
        )


        row[
            "nowcast_quarter"
        ] = (
            nowcast_q
        )


        rows.append(
            row
        )


    if not rows:

        raise ValueError(
            "Nowcast row 없음"
        )


    now = pd.DataFrame(
        rows
    )


    X_now = (
        make_design_matrix(
            now,
            features,
        )
    )


    X_now = (
        X_now
        .fillna(
            medians
        )
    )


    residual_pred = (
        model.predict(
            X_now
        )
    )


    structural = (
        now[
            "structural_revenue_yoy"
        ]
        .to_numpy(
            dtype=float
        )
    )


    final_prediction = (
        structural
        +
        residual_pred
    )


    final_prediction = np.clip(
        final_prediction,
        PREDICTION_MIN,
        PREDICTION_MAX,
    )


    now[
        "residual_adjustment"
    ] = (
        residual_pred
    )


    now[
        "predicted_revenue_yoy"
    ] = (
        final_prediction
    )


    # ========================================================
    # Convert growth to revenue level
    # ========================================================

    revenue_predictions = []


    for _, row in (
        now.iterrows()
    ):

        ticker = (
            row["ticker"]
        )


        q = (
            row[
                "nowcast_quarter"
            ]
        )


        base_q = (
            q - 4
        )


        base = (
            panel[
                (
                    panel[
                        "ticker"
                    ]
                    == ticker
                )
                &
                (
                    panel[
                        "quarter"
                    ]
                    == base_q
                )
            ]
        )


        if (
            base.empty
            or
            pd.isna(
                base.iloc[0][
                    "revenue"
                ]
            )
        ):

            revenue_predictions.append(
                np.nan
            )

            continue


        base_revenue = float(
            base.iloc[0][
                "revenue"
            ]
        )


        predicted = (

            base_revenue

            *

            np.exp(
                row[
                    "predicted_revenue_yoy"
                ]
                /
                100
            )
        )


        revenue_predictions.append(
            predicted
        )


    now[
        "predicted_revenue"
    ] = (
        revenue_predictions
    )


    now[
        "predicted_revenue_B"
    ] = (
        now[
            "predicted_revenue"
        ]
        /
        1e9
    )


    # ========================================================
    # Output
    # ========================================================

    output_columns = [

        "ticker",
        "nowcast_quarter",

        "predicted_revenue_yoy",
        "predicted_revenue_B",

        "structural_revenue_yoy",
        "residual_adjustment",

        "company_price_mix_yoy",
        "company_volume_yoy_proxy",

        "company_total_prod_yoy_l1",

        "company_total_prod",
        "company_oil_prod",
        "company_ngl_prod",
        "company_gas_prod",

        "est_realized_oil_yoy",
        "est_realized_gas_yoy",

        "wti_yoy",
        "henry_yoy",
    ]


    available = [
        c
        for c in output_columns
        if c in now.columns
    ]


    output = (
        now[
            available
        ]
        .copy()
    )


    print(
        "\n"
        + "=" * 90
    )

    print(
        "🚀 ENERGY REVENUE V3 NOWCAST"
    )

    print(
        "=" * 90
    )


    print(
        output.round(
            2
        )
        .to_string(
            index=False
        )
    )


    # ========================================================
    # Coefficients
    # ========================================================

    coefficients = (
        pd.Series(

            model
            .named_steps[
                "ridge"
            ]
            .coef_,

            index=(
                X_train.columns
            ),
        )
        .sort_values(
            key=np.abs,
            ascending=False,
        )
    )


    print(
        "\n===== RESIDUAL MODEL COEFFICIENTS ====="
    )


    print(
        coefficients.round(
            3
        )
    )


    nowcast_file = lake_path(
        "energy_v3_nowcast.csv"
    )


    coef_file = lake_path(
        "energy_v3_coefficients.csv"
    )


    output.to_csv(
        nowcast_file,
        index=False,
    )


    coefficients.to_frame(
        "coefficient"
    ).to_csv(
        coef_file
    )


    print(
        f"\n💾 {nowcast_file}"
    )


    print(
        f"💾 {coef_file}"
    )


    return (
        model,
        output,
        coefficients,
    )


# ============================================================
# 28. RUN
# ============================================================

validation, metrics = (
    walk_forward(
        panel_v3
    )
)


model, nowcast, coefficients = (
    final_model_and_nowcast(
        panel_v3
    )
)


print(
    "\n"
    + "=" * 90
)

print(
    "DONE"
)

print(
    "=" * 90
)


print(
    "\nMain V3 files:"
)


for filename in [

    "energy_v3_panel.csv",
    "energy_v3_feature_coverage.csv",
    "energy_v3_validation.csv",
    "energy_v3_metrics.csv",
    "energy_v3_nowcast.csv",
    "energy_v3_coefficients.csv",
    "energy_v3_kpi_overrides.json",

]:

    print(
        " -",
        lake_path(
            filename
        )
    )


print(
    "\nCompany KPI files:"
)


for ticker in TICKERS:

    print(
        " -",
        lake_path(
            f"energy_v3_kpi_{ticker}.csv"
        )
    )

    print(
        " -",
        lake_path(
            f"energy_v3_kpi_candidates_{ticker}.csv"
        )
    )

    print(
        " -",
        lake_path(
            f"energy_v3_kpi_selected_{ticker}.csv"
        )
    )
