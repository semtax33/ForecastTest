# ============================================================
# ENERGY REVENUE NOWCAST V3.3
# ============================================================
#
# V3.3 = COMPONENT PRICE x VOLUME MODEL
#
# ------------------------------------------------------------
# EOG ONLY:
#
# Oil Revenue Proxy
#   = Oil MBod * WTI $/bbl
#
# NGL Revenue Proxy
#   = NGL MBbld * Mont Belvieu Propane $/gal * 42
#
# Gas Revenue Proxy
#   = Gas MMcfd * Henry Hub $/Mcf
#
#
# Total Economic Revenue Driver
#   =
#   Oil Driver
#   + NGL Driver
#   + Gas Driver
#
#
# Component Structural Revenue Log YoY
#   =
#   log(
#       Current Economic Driver
#       /
#       Prior-Year Economic Driver
#   ) * 100
#
#
# ------------------------------------------------------------
# IMPORTANT:
#
# Current quarter = QTD prices through AS_OF_DATE.
#
# Historical validation quarters use the SAME
# day-of-quarter cutoff.
#
# Example:
#
# AS_OF = 2026-08-31
#
# 2026Q3 price:
#     Jul 1 ~ Aug 31
#
# Historical 2025Q3 validation:
#     Jul 1 ~ Aug 31
#
# NOT:
#     Jul 1 ~ Sep 30
#
# This reduces intra-quarter look-ahead.
#
#
# ------------------------------------------------------------
# VOLUME
#
# Target-quarter guidance components:
#
#   current oil/ngl/gas
#
# Prior-year actual:
#
#   q - 4 actual oil/ngl/gas
#
#
# If exactly one guidance component is missing:
#
#   solve from Total BOE
#
# Example:
#
# NGL
# =
# Total
# - Oil
# - Gas/6
#
#
# ------------------------------------------------------------
# NGL PRICE
#
# Mont Belvieu TX Propane Spot Price FOB
#
# EIA legacy SeriesID:
#
# PET.EER_EPLLPA_PF4_Y44MB_DPG.D
#
#
# ------------------------------------------------------------
# OTHER COMPANIES
#
# COP / FANG / DVN:
#
# keep V3.2.7 structural model unchanged.
#
#
# ------------------------------------------------------------
# FINAL MODEL
#
# Final Revenue Log YoY
# =
# w * Structural
# +
# (1-w) * V2.1
#
# Walk-forward blend weights retained.
#
#
# ------------------------------------------------------------
# INPUT FILES
#
# energy_v2_1_panel.csv
# energy_v2_1_validation.csv
# energy_v2_1_nowcast.csv
#
# energy_v3_2_7_structural_panel.csv
# energy_v3_2_7_actual_EOG.csv
# energy_v3_2_7_guidance_EOG.csv
#
#
# ------------------------------------------------------------
# OUTPUT
#
# energy_v3_3_eia_prices_daily.csv
# energy_v3_3_price_quarters.csv
# energy_v3_3_eog_component_panel.csv
# energy_v3_3_structural_panel.csv
# energy_v3_3_validation.csv
# energy_v3_3_metrics.csv
# energy_v3_3_blend_weights.csv
# energy_v3_3_nowcast.csv
# energy_v3_3_metadata.json
#
# ============================================================


import os
import json
import warnings

from pathlib import Path
from datetime import date

import numpy as np
import pandas as pd
import requests


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


EIA_API_KEY = os.getenv(
    "EIA_API_KEY"
)


AS_OF_DATE_ENV = os.getenv(
    "AS_OF_DATE"
)


TICKERS = [
    x.strip().upper()

    for x in os.getenv(
        "TICKERS",
        "COP,EOG,FANG,DVN",
    ).split(",")

    if x.strip()
]


# ============================================================
# PRICE WINDOW
# ============================================================

PRICE_WINDOW_MODE = os.getenv(
    "PRICE_WINDOW_MODE",
    "SAME_DAY_OF_QUARTER",
).upper()


# ============================================================
# EIA SERIES
# ============================================================

EIA_SERIES = {

    "wti":
        "PET.RWTC.D",

    "henry":
        "NG.RNGWHHD.D",

    "propane":
        "PET.EER_EPLLPA_PF4_Y44MB_DPG.D",
}


# ============================================================
# EIA HISTORY
# ============================================================

EIA_START_DATE = os.getenv(
    "EIA_START_DATE",
    "2021-01-01",
)


# ============================================================
# BLEND
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


# ============================================================
# MODEL BOUNDS
# ============================================================

MIN_LOG_GROWTH = -100.0
MAX_LOG_GROWTH = 150.0


# ============================================================
# COMPONENT QUALITY
# ============================================================

GUIDANCE_EXACT_QUALITY = 1.00

GUIDANCE_SOLVED_QUALITY = 0.90

GUIDANCE_MIX_IMPUTED_QUALITY = 0.75

PRICE_COMPLETE_QUALITY = 1.00


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


CURRENT_QUARTER = (
    AS_OF.to_period(
        "Q"
    )
)


CURRENT_QUARTER_START = (
    CURRENT_QUARTER
    .start_time
    .normalize()
)


DAY_OF_QUARTER = int(
    (
        AS_OF
        -
        CURRENT_QUARTER_START
    ).days
)


print("=" * 95)

print(
    "ENERGY REVENUE NOWCAST V3.3"
)

print("=" * 95)

print(
    "AS OF              :",
    AS_OF.date()
)

print(
    "CURRENT QUARTER    :",
    CURRENT_QUARTER
)

print(
    "DAY OF QUARTER     :",
    DAY_OF_QUARTER
)

print(
    "PRICE WINDOW       :",
    PRICE_WINDOW_MODE
)

print(
    "DATA LAKE          :",
    DATA_LAKE_DIR.resolve()
)


# ============================================================
# 2. REQUIRED FILES
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


STRUCTURAL_FILE = lake_path(
    "energy_v3_2_7_structural_panel.csv"
)


EOG_ACTUAL_FILE = lake_path(
    "energy_v3_2_7_actual_EOG.csv"
)


EOG_GUIDANCE_FILE = lake_path(
    "energy_v3_2_7_guidance_EOG.csv"
)


for path in [

    PANEL_FILE,

    VALIDATION_FILE,

    NOWCAST_FILE,

    STRUCTURAL_FILE,

    EOG_ACTUAL_FILE,

    EOG_GUIDANCE_FILE,

]:

    if not path.exists():

        raise FileNotFoundError(
            f"\n필수 파일 없음:\n{path}"
        )


if not EIA_API_KEY:

    raise ValueError(
        "\nEIA_API_KEY 환경변수가 없어.\n\n"
        'export EIA_API_KEY="네_API_KEY"\n'
    )


# ============================================================
# 3. GENERIC HELPERS
# ============================================================

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


    text = str(
        value
    ).strip()


    if text in {
        "",
        "-",
        "--",
        "NA",
        "N/A",
        "None",
    }:

        return np.nan


    text = (
        text
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


def log_ratio(
    current,
    previous
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
        *
        100
    )


def log_to_normal_pct(
    value
):

    if isinstance(
        value,
        pd.Series,
    ):

        return (
            np.exp(
                value
                /
                100
            )
            -
            1
        ) * 100


    if isinstance(
        value,
        np.ndarray,
    ):

        return (
            np.exp(
                value
                /
                100
            )
            -
            1
        ) * 100


    if pd.isna(
        value
    ):

        return np.nan


    return (
        np.exp(
            value
            /
            100
        )
        -
        1
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
# 4. LOAD CORE DATA
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
    STRUCTURAL_FILE
)


base_structural[
    "quarter"
] = pd.PeriodIndex(
    base_structural[
        "quarter"
    ].astype(str),
    freq="Q",
)


eog_actual = pd.read_csv(
    EOG_ACTUAL_FILE
)


eog_actual[
    "quarter"
] = pd.PeriodIndex(
    eog_actual[
        "quarter"
    ].astype(str),
    freq="Q",
)


eog_guidance = pd.read_csv(
    EOG_GUIDANCE_FILE
)


eog_guidance[
    "target_quarter"
] = pd.PeriodIndex(
    eog_guidance[
        "target_quarter"
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
    "V3.2.7 panel    :",
    base_structural.shape
)

print(
    "EOG actual      :",
    eog_actual.shape
)

print(
    "EOG guidance    :",
    eog_guidance.shape
)


# ============================================================
# 5. EIA API
# ============================================================

session = requests.Session()


session.headers.update(
    {
        "User-Agent":
            (
                "Energy-Revenue-Nowcast/3.3 "
                "research"
            )
    }
)


def extract_eia_row_value(
    row
):

    # Standard v2 series-id translation usually contains value.
    for key in [

        "value",

        "Value",

        "price",

        "Price",

    ]:

        if key in row:

            value = numeric(
                row[
                    key
                ]
            )


            if pd.notna(
                value
            ):

                return value


    # Defensive fallback
    ignored = {

        "period",

        "series",

        "series-id",

        "seriesDescription",

        "series-description",

        "name",

        "description",

        "unit",

        "units",

    }


    for key, raw_value in (
        row.items()
    ):

        if key in ignored:

            continue


        value = numeric(
            raw_value
        )


        if pd.notna(
            value
        ):

            return value


    return np.nan


def fetch_eia_daily_series(
    series_id,
    label
):

    url = (
        "https://api.eia.gov/"
        "v2/seriesid/"
        f"{series_id}"
    )


    params = {

        "api_key":
            EIA_API_KEY,

        "start":
            EIA_START_DATE,

        "end":
            AS_OF.strftime(
                "%Y-%m-%d"
            ),

        "length":
            5000,

        "sort[0][column]":
            "period",

        "sort[0][direction]":
            "asc",
    }


    response = session.get(
        url,
        params=params,
        timeout=45,
    )


    if not response.ok:

        raise RuntimeError(
            f"\nEIA API 실패\n"
            f"Series: {series_id}\n"
            f"HTTP: {response.status_code}\n"
            f"{response.text[:1000]}"
        )


    payload = response.json()


    rows = (
        payload
        .get(
            "response",
            {}
        )
        .get(
            "data",
            []
        )
    )


    if not rows:

        raise RuntimeError(
            f"EIA series 데이터 없음: {series_id}"
        )


    records = []


    for row in rows:

        period = row.get(
            "period"
        )


        value = extract_eia_row_value(
            row
        )


        if (
            period is None
            or
            pd.isna(
                value
            )
        ):

            continue


        timestamp = pd.to_datetime(
            period,
            errors="coerce",
        )


        if pd.isna(
            timestamp
        ):

            continue


        records.append(
            {
                "date":
                    timestamp.normalize(),

                "series":
                    label,

                "series_id":
                    series_id,

                "value":
                    float(
                        value
                    ),
            }
        )


    result = pd.DataFrame(
        records
    )


    if result.empty:

        raise RuntimeError(
            f"EIA parsing 결과 없음: {series_id}"
        )


    return (
        result
        .drop_duplicates(
            [
                "date",
                "series",
            ]
        )
        .sort_values(
            "date"
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# 6. FETCH PRICE DATA
# ============================================================

print(
    "\n"
    + "=" * 95
)

print(
    "FETCHING EIA COMPONENT PRICES"
)

print(
    "=" * 95
)


price_frames = []


for label, series_id in (
    EIA_SERIES.items()
):

    df = fetch_eia_daily_series(
        series_id,
        label,
    )


    price_frames.append(
        df
    )


    print(
        f"{label:8s} "
        f"{series_id:40s} "
        f"{len(df):5d} observations "
        f"{df['date'].min().date()} "
        f"→ {df['date'].max().date()}"
    )


prices_daily_long = pd.concat(
    price_frames,
    ignore_index=True,
)


prices_daily = (
    prices_daily_long
    .pivot_table(
        index="date",
        columns="series",
        values="value",
        aggfunc="last",
    )
    .sort_index()
)


prices_daily.to_csv(
    lake_path(
        "energy_v3_3_eia_prices_daily.csv"
    )
)


# ============================================================
# 7. PRICE WINDOW
# ============================================================

def price_window_for_quarter(
    quarter
):

    start = (
        quarter
        .start_time
        .normalize()
    )


    full_end = (
        quarter
        .end_time
        .normalize()
    )


    if (
        PRICE_WINDOW_MODE
        ==
        "FULL_QUARTER"
    ):

        end = full_end


    else:

        # Same intra-quarter cutoff
        end = (
            start
            +
            pd.Timedelta(
                days=DAY_OF_QUARTER
            )
        )


        end = min(
            end,
            full_end,
        )


    # Never use future dates
    if quarter == CURRENT_QUARTER:

        end = min(
            end,
            AS_OF,
        )


    return (
        start,
        end,
    )


def quarter_price_mean(
    quarter,
    column
):

    start, end = (
        price_window_for_quarter(
            quarter
        )
    )


    sample = prices_daily.loc[
        (
            prices_daily.index
            >=
            start
        )
        &
        (
            prices_daily.index
            <=
            end
        ),
        column,
    ]


    sample = (
        pd.to_numeric(
            sample,
            errors="coerce",
        )
        .dropna()
    )


    if sample.empty:

        return np.nan


    return float(
        sample.mean()
    )


# ============================================================
# 8. QUARTER PRICE TABLE
# ============================================================

eog_quarters = (
    base_structural[
        base_structural[
            "ticker"
        ]
        ==
        "EOG"
    ][
        "quarter"
    ]
    .sort_values()
    .unique()
)


price_rows = []


for q in eog_quarters:

    start, end = (
        price_window_for_quarter(
            q
        )
    )


    price_rows.append(
        {
            "quarter":
                q,

            "price_window_start":
                start,

            "price_window_end":
                end,

            "wti_price":
                quarter_price_mean(
                    q,
                    "wti",
                ),

            "propane_price_gal":
                quarter_price_mean(
                    q,
                    "propane",
                ),

            "henry_price":
                quarter_price_mean(
                    q,
                    "henry",
                ),
        }
    )


price_quarters = pd.DataFrame(
    price_rows
)


price_quarters[
    "propane_price_bbl"
] = (
    price_quarters[
        "propane_price_gal"
    ]
    *
    42.0
)


price_quarters.to_csv(
    lake_path(
        "energy_v3_3_price_quarters.csv"
    ),
    index=False,
)


print(
    "\n===== LATEST PRICE WINDOWS ====="
)


print(
    price_quarters
    .tail(8)
    .round(3)
    .to_string(
        index=False
    )
)


# ============================================================
# 9. LOOKUP HELPERS
# ============================================================

def dataframe_row_for_period(
    df,
    period_column,
    period
):

    rows = df[
        df[
            period_column
        ]
        ==
        period
    ]


    if rows.empty:

        return None


    return rows.iloc[
        -1
    ]


def actual_row(
    quarter
):

    return dataframe_row_for_period(
        eog_actual,
        "quarter",
        quarter,
    )


def guidance_row(
    quarter
):

    return dataframe_row_for_period(
        eog_guidance,
        "target_quarter",
        quarter,
    )


def price_row(
    quarter
):

    return dataframe_row_for_period(
        price_quarters,
        "quarter",
        quarter,
    )


# ============================================================
# 10. GUIDANCE COMPONENT RECONSTRUCTION
# ============================================================

def actual_components(
    quarter
):

    row = actual_row(
        quarter
    )


    if row is None:

        return None


    result = {

        "oil":
            numeric(
                row.get(
                    "oil_production"
                )
            ),

        "ngl":
            numeric(
                row.get(
                    "ngl_production"
                )
            ),

        "gas":
            numeric(
                row.get(
                    "gas_production"
                )
            ),

        "total":
            numeric(
                row.get(
                    "total_production"
                )
            ),

        "quality":
            numeric(
                row.get(
                    "data_quality_score"
                )
            ),
    }


    if pd.isna(
        result[
            "quality"
        ]
    ):

        result[
            "quality"
        ] = 1.0


    return result


def previous_actual_mix(
    quarter
):

    candidates = (
        eog_actual[
            eog_actual[
                "quarter"
            ]
            <
            quarter
        ]
        .sort_values(
            "quarter"
        )
    )


    if candidates.empty:

        return None


    row = candidates.iloc[
        -1
    ]


    oil = numeric(
        row.get(
            "oil_production"
        )
    )


    ngl = numeric(
        row.get(
            "ngl_production"
        )
    )


    gas = numeric(
        row.get(
            "gas_production"
        )
    )


    total = numeric(
        row.get(
            "total_production"
        )
    )


    if (
        pd.isna(oil)
        or
        pd.isna(ngl)
        or
        pd.isna(gas)
        or
        pd.isna(total)
        or
        total <= 0
    ):

        return None


    gas_boe = (
        gas
        /
        6.0
    )


    denominator = (
        oil
        +
        ngl
        +
        gas_boe
    )


    if denominator <= 0:

        return None


    return {

        "oil_share":
            oil
            /
            denominator,

        "ngl_share":
            ngl
            /
            denominator,

        "gas_boe_share":
            gas_boe
            /
            denominator,
    }


def projected_guidance_components(
    quarter
):

    row = guidance_row(
        quarter
    )


    if row is None:

        return None


    oil = numeric(
        row.get(
            "guidance_oil_production"
        )
    )


    ngl = numeric(
        row.get(
            "guidance_ngl_production"
        )
    )


    gas = numeric(
        row.get(
            "guidance_gas_production"
        )
    )


    total = numeric(
        row.get(
            "guidance_total_production"
        )
    )


    base_quality = numeric(
        row.get(
            "guidance_data_quality_score"
        )
    )


    if pd.isna(
        base_quality
    ):

        base_quality = 1.0


    components = {

        "oil":
            oil,

        "ngl":
            ngl,

        "gas":
            gas,

        "total":
            total,
    }


    missing = [
        key

        for key in [
            "oil",
            "ngl",
            "gas",
        ]

        if pd.isna(
            components[
                key
            ]
        )
    ]


    method = "EXACT_GUIDANCE"

    quality = min(
        float(
            base_quality
        ),
        GUIDANCE_EXACT_QUALITY,
    )


    # ========================================================
    # One missing component:
    # solve from total BOE.
    # ========================================================

    if (
        len(
            missing
        )
        ==
        1
        and
        pd.notna(
            total
        )
    ):

        missing_key = (
            missing[
                0
            ]
        )


        if (
            missing_key
            ==
            "oil"
            and
            pd.notna(ngl)
            and
            pd.notna(gas)
        ):

            oil = (
                total
                -
                ngl
                -
                gas / 6.0
            )


        elif (
            missing_key
            ==
            "ngl"
            and
            pd.notna(oil)
            and
            pd.notna(gas)
        ):

            ngl = (
                total
                -
                oil
                -
                gas / 6.0
            )


        elif (
            missing_key
            ==
            "gas"
            and
            pd.notna(oil)
            and
            pd.notna(ngl)
        ):

            gas = (
                (
                    total
                    -
                    oil
                    -
                    ngl
                )
                *
                6.0
            )


        method = (
            f"SOLVED_{missing_key.upper()}"
        )


        quality = min(
            quality,
            GUIDANCE_SOLVED_QUALITY,
        )


    # ========================================================
    # More than one missing:
    # previous actual BOE mix.
    # ========================================================

    elif (
        len(
            missing
        )
        >=
        2
        and
        pd.notna(
            total
        )
    ):

        mix = previous_actual_mix(
            quarter
        )


        if mix is not None:

            if pd.isna(
                oil
            ):

                oil = (
                    total
                    *
                    mix[
                        "oil_share"
                    ]
                )


            if pd.isna(
                ngl
            ):

                ngl = (
                    total
                    *
                    mix[
                        "ngl_share"
                    ]
                )


            if pd.isna(
                gas
            ):

                gas = (
                    total
                    *
                    mix[
                        "gas_boe_share"
                    ]
                    *
                    6.0
                )


            method = (
                "PREVIOUS_ACTUAL_MIX_IMPUTED"
            )


            quality = min(
                quality,
                GUIDANCE_MIX_IMPUTED_QUALITY,
            )


    # ========================================================
    # Reconstruct total if missing
    # ========================================================

    if (
        pd.isna(
            total
        )
        and
        pd.notna(
            oil
        )
        and
        pd.notna(
            ngl
        )
        and
        pd.notna(
            gas
        )
    ):

        total = (
            oil
            +
            ngl
            +
            gas / 6.0
        )


        method = (
            method
            +
            "_TOTAL_RECONSTRUCTED"
        )


        quality = min(
            quality,
            0.90,
        )


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
        or
        pd.isna(
            total
        )
        or
        oil <= 0
        or
        ngl < 0
        or
        gas <= 0
        or
        total <= 0
    ):

        return None


    return {

        "oil":
            float(
                oil
            ),

        "ngl":
            float(
                ngl
            ),

        "gas":
            float(
                gas
            ),

        "total":
            float(
                total
            ),

        "quality":
            float(
                quality
            ),

        "method":
            method,
    }


# ============================================================
# 11. ECONOMIC DRIVER
# ============================================================

def economic_driver(
    volumes,
    prices
):

    if (
        volumes is None
        or
        prices is None
    ):

        return None


    wti = numeric(
        prices.get(
            "wti_price"
        )
    )


    propane_gal = numeric(
        prices.get(
            "propane_price_gal"
        )
    )


    henry = numeric(
        prices.get(
            "henry_price"
        )
    )


    if (
        pd.isna(wti)
        or
        pd.isna(propane_gal)
        or
        pd.isna(henry)
        or
        wti <= 0
        or
        propane_gal <= 0
        or
        henry <= 0
    ):

        return None


    # --------------------------------------------------------
    # Common factor 1,000 cancels.
    #
    # Oil:
    # MBod * $/bbl
    #
    # NGL:
    # MBbld * $/gal * 42 gal/bbl
    #
    # Gas:
    # MMcfd * $/Mcf
    #
    # Since:
    # 1 MMcf = 1,000 Mcf
    # and
    # 1 MBbl = 1,000 bbl
    #
    # all three have same factor 1,000.
    # --------------------------------------------------------

    oil_driver = (
        volumes[
            "oil"
        ]
        *
        wti
    )


    ngl_driver = (
        volumes[
            "ngl"
        ]
        *
        propane_gal
        *
        42.0
    )


    gas_driver = (
        volumes[
            "gas"
        ]
        *
        henry
    )


    total_driver = (
        oil_driver
        +
        ngl_driver
        +
        gas_driver
    )


    return {

        "oil":
            float(
                oil_driver
            ),

        "ngl":
            float(
                ngl_driver
            ),

        "gas":
            float(
                gas_driver
            ),

        "total":
            float(
                total_driver
            ),
    }


# ============================================================
# 12. BUILD ONE COMPONENT OBSERVATION
# ============================================================

def component_structural_for_quarter(
    quarter
):

    prior_q = (
        quarter
        -
        4
    )


    current_volumes = (
        projected_guidance_components(
            quarter
        )
    )


    prior_volumes = (
        actual_components(
            prior_q
        )
    )


    current_prices_row = (
        price_row(
            quarter
        )
    )


    prior_prices_row = (
        price_row(
            prior_q
        )
    )


    if (
        current_volumes
        is None
        or
        prior_volumes
        is None
        or
        current_prices_row
        is None
        or
        prior_prices_row
        is None
    ):

        return None


    current_prices = {

        "wti_price":
            numeric(
                current_prices_row.get(
                    "wti_price"
                )
            ),

        "propane_price_gal":
            numeric(
                current_prices_row.get(
                    "propane_price_gal"
                )
            ),

        "henry_price":
            numeric(
                current_prices_row.get(
                    "henry_price"
                )
            ),
    }


    prior_prices = {

        "wti_price":
            numeric(
                prior_prices_row.get(
                    "wti_price"
                )
            ),

        "propane_price_gal":
            numeric(
                prior_prices_row.get(
                    "propane_price_gal"
                )
            ),

        "henry_price":
            numeric(
                prior_prices_row.get(
                    "henry_price"
                )
            ),
    }


    current_driver = (
        economic_driver(
            current_volumes,
            current_prices,
        )
    )


    prior_driver = (
        economic_driver(
            prior_volumes,
            prior_prices,
        )
    )


    if (
        current_driver is None
        or
        prior_driver is None
        or
        current_driver[
            "total"
        ]
        <= 0
        or
        prior_driver[
            "total"
        ]
        <= 0
    ):

        return None


    # ========================================================
    # Exact economic-driver growth
    # ========================================================

    component_structural_log = (
        log_ratio(
            current_driver[
                "total"
            ],
            prior_driver[
                "total"
            ],
        )
    )


    production_log = (
        log_ratio(
            current_volumes[
                "total"
            ],
            prior_volumes[
                "total"
            ],
        )
    )


    # ========================================================
    # Individual component growth
    # ========================================================

    oil_log = (
        log_ratio(
            current_driver[
                "oil"
            ],
            prior_driver[
                "oil"
            ],
        )
    )


    ngl_log = (
        log_ratio(
            current_driver[
                "ngl"
            ],
            prior_driver[
                "ngl"
            ],
        )
    )


    gas_log = (
        log_ratio(
            current_driver[
                "gas"
            ],
            prior_driver[
                "gas"
            ],
        )
    )


    # ========================================================
    # Prior-year economic revenue shares
    # ========================================================

    prior_total = (
        prior_driver[
            "total"
        ]
    )


    oil_share = (
        prior_driver[
            "oil"
        ]
        /
        prior_total
    )


    ngl_share = (
        prior_driver[
            "ngl"
        ]
        /
        prior_total
    )


    gas_share = (
        prior_driver[
            "gas"
        ]
        /
        prior_total
    )


    # Approximate decomposition
    oil_contribution = (
        oil_share
        *
        oil_log
    )


    ngl_contribution = (
        ngl_share
        *
        ngl_log
    )


    gas_contribution = (
        gas_share
        *
        gas_log
    )


    contribution_sum = (
        oil_contribution
        +
        ngl_contribution
        +
        gas_contribution
    )


    mix_residual = (
        component_structural_log
        -
        contribution_sum
    )


    # ========================================================
    # Pure price effect
    #
    # Keep prior-year volumes fixed,
    # replace only prices.
    # ========================================================

    prior_vol_current_price = (
        economic_driver(
            prior_volumes,
            current_prices,
        )
    )


    price_only_log = (
        log_ratio(
            prior_vol_current_price[
                "total"
            ],
            prior_driver[
                "total"
            ],
        )
    )


    # ========================================================
    # Quality
    # ========================================================

    prior_quality = float(
        prior_volumes.get(
            "quality",
            1.0,
        )
    )


    quality = min(
        float(
            current_volumes[
                "quality"
            ]
        ),
        prior_quality,
        PRICE_COMPLETE_QUALITY,
    )


    return {

        "quarter":
            quarter,

        "prior_quarter":
            prior_q,


        # -------------------------------------------
        # VOLUME
        # -------------------------------------------

        "current_oil":
            current_volumes[
                "oil"
            ],

        "current_ngl":
            current_volumes[
                "ngl"
            ],

        "current_gas":
            current_volumes[
                "gas"
            ],

        "current_total_boe":
            current_volumes[
                "total"
            ],


        "prior_oil":
            prior_volumes[
                "oil"
            ],

        "prior_ngl":
            prior_volumes[
                "ngl"
            ],

        "prior_gas":
            prior_volumes[
                "gas"
            ],

        "prior_total_boe":
            prior_volumes[
                "total"
            ],


        # -------------------------------------------
        # PRICE
        # -------------------------------------------

        "current_wti":
            current_prices[
                "wti_price"
            ],

        "current_propane_gal":
            current_prices[
                "propane_price_gal"
            ],

        "current_henry":
            current_prices[
                "henry_price"
            ],


        "prior_wti":
            prior_prices[
                "wti_price"
            ],

        "prior_propane_gal":
            prior_prices[
                "propane_price_gal"
            ],

        "prior_henry":
            prior_prices[
                "henry_price"
            ],


        # -------------------------------------------
        # DRIVER
        # -------------------------------------------

        "current_oil_driver":
            current_driver[
                "oil"
            ],

        "current_ngl_driver":
            current_driver[
                "ngl"
            ],

        "current_gas_driver":
            current_driver[
                "gas"
            ],

        "current_total_driver":
            current_driver[
                "total"
            ],


        "prior_oil_driver":
            prior_driver[
                "oil"
            ],

        "prior_ngl_driver":
            prior_driver[
                "ngl"
            ],

        "prior_gas_driver":
            prior_driver[
                "gas"
            ],

        "prior_total_driver":
            prior_driver[
                "total"
            ],


        # -------------------------------------------
        # GROWTH
        # -------------------------------------------

        "component_structural_log_yoy":
            component_structural_log,

        "component_structural_yoy_pct":
            log_to_normal_pct(
                component_structural_log
            ),

        "company_prod_yoy_proxy":
            production_log,

        "price_only_log_yoy":
            price_only_log,


        # -------------------------------------------
        # COMPONENTS
        # -------------------------------------------

        "oil_component_log_yoy":
            oil_log,

        "ngl_component_log_yoy":
            ngl_log,

        "gas_component_log_yoy":
            gas_log,


        "prior_oil_revenue_share":
            oil_share,

        "prior_ngl_revenue_share":
            ngl_share,

        "prior_gas_revenue_share":
            gas_share,


        "oil_contribution_log_points":
            oil_contribution,

        "ngl_contribution_log_points":
            ngl_contribution,

        "gas_contribution_log_points":
            gas_contribution,

        "component_mix_residual":
            mix_residual,


        # -------------------------------------------
        # SOURCE / QUALITY
        # -------------------------------------------

        "volume_method":
            current_volumes[
                "method"
            ],

        "production_yoy_source":
            "GUIDANCE_VS_ACTUAL",

        "source_quality_score":
            quality,

        "component_model_used":
            1.0,
    }


# ============================================================
# 13. BUILD EOG COMPONENT PANEL
# ============================================================

eog_base = (
    base_structural[
        base_structural[
            "ticker"
        ]
        ==
        "EOG"
    ]
    .sort_values(
        "quarter"
    )
    .reset_index(
        drop=True
    )
    .copy()
)


component_rows = []


for quarter in (
    eog_base[
        "quarter"
    ]
):

    result = (
        component_structural_for_quarter(
            quarter
        )
    )


    if result is not None:

        component_rows.append(
            result
        )


component_panel = pd.DataFrame(
    component_rows
)


component_panel.to_csv(
    lake_path(
        "energy_v3_3_eog_component_panel.csv"
    ),
    index=False,
)


print(
    "\n"
    + "=" * 95
)

print(
    "EOG COMPONENT PRICE × VOLUME MODEL"
)

print(
    "=" * 95
)


if not component_panel.empty:

    display_columns = [

        "quarter",

        "current_oil",

        "current_ngl",

        "current_gas",

        "current_total_boe",

        "current_wti",

        "current_propane_gal",

        "current_henry",

        "company_prod_yoy_proxy",

        "price_only_log_yoy",

        "component_structural_log_yoy",

        "source_quality_score",

        "volume_method",
    ]


    print(
        component_panel[
            display_columns
        ]
        .tail(12)
        .round(3)
        .to_string(
            index=False
        )
    )


# ============================================================
# 14. PATCH EOG STRUCTURAL MODEL
# ============================================================

component_mapping = {

    row[
        "quarter"
    ]:
        row

    for _, row in (
        component_panel.iterrows()
    )
}


patched_rows = []


for _, row in (
    eog_base.iterrows()
):

    quarter = row[
        "quarter"
    ]


    output_row = (
        row.copy()
    )


    component = (
        component_mapping.get(
            quarter
        )
    )


    # Keep old model for quarters where component
    # information isn't available.
    if component is None:

        output_row[
            "structural_model_type"
        ] = (
            "LEGACY_V3_2_7_FALLBACK"
        )


        output_row[
            "component_model_used"
        ] = 0.0


        patched_rows.append(
            output_row
        )

        continue


    component_log = float(
        np.clip(
            component[
                "component_structural_log_yoy"
            ],
            MIN_LOG_GROWTH,
            MAX_LOG_GROWTH,
        )
    )


    # Replace EOG structural model
    output_row[
        "structural_revenue_log_yoy"
    ] = component_log


    output_row[
        "structural_revenue_yoy_pct"
    ] = (
        log_to_normal_pct(
            component_log
        )
    )


    output_row[
        "company_prod_yoy_proxy"
    ] = component[
        "company_prod_yoy_proxy"
    ]


    output_row[
        "price_mix_yoy"
    ] = component[
        "price_only_log_yoy"
    ]


    output_row[
        "production_yoy_source"
    ] = component[
        "production_yoy_source"
    ]


    output_row[
        "source_quality_score"
    ] = component[
        "source_quality_score"
    ]


    output_row[
        "has_company_prod"
    ] = 1.0


    output_row[
        "has_guidance"
    ] = 1.0


    output_row[
        "structural_model_type"
    ] = (
        "COMPONENT_PRICE_X_VOLUME"
    )


    output_row[
        "component_model_used"
    ] = 1.0


    # ========================================================
    # COMPONENT DIAGNOSTICS
    # ========================================================

    diagnostic_columns = [

        "current_oil",

        "current_ngl",

        "current_gas",

        "current_total_boe",

        "prior_oil",

        "prior_ngl",

        "prior_gas",

        "prior_total_boe",

        "current_wti",

        "current_propane_gal",

        "current_henry",

        "prior_wti",

        "prior_propane_gal",

        "prior_henry",

        "component_structural_log_yoy",

        "component_structural_yoy_pct",

        "price_only_log_yoy",

        "oil_component_log_yoy",

        "ngl_component_log_yoy",

        "gas_component_log_yoy",

        "prior_oil_revenue_share",

        "prior_ngl_revenue_share",

        "prior_gas_revenue_share",

        "oil_contribution_log_points",

        "ngl_contribution_log_points",

        "gas_contribution_log_points",

        "component_mix_residual",

        "volume_method",
    ]


    for column in (
        diagnostic_columns
    ):

        output_row[
            column
        ] = component.get(
            column,
            np.nan,
        )


    patched_rows.append(
        output_row
    )


patched_eog = pd.DataFrame(
    patched_rows
)


# ============================================================
# 15. COMBINE ALL COMPANIES
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


if (
    "structural_model_type"
    not in non_eog.columns
):

    non_eog[
        "structural_model_type"
    ] = (
        "V3_2_7_LEGACY"
    )


if (
    "component_model_used"
    not in non_eog.columns
):

    non_eog[
        "component_model_used"
    ] = 0.0


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
        "energy_v3_3_structural_panel.csv"
    ),
    index=False,
)


# ============================================================
# 16. MODEL SOURCE SUMMARY
# ============================================================

source_summary = (
    structural_panel
    .groupby(
        [
            "ticker",
            "structural_model_type",
            "production_yoy_source",
        ]
    )
    .agg(
        observations=(
            "ticker",
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
        "energy_v3_3_source_summary.csv"
    ),
    index=False,
)


print(
    "\n"
    + "=" * 95
)

print(
    "STRUCTURAL SOURCE SUMMARY"
)

print(
    "=" * 95
)


print(
    source_summary
    .round(3)
    .to_string(
        index=False
    )
)


# ============================================================
# 17. VALIDATION ALIGNMENT
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

            "structural_model_type",

            "component_model_used",
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
    v21_validation
    .merge(
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
# 18. BLEND HELPERS
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

    quality = numeric(
        row[
            "source_quality_score"
        ]
    )


    if pd.isna(
        quality
    ):

        quality = 0.35


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
# 19. WALK-FORWARD VALIDATION
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

        row = (
            company_df.iloc[
                i
            ]
        )


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

                "structural_model_type":
                    row[
                        "structural_model_type"
                    ],

                "component_model_used":
                    row[
                        "component_model_used"
                    ],
            }
        )


walk_validation = pd.DataFrame(
    walk_rows
)


# ============================================================
# 20. METRICS
# ============================================================

metric_rows = []


print(
    "\n"
    + "=" * 95
)

print(
    "V3.3 WALK-FORWARD VALIDATION"
)

print(
    "=" * 95
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


            "V3_3_MAE_log_points":
                mae(
                    group[
                        "actual_log_yoy"
                    ],
                    group[
                        "blend_log_yoy"
                    ],
                ),


            "V3_3_MAE_yoy_pct_points":
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


overall_structural_log = mae(
    walk_validation[
        "actual_log_yoy"
    ],
    walk_validation[
        "structural_log_yoy"
    ],
)


overall_structural_pct = (
    mae_yoy_pct_points(
        walk_validation[
            "actual_log_yoy"
        ],
        walk_validation[
            "structural_log_yoy"
        ],
    )
)


overall_v33_log = mae(
    walk_validation[
        "actual_log_yoy"
    ],
    walk_validation[
        "blend_log_yoy"
    ],
)


overall_v33_pct = (
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
    f"{overall_structural_log:.2f} log-points"
)

print(
    f"V3.3       : "
    f"{overall_v33_log:.2f} log-points"
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
    f"{overall_structural_pct:.2f} %p"
)

print(
    f"V3.3       : "
    f"{overall_v33_pct:.2f} %p"
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
        "energy_v3_3_validation.csv"
    ),
    index=False,
)


metrics.to_csv(
    lake_path(
        "energy_v3_3_metrics.csv"
    )
)


# ============================================================
# 21. EOG COMPONENT-ONLY VALIDATION
# ============================================================

eog_component_validation = (
    walk_validation[
        (
            walk_validation[
                "ticker"
            ]
            ==
            "EOG"
        )
        &
        (
            walk_validation[
                "component_model_used"
            ]
            >
            0.5
        )
    ]
    .copy()
)


print(
    "\n"
    + "=" * 95
)

print(
    "EOG COMPONENT MODEL VALIDATION ONLY"
)

print(
    "=" * 95
)


if not eog_component_validation.empty:

    component_mae_log = mae(
        eog_component_validation[
            "actual_log_yoy"
        ],
        eog_component_validation[
            "structural_log_yoy"
        ],
    )


    component_mae_pct = (
        mae_yoy_pct_points(
            eog_component_validation[
                "actual_log_yoy"
            ],
            eog_component_validation[
                "structural_log_yoy"
            ],
        )
    )


    print(
        "Observations :",
        len(
            eog_component_validation
        )
    )


    print(
        f"Structural MAE : "
        f"{component_mae_log:.2f} log-points"
    )


    print(
        f"Structural MAE : "
        f"{component_mae_pct:.2f} %p"
    )


# ============================================================
# 22. FINAL BASE WEIGHTS
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
        "energy_v3_3_blend_weights.csv"
    )
)


# ============================================================
# 23. CURRENT STRUCTURAL NOWCAST
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
        .sort_values(
            "quarter"
        )
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


    last_actual_q = (
        actual_revenue[
            "quarter"
        ]
        .max()
    )


    target_q = (
        last_actual_q
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
                log_to_normal_pct(
                    row[
                        "structural_revenue_log_yoy"
                    ]
                ),


            "price_effect_log_yoy":
                row.get(
                    "price_mix_yoy",
                    np.nan,
                ),


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

            "structural_model_type":
                row[
                    "structural_model_type"
                ],

            "component_model_used":
                row[
                    "component_model_used"
                ],


            "guidance_total_production":
                row.get(
                    "guidance_total_production",
                    np.nan,
                ),


            "oil_contribution_log_points":
                row.get(
                    "oil_contribution_log_points",
                    np.nan,
                ),

            "ngl_contribution_log_points":
                row.get(
                    "ngl_contribution_log_points",
                    np.nan,
                ),

            "gas_contribution_log_points":
                row.get(
                    "gas_contribution_log_points",
                    np.nan,
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
# 24. MERGE V2.1 CURRENT
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
    structural_nowcast
    .merge(
        v21_nowcast,
        on=[
            "ticker",
            "nowcast_quarter",
        ],
        how="inner",
    )
)


# ============================================================
# 25. CURRENT WEIGHTS
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
# 26. FINAL PREDICTION
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
# 27. REVENUE LEVEL
# ============================================================

revenue_predictions = []


for _, row in (
    current.iterrows()
):

    ticker = (
        row[
            "ticker"
        ]
    )


    target_q = (
        row[
            "nowcast_quarter"
        ]
    )


    base_q = (
        target_q
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
                ticker
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
] = (
    revenue_predictions
)


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
# 28. CONFIDENCE
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
# 29. FINAL OUTPUT
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

    "structural_model_type",


    "company_prod_yoy_proxy",

    "price_effect_log_yoy",

    "production_yoy_source",


    "oil_contribution_log_points",

    "ngl_contribution_log_points",

    "gas_contribution_log_points",


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
    + "=" * 95
)

print(
    "🚀 ENERGY REVENUE V3.3 NOWCAST"
)

print(
    "=" * 95
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
        "energy_v3_3_nowcast.csv"
    ),
    index=False,
)


# ============================================================
# 30. EOG CURRENT DECOMPOSITION
# ============================================================

eog_current = (
    output[
        output[
            "ticker"
        ]
        ==
        "EOG"
    ]
)


print(
    "\n"
    + "=" * 95
)

print(
    "EOG V3.3 COMPONENT DECOMPOSITION"
)

print(
    "=" * 95
)


if not eog_current.empty:

    row = (
        eog_current.iloc[
            0
        ]
    )


    print(
        f"Oil contribution : "
        f"{row['oil_contribution_log_points']:.2f} log-points"
    )


    print(
        f"NGL contribution : "
        f"{row['ngl_contribution_log_points']:.2f} log-points"
    )


    print(
        f"Gas contribution : "
        f"{row['gas_contribution_log_points']:.2f} log-points"
    )


    print(
        f"Production growth: "
        f"{row['company_prod_yoy_proxy']:.2f} log-points"
    )


    print(
        f"Structural       : "
        f"{row['structural_log_yoy']:.2f} log-points"
    )


    print(
        f"V2.1             : "
        f"{row['v21_log_yoy']:.2f} log-points"
    )


    print(
        f"Final            : "
        f"{row['predicted_revenue_log_yoy']:.2f} log-points"
    )


    print(
        f"Final Revenue    : "
        f"${row['predicted_revenue_B']:.2f}B"
    )


# ============================================================
# 31. V3.2.7 COMPARISON
# ============================================================

OLD_METRICS_FILE = lake_path(
    "energy_v3_2_7_metrics.csv"
)


if OLD_METRICS_FILE.exists():

    old_metrics = pd.read_csv(
        OLD_METRICS_FILE,
        index_col=0,
    )


    print(
        "\n"
        + "=" * 95
    )

    print(
        "V3.2.7 vs V3.3"
    )

    print(
        "=" * 95
    )


    comparison = pd.DataFrame(
        index=metrics.index
    )


    if (
        "V3_2_7_MAE_log_points"
        in old_metrics.columns
    ):

        comparison[
            "V3_2_7_log_MAE"
        ] = (
            old_metrics[
                "V3_2_7_MAE_log_points"
            ]
        )


        comparison[
            "V3_3_log_MAE"
        ] = (
            metrics[
                "V3_3_MAE_log_points"
            ]
        )


        comparison[
            "log_improvement"
        ] = (
            comparison[
                "V3_2_7_log_MAE"
            ]
            -
            comparison[
                "V3_3_log_MAE"
            ]
        )


    if (
        "V3_2_7_MAE_yoy_pct_points"
        in old_metrics.columns
    ):

        comparison[
            "V3_2_7_pct_MAE"
        ] = (
            old_metrics[
                "V3_2_7_MAE_yoy_pct_points"
            ]
        )


        comparison[
            "V3_3_pct_MAE"
        ] = (
            metrics[
                "V3_3_MAE_yoy_pct_points"
            ]
        )


        comparison[
            "pct_improvement"
        ] = (
            comparison[
                "V3_2_7_pct_MAE"
            ]
            -
            comparison[
                "V3_3_pct_MAE"
            ]
        )


    print(
        comparison.round(
            2
        )
    )


# ============================================================
# 32. METADATA
# ============================================================

metadata = {

    "version":
        "3.3",

    "as_of_date":
        str(
            AS_OF.date()
        ),

    "price_window_mode":
        PRICE_WINDOW_MODE,

    "day_of_quarter":
        DAY_OF_QUARTER,

    "eia_series":
        EIA_SERIES,

    "eog_component_model":

        (
            "Oil volume * WTI + "
            "NGL volume * Mont Belvieu Propane * 42 + "
            "Gas volume * Henry Hub"
        ),

    "current_volume_source":
        "Target-quarter company guidance",

    "comparison_volume_source":
        "Prior-year actual production",

    "ngl_price_proxy":
        "Mont Belvieu TX Propane Spot Price FOB",

    "non_eog_model":
        "V3.2.7 structural model",

    "metrics": [

        "MAE_log_points",

        "MAE_yoy_pct_points",
    ],
}


with open(
    lake_path(
        "energy_v3_3_metadata.json"
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
# 33. DONE
# ============================================================

print(
    "\n"
    + "=" * 95
)

print(
    "DONE"
)

print(
    "=" * 95
)


print(
    "\nMain outputs:"
)


for filename in [

    "energy_v3_3_eia_prices_daily.csv",

    "energy_v3_3_price_quarters.csv",

    "energy_v3_3_eog_component_panel.csv",

    "energy_v3_3_structural_panel.csv",

    "energy_v3_3_source_summary.csv",

    "energy_v3_3_validation.csv",

    "energy_v3_3_metrics.csv",

    "energy_v3_3_blend_weights.csv",

    "energy_v3_3_nowcast.csv",

    "energy_v3_3_metadata.json",

]:

    print(
        " -",
        lake_path(
            filename
        )
    )
