# ============================================================
# ENERGY REVENUE NOWCAST V3.2.4
# ============================================================
#
# INPUT
# ------------------------------------------------------------
# V2.1
#   ./data-lake/energy_v2_1_panel.csv
#   ./data-lake/energy_v2_1_validation.csv
#   ./data-lake/energy_v2_1_nowcast.csv
#
# V3.2.1 cache
#   COP / FANG / DVN actual & guidance
#
# EOG
#   V3.2.4에서 SEC 8-K EX-99 earnings release를 다시 읽음
#
#
# V3.2.4 핵심
# ------------------------------------------------------------
#
# 1. EOG EXACT-TABLE PARSER
#
#    실제 행:
#
#    Crude Oil and Condensate (MBod)
#    Natural Gas Liquids (MBbld)
#    Natural Gas (MMcfd)
#    Total Crude Oil Equivalent (MBoed)
#
#
# 2. BOE RECONSTRUCTION QC
#
#    reconstructed total
#       =
#       oil
#       + NGL
#       + gas / 6
#
#    reported total과 reconstructed total 비교
#
#
# 3. EOG Guidance도 동일한 방식으로 검증
#
#
# 4. V3.2.3 Production Regime QC 유지
#
#
# 5. Production source priority
#
#    GUIDANCE_VS_ACTUAL
#    GUIDANCE_VS_GUIDANCE
#    ACTUAL_VS_ACTUAL
#    INDUSTRY_FALLBACK
#
#
# 6. Validation metric 두 종류 출력
#
#    MAE_log_points
#
#    MAE_yoy_pct_points
#       = 일반적인 Revenue YoY % 간의 평균 절대 %p 오차
#
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

from edgar import Company, set_identity


warnings.filterwarnings("ignore")


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


AS_OF_DATE_ENV = os.getenv(
    "AS_OF_DATE"
)


EDGAR_IDENTITY = os.getenv(
    "EDGAR_IDENTITY"
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
        "50",
    )
)


# ============================================================
# BLENDING
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


TOTAL_PRODUCTION_MIN = 20
TOTAL_PRODUCTION_MAX = 5000

OIL_PRODUCTION_MIN = 5
OIL_PRODUCTION_MAX = 3000

NGL_PRODUCTION_MIN = 0
NGL_PRODUCTION_MAX = 3000

GAS_PRODUCTION_MIN = 0
GAS_PRODUCTION_MAX = 20000


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
# GROWTH LIMIT
# ============================================================

MIN_LOG_GROWTH = -100.0
MAX_LOG_GROWTH = 150.0


# ============================================================
# DEFAULT OIL SHARE
# ============================================================

DEFAULT_OIL_SHARE = {

    "COP":
        0.78,

    "EOG":
        0.78,

    "FANG":
        0.82,

    "DVN":
        0.72,

}


# ============================================================
# 1. HELPERS
# ============================================================

DATA_LAKE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


def lake_path(filename):

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


print("=" * 90)
print("ENERGY REVENUE NOWCAST V3.2.4")
print("=" * 90)

print("AS OF       :", AS_OF.date())
print("TICKERS     :", TICKERS)
print("DATA LAKE   :", DATA_LAKE_DIR.resolve())
print("REFRESH EOG :", REFRESH_EOG)
print("EOG RECON % :", EOG_RECON_ERROR_MAX_PCT)


# ============================================================
# 2. GENERIC FUNCTIONS
# ============================================================

def normalize_text(text):

    if text is None:

        return ""

    text = str(text)

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


def html_to_text(raw):

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

    raw = str(raw)

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


def numeric(value):

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

        return float(value)


    text = str(value).strip()


    negative = (
        text.startswith("(")
        and
        text.endswith(")")
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


    if text in {
        "",
        "-",
        "—",
        "–",
    }:

        return np.nan


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


def log_to_normal_pct(value):

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


    if pd.isna(value):

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
# 3. QUARTER INFERENCE
# ============================================================

QUARTER_WORD = {

    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,

}


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


    filing_date = pd.Timestamp(
        filing_date
    )


    month = filing_date.month
    year = filing_date.year


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
    text,
    result_quarter,
):

    lower = normalize_text(
        text
    ).lower()


    # 3Q 2026
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


    match = re.search(

        r"(first|second|third|fourth)"
        r"\s+quarter"
        r"(?:\s+and.*?)?"
        r"\s+(20\d{2})"
        r"\s+guidance",

        lower,

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
# 4. REQUIRED FILES
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
            f"{path} 없음."
        )


# COP/FANG/DVN은 V3.2.1 cache 사용
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
                f"{path} 없음."
            )


# ============================================================
# 5. LOAD V2.1
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


if "ma_event" not in panel_v21.columns:

    panel_v21[
        "ma_event"
    ] = 0.0


if "ma_window" not in panel_v21.columns:

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


# ============================================================
# 6. CACHE READER
# ============================================================

def read_period_cache(path):

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


    return df.sort_index()


# ============================================================
# 7. EOG EXACT-TABLE HELPERS
# ============================================================

def clean_cell(value):

    if pd.isna(value):

        return ""

    return normalize_text(
        value
    )


def row_cells(row):

    return [
        clean_cell(x)
        for x in row.tolist()
    ]


def numbers_after_label(
    cells,
    label_index,
):

    values = []


    for cell in cells[
        label_index + 1:
    ]:

        value = numeric(
            cell
        )

        if pd.notna(value):

            # year 제거
            if 1990 <= value <= 2100:

                continue

            values.append(
                value
            )


    return values


def find_label_index(
    cells,
    pattern,
):

    for i, cell in enumerate(
        cells
    ):

        if re.search(
            pattern,
            cell,
            flags=re.I,
        ):

            return i


    return None


def first_value_in_range(
    values,
    low,
    high,
):

    for value in values:

        if (
            pd.notna(value)
            and
            low <= value <= high
        ):

            return float(value)


    return np.nan


def guidance_midpoint(
    values,
    low,
    high,
):

    valid = [

        float(x)

        for x in values

        if (
            pd.notna(x)
            and
            low <= x <= high
        )

    ]


    if not valid:

        return np.nan


    # low / high / midpoint
    if len(valid) >= 3:

        expected_mid = (
            valid[0]
            +
            valid[1]
        ) / 2


        # 보통 3번째가 midpoint
        if abs(
            valid[2]
            -
            expected_mid
        ) <= max(
            1.0,
            abs(expected_mid)
            * 0.03,
        ):

            return valid[2]


    if len(valid) >= 2:

        return (
            valid[0]
            +
            valid[1]
        ) / 2


    return valid[0]


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

        * 100

    )


# ============================================================
# 8. EOG TABLE EXTRACTOR
# ============================================================

def parse_eog_table(
    table,
    is_guidance=False,
):

    result = {

        "oil":
            np.nan,

        "ngl":
            np.nan,

        "gas":
            np.nan,

        "reported_total":
            np.nan,
    }


    try:

        table = (
            table
            .copy()
            .fillna("")
        )

    except Exception:

        return result


    # --------------------------------------------------------
    # 먼저 direct rows 탐색
    # --------------------------------------------------------

    section = None


    for _, row in table.iterrows():

        cells = row_cells(
            row
        )


        joined = normalize_text(
            " | ".join(cells)
        )


        lower = joined.lower()


        # ====================================================
        # Direct Key Operational Results rows
        # ====================================================

        label_index = find_label_index(
            cells,
            r"^crude\s+oil\s+and\s+condensate"
            r".*\(mbod\)",
        )


        if label_index is not None:

            values = numbers_after_label(
                cells,
                label_index,
            )


            if is_guidance:

                result["oil"] = guidance_midpoint(
                    values,
                    10,
                    2000,
                )

            else:

                result["oil"] = first_value_in_range(
                    values,
                    10,
                    2000,
                )


            section = "oil"

            continue


        label_index = find_label_index(
            cells,
            r"^natural\s+gas\s+liquids"
            r".*\(mbbld\)",
        )


        if label_index is not None:

            values = numbers_after_label(
                cells,
                label_index,
            )


            if is_guidance:

                result["ngl"] = guidance_midpoint(
                    values,
                    0,
                    2000,
                )

            else:

                result["ngl"] = first_value_in_range(
                    values,
                    0,
                    2000,
                )


            section = "ngl"

            continue


        label_index = find_label_index(
            cells,
            r"^natural\s+gas"
            r"(?!.*liquid)"
            r".*\(mmcfd\)",
        )


        if label_index is not None:

            values = numbers_after_label(
                cells,
                label_index,
            )


            if is_guidance:

                result["gas"] = guidance_midpoint(
                    values,
                    0,
                    20000,
                )

            else:

                result["gas"] = first_value_in_range(
                    values,
                    0,
                    20000,
                )


            section = "gas"

            continue


        label_index = find_label_index(
            cells,
            r"^(?:total\s+)?"
            r"crude\s+oil\s+equivalent"
            r".*\(mboed\)",
        )


        if label_index is not None:

            values = numbers_after_label(
                cells,
                label_index,
            )


            if is_guidance:

                result[
                    "reported_total"
                ] = guidance_midpoint(
                    values,
                    200,
                    4000,
                )

            else:

                result[
                    "reported_total"
                ] = first_value_in_range(
                    values,
                    200,
                    4000,
                )


            section = "total"

            continue


        # ====================================================
        # Results-vs-guidance / guidance section headers
        # ====================================================

        if re.search(
            r"crude\s+oil\s+and\s+condensate"
            r".*volumes.*\(mbod\)",
            lower,
        ):

            section = "oil"

            continue


        if re.search(
            r"natural\s+gas\s+liquids"
            r".*volumes.*\(mbbld\)",
            lower,
        ):

            section = "ngl"

            continue


        if (
            re.search(
                r"natural\s+gas.*volumes.*\(mmcfd\)",
                lower,
            )
            and
            "liquid"
            not in lower
        ):

            section = "gas"

            continue


        if re.search(
            r"crude\s+oil\s+equivalent"
            r".*volumes.*\(mboed\)",
            lower,
        ):

            section = "total"

            continue


        # ====================================================
        # Section의 Total row
        # ====================================================

        first_nonempty = ""

        first_nonempty_index = None


        for i, cell in enumerate(cells):

            if cell.strip():

                first_nonempty = (
                    cell.strip()
                )

                first_nonempty_index = i

                break


        if (
            section is None
            or
            first_nonempty_index is None
        ):

            continue


        if not re.fullmatch(
            r"total",
            first_nonempty,
            flags=re.I,
        ):

            continue


        values = numbers_after_label(
            cells,
            first_nonempty_index,
        )


        if section == "oil":

            if is_guidance:

                value = guidance_midpoint(
                    values,
                    10,
                    2000,
                )

            else:

                value = first_value_in_range(
                    values,
                    10,
                    2000,
                )


            if pd.notna(value):

                result["oil"] = value


        elif section == "ngl":

            if is_guidance:

                value = guidance_midpoint(
                    values,
                    0,
                    2000,
                )

            else:

                value = first_value_in_range(
                    values,
                    0,
                    2000,
                )


            if pd.notna(value):

                result["ngl"] = value


        elif section == "gas":

            if is_guidance:

                value = guidance_midpoint(
                    values,
                    0,
                    20000,
                )

            else:

                value = first_value_in_range(
                    values,
                    0,
                    20000,
                )


            if pd.notna(value):

                result["gas"] = value


        elif section == "total":

            if is_guidance:

                value = guidance_midpoint(
                    values,
                    200,
                    4000,
                )

            else:

                value = first_value_in_range(
                    values,
                    200,
                    4000,
                )


            if pd.notna(value):

                result[
                    "reported_total"
                ] = value


    return result


# ============================================================
# 9. COMBINE EOG TABLE RESULTS
# ============================================================

def combine_eog_results(
    results,
):

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


    # 완전한 table 우선
    sorted_results = sorted(

        results,

        key=lambda x: sum(
            pd.notna(
                x[k]
            )

            for k in [
                "oil",
                "ngl",
                "gas",
                "reported_total",
            ]
        ),

        reverse=True,

    )


    for result in sorted_results:

        for key in combined:

            if (
                pd.isna(
                    combined[key]
                )
                and
                pd.notna(
                    result.get(
                        key
                    )
                )
            ):

                combined[key] = result[
                    key
                ]


    return combined


# ============================================================
# 10. EOG RECONSTRUCTION QC
# ============================================================

def finalize_eog_components(
    components,
):

    oil = components[
        "oil"
    ]

    ngl = components[
        "ngl"
    ]

    gas = components[
        "gas"
    ]

    reported = components[
        "reported_total"
    ]


    reconstructed = reconstruct_boe(
        oil,
        ngl,
        gas,
    )


    recon_error = reconstruction_error_pct(
        reported,
        reconstructed,
    )


    if (
        pd.notna(reported)
        and
        pd.notna(reconstructed)
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

            data_quality = 1.00


        else:

            final_total = (
                reconstructed
            )

            qc_flag = (
                "REPORTED_REJECTED_USE_RECONSTRUCTED"
            )

            data_quality = 0.90


    elif pd.notna(
        reconstructed
    ):

        final_total = (
            reconstructed
        )

        qc_flag = (
            "RECONSTRUCTED_TOTAL"
        )

        data_quality = 0.90


    elif pd.notna(
        reported
    ):

        final_total = (
            reported
        )

        qc_flag = (
            "REPORTED_ONLY"
        )

        data_quality = 0.75


    else:

        final_total = np.nan

        qc_flag = (
            "NO_VALID_TOTAL"
        )

        data_quality = 0.0


    return {

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
            data_quality,
    }


# ============================================================
# 11. DOWNLOAD EOG EXHIBIT
# ============================================================

def download_attachment(
    attachment,
):

    try:

        raw = attachment.download()

    except Exception:

        return (
            "",
            [],
        )


    if isinstance(
        raw,
        bytes,
    ):

        raw = raw.decode(
            "utf-8",
            errors="ignore",
        )


    raw = str(raw)


    text = html_to_text(
        raw
    )


    try:

        tables = pd.read_html(
            StringIO(
                raw
            )
        )

    except Exception:

        tables = []


    return (
        text,
        tables,
    )


# ============================================================
# 12. EOG SEC SCANNER
# ============================================================

def scan_eog_exact():

    if not EDGAR_IDENTITY:

        raise ValueError(
            "REFRESH_EOG=1이면 "
            "EDGAR_IDENTITY가 필요해."
        )


    set_identity(
        EDGAR_IDENTITY
    )


    print(
        "\n"
        + "=" * 90
    )

    print(
        "EOG EXACT SEC TABLE SCAN"
    )

    print(
        "=" * 90
    )


    company = Company(
        "EOG"
    )


    filings = company.get_filings(
        form="8-K"
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


    actual_rows = []

    guidance_rows = []


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
            pd.isna(filing_date)
            or
            filing_date > AS_OF
        ):

            continue


        exhibits = []


        try:

            for exhibit in filing.exhibits:

                doc_type = str(
                    getattr(
                        exhibit,
                        "document_type",
                        "",
                    )
                ).upper()


                if doc_type.startswith(
                    "EX-99"
                ):

                    exhibits.append(
                        exhibit
                    )

        except Exception:

            continue


        filing_used = False


        for exhibit in exhibits:

            text, tables = (
                download_attachment(
                    exhibit
                )
            )


            if (
                not text
                or
                not tables
            ):

                continue


            lower = text.lower()


            if (
                "eog resources"
                not in lower
                or
                "production"
                not in lower
            ):

                continue


            result_q = infer_result_quarter(
                filing_date,
                text,
            )


            actual_table_results = []

            guidance_table_results = []


            for table in tables:

                table_text = normalize_text(

                    " ".join(
                        str(x)
                        for x in table.columns
                    )

                    +

                    " "

                    +

                    " ".join(
                        str(x)
                        for x
                        in table.astype(str)
                        .values.flatten()
                    )

                )


                lower_table = (
                    table_text.lower()
                )


                is_guidance = (
                    "guidance range"
                    in lower_table
                    or
                    (
                        "guidance"
                        in lower_table
                        and
                        "midpoint"
                        in lower_table
                    )
                )


                parsed = parse_eog_table(
                    table,
                    is_guidance=is_guidance,
                )


                if is_guidance:

                    guidance_table_results.append(
                        parsed
                    )

                else:

                    actual_table_results.append(
                        parsed
                    )


            # =================================================
            # Actual
            # =================================================

            combined_actual = (
                combine_eog_results(
                    actual_table_results
                )
            )


            finalized_actual = (
                finalize_eog_components(
                    combined_actual
                )
            )


            if pd.notna(
                finalized_actual[
                    "total_production"
                ]
            ):

                actual_rows.append(
                    {
                        "quarter":
                            str(
                                result_q
                            ),

                        "filing_date":
                            str(
                                filing_date.date()
                            ),

                        **finalized_actual,
                    }
                )


                filing_used = True


            # =================================================
            # Guidance
            # =================================================

            combined_guidance = (
                combine_eog_results(
                    guidance_table_results
                )
            )


            finalized_guidance = (
                finalize_eog_components(
                    combined_guidance
                )
            )


            if pd.notna(
                finalized_guidance[
                    "total_production"
                ]
            ):

                target_q = (
                    infer_guidance_quarter(
                        text,
                        result_q,
                    )
                )


                guidance_rows.append(
                    {
                        "target_quarter":
                            str(
                                target_q
                            ),

                        "filing_date":
                            str(
                                filing_date.date()
                            ),

                        "guidance_total_production":
                            finalized_guidance[
                                "total_production"
                            ],

                        "guidance_oil_production":
                            finalized_guidance[
                                "oil_production"
                            ],

                        "guidance_ngl_production":
                            finalized_guidance[
                                "ngl_production"
                            ],

                        "guidance_gas_production":
                            finalized_guidance[
                                "gas_production"
                            ],

                        "guidance_reported_total":
                            finalized_guidance[
                                "reported_total_production"
                            ],

                        "guidance_reconstructed_total":
                            finalized_guidance[
                                "reconstructed_total_production"
                            ],

                        "guidance_reconstruction_error_pct":
                            finalized_guidance[
                                "reconstruction_error_pct"
                            ],

                        "guidance_component_qc_flag":
                            finalized_guidance[
                                "component_qc_flag"
                            ],

                        "guidance_data_quality_score":
                            finalized_guidance[
                                "data_quality_score"
                            ],
                    }
                )


                filing_used = True


        if filing_used:

            used_filings += 1


    actual_df = pd.DataFrame(
        actual_rows
    )


    guidance_df = pd.DataFrame(
        guidance_rows
    )


    # ========================================================
    # 중복 quarter 처리
    # ========================================================

    if not actual_df.empty:

        actual_df[
            "filing_date"
        ] = pd.to_datetime(
            actual_df[
                "filing_date"
            ]
        )


        actual_df = (

            actual_df

            .sort_values(
                [
                    "quarter",
                    "data_quality_score",
                    "filing_date",
                ]
            )

            .drop_duplicates(
                "quarter",
                keep="last",
            )

        )


    if not guidance_df.empty:

        guidance_df[
            "filing_date"
        ] = pd.to_datetime(
            guidance_df[
                "filing_date"
            ]
        )


        guidance_df = (

            guidance_df

            .sort_values(
                [
                    "target_quarter",
                    "guidance_data_quality_score",
                    "filing_date",
                ]
            )

            .drop_duplicates(
                "target_quarter",
                keep="last",
            )

        )


    return (
        actual_df,
        guidance_df,
    )


# ============================================================
# 13. LOAD/BUILD EOG EXACT CACHE
# ============================================================

EOG_ACTUAL_CACHE = lake_path(
    "energy_v3_2_4_actual_EOG.csv"
)


EOG_GUIDANCE_CACHE = lake_path(
    "energy_v3_2_4_guidance_EOG.csv"
)


if (
    REFRESH_EOG
    or
    not EOG_ACTUAL_CACHE.exists()
    or
    not EOG_GUIDANCE_CACHE.exists()
):

    eog_actual_raw, eog_guidance_raw = (
        scan_eog_exact()
    )


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
# 14. EOG DIAGNOSTIC
# ============================================================

print(
    "\n"
    + "=" * 90
)

print(
    "EOG EXACT TABLE CHECK"
)

print(
    "=" * 90
)


if not eog_actual_raw.empty:

    diagnostic_cols = [

        "quarter",

        "oil_production",

        "ngl_production",

        "gas_production",

        "reported_total_production",

        "reconstructed_total_production",

        "reconstruction_error_pct",

        "total_production",

        "component_qc_flag",

    ]


    print(

        eog_actual_raw[
            diagnostic_cols
        ]

        .tail(12)

        .round(2)

        .to_string(
            index=False
        )

    )


if not eog_guidance_raw.empty:

    print(
        "\n===== EOG GUIDANCE ====="
    )


    guidance_cols = [

        "target_quarter",

        "guidance_oil_production",

        "guidance_ngl_production",

        "guidance_gas_production",

        "guidance_total_production",

        "guidance_reconstruction_error_pct",

        "guidance_component_qc_flag",

    ]


    print(

        eog_guidance_raw[
            guidance_cols
        ]

        .tail(8)

        .round(2)

        .to_string(
            index=False
        )

    )


# ============================================================
# 15. BUILD PERIOD CACHE
# ============================================================

def build_eog_actual_cache(
    df,
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


    return result.sort_index()


def build_eog_guidance_cache(
    df,
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


    return result.sort_index()


# ============================================================
# 16. LOAD ALL COMPANY KPI
# ============================================================

actual_kpis = {}

guidance_kpis = {}


for ticker in TICKERS:

    if ticker == "EOG":

        actual_kpis[
            ticker
        ] = build_eog_actual_cache(
            eog_actual_raw
        )


        guidance_kpis[
            ticker
        ] = build_eog_guidance_cache(
            eog_guidance_raw
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
# 17. PERIOD MAPPER
# ============================================================

def map_period_series(
    quarters,
    series,
    default=np.nan,
):

    if (
        series is None
        or
        len(series) == 0
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

            for q in quarters
        ],

        index=quarters.index,

    )


# ============================================================
# 18. PRODUCTION QC
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
    # Raw total/oil
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
    # Optional EOG components
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
            col in actual.columns
        ):

            df[col] = map_period_series(

                df[
                    "quarter"
                ],

                actual[col],

            )

        else:

            if col == "data_quality_score":

                df[col] = 1.0

            else:

                df[col] = np.nan


    if (
        not actual.empty
        and
        "component_qc_flag"
        in actual.columns
    ):

        df[
            "component_qc_flag"
        ] = map_period_series(

            df[
                "quarter"
            ],

            actual[
                "component_qc_flag"
            ],

            default="NOT_APPLICABLE",

        )

    else:

        df[
            "component_qc_flag"
        ] = "NOT_APPLICABLE"


    # ========================================================
    # Absolute bounds
    # ========================================================

    total_valid = (
        pd.to_numeric(
            df[
                "total_production_raw"
            ],
            errors="coerce",
        )
        .between(
            TOTAL_PRODUCTION_MIN,
            TOTAL_PRODUCTION_MAX,
        )
    )


    oil_valid = (
        pd.to_numeric(
            df[
                "oil_production_raw"
            ],
            errors="coerce",
        )
        .between(
            OIL_PRODUCTION_MIN,
            OIL_PRODUCTION_MAX,
        )
    )


    df[
        "total_candidate"
    ] = (
        df[
            "total_production_raw"
        ]
        .where(
            total_valid
        )
    )


    df[
        "oil_candidate"
    ] = (
        df[
            "oil_production_raw"
        ]
        .where(
            oil_valid
        )
    )


    # ========================================================
    # Total / Oil sanity
    #
    # Bad ratio -> Oil만 reject
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
    # M&A exception
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


        current_value = df.loc[
            i,
            "total_candidate"
        ]


        if (
            pd.isna(current_value)
            or
            current_value <= 0
        ):

            continue


        current_value = float(
            current_value
        )


        # ====================================================
        # Initial regime
        # ====================================================

        if accepted_value is None:

            if pending_value is None:

                pending_value = (
                    current_value
                )

                pending_quarter = q


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
                current_value,
                pending_value,
            )


            threshold = (
                REGIME_CONFIRM_MAX_LOG_GROWTH
                *
                np.sqrt(gap)
            )


            if (
                gap
                <=
                MAX_REGIME_CONFIRM_GAP

                and
                pd.notna(growth)

                and
                abs(growth)
                <=
                threshold
            ):

                accepted_value = (
                    current_value
                )

                accepted_quarter = q


                df.loc[
                    i,
                    "total_production_clean"
                ] = (
                    current_value
                )


                df.loc[
                    i,
                    "total_qc_flag"
                ] = (
                    "INITIAL_REGIME_CONFIRMED"
                )


                pending_value = None
                pending_quarter = None


            else:

                pending_value = (
                    current_value
                )

                pending_quarter = q


                df.loc[
                    i,
                    "total_qc_flag"
                ] = (
                    "PENDING_INITIAL_REGIME"
                )


            continue


        # ====================================================
        # Normal regime
        # ====================================================

        gap = max(
            1,
            quarter_gap(
                q,
                accepted_quarter,
            )
        )


        growth = log_ratio_growth(
            current_value,
            accepted_value,
        )


        threshold = min(

            MAX_ORGANIC_QOQ_LOG_GROWTH
            *
            np.sqrt(gap),

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
            pd.notna(growth)
            and
            abs(growth)
            <=
            threshold
        ):

            df.loc[
                i,
                "total_production_clean"
            ] = current_value


            df.loc[
                i,
                "total_qc_flag"
            ] = "OK"


            accepted_value = (
                current_value
            )

            accepted_quarter = q


            pending_value = None
            pending_quarter = None


            continue


        # ====================================================
        # M&A jump
        # ====================================================

        if (
            df.loc[
                i,
                "mna_jump_allow"
            ]
            >= 0.5
        ):

            df.loc[
                i,
                "total_production_clean"
            ] = current_value


            df.loc[
                i,
                "total_qc_flag"
            ] = "MNA_JUMP_ACCEPTED"


            accepted_value = (
                current_value
            )

            accepted_quarter = q


            pending_value = None
            pending_quarter = None


            continue


        # ====================================================
        # New regime confirmation
        # ====================================================

        if pending_value is not None:

            pending_gap = max(
                1,
                quarter_gap(
                    q,
                    pending_quarter,
                )
            )


            pending_growth = (
                log_ratio_growth(
                    current_value,
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
                ] = current_value


                df.loc[
                    i,
                    "total_qc_flag"
                ] = (
                    "NEW_REGIME_CONFIRMED"
                )


                accepted_value = (
                    current_value
                )

                accepted_quarter = q


                pending_value = None
                pending_quarter = None


                continue


        pending_value = (
            current_value
        )

        pending_quarter = q


        df.loc[
            i,
            "total_qc_flag"
        ] = (
            "REJECT_QOQ_JUMP_PENDING"
        )


    # ========================================================
    # Oil clean
    # ========================================================

    df[
        "oil_production_clean"
    ] = (
        df[
            "oil_candidate"
        ]
    )


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
    ).fillna(1.0)


    # QC reject/pending은 actual quality 0
    invalid_total = (
        df[
            "total_production_clean"
        ]
        .isna()
    )


    df.loc[
        invalid_total,
        "actual_data_quality"
    ] = 0.0


    # ========================================================
    # Save
    # ========================================================

    df.to_csv(

        lake_path(
            f"energy_v3_2_4_production_qc_{ticker}.csv"
        ),

        index=False,

    )


    print(
        f"\n{ticker} PRODUCTION QC"
    )

    print(
        "  raw total :",
        int(
            df[
                "total_production_raw"
            ]
            .notna()
            .sum()
        )
    )

    print(
        "  clean total:",
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
# 19. RUN QC
# ============================================================

qc_companies = {}


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
# 20. STRUCTURAL MODEL
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
    ).fillna(1.0)


    # ========================================================
    # Actual YoY
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


    # ========================================================
    # Actual pair quality
    # ========================================================

    actual_pair_quality = (
        pd.concat(
            [
                df[
                    "actual_data_quality"
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


    df[
        "actual_pair_quality_l1"
    ] = (
        actual_pair_quality
        .shift(1)
    )


    # ========================================================
    # Guidance comparisons
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


    df[
        "guidance_vs_guidance_yoy"
    ] = np.nan


    # --------------------------------------------------------
    # Guidance vs Actual
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # Guidance vs Guidance
    # --------------------------------------------------------

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
    # Source selection
    # ========================================================

    values = []
    sources = []
    qualities = []


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
                SOURCE_QUALITY[source]
                *
                ga_quality.iloc[i]
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
                SOURCE_QUALITY[source]
                *
                gg_quality.iloc[i]
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

            pair_quality = (
                df.loc[
                    i,
                    "actual_pair_quality_l1"
                ]
            )


            if pd.isna(
                pair_quality
            ):

                pair_quality = 1.0


            quality = (
                SOURCE_QUALITY[source]
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
                SOURCE_QUALITY[source]
            )


        if pd.notna(value):

            value = float(
                np.clip(
                    value,
                    -60,
                    120,
                )
            )


        values.append(
            value
        )

        sources.append(
            source
        )

        qualities.append(
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
    ] = values


    df[
        "production_yoy_source"
    ] = sources


    df[
        "source_quality_score"
    ] = qualities


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
        oil_share
        .median(
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

        * 0.50

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
    # Structural revenue
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
    ] = (
        log_to_normal_pct(
            df[
                "structural_revenue_log_yoy"
            ]
        )
    )


    return df


# ============================================================
# 21. BUILD STRUCTURAL PANEL
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
        "energy_v3_2_4_structural_panel.csv"
    ),

    index=False,

)


# ============================================================
# 22. VALIDATION ALIGNMENT
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


compare = v21_validation.merge(

    structural_validation,

    on=[
        "quarter",
        "ticker",
    ],

    how="inner",

)


compare[
    "actual_log_yoy"
] = (
    compare[
        "v21_actual_log_yoy"
    ]
)


# ============================================================
# 23. BEST WEIGHT
# ============================================================

def best_weight(
    history,
):

    if history.empty:

        return 0.0


    best_w = 0.0
    best_error = np.inf


    for weight in BLEND_WEIGHTS:

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


        if error < best_error:

            best_error = error
            best_w = float(
                weight
            )


    return best_w


def guarded_base_weight(
    history,
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
    row,
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
# 24. WALK-FORWARD
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
        len(company_df)
    ):

        row = company_df.iloc[
            i
        ]


        history = company_df.iloc[
            :i
        ]


        if (
            len(history)
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
# 25. METRICS - LOG + NORMAL %p
# ============================================================

metric_rows = []


print(
    "\n"
    + "=" * 90
)

print(
    "V3.2.4 WALK-FORWARD VALIDATION"
)

print(
    "=" * 90
)


for ticker, group in (
    walk_validation.groupby(
        "ticker"
    )
):

    row = {

        "ticker":
            ticker,


        # V2.1
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


        # Structural
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


        # V3.2.4
        "V3_2_4_MAE_log_points":
            mae(
                group[
                    "actual_log_yoy"
                ],
                group[
                    "blend_log_yoy"
                ],
            ),

        "V3_2_4_MAE_yoy_pct_points":
            mae_yoy_pct_points(
                group[
                    "actual_log_yoy"
                ],
                group[
                    "blend_log_yoy"
                ],
            ),

    }


    metric_rows.append(
        row
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


overall_v324_log = mae(
    walk_validation[
        "actual_log_yoy"
    ],
    walk_validation[
        "blend_log_yoy"
    ],
)


overall_v324_pct = (
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
    f"V3.2.4     MAE : "
    f"{overall_v324_log:.2f} log-points"
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
    f"V3.2.4     MAE : "
    f"{overall_v324_pct:.2f} %p"
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
        "energy_v3_2_4_validation.csv"
    ),

    index=False,

)


metrics.to_csv(

    lake_path(
        "energy_v3_2_4_metrics.csv"
    )

)


# ============================================================
# 26. FINAL BASE WEIGHTS
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
        "energy_v3_2_4_blend_weights.csv"
    )

)


# ============================================================
# 27. CURRENT STRUCTURAL NOWCAST
# ============================================================

structural_nowcast_rows = []


for ticker in TICKERS:

    company = (
        structural_panel[
            structural_panel[
                "ticker"
            ]
            == ticker
        ]
        .copy()
    )


    actual_revenue = (
        company[
            company[
                "revenue"
            ]
            .notna()
        ]
    )


    if actual_revenue.empty:

        continue


    last_q = (
        actual_revenue[
            "quarter"
        ]
        .max()
    )


    target_q = (
        last_q
        + 1
    )


    row_df = (
        company[
            company[
                "quarter"
            ]
            == target_q
        ]
    )


    if row_df.empty:

        continue


    row = row_df.iloc[
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
# 28. MERGE V2.1 NOWCAST
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


current = structural_nowcast.merge(

    v21_nowcast,

    on=[
        "ticker",
        "nowcast_quarter",
    ],

    how="inner",

)


# ============================================================
# 29. CURRENT WEIGHTS
# ============================================================

base_weights = []

effective_weights = []


for _, row in current.iterrows():

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
# 30. FINAL PREDICTION
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
] = (
    log_to_normal_pct(
        current[
            "predicted_revenue_log_yoy"
        ]
    )
)


current[
    "v21_yoy_pct"
] = (
    log_to_normal_pct(
        current[
            "v21_log_yoy"
        ]
    )
)


# ============================================================
# 31. REVENUE LEVEL
# ============================================================

revenue_predictions = []


for _, row in current.iterrows():

    base_q = (
        row[
            "nowcast_quarter"
        ]
        - 4
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

            / 100

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
    / 1e9
)


# ============================================================
# 32. CONFIDENCE
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


def confidence(
    row,
):

    if (
        row[
            "base_structural_weight"
        ]
        <= 0
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
        >= 0.90

        and

        row[
            "model_spread_log_points"
        ]
        <= 10
    ):

        return "HIGH"


    if (
        row[
            "source_quality_score"
        ]
        >= 0.70

        and

        row[
            "model_spread_log_points"
        ]
        <= 20
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
# 33. FINAL OUTPUT
# ============================================================

output = current[
    [

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

        "company_prod_yoy_proxy",

        "production_yoy_source",

        "guidance_total_production",

        "model_spread_log_points",

        "confidence",

    ]
].copy()


print(
    "\n"
    + "=" * 90
)

print(
    "🚀 ENERGY REVENUE V3.2.4 NOWCAST"
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
        "energy_v3_2_4_nowcast.csv"
    ),

    index=False,

)


# ============================================================
# 34. METADATA
# ============================================================

metadata = {

    "version":
        "3.2.4",

    "eog_exact_rows": [

        "Crude Oil and Condensate (MBod)",

        "Natural Gas Liquids (MBbld)",

        "Natural Gas (MMcfd)",

        "Total Crude Oil Equivalent (MBoed)",

    ],

    "eog_reconstruction_formula":

        (
            "Oil MBod + NGL MBbld "
            "+ Natural Gas MMcfd / 6 "
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
        "energy_v3_2_4_metadata.json"
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
# 35. DONE
# ============================================================

print(
    "\n"
    + "=" * 90
)

print("DONE")

print("=" * 90)


print(
    "\nMain outputs:"
)


for filename in [

    "energy_v3_2_4_actual_EOG.csv",

    "energy_v3_2_4_guidance_EOG.csv",

    "energy_v3_2_4_structural_panel.csv",

    "energy_v3_2_4_validation.csv",

    "energy_v3_2_4_metrics.csv",

    "energy_v3_2_4_blend_weights.csv",

    "energy_v3_2_4_nowcast.csv",

    "energy_v3_2_4_metadata.json",

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
            f"energy_v3_2_4_production_qc_{ticker}.csv"
        )
    )
