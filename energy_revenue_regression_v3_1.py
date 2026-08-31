# ============================================================
# ENERGY REVENUE NOWCAST V3.1
#
# 핵심 변경:
#
# V3:
#   filing-level XBRL custom tag 자동 추측
#
# V3.1:
#   8-K Item 2.02 earnings release
#   EX-99.1 / EX-99.2
#   실제 텍스트 + HTML TABLE에서
#
#   - Total production
#   - Oil production
#   - Gas production
#   - Realized oil price
#   - Realized gas price
#   - Realized combined price
#   - Next-quarter production guidance
#
#   를 직접 추출
#
# 모델:
#
# Structural Revenue YoY
# =
# Price Mix YoY
# +
# Company Production YoY Proxy
#
# Company Production YoY Proxy:
#
# 1. current-quarter guidance가 있으면 최우선
# 2. 없으면 previous-quarter company production YoY
# 3. 없으면 company oil production YoY
# 4. 없으면 EIA industry production fallback
#
# Final V3.1:
#
# Revenue YoY
# =
# Structural Revenue YoY
# +
# Ridge residual correction
#
#
# Required existing files:
#
# ./data-lake/energy_v2_1_macro.csv
# ./data-lake/energy_v2_1_panel.csv
#
#
# Required ENV:
# EDGAR_IDENTITY
#
# Optional ENV:
#
# DATA_LAKE_DIR=./data-lake
# TICKERS=COP,EOG,FANG,DVN
# AS_OF_DATE=2026-08-31
# REFRESH_KPI=1
# EARNINGS_LOOKBACK_FILINGS=50
#
# ============================================================


import os
import re
import json
import warnings

from io import StringIO
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


warnings.filterwarnings(
    "ignore"
)


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


EARNINGS_LOOKBACK_FILINGS = int(
    os.getenv(
        "EARNINGS_LOOKBACK_FILINGS",
        "50",
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


MIN_FEATURE_COVERAGE = float(
    os.getenv(
        "MIN_FEATURE_COVERAGE",
        "0.35",
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
# 1. CONFIG CHECK
# ============================================================

if not EDGAR_IDENTITY:

    raise ValueError(

        "EDGAR_IDENTITY 환경변수가 없어.\n\n"

        'export EDGAR_IDENTITY='
        '"Your Name your_email@example.com"'

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
    "ENERGY REVENUE NOWCAST V3.1"
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
# 2. LOAD V2.1 DATA
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
        "V2.1을 먼저 실행해줘."

    )


if not PANEL_FILE.exists():

    raise FileNotFoundError(

        f"{PANEL_FILE} 없음.\n"
        "V2.1을 먼저 실행해줘."

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
# 3. GENERIC HELPERS
# ============================================================

def normalize_text(
    text
):

    if text is None:

        return ""

    text = str(
        text
    )

    text = (
        text
        .replace("\xa0", " ")
        .replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return (
        text.strip()
    )


def numeric_token(
    value
):

    if value is None:

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


    text = str(
        value
    ).strip()


    # $(2.15)
    negative = (
        "(" in text
        and ")" in text
    )


    text = (
        text
        .replace("$", "")
        .replace(",", "")
        .replace("(", "")
        .replace(")", "")
        .replace("%", "")
        .strip()
    )


    try:

        number = float(
            text
        )

    except Exception:

        return np.nan


    if negative:

        number = (
            -abs(number)
        )


    return number


def log_growth(
    series,
    periods=4,
):

    series = pd.to_numeric(
        series,
        errors="coerce",
    )


    lagged = (
        series.shift(
            periods
        )
    )


    output = pd.Series(
        np.nan,
        index=series.index,
        dtype=float,
    )


    valid = (
        (series > 0)
        &
        (lagged > 0)
    )


    output.loc[
        valid
    ] = (

        np.log(

            series.loc[
                valid
            ]
            /
            lagged.loc[
                valid
            ]

        )
        * 100

    )


    return output


# ============================================================
# 4. QUARTER INFERENCE
# ============================================================

MONTH_MAP = {

    "january": 1,
    "february": 2,
    "march": 3,

    "april": 4,
    "may": 5,
    "june": 6,

    "july": 7,
    "august": 8,
    "september": 9,

    "october": 10,
    "november": 11,
    "december": 12,

}


QUARTER_WORD_MAP = {

    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,

}


def infer_result_quarter(
    filing_date,
    text
):

    text_lower = (
        normalize_text(
            text
        )
        .lower()
    )


    # ========================================================
    # "quarter ended June 30, 2026"
    # ========================================================

    match = re.search(

        r"quarter\s+ended\s+"

        r"(january|february|march|april|may|june|"
        r"july|august|september|october|november|december)"

        r"\s+\d{1,2},?\s+"

        r"(20\d{2})",

        text_lower,

        flags=re.IGNORECASE,

    )


    if match:

        month = MONTH_MAP[
            match.group(1).lower()
        ]

        year = int(
            match.group(2)
        )


        quarter = (
            (month - 1)
            // 3
            + 1
        )


        return pd.Period(
            f"{year}Q{quarter}",
            freq="Q",
        )


    # ========================================================
    # "second quarter 2026"
    # ========================================================

    match = re.search(

        r"(first|second|third|fourth)"
        r"\s+quarter"

        r"(?:\s+of)?"
        r"\s+(20\d{2})",

        text_lower,

        flags=re.IGNORECASE,

    )


    if match:

        quarter = (
            QUARTER_WORD_MAP[
                match.group(1).lower()
            ]
        )

        year = int(
            match.group(2)
        )


        return pd.Period(
            f"{year}Q{quarter}",
            freq="Q",
        )


    # ========================================================
    # Filing date fallback
    #
    # Jan-Mar  -> previous Q4
    # Apr-Jun  -> current Q1
    # Jul-Sep  -> current Q2
    # Oct-Dec  -> current Q3
    # ========================================================

    filing_date = pd.Timestamp(
        filing_date
    )


    month = (
        filing_date.month
    )

    year = (
        filing_date.year
    )


    if month <= 3:

        return pd.Period(
            f"{year - 1}Q4",
            freq="Q",
        )


    if month <= 6:

        return pd.Period(
            f"{year}Q1",
            freq="Q",
        )


    if month <= 9:

        return pd.Period(
            f"{year}Q2",
            freq="Q",
        )


    return pd.Period(
        f"{year}Q3",
        freq="Q",
    )


# ============================================================
# 5. UNIT CONVERSION
# ============================================================

def to_mboed(
    value,
    unit
):

    value = numeric_token(
        value
    )

    if pd.isna(
        value
    ):

        return np.nan


    unit = (
        normalize_text(
            unit
        )
        .lower()
    )


    # 1,359,000 Boe per day
    if (
        "boe per day" in unit
        or "boe/day" in unit
        or "boe/d" in unit
    ):

        if (
            "mboe" not in unit
            and
            "mmboe" not in unit
        ):

            return (
                value
                / 1000
            )


    # million BOE/day
    if (
        "mmboe" in unit
        or
        "million barrels of oil equivalent"
        in unit
    ):

        return (
            value
            * 1000
        )


    # MBOE/D
    if (
        "mboe" in unit
        or
        "mboed" in unit
    ):

        return value


    # Raw Boe/day inferred from huge number
    if value > 10000:

        return (
            value
            / 1000
        )


    return value


def to_mbod(
    value,
    unit
):

    value = numeric_token(
        value
    )

    if pd.isna(value):

        return np.nan


    unit = (
        normalize_text(
            unit
        )
        .lower()
    )


    if (
        "barrels per day"
        in unit
        or
        "bbl per day"
        in unit
        or
        "bbl/day"
        in unit
    ):

        if (
            "mbo" not in unit
            and
            "mbbl" not in unit
        ):

            return (
                value
                / 1000
            )


    if (
        "mmbo" in unit
        or
        "million barrels per day"
        in unit
    ):

        return (
            value
            * 1000
        )


    if (
        "mbo/d" in unit
        or
        "mbod" in unit
        or
        "mbbl/d" in unit
        or
        "mbbls/d" in unit
    ):

        return value


    if value > 10000:

        return (
            value
            / 1000
        )


    return value


def to_mmcfd(
    value,
    unit
):

    value = numeric_token(
        value
    )

    if pd.isna(value):

        return np.nan


    unit = (
        normalize_text(
            unit
        )
        .lower()
    )


    if (
        "bcf/d" in unit
        or
        "bcf per day" in unit
    ):

        return (
            value
            * 1000
        )


    if (
        "mmcf/d" in unit
        or
        "mmcfd" in unit
        or
        "million cubic feet per day"
        in unit
    ):

        return value


    if (
        "mcf/d" in unit
        or
        "mcf per day" in unit
    ):

        return (
            value
            / 1000
        )


    return value


# ============================================================
# 6. PLAUSIBILITY LIMITS
# ============================================================

LIMITS = {

    "total_production": (
        20,
        5000,
    ),

    "oil_production": (
        10,
        3000,
    ),

    "gas_production": (
        20,
        20000,
    ),

    "realized_oil_price": (
        10,
        250,
    ),

    "realized_gas_price": (
        -20,
        30,
    ),

    "realized_combined_price": (
        5,
        200,
    ),

}


def plausible(
    kpi,
    value
):

    if pd.isna(value):

        return False


    low, high = (
        LIMITS[
            kpi
        ]
    )


    return (
        low
        <= value
        <= high
    )


# ============================================================
# 7. CANDIDATE STORAGE
# ============================================================

def candidate(
    ticker,
    quarter,
    kpi,
    value,
    score,
    filing_date,
    source,
    method,
    raw_text,
):

    return {

        "ticker":
            ticker,

        "quarter":
            str(
                quarter
            ),

        "kpi":
            kpi,

        "value":
            value,

        "score":
            score,

        "filing_date":
            filing_date,

        "source":
            source,

        "method":
            method,

        "raw_text":
            normalize_text(
                raw_text
            )[:1000],

    }


# ============================================================
# 8. PROSE EXTRACTION
# ============================================================

NUMBER = (
    r"(?P<value>"
    r"\(?-?\$?[\d,]+(?:\.\d+)?\)?"
    r")"
)


def extract_actual_from_text(
    ticker,
    quarter,
    text,
    filing_date,
    source,
):

    text = normalize_text(
        text
    )


    results = []


    # ========================================================
    # TOTAL PRODUCTION
    # ========================================================

    total_patterns = [

        # Devon
        (
            r"production\s+averaged\s+"
            + NUMBER
            +
            r"\s*"
            r"(?P<unit>"
            r"boe\s+per\s+day|"
            r"boe/d|"
            r"mboe/d|"
            r"mboed|"
            r"mmboe/d"
            r")"
        ),

        # FANG
        (
            r"production\s+of\s+"
            + NUMBER
            +
            r"\s*"
            r"(?P<unit>"
            r"mboe/d|"
            r"mboed|"
            r"boe/d"
            r")"
        ),

        # COP
        (
            r"production"
            r"(?:\s+for\s+the\s+"
            r"(?:first|second|third|fourth)"
            r"\s+quarter)?"
            r"\s+(?:was|averaged)\s+"
            + NUMBER
            +
            r"\s*"
            r"(?P<unit>"
            r"mboed|"
            r"mboe/d|"
            r"boe\s+per\s+day|"
            r"mmboed|"
            r"million\s+barrels\s+of\s+"
            r"oil\s+equivalent\s+per\s+day"
            r")"
        ),

        (
            r"total\s+production"
            r".{0,40}?"
            + NUMBER
            +
            r"\s*"
            r"(?P<unit>"
            r"mboe/d|"
            r"mboed|"
            r"boe\s+per\s+day"
            r")"
        ),

    ]


    for pattern in total_patterns:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )


        if match:

            value = to_mboed(
                match.group(
                    "value"
                ),
                match.group(
                    "unit"
                ),
            )


            if plausible(
                "total_production",
                value
            ):

                results.append(

                    candidate(
                        ticker,
                        quarter,
                        "total_production",
                        value,
                        100,
                        filing_date,
                        source,
                        "prose",
                        match.group(0),
                    )

                )

                break


    # ========================================================
    # OIL PRODUCTION
    # ========================================================

    oil_patterns = [

        # Devon
        (
            r"oil\s+totaled\s+"
            + NUMBER
            +
            r"\s*"
            r"(?P<unit>"
            r"barrels\s+per\s+day|"
            r"bbl/d|"
            r"mbo/d|"
            r"mbod"
            r")"
        ),

        # FANG
        (
            r"average\s+oil\s+production"
            r"(?:\s+of)?\s+"
            + NUMBER
            +
            r"\s*"
            r"(?P<unit>"
            r"mbo/d|"
            r"mbod|"
            r"barrels\s+per\s+day"
            r")"
        ),

        (
            r"oil\s+production"
            r".{0,30}?"
            r"(?:averaged|was|of)?\s*"
            + NUMBER
            +
            r"\s*"
            r"(?P<unit>"
            r"mbo/d|"
            r"mbod|"
            r"barrels\s+per\s+day|"
            r"bbl/d"
            r")"
        ),

    ]


    for pattern in oil_patterns:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )


        if match:

            value = to_mbod(
                match.group(
                    "value"
                ),
                match.group(
                    "unit"
                ),
            )


            if plausible(
                "oil_production",
                value
            ):

                results.append(

                    candidate(
                        ticker,
                        quarter,
                        "oil_production",
                        value,
                        100,
                        filing_date,
                        source,
                        "prose",
                        match.group(0),
                    )

                )

                break


    # ========================================================
    # COMBINED REALIZED PRICE
    # ========================================================

    combined_patterns = [

        (
            r"(?:total\s+)?realized\s+price"
            r".{0,50}?"
            + NUMBER
            +
            r"\s+per\s+boe"
        ),

        (
            r"realized\s+price"
            r".{0,80}?"
            + NUMBER
            +
            r"\s*(?:/|per)\s*boe"
        ),

    ]


    for pattern in combined_patterns:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )


        if match:

            value = numeric_token(
                match.group(
                    "value"
                )
            )


            if plausible(
                "realized_combined_price",
                value
            ):

                results.append(

                    candidate(
                        ticker,
                        quarter,
                        "realized_combined_price",
                        value,
                        95,
                        filing_date,
                        source,
                        "prose",
                        match.group(0),
                    )

                )

                break


    # ========================================================
    # REALIZED OIL PRICE
    # ========================================================

    oil_price_patterns = [

        # FANG
        (
            r"(?:average\s+)?"
            r"(?:unhedged\s+)?"
            r"realized\s+prices?\s+were\s+"
            + NUMBER
            +
            r"\s+per\s+barrel\s+of\s+oil"
        ),

        # Devon
        (
            r"realized\s+price"
            r".{0,100}?"
            + NUMBER
            +
            r"\s+per\s+barrel\s+of\s+oil"
        ),

        (
            r"oil"
            r".{0,30}?"
            r"(?:realized|realisation)"
            r".{0,30}?"
            + NUMBER
            +
            r"\s*(?:/|per)\s*(?:bbl|barrel)"
        ),

    ]


    for pattern in oil_price_patterns:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )


        if match:

            value = numeric_token(
                match.group(
                    "value"
                )
            )


            if plausible(
                "realized_oil_price",
                value
            ):

                results.append(

                    candidate(
                        ticker,
                        quarter,
                        "realized_oil_price",
                        value,
                        95,
                        filing_date,
                        source,
                        "prose",
                        match.group(0),
                    )

                )

                break


    # ========================================================
    # REALIZED GAS PRICE
    # ========================================================

    gas_price_patterns = [

        # FANG sentence
        (
            r"realized\s+prices?\s+were"
            r".{0,100}?"
            r",\s*"
            + NUMBER
            +
            r"\s+per\s+mcf\s+of\s+natural\s+gas"
        ),

        # Devon
        (
            r"realized\s+price"
            r".{0,180}?"
            r",\s*"
            + NUMBER
            +
            r"\s+per\s+mcf\s+of\s+natural\s+gas"
        ),

        (
            r"natural\s+gas"
            r".{0,30}?"
            r"(?:realized|price)"
            r".{0,30}?"
            + NUMBER
            +
            r"\s*(?:/|per)\s*mcf"
        ),

    ]


    for pattern in gas_price_patterns:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )


        if match:

            value = numeric_token(
                match.group(
                    "value"
                )
            )


            if plausible(
                "realized_gas_price",
                value
            ):

                results.append(

                    candidate(
                        ticker,
                        quarter,
                        "realized_gas_price",
                        value,
                        95,
                        filing_date,
                        source,
                        "prose",
                        match.group(0),
                    )

                )

                break


    return results


# ============================================================
# 9. TABLE PARSING
# ============================================================

TABLE_RULES = {

    "total_production": [

        r"total\s+production.*mboe",
        r"net\s+production.*mboe",
        r"total.*mboe/d",
        r"total.*mboed",

    ],

    "oil_production": [

        r"oil\s+production.*mbo",
        r"crude\s+oil.*condensate.*mbo",
        r"oil.*mbod",

    ],

    "gas_production": [

        r"natural\s+gas.*mmcf",
        r"gas\s+production.*mmcf",

    ],

    "realized_oil_price": [

        r"oil.*per\s+bbl",
        r"oil.*\$/bbl",
        r"crude\s+oil.*price",

    ],

    "realized_gas_price": [

        r"natural\s+gas.*per\s+mcf",
        r"natural\s+gas.*\$/mcf",

    ],

    "realized_combined_price": [

        r"combined.*per\s+boe",
        r"combined.*\$/boe",
        r"total\s+realized.*boe",

    ],

}


def find_numeric_tokens(
    text
):

    tokens = re.findall(

        r"\(?-?\$?"
        r"\d[\d,]*"
        r"(?:\.\d+)?"
        r"\)?",

        text,

    )


    output = []


    for token in tokens:

        value = numeric_token(
            token
        )


        if pd.isna(value):

            continue


        # Remove calendar years
        if (
            1990
            <= value
            <= 2100
        ):

            continue


        output.append(
            value
        )


    return output


def choose_plausible_table_value(
    kpi,
    row_text
):

    values = find_numeric_tokens(
        row_text
    )


    for value in values:

        adjusted = value


        if kpi == (
            "total_production"
        ):

            if (
                value > 10000
                and
                re.search(
                    r"boe\s+per\s+day",
                    row_text,
                    flags=re.I,
                )
            ):

                adjusted = (
                    value
                    / 1000
                )


        elif kpi == (
            "oil_production"
        ):

            if (
                value > 10000
                and
                re.search(
                    r"barrels\s+per\s+day",
                    row_text,
                    flags=re.I,
                )
            ):

                adjusted = (
                    value
                    / 1000
                )


        if plausible(
            kpi,
            adjusted
        ):

            return adjusted


    return np.nan


def extract_from_tables(
    ticker,
    quarter,
    tables,
    filing_date,
    source,
):

    results = []


    for table_number, table in enumerate(
        tables
    ):

        if table is None:

            continue


        try:

            table = (
                table
                .copy()
                .fillna("")
            )

        except Exception:

            continue


        for _, row in (
            table.iterrows()
        ):

            row_text = normalize_text(

                " | ".join(

                    str(x)

                    for x
                    in row.tolist()

                )

            )


            if not row_text:

                continue


            for kpi, patterns in (
                TABLE_RULES.items()
            ):

                matched = any(

                    re.search(
                        pattern,
                        row_text,
                        flags=re.I,
                    )

                    for pattern
                    in patterns

                )


                if not matched:

                    continue


                value = (
                    choose_plausible_table_value(
                        kpi,
                        row_text,
                    )
                )


                if not plausible(
                    kpi,
                    value
                ):

                    continue


                results.append(

                    candidate(
                        ticker,
                        quarter,
                        kpi,
                        value,
                        80,
                        filing_date,
                        (
                            f"{source}:"
                            f"table{table_number}"
                        ),
                        "table",
                        row_text,
                    )

                )


    return results


# ============================================================
# 10. GUIDANCE EXTRACTION
# ============================================================

QUARTER_PATTERN = {

    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,

}


def extract_guidance(
    ticker,
    text,
    filing_date,
    source,
):

    text = normalize_text(
        text
    )


    results = []


    # ========================================================
    # Devon-like:
    #
    # In the third quarter of 2026,
    # total production is expected to average
    # between 1,660,000 and 1,690,000 Boe per day
    # ========================================================

    pattern = (

        r"(?:in|for)\s+the\s+"

        r"(?P<qword>"
        r"first|second|third|fourth"
        r")"

        r"\s+quarter"
        r"(?:\s+of)?\s+"

        r"(?P<year>20\d{2})"

        r".{0,200}?"

        r"(?:total\s+)?production"

        r".{0,100}?"

        r"(?:between|range(?:d|s)?\s+(?:from)?|of)"

        r"\s*"

        r"(?P<low>"
        r"[\d,.]+"
        r")"

        r"\s*"

        r"(?:and|to|-)\s*"

        r"(?P<high>"
        r"[\d,.]+"
        r")"

        r"\s*"

        r"(?P<unit>"
        r"boe\s+per\s+day|"
        r"mboe/d|"
        r"mboed|"
        r"mmboed|"
        r"million\s+barrels\s+of\s+"
        r"oil\s+equivalent\s+per\s+day"
        r")"

    )


    match = re.search(
        pattern,
        text,
        flags=re.I,
    )


    if match:

        q = QUARTER_PATTERN[
            match.group(
                "qword"
            ).lower()
        ]

        year = int(
            match.group(
                "year"
            )
        )


        target_q = pd.Period(
            f"{year}Q{q}",
            freq="Q",
        )


        low = to_mboed(
            match.group(
                "low"
            ),
            match.group(
                "unit"
            ),
        )


        high = to_mboed(
            match.group(
                "high"
            ),
            match.group(
                "unit"
            ),
        )


        midpoint = (
            low + high
        ) / 2


        if plausible(
            "total_production",
            midpoint
        ):

            results.append({

                "ticker":
                    ticker,

                "target_quarter":
                    str(
                        target_q
                    ),

                "guidance_total_production":
                    midpoint,

                "guidance_oil_production":
                    np.nan,

                "filing_date":
                    filing_date,

                "source":
                    source,

                "method":
                    "prose_guidance",

                "raw_text":
                    match.group(0)[:1000],

            })


    # ========================================================
    # FANG table-style text:
    #
    # Q3 2026 Oil production - MBO/d
    # (total - MBOE/d)
    # 517 - 527
    # (995 - 1,015)
    # ========================================================

    fang_pattern = (

        r"q(?P<quarter>[1-4])"
        r"\s+(?P<year>20\d{2})"

        r".{0,120}?"

        r"oil\s+production"

        r".{0,100}?"

        r"(?P<oil_low>\d[\d,.]*)"
        r"\s*-\s*"
        r"(?P<oil_high>\d[\d,.]*)"

        r".{0,80}?"

        r"\("

        r"(?P<total_low>\d[\d,.]*)"
        r"\s*-\s*"
        r"(?P<total_high>\d[\d,.]*)"

        r"\)"

    )


    match = re.search(
        fang_pattern,
        text,
        flags=re.I,
    )


    if match:

        target_q = pd.Period(

            (
                f"{match.group('year')}"
                f"Q{match.group('quarter')}"
            ),

            freq="Q",

        )


        oil_low = numeric_token(
            match.group(
                "oil_low"
            )
        )

        oil_high = numeric_token(
            match.group(
                "oil_high"
            )
        )


        total_low = numeric_token(
            match.group(
                "total_low"
            )
        )

        total_high = numeric_token(
            match.group(
                "total_high"
            )
        )


        oil_mid = (
            oil_low + oil_high
        ) / 2


        total_mid = (
            total_low + total_high
        ) / 2


        if (
            plausible(
                "total_production",
                total_mid
            )
            and
            plausible(
                "oil_production",
                oil_mid
            )
        ):

            results.append({

                "ticker":
                    ticker,

                "target_quarter":
                    str(
                        target_q
                    ),

                "guidance_total_production":
                    total_mid,

                "guidance_oil_production":
                    oil_mid,

                "filing_date":
                    filing_date,

                "source":
                    source,

                "method":
                    "fang_guidance",

                "raw_text":
                    match.group(0)[:1000],

            })


    return results


# ============================================================
# 11. ATTACHMENT CONTENT
# ============================================================

def get_attachment_text(
    attachment
):

    try:

        text = (
            attachment.text()
        )

        if text:

            return normalize_text(
                text
            )

    except Exception:

        pass


    return ""


def get_attachment_tables(
    attachment
):

    try:

        if (
            hasattr(
                attachment,
                "is_html",
            )
            and
            not attachment.is_html()
        ):

            return []


    except Exception:

        pass


    try:

        content = (
            attachment.download()
        )

    except Exception:

        return []


    if content is None:

        return []


    if isinstance(
        content,
        bytes,
    ):

        content = content.decode(
            "utf-8",
            errors="ignore",
        )


    if not isinstance(
        content,
        str,
    ):

        return []


    try:

        tables = pd.read_html(
            StringIO(
                content
            )
        )

        return tables

    except Exception:

        return []


# ============================================================
# 12. SCAN COMPANY EARNINGS RELEASES
# ============================================================

def scan_company_earnings(
    ticker
):

    print(
        "\n"
        + "=" * 80
    )

    print(
        f"8-K EARNINGS KPI SCAN: {ticker}"
    )

    print(
        "=" * 80
    )


    company = Company(
        ticker
    )


    filings = (
        company
        .get_filings(
            form="8-K"
        )
    )


    start_date = (
        AS_OF
        -
        pd.DateOffset(
            years=10
        )
    )


    try:

        filings = (
            filings.filter(
                filing_date=(
                    f"{start_date.date()}:"
                    f"{AS_OF.date()}"
                )
            )
        )

    except Exception:

        pass


    actual_candidates = []
    guidance_candidates = []


    filing_count = 0


    for filing in filings:

        if (
            filing_count
            >=
            EARNINGS_LOOKBACK_FILINGS
        ):

            break


        filing_date = pd.to_datetime(

            getattr(
                filing,
                "filing_date",
                None,
            ),

            errors="coerce",

        )


        if pd.isna(
            filing_date
        ):

            continue


        if (
            filing_date
            > AS_OF
        ):

            continue


        items = str(
            getattr(
                filing,
                "items",
                "",
            )
        )


        # Earnings 8-K 우선
        if (
            "2.02" not in items
            and
            "7.01" not in items
        ):

            continue


        documents = []


        # ====================================================
        # EX-99.X earnings releases
        # ====================================================

        try:

            for exhibit in (
                filing.exhibits
            ):

                doc_type = str(

                    getattr(
                        exhibit,
                        "document_type",
                        "",
                    )

                ).upper()


                if not (
                    doc_type.startswith(
                        "EX-99"
                    )
                ):

                    continue


                documents.append(
                    exhibit
                )

        except Exception:

            pass


        # ====================================================
        # Primary filing fallback
        # ====================================================

        if not documents:

            try:

                documents.append(
                    filing.document
                )

            except Exception:

                pass


        for attachment in documents:

            if attachment is None:

                continue


            source = (
                f"{filing_date.date()}:"

                f"{getattr(attachment,'document_type','')}:"

                f"{getattr(attachment,'document','')}"
            )


            text = (
                get_attachment_text(
                    attachment
                )
            )


            if not text:

                continue


            quarter = (
                infer_result_quarter(
                    filing_date,
                    text,
                )
            )


            print(
                f"  {quarter} "
                f"{source}"
            )


            # =================================================
            # Actual KPI prose
            # =================================================

            actual_candidates.extend(

                extract_actual_from_text(
                    ticker,
                    quarter,
                    text,
                    filing_date,
                    source,
                )

            )


            # =================================================
            # HTML tables
            # =================================================

            tables = (
                get_attachment_tables(
                    attachment
                )
            )


            actual_candidates.extend(

                extract_from_tables(
                    ticker,
                    quarter,
                    tables,
                    filing_date,
                    source,
                )

            )


            # =================================================
            # Next-quarter guidance
            # =================================================

            guidance_candidates.extend(

                extract_guidance(
                    ticker,
                    text,
                    filing_date,
                    source,
                )

            )


        filing_count += 1


    actual_df = pd.DataFrame(
        actual_candidates
    )


    guidance_df = pd.DataFrame(
        guidance_candidates
    )


    actual_file = lake_path(
        f"energy_v3_1_kpi_candidates_"
        f"{ticker}.csv"
    )


    guidance_file = lake_path(
        f"energy_v3_1_guidance_candidates_"
        f"{ticker}.csv"
    )


    actual_df.to_csv(
        actual_file,
        index=False,
    )


    guidance_df.to_csv(
        guidance_file,
        index=False,
    )


    print(
        f"  💾 {actual_file}"
    )

    print(
        f"  💾 {guidance_file}"
    )


    return (
        actual_df,
        guidance_df,
    )


# ============================================================
# 13. SELECT BEST KPI CANDIDATES
# ============================================================

def select_best_actual_kpis(
    ticker,
    candidates
):

    if candidates.empty:

        return pd.DataFrame()


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


    work[
        "filing_date"
    ] = (
        pd.to_datetime(
            work[
                "filing_date"
            ],
            errors="coerce",
        )
    )


    selected = []


    for (
        quarter,
        kpi
    ), group in (
        work.groupby(
            [
                "quarter",
                "kpi",
            ]
        )
    ):

        # prose > table
        best = (

            group
            .sort_values(

                [
                    "score",
                    "filing_date",
                ],

                ascending=[
                    False,
                    False,
                ],

            )
            .iloc[0]

        )


        selected.append(
            best
        )


    selected_df = pd.DataFrame(
        selected
    )


    selected_file = lake_path(
        f"energy_v3_1_kpi_selected_"
        f"{ticker}.csv"
    )


    selected_df.to_csv(
        selected_file,
        index=False,
    )


    print(
        f"  💾 {selected_file}"
    )


    wide = (
        selected_df
        .pivot_table(

            index="quarter",

            columns="kpi",

            values="value",

            aggfunc="last",

        )
        .sort_index()
    )


    wide.index = (
        pd.PeriodIndex(
            wide.index,
            freq="Q",
        )
    )


    return wide


# ============================================================
# 14. SELECT GUIDANCE
# ============================================================

def select_guidance(
    ticker,
    guidance
):

    if guidance.empty:

        return pd.DataFrame()


    work = (
        guidance.copy()
    )


    work[
        "target_quarter"
    ] = (
        pd.PeriodIndex(

            work[
                "target_quarter"
            ].astype(str),

            freq="Q",

        )
    )


    work[
        "filing_date"
    ] = (
        pd.to_datetime(
            work[
                "filing_date"
            ],
            errors="coerce",
        )
    )


    selected = []


    for quarter, group in (
        work.groupby(
            "target_quarter"
        )
    ):

        # ====================================================
        # Guidance must be known before quarter end
        # ====================================================

        quarter_end = (
            quarter.end_time
        )


        valid = (
            group[
                group[
                    "filing_date"
                ]
                <= quarter_end
            ]
        )


        if valid.empty:

            continue


        best = (

            valid
            .sort_values(
                "filing_date"
            )
            .iloc[-1]

        )


        selected.append(
            best
        )


    selected_df = pd.DataFrame(
        selected
    )


    if selected_df.empty:

        return pd.DataFrame()


    selected_file = lake_path(
        f"energy_v3_1_guidance_selected_"
        f"{ticker}.csv"
    )


    selected_df.to_csv(
        selected_file,
        index=False,
    )


    print(
        f"  💾 {selected_file}"
    )


    selected_df = (
        selected_df
        .set_index(
            "target_quarter"
        )
        .sort_index()
    )


    selected_df.index = (
        pd.PeriodIndex(
            selected_df.index,
            freq="Q",
        )
    )


    return selected_df


# ============================================================
# 15. CACHE KPI
# ============================================================

def load_or_build_kpi(
    ticker
):

    actual_cache = lake_path(
        f"energy_v3_1_kpi_"
        f"{ticker}.csv"
    )


    guidance_cache = lake_path(
        f"energy_v3_1_guidance_"
        f"{ticker}.csv"
    )


    if (
        actual_cache.exists()
        and
        guidance_cache.exists()
        and
        not REFRESH_KPI
    ):

        print(
            f"\nLoading V3.1 KPI cache: "
            f"{ticker}"
        )


        actual = pd.read_csv(
            actual_cache,
            index_col=0,
        )


        actual.index = (
            pd.PeriodIndex(
                actual.index.astype(str),
                freq="Q",
            )
        )


        guidance = pd.read_csv(
            guidance_cache,
            index_col=0,
        )


        guidance.index = (
            pd.PeriodIndex(
                guidance.index.astype(str),
                freq="Q",
            )
        )


        return (
            actual,
            guidance,
        )


    actual_candidates, guidance_candidates = (
        scan_company_earnings(
            ticker
        )
    )


    actual = (
        select_best_actual_kpis(
            ticker,
            actual_candidates,
        )
    )


    guidance = (
        select_guidance(
            ticker,
            guidance_candidates,
        )
    )


    actual.to_csv(
        actual_cache
    )


    guidance.to_csv(
        guidance_cache
    )


    print(
        f"  💾 {actual_cache}"
    )

    print(
        f"  💾 {guidance_cache}"
    )


    return (
        actual,
        guidance,
    )


# ============================================================
# 16. LOAD ALL COMPANY KPI
# ============================================================

company_kpis = {}
company_guidance = {}


for ticker in TICKERS:

    try:

        actual, guidance = (
            load_or_build_kpi(
                ticker
            )
        )


        company_kpis[
            ticker
        ] = actual


        company_guidance[
            ticker
        ] = guidance


    except Exception as exc:

        print(
            f"\n❌ KPI ERROR "
            f"{ticker}: "
            f"{repr(exc)}"
        )


        company_kpis[
            ticker
        ] = pd.DataFrame()


        company_guidance[
            ticker
        ] = pd.DataFrame()


# ============================================================
# 17. KPI COVERAGE REPORT
# ============================================================

print(
    "\n"
    + "=" * 90
)

print(
    "V3.1 KPI COVERAGE"
)

print(
    "=" * 90
)


coverage_records = []


for ticker in TICKERS:

    kpi = (
        company_kpis[
            ticker
        ]
    )


    guidance = (
        company_guidance[
            ticker
        ]
    )


    print(
        f"\n{ticker}"
    )


    for col in [

        "total_production",
        "oil_production",
        "gas_production",

        "realized_oil_price",
        "realized_gas_price",
        "realized_combined_price",

    ]:

        if (
            not kpi.empty
            and
            col in kpi.columns
        ):

            count = (
                kpi[col]
                .notna()
                .sum()
            )

        else:

            count = 0


        print(
            f"  {col:<28}: "
            f"{count}"
        )


        coverage_records.append({

            "ticker":
                ticker,

            "feature":
                col,

            "observations":
                count,

        })


    if (
        not guidance.empty
        and
        "guidance_total_production"
        in guidance.columns
    ):

        guidance_count = (

            guidance[
                "guidance_total_production"
            ]
            .notna()
            .sum()

        )

    else:

        guidance_count = 0


    print(
        f"  {'production_guidance':<28}: "
        f"{guidance_count}"
    )


    coverage_records.append({

        "ticker":
            ticker,

        "feature":
            "production_guidance",

        "observations":
            guidance_count,

    })


coverage_df = pd.DataFrame(
    coverage_records
)


coverage_file = lake_path(
    "energy_v3_1_kpi_coverage.csv"
)


coverage_df.to_csv(
    coverage_file,
    index=False,
)


print(
    f"\n💾 {coverage_file}"
)


# ============================================================
# 18. COMPANY FEATURE ENGINEERING
# ============================================================

DEFAULT_OIL_SHARE = {

    "COP": 0.78,
    "EOG": 0.78,
    "FANG": 0.82,
    "DVN": 0.72,

}


def build_company_features(
    ticker,
    base_panel,
    actual_kpi,
    guidance,
):

    df = (
        base_panel
        .sort_values(
            "quarter"
        )
        .copy()
    )


    df.index = (
        pd.PeriodIndex(
            df[
                "quarter"
            ],
            freq="Q",
        )
    )


    # ========================================================
    # Actual production KPI
    # ========================================================

    for col in [

        "total_production",
        "oil_production",
        "gas_production",

        "realized_oil_price",
        "realized_gas_price",
        "realized_combined_price",

    ]:

        if (
            not actual_kpi.empty
            and
            col in actual_kpi.columns
        ):

            df[col] = (
                actual_kpi[
                    col
                ]
                .reindex(
                    df.index
                )
            )

        else:

            df[col] = (
                np.nan
            )


    # ========================================================
    # Production guidance
    # ========================================================

    df[
        "guidance_total_production"
    ] = np.nan


    df[
        "guidance_oil_production"
    ] = np.nan


    if not guidance.empty:

        if (
            "guidance_total_production"
            in guidance.columns
        ):

            df[
                "guidance_total_production"
            ] = (

                guidance[
                    "guidance_total_production"
                ]
                .reindex(
                    df.index
                )

            )


        if (
            "guidance_oil_production"
            in guidance.columns
        ):

            df[
                "guidance_oil_production"
            ] = (

                guidance[
                    "guidance_oil_production"
                ]
                .reindex(
                    df.index
                )

            )


    # ========================================================
    # Actual total production fallback
    #
    # If total production missing:
    #
    # oil + gas/6
    #
    # ========================================================

    component_total = (

        df[
            "oil_production"
        ]

        +

        (
            df[
                "gas_production"
            ]
            /
            6.0
        )

    )


    df[
        "total_production"
    ] = (

        df[
            "total_production"
        ]
        .combine_first(
            component_total
        )

    )


    # ========================================================
    # Company production YoY
    # ========================================================

    df[
        "total_prod_yoy"
    ] = (
        log_growth(
            df[
                "total_production"
            ],
            4,
        )
    )


    df[
        "oil_prod_yoy"
    ] = (
        log_growth(
            df[
                "oil_production"
            ],
            4,
        )
    )


    # ========================================================
    # ★ CURRENT QUARTER PRODUCTION PROXY
    #
    # Priority:
    #
    # A. guidance vs same quarter last year
    #
    # B. previous-quarter company total production YoY
    #
    # C. previous-quarter oil production YoY
    #
    # D. EIA fallback
    # ========================================================

    df[
        "guidance_total_prod_yoy"
    ] = np.nan


    prior_year_actual = (
        df[
            "total_production"
        ]
        .shift(4)
    )


    valid = (

        (
            df[
                "guidance_total_production"
            ]
            > 0
        )

        &

        (
            prior_year_actual
            > 0
        )

    )


    df.loc[
        valid,
        "guidance_total_prod_yoy"
    ] = (

        np.log(

            df.loc[
                valid,
                "guidance_total_production"
            ]

            /

            prior_year_actual.loc[
                valid
            ]

        )
        * 100

    )


    # Previous-quarter known actual
    df[
        "total_prod_yoy_l1"
    ] = (
        df[
            "total_prod_yoy"
        ]
        .shift(1)
    )


    df[
        "oil_prod_yoy_l1"
    ] = (
        df[
            "oil_prod_yoy"
        ]
        .shift(1)
    )


    # Industry fallback
    industry_prod = (

        0.70
        *
        df[
            "crude_prod_yoy_l1"
        ]

        +

        0.30
        *
        df[
            "gas_prod_yoy_l1"
        ]

    )


    df[
        "company_prod_yoy_proxy"
    ] = (

        df[
            "guidance_total_prod_yoy"
        ]

        .combine_first(

            df[
                "total_prod_yoy_l1"
            ]

        )

        .combine_first(

            df[
                "oil_prod_yoy_l1"
            ]

        )

        .combine_first(
            industry_prod
        )

        .clip(
            -60,
            120,
        )

    )


    df[
        "has_company_prod"
    ] = (

        (
            df[
                "guidance_total_prod_yoy"
            ]
            .notna()
        )

        |

        (
            df[
                "total_prod_yoy_l1"
            ]
            .notna()
        )

        |

        (
            df[
                "oil_prod_yoy_l1"
            ]
            .notna()
        )

    ).astype(float)


    df[
        "has_guidance"
    ] = (

        df[
            "guidance_total_prod_yoy"
        ]
        .notna()
        .astype(float)

    )


    # ========================================================
    # Product mix
    # ========================================================

    oil_share = (

        df[
            "oil_production"
        ]

        /

        df[
            "total_production"
        ]

    )


    oil_share = (

        oil_share
        .replace(
            [
                np.inf,
                -np.inf,
            ],
            np.nan,
        )
        .clip(
            0.10,
            1.00,
        )

    )


    company_median = (
        oil_share
        .median(
            skipna=True
        )
    )


    if pd.isna(
        company_median
    ):

        company_median = (
            DEFAULT_OIL_SHARE.get(
                ticker,
                0.75,
            )
        )


    df[
        "oil_share_l1"
    ] = (

        oil_share
        .shift(1)
        .fillna(
            company_median
        )
        .clip(
            0.1,
            1.0,
        )

    )


    # ========================================================
    # PRICE MIX
    #
    # Oil-dominant E&P:
    #
    # Oil share      -> WTI
    #
    # remaining BOE  -> mix of gas/NGL
    #
    # To avoid Henry Hub dominating too much,
    # only 50% of residual is assigned directly to gas.
    #
    # ========================================================

    gas_weight = (

        (
            1
            -
            df[
                "oil_share_l1"
            ]
        )
        *
        0.50

    )


    oil_like_weight = (

        1
        -
        gas_weight

    )


    df[
        "price_mix_yoy"
    ] = (

        oil_like_weight
        *
        df[
            "wti_yoy"
        ]

        +

        gas_weight
        *
        df[
            "henry_yoy"
        ]

    )


    # ========================================================
    # Optional combined realized-price basis
    #
    # Historical actual combined realized price is only
    # used as a residual-model feature.
    #
    # It is NOT used directly to construct current revenue
    # because the current-quarter value is not known yet.
    # ========================================================

    benchmark_level = (

        oil_like_weight
        *
        df[
            "wti"
        ]

        +

        gas_weight
        *
        (
            df[
                "henry_hub"
            ]
            * 6
        )

    )


    realized_basis = (

        df[
            "realized_combined_price"
        ]

        /

        benchmark_level

        -
        1

    )


    df[
        "realized_basis_l1"
    ] = (

        realized_basis
        .shift(1)
        .replace(
            [
                np.inf,
                -np.inf,
            ],
            np.nan,
        )
        .clip(
            -1,
            2,
        )
        *
        100

    )


    # ========================================================
    # ★ STRUCTURAL MODEL
    #
    # log Revenue ≈ log Price + log Volume
    # ========================================================

    df[
        "structural_revenue_yoy"
    ] = (

        df[
            "price_mix_yoy"
        ]

        +

        df[
            "company_prod_yoy_proxy"
        ]

    )


    df[
        "structural_revenue_yoy"
    ] = (

        df[
            "structural_revenue_yoy"
        ]
        .clip(
            -100,
            150,
        )

    )


    # ========================================================
    # Residual target
    # ========================================================

    df[
        "structural_error"
    ] = (

        df[
            "revenue_yoy"
        ]

        -

        df[
            "structural_revenue_yoy"
        ]

    )


    df.index = (
        np.arange(
            len(df)
        )
    )


    return df


# ============================================================
# 19. BUILD V3.1 PANEL
# ============================================================

frames = []


for ticker in TICKERS:

    company_panel = (

        panel_v21[
            panel_v21[
                "ticker"
            ]
            == ticker
        ]
        .copy()

    )


    if company_panel.empty:

        continue


    company_v31 = (
        build_company_features(

            ticker,

            company_panel,

            company_kpis[
                ticker
            ],

            company_guidance[
                ticker
            ],

        )
    )


    frames.append(
        company_v31
    )


panel = (
    pd.concat(
        frames,
        ignore_index=True,
    )
)


panel[
    "quarter"
] = pd.PeriodIndex(
    panel[
        "quarter"
    ].astype(str),
    freq="Q",
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


panel_file = lake_path(
    "energy_v3_1_panel.csv"
)


panel.to_csv(
    panel_file,
    index=False,
)


print(
    f"\n💾 {panel_file}"
)


# ============================================================
# 20. RESIDUAL MODEL FEATURES
# ============================================================

CANDIDATE_FEATURES = [

    # ========================================================
    # Company fundamental momentum
    # ========================================================

    "revenue_yoy_l1_clip",

    "company_prod_yoy_proxy",

    "total_prod_yoy_l1",

    "oil_prod_yoy_l1",

    "has_company_prod",

    "has_guidance",


    # ========================================================
    # Price
    # ========================================================

    "wti_yoy",

    "henry_yoy",

    "realized_basis_l1",


    # ========================================================
    # Industry
    # ========================================================

    "bea_go_yoy_l1",


    # ========================================================
    # Financial / M&A controls
    # ========================================================

    "assets_yoy_l1_clip",

    "ppe_yoy_l1_clip",

    "shares_yoy_l1_clip",

    "debt_yoy_l1_clip",

    "ma_assets_interaction",

    "ma_shares_interaction",

]


# ============================================================
# 21. AUTO FEATURE SELECTION
# ============================================================

def select_features(
    train
):

    features = []


    for feature in (
        CANDIDATE_FEATURES
    ):

        if feature not in (
            train.columns
        ):

            continue


        coverage = (

            train[
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

            train[
                feature
            ]
            .std(
                skipna=True
            )

        )


        if (
            pd.isna(std)
            or
            std < 1e-8
        ):

            continue


        features.append(
            feature
        )


    return features


# ============================================================
# 22. DESIGN MATRIX
# ============================================================

def make_design_matrix(
    df,
    features,
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
# 23. TRAIN-ONLY IMPUTATION
# ============================================================

def impute(
    train_x,
    test_x,
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
# 24. RIDGE MODEL
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
# 25. TIME-SERIES ALPHA SELECTION
# ============================================================

def select_alpha(
    train,
    features,
):

    quarters = sorted(
        train[
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
                    len(quarters) - 6
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

                train[
                    train[
                        "quarter"
                    ]
                    < q
                ]
                .copy()

            )


            inner_test = (

                train[
                    train[
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
                impute(
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


            model = (
                build_model(
                    alpha
                )
            )


            model.fit(
                X_train,
                y_train,
            )


            residual = (
                model.predict(
                    X_test
                )
            )


            prediction = (

                inner_test[
                    "structural_revenue_yoy"
                ]
                .to_numpy(
                    dtype=float
                )

                +

                residual

            )


            prediction = np.clip(

                prediction,

                PREDICTION_MIN,
                PREDICTION_MAX,

            )


            error = (
                mean_absolute_error(

                    inner_test[
                        "revenue_yoy"
                    ],

                    prediction,

                )
            )


            errors.append(
                error
            )


        if not errors:

            continue


        score = float(
            np.mean(
                errors
            )
        )


        if (
            score
            <
            best_mae
        ):

            best_mae = (
                score
            )

            best_alpha = (
                alpha
            )


    return best_alpha


# ============================================================
# 26. WALK-FORWARD VALIDATION
# ============================================================

def walk_forward_validation(
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
            "V3.1 history 부족"
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
        "V3.1 WALK-FORWARD VALIDATION"
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
                f"{q}: usable feature 없음"
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
            impute(
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


        residual = (
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
            residual
        )


        prediction = np.clip(

            prediction,

            PREDICTION_MIN,
            PREDICTION_MAX,

        )


        for (
            (_, row),
            structural_pred,
            residual_pred,
            final_pred
        ) in zip(

            test.iterrows(),

            structural,

            residual,

            prediction,

        ):

            records.append({

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

                "v3_1_predicted":
                    float(
                        final_pred
                    ),

                "residual_adjustment":
                    float(
                        residual_pred
                    ),

                "price_mix_yoy":
                    row[
                        "price_mix_yoy"
                    ],

                "company_prod_yoy_proxy":
                    row[
                        "company_prod_yoy_proxy"
                    ],

                "total_prod_yoy_l1":
                    row[
                        "total_prod_yoy_l1"
                    ],

                "guidance_total_prod_yoy":
                    row[
                        "guidance_total_prod_yoy"
                    ],

                "has_company_prod":
                    row[
                        "has_company_prod"
                    ],

                "has_guidance":
                    row[
                        "has_guidance"
                    ],

                "alpha":
                    alpha,

                "feature_count":
                    len(
                        features
                    ),

            })


    result = pd.DataFrame(
        records
    )


    if result.empty:

        raise ValueError(
            "validation 결과 없음"
        )


    # ========================================================
    # Metrics
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


    final_mae = (
        mean_absolute_error(

            result[
                "actual"
            ],

            result[
                "v3_1_predicted"
            ],

        )
    )


    final_rmse = np.sqrt(

        mean_squared_error(

            result[
                "actual"
            ],

            result[
                "v3_1_predicted"
            ],

        )

    )


    improvement = (

        (
            naive_mae
            -
            final_mae
        )

        /

        naive_mae

        * 100

    )


    print(
        f"\nNaive MAE        : "
        f"{naive_mae:.2f} pp"
    )

    print(
        f"Structural MAE   : "
        f"{structural_mae:.2f} pp"
    )

    print(
        f"V3.1 MAE         : "
        f"{final_mae:.2f} pp"
    )

    print(
        f"V3.1 RMSE        : "
        f"{final_rmse:.2f} pp"
    )

    print(
        f"Naive 개선       : "
        f"{improvement:+.1f}%"
    )


    # ========================================================
    # Company metrics
    # ========================================================

    metric_rows = []


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


        structural = (
            mean_absolute_error(
                group["actual"],
                group["structural"],
            )
        )


        v31 = (
            mean_absolute_error(
                group["actual"],
                group["v3_1_predicted"],
            )
        )


        rmse = np.sqrt(

            mean_squared_error(

                group[
                    "actual"
                ],

                group[
                    "v3_1_predicted"
                ],

            )

        )


        metric_rows.append({

            "ticker":
                ticker,

            "Naive_MAE":
                naive,

            "Structural_MAE":
                structural,

            "V3_1_MAE":
                v31,

            "V3_1_RMSE":
                rmse,

            "improvement_pct":
                (
                    (
                        naive
                        - v31
                    )
                    /
                    naive
                    * 100
                ),

        })


    metrics = (

        pd.DataFrame(
            metric_rows
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

        result
        .tail(20)
        .round(2)
        .to_string(
            index=False
        )

    )


    validation_file = lake_path(
        "energy_v3_1_validation.csv"
    )


    metrics_file = lake_path(
        "energy_v3_1_metrics.csv"
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
# 27. FINAL MODEL + NOWCAST
# ============================================================

def final_model_nowcast(
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


    for feature in features:

        print(
            "  ",
            feature
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
    # Find each company's next quarter
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
            current.iloc[0]
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
            "nowcast row 없음"
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


    residual = (
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


    prediction = (
        structural
        +
        residual
    )


    prediction = np.clip(

        prediction,

        PREDICTION_MIN,
        PREDICTION_MAX,

    )


    now[
        "residual_adjustment"
    ] = (
        residual
    )


    now[
        "predicted_revenue_yoy"
    ] = (
        prediction
    )


    # ========================================================
    # Revenue level
    # ========================================================

    predicted_revenues = []


    for _, row in (
        now.iterrows()
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

            predicted_revenues.append(
                np.nan
            )

            continue


        base_revenue = float(

            base.iloc[0][
                "revenue"
            ]

        )


        estimated = (

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


        predicted_revenues.append(
            estimated
        )


    now[
        "predicted_revenue"
    ] = (
        predicted_revenues
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


    output_columns = [

        "ticker",
        "nowcast_quarter",

        "predicted_revenue_yoy",
        "predicted_revenue_B",

        "structural_revenue_yoy",
        "residual_adjustment",

        "price_mix_yoy",

        "company_prod_yoy_proxy",

        "guidance_total_prod_yoy",

        "total_prod_yoy_l1",

        "guidance_total_production",

        "total_production",

        "oil_production",

        "has_company_prod",
        "has_guidance",

        "wti_yoy",
        "henry_yoy",

    ]


    output = (

        now[
            [
                x

                for x
                in output_columns

                if x
                in now.columns
            ]
        ]
        .copy()

    )


    print(
        "\n"
        + "=" * 90
    )

    print(
        "🚀 ENERGY REVENUE V3.1 NOWCAST"
    )

    print(
        "=" * 90
    )


    print(

        output
        .round(2)
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
        "energy_v3_1_nowcast.csv"
    )


    coefficient_file = lake_path(
        "energy_v3_1_coefficients.csv"
    )


    output.to_csv(
        nowcast_file,
        index=False,
    )


    coefficients.to_frame(
        "coefficient"
    ).to_csv(
        coefficient_file
    )


    print(
        f"\n💾 {nowcast_file}"
    )

    print(
        f"💾 {coefficient_file}"
    )


    return (
        model,
        output,
        coefficients,
    )


# ============================================================
# 28. SAVE FEATURE COVERAGE
# ============================================================

feature_coverage = []


for ticker in TICKERS:

    company = (

        panel[
            panel[
                "ticker"
            ]
            == ticker
        ]

    )


    for feature in [

        "total_production",
        "oil_production",

        "guidance_total_production",

        "total_prod_yoy_l1",
        "guidance_total_prod_yoy",

        "company_prod_yoy_proxy",

        "structural_revenue_yoy",

    ]:

        coverage = (

            company[
                feature
            ]
            .notna()
            .mean()

            if feature in company.columns

            else 0

        )


        feature_coverage.append({

            "ticker":
                ticker,

            "feature":
                feature,

            "coverage_pct":
                coverage
                * 100,

        })


feature_coverage_df = (
    pd.DataFrame(
        feature_coverage
    )
)


feature_coverage_file = lake_path(
    "energy_v3_1_feature_coverage.csv"
)


feature_coverage_df.to_csv(
    feature_coverage_file,
    index=False,
)


print(
    f"\n💾 {feature_coverage_file}"
)


# ============================================================
# 29. VALIDATION
# ============================================================

validation, metrics = (
    walk_forward_validation(
        panel
    )
)


# ============================================================
# 30. FINAL NOWCAST
# ============================================================

model, nowcast, coefficients = (
    final_model_nowcast(
        panel
    )
)


# ============================================================
# 31. SAVE RUN METADATA
# ============================================================

metadata = {

    "version":
        "3.1",

    "as_of_date":
        str(
            AS_OF.date()
        ),

    "tickers":
        TICKERS,

    "refresh_kpi":
        REFRESH_KPI,

    "earnings_lookback_filings":
        EARNINGS_LOOKBACK_FILINGS,

    "structural_model":

        (
            "Price Mix YoY "
            "+ Company Production YoY Proxy"
        ),

    "production_proxy_priority": [

        "current-quarter company guidance",

        "previous-quarter company total "
        "production YoY",

        "previous-quarter company oil "
        "production YoY",

        "EIA industry production",

    ],

}


metadata_file = lake_path(
    "energy_v3_1_metadata.json"
)


with open(
    metadata_file,
    "w",
    encoding="utf-8",
) as f:

    json.dump(

        metadata,

        f,

        ensure_ascii=False,
        indent=2,

    )


print(
    f"\n💾 {metadata_file}"
)


# ============================================================
# 32. DONE
# ============================================================

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
    "\nMain V3.1 files:"
)


for filename in [

    "energy_v3_1_panel.csv",

    "energy_v3_1_kpi_coverage.csv",

    "energy_v3_1_feature_coverage.csv",

    "energy_v3_1_validation.csv",

    "energy_v3_1_metrics.csv",

    "energy_v3_1_nowcast.csv",

    "energy_v3_1_coefficients.csv",

    "energy_v3_1_metadata.json",

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
            f"energy_v3_1_kpi_"
            f"{ticker}.csv"
        )

    )

    print(

        " -",
        lake_path(
            f"energy_v3_1_kpi_selected_"
            f"{ticker}.csv"
        )

    )

    print(

        " -",
        lake_path(
            f"energy_v3_1_kpi_candidates_"
            f"{ticker}.csv"
        )

    )

    print(

        " -",
        lake_path(
            f"energy_v3_1_guidance_"
            f"{ticker}.csv"
        )

    )