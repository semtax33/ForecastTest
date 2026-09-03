# ============================================================
# ENERGY REVENUE NOWCAST V3.2.7
# ============================================================
#
# V3.2.7 핵심
# ------------------------------------------------------------
#
# EOG:
#
#   Statistics XLS actual 추출 제거
#
#   Official EOG Earnings Press Release HTML
#       ↓
#   Key Operational Results
#       ↓
#   Oil / NGL / Gas / Total
#
#
# 같은 Press Release 안의
# Next Quarter Guidance도 직접 파싱
#
#
# ACTUAL
# ------------------------------------------------------------
#
# Crude Oil and Condensate (MBod)
# Natural Gas Liquids (MBbld)
# Natural Gas (MMcfd)
# Total Crude Oil Equivalent (MBoed)
#
#
# GUIDANCE
# ------------------------------------------------------------
#
# Crude Oil and Condensate Volumes (MBod)
# Natural Gas Liquids Volumes (MBbld)
# Natural Gas Volumes (MMcfd)
# Crude Oil Equivalent Volumes (MBoed)
#
#
# BOE RECONSTRUCTION
# ------------------------------------------------------------
#
# Total MBoed
# =
# Oil MBod
# + NGL MBbld
# + Gas MMcfd / 6
#
#
# EOG만 V3.2.3 structural panel에서 교체
#
# COP/FANG/DVN은
# 기존 V3.2.3 structural 결과 유지
#
#
# Final
# ------------------------------------------------------------
#
# Final Log Revenue YoY
# =
# Structural weight * Structural
# +
# V2.1 weight * V2.1
#
#
# Metrics
# ------------------------------------------------------------
#
# 1. MAE log-points
# 2. Revenue YoY MAE %p
#
#
# REQUIRED
# ------------------------------------------------------------
#
# ./data-lake/energy_v2_1_panel.csv
# ./data-lake/energy_v2_1_validation.csv
# ./data-lake/energy_v2_1_nowcast.csv
#
# preferred:
#
# ./data-lake/energy_v3_2_3_structural_panel.csv
#
# fallback:
# ./data-lake/energy_v3_2_6_structural_panel.csv
# ./data-lake/energy_v3_2_5_structural_panel.csv
#
# ============================================================


import os
import re
import json
import warnings

from pathlib import Path
from datetime import date
from urllib.parse import urljoin

import numpy as np
import pandas as pd
import requests

from bs4 import BeautifulSoup


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


REFRESH_EOG_PR = (
    os.getenv(
        "REFRESH_EOG_PR",
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


# ------------------------------------------------------------
# Historical EOG releases
#
# validation이 2023Q3 이후라
# 2022부터 가져오면 전년 비교까지 충분
# ------------------------------------------------------------

EOG_START_YEAR = int(
    os.getenv(
        "EOG_START_YEAR",
        "2022",
    )
)


EOG_NEWS_PAGE_SIZE = int(
    os.getenv(
        "EOG_NEWS_PAGE_SIZE",
        "100",
    )
)


EOG_NEWS_MAX_PAGES = int(
    os.getenv(
        "EOG_NEWS_MAX_PAGES",
        "4",
    )
)


HTTP_TIMEOUT = int(
    os.getenv(
        "HTTP_TIMEOUT",
        "40",
    )
)


# ============================================================
# RECONSTRUCTION QC
# ============================================================

EOG_RECON_ERROR_MAX_PCT = float(
    os.getenv(
        "EOG_RECON_ERROR_MAX_PCT",
        "5.0",
    )
)


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


NO_COMPANY_PROD_MAX_WEIGHT = float(
    os.getenv(
        "NO_COMPANY_PROD_MAX_WEIGHT",
        "0.25",
    )
)


MIN_LOG_GROWTH = -100.0
MAX_LOG_GROWTH = 150.0


# ============================================================
# EOG URLs
# ============================================================

EOG_BASE_URL = (
    "https://investors.eogresources.com"
)


EOG_NEWS_URL = (
    EOG_BASE_URL
    +
    "/news"
)


# ============================================================
# 1. BASIC HELPERS
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
        /
        filename
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

print(
    "ENERGY REVENUE NOWCAST V3.2.7"
)

print("=" * 90)

print(
    "AS OF          :",
    AS_OF.date()
)

print(
    "TICKERS        :",
    TICKERS
)

print(
    "DATA LAKE      :",
    DATA_LAKE_DIR.resolve()
)

print(
    "REFRESH EOG PR :",
    REFRESH_EOG_PR
)


# ============================================================
# 2. HTTP
# ============================================================

session = requests.Session()


session.headers.update(
    {
        "User-Agent":
            (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "Chrome/140 Safari/537.36"
            ),

        "Accept-Language":
            "en-US,en;q=0.9",
    }
)


def http_get(
    url
):

    response = session.get(
        url,
        timeout=HTTP_TIMEOUT,
    )

    response.raise_for_status()

    return response


# ============================================================
# 3. TEXT / NUMERIC HELPERS
# ============================================================

def normalize_text(
    value
):

    if value is None:

        return ""

    value = str(
        value
    )

    value = (
        value
        .replace("\xa0", " ")
        .replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def normalize_label(
    value
):

    value = normalize_text(
        value
    ).lower()

    value = value.replace(
        "&",
        " and ",
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


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


def extract_numbers(
    cells
):

    values = []


    for cell in cells:

        text = normalize_text(
            cell
        )


        direct = numeric(
            text
        )


        if pd.notna(
            direct
        ):

            if not (
                1990
                <= direct
                <= 2100
            ):

                values.append(
                    float(
                        direct
                    )
                )

            continue


        tokens = re.findall(
            r"\(?-?"
            r"\d[\d,]*"
            r"(?:\.\d+)?"
            r"%?\)?",
            text,
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
                float(
                    number
                )
            )


    return values


# ============================================================
# 4. GROWTH HELPERS
# ============================================================

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


    result = pd.Series(
        np.nan,
        index=series.index,
        dtype=float,
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


    return result


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
    predicted
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
    predicted_log
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


# ============================================================
# 5. REQUIRED BASE FILES
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


for file_path in [
    PANEL_FILE,
    VALIDATION_FILE,
    NOWCAST_FILE,
]:

    if not file_path.exists():

        raise FileNotFoundError(
            f"{file_path} 없음."
        )


# ------------------------------------------------------------
# V3.2.3 champion 우선
# ------------------------------------------------------------

STRUCTURAL_CANDIDATES = [

    lake_path(
        "energy_v3_2_3_structural_panel.csv"
    ),

    lake_path(
        "energy_v3_2_6_structural_panel.csv"
    ),

    lake_path(
        "energy_v3_2_5_structural_panel.csv"
    ),

    lake_path(
        "energy_v3_2_4_structural_panel.csv"
    ),
]


STRUCTURAL_BASE_FILE = None


for candidate in (
    STRUCTURAL_CANDIDATES
):

    if candidate.exists():

        STRUCTURAL_BASE_FILE = (
            candidate
        )

        break


if STRUCTURAL_BASE_FILE is None:

    raise FileNotFoundError(
        "V3 structural panel 파일이 없어."
    )


print(
    "\nStructural base:",
    STRUCTURAL_BASE_FILE
)


# ============================================================
# 6. LOAD BASE DATA
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


base_structural = pd.read_csv(
    STRUCTURAL_BASE_FILE
)


base_structural[
    "quarter"
] = pd.PeriodIndex(
    base_structural[
        "quarter"
    ].astype(str),
    freq="Q",
)


base_structural = (
    base_structural[
        base_structural[
            "ticker"
        ].isin(
            TICKERS
        )
    ]
    .copy()
)


# ============================================================
# 7. QUARTER PARSING
# ============================================================

QUARTER_WORD = {

    "first":
        1,

    "second":
        2,

    "third":
        3,

    "fourth":
        4,
}


def headline_to_quarter(
    headline
):

    headline = normalize_text(
        headline
    )


    match = re.search(
        r"EOG\s+Resources\s+Reports\s+"
        r"(First|Second|Third|Fourth)\s+Quarter"
        r"(?:\s+and\s+Full[-\s]?Year)?"
        r"\s+(20\d{2})"
        r"\s+Results",
        headline,
        flags=re.I,
    )


    if not match:

        return None


    quarter_number = (
        QUARTER_WORD[
            match.group(1).lower()
        ]
    )


    year = int(
        match.group(2)
    )


    return pd.Period(
        f"{year}Q{quarter_number}",
        freq="Q",
    )


def period_from_cell(
    value
):

    text = normalize_text(
        value
    ).lower()


    # 2Q 2026
    match = re.search(
        r"\b([1-4])q\s*(20\d{2})\b",
        text,
    )


    if match:

        return pd.Period(
            (
                f"{match.group(2)}"
                f"Q{match.group(1)}"
            ),
            freq="Q",
        )


    # Q2 2026
    match = re.search(
        r"\bq([1-4])\s*(20\d{2})\b",
        text,
    )


    if match:

        return pd.Period(
            (
                f"{match.group(2)}"
                f"Q{match.group(1)}"
            ),
            freq="Q",
        )


    return None


# ============================================================
# 8. PRESS RELEASE DATE
# ============================================================

def url_release_date(
    url
):

    match = re.search(
        r"/(20\d{2})-(\d{2})-(\d{2})-",
        url,
    )


    if not match:

        return pd.NaT


    return pd.Timestamp(
        (
            f"{match.group(1)}-"
            f"{match.group(2)}-"
            f"{match.group(3)}"
        )
    )


# ============================================================
# 9. DISCOVER EOG EARNINGS RELEASES
# ============================================================

def discover_eog_press_releases():

    releases = {}


    for page_number in range(
        EOG_NEWS_MAX_PAGES
    ):

        offset = (
            page_number
            *
            EOG_NEWS_PAGE_SIZE
        )


        url = (
            EOG_NEWS_URL
            +
            f"?l={EOG_NEWS_PAGE_SIZE}"
            +
            f"&o={offset}"
        )


        try:

            response = http_get(
                url
            )

        except Exception as exc:

            print(
                f"⚠️ news page 실패 {url}:",
                repr(exc),
            )

            continue


        soup = BeautifulSoup(
            response.text,
            "lxml",
        )


        page_found = 0


        for anchor in soup.find_all(
            "a",
            href=True,
        ):

            headline = normalize_text(
                anchor.get_text(
                    " ",
                    strip=True,
                )
            )


            quarter = headline_to_quarter(
                headline
            )


            if quarter is None:

                continue


            if (
                quarter.year
                <
                EOG_START_YEAR
            ):

                continue


            href = urljoin(
                EOG_BASE_URL,
                anchor[
                    "href"
                ],
            )


            release_date = (
                url_release_date(
                    href
                )
            )


            if (
                pd.notna(
                    release_date
                )
                and
                release_date
                >
                AS_OF
            ):

                continue


            releases[
                quarter
            ] = {
                "quarter":
                    quarter,

                "headline":
                    headline,

                "url":
                    href,

                "release_date":
                    release_date,
            }


            page_found += 1


        if (
            releases
            and
            min(
                q.year
                for q
                in releases
            )
            <=
            EOG_START_YEAR
        ):

            break


        if (
            page_number > 0
            and
            page_found == 0
        ):

            break


    # --------------------------------------------------------
    # 최신 공식 News 페이지 fallback
    # --------------------------------------------------------

    if not releases:

        response = http_get(
            (
                EOG_NEWS_URL
                +
                "?l=100"
            )
        )


        soup = BeautifulSoup(
            response.text,
            "lxml",
        )


        for anchor in soup.find_all(
            "a",
            href=True,
        ):

            headline = normalize_text(
                anchor.get_text(
                    " ",
                    strip=True,
                )
            )


            quarter = headline_to_quarter(
                headline
            )


            if quarter is None:

                continue


            href = urljoin(
                EOG_BASE_URL,
                anchor[
                    "href"
                ],
            )


            releases[
                quarter
            ] = {
                "quarter":
                    quarter,

                "headline":
                    headline,

                "url":
                    href,

                "release_date":
                    url_release_date(
                        href
                    ),
            }


    result = sorted(
        releases.values(),
        key=lambda x:
            x[
                "quarter"
            ],
    )


    pd.DataFrame(
        result
    ).to_csv(
        lake_path(
            "energy_v3_2_7_eog_press_releases.csv"
        ),
        index=False,
    )


    print(
        "\nEOG earnings releases discovered:",
        len(
            result
        )
    )


    if result:

        print(
            pd.DataFrame(
                result
            )[
                [
                    "quarter",
                    "release_date",
                    "url",
                ]
            ]
            .tail(12)
            .to_string(
                index=False
            )
        )


    return result


# ============================================================
# 10. RAW HTML TABLE ROWS
# ============================================================

def table_rows(
    table_tag
):

    rows = []


    for tr in table_tag.find_all(
        "tr"
    ):

        cells = [
            normalize_text(
                cell.get_text(
                    " ",
                    strip=True,
                )
            )

            for cell
            in tr.find_all(
                [
                    "th",
                    "td",
                ]
            )
        ]


        if any(
            cell
            for cell
            in cells
        ):

            rows.append(
                cells
            )


    return rows


# ============================================================
# 11. ACTUAL COMPONENT DETECTOR
# ============================================================

def actual_component(
    label
):

    label = normalize_label(
        label
    )


    if (
        "crude oil and condensate"
        in label
        and
        "mbod"
        in label
        and
        "volumes"
        not in label
    ):

        return "oil"


    if (
        "natural gas liquids"
        in label
        and
        "mbbld"
        in label
        and
        "volumes"
        not in label
    ):

        return "ngl"


    if (
        "natural gas"
        in label
        and
        "liquid"
        not in label
        and
        "mmcfd"
        in label
        and
        "volumes"
        not in label
    ):

        return "gas"


    if (
        "total crude oil equivalent"
        in label
        and
        "mboed"
        in label
    ):

        return "total"


    return None


# ============================================================
# 12. HEADER COLUMN FOR CURRENT QUARTER
# ============================================================

def find_actual_quarter_column(
    rows,
    target_quarter
):

    for row_index, row in enumerate(
        rows
    ):

        periods = [
            period_from_cell(
                cell
            )
            for cell
            in row
        ]


        valid_periods = [
            x
            for x
            in periods
            if x is not None
        ]


        if (
            target_quarter
            not in valid_periods
        ):

            continue


        # 실제 Key Operational Results는
        # 여러 quarter가 같이 있음
        if len(
            valid_periods
        ) < 2:

            continue


        for column_index, period in enumerate(
            periods
        ):

            if period == target_quarter:

                return (
                    row_index,
                    column_index,
                )


    return (
        None,
        None,
    )


# ============================================================
# 13. ACTUAL TABLE PARSER
# ============================================================

def parse_actual_table(
    rows,
    target_quarter
):

    (
        header_row,
        target_column,
    ) = find_actual_quarter_column(
        rows,
        target_quarter,
    )


    if target_column is None:

        return None


    values = {

        "oil":
            np.nan,

        "ngl":
            np.nan,

        "gas":
            np.nan,

        "reported_total":
            np.nan,
    }


    matched_rows = []


    for row_index in range(
        header_row + 1,
        len(rows),
    ):

        row = rows[
            row_index
        ]


        component = None
        label_column = None


        for c, cell in enumerate(
            row
        ):

            detected = actual_component(
                cell
            )


            if detected:

                component = (
                    detected
                )

                label_column = c

                break


        if component is None:

            continue


        value = np.nan


        # ----------------------------------------------------
        # Header와 같은 column position
        # ----------------------------------------------------

        if (
            target_column
            <
            len(row)
        ):

            value = numeric(
                row[
                    target_column
                ]
            )


        # ----------------------------------------------------
        # colspan 때문에 위치가 다르면
        # label 뒤 첫 번째 numeric 사용
        #
        # Press Release current quarter는
        # 항상 첫 actual column
        # ----------------------------------------------------

        if pd.isna(
            value
        ):

            numeric_values = extract_numbers(
                row[
                    label_column + 1:
                ]
            )


            if numeric_values:

                value = numeric_values[
                    0
                ]


        if pd.notna(
            value
        ):

            values[
                (
                    "reported_total"
                    if component
                    ==
                    "total"
                    else
                    component
                )
            ] = float(
                value
            )


            matched_rows.append(
                {
                    "component":
                        component,

                    "row_index":
                        row_index,

                    "row_text":
                        " | ".join(
                            row
                        ),

                    "value":
                        value,
                }
            )


    component_count = sum(
        pd.notna(
            value
        )
        for value
        in values.values()
    )


    if component_count == 0:

        return None


    return {
        **values,

        "component_count":
            component_count,

        "matched_rows":
            matched_rows,
    }


# ============================================================
# 14. GUIDANCE SECTION DETECTOR
# ============================================================

def guidance_component(
    label
):

    label = normalize_label(
        label
    )


    if (
        "crude oil and condensate"
        in label
        and
        "volume"
        in label
        and
        "mbod"
        in label
    ):

        return "oil"


    if (
        "natural gas liquids"
        in label
        and
        "volume"
        in label
        and
        "mbbld"
        in label
    ):

        return "ngl"


    if (
        "natural gas"
        in label
        and
        "liquid"
        not in label
        and
        "volume"
        in label
        and
        "mmcfd"
        in label
    ):

        return "gas"


    if (
        "crude oil equivalent"
        in label
        and
        "volume"
        in label
        and
        "mboed"
        in label
    ):

        return "total"


    return None


# ============================================================
# 15. GUIDANCE TABLE TARGET
# ============================================================

def guidance_table_target_quarter(
    rows,
    result_quarter
):

    candidate_periods = []


    for row in rows[
        :8
    ]:

        for cell in row:

            period = period_from_cell(
                cell
            )


            if (
                period is not None
                and
                period
                >
                result_quarter
            ):

                candidate_periods.append(
                    period
                )


    if not candidate_periods:

        return None


    # 가장 가까운 미래 quarter
    return min(
        candidate_periods
    )


# ============================================================
# 16. GUIDANCE MIDPOINT
# ============================================================

COMPONENT_LIMITS = {

    "oil":
        (
            10,
            2000,
        ),

    "ngl":
        (
            0,
            2000,
        ),

    "gas":
        (
            0,
            20000,
        ),

    "total":
        (
            100,
            4000,
        ),
}


def guidance_midpoint(
    row,
    component
):

    values = extract_numbers(
        row[
            1:
        ]
    )


    low_limit, high_limit = (
        COMPONENT_LIMITS[
            component
        ]
    )


    values = [
        x

        for x
        in values

        if (
            low_limit
            <= x
            <= high_limit
        )
    ]


    if len(
        values
    ) >= 3:

        expected_mid = (
            values[
                0
            ]
            +
            values[
                1
            ]
        ) / 2


        tolerance = max(
            0.5,
            abs(
                expected_mid
            )
            *
            0.04,
        )


        if abs(
            values[
                2
            ]
            -
            expected_mid
        ) <= tolerance:

            return float(
                values[
                    2
                ]
            )


    if len(
        values
    ) >= 2:

        return float(
            (
                values[
                    0
                ]
                +
                values[
                    1
                ]
            ) / 2
        )


    if len(
        values
    ) == 1:

        return float(
            values[
                0
            ]
        )


    return np.nan


# ============================================================
# 17. GUIDANCE TABLE PARSER
# ============================================================

def parse_guidance_table(
    rows,
    result_quarter
):

    target_quarter = (
        guidance_table_target_quarter(
            rows,
            result_quarter,
        )
    )


    if target_quarter is None:

        return None


    # 반드시 다음 분기여야 함.
    if (
        target_quarter
        !=
        result_quarter
        +
        1
    ):

        return None


    table_text = normalize_label(
        " ".join(
            cell
            for row
            in rows
            for cell
            in row
        )
    )


    if (
        "guidance"
        not in table_text
        or
        "midpoint"
        not in table_text
    ):

        return None


    values = {

        "oil":
            np.nan,

        "ngl":
            np.nan,

        "gas":
            np.nan,

        "reported_total":
            np.nan,
    }


    current_section = None


    debug = []


    for row_index, row in enumerate(
        rows
    ):

        if not row:

            continue


        # ----------------------------------------------------
        # Section header
        # ----------------------------------------------------

        for cell in row:

            component = guidance_component(
                cell
            )


            if component is not None:

                current_section = (
                    component
                )

                break


        if current_section is None:

            continue


        first_nonempty = None


        for cell in row:

            if normalize_text(
                cell
            ):

                first_nonempty = (
                    normalize_text(
                        cell
                    )
                )

                break


        if first_nonempty is None:

            continue


        # ----------------------------------------------------
        # Total row
        # ----------------------------------------------------

        if (
            normalize_label(
                first_nonempty
            )
            !=
            "total"
        ):

            continue


        midpoint = (
            guidance_midpoint(
                row,
                current_section,
            )
        )


        if pd.isna(
            midpoint
        ):

            continue


        target_key = (
            "reported_total"

            if current_section
            ==
            "total"

            else current_section
        )


        values[
            target_key
        ] = (
            midpoint
        )


        debug.append(
            {
                "section":
                    current_section,

                "row_index":
                    row_index,

                "row_text":
                    " | ".join(
                        row
                    ),

                "midpoint":
                    midpoint,
            }
        )


    component_count = sum(
        pd.notna(
            value
        )
        for value
        in values.values()
    )


    if component_count == 0:

        return None


    return {
        "target_quarter":
            target_quarter,

        **values,

        "component_count":
            component_count,

        "matched_rows":
            debug,
    }


# ============================================================
# 18. BOE RECONSTRUCTION
# ============================================================

def reconstruct_total_boe(
    oil,
    ngl,
    gas
):

    if (
        pd.isna(
            oil
        )
        or
        pd.isna(
            ngl
        )
        or
        pd.isna(
            gas
        )
    ):

        return np.nan


    return float(
        oil
        +
        ngl
        +
        gas / 6.0
    )


def recon_error_pct(
    reported,
    reconstructed
):

    if (
        pd.isna(
            reported
        )
        or
        pd.isna(
            reconstructed
        )
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


def finalize_production(
    candidate
):

    oil = candidate.get(
        "oil",
        np.nan,
    )

    ngl = candidate.get(
        "ngl",
        np.nan,
    )

    gas = candidate.get(
        "gas",
        np.nan,
    )

    reported = candidate.get(
        "reported_total",
        np.nan,
    )


    reconstructed = (
        reconstruct_total_boe(
            oil,
            ngl,
            gas,
        )
    )


    error = recon_error_pct(
        reported,
        reconstructed,
    )


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
            error
            <=
            EOG_RECON_ERROR_MAX_PCT
        ):

            total = (
                reported
            )

            flag = (
                "REPORTED_RECON_MATCH"
            )

            quality = 1.00


        else:

            total = (
                reconstructed
            )

            flag = (
                "REPORTED_REJECTED_USE_RECONSTRUCTED"
            )

            quality = 0.85


    elif pd.notna(
        reconstructed
    ):

        total = (
            reconstructed
        )

        flag = (
            "RECONSTRUCTED_ONLY"
        )

        quality = 0.90


    elif pd.notna(
        reported
    ):

        total = (
            reported
        )

        flag = (
            "REPORTED_ONLY"
        )

        quality = 0.75


    else:

        total = np.nan

        flag = (
            "NO_VALID_TOTAL"
        )

        quality = 0.0


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
            error,

        "total_production":
            total,

        "component_qc_flag":
            flag,

        "data_quality_score":
            quality,
    }


# ============================================================
# 19. PARSE ONE PRESS RELEASE
# ============================================================

def parse_eog_press_release(
    release
):

    quarter = release[
        "quarter"
    ]


    url = release[
        "url"
    ]


    response = http_get(
        url
    )


    soup = BeautifulSoup(
        response.text,
        "lxml",
    )


    actual_candidates = []

    guidance_candidates = []

    debug_rows = []


    for table_index, table in enumerate(
        soup.find_all(
            "table"
        )
    ):

        rows = table_rows(
            table
        )


        if not rows:

            continue


        # ----------------------------------------------------
        # Actual candidate
        # ----------------------------------------------------

        actual = parse_actual_table(
            rows,
            quarter,
        )


        if actual is not None:

            actual[
                "table_index"
            ] = table_index


            actual_candidates.append(
                actual
            )


        # ----------------------------------------------------
        # Guidance candidate
        # ----------------------------------------------------

        guidance = (
            parse_guidance_table(
                rows,
                quarter,
            )
        )


        if guidance is not None:

            guidance[
                "table_index"
            ] = table_index


            guidance_candidates.append(
                guidance
            )


    # ========================================================
    # Pick best actual
    # ========================================================

    actual_output = None


    if actual_candidates:

        actual_candidates = sorted(
            actual_candidates,
            key=lambda x:
                x[
                    "component_count"
                ],
            reverse=True,
        )


        best = actual_candidates[
            0
        ]


        finalized = (
            finalize_production(
                best
            )
        )


        actual_output = {
            "quarter":
                quarter,

            "release_date":
                release[
                    "release_date"
                ],

            "source_url":
                url,

            **finalized,
        }


        for item in best[
            "matched_rows"
        ]:

            debug_rows.append(
                {
                    "quarter":
                        quarter,

                    "type":
                        "ACTUAL",

                    "table_index":
                        best[
                            "table_index"
                        ],

                    **item,
                }
            )


    # ========================================================
    # Pick best guidance
    # ========================================================

    guidance_output = None


    if guidance_candidates:

        # 다음 분기 + component 수 많은 것
        guidance_candidates = sorted(
            guidance_candidates,
            key=lambda x:
                x[
                    "component_count"
                ],
            reverse=True,
        )


        best = guidance_candidates[
            0
        ]


        finalized = (
            finalize_production(
                best
            )
        )


        guidance_output = {
            "target_quarter":
                best[
                    "target_quarter"
                ],

            "release_date":
                release[
                    "release_date"
                ],

            "source_url":
                url,

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


        for item in best[
            "matched_rows"
        ]:

            debug_rows.append(
                {
                    "quarter":
                        best[
                            "target_quarter"
                        ],

                    "type":
                        "GUIDANCE",

                    "table_index":
                        best[
                            "table_index"
                        ],

                    **item,
                }
            )


    return (
        actual_output,
        guidance_output,
        debug_rows,
    )


# ============================================================
# 20. EOG CACHE
# ============================================================

EOG_ACTUAL_FILE = lake_path(
    "energy_v3_2_7_actual_EOG.csv"
)


EOG_GUIDANCE_FILE = lake_path(
    "energy_v3_2_7_guidance_EOG.csv"
)


EOG_DEBUG_FILE = lake_path(
    "energy_v3_2_7_eog_press_release_debug.csv"
)


if (
    REFRESH_EOG_PR
    or
    not EOG_ACTUAL_FILE.exists()
    or
    not EOG_GUIDANCE_FILE.exists()
):

    releases = (
        discover_eog_press_releases()
    )


    actual_rows = []

    guidance_rows = []

    debug_rows = []


    for release in releases:

        try:

            (
                actual,
                guidance,
                debug,
            ) = (
                parse_eog_press_release(
                    release
                )
            )


        except Exception as exc:

            print(
                f"⚠️ EOG {release['quarter']} "
                f"parse 실패:",
                repr(
                    exc
                ),
            )

            continue


        if actual is not None:

            actual_rows.append(
                actual
            )


        if guidance is not None:

            guidance_rows.append(
                guidance
            )


        debug_rows.extend(
            debug
        )


    eog_actual = pd.DataFrame(
        actual_rows
    )


    eog_guidance = pd.DataFrame(
        guidance_rows
    )


    if not eog_actual.empty:

        eog_actual[
            "quarter"
        ] = pd.PeriodIndex(
            eog_actual[
                "quarter"
            ].astype(str),
            freq="Q",
        )


        eog_actual = (
            eog_actual
            .sort_values(
                [
                    "quarter",
                    "data_quality_score",
                ]
            )
            .drop_duplicates(
                "quarter",
                keep="last",
            )
            .sort_values(
                "quarter"
            )
        )


    if not eog_guidance.empty:

        eog_guidance[
            "target_quarter"
        ] = pd.PeriodIndex(
            eog_guidance[
                "target_quarter"
            ].astype(str),
            freq="Q",
        )


        eog_guidance = (
            eog_guidance
            .sort_values(
                [
                    "target_quarter",
                    "guidance_data_quality_score",
                ]
            )
            .drop_duplicates(
                "target_quarter",
                keep="last",
            )
            .sort_values(
                "target_quarter"
            )
        )


    eog_actual.to_csv(
        EOG_ACTUAL_FILE,
        index=False,
    )


    eog_guidance.to_csv(
        EOG_GUIDANCE_FILE,
        index=False,
    )


    pd.DataFrame(
        debug_rows
    ).to_csv(
        EOG_DEBUG_FILE,
        index=False,
    )


else:

    eog_actual = pd.read_csv(
        EOG_ACTUAL_FILE
    )


    eog_guidance = pd.read_csv(
        EOG_GUIDANCE_FILE
    )


    if not eog_actual.empty:

        eog_actual[
            "quarter"
        ] = pd.PeriodIndex(
            eog_actual[
                "quarter"
            ].astype(str),
            freq="Q",
        )


    if not eog_guidance.empty:

        eog_guidance[
            "target_quarter"
        ] = pd.PeriodIndex(
            eog_guidance[
                "target_quarter"
            ].astype(str),
            freq="Q",
        )


# ============================================================
# 21. EXACT CHECK
# ============================================================

print(
    "\n"
    + "=" * 90
)

print(
    "EOG V3.2.7 PRESS RELEASE CHECK"
)

print(
    "=" * 90
)


if not eog_actual.empty:

    print(
        eog_actual[
            [
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
        ]
        .tail(16)
        .round(2)
        .to_string(
            index=False
        )
    )


if not eog_guidance.empty:

    print(
        "\n===== EOG GUIDANCE ====="
    )


    print(
        eog_guidance[
            [
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
        ]
        .tail(10)
        .round(2)
        .to_string(
            index=False
        )
    )


# ============================================================
# 22. CURRENT DATA CHECK
# ============================================================

eog_last_revenue_q = (
    panel_v21[
        (
            panel_v21[
                "ticker"
            ]
            ==
            "EOG"
        )
        &
        (
            panel_v21[
                "revenue"
            ]
            .notna()
        )
    ][
        "quarter"
    ]
    .max()
)


eog_target_q = (
    eog_last_revenue_q
    +
    1
)


latest_actual_q = (
    eog_actual[
        "quarter"
    ]
    .max()

    if not eog_actual.empty

    else None
)


guidance_quarters = (
    set(
        eog_guidance[
            "target_quarter"
        ]
    )

    if not eog_guidance.empty

    else set()
)


print(
    "\nEOG latest revenue quarter :",
    eog_last_revenue_q
)

print(
    "EOG latest PR actual      :",
    latest_actual_q
)

print(
    "EOG target nowcast        :",
    eog_target_q
)

print(
    "EOG target guidance found :",
    (
        eog_target_q
        in
        guidance_quarters
    )
)


# ============================================================
# 23. PERIOD MAPPER
# ============================================================

def map_period_values(
    quarter_series,
    source_df,
    index_column,
    value_column,
    default=np.nan,
):

    if (
        source_df is None
        or
        source_df.empty
        or
        value_column
        not in source_df.columns
    ):

        return pd.Series(
            default,
            index=quarter_series.index,
        )


    mapping = dict(
        zip(
            source_df[
                index_column
            ],
            source_df[
                value_column
            ],
        )
    )


    return pd.Series(
        [
            mapping.get(
                q,
                default,
            )

            for q
            in quarter_series
        ],
        index=quarter_series.index,
    )


# ============================================================
# 24. REBUILD EOG STRUCTURAL
# ============================================================

def rebuild_eog_structural(
    base_eog,
    actual_df,
    guidance_df,
):

    df = (
        base_eog
        .sort_values(
            "quarter"
        )
        .reset_index(
            drop=True
        )
        .copy()
    )


    # ========================================================
    # ACTUAL
    # ========================================================

    for source_col in [

        "total_production",

        "oil_production",

        "ngl_production",

        "gas_production",

        "data_quality_score",
    ]:

        target_col = (
            "actual_data_quality"

            if source_col
            ==
            "data_quality_score"

            else source_col
        )


        df[
            target_col
        ] = map_period_values(
            df[
                "quarter"
            ],
            actual_df,
            "quarter",
            source_col,
            default=(
                0.0

                if target_col
                ==
                "actual_data_quality"

                else
                np.nan
            ),
        )


    # ========================================================
    # GUIDANCE
    # ========================================================

    df[
        "guidance_total_production"
    ] = map_period_values(
        df[
            "quarter"
        ],
        guidance_df,
        "target_quarter",
        "guidance_total_production",
    )


    df[
        "guidance_data_quality"
    ] = map_period_values(
        df[
            "quarter"
        ],
        guidance_df,
        "target_quarter",
        "guidance_data_quality_score",
        default=0.0,
    )


    # ========================================================
    # ACTUAL YOY
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
    # ACTUAL PAIR QUALITY
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
    # GUIDANCE VS ACTUAL
    # ========================================================

    prior_actual = (
        df[
            "total_production"
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
        *
        100
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
    # GUIDANCE VS GUIDANCE
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
        *
        100
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
    # INDUSTRY
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
    # SOURCE SELECTION
    # ========================================================

    values = []

    sources = []

    qualities = []


    for i in range(
        len(
            df
        )
    ):

        # ----------------------------------------------------
        # 1. Guidance vs Actual
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # 2. Guidance vs Guidance
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # 3. Actual vs Actual
        # ----------------------------------------------------

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

                pair_quality = 0.0


            quality = (
                SOURCE_QUALITY[
                    source
                ]
                *
                pair_quality
            )


        # ----------------------------------------------------
        # 4. Industry fallback
        # ----------------------------------------------------

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
            np.nan,
        )
        .clip(
            0.10,
            1.0,
        )
    )


    median_oil_share = (
        oil_share.median(
            skipna=True
        )
    )


    # 실제 EOG는 최근 oil BOE share 약 39%
    if pd.isna(
        median_oil_share
    ):

        median_oil_share = 0.39


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
            1.0,
        )
    )


    # ========================================================
    # PRICE MIX
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
    # STRUCTURAL REVENUE
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
# 25. PATCH EOG
# ============================================================

non_eog = (
    base_structural[
        base_structural[
            "ticker"
        ]
        !=
        "EOG"
    ]
    .copy()
)


base_eog = (
    base_structural[
        base_structural[
            "ticker"
        ]
        ==
        "EOG"
    ]
    .copy()
)


patched_eog = (
    rebuild_eog_structural(
        base_eog,
        eog_actual,
        eog_guidance,
    )
)


structural_panel = (
    pd.concat(
        [
            non_eog,
            patched_eog,
        ],
        ignore_index=True,
        sort=False,
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
        "energy_v3_2_7_structural_panel.csv"
    ),
    index=False,
)


# ============================================================
# 26. SOURCE SUMMARY
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
        "energy_v3_2_7_source_quality_summary.csv"
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
# 27. VALIDATION ALIGNMENT
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
] = (
    compare[
        "v21_actual_log_yoy"
    ]
)


# ============================================================
# 28. BLEND HELPERS
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
                1
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
# 29. WALK-FORWARD
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
                1
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
# 30. METRICS
# ============================================================

metric_rows = []


print(
    "\n"
    + "=" * 90
)

print(
    "V3.2.7 WALK-FORWARD VALIDATION"
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

            "V3_2_7_MAE_log_points":
                mae(
                    group[
                        "actual_log_yoy"
                    ],
                    group[
                        "blend_log_yoy"
                    ],
                ),

            "V3_2_7_MAE_yoy_pct_points":
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


overall_v327_log = mae(
    walk_validation[
        "actual_log_yoy"
    ],
    walk_validation[
        "blend_log_yoy"
    ],
)


overall_v327_pct = (
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
    f"V2.1       : "
    f"{overall_v21_log:.2f} log-points"
)

print(
    f"Structural : "
    f"{overall_struct_log:.2f} log-points"
)

print(
    f"V3.2.7     : "
    f"{overall_v327_log:.2f} log-points"
)


print(
    "\n===== NORMAL REVENUE YOY SCALE ====="
)

print(
    f"V2.1       : "
    f"{overall_v21_pct:.2f} %p"
)

print(
    f"Structural : "
    f"{overall_struct_pct:.2f} %p"
)

print(
    f"V3.2.7     : "
    f"{overall_v327_pct:.2f} %p"
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
        "energy_v3_2_7_validation.csv"
    ),
    index=False,
)


metrics.to_csv(
    lake_path(
        "energy_v3_2_7_metrics.csv"
    )
)


# ============================================================
# 31. FINAL BASE WEIGHTS
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
        "energy_v3_2_7_blend_weights.csv"
    )
)


# ============================================================
# 32. CURRENT STRUCTURAL NOWCAST
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
        +
        1
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
                (
                    row[
                        "guidance_total_production"
                    ]

                    if
                    "guidance_total_production"
                    in
                    row.index

                    else
                    np.nan
                ),
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
# 33. MERGE CURRENT V2.1
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
# 34. CURRENT WEIGHTS
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
    1
    -
    current[
        "structural_weight"
    ]
)


# ============================================================
# 35. FINAL NOWCAST
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
# 36. REVENUE LEVEL
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


    revenue = (
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
        revenue
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
# 37. CONFIDENCE
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
    "selected_model"
] = current.apply(
    selected_model,
    axis=1,
)


current[
    "confidence"
] = current.apply(
    confidence,
    axis=1,
)


# ============================================================
# 38. FINAL OUTPUT
# ============================================================

output = (
    current[
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

            "selected_model",

            "company_prod_yoy_proxy",

            "production_yoy_source",

            "guidance_total_production",

            "model_spread_log_points",

            "confidence",
        ]
    ]
    .copy()
)


print(
    "\n"
    + "=" * 90
)

print(
    "🚀 ENERGY REVENUE V3.2.7 NOWCAST"
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
        "energy_v3_2_7_nowcast.csv"
    ),
    index=False,
)


# ============================================================
# 39. COMPARE PREVIOUS VERSIONS
# ============================================================

for version in [
    "3_2_6",
    "3_2_5",
    "3_2_4",
]:

    previous_file = lake_path(
        f"energy_v{version}_metrics.csv"
    )


    if not previous_file.exists():

        continue


    try:

        old = pd.read_csv(
            previous_file,
            index_col=0,
        )


        old_log_column = (
            f"V{version}_MAE_log_points"
        )


        old_pct_column = (
            f"V{version}_MAE_yoy_pct_points"
        )


        if (
            old_log_column
            not in old.columns
        ):

            continue


        print(
            "\n"
            + "=" * 90
        )

        print(
            f"V{version.replace('_', '.')} "
            f"vs V3.2.7"
        )

        print(
            "=" * 90
        )


        comparison = pd.DataFrame(
            index=metrics.index
        )


        comparison[
            "previous_log_MAE"
        ] = old[
            old_log_column
        ]


        comparison[
            "V3_2_7_log_MAE"
        ] = metrics[
            "V3_2_7_MAE_log_points"
        ]


        comparison[
            "log_improvement"
        ] = (
            comparison[
                "previous_log_MAE"
            ]
            -
            comparison[
                "V3_2_7_log_MAE"
            ]
        )


        if (
            old_pct_column
            in old.columns
        ):

            comparison[
                "previous_pct_MAE"
            ] = old[
                old_pct_column
            ]


            comparison[
                "V3_2_7_pct_MAE"
            ] = metrics[
                "V3_2_7_MAE_yoy_pct_points"
            ]


            comparison[
                "pct_improvement"
            ] = (
                comparison[
                    "previous_pct_MAE"
                ]
                -
                comparison[
                    "V3_2_7_pct_MAE"
                ]
            )


        print(
            comparison.round(
                2
            )
        )


        break


    except Exception:

        pass


# ============================================================
# 40. METADATA
# ============================================================

metadata = {

    "version":
        "3.2.7",

    "structural_base_file":
        str(
            STRUCTURAL_BASE_FILE
        ),

    "eog_actual_source":
        (
            "Official EOG Earnings "
            "Press Release HTML"
        ),

    "eog_guidance_source":
        (
            "Official EOG Earnings "
            "Press Release HTML"
        ),

    "eog_start_year":
        EOG_START_YEAR,

    "eog_reconstruction_formula":
        (
            "Oil MBod + NGL MBbld "
            "+ Gas MMcfd / 6 "
            "= Total MBoed"
        ),

    "eog_reconstruction_error_max_pct":
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
        "energy_v3_2_7_metadata.json"
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
# 41. DONE
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

    "energy_v3_2_7_eog_press_releases.csv",

    "energy_v3_2_7_actual_EOG.csv",

    "energy_v3_2_7_guidance_EOG.csv",

    "energy_v3_2_7_eog_press_release_debug.csv",

    "energy_v3_2_7_structural_panel.csv",

    "energy_v3_2_7_source_quality_summary.csv",

    "energy_v3_2_7_validation.csv",

    "energy_v3_2_7_metrics.csv",

    "energy_v3_2_7_blend_weights.csv",

    "energy_v3_2_7_nowcast.csv",

    "energy_v3_2_7_metadata.json",
]:

    print(
        " -",
        lake_path(
            filename
        )
    )
