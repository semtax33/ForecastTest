# ============================================================
# ENERGY REVENUE NOWCAST V3.2.3
# ============================================================
#
# INPUT
# ------------------------------------------------------------
# V2.1:
#
# ./data-lake/energy_v2_1_panel.csv
# ./data-lake/energy_v2_1_validation.csv
# ./data-lake/energy_v2_1_nowcast.csv
#
#
# V3.2.1 production cache:
#
# ./data-lake/energy_v3_2_1_actual_COP.csv
# ./data-lake/energy_v3_2_1_guidance_COP.csv
# ...
#
#
# ------------------------------------------------------------
# V3.2.3 주요 개선
# ------------------------------------------------------------
#
# 1. Field-level QC
#
#    total/oil ratio가 이상하다고
#    total production까지 버리지 않음.
#
#    EOG처럼:
#
#       total = 1,232
#       "oil" = 1,948
#
#    이면 oil series만 reject.
#
#
# 2. Point-in-time Production Regime Confirmation
#
#    큰 production jump 발생:
#
#       q0 = 400
#       q1 = 850  <- suspicious
#
#    q1은 일단 사용하지 않음.
#
#       q2 = 841
#
#    q1과 q2가 비슷하면:
#
#       q2 = NEW_REGIME_CONFIRMED
#
#    단, q1을 미래 정보를 사용해
#    소급 복구하지 않음.
#
#
# 3. M&A window
#
#    ma_window == 1이면
#    큰 production jump 허용.
#
#
# 4. Production Source Priority
#
#    1. GUIDANCE_VS_ACTUAL
#    2. GUIDANCE_VS_GUIDANCE
#    3. ACTUAL_VS_ACTUAL
#    4. INDUSTRY_FALLBACK
#
#
# 5. Source Quality
#
#    GUIDANCE_VS_ACTUAL     1.00
#    GUIDANCE_VS_GUIDANCE   0.80
#    ACTUAL_VS_ACTUAL       0.90
#    INDUSTRY_FALLBACK      0.35
#
#
# 6. Final model
#
#    Revenue Log YoY
#        =
#        w * Structural
#        +
#        (1-w) * V2.1
#
#
#    effective w
#        =
#        historical optimal weight
#        *
#        production source quality
#
#
# 7. Guardrail
#
#    Historical Structural MAE >= V2.1 MAE
#
#        -> Structural OFF
#
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


DATA_LAKE_DIR.mkdir(
    parents=True,
    exist_ok=True,
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

# ------------------------------------------------------------
# 일반적인 quarter-to-quarter production jump 허용치
#
# log-growth 기준
# ------------------------------------------------------------

MAX_ORGANIC_QOQ_LOG_GROWTH = float(
    os.getenv(
        "MAX_ORGANIC_QOQ_LOG_GROWTH",
        "35",
    )
)


# 여러 quarter가 비어 있을 경우
# threshold 증가 상한
MAX_QOQ_THRESHOLD = float(
    os.getenv(
        "MAX_QOQ_THRESHOLD",
        "55",
    )
)


# ------------------------------------------------------------
# 새로운 production regime 확인
#
# 예:
#
# 400 → 850 → 841
#
# 850은 suspicious
#
# 다음 841이 850 근처이면
# 841부터 새로운 regime으로 인정
# ------------------------------------------------------------

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
# TOTAL / OIL SANITY
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


# production absolute bounds
TOTAL_PRODUCTION_MIN = 20
TOTAL_PRODUCTION_MAX = 5000

OIL_PRODUCTION_MIN = 5
OIL_PRODUCTION_MAX = 3000


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
# PREDICTION BOUNDS
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
# 1. PATH HELPER
# ============================================================

def lake_path(filename):

    return (
        DATA_LAKE_DIR
        / filename
    )


print("=" * 90)

print(
    "ENERGY REVENUE NOWCAST V3.2.3"
)

print("=" * 90)

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
    MAX_ORGANIC_QOQ_LOG_GROWTH
)

print(
    "REGIME CONFIRM LIMIT :",
    REGIME_CONFIRM_MAX_LOG_GROWTH
)

print(
    "TOTAL/OIL RATIO :",
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

    actual_file = lake_path(
        f"energy_v3_2_1_actual_{ticker}.csv"
    )

    guidance_file = lake_path(
        f"energy_v3_2_1_guidance_{ticker}.csv"
    )


    if not actual_file.exists():

        raise FileNotFoundError(

            f"{actual_file} 없음.\n"
            "먼저 V3.2.1을 실행해줘."

        )


    if not guidance_file.exists():

        raise FileNotFoundError(

            f"{guidance_file} 없음.\n"
            "먼저 V3.2.1을 실행해줘."

        )


# ============================================================
# 3. GENERIC HELPERS
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


def log_to_normal_pct(
    value,
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


# M&A fallback
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


# ------------------------------------------------------------
# Validation
# ------------------------------------------------------------

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


# ------------------------------------------------------------
# Nowcast
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
# 5. LOAD V3.2.1 CACHE
# ============================================================

def read_period_cache(
    path,
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


    return df.sort_index()


actual_kpis = {}
guidance_kpis = {}


for ticker in TICKERS:

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
# 6. PERIOD MAPPING
#
# DataFrame은 RangeIndex 유지.
#
# quarter 컬럼과 index 충돌을
# 아예 만들지 않음.
# ============================================================

def map_period_series(
    quarters,
    series,
):

    if (
        series is None
        or
        len(series) == 0
    ):

        return pd.Series(
            np.nan,
            index=quarters.index,
            dtype=float,
        )


    mapping = series.to_dict()


    values = [

        mapping.get(
            q,
            np.nan,
        )

        for q in quarters

    ]


    return pd.Series(
        values,
        index=quarters.index,
        dtype=float,
    )


# ============================================================
# 7. PRODUCTION QC
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
    # RAW ACTUAL PRODUCTION
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
    # ABSOLUTE BOUNDS
    # ========================================================

    total_valid = (

        df[
            "total_production_raw"
        ]
        .between(
            TOTAL_PRODUCTION_MIN,
            TOTAL_PRODUCTION_MAX,
        )

    )


    oil_valid = (

        df[
            "oil_production_raw"
        ]
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
    # TOTAL / OIL FIELD SANITY
    #
    # IMPORTANT V3.2.3:
    #
    # ratio가 이상해도
    # TOTAL을 제거하지 않음.
    #
   # Oil만 의심.
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


    # Oil만 제거
    df.loc[
        ratio_bad,
        "oil_candidate"
    ] = np.nan


    # ========================================================
    # M&A WINDOW
    #
    # V3.2.3:
    #
    # event quarter + 1Q가 아니라
    # 전체 ma_window 사용
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
    # SEQUENTIAL TOTAL PRODUCTION QC
    #
    # Point-in-time 방식
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


    df[
        "pending_regime_value"
    ] = np.nan


    df[
        "pending_regime_quarter"
    ] = ""


    # last accepted regime
    accepted_value = None
    accepted_quarter = None


    # suspicious candidate
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


        # ----------------------------------------------------
        # Missing
        # ----------------------------------------------------

        if (
            pd.isna(current)
            or
            current <= 0
        ):

            df.loc[
                i,
                "total_qc_flag"
            ] = "MISSING"

            continue


        current = float(
            current
        )


        # ====================================================
        # INITIAL REGIME
        #
        # 첫 production 하나만 보고
        # 바로 regime으로 인정하지 않음.
        # ====================================================

        if (
            accepted_value is None
            or
            accepted_quarter is None
        ):

            if (
                pending_value is None
                or
                pending_quarter is None
            ):

                pending_value = (
                    current
                )

                pending_quarter = q


                df.loc[
                    i,
                    "total_qc_flag"
                ] = (
                    "PENDING_INITIAL_REGIME"
                )


                df.loc[
                    i,
                    "pending_regime_value"
                ] = pending_value


                df.loc[
                    i,
                    "pending_regime_quarter"
                ] = str(
                    pending_quarter
                )


                continue


            # previous pending candidate와 비교
            gap = max(
                1,
                quarter_gap(
                    q,
                    pending_quarter
                )
            )


            pending_growth = (
                log_ratio_growth(
                    current,
                    pending_value
                )
            )


            confirmation_threshold = (

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
                    pending_growth
                )

                and

                abs(
                    pending_growth
                )
                <=
                confirmation_threshold
            ):

                # ============================================
                # Initial regime confirmed
                #
                # IMPORTANT:
                # previous pending quarter는 복구하지 않음.
                # ============================================

                accepted_value = (
                    current
                )

                accepted_quarter = q


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


                pending_value = None
                pending_quarter = None


                continue


            # 아직 regime 확인 안 됨
            pending_value = (
                current
            )

            pending_quarter = q


            df.loc[
                i,
                "total_qc_flag"
            ] = (
                "PENDING_INITIAL_REGIME"
            )


            df.loc[
                i,
                "pending_regime_value"
            ] = pending_value


            df.loc[
                i,
                "pending_regime_quarter"
            ] = str(
                pending_quarter
            )


            continue


        # ====================================================
        # NORMAL CONTINUITY CHECK
        # ====================================================

        gap_from_accepted = max(
            1,
            quarter_gap(
                q,
                accepted_quarter
            )
        )


        growth_from_accepted = (
            log_ratio_growth(
                current,
                accepted_value
            )
        )


        threshold = min(

            (
                MAX_ORGANIC_QOQ_LOG_GROWTH

                *

                np.sqrt(
                    gap_from_accepted
                )
            ),

            MAX_QOQ_THRESHOLD,

        )


        df.loc[
            i,
            "production_qoq_log_raw"
        ] = growth_from_accepted


        df.loc[
            i,
            "production_qoq_threshold"
        ] = threshold


        # ====================================================
        # Normal regime
        # ====================================================

        if (
            pd.notna(
                growth_from_accepted
            )

            and

            abs(
                growth_from_accepted
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

            accepted_quarter = q


            # old pending candidate 폐기
            pending_value = None
            pending_quarter = None


            continue


        # ====================================================
        # M&A WINDOW
        #
        # 큰 jump 허용
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

            accepted_quarter = q


            pending_value = None
            pending_quarter = None


            continue


        # ====================================================
        # NEW REGIME CONFIRMATION
        #
        # 현재 값이 old regime과 다르지만,
        #
        # 바로 전 suspicious candidate와 비슷하면
        # 새로운 production regime 인정.
        # ====================================================

        if (
            pending_value is not None
            and
            pending_quarter is not None
        ):

            pending_gap = max(
                1,
                quarter_gap(
                    q,
                    pending_quarter
                )
            )


            pending_growth = (
                log_ratio_growth(
                    current,
                    pending_value
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

                # ============================================
                # 새로운 regime 확정
                #
                # previous suspicious quarter는
                # look-ahead 방지를 위해 복구하지 않음.
                # ============================================

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

                accepted_quarter = q


                pending_value = None
                pending_quarter = None


                continue


        # ====================================================
        # 아직 새로운 regime 확인 안 됨
        # ====================================================

        pending_value = (
            current
        )

        pending_quarter = q


        df.loc[
            i,
            "total_qc_flag"
        ] = (
            "REJECT_QOQ_JUMP_PENDING"
        )


        df.loc[
            i,
            "pending_regime_value"
        ] = pending_value


        df.loc[
            i,
            "pending_regime_quarter"
        ] = str(
            pending_quarter
        )


    # ========================================================
    # CLEAN OIL
    #
    # Total이 clean인 분기에서만
    # oil share 계산 허용
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
    # COMBINED FLAG
    # ========================================================

    df[
        "production_qc_flag"
    ] = (
        df[
            "total_qc_flag"
        ]
    )


    # ========================================================
    # YOY
    # ========================================================

    df[
        "total_prod_yoy_raw"
    ] = log_growth(
        df[
            "total_production_raw"
        ],
        4,
    )


    df[
        "total_prod_yoy_clean"
    ] = log_growth(
        df[
            "total_production_clean"
        ],
        4,
    )


    # ========================================================
    # SAVE QC
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

        "oil_qc_flag",

        "total_production_clean",

        "oil_production_clean",

        "production_qoq_log_raw",

        "production_qoq_threshold",

        "pending_regime_value",

        "pending_regime_quarter",

        "total_prod_yoy_raw",

        "total_prod_yoy_clean",

        "total_qc_flag",

        "production_qc_flag",

    ]


    df[
        qc_columns
    ].to_csv(

        lake_path(
            f"energy_v3_2_3_production_qc_{ticker}.csv"
        ),

        index=False,

    )


    # ========================================================
    # DIAGNOSTICS
    # ========================================================

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


    oil_rejected = int(
        df[
            "oil_qc_flag"
        ]
        .eq(
            "REJECT_OIL_RATIO"
        )
        .sum()
    )


    regime_confirmed = int(
        df[
            "total_qc_flag"
        ]
        .eq(
            "NEW_REGIME_CONFIRMED"
        )
        .sum()
    )


    mna_accepted = int(
        df[
            "total_qc_flag"
        ]
        .eq(
            "MNA_JUMP_ACCEPTED"
        )
        .sum()
    )


    print(
        f"\n{ticker} PRODUCTION QC"
    )


    print(
        "  raw total production     :",
        raw_count
    )


    print(
        "  clean total production   :",
        clean_count
    )


    print(
        "  rejected oil fields      :",
        oil_rejected
    )


    print(
        "  new regimes confirmed    :",
        regime_confirmed
    )


    print(
        "  M&A jumps accepted       :",
        mna_accepted
    )


    interesting = (

        df[

            df[
                "total_qc_flag"
            ]
            .ne(
                "OK"
            )

            &

            df[
                "total_production_raw"
            ]
            .notna()

        ]

    )


    if not interesting.empty:

        print(
            "\n  ===== QC EVENTS ====="
        )


        print(

            interesting[
                [
                    "quarter",

                    "total_production_raw",

                    "oil_production_raw",

                    "total_oil_ratio",

                    "production_qoq_log_raw",

                    "ma_window",

                    "total_qc_flag",

                    "oil_qc_flag",
                ]
            ]

            .round(2)

            .to_string(
                index=False
            )

        )


    return df


# ============================================================
# 8. RUN PRODUCTION QC
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
# 9. STRUCTURAL FEATURE ENGINEERING
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


    if (
        not guidance.empty

        and

        "guidance_oil_production"
        in guidance.columns
    ):

        df[
            "guidance_oil_production"
        ] = map_period_series(

            df[
                "quarter"
            ],

            guidance[
                "guidance_oil_production"
            ],

        )

    else:

        df[
            "guidance_oil_production"
        ] = np.nan


    # ========================================================
    # ACTUAL PRODUCTION YOY
    # ========================================================

    df[
        "total_prod_yoy"
    ] = log_growth(

        df[
            "total_production_clean"
        ],

        4,

    )


    # Target quarter에서 알 수 있는
    # 직전 분기 actual production YoY
    df[
        "total_prod_yoy_l1"
    ] = (

        df[
            "total_prod_yoy"
        ]
        .shift(1)

    )


    # ========================================================
    # GUIDANCE VS PRIOR ACTUAL
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


    # ========================================================
    # GUIDANCE VS PRIOR GUIDANCE
    # ========================================================

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
    # PRODUCTION PROXY
    #
    # V3.2.3 PRIORITY
    #
    # 1 GA
    # 2 GG
    # 3 AA
    # 4 Industry
    # ========================================================

    proxy_values = []

    proxy_sources = []

    quality_scores = []


    for i in range(
        len(df)
    ):

        row = df.iloc[
            i
        ]


        # ----------------------------------------------------
        # 1. Guidance vs Actual
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
        # 2. Guidance vs Guidance
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
        # 3. Actual vs Actual
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
        # 4. Industry
        # ----------------------------------------------------

        else:

            value = (
                industry_prod_proxy.iloc[
                    i
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
                    120,
                )

            )


        proxy_values.append(
            value
        )


        proxy_sources.append(
            source
        )


        quality_scores.append(

            SOURCE_QUALITY[
                source
            ]

        )


    df[
        "company_prod_yoy_proxy"
    ] = (
        proxy_values
    )


    df[
        "production_yoy_source"
    ] = (
        proxy_sources
    )


    df[
        "source_quality_score"
    ] = (
        quality_scores
    )


    # ========================================================
    # FLAGS
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
    # OIL SHARE
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
    # PRICE MIX
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
    # STRUCTURAL REVENUE
    #
    # log Revenue growth
    # ~
    # log Price growth
    # +
    # log Production growth
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
# 10. BUILD STRUCTURAL PANEL
# ============================================================

frames = []


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


    frames.append(
        company
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
        "energy_v3_2_3_structural_panel.csv"
    ),

    index=False,

)


# ============================================================
# 11. PRODUCTION SOURCE SUMMARY
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
        "energy_v3_2_3_source_quality_summary.csv"
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
# 12. VALIDATION DATA
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

            "total_qc_flag",

            "oil_qc_flag",

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
# 13. MERGE V2.1 VALIDATION
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
# 14. BEST BLEND WEIGHT
# ============================================================

def best_weight(
    history,
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


        if error < best_error:

            best_error = (
                error
            )

            best_w = float(
                weight
            )


    return best_w


# ============================================================
# 15. HISTORICAL GUARDRAIL
# ============================================================

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


# ============================================================
# 16. SOURCE QUALITY WEIGHT
# ============================================================

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
# 17. WALK-FORWARD VALIDATION
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

            base_weight = (
                0.0
            )

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


                # actual
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


                # models
                "v21_log_yoy":
                    row[
                        "v21_log_yoy"
                    ],

                "structural_log_yoy":
                    row[
                        "structural_revenue_log_yoy"
                    ],


                # weights
                "base_structural_weight":
                    base_weight,

                "source_quality_score":
                    row[
                        "source_quality_score"
                    ],

                "effective_structural_weight":
                    effective_weight,


                # prediction
                "blend_log_yoy":
                    prediction,

                "blend_yoy_pct":
                    log_to_normal_pct(
                        prediction
                    ),


                # production
                "company_prod_yoy_proxy":
                    row[
                        "company_prod_yoy_proxy"
                    ],

                "production_yoy_source":
                    row[
                        "production_yoy_source"
                    ],

                "total_qc_flag":
                    row[
                        "total_qc_flag"
                    ],

                "oil_qc_flag":
                    row[
                        "oil_qc_flag"
                    ],

            }
        )


walk_validation = pd.DataFrame(
    walk_rows
)


# ============================================================
# 18. VALIDATION METRICS
# ============================================================

metric_rows = []


print(
    "\n"
    + "=" * 90
)

print(
    "V3.2.3 WALK-FORWARD VALIDATION"
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

            "V3_2_3_MAE":
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
    f"Overall V3.2.3 MAE     : "
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

    walk_validation
    .tail(20)
    .round(2)
    .to_string(
        index=False
    )

)


walk_validation.to_csv(

    lake_path(
        "energy_v3_2_3_validation.csv"
    ),

    index=False,

)


metrics.to_csv(

    lake_path(
        "energy_v3_2_3_metrics.csv"
    )

)


# ============================================================
# 19. FINAL BASE WEIGHTS
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
    ] = (
        weight
    )


    weight_rows.append(
        {

            "ticker":
                ticker,

            "base_structural_weight":
                weight,

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
    weights_df.round(
        3
    )
)


weights_df.to_csv(

    lake_path(
        "energy_v3_2_3_blend_weights.csv"
    )

)


# ============================================================
# 20. CURRENT STRUCTURAL NOWCAST
# ============================================================

nowcast_rows = []


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


    current_row = (

        company[

            company[
                "quarter"
            ]
            == target_q

        ]

    )


    if current_row.empty:

        continue


    row = current_row.iloc[
        0
    ]


    nowcast_rows.append(
        {

            "ticker":
                ticker,

            "nowcast_quarter":
                target_q,


            # structural
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


            # production
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


            # guidance
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


            # actual
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


            # QC
            "total_qc_flag":
                row[
                    "total_qc_flag"
                ],

            "oil_qc_flag":
                row[
                    "oil_qc_flag"
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
    nowcast_rows
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
# 21. MERGE V2.1 NOWCAST
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
# 22. EFFECTIVE CURRENT WEIGHTS
# ============================================================

base_weights = []

effective_weights = []


for _, row in (
    current.iterrows()
):

    ticker = row[
        "ticker"
    ]


    base = (

        final_base_weights.get(
            ticker,
            0.0
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
# 23. FINAL PREDICTION
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
# 24. REVENUE LEVEL
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
# 25. MODEL SPREAD
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
# 26. MODEL LABEL
# ============================================================

def selected_model(
    row
):

    weight = row[
        "structural_weight"
    ]


    if weight <= 0.001:

        return "V2.1_ONLY"


    if weight >= 0.999:

        return "STRUCTURAL_ONLY"


    return "BLEND"


current[
    "selected_model"
] = current.apply(
    selected_model,
    axis=1,
)


# ============================================================
# 27. CONFIDENCE
# ============================================================

def confidence_and_reason(
    row
):

    base_weight = row[
        "base_structural_weight"
    ]


    quality = row[
        "source_quality_score"
    ]


    spread = row[
        "model_spread_pp"
    ]


    source = row[
        "production_yoy_source"
    ]


    # --------------------------------------------------------
    # Structural historical failure
    # --------------------------------------------------------

    if base_weight <= 0:

        return (
            "LOW",
            "STRUCTURAL_DISABLED",
        )


    # --------------------------------------------------------
    # Industry fallback
    # --------------------------------------------------------

    if (
        source
        ==
        "INDUSTRY_FALLBACK"
    ):

        return (
            "LOW",
            "INDUSTRY_FALLBACK",
        )


    # --------------------------------------------------------
    # HIGH
    # --------------------------------------------------------

    if (
        quality >= 0.90
        and
        spread <= 10
    ):

        return (
            "HIGH",
            "HIGH_QUALITY_PRODUCTION_AND_MODEL_AGREEMENT",
        )


    # --------------------------------------------------------
    # MEDIUM
    # --------------------------------------------------------

    if (
        quality >= 0.75
        and
        spread <= 20
    ):

        return (
            "MEDIUM",
            "ACCEPTABLE_DATA_AND_MODEL_SPREAD",
        )


    return (
        "LOW",
        "MODEL_DISAGREEMENT_OR_LOW_DATA_QUALITY",
    )


confidence_result = current.apply(
    confidence_and_reason,
    axis=1,
)


current[
    "confidence"
] = [

    x[0]

    for x in confidence_result

]


current[
    "confidence_reason"
] = [

    x[1]

    for x in confidence_result

]


# ============================================================
# 28. FINAL OUTPUT
# ============================================================

output_columns = [

    "ticker",

    "nowcast_quarter",


    # ========================================================
    # FINAL
    # ========================================================

    "predicted_revenue_B",

    "predicted_revenue_log_yoy",

    "predicted_revenue_yoy_pct",


    # ========================================================
    # MODELS
    # ========================================================

    "v21_log_yoy",

    "v21_yoy_pct",

    "structural_log_yoy",

    "structural_yoy_pct",


    # ========================================================
    # WEIGHTS
    # ========================================================

    "base_structural_weight",

    "source_quality_score",

    "structural_weight",

    "v21_weight",

    "selected_model",


    # ========================================================
    # CONFIDENCE
    # ========================================================

    "model_spread_pp",

    "confidence",

    "confidence_reason",


    # ========================================================
    # PRODUCTION
    # ========================================================

    "company_prod_yoy_proxy",

    "production_yoy_source",

    "guidance_total_production",

    "guidance_vs_actual_yoy",

    "guidance_vs_guidance_yoy",

    "total_prod_yoy_l1",


    # ========================================================
    # ACTUAL/QC
    # ========================================================

    "total_production_raw",

    "total_production_clean",

    "oil_production_clean",

    "total_qc_flag",

    "oil_qc_flag",

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
    "🚀 ENERGY REVENUE V3.2.3 NOWCAST"
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

    "company_prod_yoy_proxy",

    "model_spread_pp",

    "confidence",

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
        "energy_v3_2_3_nowcast.csv"
    ),

    index=False,

)


# ============================================================
# 29. MODEL COMPARISON
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

    "production_yoy_source",

    "model_spread_pp",

    "confidence",

    "confidence_reason",

]


output[
    comparison_columns
].to_csv(

    lake_path(
        "energy_v3_2_3_model_comparison.csv"
    ),

    index=False,

)


# ============================================================
# 30. METADATA
# ============================================================

metadata = {

    "version":
        "3.2.3",

    "tickers":
        TICKERS,


    "production_qc": {

        "max_organic_qoq_log_growth":
            MAX_ORGANIC_QOQ_LOG_GROWTH,

        "max_qoq_threshold":
            MAX_QOQ_THRESHOLD,

        "regime_confirmation_log_growth":
            REGIME_CONFIRM_MAX_LOG_GROWTH,

        "max_regime_confirmation_gap":
            MAX_REGIME_CONFIRM_GAP,

        "total_oil_ratio_min":
            TOTAL_OIL_RATIO_MIN,

        "total_oil_ratio_max":
            TOTAL_OIL_RATIO_MAX,

    },


    "field_qc_rule":

        (
            "Bad total/oil ratio rejects oil field only; "
            "total production is validated independently."
        ),


    "mna_rule":

        (
            "Large production changes are accepted when "
            "ma_window > 0."
        ),


    "regime_rule":

        (
            "First suspicious production jump is not accepted. "
            "If a subsequent observation confirms the same "
            "new production level, only the subsequent quarter "
            "is accepted as NEW_REGIME_CONFIRMED. "
            "No retrospective correction is performed."
        ),


    "production_source_priority": [

        "GUIDANCE_VS_ACTUAL",

        "GUIDANCE_VS_GUIDANCE",

        "ACTUAL_VS_ACTUAL",

        "INDUSTRY_FALLBACK",

    ],


    "source_quality":
        SOURCE_QUALITY,


    "guardrail":

        (
            "Structural model is disabled when its historical "
            "MAE is not better than V2.1."
        ),

}


with open(

    lake_path(
        "energy_v3_2_3_metadata.json"
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
# 31. OPTIONAL V3.2.2 BENCHMARK
# ============================================================

previous_metrics_file = lake_path(
    "energy_v3_2_2_metrics.csv"
)


if previous_metrics_file.exists():

    try:

        previous_metrics = pd.read_csv(
            previous_metrics_file,
            index_col=0,
        )


        print(
            "\n"
            + "=" * 90
        )

        print(
            "V3.2.2 vs V3.2.3 BY TICKER"
        )

        print(
            "=" * 90
        )


        benchmark = metrics.copy()


        if (
            "V3_2_2_MAE"
            in previous_metrics.columns
        ):

            benchmark[
                "V3_2_2_MAE"
            ] = (
                previous_metrics[
                    "V3_2_2_MAE"
                ]
            )


            benchmark[
                "V3_2_3_vs_3_2_2"
            ] = (

                benchmark[
                    "V3_2_2_MAE"
                ]

                -

                benchmark[
                    "V3_2_3_MAE"
                ]

            )


            print(

                benchmark[
                    [
                        "V3_2_2_MAE",
                        "V3_2_3_MAE",
                        "V3_2_3_vs_3_2_2",
                    ]
                ]

                .round(2)

            )


    except Exception:

        pass


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
    "\nMain outputs:"
)


for filename in [

    "energy_v3_2_3_structural_panel.csv",

    "energy_v3_2_3_source_quality_summary.csv",

    "energy_v3_2_3_validation.csv",

    "energy_v3_2_3_metrics.csv",

    "energy_v3_2_3_blend_weights.csv",

    "energy_v3_2_3_nowcast.csv",

    "energy_v3_2_3_model_comparison.csv",

    "energy_v3_2_3_metadata.json",

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
            f"energy_v3_2_3_production_qc_{ticker}.csv"
        )
    )
