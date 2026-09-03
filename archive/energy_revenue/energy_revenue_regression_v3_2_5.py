# ============================================================
# ENERGY REVENUE NOWCAST V3.2.5
# ============================================================
#
# 핵심 변경
# ------------------------------------------------------------
# V3.2.4:
#   EOG table-level actual/guidance classification
#
# V3.2.5:
#   EOG ROW-LEVEL EXACT PARSER
#
#   - Key Operational Results
#   - Results vs Guidance
#   - Next Quarter Guidance
#
#   가 같은 HTML/테이블 안에 섞여 있어도
#   행을 위에서 아래로 읽으면서 ACTUAL/GUIDANCE 구분
#
#
# EOG Exact Components
# ------------------------------------------------------------
# Oil   : Crude Oil and Condensate (MBod)
# NGL   : Natural Gas Liquids (MBbld)
# Gas   : Natural Gas (MMcfd)
# Total : Crude Oil Equivalent (MBoed)
#
#
# BOE Reconstruction
# ------------------------------------------------------------
#
# Total MBoed
#   =
#   Oil MBod
#   + NGL MBbld
#   + Gas MMcfd / 6
#
#
# reported vs reconstructed error <= 5%
#   -> reported total 사용
#
# mismatch > 5%
#   -> reconstructed total 사용
#      + quality penalty
#
#
# V3.2.3 QC 유지
# ------------------------------------------------------------
# - bad oil field가 total을 죽이지 않음
# - M&A window jump 허용
# - point-in-time new regime confirmation
#
#
# Production source
# ------------------------------------------------------------
# 1. GUIDANCE_VS_ACTUAL
# 2. GUIDANCE_VS_GUIDANCE
# 3. ACTUAL_VS_ACTUAL
# 4. INDUSTRY_FALLBACK
#
#
# Final Model
# ------------------------------------------------------------
#
# Final Revenue Log YoY
#   =
#   structural_weight * Structural
#   +
#   (1 - structural_weight) * V2.1
#
#
# Metrics
# ------------------------------------------------------------
# - MAE_log_points
# - MAE_yoy_pct_points
#
#
# REQUIRED FILES
# ------------------------------------------------------------
#
# ./data-lake/energy_v2_1_panel.csv
# ./data-lake/energy_v2_1_validation.csv
# ./data-lake/energy_v2_1_nowcast.csv
#
# COP/FANG/DVN:
# ./data-lake/energy_v3_2_1_actual_*.csv
# ./data-lake/energy_v3_2_1_guidance_*.csv
#
# EOG:
# V3.2.5에서 SEC EX-99 다시 읽음
#
# ============================================================


import os
import re
import html
import json
import warnings

from io import StringIO
from pathlib import Path
from datetime import date

import numpy as np
import pandas as pd

from bs4 import BeautifulSoup

from edgar import (
    Company,
    set_identity,
)


warnings.filterwarnings(
    "ignore"
)


# ============================================================
# 0. CONFIG
# ============================================================

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


EDGAR_IDENTITY = os.getenv(
    "EDGAR_IDENTITY"
)


AS_OF_DATE_ENV = os.getenv(
    "AS_OF_DATE"
)


REFRESH_EOG = (
    os.getenv(
        "REFRESH_EOG",
        "1",
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


EOG_LOOKBACK_FILINGS = int(
    os.getenv(
        "EOG_LOOKBACK_FILINGS",
        "55",
    )
)


# ============================================================
# BLEND CONFIG
# ============================================================

BLEND_WEIGHTS = np.round(
    np.arange(
        0.0,
        1.0001,
        0.05,
    ),
    2,
)


MIN_BLEND_HISTORY = int(
    os.getenv(
        "MIN_BLEND_HISTORY",
        "3",
    )
)


# ============================================================
# PRODUCTION QC
# ============================================================

MAX_ORGANIC_QOQ_LOG_GROWTH = float(
    os.getenv(
        "MAX_ORGANIC_QOQ_LOG_GROWTH",
        "35",
    )
)


MAX_QOQ_THRESHOLD = float(
    os.getenv(
        "MAX_QOQ_THRESHOLD",
        "55",
    )
)


REGIME_CONFIRM_MAX_LOG_GROWTH = float(
    os.getenv(
        "REGIME_CONFIRM_MAX_LOG_GROWTH",
        "20",
    )
)


MAX_REGIME_CONFIRM_GAP = int(
    os.getenv(
        "MAX_REGIME_CONFIRM_GAP",
        "2",
    )
)


# ============================================================
# FIELD QC
# ============================================================

TOTAL_OIL_RATIO_MIN = float(
    os.getenv(
        "TOTAL_OIL_RATIO_MIN",
        "1.15",
    )
)


TOTAL_OIL_RATIO_MAX = float(
    os.getenv(
        "TOTAL_OIL_RATIO_MAX",
        "5.0",
    )
)


EOG_RECON_ERROR_MAX_PCT = float(
    os.getenv(
        "EOG_RECON_ERROR_MAX_PCT",
        "5.0",
    )
)


TOTAL_PRODUCTION_MIN = 20.0
TOTAL_PRODUCTION_MAX = 5000.0

OIL_PRODUCTION_MIN = 5.0
OIL_PRODUCTION_MAX = 3000.0

NGL_PRODUCTION_MIN = 0.0
NGL_PRODUCTION_MAX = 3000.0

GAS_PRODUCTION_MIN = 0.0
GAS_PRODUCTION_MAX = 20000.0


# ============================================================
# SOURCE QUALITY
# ============================================================

SOURCE_QUALITY = {

    "GUIDANCE_VS_ACTUAL":
        1.00,

    "GUIDANCE_VS_GUIDANCE":
        0.80,

    "ACTUAL_VS_ACTUAL":
        0.90,

    "INDUSTRY_FALLBACK":
        0.35,

}


NO_COMPANY_PROD_MAX_WEIGHT = float(
    os.getenv(
        "NO_COMPANY_PROD_MAX_WEIGHT",
        "0.25",
    )
)


# ============================================================
# PREDICTION LIMIT
# ============================================================

MIN_LOG_GROWTH = -100.0
MAX_LOG_GROWTH = 150.0


# ============================================================
# OIL SHARE FALLBACK
# ============================================================

DEFAULT_OIL_SHARE = {

    "COP":
        0.78,

    "EOG":
        0.39,

    "FANG":
        0.82,

    "DVN":
        0.72,

}


# ============================================================
# 1. PATH / DATE
# ============================================================

DATA_LAKE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


def lake_path(
    filename
):

    return (
        DATA_LAKE_DIR
        / filename
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


print(
    "=" * 90
)

print(
    "ENERGY REVENUE NOWCAST V3.2.5"
)

print(
    "=" * 90
)

print(
    "AS OF       :",
    AS_OF.date()
)

print(
    "TICKERS     :",
    TICKERS
)

print(
    "DATA LAKE   :",
    DATA_LAKE_DIR.resolve()
)

print(
    "REFRESH EOG :",
    REFRESH_EOG
)

print(
    "EOG RECON % :",
    EOG_RECON_ERROR_MAX_PCT
)


# ============================================================
# 2. GENERIC HELPERS
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

    return text.strip()


def normalize_label(
    text
):

    text = normalize_text(
        text
    ).lower()

    text = text.replace(
        "&",
        " and ",
    )

    text = re.sub(
        r"[\u200b\u200c\u200d]",
        "",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def html_to_text(
    raw
):

    if raw is None:

        return ""

    if isinstance(
        raw,
        bytes,
    ):

        raw = raw.decode(
            "utf-8",
            errors="ignore",
        )

    raw = str(
        raw
    )

    raw = re.sub(
        r"<script.*?</script>",
        " ",
        raw,
        flags=re.I | re.S,
    )

    raw = re.sub(
        r"<style.*?</style>",
        " ",
        raw,
        flags=re.I | re.S,
    )

    raw = re.sub(
        r"<[^>]+>",
        " ",
        raw,
    )

    raw = html.unescape(
        raw
    )

    return normalize_text(
        raw
    )


def numeric(
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
        ),
    ):

        return float(
            value
        )

    text = normalize_text(
        value
    )

    if text in {
        "",
        "-",
        "—",
        "–",
    }:

        return np.nan

    negative = (
        text.startswith("(")
        and
        text.endswith(")")
    )

    text = (
        text
        .replace("$", "")
        .replace(",", "")
        .replace("%", "")
        .replace("(", "")
        .replace(")", "")
        .strip()
    )

    try:

        result = float(
            text
        )

    except Exception:

        return np.nan

    if negative:

        result = -abs(
            result
        )

    return result


def extract_numeric_values(
    cells,
    start_index=0,
):

    values = []

    for cell in cells[
        start_index:
    ]:

        cell_text = normalize_text(
            cell
        )

        # 순수 숫자 cell
        direct = numeric(
            cell_text
        )

        if pd.notna(
            direct
        ):

            # 연도 제거
            if not (
                1990
                <= direct
                <= 2100
            ):

                values.append(
                    float(direct)
                )

            continue


        # cell 안에 숫자가 섞인 경우
        tokens = re.findall(
            r"\(?-?\$?"
            r"\d[\d,]*"
            r"(?:\.\d+)?"
            r"%?\)?",
            cell_text,
        )

        for token in tokens:

            number = numeric(
                token
            )

            if pd.isna(
                number
            ):

                continue

            if (
                1990
                <= number
                <= 2100
            ):

                continue

            values.append(
                float(number)
            )


    return values


# ============================================================
# 3. GROWTH FUNCTIONS
# ============================================================

def log_ratio_growth(
    current,
    previous,
):

    if (
        pd.isna(current)
        or
        pd.isna(previous)
        or
        current <= 0
        or
        previous <= 0
    ):

        return np.nan

    return float(
        np.log(
            current
            /
            previous
        )
        * 100
    )


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
            series.loc[valid]
            /
            lagged.loc[valid]
        )
        * 100
    )

    return output


def log_to_normal_pct(
    value
):

    if isinstance(
        value,
        pd.Series,
    ):

        return (
            np.exp(
                value / 100
            )
            - 1
        ) * 100

    if isinstance(
        value,
        np.ndarray,
    ):

        return (
            np.exp(
                value / 100
            )
            - 1
        ) * 100

    if pd.isna(
        value
    ):

        return np.nan

    return (
        np.exp(
            value / 100
        )
        - 1
    ) * 100


def mae(
    actual,
    predicted,
):

    actual = np.asarray(
        actual,
        dtype=float,
    )

    predicted = np.asarray(
        predicted,
        dtype=float,
    )

    return float(
        np.mean(
            np.abs(
                actual
                -
                predicted
            )
        )
    )


def mae_yoy_pct_points(
    actual_log,
    predicted_log,
):

    actual_pct = (
        log_to_normal_pct(
            np.asarray(
                actual_log,
                dtype=float,
            )
        )
    )

    predicted_pct = (
        log_to_normal_pct(
            np.asarray(
                predicted_log,
                dtype=float,
            )
        )
    )

    return float(
        np.mean(
            np.abs(
                actual_pct
                -
                predicted_pct
            )
        )
    )


def quarter_gap(
    newer,
    older,
):

    return (
        newer.ordinal
        -
        older.ordinal
    )


# ============================================================
# 4. QUARTER INFERENCE
# ============================================================

QUARTER_WORD = {

    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,

}


def quarter_from_word(
    qword,
    year,
):

    return pd.Period(
        (
            f"{int(year)}"
            f"Q{QUARTER_WORD[qword.lower()]}"
        ),
        freq="Q",
    )


def infer_result_quarter(
    filing_date,
    text,
):

    lower = normalize_text(
        text
    ).lower()

    # "Second Quarter 2026"
    match = re.search(
        r"(first|second|third|fourth)"
        r"\s+quarter"
        r"(?:\s+of)?"
        r"\s+(20\d{2})",
        lower,
    )

    if match:

        return quarter_from_word(
            match.group(1),
            match.group(2),
        )

    # "2Q 2026"
    match = re.search(
        r"\b([1-4])q\s*(20\d{2})\b",
        lower,
    )

    if match:

        return pd.Period(
            (
                f"{match.group(2)}"
                f"Q{match.group(1)}"
            ),
            freq="Q",
        )

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


def infer_guidance_quarter(
    context,
    full_text,
    result_quarter,
):

    search_text = normalize_text(
        f"{context} {full_text}"
    ).lower()

    # 3Q 2026 Guidance
    match = re.search(
        r"\b([1-4])q\s*(20\d{2})"
        r".{0,60}?"
        r"guidance",
        search_text,
    )

    if match:

        return pd.Period(
            (
                f"{match.group(2)}"
                f"Q{match.group(1)}"
            ),
            freq="Q",
        )

    # Third Quarter and Full-Year 2026 Guidance
    match = re.search(
        r"(first|second|third|fourth)"
        r"\s+quarter"
        r".{0,80}?"
        r"(20\d{2})"
        r".{0,40}?"
        r"guidance",
        search_text,
    )

    if match:

        return quarter_from_word(
            match.group(1),
            match.group(2),
        )

    return (
        result_quarter
        + 1
    )


# ============================================================
# 5. REQUIRED FILES
# ============================================================

PANEL_FILE = lake_path(
    "energy_v2_1_panel.csv"
)

VALIDATION_FILE = lake_path(
    "energy_v2_1_validation.csv"
)

NOWCAST_FILE = lake_path(
    "energy_v2_1_nowcast.csv"
)


for path in [
    PANEL_FILE,
    VALIDATION_FILE,
    NOWCAST_FILE,
]:

    if not path.exists():

        raise FileNotFoundError(
            f"{path} 없음.\n"
            "먼저 V2.1을 실행해줘."
        )


for ticker in [
    x
    for x in TICKERS
    if x != "EOG"
]:

    for kind in [
        "actual",
        "guidance",
    ]:

        path = lake_path(
            f"energy_v3_2_1_{kind}_{ticker}.csv"
        )

        if not path.exists():

            raise FileNotFoundError(
                f"{path} 없음.\n"
                "먼저 V3.2.1을 실행해줘."
            )


# ============================================================
# 6. LOAD V2.1
# ============================================================

panel_v21 = pd.read_csv(
    PANEL_FILE
)


panel_v21[
    "quarter"
] = pd.PeriodIndex(
    panel_v21[
        "quarter"
    ].astype(str),
    freq="Q",
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


if (
    "ma_event"
    not in panel_v21.columns
):

    panel_v21[
        "ma_event"
    ] = 0.0


if (
    "ma_window"
    not in panel_v21.columns
):

    panel_v21[
        "ma_window"
    ] = 0.0


panel_v21[
    "ma_event"
] = pd.to_numeric(
    panel_v21[
        "ma_event"
    ],
    errors="coerce",
).fillna(0)


panel_v21[
    "ma_window"
] = pd.to_numeric(
    panel_v21[
        "ma_window"
    ],
    errors="coerce",
).fillna(0)


validation_v21 = pd.read_csv(
    VALIDATION_FILE
)


validation_v21[
    "quarter"
] = pd.PeriodIndex(
    validation_v21[
        "quarter"
    ].astype(str),
    freq="Q",
)


nowcast_v21 = pd.read_csv(
    NOWCAST_FILE
)


nowcast_v21[
    "nowcast_quarter"
] = pd.PeriodIndex(
    nowcast_v21[
        "nowcast_quarter"
    ].astype(str),
    freq="Q",
)


print(
    "\nV2.1 panel      :",
    panel_v21.shape
)

print(
    "V2.1 validation :",
    validation_v21.shape
)

print(
    "V2.1 nowcast    :",
    nowcast_v21.shape
)


# ============================================================
# 7. PERIOD CACHE READER
# ============================================================

def read_period_cache(
    path
):

    try:

        df = pd.read_csv(
            path,
            index_col=0,
        )

    except pd.errors.EmptyDataError:

        return pd.DataFrame()


    if df.empty:

        return df


    df.index = pd.PeriodIndex(
        df.index.astype(str),
        freq="Q",
    )


    df.index.name = None


    return (
        df.sort_index()
    )


# ============================================================
# 8. EOG ROW LABEL DETECTION
# ============================================================

def detect_eog_component(
    label
):

    label = normalize_label(
        label
    )


    # Oil
    if (
        re.search(
            r"crude\s+oil\s+and\s+condensate",
            label,
        )
        and
        re.search(
            r"mbod|mbopd",
            label,
        )
    ):

        return "oil"


    # NGL
    if (
        re.search(
            r"natural\s+gas\s+liquids?",
            label,
        )
        and
        re.search(
            r"mbbld|mbbl/d|mbd",
            label,
        )
    ):

        return "ngl"


    # Gas
    if (
        re.search(
            r"natural\s+gas",
            label,
        )
        and
        "liquid"
        not in label
        and
        re.search(
            r"mmcfd|mmcf/d",
            label,
        )
    ):

        return "gas"


    # Total BOE
    if (
        re.search(
            r"crude\s+oil\s+equivalent",
            label,
        )
        and
        re.search(
            r"mboed|mboe/d|mboepd",
            label,
        )
    ):

        return "total"


    return None


# ============================================================
# 9. ROW VALUE SELECTION
# ============================================================

COMPONENT_RANGES = {

    "oil":
        (
            10.0,
            2000.0,
        ),

    "ngl":
        (
            0.0,
            2000.0,
        ),

    "gas":
        (
            0.0,
            20000.0,
        ),

    "total":
        (
            100.0,
            4000.0,
        ),

}


def plausible_values(
    values,
    component,
):

    low, high = (
        COMPONENT_RANGES[
            component
        ]
    )

    return [
        float(x)

        for x in values

        if (
            pd.notna(x)
            and
            low <= x <= high
        )
    ]


def choose_actual_value(
    values,
    component,
):

    values = plausible_values(
        values,
        component,
    )

    if not values:

        return np.nan

    # Actual table:
    # 첫 번째 숫자가 현재 분기 actual
    return float(
        values[0]
    )


def choose_guidance_midpoint(
    values,
    component,
):

    values = plausible_values(
        values,
        component,
    )

    if not values:

        return np.nan


    # 보통:
    #
    # low, high, midpoint,
    # FY low, FY high, FY midpoint
    #
    # 또는
    #
    # low, high, midpoint
    #
    if len(values) >= 3:

        calculated_midpoint = (
            values[0]
            +
            values[1]
        ) / 2


        tolerance = max(
            0.5,
            abs(
                calculated_midpoint
            )
            * 0.03,
        )


        if abs(
            values[2]
            -
            calculated_midpoint
        ) <= tolerance:

            return float(
                values[2]
            )


    if len(values) >= 2:

        return float(
            (
                values[0]
                +
                values[1]
            )
            / 2
        )


    return float(
        values[0]
    )


# ============================================================
# 10. EOG TABLE MODE
# ============================================================

def table_mode_hint(
    context,
    table
):

    try:

        column_text = normalize_text(
            " ".join(
                str(x)
                for x in table.columns
            )
        )

    except Exception:

        column_text = ""


    try:

        first_rows = normalize_text(
            " ".join(
                str(x)
                for x
                in table
                .head(5)
                .astype(str)
                .values
                .flatten()
            )
        )

    except Exception:

        first_rows = ""


    text = normalize_label(
        f"{context} "
        f"{column_text} "
        f"{first_rows}"
    )


    # Results vs Guidance는 ACTUAL table
    if (
        "results vs guidance"
        in text
        or
        "variance"
        in text
    ):

        return "ACTUAL"


    # Key Operational Results
    if (
        "key operational results"
        in text
    ):

        return "ACTUAL"


    # 다음 분기 guidance
    if (
        "guidance range"
        in text
        and
        "midpoint"
        in text
    ):

        return "GUIDANCE"


    if (
        re.search(
            r"(first|second|third|fourth)"
            r"\s+quarter"
            r".{0,60}"
            r"guidance",
            text,
        )
    ):

        return "GUIDANCE"


    if (
        re.search(
            r"\b[1-4]q\s*20\d{2}"
            r".{0,50}"
            r"guidance",
            text,
        )
    ):

        return "GUIDANCE"


    return "ACTUAL"


# ============================================================
# 11. ROW MODE SWITCH
# ============================================================

def switch_row_mode(
    current_mode,
    row_text,
):

    text = normalize_label(
        row_text
    )


    if (
        "key operational results"
        in text
    ):

        return "ACTUAL"


    if (
        "results vs guidance"
        in text
    ):

        return "ACTUAL"


    if (
        "guidance range"
        in text
        and
        "midpoint"
        in text
    ):

        return "GUIDANCE"


    if (
        re.search(
            r"(first|second|third|fourth)"
            r"\s+quarter"
            r".{0,100}"
            r"guidance",
            text,
        )
    ):

        return "GUIDANCE"


    if (
        re.search(
            r"\b[1-4]q\s*20\d{2}"
            r".{0,80}"
            r"guidance",
            text,
        )
    ):

        return "GUIDANCE"


    return current_mode


# ============================================================
# 12. EOG ROW PARSER
# ============================================================

def parse_eog_table_rows(
    table,
    context,
    table_index,
    filing_date,
    result_quarter,
    full_text,
):

    try:

        table = (
            table
            .copy()
            .fillna("")
        )

    except Exception:

        return (
            [],
            [],
            [],
        )


    mode = table_mode_hint(
        context,
        table,
    )


    section = None


    actual_values = {

        "oil":
            np.nan,

        "ngl":
            np.nan,

        "gas":
            np.nan,

        "total":
            np.nan,
    }


    guidance_values = {

        "oil":
            np.nan,

        "ngl":
            np.nan,

        "gas":
            np.nan,

        "total":
            np.nan,
    }


    row_debug = []


    for row_number, (
        _,
        row
    ) in enumerate(
        table.iterrows()
    ):

        cells = [
            normalize_text(x)
            for x in row.tolist()
        ]


        row_text = normalize_text(
            " | ".join(
                cells
            )
        )


        if not row_text:

            continue


        mode = switch_row_mode(
            mode,
            row_text,
        )


        # ----------------------------------------------------
        # 첫 non-empty cell
        # ----------------------------------------------------

        label_index = None
        label_text = ""


        for i, cell in enumerate(
            cells
        ):

            if cell.strip():

                label_index = i
                label_text = cell
                break


        if label_index is None:

            continue


        component = detect_eog_component(
            label_text
        )


        # ----------------------------------------------------
        # Exact component label row
        # ----------------------------------------------------

        if component is not None:

            section = component


            values = extract_numeric_values(
                cells,
                label_index + 1,
            )


            # 행 자체에 숫자가 있을 때
            if values:

                if mode == "GUIDANCE":

                    selected = (
                        choose_guidance_midpoint(
                            values,
                            component,
                        )
                    )


                    if pd.notna(
                        selected
                    ):

                        guidance_values[
                            component
                        ] = selected


                else:

                    selected = (
                        choose_actual_value(
                            values,
                            component,
                        )
                    )


                    if pd.notna(
                        selected
                    ):

                        actual_values[
                            component
                        ] = selected


                row_debug.append(
                    {
                        "filing_date":
                            filing_date,

                        "result_quarter":
                            str(
                                result_quarter
                            ),

                        "table_index":
                            table_index,

                        "row_number":
                            row_number,

                        "mode":
                            mode,

                        "section":
                            component,

                        "row_text":
                            row_text[:1200],

                        "numeric_values":
                            str(values),

                        "selected_value":
                            selected,
                    }
                )


            continue


        # ----------------------------------------------------
        # section 다음 Total row
        # ----------------------------------------------------

        label_normalized = normalize_label(
            label_text
        )


        is_total_row = (
            re.fullmatch(
                r"total(?:\s*\^\{?.*?\}?)?",
                label_normalized,
            )
            is not None
        )


        # Total BOE guidance 표에서는
        # Composite라는 행을 쓰는 경우도 대비
        if (
            section == "total"
            and
            label_normalized
            == "composite"
        ):

            is_total_row = True


        if (
            section is None
            or
            not is_total_row
        ):

            continue


        values = extract_numeric_values(
            cells,
            label_index + 1,
        )


        if not values:

            continue


        if mode == "GUIDANCE":

            selected = (
                choose_guidance_midpoint(
                    values,
                    section,
                )
            )


            if pd.notna(
                selected
            ):

                guidance_values[
                    section
                ] = selected


        else:

            selected = (
                choose_actual_value(
                    values,
                    section,
                )
            )


            if pd.notna(
                selected
            ):

                actual_values[
                    section
                ] = selected


        row_debug.append(
            {
                "filing_date":
                    filing_date,

                "result_quarter":
                    str(
                        result_quarter
                    ),

                "table_index":
                    table_index,

                "row_number":
                    row_number,

                "mode":
                    mode,

                "section":
                    section,

                "row_text":
                    row_text[:1200],

                "numeric_values":
                    str(values),

                "selected_value":
                    selected,
            }
        )


    # Guidance target quarter
    target_q = infer_guidance_quarter(
        context,
        full_text,
        result_quarter,
    )


    actual_rows = []


    if any(
        pd.notna(x)
        for x
        in actual_values.values()
    ):

        actual_rows.append(
            {
                "quarter":
                    str(
                        result_quarter
                    ),

                "filing_date":
                    str(
                        pd.Timestamp(
                            filing_date
                        ).date()
                    ),

                "oil":
                    actual_values["oil"],

                "ngl":
                    actual_values["ngl"],

                "gas":
                    actual_values["gas"],

                "reported_total":
                    actual_values["total"],

                "table_index":
                    table_index,

                "table_context":
                    context[:1000],
            }
        )


    guidance_rows = []


    if any(
        pd.notna(x)
        for x
        in guidance_values.values()
    ):

        guidance_rows.append(
            {
                "target_quarter":
                    str(
                        target_q
                    ),

                "filing_date":
                    str(
                        pd.Timestamp(
                            filing_date
                        ).date()
                    ),

                "oil":
                    guidance_values["oil"],

                "ngl":
                    guidance_values["ngl"],

                "gas":
                    guidance_values["gas"],

                "reported_total":
                    guidance_values[
                        "total"
                    ],

                "table_index":
                    table_index,

                "table_context":
                    context[:1000],
            }
        )


    return (
        actual_rows,
        guidance_rows,
        row_debug,
    )


# ============================================================
# 13. HTML TABLE + CONTEXT EXTRACTOR
# ============================================================

def extract_html_tables_with_context(
    raw_html
):

    if isinstance(
        raw_html,
        bytes,
    ):

        raw_html = raw_html.decode(
            "utf-8",
            errors="ignore",
        )


    raw_html = str(
        raw_html
    )


    soup = BeautifulSoup(
        raw_html,
        "lxml",
    )


    output = []


    table_tags = soup.find_all(
        "table"
    )


    for table_index, table_tag in enumerate(
        table_tags
    ):

        context_parts = []


        # 가까운 앞쪽 heading/text
        for prev in table_tag.find_all_previous(
            [
                "h1",
                "h2",
                "h3",
                "h4",
                "p",
                "strong",
                "b",
                "div",
            ],
            limit=15,
        ):

            text = normalize_text(
                prev.get_text(
                    " ",
                    strip=True,
                )
            )


            if not text:

                continue


            # 너무 큰 wrapper div는 제외
            if len(
                text
            ) > 500:

                continue


            if text not in context_parts:

                context_parts.append(
                    text
                )


            if len(
                context_parts
            ) >= 8:

                break


        context = normalize_text(
            " ".join(
                reversed(
                    context_parts
                )
            )
        )


        try:

            tables = pd.read_html(
                StringIO(
                    str(
                        table_tag
                    )
                )
            )

        except Exception:

            continue


        if not tables:

            continue


        output.append(
            {
                "table_index":
                    table_index,

                "context":
                    context,

                "table":
                    tables[0],
            }
        )


    return output


# ============================================================
# 14. EOG PROSE FALLBACK
# ============================================================

def parse_eog_prose_actual(
    text,
    quarter,
    filing_date,
):

    # Quarterly oil volumes of 548.8 MBod
    # and total volumes of 1,410.4 MBoed

    match = re.search(
        r"quarterly\s+oil\s+volumes\s+of\s+"
        r"(?P<oil>[\d,.]+)"
        r"\s*mbod"
        r".{0,180}?"
        r"total\s+volumes\s+of\s+"
        r"(?P<total>[\d,.]+)"
        r"\s*mboed",
        normalize_text(
            text
        ),
        flags=re.I,
    )


    if not match:

        return None


    oil = numeric(
        match.group(
            "oil"
        )
    )

    total = numeric(
        match.group(
            "total"
        )
    )


    if (
        pd.isna(
            total
        )
        or
        not (
            TOTAL_PRODUCTION_MIN
            <= total
            <= TOTAL_PRODUCTION_MAX
        )
    ):

        return None


    return {
        "quarter":
            str(
                quarter
            ),

        "filing_date":
            str(
                pd.Timestamp(
                    filing_date
                ).date()
            ),

        "oil":
            oil,

        "ngl":
            np.nan,

        "gas":
            np.nan,

        "reported_total":
            total,

        "table_index":
            -1,

        "table_context":
            "PROSE_FALLBACK",
    }


# ============================================================
# 15. BOE RECONSTRUCTION
# ============================================================

def reconstruct_boe(
    oil,
    ngl,
    gas,
):

    if (
        pd.isna(oil)
        or
        pd.isna(ngl)
        or
        pd.isna(gas)
    ):

        return np.nan


    return float(
        oil
        +
        ngl
        +
        gas / 6.0
    )


def reconstruction_error_pct(
    reported,
    reconstructed,
):

    if (
        pd.isna(reported)
        or
        pd.isna(reconstructed)
        or
        reported <= 0
    ):

        return np.nan


    return float(
        abs(
            reported
            -
            reconstructed
        )
        /
        reported
        *
        100
    )


def finalize_eog_record(
    record,
):

    oil = record.get(
        "oil",
        np.nan,
    )

    ngl = record.get(
        "ngl",
        np.nan,
    )

    gas = record.get(
        "gas",
        np.nan,
    )

    reported = record.get(
        "reported_total",
        np.nan,
    )


    reconstructed = reconstruct_boe(
        oil,
        ngl,
        gas,
    )


    recon_error = reconstruction_error_pct(
        reported,
        reconstructed,
    )


    # --------------------------------------------------------
    # reported + reconstructed 둘 다 존재
    # --------------------------------------------------------

    if (
        pd.notna(
            reported
        )
        and
        pd.notna(
            reconstructed
        )
    ):

        if (
            recon_error
            <=
            EOG_RECON_ERROR_MAX_PCT
        ):

            final_total = (
                reported
            )

            qc_flag = (
                "REPORTED_RECON_MATCH"
            )

            quality = 1.00


        else:

            final_total = (
                reconstructed
            )

            qc_flag = (
                "REPORTED_REJECTED_USE_RECONSTRUCTED"
            )

            quality = 0.85


    # --------------------------------------------------------
    # reconstructed only
    # --------------------------------------------------------

    elif pd.notna(
        reconstructed
    ):

        final_total = (
            reconstructed
        )

        qc_flag = (
            "RECONSTRUCTED_TOTAL"
        )

        quality = 0.90


    # --------------------------------------------------------
    # reported only
    # --------------------------------------------------------

    elif pd.notna(
        reported
    ):

        final_total = (
            reported
        )

        qc_flag = (
            "REPORTED_ONLY"
        )

        quality = 0.70


    else:

        final_total = np.nan

        qc_flag = (
            "NO_VALID_TOTAL"
        )

        quality = 0.0


    return {
        **record,

        "oil_production":
            oil,

        "ngl_production":
            ngl,

        "gas_production":
            gas,

        "reported_total_production":
            reported,

        "reconstructed_total_production":
            reconstructed,

        "reconstruction_error_pct":
            recon_error,

        "total_production":
            final_total,

        "component_qc_flag":
            qc_flag,

        "data_quality_score":
            quality,
    }


# ============================================================
# 16. COMBINE EOG CANDIDATES PER QUARTER
# ============================================================

def combine_candidate_group(
    group
):

    group = group.copy()


    # 완전한 component set + latest filing 우선
    group[
        "component_count"
    ] = (
        group[
            [
                "oil",
                "ngl",
                "gas",
                "reported_total",
            ]
        ]
        .notna()
        .sum(
            axis=1
        )
    )


    group[
        "filing_date_dt"
    ] = pd.to_datetime(
        group[
            "filing_date"
        ],
        errors="coerce",
    )


    group = (
        group.sort_values(
            [
                "component_count",
                "filing_date_dt",
            ],
            ascending=[
                False,
                False,
            ],
        )
    )


    combined = {
        "oil":
            np.nan,

        "ngl":
            np.nan,

        "gas":
            np.nan,

        "reported_total":
            np.nan,
    }


    best_meta = (
        group.iloc[0]
    )


    for _, row in group.iterrows():

        for component in combined:

            if (
                pd.isna(
                    combined[
                        component
                    ]
                )
                and
                pd.notna(
                    row[
                        component
                    ]
                )
            ):

                combined[
                    component
                ] = row[
                    component
                ]


    return {
        **combined,

        "filing_date":
            best_meta[
                "filing_date"
            ],

        "table_index":
            best_meta[
                "table_index"
            ],

        "table_context":
            best_meta[
                "table_context"
            ],
    }


# ============================================================
# 17. EOG SEC EXACT SCAN
# ============================================================

def scan_eog_exact():

    if not EDGAR_IDENTITY:

        raise ValueError(
            "REFRESH_EOG=1이면 "
            "EDGAR_IDENTITY 환경변수가 필요해."
        )


    set_identity(
        EDGAR_IDENTITY
    )


    print(
        "\n"
        + "=" * 90
    )

    print(
        "EOG V3.2.5 ROW-LEVEL SEC SCAN"
    )

    print(
        "=" * 90
    )


    company = Company(
        "EOG"
    )


    filings = (
        company.get_filings(
            form="8-K"
        )
    )


    start_date = (
        AS_OF
        -
        pd.DateOffset(
            years=11
        )
    )


    try:

        filings = filings.filter(
            filing_date=(
                f"{start_date.date()}:"
                f"{AS_OF.date()}"
            )
        )

    except Exception:

        pass


    actual_candidates = []

    guidance_candidates = []

    debug_rows = []


    used_filings = 0


    for filing in filings:

        if (
            used_filings
            >=
            EOG_LOOKBACK_FILINGS
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


        if (
            pd.isna(
                filing_date
            )
            or
            filing_date
            >
            AS_OF
        ):

            continue


        exhibits = []


        try:

            for exhibit in (
                filing.exhibits
            ):

                document_type = str(
                    getattr(
                        exhibit,
                        "document_type",
                        "",
                    )
                ).upper()


                if document_type.startswith(
                    "EX-99"
                ):

                    exhibits.append(
                        exhibit
                    )

        except Exception:

            continue


        if not exhibits:

            continue


        filing_used = False


        for exhibit in exhibits:

            try:

                raw = exhibit.download()

            except Exception:

                continue


            if raw is None:

                continue


            if isinstance(
                raw,
                bytes,
            ):

                raw = raw.decode(
                    "utf-8",
                    errors="ignore",
                )


            raw = str(
                raw
            )


            full_text = html_to_text(
                raw
            )


            lower = (
                full_text.lower()
            )


            if (
                "eog resources"
                not in lower
                or
                (
                    "production"
                    not in lower
                    and
                    "volumes"
                    not in lower
                )
            ):

                continue


            result_q = infer_result_quarter(
                filing_date,
                full_text,
            )


            source = (
                f"{filing_date.date()}:"
                f"{getattr(exhibit, 'document_type', '')}:"
                f"{getattr(exhibit, 'document', '')}"
            )


            table_items = (
                extract_html_tables_with_context(
                    raw
                )
            )


            exhibit_actual = []

            exhibit_guidance = []


            for item in table_items:

                (
                    actual_rows,
                    guidance_rows,
                    row_debug,
                ) = (
                    parse_eog_table_rows(
                        item[
                            "table"
                        ],
                        item[
                            "context"
                        ],
                        item[
                            "table_index"
                        ],
                        filing_date,
                        result_q,
                        full_text,
                    )
                )


                for row in actual_rows:

                    row[
                        "source"
                    ] = source


                for row in guidance_rows:

                    row[
                        "source"
                    ] = source


                for row in row_debug:

                    row[
                        "source"
                    ] = source


                exhibit_actual.extend(
                    actual_rows
                )

                exhibit_guidance.extend(
                    guidance_rows
                )

                debug_rows.extend(
                    row_debug
                )


            # ------------------------------------------------
            # 실제값 prose fallback
            # ------------------------------------------------

            if not exhibit_actual:

                prose_row = (
                    parse_eog_prose_actual(
                        full_text,
                        result_q,
                        filing_date,
                    )
                )


                if prose_row is not None:

                    prose_row[
                        "source"
                    ] = source

                    exhibit_actual.append(
                        prose_row
                    )


            if exhibit_actual:

                actual_candidates.extend(
                    exhibit_actual
                )

                filing_used = True


            if exhibit_guidance:

                guidance_candidates.extend(
                    exhibit_guidance
                )

                filing_used = True


        if filing_used:

            used_filings += 1


    # ========================================================
    # SAVE DEBUG ROWS
    # ========================================================

    debug_df = pd.DataFrame(
        debug_rows
    )


    debug_df.to_csv(
        lake_path(
            "energy_v3_2_5_eog_row_debug.csv"
        ),
        index=False,
    )


    # ========================================================
    # ACTUAL COMBINE
    # ========================================================

    actual_df = pd.DataFrame(
        actual_candidates
    )


    finalized_actual_rows = []


    if not actual_df.empty:

        for quarter, group in (
            actual_df.groupby(
                "quarter"
            )
        ):

            combined = (
                combine_candidate_group(
                    group
                )
            )


            combined[
                "quarter"
            ] = quarter


            finalized_actual_rows.append(
                finalize_eog_record(
                    combined
                )
            )


    final_actual = pd.DataFrame(
        finalized_actual_rows
    )


    # ========================================================
    # GUIDANCE COMBINE
    # ========================================================

    guidance_df = pd.DataFrame(
        guidance_candidates
    )


    finalized_guidance_rows = []


    if not guidance_df.empty:

        for target_q, group in (
            guidance_df.groupby(
                "target_quarter"
            )
        ):

            combined = (
                combine_candidate_group(
                    group.rename(
                        columns={
                            "target_quarter":
                                "quarter"
                        }
                    )
                )
            )


            combined[
                "target_quarter"
            ] = target_q


            finalized = (
                finalize_eog_record(
                    combined
                )
            )


            finalized_guidance_rows.append(
                {
                    "target_quarter":
                        target_q,

                    "filing_date":
                        finalized[
                            "filing_date"
                        ],

                    "guidance_oil_production":
                        finalized[
                            "oil_production"
                        ],

                    "guidance_ngl_production":
                        finalized[
                            "ngl_production"
                        ],

                    "guidance_gas_production":
                        finalized[
                            "gas_production"
                        ],

                    "guidance_reported_total":
                        finalized[
                            "reported_total_production"
                        ],

                    "guidance_reconstructed_total":
                        finalized[
                            "reconstructed_total_production"
                        ],

                    "guidance_reconstruction_error_pct":
                        finalized[
                            "reconstruction_error_pct"
                        ],

                    "guidance_total_production":
                        finalized[
                            "total_production"
                        ],

                    "guidance_component_qc_flag":
                        finalized[
                            "component_qc_flag"
                        ],

                    "guidance_data_quality_score":
                        finalized[
                            "data_quality_score"
                        ],
                }
            )


    final_guidance = pd.DataFrame(
        finalized_guidance_rows
    )


    return (
        final_actual,
        final_guidance,
    )


# ============================================================
# 18. EOG CACHE
# ============================================================

EOG_ACTUAL_CACHE = lake_path(
    "energy_v3_2_5_actual_EOG.csv"
)


EOG_GUIDANCE_CACHE = lake_path(
    "energy_v3_2_5_guidance_EOG.csv"
)


if (
    REFRESH_EOG
    or
    not EOG_ACTUAL_CACHE.exists()
    or
    not EOG_GUIDANCE_CACHE.exists()
):

    (
        eog_actual_raw,
        eog_guidance_raw,
    ) = scan_eog_exact()


    eog_actual_raw.to_csv(
        EOG_ACTUAL_CACHE,
        index=False,
    )


    eog_guidance_raw.to_csv(
        EOG_GUIDANCE_CACHE,
        index=False,
    )


else:

    eog_actual_raw = pd.read_csv(
        EOG_ACTUAL_CACHE
    )


    eog_guidance_raw = pd.read_csv(
        EOG_GUIDANCE_CACHE
    )


# ============================================================
# 19. EOG EXACT CHECK
# ============================================================

print(
    "\n"
    + "=" * 90
)

print(
    "EOG V3.2.5 EXACT CHECK"
)

print(
    "=" * 90
)


if not eog_actual_raw.empty:

    check_columns = [

        "quarter",

        "oil_production",

        "ngl_production",

        "gas_production",

        "reported_total_production",

        "reconstructed_total_production",

        "reconstruction_error_pct",

        "total_production",

        "component_qc_flag",

        "data_quality_score",

    ]


    print(
        eog_actual_raw[
            [
                x
                for x in check_columns
                if x
                in eog_actual_raw.columns
            ]
        ]
        .tail(16)
        .round(2)
        .to_string(
            index=False
        )
    )


if not eog_guidance_raw.empty:

    print(
        "\n===== EOG GUIDANCE ====="
    )


    guidance_columns = [

        "target_quarter",

        "guidance_oil_production",

        "guidance_ngl_production",

        "guidance_gas_production",

        "guidance_reported_total",

        "guidance_reconstructed_total",

        "guidance_reconstruction_error_pct",

        "guidance_total_production",

        "guidance_component_qc_flag",

        "guidance_data_quality_score",

    ]


    print(
        eog_guidance_raw[
            [
                x
                for x in guidance_columns
                if x
                in eog_guidance_raw.columns
            ]
        ]
        .tail(10)
        .round(2)
        .to_string(
            index=False
        )
    )


# ============================================================
# 20. BUILD EOG PERIOD CACHE
# ============================================================

def build_eog_actual_cache(
    df
):

    if df.empty:

        return pd.DataFrame()


    result = df.copy()


    result[
        "quarter"
    ] = pd.PeriodIndex(
        result[
            "quarter"
        ].astype(str),
        freq="Q",
    )


    result = result.set_index(
        "quarter"
    )


    result.index.name = None


    return (
        result.sort_index()
    )


def build_eog_guidance_cache(
    df
):

    if df.empty:

        return pd.DataFrame()


    result = df.copy()


    result[
        "target_quarter"
    ] = pd.PeriodIndex(
        result[
            "target_quarter"
        ].astype(str),
        freq="Q",
    )


    result = result.set_index(
        "target_quarter"
    )


    result.index.name = None


    return (
        result.sort_index()
    )


# ============================================================
# 21. LOAD ALL COMPANY KPI
# ============================================================

actual_kpis = {}

guidance_kpis = {}


for ticker in TICKERS:

    if ticker == "EOG":

        actual_kpis[
            ticker
        ] = (
            build_eog_actual_cache(
                eog_actual_raw
            )
        )


        guidance_kpis[
            ticker
        ] = (
            build_eog_guidance_cache(
                eog_guidance_raw
            )
        )


    else:

        actual_kpis[
            ticker
        ] = read_period_cache(
            lake_path(
                f"energy_v3_2_1_actual_{ticker}.csv"
            )
        )


        guidance_kpis[
            ticker
        ] = read_period_cache(
            lake_path(
                f"energy_v3_2_1_guidance_{ticker}.csv"
            )
        )


# ============================================================
# 22. PERIOD MAPPER
# ============================================================

def map_period_series(
    quarters,
    series,
    default=np.nan,
):

    if (
        series is None
        or
        len(
            series
        )
        == 0
    ):

        return pd.Series(
            default,
            index=quarters.index,
        )


    mapping = (
        series.to_dict()
    )


    return pd.Series(
        [
            mapping.get(
                q,
                default,
            )

            for q
            in quarters
        ],
        index=quarters.index,
    )


# ============================================================
# 23. PRODUCTION QUALITY CONTROL
# ============================================================

def production_quality_control(
    ticker,
    company_panel,
    actual,
):

    df = (
        company_panel
        .sort_values(
            "quarter"
        )
        .reset_index(
            drop=True
        )
        .copy()
    )


    # ========================================================
    # RAW TOTAL
    # ========================================================

    if (
        not actual.empty
        and
        "total_production"
        in actual.columns
    ):

        df[
            "total_production_raw"
        ] = map_period_series(
            df[
                "quarter"
            ],
            actual[
                "total_production"
            ],
        )

    else:

        df[
            "total_production_raw"
        ] = np.nan


    # ========================================================
    # RAW OIL
    # ========================================================

    if (
        not actual.empty
        and
        "oil_production"
        in actual.columns
    ):

        df[
            "oil_production_raw"
        ] = map_period_series(
            df[
                "quarter"
            ],
            actual[
                "oil_production"
            ],
        )

    else:

        df[
            "oil_production_raw"
        ] = np.nan


    # ========================================================
    # EOG optional components
    # ========================================================

    for col in [
        "ngl_production",
        "gas_production",
        "reconstruction_error_pct",
        "data_quality_score",
    ]:

        if (
            not actual.empty
            and
            col
            in actual.columns
        ):

            df[
                col
            ] = map_period_series(
                df[
                    "quarter"
                ],
                actual[
                    col
                ],
            )

        else:

            if (
                col
                ==
                "data_quality_score"
            ):

                df[
                    col
                ] = 1.0

            else:

                df[
                    col
                ] = np.nan


    # ========================================================
    # Absolute sanity
    # ========================================================

    total_candidate = (
        pd.to_numeric(
            df[
                "total_production_raw"
            ],
            errors="coerce",
        )
    )


    total_candidate = (
        total_candidate.where(
            total_candidate.between(
                TOTAL_PRODUCTION_MIN,
                TOTAL_PRODUCTION_MAX,
            )
        )
    )


    oil_candidate = (
        pd.to_numeric(
            df[
                "oil_production_raw"
            ],
            errors="coerce",
        )
    )


    oil_candidate = (
        oil_candidate.where(
            oil_candidate.between(
                OIL_PRODUCTION_MIN,
                OIL_PRODUCTION_MAX,
            )
        )
    )


    df[
        "total_candidate"
    ] = total_candidate


    df[
        "oil_candidate"
    ] = oil_candidate


    # ========================================================
    # Total/Oil sanity
    #
    # Oil만 reject
    # ========================================================

    df[
        "total_oil_ratio"
    ] = (
        df[
            "total_candidate"
        ]
        /
        df[
            "oil_candidate"
        ]
    )


    ratio_bad = (
        df[
            "total_oil_ratio"
        ].notna()

        &

        (
            (
                df[
                    "total_oil_ratio"
                ]
                <
                TOTAL_OIL_RATIO_MIN
            )

            |

            (
                df[
                    "total_oil_ratio"
                ]
                >
                TOTAL_OIL_RATIO_MAX
            )
        )
    )


    df[
        "oil_qc_flag"
    ] = "OK"


    df.loc[
        df[
            "oil_candidate"
        ].isna(),
        "oil_qc_flag"
    ] = "MISSING"


    df.loc[
        ratio_bad,
        "oil_qc_flag"
    ] = "REJECT_OIL_RATIO"


    df.loc[
        ratio_bad,
        "oil_candidate"
    ] = np.nan


    # ========================================================
    # M&A window exception
    # ========================================================

    df[
        "mna_jump_allow"
    ] = (
        df[
            "ma_window"
        ]
        .fillna(0)
        .gt(0)
        .astype(float)
    )


    # ========================================================
    # Sequential regime QC
    # ========================================================

    df[
        "total_production_clean"
    ] = np.nan


    df[
        "total_qc_flag"
    ] = "MISSING"


    df[
        "production_qoq_log_raw"
    ] = np.nan


    df[
        "production_qoq_threshold"
    ] = np.nan


    accepted_value = None
    accepted_quarter = None

    pending_value = None
    pending_quarter = None


    for i in range(
        len(df)
    ):

        q = df.loc[
            i,
            "quarter"
        ]


        current = df.loc[
            i,
            "total_candidate"
        ]


        if (
            pd.isna(
                current
            )
            or
            current
            <= 0
        ):

            continue


        current = float(
            current
        )


        # ----------------------------------------------------
        # Initial regime
        # ----------------------------------------------------

        if (
            accepted_value
            is None
        ):

            if (
                pending_value
                is None
            ):

                pending_value = (
                    current
                )

                pending_quarter = (
                    q
                )

                df.loc[
                    i,
                    "total_qc_flag"
                ] = (
                    "PENDING_INITIAL_REGIME"
                )

                continue


            gap = max(
                1,
                quarter_gap(
                    q,
                    pending_quarter,
                )
            )


            growth = log_ratio_growth(
                current,
                pending_value,
            )


            threshold = (
                REGIME_CONFIRM_MAX_LOG_GROWTH
                *
                np.sqrt(
                    gap
                )
            )


            if (
                gap
                <=
                MAX_REGIME_CONFIRM_GAP
                and
                pd.notna(
                    growth
                )
                and
                abs(
                    growth
                )
                <=
                threshold
            ):

                df.loc[
                    i,
                    "total_production_clean"
                ] = current


                df.loc[
                    i,
                    "total_qc_flag"
                ] = (
                    "INITIAL_REGIME_CONFIRMED"
                )


                accepted_value = (
                    current
                )

                accepted_quarter = (
                    q
                )


                pending_value = None
                pending_quarter = None


            else:

                pending_value = (
                    current
                )

                pending_quarter = (
                    q
                )


            continue


        # ----------------------------------------------------
        # Existing regime
        # ----------------------------------------------------

        gap = max(
            1,
            quarter_gap(
                q,
                accepted_quarter,
            )
        )


        growth = log_ratio_growth(
            current,
            accepted_value,
        )


        threshold = min(
            MAX_ORGANIC_QOQ_LOG_GROWTH
            *
            np.sqrt(
                gap
            ),
            MAX_QOQ_THRESHOLD,
        )


        df.loc[
            i,
            "production_qoq_log_raw"
        ] = growth


        df.loc[
            i,
            "production_qoq_threshold"
        ] = threshold


        if (
            pd.notna(
                growth
            )
            and
            abs(
                growth
            )
            <=
            threshold
        ):

            df.loc[
                i,
                "total_production_clean"
            ] = current


            df.loc[
                i,
                "total_qc_flag"
            ] = "OK"


            accepted_value = (
                current
            )

            accepted_quarter = (
                q
            )


            pending_value = None
            pending_quarter = None


            continue


        # ----------------------------------------------------
        # M&A
        # ----------------------------------------------------

        if (
            df.loc[
                i,
                "mna_jump_allow"
            ]
            >=
            0.5
        ):

            df.loc[
                i,
                "total_production_clean"
            ] = current


            df.loc[
                i,
                "total_qc_flag"
            ] = (
                "MNA_JUMP_ACCEPTED"
            )


            accepted_value = (
                current
            )

            accepted_quarter = (
                q
            )


            pending_value = None
            pending_quarter = None


            continue


        # ----------------------------------------------------
        # New regime confirmation
        # ----------------------------------------------------

        if (
            pending_value
            is not None
        ):

            pending_gap = max(
                1,
                quarter_gap(
                    q,
                    pending_quarter,
                )
            )


            pending_growth = (
                log_ratio_growth(
                    current,
                    pending_value,
                )
            )


            confirm_threshold = (
                REGIME_CONFIRM_MAX_LOG_GROWTH
                *
                np.sqrt(
                    pending_gap
                )
            )


            if (
                pending_gap
                <=
                MAX_REGIME_CONFIRM_GAP
                and
                pd.notna(
                    pending_growth
                )
                and
                abs(
                    pending_growth
                )
                <=
                confirm_threshold
            ):

                df.loc[
                    i,
                    "total_production_clean"
                ] = current


                df.loc[
                    i,
                    "total_qc_flag"
                ] = (
                    "NEW_REGIME_CONFIRMED"
                )


                accepted_value = (
                    current
                )

                accepted_quarter = (
                    q
                )


                pending_value = None
                pending_quarter = None


                continue


        pending_value = (
            current
        )

        pending_quarter = (
            q
        )


        df.loc[
            i,
            "total_qc_flag"
        ] = (
            "REJECT_QOQ_JUMP_PENDING"
        )


    # ========================================================
    # Clean Oil
    # ========================================================

    df[
        "oil_production_clean"
    ] = df[
        "oil_candidate"
    ]


    df.loc[
        df[
            "total_production_clean"
        ].isna(),
        "oil_production_clean"
    ] = np.nan


    # ========================================================
    # Actual data quality
    # ========================================================

    df[
        "actual_data_quality"
    ] = pd.to_numeric(
        df[
            "data_quality_score"
        ],
        errors="coerce",
    ).fillna(
        1.0
    )


    df.loc[
        df[
            "total_production_clean"
        ].isna(),
        "actual_data_quality"
    ] = 0.0


    # ========================================================
    # Save QC
    # ========================================================

    df.to_csv(
        lake_path(
            f"energy_v3_2_5_production_qc_{ticker}.csv"
        ),
        index=False,
    )


    print(
        f"\n{ticker} PRODUCTION QC"
    )

    print(
        "  raw total   :",
        int(
            df[
                "total_production_raw"
            ]
            .notna()
            .sum()
        )
    )

    print(
        "  clean total :",
        int(
            df[
                "total_production_clean"
            ]
            .notna()
            .sum()
        )
    )


    return df


# ============================================================
# 24. RUN PRODUCTION QC
# ============================================================

qc_companies = {}


for ticker in TICKERS:

    company_panel = (
        panel_v21[
            panel_v21[
                "ticker"
            ]
            ==
            ticker
        ]
        .copy()
    )


    qc_companies[
        ticker
    ] = (
        production_quality_control(
            ticker,
            company_panel,
            actual_kpis[
                ticker
            ],
        )
    )


# ============================================================
# 25. STRUCTURAL FEATURES
# ============================================================

def build_structural_company(
    ticker,
    qc_df,
    guidance,
):

    df = (
        qc_df
        .sort_values(
            "quarter"
        )
        .reset_index(
            drop=True
        )
        .copy()
    )


    # ========================================================
    # Guidance total
    # ========================================================

    if (
        not guidance.empty
        and
        "guidance_total_production"
        in guidance.columns
    ):

        df[
            "guidance_total_production"
        ] = map_period_series(
            df[
                "quarter"
            ],
            guidance[
                "guidance_total_production"
            ],
        )

    else:

        df[
            "guidance_total_production"
        ] = np.nan


    # ========================================================
    # Guidance quality
    # ========================================================

    if (
        not guidance.empty
        and
        "guidance_data_quality_score"
        in guidance.columns
    ):

        df[
            "guidance_data_quality"
        ] = map_period_series(
            df[
                "quarter"
            ],
            guidance[
                "guidance_data_quality_score"
            ],
        )

    else:

        df[
            "guidance_data_quality"
        ] = 1.0


    df[
        "guidance_data_quality"
    ] = pd.to_numeric(
        df[
            "guidance_data_quality"
        ],
        errors="coerce",
    ).fillna(
        1.0
    )


    # ========================================================
    # Actual production YoY
    # ========================================================

    df[
        "total_prod_yoy"
    ] = log_growth(
        df[
            "total_production_clean"
        ],
        4,
    )


    df[
        "total_prod_yoy_l1"
    ] = (
        df[
            "total_prod_yoy"
        ]
        .shift(1)
    )


    # Pair quality
    actual_pair_quality = (
        pd.concat(
            [
                df[
                    "actual_data_quality"
                ],

                df[
                    "actual_data_quality"
                ].shift(4),
            ],
            axis=1,
        )
        .min(
            axis=1
        )
    )


    df[
        "actual_pair_quality_l1"
    ] = (
        actual_pair_quality.shift(
            1
        )
    )


    # ========================================================
    # Guidance vs Actual
    # ========================================================

    prior_actual = (
        df[
            "total_production_clean"
        ]
        .shift(4)
    )


    prior_guidance = (
        df[
            "guidance_total_production"
        ]
        .shift(4)
    )


    df[
        "guidance_vs_actual_yoy"
    ] = np.nan


    valid = (
        (
            df[
                "guidance_total_production"
            ]
            > 0
        )
        &
        (
            prior_actual
            > 0
        )
    )


    df.loc[
        valid,
        "guidance_vs_actual_yoy"
    ] = (
        np.log(
            df.loc[
                valid,
                "guidance_total_production"
            ]
            /
            prior_actual.loc[
                valid
            ]
        )
        * 100
    )


    ga_quality = (
        pd.concat(
            [
                df[
                    "guidance_data_quality"
                ],

                df[
                    "actual_data_quality"
                ]
                .shift(4),
            ],
            axis=1,
        )
        .min(
            axis=1
        )
    )


    # ========================================================
    # Guidance vs Guidance
    # ========================================================

    df[
        "guidance_vs_guidance_yoy"
    ] = np.nan


    valid = (
        (
            df[
                "guidance_total_production"
            ]
            > 0
        )
        &
        (
            prior_guidance
            > 0
        )
    )


    df.loc[
        valid,
        "guidance_vs_guidance_yoy"
    ] = (
        np.log(
            df.loc[
                valid,
                "guidance_total_production"
            ]
            /
            prior_guidance.loc[
                valid
            ]
        )
        * 100
    )


    gg_quality = (
        pd.concat(
            [
                df[
                    "guidance_data_quality"
                ],

                df[
                    "guidance_data_quality"
                ]
                .shift(4),
            ],
            axis=1,
        )
        .min(
            axis=1
        )
    )


    # ========================================================
    # Industry fallback
    # ========================================================

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


    # ========================================================
    # Production source
    # ========================================================

    proxy_values = []

    proxy_sources = []

    quality_values = []


    for i in range(
        len(df)
    ):

        # 1. Guidance vs Actual
        if pd.notna(
            df.loc[
                i,
                "guidance_vs_actual_yoy"
            ]
        ):

            value = df.loc[
                i,
                "guidance_vs_actual_yoy"
            ]

            source = (
                "GUIDANCE_VS_ACTUAL"
            )

            quality = (
                SOURCE_QUALITY[
                    source
                ]
                *
                ga_quality.iloc[
                    i
                ]
            )


        # 2. Guidance vs Guidance
        elif pd.notna(
            df.loc[
                i,
                "guidance_vs_guidance_yoy"
            ]
        ):

            value = df.loc[
                i,
                "guidance_vs_guidance_yoy"
            ]

            source = (
                "GUIDANCE_VS_GUIDANCE"
            )

            quality = (
                SOURCE_QUALITY[
                    source
                ]
                *
                gg_quality.iloc[
                    i
                ]
            )


        # 3. Actual vs Actual
        elif pd.notna(
            df.loc[
                i,
                "total_prod_yoy_l1"
            ]
        ):

            value = df.loc[
                i,
                "total_prod_yoy_l1"
            ]

            source = (
                "ACTUAL_VS_ACTUAL"
            )


            pair_quality = df.loc[
                i,
                "actual_pair_quality_l1"
            ]


            if pd.isna(
                pair_quality
            ):

                pair_quality = 1.0


            quality = (
                SOURCE_QUALITY[
                    source
                ]
                *
                pair_quality
            )


        # 4. Industry
        else:

            value = (
                industry_prod.iloc[
                    i
                ]
            )

            source = (
                "INDUSTRY_FALLBACK"
            )

            quality = (
                SOURCE_QUALITY[
                    source
                ]
            )


        if pd.notna(
            value
        ):

            value = float(
                np.clip(
                    value,
                    -60,
                    120,
                )
            )


        proxy_values.append(
            value
        )

        proxy_sources.append(
            source
        )

        quality_values.append(
            float(
                np.clip(
                    quality,
                    0,
                    1,
                )
            )
        )


    df[
        "company_prod_yoy_proxy"
    ] = proxy_values


    df[
        "production_yoy_source"
    ] = proxy_sources


    df[
        "source_quality_score"
    ] = quality_values


    df[
        "has_company_prod"
    ] = (
        df[
            "production_yoy_source"
        ]
        .ne(
            "INDUSTRY_FALLBACK"
        )
        .astype(float)
    )


    df[
        "has_guidance"
    ] = (
        df[
            "guidance_total_production"
        ]
        .notna()
        .astype(float)
    )


    # ========================================================
    # Oil share
    # ========================================================

    oil_share = (
        df[
            "oil_production_clean"
        ]
        /
        df[
            "total_production_clean"
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


    median_oil_share = (
        oil_share.median(
            skipna=True
        )
    )


    if pd.isna(
        median_oil_share
    ):

        median_oil_share = (
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
            median_oil_share
        )
        .clip(
            0.10,
            1.00,
        )
    )


    # ========================================================
    # Price mix
    # ========================================================

    gas_weight = (
        (
            1.0
            -
            df[
                "oil_share_l1"
            ]
        )
        *
        0.50
    )


    oil_like_weight = (
        1.0
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
    # Structural Revenue
    # ========================================================

    df[
        "structural_revenue_log_yoy"
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
        "structural_revenue_log_yoy"
    ] = (
        df[
            "structural_revenue_log_yoy"
        ]
        .clip(
            MIN_LOG_GROWTH,
            MAX_LOG_GROWTH,
        )
    )


    df[
        "structural_revenue_yoy_pct"
    ] = log_to_normal_pct(
        df[
            "structural_revenue_log_yoy"
        ]
    )


    return df


# ============================================================
# 26. BUILD STRUCTURAL PANEL
# ============================================================

frames = []


for ticker in TICKERS:

    frames.append(
        build_structural_company(
            ticker,
            qc_companies[
                ticker
            ],
            guidance_kpis[
                ticker
            ],
        )
    )


structural_panel = (
    pd.concat(
        frames,
        ignore_index=True,
    )
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


structural_panel.to_csv(
    lake_path(
        "energy_v3_2_5_structural_panel.csv"
    ),
    index=False,
)


# ============================================================
# 27. SOURCE SUMMARY
# ============================================================

source_summary = (
    structural_panel
    .groupby(
        [
            "ticker",
            "production_yoy_source",
        ]
    )
    .agg(
        observations=(
            "production_yoy_source",
            "size",
        ),
        avg_quality=(
            "source_quality_score",
            "mean",
        ),
    )
    .reset_index()
)


source_summary.to_csv(
    lake_path(
        "energy_v3_2_5_source_quality_summary.csv"
    ),
    index=False,
)


print(
    "\n"
    + "=" * 90
)

print(
    "PRODUCTION SOURCE SUMMARY"
)

print(
    "=" * 90
)


print(
    source_summary
    .round(2)
    .to_string(
        index=False
    )
)


# ============================================================
# 28. VALIDATION ALIGNMENT
# ============================================================

structural_validation = (
    structural_panel[
        structural_panel[
            "revenue_yoy"
        ]
        .notna()
    ][
        [
            "quarter",
            "ticker",
            "revenue_yoy",
            "structural_revenue_log_yoy",
            "company_prod_yoy_proxy",
            "production_yoy_source",
            "source_quality_score",
            "has_company_prod",
        ]
    ]
    .copy()
    .rename(
        columns={
            "revenue_yoy":
                "actual_log_yoy"
        }
    )
)


v21_validation = (
    validation_v21[
        [
            "quarter",
            "ticker",
            "actual",
            "predicted",
        ]
    ]
    .copy()
    .rename(
        columns={
            "actual":
                "v21_actual_log_yoy",

            "predicted":
                "v21_log_yoy",
        }
    )
)


compare = (
    v21_validation.merge(
        structural_validation,
        on=[
            "quarter",
            "ticker",
        ],
        how="inner",
    )
)


compare[
    "actual_log_yoy"
] = compare[
    "v21_actual_log_yoy"
]


# ============================================================
# 29. BLEND FUNCTIONS
# ============================================================

def best_weight(
    history
):

    if history.empty:

        return 0.0


    best_w = 0.0

    best_error = np.inf


    for weight in (
        BLEND_WEIGHTS
    ):

        prediction = (
            weight
            *
            history[
                "structural_revenue_log_yoy"
            ]
            +
            (
                1.0
                -
                weight
            )
            *
            history[
                "v21_log_yoy"
            ]
        )


        error = mae(
            history[
                "actual_log_yoy"
            ],
            prediction,
        )


        if (
            error
            <
            best_error
        ):

            best_error = (
                error
            )

            best_w = float(
                weight
            )


    return best_w


def guarded_base_weight(
    history
):

    if history.empty:

        return 0.0


    structural_error = mae(
        history[
            "actual_log_yoy"
        ],
        history[
            "structural_revenue_log_yoy"
        ],
    )


    v21_error = mae(
        history[
            "actual_log_yoy"
        ],
        history[
            "v21_log_yoy"
        ],
    )


    if (
        structural_error
        >=
        v21_error
    ):

        return 0.0


    return best_weight(
        history
    )


def quality_adjusted_weight(
    base_weight,
    row
):

    quality = float(
        row[
            "source_quality_score"
        ]
    )


    effective = (
        base_weight
        *
        quality
    )


    if (
        row[
            "production_yoy_source"
        ]
        ==
        "INDUSTRY_FALLBACK"
    ):

        effective = min(
            effective,
            NO_COMPANY_PROD_MAX_WEIGHT,
        )


    return float(
        np.clip(
            effective,
            0,
            1,
        )
    )


# ============================================================
# 30. WALK-FORWARD VALIDATION
# ============================================================

walk_rows = []


for ticker, company_df in (
    compare.groupby(
        "ticker"
    )
):

    company_df = (
        company_df
        .sort_values(
            "quarter"
        )
        .reset_index(
            drop=True
        )
    )


    for i in range(
        len(
            company_df
        )
    ):

        row = company_df.iloc[
            i
        ]


        history = (
            company_df.iloc[
                :i
            ]
        )


        if (
            len(
                history
            )
            <
            MIN_BLEND_HISTORY
        ):

            base_weight = 0.0

        else:

            base_weight = (
                guarded_base_weight(
                    history
                )
            )


        effective_weight = (
            quality_adjusted_weight(
                base_weight,
                row,
            )
        )


        prediction = (
            effective_weight
            *
            row[
                "structural_revenue_log_yoy"
            ]
            +
            (
                1.0
                -
                effective_weight
            )
            *
            row[
                "v21_log_yoy"
            ]
        )


        prediction = float(
            np.clip(
                prediction,
                MIN_LOG_GROWTH,
                MAX_LOG_GROWTH,
            )
        )


        walk_rows.append(
            {
                "quarter":
                    row[
                        "quarter"
                    ],

                "ticker":
                    ticker,

                "actual_log_yoy":
                    row[
                        "actual_log_yoy"
                    ],

                "actual_yoy_pct":
                    log_to_normal_pct(
                        row[
                            "actual_log_yoy"
                        ]
                    ),

                "v21_log_yoy":
                    row[
                        "v21_log_yoy"
                    ],

                "v21_yoy_pct":
                    log_to_normal_pct(
                        row[
                            "v21_log_yoy"
                        ]
                    ),

                "structural_log_yoy":
                    row[
                        "structural_revenue_log_yoy"
                    ],

                "structural_yoy_pct":
                    log_to_normal_pct(
                        row[
                            "structural_revenue_log_yoy"
                        ]
                    ),

                "base_structural_weight":
                    base_weight,

                "source_quality_score":
                    row[
                        "source_quality_score"
                    ],

                "effective_structural_weight":
                    effective_weight,

                "blend_log_yoy":
                    prediction,

                "blend_yoy_pct":
                    log_to_normal_pct(
                        prediction
                    ),

                "company_prod_yoy_proxy":
                    row[
                        "company_prod_yoy_proxy"
                    ],

                "production_yoy_source":
                    row[
                        "production_yoy_source"
                    ],
            }
        )


walk_validation = pd.DataFrame(
    walk_rows
)


# ============================================================
# 31. METRICS
# ============================================================

metric_rows = []


print(
    "\n"
    + "=" * 90
)

print(
    "V3.2.5 WALK-FORWARD VALIDATION"
)

print(
    "=" * 90
)


for ticker, group in (
    walk_validation.groupby(
        "ticker"
    )
):

    metric_rows.append(
        {
            "ticker":
                ticker,

            "V2_1_MAE_log_points":
                mae(
                    group[
                        "actual_log_yoy"
                    ],
                    group[
                        "v21_log_yoy"
                    ],
                ),

            "V2_1_MAE_yoy_pct_points":
                mae_yoy_pct_points(
                    group[
                        "actual_log_yoy"
                    ],
                    group[
                        "v21_log_yoy"
                    ],
                ),

            "Structural_MAE_log_points":
                mae(
                    group[
                        "actual_log_yoy"
                    ],
                    group[
                        "structural_log_yoy"
                    ],
                ),

            "Structural_MAE_yoy_pct_points":
                mae_yoy_pct_points(
                    group[
                        "actual_log_yoy"
                    ],
                    group[
                        "structural_log_yoy"
                    ],
                ),

            "V3_2_5_MAE_log_points":
                mae(
                    group[
                        "actual_log_yoy"
                    ],
                    group[
                        "blend_log_yoy"
                    ],
                ),

            "V3_2_5_MAE_yoy_pct_points":
                mae_yoy_pct_points(
                    group[
                        "actual_log_yoy"
                    ],
                    group[
                        "blend_log_yoy"
                    ],
                ),
        }
    )


metrics = (
    pd.DataFrame(
        metric_rows
    )
    .set_index(
        "ticker"
    )
)


overall_v21_log = mae(
    walk_validation[
        "actual_log_yoy"
    ],
    walk_validation[
        "v21_log_yoy"
    ],
)


overall_v21_pct = (
    mae_yoy_pct_points(
        walk_validation[
            "actual_log_yoy"
        ],
        walk_validation[
            "v21_log_yoy"
        ],
    )
)


overall_struct_log = mae(
    walk_validation[
        "actual_log_yoy"
    ],
    walk_validation[
        "structural_log_yoy"
    ],
)


overall_struct_pct = (
    mae_yoy_pct_points(
        walk_validation[
            "actual_log_yoy"
        ],
        walk_validation[
            "structural_log_yoy"
        ],
    )
)


overall_v325_log = mae(
    walk_validation[
        "actual_log_yoy"
    ],
    walk_validation[
        "blend_log_yoy"
    ],
)


overall_v325_pct = (
    mae_yoy_pct_points(
        walk_validation[
            "actual_log_yoy"
        ],
        walk_validation[
            "blend_log_yoy"
        ],
    )
)


print(
    "\n===== LOG-GROWTH SCALE ====="
)

print(
    f"V2.1       MAE : "
    f"{overall_v21_log:.2f} log-points"
)

print(
    f"Structural MAE : "
    f"{overall_struct_log:.2f} log-points"
)

print(
    f"V3.2.5     MAE : "
    f"{overall_v325_log:.2f} log-points"
)


print(
    "\n===== NORMAL REVENUE YOY SCALE ====="
)

print(
    f"V2.1       MAE : "
    f"{overall_v21_pct:.2f} %p"
)

print(
    f"Structural MAE : "
    f"{overall_struct_pct:.2f} %p"
)

print(
    f"V3.2.5     MAE : "
    f"{overall_v325_pct:.2f} %p"
)


print(
    "\n===== BY TICKER ====="
)

print(
    metrics.round(
        2
    )
)


walk_validation.to_csv(
    lake_path(
        "energy_v3_2_5_validation.csv"
    ),
    index=False,
)


metrics.to_csv(
    lake_path(
        "energy_v3_2_5_metrics.csv"
    )
)


# ============================================================
# 32. FINAL BASE WEIGHTS
# ============================================================

final_base_weights = {}

weight_rows = []


for ticker, group in (
    compare.groupby(
        "ticker"
    )
):

    structural_error = mae(
        group[
            "actual_log_yoy"
        ],
        group[
            "structural_revenue_log_yoy"
        ],
    )


    v21_error = mae(
        group[
            "actual_log_yoy"
        ],
        group[
            "v21_log_yoy"
        ],
    )


    if (
        structural_error
        >=
        v21_error
    ):

        weight = 0.0

        guardrail = (
            "STRUCTURAL_DISABLED"
        )

    else:

        weight = best_weight(
            group
        )

        guardrail = (
            "STRUCTURAL_ENABLED"
        )


    final_base_weights[
        ticker
    ] = weight


    weight_rows.append(
        {
            "ticker":
                ticker,

            "base_structural_weight":
                weight,

            "historical_structural_MAE_log_points":
                structural_error,

            "historical_v21_MAE_log_points":
                v21_error,

            "guardrail":
                guardrail,
        }
    )


weights_df = (
    pd.DataFrame(
        weight_rows
    )
    .set_index(
        "ticker"
    )
)


print(
    "\n===== FINAL BASE WEIGHTS ====="
)

print(
    weights_df.round(
        3
    )
)


weights_df.to_csv(
    lake_path(
        "energy_v3_2_5_blend_weights.csv"
    )
)


# ============================================================
# 33. CURRENT STRUCTURAL NOWCAST
# ============================================================

structural_nowcast_rows = []


for ticker in TICKERS:

    company = (
        structural_panel[
            structural_panel[
                "ticker"
            ]
            ==
            ticker
        ]
        .copy()
    )


    revenue_rows = (
        company[
            company[
                "revenue"
            ].notna()
        ]
    )


    if revenue_rows.empty:

        continue


    last_actual_q = (
        revenue_rows[
            "quarter"
        ].max()
    )


    target_q = (
        last_actual_q
        + 1
    )


    target = (
        company[
            company[
                "quarter"
            ]
            ==
            target_q
        ]
    )


    if target.empty:

        continue


    row = target.iloc[
        0
    ]


    structural_nowcast_rows.append(
        {
            "ticker":
                ticker,

            "nowcast_quarter":
                target_q,

            "structural_log_yoy":
                row[
                    "structural_revenue_log_yoy"
                ],

            "structural_yoy_pct":
                row[
                    "structural_revenue_yoy_pct"
                ],

            "price_mix_yoy":
                row[
                    "price_mix_yoy"
                ],

            "company_prod_yoy_proxy":
                row[
                    "company_prod_yoy_proxy"
                ],

            "production_yoy_source":
                row[
                    "production_yoy_source"
                ],

            "source_quality_score":
                row[
                    "source_quality_score"
                ],

            "guidance_total_production":
                row[
                    "guidance_total_production"
                ],

            "has_company_prod":
                row[
                    "has_company_prod"
                ],

            "has_guidance":
                row[
                    "has_guidance"
                ],
        }
    )


structural_nowcast = pd.DataFrame(
    structural_nowcast_rows
)


structural_nowcast[
    "nowcast_quarter"
] = pd.PeriodIndex(
    structural_nowcast[
        "nowcast_quarter"
    ].astype(str),
    freq="Q",
)


# ============================================================
# 34. MERGE V2.1 NOWCAST
# ============================================================

v21_nowcast = (
    nowcast_v21[
        [
            "ticker",
            "nowcast_quarter",
            "predicted_revenue_yoy",
        ]
    ]
    .copy()
    .rename(
        columns={
            "predicted_revenue_yoy":
                "v21_log_yoy"
        }
    )
)


current = (
    structural_nowcast.merge(
        v21_nowcast,
        on=[
            "ticker",
            "nowcast_quarter",
        ],
        how="inner",
    )
)


# ============================================================
# 35. CURRENT WEIGHTS
# ============================================================

base_weights = []

effective_weights = []


for _, row in (
    current.iterrows()
):

    base = (
        final_base_weights.get(
            row[
                "ticker"
            ],
            0.0,
        )
    )


    effective = (
        quality_adjusted_weight(
            base,
            row,
        )
    )


    base_weights.append(
        base
    )


    effective_weights.append(
        effective
    )


current[
    "base_structural_weight"
] = base_weights


current[
    "structural_weight"
] = effective_weights


current[
    "v21_weight"
] = (
    1.0
    -
    current[
        "structural_weight"
    ]
)


# ============================================================
# 36. FINAL PREDICTION
# ============================================================

current[
    "predicted_revenue_log_yoy"
] = (
    current[
        "structural_weight"
    ]
    *
    current[
        "structural_log_yoy"
    ]
    +
    current[
        "v21_weight"
    ]
    *
    current[
        "v21_log_yoy"
    ]
)


current[
    "predicted_revenue_log_yoy"
] = (
    current[
        "predicted_revenue_log_yoy"
    ]
    .clip(
        MIN_LOG_GROWTH,
        MAX_LOG_GROWTH,
    )
)


current[
    "predicted_revenue_yoy_pct"
] = log_to_normal_pct(
    current[
        "predicted_revenue_log_yoy"
    ]
)


current[
    "v21_yoy_pct"
] = log_to_normal_pct(
    current[
        "v21_log_yoy"
    ]
)


# ============================================================
# 37. REVENUE LEVEL
# ============================================================

revenue_predictions = []


for _, row in (
    current.iterrows()
):

    base_q = (
        row[
            "nowcast_quarter"
        ]
        -
        4
    )


    base = (
        panel_v21[
            (
                panel_v21[
                    "ticker"
                ]
                ==
                row[
                    "ticker"
                ]
            )
            &
            (
                panel_v21[
                    "quarter"
                ]
                ==
                base_q
            )
        ]
    )


    if (
        base.empty
        or
        pd.isna(
            base.iloc[
                0
            ][
                "revenue"
            ]
        )
    ):

        revenue_predictions.append(
            np.nan
        )

        continue


    base_revenue = float(
        base.iloc[
            0
        ][
            "revenue"
        ]
    )


    predicted_revenue = (
        base_revenue
        *
        np.exp(
            row[
                "predicted_revenue_log_yoy"
            ]
            /
            100
        )
    )


    revenue_predictions.append(
        predicted_revenue
    )


current[
    "predicted_revenue"
] = revenue_predictions


current[
    "predicted_revenue_B"
] = (
    current[
        "predicted_revenue"
    ]
    /
    1e9
)


# ============================================================
# 38. MODEL SPREAD / CONFIDENCE
# ============================================================

current[
    "model_spread_log_points"
] = (
    current[
        "structural_log_yoy"
    ]
    -
    current[
        "v21_log_yoy"
    ]
).abs()


def selected_model(
    row
):

    if (
        row[
            "structural_weight"
        ]
        <=
        0.001
    ):

        return "V2.1_ONLY"


    if (
        row[
            "structural_weight"
        ]
        >=
        0.999
    ):

        return "STRUCTURAL_ONLY"


    return "BLEND"


current[
    "selected_model"
] = current.apply(
    selected_model,
    axis=1,
)


def confidence(
    row
):

    if (
        row[
            "base_structural_weight"
        ]
        <=
        0
    ):

        return "LOW"


    if (
        row[
            "production_yoy_source"
        ]
        ==
        "INDUSTRY_FALLBACK"
    ):

        return "LOW"


    if (
        row[
            "source_quality_score"
        ]
        >=
        0.90
        and
        row[
            "model_spread_log_points"
        ]
        <=
        10
    ):

        return "HIGH"


    if (
        row[
            "source_quality_score"
        ]
        >=
        0.70
        and
        row[
            "model_spread_log_points"
        ]
        <=
        20
    ):

        return "MEDIUM"


    return "LOW"


current[
    "confidence"
] = current.apply(
    confidence,
    axis=1,
)


# ============================================================
# 39. FINAL OUTPUT
# ============================================================

output_columns = [

    "ticker",

    "nowcast_quarter",

    "predicted_revenue_B",

    "predicted_revenue_log_yoy",

    "predicted_revenue_yoy_pct",

    "v21_log_yoy",

    "v21_yoy_pct",

    "structural_log_yoy",

    "structural_yoy_pct",

    "base_structural_weight",

    "source_quality_score",

    "structural_weight",

    "v21_weight",

    "selected_model",

    "company_prod_yoy_proxy",

    "production_yoy_source",

    "guidance_total_production",

    "model_spread_log_points",

    "confidence",

]


output = (
    current[
        output_columns
    ]
    .copy()
)


print(
    "\n"
    + "=" * 90
)

print(
    "🚀 ENERGY REVENUE V3.2.5 NOWCAST"
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


output.to_csv(
    lake_path(
        "energy_v3_2_5_nowcast.csv"
    ),
    index=False,
)


# ============================================================
# 40. V3.2.4 BENCHMARK
# ============================================================

previous_metrics_file = lake_path(
    "energy_v3_2_4_metrics.csv"
)


if previous_metrics_file.exists():

    try:

        old_metrics = pd.read_csv(
            previous_metrics_file,
            index_col=0,
        )


        print(
            "\n"
            + "=" * 90
        )

        print(
            "V3.2.4 vs V3.2.5"
        )

        print(
            "=" * 90
        )


        benchmark = metrics.copy()


        if (
            "V3_2_4_MAE_log_points"
            in old_metrics.columns
        ):

            benchmark[
                "V3_2_4_log_MAE"
            ] = old_metrics[
                "V3_2_4_MAE_log_points"
            ]


            benchmark[
                "log_MAE_improvement"
            ] = (
                benchmark[
                    "V3_2_4_log_MAE"
                ]
                -
                benchmark[
                    "V3_2_5_MAE_log_points"
                ]
            )


        if (
            "V3_2_4_MAE_yoy_pct_points"
            in old_metrics.columns
        ):

            benchmark[
                "V3_2_4_pct_MAE"
            ] = old_metrics[
                "V3_2_4_MAE_yoy_pct_points"
            ]


            benchmark[
                "pct_MAE_improvement"
            ] = (
                benchmark[
                    "V3_2_4_pct_MAE"
                ]
                -
                benchmark[
                    "V3_2_5_MAE_yoy_pct_points"
                ]
            )


        print(
            benchmark.round(
                2
            )
        )


    except Exception as exc:

        print(
            "Benchmark load skipped:",
            exc
        )


# ============================================================
# 41. METADATA
# ============================================================

metadata = {

    "version":
        "3.2.5",

    "eog_parser":
        (
            "row-level exact parser with "
            "ACTUAL/GUIDANCE mode switching"
        ),

    "eog_exact_components": [

        "Crude Oil and Condensate (MBod)",

        "Natural Gas Liquids (MBbld)",

        "Natural Gas (MMcfd)",

        "Crude Oil Equivalent (MBoed)",

    ],

    "eog_reconstruction_formula":
        (
            "Oil MBod + NGL MBbld "
            "+ Gas MMcfd / 6 "
            "= Total MBoed"
        ),

    "eog_max_reconstruction_error_pct":
        EOG_RECON_ERROR_MAX_PCT,

    "production_source_priority": [

        "GUIDANCE_VS_ACTUAL",

        "GUIDANCE_VS_GUIDANCE",

        "ACTUAL_VS_ACTUAL",

        "INDUSTRY_FALLBACK",

    ],

    "metrics": [

        "MAE_log_points",

        "MAE_yoy_pct_points",

    ],

}


with open(
    lake_path(
        "energy_v3_2_5_metadata.json"
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
# 42. DONE
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
    "\nMain outputs:"
)


for filename in [

    "energy_v3_2_5_actual_EOG.csv",

    "energy_v3_2_5_guidance_EOG.csv",

    "energy_v3_2_5_eog_row_debug.csv",

    "energy_v3_2_5_structural_panel.csv",

    "energy_v3_2_5_source_quality_summary.csv",

    "energy_v3_2_5_validation.csv",

    "energy_v3_2_5_metrics.csv",

    "energy_v3_2_5_blend_weights.csv",

    "energy_v3_2_5_nowcast.csv",

    "energy_v3_2_5_metadata.json",

]:

    print(
        " -",
        lake_path(
            filename
        )
    )


print(
    "\nProduction QC:"
)


for ticker in TICKERS:

    print(
        " -",
        lake_path(
            f"energy_v3_2_5_production_qc_{ticker}.csv"
        )
    )
