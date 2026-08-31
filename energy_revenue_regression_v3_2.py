# ============================================================
# ENERGY REVENUE NOWCAST V3.2
#
# 개선점
# ------------------------------------------------------------
# 1. COP:
#    "Production for ... quarter ... was X MBOED"
#    total-company production만 강하게 선택
#
# 2. EOG:
#    earnings release 전용 parser
#
#    actual:
#      Quarterly oil volumes of X MBod
#      total volumes of Y MBoed
#
#    guidance:
#      Total Crude Oil Equivalent Volumes (MBoed)
#      Q3 Guidance Range / Midpoint
#
# 3. FANG / DVN:
#    기존에 잘 작동했던 production/guidance parser 유지
#
# 4. Residual Ridge 제거
#
# 5. V2.1 vs Structural:
#
#    Final =
#        w * Structural
#        + (1-w) * V2.1
#
#    회사별 w를 과거 validation으로 자동 학습
#
# 6. Blend weight도 walk-forward 방식으로 검증
#
#
# 필요한 기존 파일
# ------------------------------------------------------------
# ./data-lake/energy_v2_1_panel.csv
# ./data-lake/energy_v2_1_validation.csv
# ./data-lake/energy_v2_1_nowcast.csv
#
#
# 필수 ENV
# ------------------------------------------------------------
# EDGAR_IDENTITY
#
#
# 선택 ENV
# ------------------------------------------------------------
# DATA_LAKE_DIR=./data-lake
# TICKERS=COP,EOG,FANG,DVN
# AS_OF_DATE=2026-08-31
# REFRESH_KPI=1
# EARNINGS_LOOKBACK_FILINGS=50
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

EDGAR_IDENTITY = os.getenv(
    "EDGAR_IDENTITY"
)


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


AS_OF_DATE_ENV = os.getenv(
    "AS_OF_DATE"
)


REFRESH_KPI = (
    os.getenv(
        "REFRESH_KPI",
        "0"
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
        "50"
    )
)


# Structural blend 후보
BLEND_WEIGHTS = np.round(
    np.arange(
        0.0,
        1.0001,
        0.05
    ),
    2
)


# weight walk-forward에서
# 최소 과거 observation
MIN_BLEND_HISTORY = 3


# 회사 생산량이 하나도 없다면
# Structural weight 최대치
NO_COMPANY_PROD_MAX_WEIGHT = 0.25


# prediction safety
MIN_GROWTH = -100.0
MAX_GROWTH = 150.0


# ============================================================
# 1. ENV CHECK
# ============================================================

if not EDGAR_IDENTITY:

    raise ValueError(
        "EDGAR_IDENTITY 환경변수가 필요해.\n"
        '예: export EDGAR_IDENTITY='
        '"Your Name you@example.com"'
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
    exist_ok=True
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


print("=" * 90)
print("ENERGY REVENUE NOWCAST V3.2")
print("=" * 90)

print("AS OF      :", AS_OF.date())
print("TICKERS    :", TICKERS)
print("DATA LAKE  :", DATA_LAKE_DIR.resolve())
print("REFRESH KPI:", REFRESH_KPI)


# ============================================================
# 2. LOAD V2.1 FILES
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


for required_file in [
    PANEL_FILE,
    VALIDATION_FILE,
    NOWCAST_FILE,
]:

    if not required_file.exists():

        raise FileNotFoundError(
            f"{required_file} 없음.\n"
            "먼저 V2.1을 실행해줘."
        )


panel_v21 = pd.read_csv(
    PANEL_FILE
)


panel_v21["quarter"] = pd.PeriodIndex(
    panel_v21["quarter"].astype(str),
    freq="Q"
)


panel_v21 = (
    panel_v21[
        panel_v21["ticker"].isin(
            TICKERS
        )
    ]
    .copy()
)


validation_v21 = pd.read_csv(
    VALIDATION_FILE
)


validation_v21["quarter"] = pd.PeriodIndex(
    validation_v21["quarter"].astype(str),
    freq="Q"
)


nowcast_v21 = pd.read_csv(
    NOWCAST_FILE
)


nowcast_v21["nowcast_quarter"] = pd.PeriodIndex(
    nowcast_v21[
        "nowcast_quarter"
    ].astype(str),
    freq="Q"
)


print(
    "\nV2.1 panel     :",
    panel_v21.shape
)

print(
    "V2.1 validation:",
    validation_v21.shape
)

print(
    "V2.1 nowcast   :",
    nowcast_v21.shape
)


# ============================================================
# 3. TEXT HELPERS
# ============================================================

def normalize_text(
    text
):

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
        text
    )

    return text.strip()


def html_to_text(
    raw
):

    if raw is None:

        return ""

    if isinstance(
        raw,
        bytes
    ):

        raw = raw.decode(
            "utf-8",
            errors="ignore"
        )

    raw = str(raw)


    # script/style 제거
    raw = re.sub(
        r"<script.*?</script>",
        " ",
        raw,
        flags=re.I | re.S
    )

    raw = re.sub(
        r"<style.*?</style>",
        " ",
        raw,
        flags=re.I | re.S
    )


    # HTML tag 제거
    raw = re.sub(
        r"<[^>]+>",
        " ",
        raw
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
        )
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


    try:

        value = float(text)

    except Exception:

        return np.nan


    if negative:

        value = -abs(
            value
        )


    return value


def find_numbers(
    text
):

    text = normalize_text(
        text
    )


    tokens = re.findall(
        r"\(?-?\$?"
        r"\d[\d,]*"
        r"(?:\.\d+)?"
        r"\)?",
        text
    )


    result = []


    for token in tokens:

        value = numeric(
            token
        )


        if pd.isna(value):

            continue


        # 연도 제거
        if 1990 <= value <= 2100:

            continue


        result.append(
            value
        )


    return result


# ============================================================
# 4. GROWTH HELPER
# ============================================================

def log_growth(
    series,
    periods=4
):

    series = pd.to_numeric(
        series,
        errors="coerce"
    )


    lagged = series.shift(
        periods
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


    result.loc[
        valid
    ] = (
        np.log(
            series.loc[valid]
            /
            lagged.loc[valid]
        )
        * 100
    )


    return result


# ============================================================
# 5. QUARTER INFERENCE
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


def infer_result_quarter(
    filing_date,
    text
):

    lower = normalize_text(
        text
    ).lower()


    # second quarter 2026
    match = re.search(
        r"(first|second|third|fourth)"
        r"\s+quarter"
        r"(?:\s+of)?"
        r"\s+(20\d{2})",
        lower
    )


    if match:

        q = QUARTER_WORD[
            match.group(1)
        ]

        year = int(
            match.group(2)
        )

        return pd.Period(
            f"{year}Q{q}",
            freq="Q"
        )


    # quarter ended June 30, 2026
    match = re.search(

        r"quarter\s+ended\s+"

        r"(january|february|march|"
        r"april|may|june|"
        r"july|august|september|"
        r"october|november|december)"

        r"\s+\d{1,2},?\s+"

        r"(20\d{2})",

        lower

    )


    if match:

        month = MONTH_MAP[
            match.group(1)
        ]

        year = int(
            match.group(2)
        )

        q = (
            (month - 1)
            // 3
            + 1
        )

        return pd.Period(
            f"{year}Q{q}",
            freq="Q"
        )


    # filing date fallback
    filing_date = pd.Timestamp(
        filing_date
    )


    month = filing_date.month
    year = filing_date.year


    if month <= 3:

        return pd.Period(
            f"{year - 1}Q4",
            freq="Q"
        )


    if month <= 6:

        return pd.Period(
            f"{year}Q1",
            freq="Q"
        )


    if month <= 9:

        return pd.Period(
            f"{year}Q2",
            freq="Q"
        )


    return pd.Period(
        f"{year}Q3",
        freq="Q"
    )


def quarter_from_word(
    qword,
    year
):

    return pd.Period(
        (
            f"{int(year)}"
            f"Q{QUARTER_WORD[qword.lower()]}"
        ),
        freq="Q"
    )


# ============================================================
# 6. UNIT CONVERSION
# ============================================================

def total_to_mboed(
    value,
    unit
):

    value = numeric(
        value
    )

    if pd.isna(value):

        return np.nan


    unit = normalize_text(
        unit
    ).lower()


    # million BOE/day
    if (
        "million" in unit
        or
        "mmboed" in unit
        or
        "mmboe/d" in unit
    ):

        return value * 1000


    # raw BOE/day
    if (
        "boe per day" in unit
        or
        "boe/day" in unit
        or
        "boe/d" in unit
    ):

        if (
            "mboe" not in unit
            and
            value > 10000
        ):

            return (
                value / 1000
            )


    return value


def oil_to_mbod(
    value,
    unit
):

    value = numeric(
        value
    )

    if pd.isna(value):

        return np.nan


    unit = normalize_text(
        unit
    ).lower()


    if (
        "million" in unit
        or
        "mmbo/d" in unit
    ):

        return value * 1000


    if (
        "barrels per day"
        in unit
        and
        value > 10000
    ):

        return value / 1000


    return value


# ============================================================
# 7. PLAUSIBILITY
# ============================================================

def valid_total(
    value
):

    return (
        pd.notna(value)
        and
        20 <= value <= 5000
    )


def valid_oil(
    value
):

    return (
        pd.notna(value)
        and
        5 <= value <= 3000
    )


# ============================================================
# 8. ATTACHMENTS
# ============================================================

def download_attachment(
    attachment
):

    try:

        raw = attachment.download()

    except Exception:

        return (
            "",
            []
        )


    if isinstance(
        raw,
        bytes
    ):

        raw = raw.decode(
            "utf-8",
            errors="ignore"
        )


    raw = str(
        raw
    )


    text = html_to_text(
        raw
    )


    tables = []


    try:

        tables = pd.read_html(
            StringIO(
                raw
            )
        )

    except Exception:

        pass


    return (
        text,
        tables
    )


# ============================================================
# 9. RESULT RECORDS
# ============================================================

def actual_record(
    ticker,
    quarter,
    filing_date,
    total=np.nan,
    oil=np.nan,
    score=100,
    source="",
    raw_text="",
):

    return {

        "ticker":
            ticker,

        "quarter":
            str(quarter),

        "filing_date":
            str(
                pd.Timestamp(
                    filing_date
                ).date()
            ),

        "total_production":
            total,

        "oil_production":
            oil,

        "score":
            score,

        "source":
            source,

        "raw_text":
            normalize_text(
                raw_text
            )[:1500],

    }


def guidance_record(
    ticker,
    quarter,
    filing_date,
    total=np.nan,
    oil=np.nan,
    score=100,
    source="",
    raw_text="",
):

    return {

        "ticker":
            ticker,

        "target_quarter":
            str(quarter),

        "filing_date":
            str(
                pd.Timestamp(
                    filing_date
                ).date()
            ),

        "guidance_total_production":
            total,

        "guidance_oil_production":
            oil,

        "score":
            score,

        "source":
            source,

        "raw_text":
            normalize_text(
                raw_text
            )[:1500],

    }


# ============================================================
# 10. COP PARSER
# ============================================================

def parse_cop(
    text,
    tables,
    filing_date,
    source
):

    actuals = []
    guidance = []


    quarter = infer_result_quarter(
        filing_date,
        text
    )


    # ========================================================
    # COP ACTUAL
    #
    # 강하게 이 문장만 우선:
    #
    # Production for the second quarter of 2026
    # was 2,248 MBOED
    # ========================================================

    patterns = [

        (
            r"production\s+for\s+the\s+"
            r"(?:first|second|third|fourth)"
            r"\s+quarter"
            r"(?:\s+of\s+20\d{2})?"
            r"\s+was\s+"
            r"(?P<value>[\d,.]+)"
            r"\s*"
            r"(?P<unit>"
            r"MBOED|MBOE/D|"
            r"million\s+barrels\s+of\s+"
            r"oil\s+equivalent\s+per\s+day"
            r")"
        ),

        (
            r"delivered\s+total\s+company"
            r".{0,100}?"
            r"production\s+of\s+"
            r"(?P<value>[\d,.]+)"
            r"\s*"
            r"(?P<unit>"
            r"MBOED|"
            r"thousand\s+barrels\s+of\s+"
            r"oil\s+equivalent\s+per\s+day"
            r")"
        ),

    ]


    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.I
        )


        if not match:

            continue


        value = total_to_mboed(
            match.group("value"),
            match.group("unit")
        )


        if valid_total(
            value
        ):

            actuals.append(
                actual_record(
                    "COP",
                    quarter,
                    filing_date,
                    total=value,
                    score=120,
                    source=source,
                    raw_text=match.group(0),
                )
            )

            break


    # ========================================================
    # COP GUIDANCE
    #
    # Third-quarter 2026 production
    # is expected to be
    # 2.29 to 2.32 million BOE/day
    # ========================================================

    pattern = (

        r"(?P<qword>"
        r"first|second|third|fourth"
        r")"

        r"[-\s]quarter"

        r"(?:\s+(?P<year>20\d{2}))?"

        r"\s+production"

        r".{0,80}?"

        r"(?:expected|forecast|guidance)"

        r".{0,100}?"

        r"(?P<low>\d+(?:\.\d+)?)"

        r"\s*(?:to|-)\s*"

        r"(?P<high>\d+(?:\.\d+)?)"

        r"\s*"

        r"(?P<unit>"
        r"million\s+barrels\s+of\s+"
        r"oil\s+equivalent\s+per\s+day|"
        r"MMBOED|MBOED"
        r")"

    )


    match = re.search(
        pattern,
        text,
        flags=re.I
    )


    if match:

        qword = match.group(
            "qword"
        )


        year_text = match.group(
            "year"
        )


        if year_text:

            year = int(
                year_text
            )

        else:

            year = (
                quarter.year
            )


            target_q_number = (
                QUARTER_WORD[
                    qword.lower()
                ]
            )


            if (
                target_q_number
                <
                quarter.quarter
            ):

                year += 1


        target_q = quarter_from_word(
            qword,
            year
        )


        low = total_to_mboed(
            match.group("low"),
            match.group("unit")
        )


        high = total_to_mboed(
            match.group("high"),
            match.group("unit")
        )


        midpoint = (
            low + high
        ) / 2


        if valid_total(
            midpoint
        ):

            guidance.append(
                guidance_record(
                    "COP",
                    target_q,
                    filing_date,
                    total=midpoint,
                    score=120,
                    source=source,
                    raw_text=match.group(0),
                )
            )


    return (
        actuals,
        guidance
    )


# ============================================================
# 11. EOG PARSER
# ============================================================

def parse_eog(
    text,
    tables,
    filing_date,
    source
):

    actuals = []
    guidance = []


    quarter = infer_result_quarter(
        filing_date,
        text
    )


    # ========================================================
    # EOG ACTUAL PROSE
    #
    # Quarterly oil volumes of 548.8 MBod
    # and total volumes of 1,410.4 MBoed
    # ========================================================

    pattern = (

        r"quarterly\s+oil\s+volumes\s+of\s+"

        r"(?P<oil>[\d,.]+)"

        r"\s*MBod"

        r".{0,100}?"

        r"total\s+volumes\s+of\s+"

        r"(?P<total>[\d,.]+)"

        r"\s*MBoed"

    )


    match = re.search(
        pattern,
        text,
        flags=re.I
    )


    if match:

        oil = numeric(
            match.group("oil")
        )

        total = numeric(
            match.group("total")
        )


        if (
            valid_oil(oil)
            and
            valid_total(total)
        ):

            actuals.append(
                actual_record(
                    "EOG",
                    quarter,
                    filing_date,
                    total=total,
                    oil=oil,
                    score=130,
                    source=source,
                    raw_text=match.group(0),
                )
            )


    # ========================================================
    # EOG ACTUAL TABLE FALLBACK
    # ========================================================

    if not actuals:

        found_total = np.nan
        found_oil = np.nan


        for table in tables:

            try:

                rows = (
                    table
                    .fillna("")
                )

            except Exception:

                continue


            for _, row in rows.iterrows():

                row_text = normalize_text(
                    " | ".join(
                        str(x)
                        for x
                        in row.tolist()
                    )
                )


                lower = row_text.lower()


                # Key Operational Results
                if (
                    "crude oil and condensate"
                    in lower
                    and
                    "mbod"
                    in lower
                ):

                    nums = find_numbers(
                        row_text
                    )


                    if nums:

                        possible = nums[0]

                        if valid_oil(
                            possible
                        ):

                            found_oil = (
                                possible
                            )


                if (
                    "total crude oil equivalent"
                    in lower
                    and
                    "mboe"
                    in lower
                ):

                    nums = find_numbers(
                        row_text
                    )


                    if nums:

                        possible = nums[0]

                        if valid_total(
                            possible
                        ):

                            found_total = (
                                possible
                            )


        if (
            valid_total(
                found_total
            )
            or
            valid_oil(
                found_oil
            )
        ):

            actuals.append(
                actual_record(
                    "EOG",
                    quarter,
                    filing_date,
                    total=found_total,
                    oil=found_oil,
                    score=110,
                    source=source,
                    raw_text=(
                        "EOG dedicated actual table"
                    ),
                )
            )


    # ========================================================
    # EOG GUIDANCE TABLE
    #
    # Third Quarter Guidance:
    #
    # Crude Oil Equivalent Volumes (MBoed)
    # Total | low | - | high | midpoint
    #
    # ========================================================

    for table in tables:

        try:

            table_clean = (
                table
                .fillna("")
            )

        except Exception:

            continue


        # columns + cells
        table_text = normalize_text(

            " ".join(
                str(x)
                for x
                in table_clean.columns
            )

            +

            " "

            +

            " ".join(
                str(x)
                for x
                in table_clean.astype(str)
                .values.flatten()
            )

        )


        lower_table = (
            table_text.lower()
        )


        # guidance table만
        if (
            "guidance"
            not in lower_table
        ):

            continue


        # target quarter
        target_q = None


        match = re.search(
            r"([1-4])q\s*(20\d{2})",
            lower_table
        )


        if match:

            target_q = pd.Period(
                (
                    f"{match.group(2)}"
                    f"Q{match.group(1)}"
                ),
                freq="Q"
            )


        else:

            match = re.search(
                r"(first|second|third|fourth)"
                r"\s+quarter"
                r".{0,20}?"
                r"(20\d{2})",
                lower_table
            )


            if match:

                target_q = quarter_from_word(
                    match.group(1),
                    match.group(2)
                )


        if target_q is None:

            continue


        section = None

        guidance_total = np.nan
        guidance_oil = np.nan


        for _, row in (
            table_clean.iterrows()
        ):

            row_text = normalize_text(
                " | ".join(
                    str(x)
                    for x
                    in row.tolist()
                )
            )


            lower = row_text.lower()


            if (
                "crude oil and condensate"
                in lower
                and
                "volume"
                in lower
            ):

                section = "oil"
                continue


            if (
                "crude oil equivalent"
                in lower
                and
                "volume"
                in lower
            ):

                section = "total"
                continue


            # Total row
            if (
                section is not None
                and
                re.search(
                    r"^\s*total\b",
                    lower
                )
            ):

                nums = find_numbers(
                    row_text
                )


                # guidance range:
                # low, high, midpoint, ...
                if len(nums) >= 3:

                    midpoint = nums[2]

                elif len(nums) >= 2:

                    midpoint = (
                        nums[0]
                        +
                        nums[1]
                    ) / 2

                else:

                    continue


                if (
                    section == "oil"
                    and
                    valid_oil(midpoint)
                ):

                    guidance_oil = (
                        midpoint
                    )


                if (
                    section == "total"
                    and
                    valid_total(midpoint)
                ):

                    guidance_total = (
                        midpoint
                    )


        if (
            valid_total(
                guidance_total
            )
            or
            valid_oil(
                guidance_oil
            )
        ):

            guidance.append(
                guidance_record(
                    "EOG",
                    target_q,
                    filing_date,
                    total=guidance_total,
                    oil=guidance_oil,
                    score=130,
                    source=source,
                    raw_text=(
                        "EOG dedicated guidance table"
                    ),
                )
            )


    return (
        actuals,
        guidance
    )


# ============================================================
# 12. FANG PARSER
# ============================================================

def parse_fang(
    text,
    tables,
    filing_date,
    source
):

    actuals = []
    guidance = []


    quarter = infer_result_quarter(
        filing_date,
        text
    )


    # ========================================================
    # ACTUAL
    #
    # average oil production of 525 MBO/d
    # ... 1,018 MBOE/d
    # ========================================================

    patterns = [

        (
            r"(?:average\s+)?oil\s+production"
            r".{0,30}?"
            r"(?P<oil>[\d,.]+)"
            r"\s*MBO/D"
            r".{0,100}?"
            r"(?P<total>[\d,.]+)"
            r"\s*MBOE/D"
        ),

        (
            r"(?P<oil>[\d,.]+)"
            r"\s*MBO/D"
            r".{0,100}?"
            r"(?P<total>[\d,.]+)"
            r"\s*MBOE/D"
        ),

    ]


    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.I
        )


        if not match:

            continue


        oil = numeric(
            match.group("oil")
        )

        total = numeric(
            match.group("total")
        )


        if (
            valid_oil(oil)
            and
            valid_total(total)
        ):

            actuals.append(
                actual_record(
                    "FANG",
                    quarter,
                    filing_date,
                    total=total,
                    oil=oil,
                    score=120,
                    source=source,
                    raw_text=match.group(0),
                )
            )

            break


    # ========================================================
    # GUIDANCE
    #
    # Q3 2026 Oil production - MBO/d
    # (total - MBOE/d)
    #
    # 517 - 527
    # (995 - 1,015)
    # ========================================================

    pattern = (

        r"Q(?P<q>[1-4])\s*"

        r"(?P<year>20\d{2})"

        r".{0,180}?"

        r"oil\s+production"

        r".{0,160}?"

        r"(?P<oil_low>[\d,.]+)"

        r"\s*-\s*"

        r"(?P<oil_high>[\d,.]+)"

        r".{0,100}?"

        r"(?P<total_low>[\d,.]+)"

        r"\s*-\s*"

        r"(?P<total_high>[\d,.]+)"

    )


    match = re.search(
        pattern,
        text,
        flags=re.I
    )


    if match:

        target_q = pd.Period(
            (
                f"{match.group('year')}"
                f"Q{match.group('q')}"
            ),
            freq="Q"
        )


        oil_mid = (
            numeric(
                match.group(
                    "oil_low"
                )
            )
            +
            numeric(
                match.group(
                    "oil_high"
                )
            )
        ) / 2


        total_mid = (
            numeric(
                match.group(
                    "total_low"
                )
            )
            +
            numeric(
                match.group(
                    "total_high"
                )
            )
        ) / 2


        if (
            valid_oil(oil_mid)
            and
            valid_total(total_mid)
        ):

            guidance.append(
                guidance_record(
                    "FANG",
                    target_q,
                    filing_date,
                    total=total_mid,
                    oil=oil_mid,
                    score=120,
                    source=source,
                    raw_text=match.group(0),
                )
            )


    return (
        actuals,
        guidance
    )


# ============================================================
# 13. DVN PARSER
# ============================================================

def parse_dvn(
    text,
    tables,
    filing_date,
    source
):

    actuals = []
    guidance = []


    quarter = infer_result_quarter(
        filing_date,
        text
    )


    # ========================================================
    # ACTUAL
    #
    # production averaged 853,000 Boe per day
    # oil totaled 390,000 barrels per day
    # ========================================================

    total_match = re.search(

        r"production\s+averaged\s+"

        r"(?P<value>[\d,.]+)"

        r"\s*"

        r"(?P<unit>"
        r"boe\s+per\s+day|"
        r"MBOE/D|"
        r"MBOED"
        r")",

        text,

        flags=re.I,

    )


    oil_match = re.search(

        r"oil\s+(?:production\s+)?"
        r"(?:totaled|averaged)\s+"

        r"(?P<value>[\d,.]+)"

        r"\s*"

        r"(?P<unit>"
        r"barrels\s+per\s+day|"
        r"MBO/D"
        r")",

        text,

        flags=re.I,

    )


    total = np.nan
    oil = np.nan


    if total_match:

        total = total_to_mboed(
            total_match.group(
                "value"
            ),
            total_match.group(
                "unit"
            ),
        )


    if oil_match:

        oil = oil_to_mbod(
            oil_match.group(
                "value"
            ),
            oil_match.group(
                "unit"
            ),
        )


    if (
        valid_total(total)
        or
        valid_oil(oil)
    ):

        actuals.append(
            actual_record(
                "DVN",
                quarter,
                filing_date,
                total=total,
                oil=oil,
                score=120,
                source=source,
                raw_text=(
                    f"{total_match.group(0) if total_match else ''} "
                    f"{oil_match.group(0) if oil_match else ''}"
                ),
            )
        )


    # ========================================================
    # GUIDANCE
    # ========================================================

    pattern = (

        r"(?:in|for)\s+the\s+"

        r"(?P<qword>"
        r"first|second|third|fourth"
        r")"

        r"\s+quarter"

        r"(?:\s+of)?\s+"

        r"(?P<year>20\d{2})"

        r".{0,250}?"

        r"(?:total\s+)?production"

        r".{0,120}?"

        r"(?:between|from)"

        r"\s*"

        r"(?P<low>[\d,.]+)"

        r"\s*(?:and|to|-)\s*"

        r"(?P<high>[\d,.]+)"

        r"\s*"

        r"(?P<unit>"
        r"boe\s+per\s+day|"
        r"MBOE/D|"
        r"MBOED"
        r")"

    )


    match = re.search(
        pattern,
        text,
        flags=re.I
    )


    if match:

        target_q = quarter_from_word(
            match.group("qword"),
            match.group("year")
        )


        low = total_to_mboed(
            match.group("low"),
            match.group("unit")
        )


        high = total_to_mboed(
            match.group("high"),
            match.group("unit")
        )


        midpoint = (
            low + high
        ) / 2


        if valid_total(
            midpoint
        ):

            guidance.append(
                guidance_record(
                    "DVN",
                    target_q,
                    filing_date,
                    total=midpoint,
                    score=120,
                    source=source,
                    raw_text=match.group(0),
                )
            )


    return (
        actuals,
        guidance
    )


# ============================================================
# 14. GENERIC FALLBACK
# ============================================================

def parse_generic(
    ticker,
    text,
    tables,
    filing_date,
    source
):

    actuals = []
    guidance = []


    quarter = infer_result_quarter(
        filing_date,
        text
    )


    pattern = (

        r"(?:total\s+)?production"

        r".{0,80}?"

        r"(?:was|averaged|of)\s+"

        r"(?P<value>[\d,.]+)"

        r"\s*"

        r"(?P<unit>"
        r"MBOED|"
        r"MBOE/D|"
        r"boe\s+per\s+day"
        r")"

    )


    match = re.search(
        pattern,
        text,
        flags=re.I
    )


    if match:

        value = total_to_mboed(
            match.group("value"),
            match.group("unit")
        )


        if valid_total(value):

            actuals.append(
                actual_record(
                    ticker,
                    quarter,
                    filing_date,
                    total=value,
                    score=60,
                    source=source,
                    raw_text=match.group(0),
                )
            )


    return (
        actuals,
        guidance
    )


# ============================================================
# 15. COMPANY PARSER ROUTER
# ============================================================

def parse_company(
    ticker,
    text,
    tables,
    filing_date,
    source
):

    if ticker == "COP":

        return parse_cop(
            text,
            tables,
            filing_date,
            source
        )


    if ticker == "EOG":

        return parse_eog(
            text,
            tables,
            filing_date,
            source
        )


    if ticker == "FANG":

        return parse_fang(
            text,
            tables,
            filing_date,
            source
        )


    if ticker == "DVN":

        return parse_dvn(
            text,
            tables,
            filing_date,
            source
        )


    return parse_generic(
        ticker,
        text,
        tables,
        filing_date,
        source
    )


# ============================================================
# 16. SCAN SEC 8-K EARNINGS RELEASES
# ============================================================

def scan_company(
    ticker
):

    print(
        "\n"
        + "=" * 80
    )

    print(
        f"SEC EARNINGS SCAN: {ticker}"
    )

    print(
        "=" * 80
    )


    company = Company(
        ticker
    )


    filings = company.get_filings(
        form="8-K"
    )


    start_date = (
        AS_OF
        -
        pd.DateOffset(
            years=10
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


    actual_records = []
    guidance_records = []


    used_filings = 0


    for filing in filings:

        if (
            used_filings
            >=
            EARNINGS_LOOKBACK_FILINGS
        ):

            break


        filing_date = pd.to_datetime(
            getattr(
                filing,
                "filing_date",
                None
            ),
            errors="coerce"
        )


        if pd.isna(
            filing_date
        ):

            continue


        if filing_date > AS_OF:

            continue


        exhibits = []


        try:

            for exhibit in filing.exhibits:

                doc_type = str(
                    getattr(
                        exhibit,
                        "document_type",
                        ""
                    )
                ).upper()


                if doc_type.startswith(
                    "EX-99"
                ):

                    exhibits.append(
                        exhibit
                    )

        except Exception:

            pass


        # earnings exhibit 없는 8-K는 무시
        if not exhibits:

            continue


        filing_used = False


        for exhibit in exhibits:

            text, tables = download_attachment(
                exhibit
            )


            if not text:

                continue


            lower = text.lower()


            # earnings/production 관련 문서만
            if (
                "production"
                not in lower
            ):

                continue


            source = (
                f"{filing_date.date()}:"
                f"{getattr(exhibit, 'document_type', '')}:"
                f"{getattr(exhibit, 'document', '')}"
            )


            actual, guidance = (
                parse_company(
                    ticker,
                    text,
                    tables,
                    filing_date,
                    source
                )
            )


            if (
                actual
                or
                guidance
            ):

                filing_used = True


            actual_records.extend(
                actual
            )

            guidance_records.extend(
                guidance
            )


        if filing_used:

            used_filings += 1


    actual_df = pd.DataFrame(
        actual_records
    )


    guidance_df = pd.DataFrame(
        guidance_records
    )


    actual_candidate_file = lake_path(
        (
            f"energy_v3_2_"
            f"actual_candidates_{ticker}.csv"
        )
    )


    guidance_candidate_file = lake_path(
        (
            f"energy_v3_2_"
            f"guidance_candidates_{ticker}.csv"
        )
    )


    actual_df.to_csv(
        actual_candidate_file,
        index=False
    )


    guidance_df.to_csv(
        guidance_candidate_file,
        index=False
    )


    print(
        "  candidate actuals :",
        len(actual_df)
    )

    print(
        "  candidate guidance:",
        len(guidance_df)
    )


    return (
        actual_df,
        guidance_df
    )


# ============================================================
# 17. SELECT BEST ACTUAL
# ============================================================

def select_actuals(
    ticker,
    candidates
):

    if candidates.empty:

        return pd.DataFrame()


    work = candidates.copy()


    work["quarter"] = pd.PeriodIndex(
        work["quarter"].astype(str),
        freq="Q"
    )


    work["filing_date"] = pd.to_datetime(
        work["filing_date"],
        errors="coerce"
    )


    selected = []


    for quarter, group in work.groupby(
        "quarter"
    ):

        # score 우선
        # 같은 score면 최신 filing
        row = (
            group
            .sort_values(
                [
                    "score",
                    "filing_date",
                ],
                ascending=[
                    False,
                    False,
                ]
            )
            .iloc[0]
        )


        selected.append(
            row
        )


    selected_df = pd.DataFrame(
        selected
    )


    selected_df = (
        selected_df
        .sort_values(
            "quarter"
        )
    )


    output = (
        selected_df[
            [
                "quarter",
                "total_production",
                "oil_production",
            ]
        ]
        .set_index(
            "quarter"
        )
    )


    output.index = pd.PeriodIndex(
        output.index,
        freq="Q"
    )


    selected_file = lake_path(
        (
            f"energy_v3_2_"
            f"actual_selected_{ticker}.csv"
        )
    )


    selected_df.to_csv(
        selected_file,
        index=False
    )


    return output


# ============================================================
# 18. SELECT BEST GUIDANCE
# ============================================================

def select_guidance(
    ticker,
    candidates
):

    if candidates.empty:

        return pd.DataFrame()


    work = candidates.copy()


    work[
        "target_quarter"
    ] = pd.PeriodIndex(
        work[
            "target_quarter"
        ].astype(str),
        freq="Q"
    )


    work[
        "filing_date"
    ] = pd.to_datetime(
        work[
            "filing_date"
        ],
        errors="coerce"
    )


    selected = []


    for quarter, group in work.groupby(
        "target_quarter"
    ):

        # target quarter가 끝나기 전에
        # 알려진 guidance만 사용
        quarter_end = quarter.end_time


        valid = group[
            group[
                "filing_date"
            ]
            <= quarter_end
        ]


        if valid.empty:

            continue


        row = (
            valid
            .sort_values(
                [
                    "score",
                    "filing_date",
                ],
                ascending=[
                    False,
                    False,
                ]
            )
            .iloc[0]
        )


        selected.append(
            row
        )


    selected_df = pd.DataFrame(
        selected
    )


    if selected_df.empty:

        return pd.DataFrame()


    output = (
        selected_df[
            [
                "target_quarter",
                "guidance_total_production",
                "guidance_oil_production",
            ]
        ]
        .set_index(
            "target_quarter"
        )
    )


    output.index = pd.PeriodIndex(
        output.index,
        freq="Q"
    )


    selected_file = lake_path(
        (
            f"energy_v3_2_"
            f"guidance_selected_{ticker}.csv"
        )
    )


    selected_df.to_csv(
        selected_file,
        index=False
    )


    return output


# ============================================================
# 19. CACHE
# ============================================================

def load_or_build_company_kpi(
    ticker
):

    actual_cache = lake_path(
        f"energy_v3_2_actual_{ticker}.csv"
    )


    guidance_cache = lake_path(
        f"energy_v3_2_guidance_{ticker}.csv"
    )


    if (
        actual_cache.exists()
        and
        guidance_cache.exists()
        and
        not REFRESH_KPI
    ):

        print(
            f"\nLoading cached V3.2 KPI: {ticker}"
        )


        actual = pd.read_csv(
            actual_cache,
            index_col=0
        )


        actual.index = pd.PeriodIndex(
            actual.index.astype(str),
            freq="Q"
        )


        guidance = pd.read_csv(
            guidance_cache,
            index_col=0
        )


        guidance.index = pd.PeriodIndex(
            guidance.index.astype(str),
            freq="Q"
        )


        return (
            actual,
            guidance
        )


    candidates_actual, candidates_guidance = (
        scan_company(
            ticker
        )
    )


    actual = select_actuals(
        ticker,
        candidates_actual
    )


    guidance = select_guidance(
        ticker,
        candidates_guidance
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
        guidance
    )


# ============================================================
# 20. LOAD ALL KPI
# ============================================================

actual_kpis = {}
guidance_kpis = {}


for ticker in TICKERS:

    try:

        actual, guidance = (
            load_or_build_company_kpi(
                ticker
            )
        )


        actual_kpis[
            ticker
        ] = actual


        guidance_kpis[
            ticker
        ] = guidance


    except Exception as exc:

        print(
            f"\n❌ {ticker}: "
            f"{repr(exc)}"
        )


        actual_kpis[
            ticker
        ] = pd.DataFrame()


        guidance_kpis[
            ticker
        ] = pd.DataFrame()


# ============================================================
# 21. KPI COVERAGE
# ============================================================

print(
    "\n"
    + "=" * 90
)

print(
    "V3.2 PRODUCTION KPI COVERAGE"
)

print(
    "=" * 90
)


coverage_rows = []


for ticker in TICKERS:

    actual = actual_kpis[
        ticker
    ]

    guidance = guidance_kpis[
        ticker
    ]


    actual_total = (
        actual[
            "total_production"
        ]
        .notna()
        .sum()

        if (
            not actual.empty
            and
            "total_production"
            in actual.columns
        )

        else 0
    )


    actual_oil = (
        actual[
            "oil_production"
        ]
        .notna()
        .sum()

        if (
            not actual.empty
            and
            "oil_production"
            in actual.columns
        )

        else 0
    )


    guidance_total = (
        guidance[
            "guidance_total_production"
        ]
        .notna()
        .sum()

        if (
            not guidance.empty
            and
            "guidance_total_production"
            in guidance.columns
        )

        else 0
    )


    print(
        f"\n{ticker}"
    )

    print(
        "  actual total production :",
        actual_total
    )

    print(
        "  actual oil production   :",
        actual_oil
    )

    print(
        "  total production guidance:",
        guidance_total
    )


    coverage_rows.append(
        {
            "ticker":
                ticker,

            "actual_total":
                actual_total,

            "actual_oil":
                actual_oil,

            "guidance_total":
                guidance_total,
        }
    )


pd.DataFrame(
    coverage_rows
).to_csv(
    lake_path(
        "energy_v3_2_kpi_coverage.csv"
    ),
    index=False
)


# ============================================================
# 22. STRUCTURAL FEATURE ENGINEERING
# ============================================================

DEFAULT_OIL_SHARE = {

    "COP": 0.78,

    "EOG": 0.78,

    "FANG": 0.82,

    "DVN": 0.72,

}


def build_structural_company(
    ticker,
    company_panel,
    actual,
    guidance
):

    df = (
        company_panel
        .sort_values(
            "quarter"
        )
        .copy()
    )


    df.index = pd.PeriodIndex(
        df["quarter"],
        freq="Q"
    )


    # ========================================================
    # ACTUAL PRODUCTION
    # ========================================================

    if (
        not actual.empty
        and
        "total_production"
        in actual.columns
    ):

        df[
            "total_production"
        ] = (
            actual[
                "total_production"
            ]
            .reindex(
                df.index
            )
        )

    else:

        df[
            "total_production"
        ] = np.nan


    if (
        not actual.empty
        and
        "oil_production"
        in actual.columns
    ):

        df[
            "oil_production"
        ] = (
            actual[
                "oil_production"
            ]
            .reindex(
                df.index
            )
        )

    else:

        df[
            "oil_production"
        ] = np.nan


    # ========================================================
    # GUIDANCE
    # ========================================================

    if (
        not guidance.empty
        and
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

    else:

        df[
            "guidance_total_production"
        ] = np.nan


    # ========================================================
    # HISTORICAL PRODUCTION GROWTH
    # ========================================================

    df[
        "total_prod_yoy"
    ] = log_growth(
        df[
            "total_production"
        ],
        4
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
    # GUIDANCE YoY
    #
    # current guidance
    # /
    # same quarter last year actual
    # ========================================================

    prior_year_actual = (
        df[
            "total_production"
        ]
        .shift(4)
    )


    df[
        "guidance_total_prod_yoy"
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


    # ========================================================
    # INDUSTRY FALLBACK
    # ========================================================

    industry_prod_proxy = (
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
    # COMPANY PRODUCTION PROXY
    #
    # 1. Current-quarter guidance
    # 2. Previous-quarter company YoY
    # 3. Industry
    # ========================================================

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
            industry_prod_proxy
        )
        .clip(
            -60,
            120
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
    # OIL SHARE
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
            np.nan
        )
        .clip(
            0.10,
            1.00
        )
    )


    company_oil_share = (
        oil_share
        .median(
            skipna=True
        )
    )


    if pd.isna(
        company_oil_share
    ):

        company_oil_share = (
            DEFAULT_OIL_SHARE.get(
                ticker,
                0.75
            )
        )


    df[
        "oil_share_l1"
    ] = (
        oil_share
        .shift(1)
        .fillna(
            company_oil_share
        )
        .clip(
            0.1,
            1.0
        )
    )


    # ========================================================
    # PRICE MIX
    #
    # Oil + NGL = oil-like
    #
    # residual non-oil BOE 중
    # 절반만 Henry Hub에 직접 노출
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
    # STRUCTURAL REVENUE
    #
    # log Revenue
    # ~
    # log Price
    # +
    # log Volume
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
            MIN_GROWTH,
            MAX_GROWTH
        )
    )


    df.index = np.arange(
        len(df)
    )


    return df


# ============================================================
# 23. BUILD STRUCTURAL PANEL
# ============================================================

structural_frames = []


for ticker in TICKERS:

    base = (
        panel_v21[
            panel_v21[
                "ticker"
            ]
            == ticker
        ]
        .copy()
    )


    if base.empty:

        continue


    company = build_structural_company(

        ticker,

        base,

        actual_kpis[
            ticker
        ],

        guidance_kpis[
            ticker
        ],

    )


    structural_frames.append(
        company
    )


structural_panel = (
    pd.concat(
        structural_frames,
        ignore_index=True
    )
)


structural_panel[
    "quarter"
] = pd.PeriodIndex(
    structural_panel[
        "quarter"
    ].astype(str),
    freq="Q"
)


structural_panel = (
    structural_panel
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
        "energy_v3_2_structural_panel.csv"
    ),
    index=False
)


# ============================================================
# 24. STRUCTURAL VALIDATION
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
            "structural_revenue_yoy",
            "company_prod_yoy_proxy",
            "guidance_total_prod_yoy",
            "total_prod_yoy_l1",
            "has_company_prod",
            "has_guidance",
        ]
    ]
    .copy()
)


structural_validation = (
    structural_validation.rename(
        columns={
            "revenue_yoy":
                "actual"
        }
    )
)


# ============================================================
# 25. ALIGN WITH V2.1 VALIDATION
# ============================================================

v21 = validation_v21[
    [
        "quarter",
        "ticker",
        "actual",
        "predicted",
    ]
].copy()


v21 = v21.rename(
    columns={
        "predicted":
            "v21_predicted"
    }
)


compare = v21.merge(

    structural_validation,

    on=[
        "quarter",
        "ticker",
    ],

    how="inner",

    suffixes=(
        "_v21",
        "_struct"
    )

)


# actual duplicate cleanup
if (
    "actual_v21"
    in compare.columns
):

    compare[
        "actual"
    ] = compare[
        "actual_v21"
    ]


elif (
    "actual"
    not in compare.columns
):

    compare[
        "actual"
    ] = compare[
        "actual_struct"
    ]


# ============================================================
# 26. BEST BLEND WEIGHT
# ============================================================

def best_weight(
    history
):

    if history.empty:

        return 0.5


    best_w = 0.5
    best_mae = np.inf


    for w in BLEND_WEIGHTS:

        prediction = (
            w
            *
            history[
                "structural_revenue_yoy"
            ]

            +

            (
                1 - w
            )
            *
            history[
                "v21_predicted"
            ]
        )


        mae = np.mean(
            np.abs(
                history[
                    "actual"
                ]
                -
                prediction
            )
        )


        if mae < best_mae:

            best_mae = mae
            best_w = float(w)


    return best_w


# ============================================================
# 27. WALK-FORWARD BLEND VALIDATION
# ============================================================

blend_rows = []


for ticker, group in (
    compare.groupby(
        "ticker"
    )
):

    group = (
        group
        .sort_values(
            "quarter"
        )
        .reset_index(
            drop=True
        )
    )


    for i in range(
        len(group)
    ):

        current = group.iloc[
            i
        ]


        history = group.iloc[
            :i
        ]


        if (
            len(history)
            <
            MIN_BLEND_HISTORY
        ):

            weight = 0.50

        else:

            weight = best_weight(
                history
            )


        # company production 없는 structural은
        # weight 제한
        if (
            current[
                "has_company_prod"
            ]
            < 0.5
        ):

            weight = min(
                weight,
                NO_COMPANY_PROD_MAX_WEIGHT
            )


        prediction = (
            weight
            *
            current[
                "structural_revenue_yoy"
            ]

            +

            (
                1 - weight
            )
            *
            current[
                "v21_predicted"
            ]
        )


        prediction = np.clip(
            prediction,
            MIN_GROWTH,
            MAX_GROWTH
        )


        blend_rows.append(
            {
                "quarter":
                    current[
                        "quarter"
                    ],

                "ticker":
                    ticker,

                "actual":
                    current[
                        "actual"
                    ],

                "v21_predicted":
                    current[
                        "v21_predicted"
                    ],

                "structural_predicted":
                    current[
                        "structural_revenue_yoy"
                    ],

                "structural_weight":
                    weight,

                "blend_predicted":
                    prediction,

                "company_prod_yoy_proxy":
                    current[
                        "company_prod_yoy_proxy"
                    ],

                "has_company_prod":
                    current[
                        "has_company_prod"
                    ],

                "has_guidance":
                    current[
                        "has_guidance"
                    ],
            }
        )


blend_validation = pd.DataFrame(
    blend_rows
)


# ============================================================
# 28. METRICS
# ============================================================

def mae(
    actual,
    predicted
):

    return float(
        np.mean(
            np.abs(
                np.asarray(actual)
                -
                np.asarray(predicted)
            )
        )
    )


metric_rows = []


print(
    "\n"
    + "=" * 90
)

print(
    "V3.2 WALK-FORWARD BLEND VALIDATION"
)

print(
    "=" * 90
)


for ticker, group in (
    blend_validation.groupby(
        "ticker"
    )
):

    v21_mae = mae(
        group["actual"],
        group["v21_predicted"]
    )


    structural_mae = mae(
        group["actual"],
        group["structural_predicted"]
    )


    blend_mae = mae(
        group["actual"],
        group["blend_predicted"]
    )


    metric_rows.append(
        {
            "ticker":
                ticker,

            "V2_1_MAE":
                v21_mae,

            "Structural_MAE":
                structural_mae,

            "Blend_MAE":
                blend_mae,

            "vs_V2_1_improvement_pct":
                (
                    (
                        v21_mae
                        -
                        blend_mae
                    )
                    /
                    v21_mae
                    *
                    100
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


overall_v21 = mae(
    blend_validation["actual"],
    blend_validation["v21_predicted"]
)


overall_structural = mae(
    blend_validation["actual"],
    blend_validation[
        "structural_predicted"
    ]
)


overall_blend = mae(
    blend_validation["actual"],
    blend_validation[
        "blend_predicted"
    ]
)


print(
    f"\nOverall V2.1 MAE     : "
    f"{overall_v21:.2f} pp"
)

print(
    f"Overall Structural   : "
    f"{overall_structural:.2f} pp"
)

print(
    f"Overall V3.2 Blend   : "
    f"{overall_blend:.2f} pp"
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
    blend_validation
    .tail(20)
    .round(2)
    .to_string(
        index=False
    )
)


blend_validation.to_csv(
    lake_path(
        "energy_v3_2_validation.csv"
    ),
    index=False
)


metrics.to_csv(
    lake_path(
        "energy_v3_2_metrics.csv"
    )
)


# ============================================================
# 29. FINAL STRUCTURAL WEIGHT PER COMPANY
# ============================================================

final_weights = {}


weight_rows = []


for ticker, group in (
    compare.groupby(
        "ticker"
    )
):

    weight = best_weight(
        group
    )


    structural_mae = mae(
        group[
            "actual"
        ],
        group[
            "structural_revenue_yoy"
        ]
    )


    v21_mae = mae(
        group[
            "actual"
        ],
        group[
            "v21_predicted"
        ]
    )


    final_weights[
        ticker
    ] = weight


    weight_rows.append(
        {
            "ticker":
                ticker,

            "structural_weight":
                weight,

            "v21_weight":
                1 - weight,

            "historical_structural_mae":
                structural_mae,

            "historical_v21_mae":
                v21_mae,
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
    "\n===== FINAL COMPANY BLEND WEIGHTS ====="
)

print(
    weights_df.round(
        3
    )
)


weights_df.to_csv(
    lake_path(
        "energy_v3_2_blend_weights.csv"
    )
)


# ============================================================
# 30. STRUCTURAL NOWCAST ROWS
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


    actual = company[
        company[
            "revenue"
        ]
        .notna()
    ]


    if actual.empty:

        continue


    last_actual_q = (
        actual[
            "quarter"
        ]
        .max()
    )


    target_q = (
        last_actual_q
        + 1
    )


    row = company[
        company[
            "quarter"
        ]
        == target_q
    ]


    if row.empty:

        continue


    row = row.iloc[
        0
    ]


    structural_nowcast_rows.append(
        {
            "ticker":
                ticker,

            "nowcast_quarter":
                target_q,

            "structural_revenue_yoy":
                row[
                    "structural_revenue_yoy"
                ],

            "price_mix_yoy":
                row[
                    "price_mix_yoy"
                ],

            "company_prod_yoy_proxy":
                row[
                    "company_prod_yoy_proxy"
                ],

            "guidance_total_prod_yoy":
                row[
                    "guidance_total_prod_yoy"
                ],

            "total_prod_yoy_l1":
                row[
                    "total_prod_yoy_l1"
                ],

            "guidance_total_production":
                row[
                    "guidance_total_production"
                ],

            "total_production":
                row[
                    "total_production"
                ],

            "oil_production":
                row[
                    "oil_production"
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
    freq="Q"
)


# ============================================================
# 31. MERGE V2.1 NOWCAST
# ============================================================

v21_now = (
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
                "v21_revenue_yoy"
        }
    )
)


final_nowcast = structural_nowcast.merge(

    v21_now,

    on=[
        "ticker",
        "nowcast_quarter",
    ],

    how="inner"

)


# ============================================================
# 32. FINAL BLENDED NOWCAST
# ============================================================

predictions = []
weights_used = []


for _, row in (
    final_nowcast.iterrows()
):

    ticker = row[
        "ticker"
    ]


    weight = final_weights.get(
        ticker,
        0.50
    )


    # 실제 company production/guidance가
    # 이번 분기에 없다면 structural 비중 제한
    if (
        row[
            "has_company_prod"
        ]
        < 0.5
    ):

        weight = min(
            weight,
            NO_COMPANY_PROD_MAX_WEIGHT
        )


    prediction = (
        weight
        *
        row[
            "structural_revenue_yoy"
        ]

        +

        (
            1 - weight
        )
        *
        row[
            "v21_revenue_yoy"
        ]
    )


    prediction = np.clip(
        prediction,
        MIN_GROWTH,
        MAX_GROWTH
    )


    weights_used.append(
        weight
    )

    predictions.append(
        prediction
    )


final_nowcast[
    "structural_weight"
] = weights_used


final_nowcast[
    "v21_weight"
] = (
    1
    -
    final_nowcast[
        "structural_weight"
    ]
)


final_nowcast[
    "predicted_revenue_yoy"
] = predictions


# ============================================================
# 33. REVENUE LEVEL
# ============================================================

revenue_levels = []


for _, row in (
    final_nowcast.iterrows()
):

    ticker = row[
        "ticker"
    ]


    q = row[
        "nowcast_quarter"
    ]


    base_q = q - 4


    base = panel_v21[
        (
            panel_v21[
                "ticker"
            ]
            == ticker
        )

        &

        (
            panel_v21[
                "quarter"
            ]
            == base_q
        )
    ]


    if (
        base.empty
        or
        pd.isna(
            base.iloc[0][
                "revenue"
            ]
        )
    ):

        revenue_levels.append(
            np.nan
        )

        continue


    base_revenue = float(
        base.iloc[0][
            "revenue"
        ]
    )


    revenue = (
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


    revenue_levels.append(
        revenue
    )


final_nowcast[
    "predicted_revenue"
] = revenue_levels


final_nowcast[
    "predicted_revenue_B"
] = (
    final_nowcast[
        "predicted_revenue"
    ]
    /
    1e9
)


# ============================================================
# 34. MODEL DISPERSION / CONFIDENCE
# ============================================================

final_nowcast[
    "model_spread_pp"
] = (
    final_nowcast[
        "structural_revenue_yoy"
    ]
    -
    final_nowcast[
        "v21_revenue_yoy"
    ]
).abs()


def confidence_label(
    row
):

    spread = row[
        "model_spread_pp"
    ]


    has_prod = (
        row[
            "has_company_prod"
        ]
        >= 0.5
    )


    if (
        has_prod
        and
        spread <= 10
    ):

        return "HIGH"


    if (
        has_prod
        and
        spread <= 20
    ):

        return "MEDIUM"


    return "LOW"


final_nowcast[
    "confidence"
] = (
    final_nowcast.apply(
        confidence_label,
        axis=1
    )
)


# ============================================================
# 35. FINAL OUTPUT
# ============================================================

output_columns = [

    "ticker",
    "nowcast_quarter",

    "predicted_revenue_yoy",
    "predicted_revenue_B",

    "v21_revenue_yoy",
    "structural_revenue_yoy",

    "structural_weight",
    "v21_weight",

    "model_spread_pp",
    "confidence",

    "price_mix_yoy",
    "company_prod_yoy_proxy",

    "guidance_total_prod_yoy",
    "total_prod_yoy_l1",

    "guidance_total_production",

    "total_production",
    "oil_production",

    "has_company_prod",
    "has_guidance",

]


output = final_nowcast[
    output_columns
].copy()


print(
    "\n"
    + "=" * 90
)

print(
    "🚀 ENERGY REVENUE V3.2 BLENDED NOWCAST"
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
        "energy_v3_2_nowcast.csv"
    ),
    index=False
)


# ============================================================
# 36. SAVE METADATA
# ============================================================

metadata = {

    "version":
        "3.2",

    "as_of_date":
        str(
            AS_OF.date()
        ),

    "tickers":
        TICKERS,

    "blend_weight_grid":
        BLEND_WEIGHTS.tolist(),

    "no_company_prod_max_structural_weight":
        NO_COMPANY_PROD_MAX_WEIGHT,

    "model":
        (
            "ticker-specific blend of "
            "V2.1 macro/financial model "
            "and structural price x production model"
        ),

    "production_priority": [

        "current-quarter production guidance",

        "previous-quarter company production YoY",

        "EIA industry production fallback",

    ],

    "company_specific_parsers": {

        "COP":
            (
                "total-company Production for quarter "
                "prose + total company guidance"
            ),

        "EOG":
            (
                "quarterly oil/total volume prose "
                "+ dedicated guidance table parser"
            ),

        "FANG":
            (
                "MBO/d and MBOE/d earnings release parser"
            ),

        "DVN":
            (
                "Boe/day earnings release "
                "+ production guidance parser"
            ),

    },

}


with open(
    lake_path(
        "energy_v3_2_metadata.json"
    ),
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        metadata,
        f,
        indent=2,
        ensure_ascii=False
    )


# ============================================================
# 37. DONE
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

    "energy_v3_2_structural_panel.csv",

    "energy_v3_2_kpi_coverage.csv",

    "energy_v3_2_validation.csv",

    "energy_v3_2_metrics.csv",

    "energy_v3_2_blend_weights.csv",

    "energy_v3_2_nowcast.csv",

    "energy_v3_2_metadata.json",

]:

    print(
        " -",
        lake_path(
            filename
        )
    )


print(
    "\nCompany production files:"
)


for ticker in TICKERS:

    print(
        " -",
        lake_path(
            f"energy_v3_2_actual_{ticker}.csv"
        )
    )

    print(
        " -",
        lake_path(
            f"energy_v3_2_guidance_{ticker}.csv"
        )
    )