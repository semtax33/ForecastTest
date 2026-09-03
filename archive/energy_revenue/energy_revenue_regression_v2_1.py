# ============================================================
# ENERGY REVENUE NOWCAST V2.1
#
# EIA + BEA + SEC(edgartools)
# + Financial Structure
# + M&A Interaction
# + Winsorization
# + Panel Ridge
# + Walk-Forward Validation
#
# Output:
#   ./data-lake/
#
# Required ENV:
#   EIA_API_KEY
#   BEA_API_KEY
#   EDGAR_IDENTITY
#
# Optional ENV:
#   DATA_LAKE_DIR=./data-lake
#   TICKERS=COP,EOG,FANG,DVN
#   START_YEAR=2014
#   AS_OF_DATE=2026-08-31
#
# pip install -U \
#   edgartools \
#   beaapi \
#   pandas \
#   numpy \
#   requests \
#   scikit-learn
# ============================================================

import os
import re
import json
import warnings
from pathlib import Path
from datetime import date

import numpy as np
import pandas as pd
import requests
import beaapi

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
# 0. ENVIRONMENT CONFIG
# ============================================================

EIA_API_KEY = os.getenv("EIA_API_KEY")
BEA_API_KEY = os.getenv("BEA_API_KEY")
EDGAR_IDENTITY = os.getenv("EDGAR_IDENTITY")

DATA_LAKE_DIR = Path(
    os.getenv(
        "DATA_LAKE_DIR",
        "./data-lake"
    )
)

TICKERS = [
    x.strip().upper()
    for x in os.getenv(
        "TICKERS",
        "COP,EOG,FANG,DVN"
    ).split(",")
    if x.strip()
]

START_YEAR = int(
    os.getenv(
        "START_YEAR",
        "2014"
    )
)

AS_OF_DATE_ENV = os.getenv(
    "AS_OF_DATE"
)

TEST_QUARTERS = int(
    os.getenv(
        "TEST_QUARTERS",
        "12"
    )
)

MIN_TRAIN_QUARTERS = int(
    os.getenv(
        "MIN_TRAIN_QUARTERS",
        "16"
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
# V2.1 WINSORIZATION
# ============================================================

FINANCIAL_CLIP_LOW = -50.0
FINANCIAL_CLIP_HIGH = 50.0

GOODWILL_CLIP_LOW = -30.0
GOODWILL_CLIP_HIGH = 30.0

REVENUE_LAG_CLIP_LOW = -100.0
REVENUE_LAG_CLIP_HIGH = 100.0


# ============================================================
# 1. CONFIG CHECK
# ============================================================

def check_config():

    missing = []

    if not EIA_API_KEY:
        missing.append(
            "EIA_API_KEY"
        )

    if not BEA_API_KEY:
        missing.append(
            "BEA_API_KEY"
        )

    if not EDGAR_IDENTITY:
        missing.append(
            "EDGAR_IDENTITY"
        )

    if missing:

        raise ValueError(
            "환경변수가 빠졌어: "
            + ", ".join(missing)
        )


def resolve_as_of_date():

    if AS_OF_DATE_ENV:

        return pd.Timestamp(
            AS_OF_DATE_ENV
        ).normalize()

    return pd.Timestamp(
        date.today()
    )


check_config()

AS_OF = resolve_as_of_date()

DATA_LAKE_DIR.mkdir(
    parents=True,
    exist_ok=True
)

set_identity(
    EDGAR_IDENTITY
)


print("=" * 80)
print("ENERGY REVENUE NOWCAST V2.1")
print("=" * 80)

print(
    "AS OF DATE :",
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


# ============================================================
# 2. SAVE HELPERS
# ============================================================

def lake_path(filename):

    return (
        DATA_LAKE_DIR
        / filename
    )


def save_dataframe(
    df,
    filename,
    index=True
):

    path = lake_path(
        filename
    )

    df.to_csv(
        path,
        index=index
    )

    print(
        f"  💾 {path}"
    )

    return path


# ============================================================
# Run metadata
# ============================================================

metadata = {
    "as_of_date":
        str(AS_OF.date()),

    "start_year":
        START_YEAR,

    "tickers":
        ",".join(TICKERS),

    "test_quarters":
        TEST_QUARTERS,

    "min_train_quarters":
        MIN_TRAIN_QUARTERS,

    "data_lake":
        str(
            DATA_LAKE_DIR.resolve()
        ),
}


with open(
    lake_path(
        "energy_v2_1_run_metadata.json"
    ),
    "w",
    encoding="utf-8",
) as f:

    json.dump(
        metadata,
        f,
        indent=2,
        ensure_ascii=False,
    )


# ============================================================
# 3. COMMON HELPERS
# ============================================================

def safe_numeric(value):

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
        return float(value)

    s = str(value).strip()

    s = (
        s
        .replace("$", "")
        .replace(",", "")
        .replace("—", "")
        .replace("–", "")
    )

    if (
        s.startswith("(")
        and s.endswith(")")
    ):

        s = (
            "-"
            + s[1:-1]
        )

    return pd.to_numeric(
        s,
        errors="coerce"
    )


def log_growth(
    series,
    periods=4
):

    series = pd.to_numeric(
        series,
        errors="coerce"
    )

    lagged = (
        series.shift(
            periods
        )
    )

    result = pd.Series(
        np.nan,
        index=series.index,
        dtype=float
    )

    valid = (
        (series > 0)
        &
        (lagged > 0)
    )

    result.loc[valid] = (
        np.log(
            series.loc[valid]
            /
            lagged.loc[valid]
        )
        * 100
    )

    return result


# ============================================================
# 4. EIA API
# ============================================================

def get_eia_series(
    series_id,
    start=None,
    length=5000,
):

    url = (
        "https://api.eia.gov/v2/"
        f"seriesid/{series_id}"
    )

    params = {
        "api_key":
            EIA_API_KEY,

        "length":
            length,
    }

    if start is not None:

        params["start"] = (
            start
        )

    r = requests.get(
        url,
        params=params,
        timeout=60,
    )

    r.raise_for_status()

    js = r.json()

    try:

        rows = (
            js["response"]["data"]
        )

    except Exception:

        raise ValueError(
            f"EIA 응답 구조 이상\n"
            f"{js}"
        )

    df = pd.DataFrame(
        rows
    )

    if df.empty:

        raise ValueError(
            f"EIA 데이터 없음: "
            f"{series_id}"
        )

    df["date"] = (
        pd.to_datetime(
            df["period"],
            errors="coerce",
        )
    )


    # --------------------------------------------------------
    # numeric column auto detect
    # --------------------------------------------------------

    if "value" in df.columns:

        value_col = (
            "value"
        )

    else:

        value_col = None

        skip = {
            "period",
            "series",
            "series-description",
            "units",
        }

        for col in df.columns:

            if (
                col in skip
                or
                str(col).endswith(
                    "-units"
                )
            ):

                continue

            candidate = (
                pd.to_numeric(
                    df[col],
                    errors="coerce",
                )
            )

            if (
                candidate
                .notna()
                .sum()
                > 0
            ):

                value_col = col
                break

        if value_col is None:

            raise ValueError(
                f"EIA value column "
                f"찾기 실패: "
                f"{df.columns.tolist()}"
            )


    df["value"] = (
        pd.to_numeric(
            df[value_col],
            errors="coerce",
        )
    )


    result = (
        df[
            [
                "date",
                "value",
            ]
        ]
        .dropna()
        .drop_duplicates(
            "date",
            keep="last",
        )
        .set_index(
            "date"
        )
        .sort_index()
        ["value"]
    )


    # point-in-time upper bound
    result = (
        result.loc[
            result.index <= AS_OF
        ]
    )

    return result


# ============================================================
# 5. EIA ENERGY DATA
# ============================================================

def get_energy_eia():

    print(
        "\nDownloading EIA..."
    )


    # --------------------------------------------------------
    # WTI daily
    # --------------------------------------------------------

    wti = get_eia_series(
        "PET.RWTC.D",
        start=(
            f"{START_YEAR}-01-01"
        ),
    )

    wti.name = "wti"


    # --------------------------------------------------------
    # Henry Hub daily
    # --------------------------------------------------------

    henry = get_eia_series(
        "NG.RNGWHHD.D",
        start=(
            f"{START_YEAR}-01-01"
        ),
    )

    henry.name = (
        "henry_hub"
    )


    # --------------------------------------------------------
    # Crude production monthly
    # --------------------------------------------------------

    crude = get_eia_series(
        "PET.MCRFPUS2.M",
        start=str(
            START_YEAR
        ),
    )

    crude.name = (
        "crude_prod"
    )


    # --------------------------------------------------------
    # Natural gas production monthly
    # --------------------------------------------------------

    gas = get_eia_series(
        "NG.N9070US2.M",
        start=str(
            START_YEAR
        ),
    )

    gas.name = (
        "gas_prod"
    )


    return {
        "wti":
            wti,

        "henry_hub":
            henry,

        "crude_prod":
            crude,

        "gas_prod":
            gas,
    }


# ============================================================
# 6. BEA GROSS OUTPUT
# ============================================================

def get_bea_gross_output():

    print(
        "\nDownloading BEA "
        "Oil & Gas Gross Output..."
    )


    # --------------------------------------------------------
    # GDPbyIndustry
    #
    # Table 15:
    # Gross Output by Industry
    #
    # Industry 211:
    # Oil and Gas Extraction
    # --------------------------------------------------------

    df = beaapi.get_data(
        BEA_API_KEY,
        "GDPbyIndustry",

        TableID=15,
        Frequency="Q",
        Year="ALL",
        Industry="211",
    )


    if (
        df is None
        or df.empty
    ):

        raise ValueError(
            "BEA Gross Output "
            "데이터가 없어."
        )


    df = df.copy()


    df["gross_output"] = (
        df["DataValue"]
        .astype(str)
        .str.replace(
            ",",
            "",
            regex=False,
        )
    )


    df["gross_output"] = (
        pd.to_numeric(
            df["gross_output"],
            errors="coerce",
        )
    )


    quarter_map = {
        "I": 1,
        "II": 2,
        "III": 3,
        "IV": 4,

        "1": 1,
        "2": 2,
        "3": 3,
        "4": 4,
    }


    df["quarter_number"] = (
        df["Quarter"]
        .astype(str)
        .map(
            quarter_map
        )
    )


    df = df.dropna(
        subset=[
            "quarter_number",
            "gross_output",
        ]
    )


    df["quarter"] = (
        pd.PeriodIndex(

            df["Year"]
            .astype(str)

            + "Q"

            + df[
                "quarter_number"
            ]
            .astype(int)
            .astype(str),

            freq="Q",
        )
    )


    result = (
        df[
            [
                "quarter",
                "gross_output",
            ]
        ]
        .drop_duplicates(
            "quarter",
            keep="last",
        )
        .set_index(
            "quarter"
        )
        .sort_index()
    )


    as_of_q = (
        AS_OF.to_period(
            "Q"
        )
    )


    result = result.loc[
        result.index
        <= as_of_q
    ]


    return result


# ============================================================
# 7. MACRO FEATURES
# ============================================================

def complete_quarter_mean(
    series
):

    quarter = (
        series.index
        .to_period("Q")
    )

    mean = (
        series
        .groupby(
            quarter
        )
        .mean()
    )

    count = (
        series
        .groupby(
            quarter
        )
        .count()
    )


    # monthly series:
    # 3 observations required
    mean.loc[
        count < 3
    ] = np.nan


    return mean


def make_macro_features():

    eia = (
        get_energy_eia()
    )

    bea = (
        get_bea_gross_output()
    )


    # ========================================================
    # Daily prices -> quarter average
    #
    # current quarter:
    # partial-quarter average
    # ========================================================

    wti_q = (
        eia["wti"]
        .groupby(
            eia["wti"]
            .index
            .to_period("Q")
        )
        .mean()
        .rename(
            "wti"
        )
    )


    henry_q = (
        eia["henry_hub"]
        .groupby(
            eia["henry_hub"]
            .index
            .to_period("Q")
        )
        .mean()
        .rename(
            "henry_hub"
        )
    )


    crude_q = (
        complete_quarter_mean(
            eia[
                "crude_prod"
            ]
        )
        .rename(
            "crude_prod"
        )
    )


    gas_q = (
        complete_quarter_mean(
            eia[
                "gas_prod"
            ]
        )
        .rename(
            "gas_prod"
        )
    )


    start_q = pd.Period(
        f"{START_YEAR}Q1",
        freq="Q",
    )


    end_q = (
        AS_OF
        .to_period("Q")
    )


    idx = pd.period_range(
        start_q,
        end_q,
        freq="Q",
    )


    macro = pd.DataFrame(
        index=idx
    )


    macro["wti"] = (
        wti_q
    )

    macro[
        "henry_hub"
    ] = (
        henry_q
    )

    macro[
        "crude_prod"
    ] = (
        crude_q
    )

    macro[
        "gas_prod"
    ] = (
        gas_q
    )

    macro[
        "bea_gross_output"
    ] = (
        bea[
            "gross_output"
        ]
    )


    # ========================================================
    # YoY
    # ========================================================

    macro[
        "wti_yoy"
    ] = log_growth(
        macro["wti"],
        4,
    )


    macro[
        "henry_yoy"
    ] = log_growth(
        macro[
            "henry_hub"
        ],
        4,
    )


    crude_yoy = (
        log_growth(
            macro[
                "crude_prod"
            ],
            4,
        )
    )


    gas_yoy = (
        log_growth(
            macro[
                "gas_prod"
            ],
            4,
        )
    )


    bea_yoy = (
        log_growth(
            macro[
                "bea_gross_output"
            ],
            4,
        )
    )


    # ========================================================
    # Production and BEA:
    #
    # use previous quarter
    #
    # Look-ahead protection
    # ========================================================

    macro[
        "crude_prod_yoy_l1"
    ] = (
        crude_yoy
        .shift(1)
        .ffill()
    )


    macro[
        "gas_prod_yoy_l1"
    ] = (
        gas_yoy
        .shift(1)
        .ffill()
    )


    macro[
        "bea_go_yoy_l1"
    ] = (
        bea_yoy
        .shift(1)
        .ffill()
    )


    save_dataframe(
        macro,
        "energy_v2_1_macro.csv"
    )


    return macro


# ============================================================
# 8. EDGAR PERIOD PARSER
# ============================================================

MONTH_PATTERN = (
    r"Jan(?:uary)?|"
    r"Feb(?:ruary)?|"
    r"Mar(?:ch)?|"
    r"Apr(?:il)?|"
    r"May|"
    r"Jun(?:e)?|"
    r"Jul(?:y)?|"
    r"Aug(?:ust)?|"
    r"Sep(?:tember)?|"
    r"Oct(?:ober)?|"
    r"Nov(?:ember)?|"
    r"Dec(?:ember)?"
)


def parse_edgar_period_column(
    col
):

    s = str(
        col
    ).strip()


    # --------------------------------------------------------
    # ISO date
    # --------------------------------------------------------

    if re.fullmatch(
        r"\d{4}-\d{2}-\d{2}",
        s,
    ):

        dt = pd.to_datetime(
            s,
            errors="coerce",
        )

        if pd.notna(dt):

            return dt.to_period(
                "Q"
            )


    # --------------------------------------------------------
    # Q1 2025
    # --------------------------------------------------------

    m = re.search(
        r"\bQ([1-4])\b.*?"
        r"\b(19|20)\d{2}\b",
        s,
        flags=re.IGNORECASE,
    )

    if m:

        year_match = re.search(
            r"\b((?:19|20)\d{2})\b",
            s
        )

        if year_match:

            q = int(
                m.group(1)
            )

            year = int(
                year_match.group(1)
            )

            return pd.Period(
                f"{year}Q{q}",
                freq="Q",
            )


    # --------------------------------------------------------
    # 2025 Q1
    # --------------------------------------------------------

    m = re.search(
        r"\b((?:19|20)\d{2})\b"
        r".*?\bQ([1-4])\b",
        s,
        flags=re.IGNORECASE,
    )

    if m:

        return pd.Period(
            f"{m.group(1)}"
            f"Q{m.group(2)}",
            freq="Q",
        )


    # --------------------------------------------------------
    # Date text
    #
    # Jun 30, 2025
    # Three Months Ended June 30, 2025
    # --------------------------------------------------------

    date_match = re.search(
        rf"({MONTH_PATTERN})"
        r"\s+\d{1,2},?\s+"
        r"(?:19|20)\d{2}",
        s,
        flags=re.IGNORECASE,
    )

    if date_match:

        dt = pd.to_datetime(
            date_match.group(0),
            errors="coerce",
        )

        if pd.notna(dt):

            return dt.to_period(
                "Q"
            )


    return None


# ============================================================
# 9. STATEMENT ROW EXTRACTOR
#
# V2.1:
# candidate scoring improves Assets extraction
# ============================================================

def normalize_label(
    value
):

    return (
        re.sub(
            r"\s+",
            " ",
            str(value)
            .strip()
            .lower(),
        )
    )


def extract_statement_series(
    stmt_df,
    standard_concepts=None,
    raw_concepts=None,
    exact_labels=None,
    label_regex=None,
    verbose=False,
):

    if (
        stmt_df is None
        or stmt_df.empty
    ):

        return pd.Series(
            dtype=float
        )


    standard_concepts = (
        standard_concepts
        or []
    )

    raw_concepts = (
        raw_concepts
        or []
    )

    exact_labels = [
        normalize_label(x)
        for x in (
            exact_labels
            or []
        )
    ]


    # --------------------------------------------------------
    # Period columns
    # --------------------------------------------------------

    period_cols = []

    for col in stmt_df.columns:

        if (
            parse_edgar_period_column(
                col
            )
            is not None
        ):

            period_cols.append(
                col
            )


    if not period_cols:

        return pd.Series(
            dtype=float
        )


    score = pd.Series(
        0.0,
        index=stmt_df.index,
    )


    # --------------------------------------------------------
    # Standard concept
    # --------------------------------------------------------

    if (
        standard_concepts
        and
        "standard_concept"
        in stmt_df.columns
    ):

        standard_values = (
            stmt_df[
                "standard_concept"
            ]
            .astype(str)
            .str.strip()
        )

        score += (
            standard_values
            .isin(
                standard_concepts
            )
            .astype(float)
            * 100
        )


    # --------------------------------------------------------
    # Raw XBRL concept
    # --------------------------------------------------------

    concept_col = None

    for candidate in [
        "concept",
        "concept_name",
        "name",
    ]:

        if (
            candidate
            in stmt_df.columns
        ):

            concept_col = (
                candidate
            )

            break


    if (
        raw_concepts
        and concept_col
    ):

        concept_values = (
            stmt_df[
                concept_col
            ]
            .astype(str)
        )

        for raw in raw_concepts:

            matched = (
                concept_values
                .str.endswith(
                    raw,
                    na=False,
                )
            )

            score += (
                matched.astype(float)
                * 90
            )


    # --------------------------------------------------------
    # Exact labels
    # --------------------------------------------------------

    if (
        exact_labels
        and
        "label"
        in stmt_df.columns
    ):

        labels = (
            stmt_df["label"]
            .map(
                normalize_label
            )
        )

        score += (
            labels
            .isin(
                exact_labels
            )
            .astype(float)
            * 80
        )


    # --------------------------------------------------------
    # Regex label fallback
    # --------------------------------------------------------

    if (
        label_regex
        and
        "label"
        in stmt_df.columns
    ):

        matched = (
            stmt_df["label"]
            .astype(str)
            .str.contains(
                label_regex,
                case=False,
                regex=True,
                na=False,
            )
        )

        score += (
            matched.astype(float)
            * 30
        )


    candidates = (
        stmt_df.loc[
            score > 0
        ]
    )


    if candidates.empty:

        return pd.Series(
            dtype=float
        )


    # --------------------------------------------------------
    # Prefer semantic match,
    # then data coverage
    # --------------------------------------------------------

    coverage = (
        candidates[
            period_cols
        ]
        .notna()
        .sum(
            axis=1
        )
    )


    candidate_score = (
        score.loc[
            candidates.index
        ]
        * 1000
        +
        coverage
    )


    best_idx = (
        candidate_score
        .idxmax()
    )


    row = (
        stmt_df
        .loc[
            best_idx
        ]
    )


    if verbose:

        print(
            "  selected:",
            row.get(
                "label",
                "?"
            ),
            "|",
            row.get(
                "standard_concept",
                ""
            ),
        )


    records = {}


    for col in period_cols:

        quarter = (
            parse_edgar_period_column(
                col
            )
        )

        value = (
            safe_numeric(
                row[col]
            )
        )

        if (
            quarter is not None
            and pd.notna(value)
        ):

            records[
                quarter
            ] = float(
                value
            )


    if not records:

        return pd.Series(
            dtype=float
        )


    result = pd.Series(
        records,
        dtype=float,
    )


    result.index = (
        pd.PeriodIndex(
            result.index,
            freq="Q",
        )
    )


    return (
        result
        .sort_index()
    )


# ============================================================
# 10. ENTITYFACTS TIME SERIES FALLBACK
#
# Especially useful for Assets
# ============================================================

def extract_fact_timeseries(
    facts,
    concepts,
    periods=80,
):

    for concept in concepts:

        try:

            df = (
                facts.time_series(
                    concept,
                    periods=periods,
                )
            )

        except Exception:

            continue


        if (
            df is None
            or df.empty
        ):

            continue


        df = df.copy()


        # ----------------------------------------------------
        # period_end
        # ----------------------------------------------------

        period_col = None

        for c in [
            "period_end",
            "end",
            "date",
        ]:

            if c in df.columns:

                period_col = c
                break


        # ----------------------------------------------------
        # numeric
        # ----------------------------------------------------

        value_col = None

        for c in [
            "numeric_value",
            "value",
            "amount",
        ]:

            if c in df.columns:

                value_col = c
                break


        if (
            period_col is None
            or value_col is None
        ):

            continue


        df[
            "_period_end"
        ] = (
            pd.to_datetime(
                df[
                    period_col
                ],
                errors="coerce",
            )
        )


        df[
            "_value"
        ] = (
            pd.to_numeric(
                df[
                    value_col
                ],
                errors="coerce",
            )
        )


        # filing date point-in-time filter
        if (
            "filing_date"
            in df.columns
        ):

            df[
                "_filing_date"
            ] = (
                pd.to_datetime(
                    df[
                        "filing_date"
                    ],
                    errors="coerce",
                )
            )

            df = df[
                (
                    df[
                        "_filing_date"
                    ].isna()
                )
                |
                (
                    df[
                        "_filing_date"
                    ]
                    <= AS_OF
                )
            ]


        df = df.dropna(
            subset=[
                "_period_end",
                "_value",
            ]
        )


        if df.empty:

            continue


        df["quarter"] = (
            df[
                "_period_end"
            ]
            .dt.to_period(
                "Q"
            )
        )


        sort_cols = [
            "_period_end"
        ]

        if (
            "_filing_date"
            in df.columns
        ):

            sort_cols.append(
                "_filing_date"
            )


        df = df.sort_values(
            sort_cols
        )


        result = (
            df
            .drop_duplicates(
                "quarter",
                keep="last",
            )
            .set_index(
                "quarter"
            )
            ["_value"]
            .sort_index()
        )


        if not result.empty:

            return result


    return pd.Series(
        dtype=float
    )


# ============================================================
# 11. SEC FINANCIAL FEATURES
# ============================================================

def get_sec_financial_features(
    ticker,
    periods=64,
):

    print(
        f"\nSEC Financials: "
        f"{ticker}"
    )


    company = Company(
        ticker
    )


    facts = (
        company
        .get_facts()
    )


    income = (
        facts
        .income_statement(
            periods=periods,
            annual=False,
            as_dataframe=True,
        )
    )


    balance = (
        facts
        .balance_sheet(
            periods=periods,
            annual=False,
            as_dataframe=True,
        )
    )


    print(
        "  income shape :",
        income.shape
    )

    print(
        "  balance shape:",
        balance.shape
    )


    # ========================================================
    # Revenue
    # ========================================================

    revenue = (
        extract_statement_series(

            income,

            standard_concepts=[
                "Revenue",
            ],

            raw_concepts=[
                "Revenues",
                (
                    "RevenueFromContractWith"
                    "CustomerExcludingAssessedTax"
                ),
                "SalesRevenueNet",
            ],

            exact_labels=[
                "Revenue",
                "Revenues",
                "Total Revenue",
                "Total Revenues",
                "Total revenues and other income",
            ],

            label_regex=(
                r"total\s+revenue|"
                r"total\s+revenues|"
                r"^revenues?$"
            ),

            verbose=True,
        )
    )


    if revenue.empty:

        raise ValueError(
            f"{ticker}: "
            f"Revenue 추출 실패"
        )


    # ========================================================
    # Assets
    #
    # V2.1 fix:
    # Assets AND Total Assets allowed
    # ========================================================

    assets = (
        extract_statement_series(

            balance,

            standard_concepts=[
                "Assets",
            ],

            raw_concepts=[
                "Assets",
            ],

            exact_labels=[
                "Assets",
                "Total Assets",
            ],

            label_regex=(
                r"^(total\s+)?assets$"
            ),

            verbose=True,
        )
    )


    # EntityFacts fallback
    if assets.empty:

        print(
            "  ⚠️ Assets statement "
            "추출 실패 → "
            "EntityFacts fallback"
        )

        assets = (
            extract_fact_timeseries(
                facts,
                [
                    "Assets",
                    "us-gaap:Assets",
                ],
                periods=80,
            )
        )


    # ========================================================
    # PPE
    # ========================================================

    ppe = (
        extract_statement_series(

            balance,

            standard_concepts=[
                "PlantPropertyEquipmentNet",
            ],

            raw_concepts=[
                "PropertyPlantAndEquipmentNet",
            ],

            exact_labels=[
                "Property, Plant and Equipment, Net",
                "Property Plant and Equipment Net",
                "Net Property Plant and Equipment",
            ],

            label_regex=(
                r"property.*plant.*equipment.*net|"
                r"oil.*gas.*propert"
            ),
        )
    )


    if ppe.empty:

        ppe = (
            extract_fact_timeseries(
                facts,
                [
                    "PropertyPlantAndEquipmentNet",
                    (
                        "us-gaap:"
                        "PropertyPlantAndEquipmentNet"
                    ),
                ],
                periods=80,
            )
        )


    # ========================================================
    # Goodwill
    # ========================================================

    goodwill = (
        extract_statement_series(

            balance,

            standard_concepts=[
                "Goodwill",
            ],

            raw_concepts=[
                "Goodwill",
            ],

            exact_labels=[
                "Goodwill",
            ],

            label_regex=(
                r"^goodwill$"
            ),
        )
    )


    if goodwill.empty:

        goodwill = (
            extract_fact_timeseries(
                facts,
                [
                    "Goodwill",
                    "us-gaap:Goodwill",
                ],
                periods=80,
            )
        )


    # ========================================================
    # Long-term debt
    # ========================================================

    long_debt = (
        extract_statement_series(

            balance,

            standard_concepts=[
                "LongTermDebt",
            ],

            raw_concepts=[
                "LongTermDebtNoncurrent",
                (
                    "LongTermDebtAnd"
                    "FinanceLeaseObligations"
                    "Noncurrent"
                ),
            ],

            exact_labels=[
                "Long-term debt",
                "Long Term Debt",
            ],

            label_regex=(
                r"long.?term debt"
            ),
        )
    )


    # ========================================================
    # Short-term debt
    # ========================================================

    short_debt = (
        extract_statement_series(

            balance,

            standard_concepts=[
                "ShortTermDebt",
            ],

            raw_concepts=[
                "ShortTermBorrowings",
                "LongTermDebtCurrent",
                (
                    "LongTermDebtAnd"
                    "FinanceLeaseObligations"
                    "Current"
                ),
            ],

            label_regex=(
                r"short.?term debt|"
                r"current portion.*debt"
            ),
        )
    )


    debt = (
        pd.concat(
            [
                long_debt.rename(
                    "long"
                ),
                short_debt.rename(
                    "short"
                ),
            ],
            axis=1,
        )
        .sum(
            axis=1,
            min_count=1,
        )
    )


    # ========================================================
    # Shares
    # ========================================================

    shares = (
        extract_statement_series(

            income,

            standard_concepts=[
                "SharesAverage",
            ],

            raw_concepts=[
                (
                    "WeightedAverageNumberOf"
                    "DilutedSharesOutstanding"
                ),
                (
                    "WeightedAverageNumberOf"
                    "SharesOutstandingBasic"
                ),
            ],

            label_regex=(
                r"weighted average.*shares"
            ),
        )
    )


    # ========================================================
    # Build quarterly frame
    # ========================================================

    valid_series = [
        s
        for s in [
            revenue,
            assets,
            ppe,
            goodwill,
            debt,
            shares,
        ]
        if not s.empty
    ]


    idx = (
        valid_series[0]
        .index
    )


    for s in (
        valid_series[1:]
    ):

        idx = idx.union(
            s.index
        )


    idx = (
        idx.sort_values()
    )


    df = pd.DataFrame(
        index=idx
    )


    df["revenue"] = revenue
    df["assets"] = assets
    df["ppe"] = ppe
    df["goodwill"] = goodwill
    df["debt"] = debt
    df["shares"] = shares


    # ========================================================
    # Revenue target
    # ========================================================

    df[
        "revenue_yoy"
    ] = log_growth(
        df["revenue"],
        4,
    )


    # ========================================================
    # YoY financial changes
    # ========================================================

    df[
        "assets_yoy"
    ] = log_growth(
        df["assets"],
        4,
    )


    df[
        "ppe_yoy"
    ] = log_growth(
        df["ppe"],
        4,
    )


    df[
        "debt_yoy"
    ] = log_growth(
        df["debt"],
        4,
    )


    df[
        "shares_yoy"
    ] = log_growth(
        df["shares"],
        4,
    )


    # ========================================================
    # QoQ jumps
    # Diagnostic M&A detector
    # ========================================================

    df[
        "assets_qoq"
    ] = log_growth(
        df["assets"],
        1,
    )


    df[
        "ppe_qoq"
    ] = log_growth(
        df["ppe"],
        1,
    )


    df[
        "debt_qoq"
    ] = log_growth(
        df["debt"],
        1,
    )


    df[
        "shares_qoq"
    ] = log_growth(
        df["shares"],
        1,
    )


    # ========================================================
    # Goodwill jump
    #
    # Δ goodwill / previous assets
    # ========================================================

    df[
        "goodwill_jump"
    ] = (
        (
            df["goodwill"]
            -
            df["goodwill"]
            .shift(1)
        )
        /
        df["assets"]
        .shift(1)
        * 100
    )


    # AS_OF upper bound
    as_of_q = (
        AS_OF
        .to_period("Q")
    )


    df = df.loc[
        df.index <= as_of_q
    ]


    # ========================================================
    # Coverage print
    # ========================================================

    print(
        f"  Revenue quarters : "
        f"{df['revenue'].notna().sum()}"
    )

    print(
        f"  Assets coverage  : "
        f"{df['assets'].notna().mean() * 100:.1f}%"
    )

    print(
        f"  PPE coverage     : "
        f"{df['ppe'].notna().mean() * 100:.1f}%"
    )

    print(
        f"  Debt coverage    : "
        f"{df['debt'].notna().mean() * 100:.1f}%"
    )

    print(
        f"  Shares coverage  : "
        f"{df['shares'].notna().mean() * 100:.1f}%"
    )


    save_dataframe(
        df,
        (
            f"energy_v2_1_"
            f"sec_{ticker}.csv"
        )
    )


    return df


# ============================================================
# 12. 8-K ITEM 2.01
#
# Used ONLY as a gating/window variable
# NOT directly fed to regression
# ============================================================

def get_ma_8k_features(
    ticker,
    full_index,
):

    company = Company(
        ticker
    )


    start_date = (
        f"{START_YEAR}-01-01"
    )

    end_date = str(
        AS_OF.date()
    )


    result = pd.DataFrame(
        index=full_index
    )


    result[
        "ma_event"
    ] = 0.0


    try:

        filings = (
            company
            .get_filings(
                form="8-K"
            )
        )


        filings = (
            filings.filter(
                filing_date=(
                    f"{start_date}:"
                    f"{end_date}"
                )
            )
        )


        filing_df = (
            filings.to_pandas()
        )


    except Exception as e:

        print(
            f"  ⚠️ {ticker} "
            f"8-K error: {e}"
        )

        filing_df = (
            pd.DataFrame()
        )


    if (
        filing_df is None
        or filing_df.empty
        or "items"
        not in filing_df.columns
    ):

        result[
            "ma_window"
        ] = 0.0

        return (
            result,
            pd.DataFrame()
        )


    events = (
        filing_df[
            filing_df[
                "items"
            ]
            .astype(str)
            .str.contains(
                "2.01",
                regex=False,
                na=False,
            )
        ]
        .copy()
    )


    if events.empty:

        result[
            "ma_window"
        ] = 0.0

        return (
            result,
            events
        )


    # --------------------------------------------------------
    # economic event date
    # --------------------------------------------------------

    report_col = None

    for candidate in [
        "reportDate",
        "report_date",
        "period_of_report",
    ]:

        if candidate in events.columns:

            report_col = candidate
            break


    if report_col:

        report_date = (
            pd.to_datetime(
                events[
                    report_col
                ],
                errors="coerce",
            )
        )

    else:

        report_date = pd.Series(
            pd.NaT,
            index=events.index,
        )


    filing_date = (
        pd.to_datetime(
            events[
                "filing_date"
            ],
            errors="coerce",
        )
    )


    event_date = (
        report_date
        .fillna(
            filing_date
        )
    )


    events[
        "event_date"
    ] = event_date


    events[
        "quarter"
    ] = (
        events[
            "event_date"
        ]
        .dt.to_period(
            "Q"
        )
    )


    for q in (
        events[
            "quarter"
        ]
        .dropna()
    ):

        if q in result.index:

            result.loc[
                q,
                "ma_event"
            ] = 1.0


    # ========================================================
    # 5-quarter M&A base distortion window
    #
    # q0, q1, q2, q3, q4
    #
    # IMPORTANT:
    # This window itself is NOT a model feature.
    # It only activates financial interactions.
    # ========================================================

    result[
        "ma_window"
    ] = 0.0


    for lag in range(
        5
    ):

        result[
            "ma_window"
        ] = np.maximum(
            result[
                "ma_window"
            ],
            (
                result[
                    "ma_event"
                ]
                .shift(
                    lag
                )
                .fillna(0)
            ),
        )


    print(
        f"  {ticker} "
        f"Item 2.01 events: "
        f"{int(result['ma_event'].sum())}"
    )


    if not events.empty:

        save_dataframe(
            events,
            (
                f"energy_v2_1_"
                f"ma_events_{ticker}.csv"
            ),
            index=False,
        )


    return (
        result,
        events
    )


# ============================================================
# 13. V2.1 FEATURE SET
# ============================================================

FEATURES_V21 = [

    # --------------------------------------------------------
    # Energy prices
    # --------------------------------------------------------

    "wti_yoy",
    "henry_yoy",


    # --------------------------------------------------------
    # Industry volume
    # --------------------------------------------------------

    "crude_prod_yoy_l1",
    "gas_prod_yoy_l1",


    # --------------------------------------------------------
    # Industry revenue baseline
    # --------------------------------------------------------

    "bea_go_yoy_l1",


    # --------------------------------------------------------
    # Company momentum
    # --------------------------------------------------------

    "revenue_yoy_l1_clip",


    # --------------------------------------------------------
    # Financial structure
    # Winsorized
    # --------------------------------------------------------

    "assets_yoy_l1_clip",
    "ppe_yoy_l1_clip",
    "debt_yoy_l1_clip",
    "shares_yoy_l1_clip",
    "goodwill_jump_l1_clip",


    # --------------------------------------------------------
    # M&A interactions
    #
    # NO ma_event standalone
    # NO ma_window standalone
    # --------------------------------------------------------

    "ma_assets_interaction",
    "ma_ppe_interaction",
    "ma_debt_interaction",
    "ma_shares_interaction",
    "ma_goodwill_interaction",
]


# ============================================================
# 14. COMPANY DATASET
# ============================================================

def make_company_dataset(
    ticker,
    macro,
):

    sec = (
        get_sec_financial_features(
            ticker
        )
    )


    idx = (
        macro.index
        .union(
            sec.index
        )
        .sort_values()
    )


    ma, _ = (
        get_ma_8k_features(
            ticker,
            idx,
        )
    )


    df = (
        macro
        .reindex(
            idx
        )
        .copy()
    )


    df[
        "ticker"
    ] = ticker


    df[
        "quarter"
    ] = df.index


    # ========================================================
    # Target
    # ========================================================

    df[
        "revenue"
    ] = (
        sec["revenue"]
        .reindex(idx)
    )


    df[
        "revenue_yoy"
    ] = (
        sec[
            "revenue_yoy"
        ]
        .reindex(idx)
    )


    # ========================================================
    # Financials:
    #
    # Always use previous quarter
    # ========================================================

    financial_cols = [
        "revenue_yoy",
        "assets_yoy",
        "ppe_yoy",
        "debt_yoy",
        "shares_yoy",
        "goodwill_jump",
    ]


    for col in (
        financial_cols
    ):

        df[
            f"{col}_l1"
        ] = (
            sec[col]
            .reindex(idx)
            .shift(1)
        )


    # ========================================================
    # V2.1 Winsorization
    # ========================================================

    df[
        "revenue_yoy_l1_clip"
    ] = (
        df[
            "revenue_yoy_l1"
        ]
        .clip(
            REVENUE_LAG_CLIP_LOW,
            REVENUE_LAG_CLIP_HIGH,
        )
    )


    for col in [
        "assets_yoy_l1",
        "ppe_yoy_l1",
        "debt_yoy_l1",
        "shares_yoy_l1",
    ]:

        df[
            f"{col}_clip"
        ] = (
            df[col]
            .clip(
                FINANCIAL_CLIP_LOW,
                FINANCIAL_CLIP_HIGH,
            )
        )


    df[
        "goodwill_jump_l1_clip"
    ] = (
        df[
            "goodwill_jump_l1"
        ]
        .clip(
            GOODWILL_CLIP_LOW,
            GOODWILL_CLIP_HIGH,
        )
    )


    # ========================================================
    # M&A diagnostic
    #
    # NOT direct model variables
    # ========================================================

    df[
        "ma_event"
    ] = (
        ma[
            "ma_event"
        ]
        .reindex(idx)
        .fillna(0)
    )


    df[
        "ma_window"
    ] = (
        ma[
            "ma_window"
        ]
        .reindex(idx)
        .fillna(0)
    )


    # ========================================================
    # V2.1 M&A Interaction
    #
    # Event alone cannot boost revenue.
    #
    # M&A has to be accompanied by
    # financial size change.
    # ========================================================

    df[
        "ma_assets_interaction"
    ] = (
        df[
            "ma_window"
        ]
        *
        df[
            "assets_yoy_l1_clip"
        ]
    )


    df[
        "ma_ppe_interaction"
    ] = (
        df[
            "ma_window"
        ]
        *
        df[
            "ppe_yoy_l1_clip"
        ]
    )


    df[
        "ma_debt_interaction"
    ] = (
        df[
            "ma_window"
        ]
        *
        df[
            "debt_yoy_l1_clip"
        ]
    )


    df[
        "ma_shares_interaction"
    ] = (
        df[
            "ma_window"
        ]
        *
        df[
            "shares_yoy_l1_clip"
        ]
    )


    df[
        "ma_goodwill_interaction"
    ] = (
        df[
            "ma_window"
        ]
        *
        df[
            "goodwill_jump_l1_clip"
        ]
    )


    return df


# ============================================================
# 15. BUILD PANEL
# ============================================================

def build_panel(
    macro
):

    frames = []


    for ticker in TICKERS:

        try:

            company_df = (
                make_company_dataset(
                    ticker,
                    macro,
                )
            )


            frames.append(
                company_df
            )


        except Exception as e:

            print(
                f"\n❌ {ticker} "
                f"DATA ERROR"
            )

            print(
                repr(e)
            )


    if not frames:

        raise ValueError(
            "사용할 회사 데이터가 없어."
        )


    panel = (
        pd.concat(
            frames,
            axis=0,
            ignore_index=True,
        )
    )


    panel[
        "quarter"
    ] = (
        pd.PeriodIndex(
            panel[
                "quarter"
            ],
            freq="Q",
        )
    )


    panel = (
        panel
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


    save_dataframe(
        panel,
        "energy_v2_1_panel.csv",
        index=False,
    )


    # ========================================================
    # Feature coverage
    #
    # 중요:
    # NaN을 median으로 덮기 전에
    # 진짜 데이터 존재 여부 확인
    # ========================================================

    coverage = (
        panel
        .groupby(
            "ticker"
        )[
            FEATURES_V21
        ]
        .agg(
            lambda x:
                x.notna()
                .mean()
                * 100
        )
        .T
    )


    save_dataframe(
        coverage,
        (
            "energy_v2_1_"
            "feature_coverage.csv"
        ),
    )


    print(
        "\n===== FEATURE COVERAGE (%) ====="
    )

    important = [
        "assets_yoy_l1_clip",
        "ppe_yoy_l1_clip",
        "debt_yoy_l1_clip",
        "shares_yoy_l1_clip",
        "goodwill_jump_l1_clip",
    ]


    print(
        coverage.loc[
            important
        ]
        .round(1)
    )


    return panel


# ============================================================
# 16. DESIGN MATRIX
#
# Includes ticker fixed effects
# ============================================================

def make_design_matrix(
    df,
):

    X = (
        df[
            FEATURES_V21
        ]
        .copy()
    )


    # --------------------------------------------------------
    # ticker fixed effects
    # --------------------------------------------------------

    if len(TICKERS) > 1:

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
# 17. MISSING VALUE HANDLER
#
# Uses TRAINING median only
# ============================================================

def fill_missing_from_train(
    X_train,
    X_test,
):

    X_train = (
        X_train.copy()
    )

    X_test = (
        X_test.copy()
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


    X_test = (
        X_test
        .fillna(
            medians
        )
    )


    return (
        X_train,
        X_test,
        medians,
    )


# ============================================================
# 18. RIDGE MODEL
# ============================================================

def make_model(
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
# 19. TIME-SERIES ALPHA SELECTION
# ============================================================

def select_alpha(
    train_df,
):

    quarters = sorted(
        train_df[
            "quarter"
        ]
        .unique()
    )


    if len(quarters) < 10:

        return 10.0


    validation_count = min(
        4,
        max(
            1,
            len(quarters) - 6
        )
    )


    validation_quarters = (
        quarters[
            -validation_count:
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
            )


            inner_test = (
                train_df[
                    train_df[
                        "quarter"
                    ]
                    == q
                ]
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
                    inner_train
                )
            )


            X_test = (
                make_design_matrix(
                    inner_test
                )
            )


            (
                X_train,
                X_test,
                _
            ) = (
                fill_missing_from_train(
                    X_train,
                    X_test,
                )
            )


            y_train = (
                inner_train[
                    "revenue_yoy"
                ]
                .astype(float)
            )


            y_test = (
                inner_test[
                    "revenue_yoy"
                ]
                .astype(float)
            )


            model = (
                make_model(
                    alpha
                )
            )


            model.fit(
                X_train,
                y_train,
            )


            pred = (
                model.predict(
                    X_test
                )
            )


            errors.append(
                mean_absolute_error(
                    y_test,
                    pred,
                )
            )


        if not errors:

            continue


        avg_mae = float(
            np.mean(
                errors
            )
        )


        if avg_mae < best_mae:

            best_mae = (
                avg_mae
            )

            best_alpha = (
                alpha
            )


    return best_alpha


# ============================================================
# 20. WALK-FORWARD VALIDATION
# ============================================================

def walk_forward_validation(
    panel
):

    history = (
        panel[
            panel[
                "revenue_yoy"
            ]
            .notna()
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
            "Walk-forward history 부족"
        )


    start_test = max(
        MIN_TRAIN_QUARTERS,
        len(quarters)
        - TEST_QUARTERS,
    )


    test_quarters = (
        quarters[
            start_test:
        ]
    )


    records = []


    print(
        "\n"
        + "=" * 80
    )

    print(
        "PANEL WALK-FORWARD VALIDATION V2.1"
    )

    print(
        "=" * 80
    )


    for test_q in (
        test_quarters
    ):

        train = (
            history[
                history[
                    "quarter"
                ]
                < test_q
            ]
            .copy()
        )


        test = (
            history[
                history[
                    "quarter"
                ]
                == test_q
            ]
            .copy()
        )


        if test.empty:

            continue


        alpha = (
            select_alpha(
                train
            )
        )


        X_train = (
            make_design_matrix(
                train
            )
        )


        X_test = (
            make_design_matrix(
                test
            )
        )


        (
            X_train,
            X_test,
            _
        ) = (
            fill_missing_from_train(
                X_train,
                X_test,
            )
        )


        y_train = (
            train[
                "revenue_yoy"
            ]
            .astype(float)
        )


        model = (
            make_model(
                alpha
            )
        )


        model.fit(
            X_train,
            y_train,
        )


        predictions = (
            model.predict(
                X_test
            )
        )


        for (
            (_, row),
            pred
        ) in zip(
            test.iterrows(),
            predictions,
        ):

            records.append(
                {
                    "quarter":
                        test_q,

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

                    "predicted":
                        float(
                            pred
                        ),

                    "naive":
                        0.0,

                    "alpha":
                        alpha,

                    # diagnostics
                    "wti_yoy":
                        row[
                            "wti_yoy"
                        ],

                    "ppe_yoy_l1_clip":
                        row[
                            "ppe_yoy_l1_clip"
                        ],

                    "assets_yoy_l1_clip":
                        row[
                            "assets_yoy_l1_clip"
                        ],

                    "ma_event":
                        row[
                            "ma_event"
                        ],

                    "ma_window":
                        row[
                            "ma_window"
                        ],
                }
            )


    result = (
        pd.DataFrame(
            records
        )
    )


    if result.empty:

        raise ValueError(
            "Validation 결과 없음"
        )


    # ========================================================
    # Overall
    # ========================================================

    model_mae = (
        mean_absolute_error(
            result["actual"],
            result["predicted"],
        )
    )


    model_rmse = (
        np.sqrt(
            mean_squared_error(
                result["actual"],
                result["predicted"],
            )
        )
    )


    naive_mae = (
        mean_absolute_error(
            result["actual"],
            result["naive"],
        )
    )


    improvement = (
        (
            naive_mae
            -
            model_mae
        )
        /
        naive_mae
        * 100
    )


    print(
        f"\nOverall V2.1 MAE : "
        f"{model_mae:.2f} pp"
    )

    print(
        f"Overall RMSE     : "
        f"{model_rmse:.2f} pp"
    )

    print(
        f"Naive MAE        : "
        f"{naive_mae:.2f} pp"
    )

    print(
        f"MAE Improvement  : "
        f"{improvement:+.1f}%"
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

        ticker_mae = (
            mean_absolute_error(
                group["actual"],
                group["predicted"],
            )
        )


        ticker_rmse = (
            np.sqrt(
                mean_squared_error(
                    group["actual"],
                    group["predicted"],
                )
            )
        )


        ticker_naive = (
            mean_absolute_error(
                group["actual"],
                group["naive"],
            )
        )


        ticker_improvement = (
            (
                ticker_naive
                -
                ticker_mae
            )
            /
            ticker_naive
            * 100
        )


        metrics.append(
            {
                "ticker":
                    ticker,

                "V2_1_MAE":
                    ticker_mae,

                "V2_1_RMSE":
                    ticker_rmse,

                "Naive_MAE":
                    ticker_naive,

                "improvement_pct":
                    ticker_improvement,
            }
        )


    metrics_df = (
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
        metrics_df.round(2)
    )


    print(
        "\n===== LAST VALIDATION ROWS ====="
    )

    print(
        result.tail(
            20
        ).round(2)
    )


    save_dataframe(
        result,
        (
            "energy_v2_1_"
            "validation.csv"
        ),
        index=False,
    )


    save_dataframe(
        metrics_df,
        (
            "energy_v2_1_"
            "metrics.csv"
        ),
    )


    return (
        result,
        metrics_df,
    )


# ============================================================
# 21. FINAL MODEL + NOWCAST
# ============================================================

def fit_final_and_nowcast(
    panel
):

    history = (
        panel[
            panel[
                "revenue_yoy"
            ]
            .notna()
        ]
        .copy()
    )


    alpha = (
        select_alpha(
            history
        )
    )


    print(
        f"\nFinal Ridge alpha: "
        f"{alpha}"
    )


    X_train = (
        make_design_matrix(
            history
        )
    )


    medians = (
        X_train
        .replace(
            [
                np.inf,
                -np.inf,
            ],
            np.nan,
        )
        .median(
            axis=0,
            skipna=True,
        )
        .fillna(0)
    )


    X_train = (
        X_train
        .replace(
            [
                np.inf,
                -np.inf,
            ],
            np.nan,
        )
        .fillna(
            medians
        )
    )


    y_train = (
        history[
            "revenue_yoy"
        ]
        .astype(float)
    )


    model = (
        make_model(
            alpha
        )
    )


    model.fit(
        X_train,
        y_train,
    )


    # ========================================================
    # Find next quarter per company
    # ========================================================

    nowcast_rows = []


    for ticker in TICKERS:

        company_df = (
            panel[
                panel[
                    "ticker"
                ]
                == ticker
            ]
            .copy()
        )


        actual = (
            company_df[
                company_df[
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


        row = (
            company_df[
                company_df[
                    "quarter"
                ]
                == nowcast_q
            ]
        )


        if row.empty:

            print(
                f"⚠️ {ticker}: "
                f"{nowcast_q} "
                f"macro feature 없음"
            )

            continue


        row = (
            row.iloc[0]
            .copy()
        )


        row[
            "nowcast_quarter"
        ] = nowcast_q


        nowcast_rows.append(
            row
        )


    if not nowcast_rows:

        raise ValueError(
            "Nowcast 가능한 종목 없음"
        )


    now_df = (
        pd.DataFrame(
            nowcast_rows
        )
    )


    X_now = (
        make_design_matrix(
            now_df
        )
    )


    X_now = (
        X_now
        .replace(
            [
                np.inf,
                -np.inf,
            ],
            np.nan,
        )
        .fillna(
            medians
        )
    )


    prediction = (
        model.predict(
            X_now
        )
    )


    now_df[
        "predicted_revenue_yoy"
    ] = (
        prediction
    )


    # ========================================================
    # YoY -> Revenue dollars
    # ========================================================

    revenue_estimates = []


    for _, row in (
        now_df.iterrows()
    ):

        ticker = (
            row[
                "ticker"
            ]
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

            revenue_estimates.append(
                np.nan
            )

            continue


        base_revenue = float(
            base.iloc[0][
                "revenue"
            ]
        )


        estimate = (
            base_revenue
            *
            np.exp(
                row[
                    "predicted_revenue_yoy"
                ]
                / 100
            )
        )


        revenue_estimates.append(
            estimate
        )


    now_df[
        "predicted_revenue"
    ] = (
        revenue_estimates
    )


    now_df[
        "predicted_revenue_B"
    ] = (
        now_df[
            "predicted_revenue"
        ]
        / 1e9
    )


    # ========================================================
    # Output
    # ========================================================

    output_cols = [

        "ticker",
        "nowcast_quarter",

        "predicted_revenue_yoy",
        "predicted_revenue",
        "predicted_revenue_B",

        "wti_yoy",
        "henry_yoy",

        "assets_yoy_l1_clip",
        "ppe_yoy_l1_clip",
        "debt_yoy_l1_clip",
        "shares_yoy_l1_clip",
        "goodwill_jump_l1_clip",

        # diagnostic only
        "ma_event",
        "ma_window",

        # actual model inputs
        "ma_assets_interaction",
        "ma_ppe_interaction",
        "ma_debt_interaction",
        "ma_shares_interaction",
        "ma_goodwill_interaction",
    ]


    output = (
        now_df[
            output_cols
        ]
        .copy()
    )


    print(
        "\n"
        + "=" * 80
    )

    print(
        "🚀 ENERGY REVENUE V2.1 NOWCAST"
    )

    print(
        "=" * 80
    )


    display_cols = [

        "ticker",
        "nowcast_quarter",

        "predicted_revenue_yoy",
        "predicted_revenue_B",

        "wti_yoy",

        "assets_yoy_l1_clip",
        "ppe_yoy_l1_clip",

        "ma_event",
        "ma_window",

        "ma_assets_interaction",
        "ma_ppe_interaction",
    ]


    print(
        output[
            display_cols
        ]
        .round(2)
        .to_string(
            index=False
        )
    )


    # ========================================================
    # Standardized coefficients
    # ========================================================

    ridge = (
        model
        .named_steps[
            "ridge"
        ]
    )


    coefficients = (
        pd.Series(
            ridge.coef_,
            index=X_train.columns,
        )
        .sort_values(
            key=np.abs,
            ascending=False,
        )
    )


    print(
        "\n===== STANDARDIZED COEFFICIENTS ====="
    )


    print(
        coefficients.round(
            3
        )
    )


    save_dataframe(
        output,
        (
            "energy_v2_1_"
            "nowcast.csv"
        ),
        index=False,
    )


    save_dataframe(
        coefficients.to_frame(
            "coefficient"
        ),
        (
            "energy_v2_1_"
            "coefficients.csv"
        ),
    )


    return (
        model,
        output,
        coefficients,
    )


# ============================================================
# 22. MAIN
# ============================================================

def main():

    # ========================================================
    # Macro
    # ========================================================

    print(
        "\n"
        + "=" * 80
    )

    print(
        "1. MACRO DATA"
    )

    print(
        "=" * 80
    )


    macro = (
        make_macro_features()
    )


    macro_features = [

        "wti_yoy",
        "henry_yoy",

        "crude_prod_yoy_l1",
        "gas_prod_yoy_l1",

        "bea_go_yoy_l1",
    ]


    print(
        "\n===== MACRO FEATURES ====="
    )


    print(
        macro[
            macro_features
        ]
        .tail(12)
        .round(2)
    )


    # ========================================================
    # Panel
    # ========================================================

    print(
        "\n"
        + "=" * 80
    )

    print(
        "2. BUILD COMPANY PANEL"
    )

    print(
        "=" * 80
    )


    panel = (
        build_panel(
            macro
        )
    )


    print(
        "\nPanel shape:",
        panel.shape
    )


    print(
        "\nRevenue observations:"
    )


    print(
        panel[
            panel[
                "revenue"
            ]
            .notna()
        ]
        .groupby(
            "ticker"
        )[
            "revenue"
        ]
        .count()
    )


    # ========================================================
    # Walk-forward validation
    # ========================================================

    validation, metrics = (
        walk_forward_validation(
            panel
        )
    )


    # ========================================================
    # Final nowcast
    # ========================================================

    (
        model,
        nowcast,
        coefficients,
    ) = (
        fit_final_and_nowcast(
            panel
        )
    )


    # ========================================================
    # Done
    # ========================================================

    print(
        "\n"
        + "=" * 80
    )

    print(
        "DONE"
    )

    print(
        "=" * 80
    )


    print(
        "\nData lake:"
    )

    print(
        DATA_LAKE_DIR.resolve()
    )


    print(
        "\nMain outputs:"
    )

    for filename in [

        "energy_v2_1_macro.csv",

        "energy_v2_1_panel.csv",

        "energy_v2_1_feature_coverage.csv",

        "energy_v2_1_validation.csv",

        "energy_v2_1_metrics.csv",

        "energy_v2_1_nowcast.csv",

        "energy_v2_1_coefficients.csv",

    ]:

        print(
            " -",
            lake_path(
                filename
            )
        )


if __name__ == "__main__":

    main()
