# ============================================================
# ENERGY REVENUE NOWCAST V3.2.1
#
# 개선사항
# ------------------------------------------------------------
# 1) Company-specific production extraction
#    COP / EOG / FANG / DVN
#
# 2) Guidance 존재 여부 버그 수정
#
#    has_guidance =
#        guidance_total_production.notna()
#
# 3) Guidance YoY 비교기준
#
#    same-quarter previous-year ACTUAL
#        ↓ 없으면
#    same-quarter previous-year GUIDANCE
#
# 4) Structural model performance guardrail
#
#    if Structural MAE >= V2.1 MAE:
#        Structural weight = 0
#
# 5) log YoY와 일반 YoY를 명확하게 분리
#
#    log growth:
#        ln(Current / Previous) * 100
#
#    일반적인 YoY:
#        (exp(log_growth / 100) - 1) * 100
#
# 6) EOG parser 추가 보강
#
# 7) Final model
#
#       Final Log Revenue YoY
#           =
#           w * Structural
#           +
#           (1-w) * V2.1
#
# 필요한 기존 파일
# ------------------------------------------------------------
# ./data-lake/energy_v2_1_panel.csv
# ./data-lake/energy_v2_1_validation.csv
# ./data-lake/energy_v2_1_nowcast.csv
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


# ------------------------------------------------------------
# Structural blend grid
# ------------------------------------------------------------

BLEND_WEIGHTS = np.round(
    np.arange(
        0.0,
        1.0001,
        0.05,
    ),
    2,
)


# ------------------------------------------------------------
# walk-forward에서 weight 추정하기 위한 최소 history
# ------------------------------------------------------------

MIN_BLEND_HISTORY = int(
    os.getenv(
        "MIN_BLEND_HISTORY",
        "3",
    )
)


# ------------------------------------------------------------
# 회사 production 정보가 없을 때
# structural weight 상한
# ------------------------------------------------------------

NO_COMPANY_PROD_MAX_WEIGHT = float(
    os.getenv(
        "NO_COMPANY_PROD_MAX_WEIGHT",
        "0.25",
    )
)


# ------------------------------------------------------------
# 안전장치
# ------------------------------------------------------------

MIN_LOG_GROWTH = -100.0
MAX_LOG_GROWTH = 150.0


# ============================================================
# 1. CONFIG CHECK
# ============================================================

if not EDGAR_IDENTITY:

    raise ValueError(
        "EDGAR_IDENTITY 환경변수를 설정해줘.\n"
        '예: export EDGAR_IDENTITY="Your Name you@example.com"'
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


def lake_path(filename):

    return (
        DATA_LAKE_DIR
        / filename
    )


print("=" * 90)
print("ENERGY REVENUE NOWCAST V3.2.1")
print("=" * 90)

print("AS OF      :", AS_OF.date())
print("TICKERS    :", TICKERS)
print("DATA LAKE  :", DATA_LAKE_DIR.resolve())
print("REFRESH KPI:", REFRESH_KPI)


# ============================================================
# 2. LOAD V2.1 RESULTS
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


# ------------------------------------------------------------
# V2.1 panel
# ------------------------------------------------------------

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
        ].isin(TICKERS)
    ]
    .copy()
)


# ------------------------------------------------------------
# V2.1 validation
# ------------------------------------------------------------

validation_v21 = pd.read_csv(
    VALIDATION_FILE
)


validation_v21["quarter"] = (
    pd.PeriodIndex(
        validation_v21[
            "quarter"
        ].astype(str),
        freq="Q",
    )
)


# ------------------------------------------------------------
# V2.1 current nowcast
# ------------------------------------------------------------

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
    "\nV2.1 panel     :",
    panel_v21.shape,
)

print(
    "V2.1 validation:",
    validation_v21.shape,
)

print(
    "V2.1 nowcast   :",
    nowcast_v21.shape,
)


# ============================================================
# 3. COMMON HELPERS
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

    try:

        value = float(text)

    except Exception:

        return np.nan

    if negative:

        value = -abs(value)

    return value


def find_numbers(text):

    tokens = re.findall(
        r"\(?-?\$?"
        r"\d[\d,]*"
        r"(?:\.\d+)?"
        r"\)?",
        normalize_text(text),
    )

    values = []

    for token in tokens:

        value = numeric(
            token
        )

        if pd.isna(value):

            continue

        # calendar year 제거
        if 1990 <= value <= 2100:

            continue

        values.append(value)

    return values


# ============================================================
# 4. GROWTH FUNCTIONS
# ============================================================

def log_growth(
    series,
    periods=4,
):

    series = pd.to_numeric(
        series,
        errors="coerce",
    )

    lagged = series.shift(
        periods
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

    output.loc[valid] = (
        np.log(
            series.loc[valid]
            /
            lagged.loc[valid]
        )
        * 100
    )

    return output


def log_to_normal_pct(
    log_growth_value,
):

    """
    log YoY를 우리가 평소 말하는
    일반적인 % YoY로 변환.

    ex)
      log growth 70
      -> arithmetic growth 약 101.4%
    """

    if isinstance(
        log_growth_value,
        pd.Series,
    ):

        return (
            np.exp(
                log_growth_value
                / 100
            )
            - 1
        ) * 100

    if pd.isna(
        log_growth_value
    ):

        return np.nan

    return (
        np.exp(
            log_growth_value
            / 100
        )
        - 1
    ) * 100


# ============================================================
# 5. QUARTER HELPERS
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


    # --------------------------------------------------------
    # second quarter 2026
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # quarter ended June 30, 2026
    # --------------------------------------------------------

    match = re.search(
        r"quarter\s+ended\s+"
        r"(january|february|march|"
        r"april|may|june|"
        r"july|august|september|"
        r"october|november|december)"
        r"\s+\d{1,2},?\s+"
        r"(20\d{2})",
        lower,
    )

    if match:

        month = MONTH_MAP[
            match.group(1)
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


    # --------------------------------------------------------
    # fallback from filing date
    # --------------------------------------------------------

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


# ============================================================
# 6. UNIT CONVERSION
# ============================================================

def total_to_mboed(
    value,
    unit,
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


    # raw BOE per day
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

            return value / 1000


    return value


def oil_to_mbod(
    value,
    unit,
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

def valid_total(value):

    return (
        pd.notna(value)
        and
        20 <= value <= 5000
    )


def valid_oil(value):

    return (
        pd.notna(value)
        and
        5 <= value <= 3000
    )


# ============================================================
# 8. ATTACHMENT DOWNLOAD
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


    tables = []

    try:

        tables = pd.read_html(
            StringIO(raw)
        )

    except Exception:

        pass


    return (
        text,
        tables,
    )


# ============================================================
# 9. RECORD HELPERS
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
    source,
):

    actuals = []
    guidance = []


    quarter = infer_result_quarter(
        filing_date,
        text,
    )


    # ========================================================
    # ACTUAL
    #
    # "Production for the second quarter of 2026
    #  was 2,248 MBOED"
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
            r"total\s+company\s+production"
            r".{0,80}?"
            r"(?:was|of|averaged)\s+"
            r"(?P<value>[\d,.]+)"
            r"\s*"
            r"(?P<unit>"
            r"MBOED|MBOE/D|"
            r"boe\s+per\s+day"
            r")"
        ),

    ]


    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.I,
        )

        if not match:

            continue

        value = total_to_mboed(
            match.group("value"),
            match.group("unit"),
        )

        if valid_total(value):

            actuals.append(
                actual_record(
                    "COP",
                    quarter,
                    filing_date,
                    total=value,
                    score=150,
                    source=source,
                    raw_text=match.group(0),
                )
            )

            break


    # ========================================================
    # GUIDANCE
    # ========================================================

    pattern = (
        r"(?P<qword>"
        r"first|second|third|fourth"
        r")"
        r"[-\s]quarter"
        r"(?:\s+(?P<year>20\d{2}))?"
        r"\s+production"
        r".{0,120}?"
        r"(?:expected|forecast|guidance)"
        r".{0,140}?"
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
        flags=re.I,
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

            year = quarter.year

            target_q_num = (
                QUARTER_WORD[
                    qword.lower()
                ]
            )

            if target_q_num < quarter.quarter:

                year += 1


        target_q = quarter_from_word(
            qword,
            year,
        )


        low = total_to_mboed(
            match.group("low"),
            match.group("unit"),
        )

        high = total_to_mboed(
            match.group("high"),
            match.group("unit"),
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
                    score=150,
                    source=source,
                    raw_text=match.group(0),
                )
            )


    return (
        actuals,
        guidance,
    )


# ============================================================
# 11. EOG PARSER - V3.2.1 강화
# ============================================================

def choose_midpoint(
    values,
    low_limit,
    high_limit,
):

    values = [
        x
        for x in values
        if (
            pd.notna(x)
            and
            low_limit <= x <= high_limit
        )
    ]


    if not values:

        return np.nan


    # low/high/midpoint 구조
    if len(values) >= 3:

        a = values[0]
        b = values[1]
        c = values[2]

        calculated = (
            a + b
        ) / 2

        # 세 번째 값이 midpoint와 비슷하면 그 값 사용
        if abs(
            c - calculated
        ) <= max(
            5,
            0.03 * calculated,
        ):

            return c


    if len(values) >= 2:

        return (
            values[0]
            +
            values[1]
        ) / 2


    return values[0]


def parse_eog(
    text,
    tables,
    filing_date,
    source,
):

    actuals = []
    guidance = []


    quarter = infer_result_quarter(
        filing_date,
        text,
    )


    # ========================================================
    # ACTUAL PROSE
    # ========================================================

    actual_patterns = [

        (
            r"quarterly\s+oil\s+volumes\s+of\s+"
            r"(?P<oil>[\d,.]+)"
            r"\s*MBod"
            r".{0,200}?"
            r"total\s+volumes\s+of\s+"
            r"(?P<total>[\d,.]+)"
            r"\s*MBoed"
        ),

        (
            r"total\s+volumes\s+of\s+"
            r"(?P<total>[\d,.]+)"
            r"\s*MBoed"
        ),

        (
            r"total\s+crude\s+oil\s+equivalent"
            r".{0,100}?"
            r"(?P<total>[\d,.]+)"
            r"\s*MBoed"
        ),

    ]


    for pattern in actual_patterns:

        match = re.search(
            pattern,
            text,
            flags=re.I,
        )

        if not match:

            continue


        total = numeric(
            match.groupdict().get(
                "total"
            )
        )

        oil = numeric(
            match.groupdict().get(
                "oil"
            )
        )


        if (
            valid_total(total)
            or
            valid_oil(oil)
        ):

            actuals.append(
                actual_record(
                    "EOG",
                    quarter,
                    filing_date,
                    total=total,
                    oil=oil,
                    score=160,
                    source=source,
                    raw_text=match.group(0),
                )
            )

            break


    # ========================================================
    # EOG TABLE ACTUAL / GUIDANCE
    # ========================================================

    guidance_total = np.nan
    guidance_oil = np.nan

    actual_total_table = np.nan
    actual_oil_table = np.nan


    for table in tables:

        try:

            table_clean = (
                table
                .copy()
                .fillna("")
            )

        except Exception:

            continue


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


        is_guidance = (
            "guidance"
            in lower_table
        )


        # ----------------------------------------------------
        # row scanning
        # ----------------------------------------------------

        section = None


        for _, row in (
            table_clean.iterrows()
        ):

            row_text = normalize_text(
                " | ".join(
                    str(x)
                    for x in row.tolist()
                )
            )

            lower = row_text.lower()


            if (
                "crude oil and condensate"
                in lower
                and
                (
                    "mbod"
                    in lower
                    or
                    "volume"
                    in lower
                )
            ):

                section = "oil"

                # 같은 행에 값이 있을 수도 있음
                nums = find_numbers(
                    row_text
                )

                if (
                    not is_guidance
                    and nums
                ):

                    candidate_value = (
                        choose_midpoint(
                            nums,
                            50,
                            2000,
                        )
                    )

                    if valid_oil(
                        candidate_value
                    ):

                        actual_oil_table = (
                            candidate_value
                        )

                continue


            if (
                "crude oil equivalent"
                in lower
                and
                (
                    "mboe"
                    in lower
                    or
                    "volume"
                    in lower
                )
            ):

                section = "total"

                nums = find_numbers(
                    row_text
                )

                if (
                    not is_guidance
                    and nums
                ):

                    candidate_value = (
                        choose_midpoint(
                            nums,
                            300,
                            3000,
                        )
                    )

                    if valid_total(
                        candidate_value
                    ):

                        actual_total_table = (
                            candidate_value
                        )

                continue


            # ------------------------------------------------
            # Total row
            # ------------------------------------------------

            if (
                section
                and
                re.search(
                    r"(?:^|\|)\s*total\s*(?:\||$)",
                    lower,
                )
            ):

                nums = find_numbers(
                    row_text
                )


                if section == "oil":

                    value = choose_midpoint(
                        nums,
                        50,
                        2000,
                    )

                    if is_guidance:

                        if valid_oil(value):

                            guidance_oil = value

                    else:

                        if valid_oil(value):

                            actual_oil_table = value


                elif section == "total":

                    value = choose_midpoint(
                        nums,
                        300,
                        3000,
                    )

                    if is_guidance:

                        if valid_total(value):

                            guidance_total = value

                    else:

                        if valid_total(value):

                            actual_total_table = value


        # ----------------------------------------------------
        # EOG guidance text-context fallback
        # ----------------------------------------------------

        if is_guidance:

            total_context_match = re.search(
                r"(?:total\s+)?"
                r"crude\s+oil\s+equivalent\s+"
                r"volumes?"
                r".{0,600}",
                table_text,
                flags=re.I,
            )

            if total_context_match:

                nums = find_numbers(
                    total_context_match.group(0)
                )

                value = choose_midpoint(
                    nums,
                    300,
                    3000,
                )

                if valid_total(value):

                    guidance_total = (
                        value
                    )


    # --------------------------------------------------------
    # actual table fallback
    # --------------------------------------------------------

    if (
        not actuals
        and
        (
            valid_total(
                actual_total_table
            )
            or
            valid_oil(
                actual_oil_table
            )
        )
    ):

        actuals.append(
            actual_record(
                "EOG",
                quarter,
                filing_date,
                total=actual_total_table,
                oil=actual_oil_table,
                score=130,
                source=source,
                raw_text=(
                    "EOG dedicated actual table parser"
                ),
            )
        )


    # ========================================================
    # GUIDANCE TARGET QUARTER
    #
    # EOG earnings release에서 explicit quarter를 못 찾으면
    # 다음 분기로 판단
    # ========================================================

    target_q = (
        quarter + 1
    )


    # text에서 명시적으로 확인
    match = re.search(
        r"(first|second|third|fourth)"
        r"\s+quarter"
        r"(?:\s+of)?"
        r"\s+(20\d{2})"
        r".{0,50}?"
        r"guidance",
        text,
        flags=re.I,
    )

    if match:

        target_q = (
            quarter_from_word(
                match.group(1),
                match.group(2),
            )
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
                score=160,
                source=source,
                raw_text=(
                    "EOG dedicated guidance table parser"
                ),
            )
        )


    return (
        actuals,
        guidance,
    )


# ============================================================
# 12. FANG PARSER
# ============================================================

def parse_fang(
    text,
    tables,
    filing_date,
    source,
):

    actuals = []
    guidance = []


    quarter = infer_result_quarter(
        filing_date,
        text,
    )


    # --------------------------------------------------------
    # actual
    # --------------------------------------------------------

    patterns = [

        (
            r"(?:average\s+)?"
            r"oil\s+production"
            r".{0,50}?"
            r"(?P<oil>[\d,.]+)"
            r"\s*MBO/D"
            r".{0,180}?"
            r"(?P<total>[\d,.]+)"
            r"\s*MBOE/D"
        ),

        (
            r"(?P<oil>[\d,.]+)"
            r"\s*MBO/D"
            r".{0,160}?"
            r"(?P<total>[\d,.]+)"
            r"\s*MBOE/D"
        ),

    ]


    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.I,
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
                    score=150,
                    source=source,
                    raw_text=match.group(0),
                )
            )

            break


    # --------------------------------------------------------
    # guidance
    # --------------------------------------------------------

    pattern = (
        r"Q(?P<q>[1-4])\s*"
        r"(?P<year>20\d{2})"
        r".{0,220}?"
        r"oil\s+production"
        r".{0,200}?"
        r"(?P<oil_low>[\d,.]+)"
        r"\s*-\s*"
        r"(?P<oil_high>[\d,.]+)"
        r".{0,120}?"
        r"(?P<total_low>[\d,.]+)"
        r"\s*-\s*"
        r"(?P<total_high>[\d,.]+)"
    )


    match = re.search(
        pattern,
        text,
        flags=re.I,
    )


    if match:

        target_q = pd.Period(
            (
                f"{match.group('year')}"
                f"Q{match.group('q')}"
            ),
            freq="Q",
        )


        oil_mid = (
            numeric(
                match.group("oil_low")
            )
            +
            numeric(
                match.group("oil_high")
            )
        ) / 2


        total_mid = (
            numeric(
                match.group("total_low")
            )
            +
            numeric(
                match.group("total_high")
            )
        ) / 2


        if (
            valid_oil(
                oil_mid
            )
            and
            valid_total(
                total_mid
            )
        ):

            guidance.append(
                guidance_record(
                    "FANG",
                    target_q,
                    filing_date,
                    total=total_mid,
                    oil=oil_mid,
                    score=150,
                    source=source,
                    raw_text=match.group(0),
                )
            )


    return (
        actuals,
        guidance,
    )


# ============================================================
# 13. DVN PARSER
# ============================================================

def parse_dvn(
    text,
    tables,
    filing_date,
    source,
):

    actuals = []
    guidance = []


    quarter = infer_result_quarter(
        filing_date,
        text,
    )


    # --------------------------------------------------------
    # actual total
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # actual oil
    # --------------------------------------------------------

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
            total_match.group("value"),
            total_match.group("unit"),
        )


    if oil_match:

        oil = oil_to_mbod(
            oil_match.group("value"),
            oil_match.group("unit"),
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
                score=150,
                source=source,
                raw_text=(
                    f"{total_match.group(0) if total_match else ''} "
                    f"{oil_match.group(0) if oil_match else ''}"
                ),
            )
        )


    # --------------------------------------------------------
    # guidance
    # --------------------------------------------------------

    pattern = (
        r"(?:in|for)\s+the\s+"
        r"(?P<qword>"
        r"first|second|third|fourth"
        r")"
        r"\s+quarter"
        r"(?:\s+of)?\s+"
        r"(?P<year>20\d{2})"
        r".{0,300}?"
        r"(?:total\s+)?production"
        r".{0,150}?"
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
        flags=re.I,
    )


    if match:

        target_q = quarter_from_word(
            match.group("qword"),
            match.group("year"),
        )


        low = total_to_mboed(
            match.group("low"),
            match.group("unit"),
        )

        high = total_to_mboed(
            match.group("high"),
            match.group("unit"),
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
                    score=150,
                    source=source,
                    raw_text=match.group(0),
                )
            )


    return (
        actuals,
        guidance,
    )


# ============================================================
# 14. ROUTER
# ============================================================

def parse_company(
    ticker,
    text,
    tables,
    filing_date,
    source,
):

    if ticker == "COP":

        return parse_cop(
            text,
            tables,
            filing_date,
            source,
        )

    if ticker == "EOG":

        return parse_eog(
            text,
            tables,
            filing_date,
            source,
        )

    if ticker == "FANG":

        return parse_fang(
            text,
            tables,
            filing_date,
            source,
        )

    if ticker == "DVN":

        return parse_dvn(
            text,
            tables,
            filing_date,
            source,
        )

    return (
        [],
        [],
    )


# ============================================================
# 15. SEC SCANNER
# ============================================================

def scan_company(
    ticker,
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
            >= EARNINGS_LOOKBACK_FILINGS
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


        if filing_date > AS_OF:

            continue


        exhibits = []


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


                if doc_type.startswith(
                    "EX-99"
                ):

                    exhibits.append(
                        exhibit
                    )

        except Exception:

            pass


        if not exhibits:

            continue


        filing_used = False


        for exhibit in exhibits:

            text, tables = (
                download_attachment(
                    exhibit
                )
            )


            if not text:

                continue


            if (
                "production"
                not in text.lower()
                and
                "volume"
                not in text.lower()
            ):

                continue


            source = (
                f"{filing_date.date()}:"
                f"{getattr(exhibit, 'document_type', '')}:"
                f"{getattr(exhibit, 'document', '')}"
            )


            actuals, guidance = (
                parse_company(
                    ticker,
                    text,
                    tables,
                    filing_date,
                    source,
                )
            )


            if (
                actuals
                or
                guidance
            ):

                filing_used = True


            actual_records.extend(
                actuals
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


    actual_df.to_csv(
        lake_path(
            (
                f"energy_v3_2_1_"
                f"actual_candidates_{ticker}.csv"
            )
        ),
        index=False,
    )


    guidance_df.to_csv(
        lake_path(
            (
                f"energy_v3_2_1_"
                f"guidance_candidates_{ticker}.csv"
            )
        ),
        index=False,
    )


    print(
        "  candidate actuals :",
        len(actual_df),
    )

    print(
        "  candidate guidance:",
        len(guidance_df),
    )


    return (
        actual_df,
        guidance_df,
    )


# ============================================================
# 16. SELECT BEST ACTUAL
# ============================================================

def select_actuals(
    ticker,
    candidates,
):

    if candidates.empty:

        return pd.DataFrame()


    work = candidates.copy()


    work["quarter"] = pd.PeriodIndex(
        work["quarter"].astype(str),
        freq="Q",
    )


    work["filing_date"] = pd.to_datetime(
        work["filing_date"],
        errors="coerce",
    )


    selected = []


    for quarter, group in (
        work.groupby(
            "quarter"
        )
    ):

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


    selected_df.to_csv(
        lake_path(
            (
                f"energy_v3_2_1_"
                f"actual_selected_{ticker}.csv"
            )
        ),
        index=False,
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
        .sort_index()
    )


    output.index = (
        pd.PeriodIndex(
            output.index,
            freq="Q",
        )
    )


    return output


# ============================================================
# 17. SELECT BEST GUIDANCE
# ============================================================

def select_guidance(
    ticker,
    candidates,
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
        freq="Q",
    )


    work["filing_date"] = (
        pd.to_datetime(
            work["filing_date"],
            errors="coerce",
        )
    )


    selected = []


    for quarter, group in (
        work.groupby(
            "target_quarter"
        )
    ):

        valid = group[
            group[
                "filing_date"
            ]
            <= quarter.end_time
        ]


        if valid.empty:

            continue


        best = (
            valid
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


    if not selected:

        return pd.DataFrame()


    selected_df = pd.DataFrame(
        selected
    )


    selected_df.to_csv(
        lake_path(
            (
                f"energy_v3_2_1_"
                f"guidance_selected_{ticker}.csv"
            )
        ),
        index=False,
    )


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
        .sort_index()
    )


    output.index = (
        pd.PeriodIndex(
            output.index,
            freq="Q",
        )
    )


    return output


# ============================================================
# 18. CACHE
# ============================================================

def load_or_build_company_kpi(
    ticker,
):

    actual_cache = lake_path(
        f"energy_v3_2_1_actual_{ticker}.csv"
    )


    guidance_cache = lake_path(
        f"energy_v3_2_1_guidance_{ticker}.csv"
    )


    if (
        actual_cache.exists()
        and
        guidance_cache.exists()
        and
        not REFRESH_KPI
    ):

        print(
            f"\nLoading cached V3.2.1 KPI: {ticker}"
        )


        actual = pd.read_csv(
            actual_cache,
            index_col=0,
        )

        actual.index = pd.PeriodIndex(
            actual.index.astype(str),
            freq="Q",
        )


        guidance = pd.read_csv(
            guidance_cache,
            index_col=0,
        )

        guidance.index = pd.PeriodIndex(
            guidance.index.astype(str),
            freq="Q",
        )


        return (
            actual,
            guidance,
        )


    actual_candidates, guidance_candidates = (
        scan_company(
            ticker
        )
    )


    actual = select_actuals(
        ticker,
        actual_candidates,
    )


    guidance = select_guidance(
        ticker,
        guidance_candidates,
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
# 19. LOAD KPI
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
            f"\n❌ {ticker} KPI ERROR: "
            f"{repr(exc)}"
        )

        actual_kpis[
            ticker
        ] = pd.DataFrame()

        guidance_kpis[
            ticker
        ] = pd.DataFrame()


# ============================================================
# 20. KPI COVERAGE
# ============================================================

print(
    "\n"
    + "=" * 90
)

print(
    "V3.2.1 KPI COVERAGE"
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


    total_actual = (
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


    oil_actual = (
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


    total_guidance = (
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
        "  actual total production  :",
        total_actual,
    )

    print(
        "  actual oil production    :",
        oil_actual,
    )

    print(
        "  total production guidance:",
        total_guidance,
    )


    coverage_rows.append(
        {
            "ticker":
                ticker,

            "actual_total":
                total_actual,

            "actual_oil":
                oil_actual,

            "guidance_total":
                total_guidance,
        }
    )


pd.DataFrame(
    coverage_rows
).to_csv(
    lake_path(
        "energy_v3_2_1_kpi_coverage.csv"
    ),
    index=False,
)


# ============================================================
# 21. STRUCTURAL MODEL
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
    guidance,
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
        freq="Q",
    )


    # ========================================================
    # Actual production
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
    # Guidance
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
    # Actual production YoY
    # ========================================================

    df[
        "total_prod_yoy"
    ] = log_growth(
        df[
            "total_production"
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
    # FIX #1
    #
    # Guidance YoY comparison base
    #
    # 전년 actual 우선
    # → 없으면 전년 guidance
    # ========================================================

    prior_year_actual = (
        df[
            "total_production"
        ]
        .shift(4)
    )


    prior_year_guidance = (
        df[
            "guidance_total_production"
        ]
        .shift(4)
    )


    prior_year_base = (
        prior_year_actual
        .combine_first(
            prior_year_guidance
        )
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
            prior_year_base
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
            prior_year_base.loc[
                valid
            ]
        )
        * 100
    )


    # ========================================================
    # FIX #2
    #
    # has_guidance는 성장률 계산 성공 여부가 아니라
    # 실제 guidance 숫자가 존재하는지로 판단
    # ========================================================

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
    # Industry fallback
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
    # Company production proxy
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
    ).astype(float)


    # ========================================================
    # Oil share
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
                0.75,
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
    # Structural Revenue LOG YoY
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


    # 일반 % YoY
    df[
        "structural_revenue_yoy_pct"
    ] = log_to_normal_pct(
        df[
            "structural_revenue_log_yoy"
        ]
    )


    df.index = np.arange(
        len(df)
    )


    return df


# ============================================================
# 22. BUILD STRUCTURAL PANEL
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


    result = (
        build_structural_company(
            ticker,
            company_panel,
            actual_kpis[
                ticker
            ],
            guidance_kpis[
                ticker
            ],
        )
    )


    frames.append(
        result
    )


structural_panel = pd.concat(
    frames,
    ignore_index=True,
)


structural_panel[
    "quarter"
] = pd.PeriodIndex(
    structural_panel[
        "quarter"
    ].astype(str),
    freq="Q",
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
        "energy_v3_2_1_structural_panel.csv"
    ),
    index=False,
)


# ============================================================
# 23. STRUCTURAL VALIDATION FRAME
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

            "price_mix_yoy",

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
# 24. ALIGN V2.1 VALIDATION
# ============================================================

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
            "predicted":
                "v21_log_yoy"
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
        suffixes=(
            "_v21",
            "_struct",
        ),
    )
)


# merge 후 actual 중복 처리
if (
    "actual_v21"
    in compare.columns
):

    compare[
        "actual"
    ] = (
        compare[
            "actual_v21"
        ]
    )

elif (
    "actual"
    not in compare.columns
):

    compare[
        "actual"
    ] = (
        compare[
            "actual_struct"
        ]
    )


# ============================================================
# 25. MAE
# ============================================================

def mae(
    actual,
    prediction,
):

    actual = np.asarray(
        actual,
        dtype=float,
    )

    prediction = np.asarray(
        prediction,
        dtype=float,
    )

    return float(
        np.mean(
            np.abs(
                actual
                -
                prediction
            )
        )
    )


# ============================================================
# 26. BEST BLEND WEIGHT
# ============================================================

def best_weight(
    history,
):

    if history.empty:

        return 0.0


    best_w = 0.0
    best_score = np.inf


    for w in (
        BLEND_WEIGHTS
    ):

        prediction = (
            w
            *
            history[
                "structural_revenue_log_yoy"
            ]

            +

            (
                1.0 - w
            )
            *
            history[
                "v21_log_yoy"
            ]
        )


        score = mae(
            history[
                "actual"
            ],
            prediction,
        )


        if score < best_score:

            best_score = score
            best_w = float(w)


    return best_w


# ============================================================
# 27. PERFORMANCE GUARDRAIL
# ============================================================

def guarded_weight(
    history,
):

    """
    V3.2.1 핵심.

    Structural 단독 모델이 V2.1보다
    역사적으로 나쁘면 structural weight = 0.

    즉 나쁜 모델을 억지로 blend하지 않음.
    """

    if history.empty:

        return 0.0


    structural_mae = mae(
        history[
            "actual"
        ],
        history[
            "structural_revenue_log_yoy"
        ],
    )


    v21_mae = mae(
        history[
            "actual"
        ],
        history[
            "v21_log_yoy"
        ],
    )


    if (
        structural_mae
        >=
        v21_mae
    ):

        return 0.0


    return best_weight(
        history
    )


# ============================================================
# 28. WALK-FORWARD BLEND
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

            weight = 0.0

        else:

            weight = guarded_weight(
                history
            )


        # ----------------------------------------------------
        # 현재 분기에 실제 company production 정보 없으면
        # structural weight 제한
        # ----------------------------------------------------

        if (
            row[
                "has_company_prod"
            ]
            < 0.5
        ):

            weight = min(
                weight,
                NO_COMPANY_PROD_MAX_WEIGHT,
            )


        prediction = (
            weight
            *
            row[
                "structural_revenue_log_yoy"
            ]

            +

            (
                1.0 - weight
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
                        "actual"
                    ],

                "actual_yoy_pct":
                    log_to_normal_pct(
                        row[
                            "actual"
                        ]
                    ),

                "v21_log_yoy":
                    row[
                        "v21_log_yoy"
                    ],

                "structural_log_yoy":
                    row[
                        "structural_revenue_log_yoy"
                    ],

                "structural_weight":
                    weight,

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
            }
        )


walk_validation = pd.DataFrame(
    walk_rows
)


# ============================================================
# 29. VALIDATION METRICS
# ============================================================

metric_rows = []


print(
    "\n"
    + "=" * 90
)

print(
    "V3.2.1 WALK-FORWARD VALIDATION"
)

print(
    "=" * 90
)


for ticker, group in (
    walk_validation.groupby(
        "ticker"
    )
):

    v21_error = mae(
        group[
            "actual_log_yoy"
        ],
        group[
            "v21_log_yoy"
        ],
    )


    structural_error = mae(
        group[
            "actual_log_yoy"
        ],
        group[
            "structural_log_yoy"
        ],
    )


    blend_error = mae(
        group[
            "actual_log_yoy"
        ],
        group[
            "blend_log_yoy"
        ],
    )


    metric_rows.append(
        {
            "ticker":
                ticker,

            "V2_1_MAE":
                v21_error,

            "Structural_MAE":
                structural_error,

            "V3_2_1_Blend_MAE":
                blend_error,

            "vs_V2_1_improvement_pct":
                (
                    (
                        v21_error
                        -
                        blend_error
                    )
                    /
                    v21_error
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
    walk_validation[
        "actual_log_yoy"
    ],
    walk_validation[
        "v21_log_yoy"
    ],
)


overall_structural = mae(
    walk_validation[
        "actual_log_yoy"
    ],
    walk_validation[
        "structural_log_yoy"
    ],
)


overall_blend = mae(
    walk_validation[
        "actual_log_yoy"
    ],
    walk_validation[
        "blend_log_yoy"
    ],
)


print(
    f"\nOverall V2.1 MAE       : "
    f"{overall_v21:.2f} pp"
)

print(
    f"Overall Structural MAE : "
    f"{overall_structural:.2f} pp"
)

print(
    f"Overall V3.2.1 MAE     : "
    f"{overall_blend:.2f} pp"
)


print(
    "\n===== BY TICKER ====="
)

print(
    metrics.round(2)
)


print(
    "\n===== LAST VALIDATION ROWS ====="
)

print(
    walk_validation
    .tail(20)
    .round(2)
    .to_string(
        index=False
    )
)


walk_validation.to_csv(
    lake_path(
        "energy_v3_2_1_validation.csv"
    ),
    index=False,
)


metrics.to_csv(
    lake_path(
        "energy_v3_2_1_metrics.csv"
    )
)


# ============================================================
# 30. FINAL COMPANY WEIGHTS
# ============================================================

weight_rows = []
final_weights = {}


for ticker, group in (
    compare.groupby(
        "ticker"
    )
):

    structural_error = mae(
        group[
            "actual"
        ],
        group[
            "structural_revenue_log_yoy"
        ],
    )


    v21_error = mae(
        group[
            "actual"
        ],
        group[
            "v21_log_yoy"
        ],
    )


    # ========================================================
    # FIX #3
    #
    # Structural이 더 나쁘면 weight = 0
    # ========================================================

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
                1.0 - weight,

            "historical_structural_mae":
                structural_error,

            "historical_v21_mae":
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
    "\n===== FINAL COMPANY WEIGHTS ====="
)

print(
    weights_df.round(3)
)


weights_df.to_csv(
    lake_path(
        "energy_v3_2_1_blend_weights.csv"
    )
)


# ============================================================
# 31. BUILD STRUCTURAL CURRENT NOWCAST
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


    target_q = (
        last_actual_q
        + 1
    )


    current = (
        company[
            company[
                "quarter"
            ]
            == target_q
        ]
    )


    if current.empty:

        continue


    row = current.iloc[
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
    freq="Q",
)


# ============================================================
# 32. MERGE V2.1 NOWCAST
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
# 33. FINAL BLENDED NOWCAST
# ============================================================

blend_log_predictions = []
weights_used = []


for _, row in (
    current.iterrows()
):

    ticker = row[
        "ticker"
    ]


    weight = final_weights.get(
        ticker,
        0.0,
    )


    # --------------------------------------------------------
    # 회사 actual/guidance를 못 쓰는 structural이면
    # 최대 25%
    # --------------------------------------------------------

    if (
        row[
            "has_company_prod"
        ]
        < 0.5
    ):

        weight = min(
            weight,
            NO_COMPANY_PROD_MAX_WEIGHT,
        )


    prediction = (
        weight
        *
        row[
            "structural_log_yoy"
        ]

        +

        (
            1.0 - weight
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


    weights_used.append(
        weight
    )

    blend_log_predictions.append(
        prediction
    )


current[
    "structural_weight"
] = weights_used


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
# FIX #4
#
# 명칭 명확화
# ============================================================

current[
    "predicted_revenue_log_yoy"
] = (
    blend_log_predictions
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


current[
    "structural_yoy_pct"
] = (
    log_to_normal_pct(
        current[
            "structural_log_yoy"
        ]
    )
)


# ============================================================
# 34. REVENUE LEVEL
# ============================================================

revenue_levels = []


for _, row in (
    current.iterrows()
):

    ticker = row[
        "ticker"
    ]

    q = row[
        "nowcast_quarter"
    ]

    base_q = (
        q - 4
    )


    base = (
        panel_v21[
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

        revenue_levels.append(
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
                "predicted_revenue_log_yoy"
            ]
            / 100
        )
    )


    revenue_levels.append(
        predicted
    )


current[
    "predicted_revenue"
] = revenue_levels


current[
    "predicted_revenue_B"
] = (
    current[
        "predicted_revenue"
    ]
    / 1e9
)


# ============================================================
# 35. MODEL DISPERSION
# ============================================================

current[
    "model_spread_pp"
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
    row
):

    spread = row[
        "model_spread_pp"
    ]

    company_data = (
        row[
            "has_company_prod"
        ]
        >= 0.5
    )


    if (
        company_data
        and
        spread <= 10
    ):

        return "HIGH"


    if (
        company_data
        and
        spread <= 20
    ):

        return "MEDIUM"


    return "LOW"


current[
    "confidence"
] = (
    current.apply(
        confidence,
        axis=1,
    )
)


# ============================================================
# 36. FINAL OUTPUT
# ============================================================

output_columns = [

    "ticker",

    "nowcast_quarter",

    # 최종 결과
    "predicted_revenue_B",

    "predicted_revenue_log_yoy",

    "predicted_revenue_yoy_pct",


    # individual models
    "v21_log_yoy",

    "v21_yoy_pct",

    "structural_log_yoy",

    "structural_yoy_pct",


    # blend
    "structural_weight",

    "v21_weight",

    "model_spread_pp",

    "confidence",


    # structural detail
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
    "🚀 ENERGY REVENUE V3.2.1 NOWCAST"
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
        "energy_v3_2_1_nowcast.csv"
    ),
    index=False,
)


# ============================================================
# 37. SAVE MODEL COMPARISON
# ============================================================

comparison = (
    output[
        [
            "ticker",

            "predicted_revenue_B",

            "predicted_revenue_yoy_pct",

            "v21_yoy_pct",

            "structural_yoy_pct",

            "structural_weight",

            "model_spread_pp",

            "confidence",
        ]
    ]
    .copy()
)


comparison.to_csv(
    lake_path(
        "energy_v3_2_1_model_comparison.csv"
    ),
    index=False,
)


# ============================================================
# 38. METADATA
# ============================================================

metadata = {

    "version":
        "3.2.1",

    "as_of_date":
        str(
            AS_OF.date()
        ),

    "tickers":
        TICKERS,

    "changes": [

        (
            "has_guidance now uses existence of "
            "guidance_total_production"
        ),

        (
            "guidance YoY denominator falls back "
            "from prior-year actual production "
            "to prior-year guidance"
        ),

        (
            "structural model is disabled if "
            "historical structural MAE >= V2.1 MAE"
        ),

        (
            "log YoY and arithmetic YoY are "
            "reported separately"
        ),

        (
            "EOG earnings/guidance extraction "
            "has additional prose and table fallbacks"
        ),

    ],

    "blend_weights_grid":
        BLEND_WEIGHTS.tolist(),

    "no_company_prod_max_weight":
        NO_COMPANY_PROD_MAX_WEIGHT,

}


with open(
    lake_path(
        "energy_v3_2_1_metadata.json"
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
# 39. DONE
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

    "energy_v3_2_1_structural_panel.csv",

    "energy_v3_2_1_kpi_coverage.csv",

    "energy_v3_2_1_validation.csv",

    "energy_v3_2_1_metrics.csv",

    "energy_v3_2_1_blend_weights.csv",

    "energy_v3_2_1_nowcast.csv",

    "energy_v3_2_1_model_comparison.csv",

    "energy_v3_2_1_metadata.json",

]:

    print(
        " -",
        lake_path(
            filename
        )
    )


print(
    "\nCompany production cache:"
)


for ticker in TICKERS:

    print(
        " -",
        lake_path(
            f"energy_v3_2_1_actual_{ticker}.csv"
        )
    )

    print(
        " -",
        lake_path(
            f"energy_v3_2_1_guidance_{ticker}.csv"
        )
    )