# ============================================================
# ENERGY REVENUE NOWCAST V3.2.2
#
# INPUT
# ------------------------------------------------------------
# V2.1:
#   ./data-lake/energy_v2_1_panel.csv
#   ./data-lake/energy_v2_1_validation.csv
#   ./data-lake/energy_v2_1_nowcast.csv
#
# V3.2.1 KPI CACHE:
#   ./data-lake/energy_v3_2_1_actual_COP.csv
#   ./data-lake/energy_v3_2_1_guidance_COP.csv
#   ...
#
#
# V3.2.2 핵심
# ------------------------------------------------------------
# 1. Production Quality Control
#
#    - Total/Oil ratio sanity check
#    - QoQ production jump sanity check
#    - M&A event quarter + next quarter exception
#
# 2. Production growth source tagging
#
#    GUIDANCE_VS_ACTUAL
#    GUIDANCE_VS_GUIDANCE
#    ACTUAL_VS_ACTUAL
#    INDUSTRY_FALLBACK
#
# 3. Source quality score
#
#    GUIDANCE_VS_ACTUAL     = 1.00
#    ACTUAL_VS_ACTUAL       = 0.90
#    GUIDANCE_VS_GUIDANCE   = 0.75
#    INDUSTRY_FALLBACK      = 0.35
#
# 4. Structural blend weight
#
#    effective structural weight
#        =
#        historical optimal weight
#        *
#        source quality score
#
# 5. Structural Guardrail
#
#    historical Structural MAE >= V2.1 MAE
#        -> Structural weight = 0
#
# 6. Confidence 개선
#
#    Structural disabled
#        -> LOW
#
#    High-quality production + low model spread
#        -> HIGH
#
# ============================================================


import os
import json
import warnings

from pathlib import Path

import numpy as np
import pandas as pd


warnings.filterwarnings("ignore")


# ============================================================
# 0. CONFIG
# ============================================================

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


# ------------------------------------------------------------
# Blend weight grid
# ------------------------------------------------------------

BLEND_WEIGHTS = np.round(
    np.arange(
        0.0,
        1.0001,
        0.05
    ),
    2
)


MIN_BLEND_HISTORY = int(
    os.getenv(
        "MIN_BLEND_HISTORY",
        "3"
    )
)


# ============================================================
# PRODUCTION QC CONFIG
# ============================================================

# ------------------------------------------------------------
# M&A가 없는 일반 회사에서
#
# quarter-to-quarter production이
# log 기준 ±35% 이상 갑자기 바뀌면 의심
# ------------------------------------------------------------

MAX_ORGANIC_QOQ_LOG_GROWTH = float(
    os.getenv(
        "MAX_ORGANIC_QOQ_LOG_GROWTH",
        "35"
    )
)


# 여러 quarter가 비어 있을 때
# 허용 threshold의 최대값
MAX_QOQ_THRESHOLD = float(
    os.getenv(
        "MAX_QOQ_THRESHOLD",
        "55"
    )
)


# ------------------------------------------------------------
# Total BOE / Oil BOE sanity
#
# 보통 E&P 회사에서:
#
# total BOE/d > oil bbl/d
#
# 너무 비슷하거나 5배 이상이면
# 잘못된 row 선택 가능성
# ------------------------------------------------------------

TOTAL_OIL_RATIO_MIN = float(
    os.getenv(
        "TOTAL_OIL_RATIO_MIN",
        "1.15"
    )
)


TOTAL_OIL_RATIO_MAX = float(
    os.getenv(
        "TOTAL_OIL_RATIO_MAX",
        "5.0"
    )
)


# ============================================================
# SOURCE QUALITY
# ============================================================

SOURCE_QUALITY = {

    "GUIDANCE_VS_ACTUAL":
        1.00,

    "ACTUAL_VS_ACTUAL":
        0.90,

    "GUIDANCE_VS_GUIDANCE":
        0.75,

    "INDUSTRY_FALLBACK":
        0.35,
}


# industry fallback만 있을 때
# Structural weight 상한
NO_COMPANY_PROD_MAX_WEIGHT = float(
    os.getenv(
        "NO_COMPANY_PROD_MAX_WEIGHT",
        "0.25"
    )
)


MIN_LOG_GROWTH = -100.0
MAX_LOG_GROWTH = 150.0


# ============================================================
# 1. PATH HELPERS
# ============================================================

DATA_LAKE_DIR.mkdir(
    parents=True,
    exist_ok=True
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
    "ENERGY REVENUE NOWCAST V3.2.2"
)

print(
    "=" * 90
)

print(
    "TICKERS   :",
    TICKERS
)

print(
    "DATA LAKE :",
    DATA_LAKE_DIR.resolve()
)

print(
    "QoQ LIMIT :",
    MAX_ORGANIC_QOQ_LOG_GROWTH,
    "log pp"
)

print(
    "TOTAL/OIL :",
    TOTAL_OIL_RATIO_MIN,
    "~",
    TOTAL_OIL_RATIO_MAX
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


for ticker in TICKERS:

    actual_path = lake_path(
        f"energy_v3_2_1_actual_{ticker}.csv"
    )

    guidance_path = lake_path(
        f"energy_v3_2_1_guidance_{ticker}.csv"
    )

    if not actual_path.exists():

        raise FileNotFoundError(
            f"{actual_path} 없음.\n"
            "먼저 V3.2.1을 한 번 실행해줘."
        )

    if not guidance_path.exists():

        raise FileNotFoundError(
            f"{guidance_path} 없음.\n"
            "먼저 V3.2.1을 한 번 실행해줘."
        )


# ============================================================
# 3. HELPERS
# ============================================================

def numeric_series(
    series
):

    return pd.to_numeric(
        series,
        errors="coerce"
    )


def log_growth(
    series,
    periods=4
):

    series = numeric_series(
        series
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


def log_ratio_growth(
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
        * 100
    )


def log_to_normal_pct(
    value
):

    if isinstance(
        value,
        pd.Series
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
    predicted
):

    actual = np.asarray(
        actual,
        dtype=float
    )

    predicted = np.asarray(
        predicted,
        dtype=float
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


def quarter_gap(
    newer,
    older
):

    return (
        newer.ordinal
        -
        older.ordinal
    )


# ============================================================
# 4. LOAD V2.1
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
    freq="Q"
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


# ------------------------------------------------------------
# M&A fields fallback
# ------------------------------------------------------------

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
    errors="coerce"
).fillna(0)


panel_v21[
    "ma_window"
] = pd.to_numeric(
    panel_v21[
        "ma_window"
    ],
    errors="coerce"
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
    freq="Q"
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
    freq="Q"
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
# 5. LOAD V3.2.1 KPI CACHE
# ============================================================

def read_period_csv(
    path
):

    try:

        df = pd.read_csv(
            path,
            index_col=0
        )

    except pd.errors.EmptyDataError:

        return pd.DataFrame()


    if df.empty:

        return df


    df.index = pd.PeriodIndex(
        df.index.astype(str),
        freq="Q"
    )


    return df.sort_index()


actual_kpis = {}
guidance_kpis = {}


for ticker in TICKERS:

    actual_kpis[
        ticker
    ] = read_period_csv(
        lake_path(
            f"energy_v3_2_1_actual_{ticker}.csv"
        )
    )


    guidance_kpis[
        ticker
    ] = read_period_csv(
        lake_path(
            f"energy_v3_2_1_guidance_{ticker}.csv"
        )
    )


# ============================================================
# 6. PRODUCTION QC
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
        .copy()
    )


    df.index = pd.PeriodIndex(
        df["quarter"].astype(str),
        freq="Q"
    )

    # 중요:
    # column "quarter"와 index level 이름 충돌 방지
    df.index.name = None


    # ========================================================
    # Raw actual
    # ========================================================

    if (
        not actual.empty
        and
        "total_production"
        in actual.columns
    ):

        df[
            "total_production_raw"
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
            "oil_production_raw"
        ] = np.nan


    df[
        "total_production_raw"
    ] = pd.to_numeric(
        df[
            "total_production_raw"
        ],
        errors="coerce"
    )


    df[
        "oil_production_raw"
    ] = pd.to_numeric(
        df[
            "oil_production_raw"
        ],
        errors="coerce"
    )


    # ========================================================
    # M&A jump allowance
    #
    # 이벤트 분기
    # +
    # 바로 다음 분기
    #
    # ma_window 전체 5분기를 허용하지 않는 이유:
    #
    # EOG처럼 M&A 몇 분기 뒤에
    # definition break가 생기는 걸 막기 위해서
    # ========================================================

    event = (
        df[
            "ma_event"
        ]
        .fillna(0)
    )


    df[
        "mna_jump_allow"
    ] = (
        (
            event > 0
        )

        |

        (
            event
            .shift(1)
            .fillna(0)
            > 0
        )
    ).astype(float)


    # ========================================================
    # STEP 1
    #
    # TOTAL / OIL RATIO CHECK
    # ========================================================

    df[
        "total_oil_ratio"
    ] = (
        df[
            "total_production_raw"
        ]
        /
        df[
            "oil_production_raw"
        ]
    )


    ratio_bad = (
        df[
            "total_oil_ratio"
        ]
        .notna()

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


    # ========================================================
    # 초기 clean candidate
    # ========================================================

    df[
        "total_production_clean"
    ] = (
        df[
            "total_production_raw"
        ]
    )


    df[
        "oil_production_clean"
    ] = (
        df[
            "oil_production_raw"
        ]
    )


    df[
        "production_qc_flag"
    ] = "OK"


    df.loc[
        df[
            "total_production_raw"
        ].isna(),
        "production_qc_flag"
    ] = "MISSING"


    # total/oil 둘 다 있을 때만 ratio 적용
    df.loc[
        ratio_bad,
        "total_production_clean"
    ] = np.nan


    df.loc[
        ratio_bad,
        "production_qc_flag"
    ] = "REJECT_TOTAL_OIL_RATIO"


    # ========================================================
    # STEP 2
    #
    # Sequential QoQ jump filter
    #
    # 직전 "accepted" production과 비교
    # ========================================================

    accepted_quarter = None
    accepted_value = None


    raw_qoq_log = pd.Series(
        np.nan,
        index=df.index,
        dtype=float
    )


    allowed_threshold = pd.Series(
        np.nan,
        index=df.index,
        dtype=float
    )


    for q in df.index:

        current = df.loc[
            q,
            "total_production_clean"
        ]


        if (
            pd.isna(current)
            or
            current <= 0
        ):

            continue


        if (
            accepted_value is None
            or
            accepted_quarter is None
        ):

            accepted_value = float(
                current
            )

            accepted_quarter = q

            continue


        gap = max(
            1,
            quarter_gap(
                q,
                accepted_quarter
            )
        )


        growth = log_ratio_growth(
            current,
            accepted_value
        )


        threshold = min(
            (
                MAX_ORGANIC_QOQ_LOG_GROWTH
                *
                np.sqrt(gap)
            ),
            MAX_QOQ_THRESHOLD
        )


        raw_qoq_log.loc[
            q
        ] = growth


        allowed_threshold.loc[
            q
        ] = threshold


        mna_allowed = (
            df.loc[
                q,
                "mna_jump_allow"
            ]
            >= 0.5
        )


        if (
            pd.notna(growth)
            and
            abs(growth)
            >
            threshold
            and
            not mna_allowed
        ):

            df.loc[
                q,
                "total_production_clean"
            ] = np.nan


            df.loc[
                q,
                "production_qc_flag"
            ] = "REJECT_QOQ_JUMP"


            # accepted value를 업데이트하지 않음
            continue


        # accepted
        accepted_value = float(
            current
        )

        accepted_quarter = q


    df[
        "production_qoq_log_raw"
    ] = raw_qoq_log


    df[
        "production_qoq_threshold"
    ] = allowed_threshold


    # ========================================================
    # Oil도 Total이 reject된 분기는 같이 reject
    #
    # product mix contamination 방지
    # ========================================================

    total_rejected = (
        df[
            "production_qc_flag"
        ]
        .str.startswith(
            "REJECT",
            na=False
        )
    )


    df.loc[
        total_rejected,
        "oil_production_clean"
    ] = np.nan


    # ========================================================
    # Raw vs clean production YoY
    # ========================================================

    df[
        "total_prod_yoy_raw"
    ] = log_growth(
        df[
            "total_production_raw"
        ],
        4
    )


    df[
        "total_prod_yoy_clean"
    ] = log_growth(
        df[
            "total_production_clean"
        ],
        4
    )


    # ========================================================
    # SAVE QC REPORT
    # ========================================================

    qc_columns = [

        "ticker",
        "quarter",

        "ma_event",
        "ma_window",
        "mna_jump_allow",

        "total_production_raw",
        "oil_production_raw",

        "total_oil_ratio",

        "total_production_clean",
        "oil_production_clean",

        "production_qoq_log_raw",
        "production_qoq_threshold",

        "total_prod_yoy_raw",
        "total_prod_yoy_clean",

        "production_qc_flag",
    ]


    qc = (
        df.reset_index(
            drop=True
        )[
            qc_columns
        ]
    )


    qc.to_csv(
        lake_path(
            f"energy_v3_2_2_production_qc_{ticker}.csv"
        ),
        index=False
    )


    # ========================================================
    # Console diagnostics
    # ========================================================

    rejected = (
        df[
            df[
                "production_qc_flag"
            ]
            .str.startswith(
                "REJECT",
                na=False
            )
        ]
    )


    raw_count = int(
        df[
            "total_production_raw"
        ]
        .notna()
        .sum()
    )


    clean_count = int(
        df[
            "total_production_clean"
        ]
        .notna()
        .sum()
    )


    print(
        f"\n{ticker} PRODUCTION QC"
    )

    print(
        f"  raw total production   : "
        f"{raw_count}"
    )

    print(
        f"  clean total production : "
        f"{clean_count}"
    )

    print(
        f"  rejected               : "
        f"{len(rejected)}"
    )


    if not rejected.empty:

        print(
            rejected[
                [
                    "total_production_raw",
                    "oil_production_raw",
                    "total_oil_ratio",
                    "production_qoq_log_raw",
                    "ma_event",
                    "production_qc_flag",
                ]
            ]
            .round(2)
            .to_string()
        )


    return df


# ============================================================
# 7. BUILD QC DATA
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
    ] = production_quality_control(
        ticker,
        company_panel,
        actual_kpis[
            ticker
        ],
    )


# ============================================================
# 8. STRUCTURAL FEATURE ENGINEERING
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


def build_structural_company(
    ticker,
    qc_df,
    guidance,
):

    # ========================================================
    # IMPORTANT
    #
    # qc_df에는
    #
    # column: quarter
    # index  : quarter
    #
    # 가 동시에 존재할 수 있음.
    #
    # Pandas sort_values("quarter")가
    # 어느 quarter인지 판단 못 하는 문제 방지.
    # ========================================================

    df = qc_df.copy()


    # index 이름이 quarter라면 제거
    if df.index.name == "quarter":

        df.index.name = None


    # column quarter를 기준으로 정렬
    df = (
        df
        .sort_values(
            "quarter"
        )
        .copy()
    )


    # 모델 계산용 PeriodIndex 생성
    df.index = pd.PeriodIndex(
        df[
            "quarter"
        ].astype(str),
        freq="Q"
    )


    # 다시 이름 충돌 방지
    df.index.name = None


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


    if (
        not guidance.empty
        and
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

    else:

        df[
            "guidance_oil_production"
        ] = np.nan


    df[
        "guidance_total_production"
    ] = pd.to_numeric(
        df[
            "guidance_total_production"
        ],
        errors="coerce"
    )


    # ========================================================
    # Clean actual production YoY
    # ========================================================

    df[
        "total_prod_yoy"
    ] = log_growth(
        df[
            "total_production_clean"
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
    # GUIDANCE YOY
    #
    # A. Guidance vs prior-year clean actual
    #
    # B. Actual missing이면
    #    Guidance vs prior-year guidance
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


    valid_ga = (
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
        valid_ga,
        "guidance_vs_actual_yoy"
    ] = (
        np.log(
            df.loc[
                valid_ga,
                "guidance_total_production"
            ]
            /
            prior_actual.loc[
                valid_ga
            ]
        )
        * 100
    )


    valid_gg = (
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
        valid_gg,
        "guidance_vs_guidance_yoy"
    ] = (
        np.log(
            df.loc[
                valid_gg,
                "guidance_total_production"
            ]
            /
            prior_guidance.loc[
                valid_gg
            ]
        )
        * 100
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
    # Production proxy + SOURCE
    # ========================================================

    prod_proxy = []

    prod_source = []

    quality_scores = []


    for q, row in (
        df.iterrows()
    ):

        # ----------------------------------------------------
        # 1. Guidance vs ACTUAL
        # ----------------------------------------------------

        if pd.notna(
            row[
                "guidance_vs_actual_yoy"
            ]
        ):

            value = row[
                "guidance_vs_actual_yoy"
            ]

            source = (
                "GUIDANCE_VS_ACTUAL"
            )


        # ----------------------------------------------------
        # 2. Previous-quarter
        # ACTUAL vs ACTUAL
        # ----------------------------------------------------

        elif pd.notna(
            row[
                "total_prod_yoy_l1"
            ]
        ):

            value = row[
                "total_prod_yoy_l1"
            ]

            source = (
                "ACTUAL_VS_ACTUAL"
            )


        # ----------------------------------------------------
        # 3. Guidance vs Guidance
        # ----------------------------------------------------

        elif pd.notna(
            row[
                "guidance_vs_guidance_yoy"
            ]
        ):

            value = row[
                "guidance_vs_guidance_yoy"
            ]

            source = (
                "GUIDANCE_VS_GUIDANCE"
            )


        # ----------------------------------------------------
        # 4. Industry
        # ----------------------------------------------------

        else:

            value = (
                industry_prod_proxy.loc[
                    q
                ]
            )

            source = (
                "INDUSTRY_FALLBACK"
            )


        if pd.notna(value):

            value = float(
                np.clip(
                    value,
                    -60,
                    120
                )
            )


        prod_proxy.append(
            value
        )

        prod_source.append(
            source
        )

        quality_scores.append(
            SOURCE_QUALITY[
                source
            ]
        )


    df[
        "company_prod_yoy_proxy"
    ] = prod_proxy


    df[
        "production_yoy_source"
    ] = prod_source


    df[
        "source_quality_score"
    ] = quality_scores


    # ========================================================
    # Raw guidance exists?
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


    # ========================================================
    # Oil share
    #
    # CLEAN values only
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
            np.nan
        )
        .clip(
            0.10,
            1.00
        )
    )


    median_share = (
        oil_share
        .median(
            skipna=True
        )
    )


    if pd.isna(
        median_share
    ):

        median_share = (
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
            median_share
        )
        .clip(
            0.10,
            1.00
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
    # Structural revenue LOG YoY
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
            MAX_LOG_GROWTH
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
# 9. BUILD STRUCTURAL PANEL
# ============================================================

structural_frames = []


for ticker in TICKERS:

    company = build_structural_company(

        ticker,

        qc_companies[
            ticker
        ],

        guidance_kpis[
            ticker
        ],
    )


    structural_frames.append(
        company
    )


structural_panel = pd.concat(
    structural_frames,
    axis=0
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
        "energy_v3_2_2_structural_panel.csv"
    ),
    index=False
)


# ============================================================
# 10. SOURCE QUALITY SUMMARY
# ============================================================

source_quality_summary = (
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
            "size"
        ),

        avg_quality=(
            "source_quality_score",
            "mean"
        ),

    )
    .reset_index()
)


source_quality_summary.to_csv(
    lake_path(
        "energy_v3_2_2_source_quality_summary.csv"
    ),
    index=False
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
    source_quality_summary
    .round(2)
    .to_string(
        index=False
    )
)


# ============================================================
# 11. STRUCTURAL VALIDATION FRAME
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

            "guidance_total_production",

            "guidance_vs_actual_yoy",

            "guidance_vs_guidance_yoy",

            "total_prod_yoy_l1",

            "has_company_prod",

            "has_guidance",

            "production_qc_flag",
        ]
    ]
    .copy()
)


structural_validation = (
    structural_validation.rename(
        columns={
            "revenue_yoy":
                "actual_log_yoy"
        }
    )
)


# ============================================================
# 12. MERGE V2.1 VALIDATION
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
# 13. BEST HISTORICAL WEIGHT
# ============================================================

def best_weight(
    history
):

    if history.empty:

        return 0.0


    best_w = 0.0
    best_score = np.inf


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


        score = mae(
            history[
                "actual_log_yoy"
            ],
            prediction
        )


        if score < best_score:

            best_score = score
            best_w = float(
                weight
            )


    return best_w


# ============================================================
# 14. HISTORICAL GUARDRAIL
# ============================================================

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
        ]
    )


    v21_error = mae(
        history[
            "actual_log_yoy"
        ],
        history[
            "v21_log_yoy"
        ]
    )


    # Structural이 더 나쁘면 아예 OFF
    if (
        structural_error
        >=
        v21_error
    ):

        return 0.0


    return best_weight(
        history
    )


# ============================================================
# 15. QUALITY-ADJUSTED WEIGHT
# ============================================================

def quality_adjusted_weight(
    base_weight,
    row
):

    quality = float(
        row[
            "source_quality_score"
        ]
    )


    weight = (
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

        weight = min(
            weight,
            NO_COMPANY_PROD_MAX_WEIGHT
        )


    return float(
        np.clip(
            weight,
            0,
            1
        )
    )


# ============================================================
# 16. WALK-FORWARD VALIDATION
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
                row
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
                MAX_LOG_GROWTH
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

                "structural_log_yoy":
                    row[
                        "structural_revenue_log_yoy"
                    ],

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

                "production_qc_flag":
                    row[
                        "production_qc_flag"
                    ],
            }
        )


walk_validation = pd.DataFrame(
    walk_rows
)


# ============================================================
# 17. VALIDATION METRICS
# ============================================================

metric_rows = []


print(
    "\n"
    + "=" * 90
)

print(
    "V3.2.2 WALK-FORWARD VALIDATION"
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
        ]
    )


    structural_error = mae(
        group[
            "actual_log_yoy"
        ],
        group[
            "structural_log_yoy"
        ]
    )


    blend_error = mae(
        group[
            "actual_log_yoy"
        ],
        group[
            "blend_log_yoy"
        ]
    )


    metric_rows.append(
        {
            "ticker":
                ticker,

            "V2_1_MAE":
                v21_error,

            "Structural_MAE":
                structural_error,

            "V3_2_2_MAE":
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
    ]
)


overall_structural = mae(
    walk_validation[
        "actual_log_yoy"
    ],
    walk_validation[
        "structural_log_yoy"
    ]
)


overall_blend = mae(
    walk_validation[
        "actual_log_yoy"
    ],
    walk_validation[
        "blend_log_yoy"
    ]
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
    f"Overall V3.2.2 MAE     : "
    f"{overall_blend:.2f} pp"
)


print(
    "\n===== BY TICKER ====="
)


print(
    metrics
    .round(2)
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
        "energy_v3_2_2_validation.csv"
    ),
    index=False
)


metrics.to_csv(
    lake_path(
        "energy_v3_2_2_metrics.csv"
    )
)


# ============================================================
# 18. FINAL COMPANY BASE WEIGHTS
# ============================================================

weight_rows = []

final_base_weights = {}


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
        ]
    )


    v21_error = mae(
        group[
            "actual_log_yoy"
        ],
        group[
            "v21_log_yoy"
        ]
    )


    if (
        structural_error
        >=
        v21_error
    ):

        base_weight = 0.0

        guardrail = (
            "STRUCTURAL_DISABLED"
        )


    else:

        base_weight = (
            best_weight(
                group
            )
        )

        guardrail = (
            "STRUCTURAL_ENABLED"
        )


    final_base_weights[
        ticker
    ] = (
        base_weight
    )


    weight_rows.append(
        {
            "ticker":
                ticker,

            "base_structural_weight":
                base_weight,

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
    "\n===== FINAL BASE WEIGHTS ====="
)


print(
    weights_df
    .round(3)
)


weights_df.to_csv(
    lake_path(
        "energy_v3_2_2_blend_weights.csv"
    )
)


# ============================================================
# 19. CURRENT STRUCTURAL NOWCAST ROWS
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


    last_actual_q = (
        actual_revenue[
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

            "guidance_vs_actual_yoy":
                row[
                    "guidance_vs_actual_yoy"
                ],

            "guidance_vs_guidance_yoy":
                row[
                    "guidance_vs_guidance_yoy"
                ],

            "total_prod_yoy_l1":
                row[
                    "total_prod_yoy_l1"
                ],

            "total_production_raw":
                row[
                    "total_production_raw"
                ],

            "total_production_clean":
                row[
                    "total_production_clean"
                ],

            "oil_production_clean":
                row[
                    "oil_production_clean"
                ],

            "production_qc_flag":
                row[
                    "production_qc_flag"
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
# 20. MERGE V2.1 CURRENT NOWCAST
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

    how="inner"
)


# ============================================================
# 21. CURRENT EFFECTIVE WEIGHT
# ============================================================

base_weights = []

effective_weights = []


for _, row in (
    current.iterrows()
):

    ticker = row[
        "ticker"
    ]


    base_weight = (
        final_base_weights.get(
            ticker,
            0.0
        )
    )


    effective = (
        quality_adjusted_weight(
            base_weight,
            row
        )
    )


    base_weights.append(
        base_weight
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
# 22. FINAL PREDICTION
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
        MAX_LOG_GROWTH
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
# 23. REVENUE LEVEL
# ============================================================

revenue_predictions = []


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

        revenue_predictions.append(
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
                "predicted_revenue_log_yoy"
            ]
            /
            100
        )
    )


    revenue_predictions.append(
        estimated
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
# 24. MODEL SPREAD
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


# ============================================================
# 25. CONFIDENCE V3.2.2
# ============================================================

def confidence_and_reason(
    row
):

    base_weight = (
        row[
            "base_structural_weight"
        ]
    )


    quality = (
        row[
            "source_quality_score"
        ]
    )


    spread = (
        row[
            "model_spread_pp"
        ]
    )


    qc_flag = str(
        row[
            "production_qc_flag"
        ]
    )


    # ========================================================
    # Structural 자체가 역사적으로 탈락
    # ========================================================

    if base_weight <= 0:

        return (
            "LOW",
            "STRUCTURAL_DISABLED"
        )


    # ========================================================
    # Production QC reject가 현재 row에 있음
    # ========================================================

    if qc_flag.startswith(
        "REJECT"
    ):

        return (
            "LOW",
            "PRODUCTION_QC_REJECT"
        )


    # ========================================================
    # Industry fallback
    # ========================================================

    if (
        row[
            "production_yoy_source"
        ]
        ==
        "INDUSTRY_FALLBACK"
    ):

        return (
            "LOW",
            "INDUSTRY_FALLBACK"
        )


    # ========================================================
    # HIGH
    # ========================================================

    if (
        quality >= 0.90
        and
        spread <= 10
    ):

        return (
            "HIGH",
            "HIGH_QUALITY_DATA_AND_MODEL_AGREEMENT"
        )


    # ========================================================
    # MEDIUM
    # ========================================================

    if (
        quality >= 0.70
        and
        spread <= 20
    ):

        return (
            "MEDIUM",
            "ACCEPTABLE_DATA_OR_MODEL_SPREAD"
        )


    return (
        "LOW",
        "MODEL_DISAGREEMENT_OR_LOW_DATA_QUALITY"
    )


confidence_results = (
    current.apply(
        confidence_and_reason,
        axis=1
    )
)


current[
    "confidence"
] = [
    x[0]
    for x in confidence_results
]


current[
    "confidence_reason"
] = [
    x[1]
    for x in confidence_results
]


# ============================================================
# 26. SELECTED MODEL LABEL
# ============================================================

def selected_model(
    row
):

    weight = (
        row[
            "structural_weight"
        ]
    )


    if weight <= 0.001:

        return "V2.1_ONLY"


    if weight >= 0.999:

        return "STRUCTURAL_ONLY"


    return "BLEND"


current[
    "selected_model"
] = current.apply(
    selected_model,
    axis=1
)


# ============================================================
# 27. FINAL OUTPUT
# ============================================================

output_columns = [

    "ticker",

    "nowcast_quarter",

    # --------------------------------------------------------
    # Final result
    # --------------------------------------------------------

    "predicted_revenue_B",

    "predicted_revenue_log_yoy",

    "predicted_revenue_yoy_pct",


    # --------------------------------------------------------
    # Models
    # --------------------------------------------------------

    "v21_log_yoy",

    "v21_yoy_pct",

    "structural_log_yoy",

    "structural_yoy_pct",


    # --------------------------------------------------------
    # Blend
    # --------------------------------------------------------

    "base_structural_weight",

    "source_quality_score",

    "structural_weight",

    "v21_weight",

    "selected_model",


    # --------------------------------------------------------
    # Confidence
    # --------------------------------------------------------

    "model_spread_pp",

    "confidence",

    "confidence_reason",


    # --------------------------------------------------------
    # Production
    # --------------------------------------------------------

    "company_prod_yoy_proxy",

    "production_yoy_source",

    "production_qc_flag",

    "guidance_total_production",

    "guidance_vs_actual_yoy",

    "guidance_vs_guidance_yoy",

    "total_prod_yoy_l1",

    "total_production_raw",

    "total_production_clean",

    "oil_production_clean",

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
    "🚀 ENERGY REVENUE V3.2.2 NOWCAST"
)

print(
    "=" * 90
)


display_columns = [

    "ticker",

    "nowcast_quarter",

    "predicted_revenue_B",

    "predicted_revenue_yoy_pct",

    "selected_model",

    "structural_weight",

    "production_yoy_source",

    "source_quality_score",

    "model_spread_pp",

    "confidence",

    "company_prod_yoy_proxy",

    "guidance_total_production",
]


print(
    output[
        display_columns
    ]
    .round(2)
    .to_string(
        index=False
    )
)


output.to_csv(
    lake_path(
        "energy_v3_2_2_nowcast.csv"
    ),
    index=False
)


# ============================================================
# 28. MODEL COMPARISON
# ============================================================

comparison_columns = [

    "ticker",

    "predicted_revenue_B",

    "predicted_revenue_yoy_pct",

    "v21_yoy_pct",

    "structural_yoy_pct",

    "base_structural_weight",

    "source_quality_score",

    "structural_weight",

    "selected_model",

    "model_spread_pp",

    "confidence",

    "confidence_reason",

    "production_yoy_source",
]


output[
    comparison_columns
].to_csv(
    lake_path(
        "energy_v3_2_2_model_comparison.csv"
    ),
    index=False
)


# ============================================================
# 29. METADATA
# ============================================================

metadata = {

    "version":
        "3.2.2",

    "tickers":
        TICKERS,


    "production_qc": {

        "max_organic_qoq_log_growth":
            MAX_ORGANIC_QOQ_LOG_GROWTH,

        "max_qoq_threshold":
            MAX_QOQ_THRESHOLD,

        "total_oil_ratio_min":
            TOTAL_OIL_RATIO_MIN,

        "total_oil_ratio_max":
            TOTAL_OIL_RATIO_MAX,

        "mna_jump_exception":
            (
                "ma_event quarter "
                "and immediately following quarter"
            ),
    },


    "source_quality": (
        SOURCE_QUALITY
    ),


    "production_source_priority": [

        "GUIDANCE_VS_ACTUAL",

        "ACTUAL_VS_ACTUAL",

        "GUIDANCE_VS_GUIDANCE",

        "INDUSTRY_FALLBACK",
    ],


    "blend_rule": (
        "historical structural weight "
        "x current production source quality"
    ),


    "guardrail": (
        "Structural disabled when its historical MAE "
        "is not better than V2.1"
    ),
}


with open(
    lake_path(
        "energy_v3_2_2_metadata.json"
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
# 30. DONE
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

    "energy_v3_2_2_structural_panel.csv",

    "energy_v3_2_2_source_quality_summary.csv",

    "energy_v3_2_2_validation.csv",

    "energy_v3_2_2_metrics.csv",

    "energy_v3_2_2_blend_weights.csv",

    "energy_v3_2_2_nowcast.csv",

    "energy_v3_2_2_model_comparison.csv",

    "energy_v3_2_2_metadata.json",

]:

    print(
        " -",
        lake_path(
            filename
        )
    )


print(
    "\nProduction QC files:"
)


for ticker in TICKERS:

    print(
        " -",
        lake_path(
            f"energy_v3_2_2_production_qc_{ticker}.csv"
        )
    )