# ============================================================
# ENERGY REVENUE NOWCAST V2
#
# EIA + BEA + SEC(edgartools) + M&A + Panel Ridge
#
# pip install -U edgartools beaapi pandas numpy requests scikit-learn
# ============================================================

import os
import re
import warnings
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
# 0. USER CONFIG
# ============================================================

# ------------------------------------------------------------
# 여기를 수정
# ------------------------------------------------------------

EIA_API_KEY = os.getenv("EIA_API_KEY")
BEA_API_KEY = os.getenv("BEA_API_KEY")
EDGAR_IDENTITY = os.getenv("EDGAR_IDENTITY")


# ------------------------------------------------------------
# 분석 종목
#
# E&P 중심으로 먼저 구성
# ------------------------------------------------------------

TICKERS = [
    "COP",
    "EOG",
    "FANG",
    "DVN",
]


# 데이터 시작 연도
START_YEAR = 2014


# ------------------------------------------------------------
# None이면 오늘 날짜
#
# 과거 특정 시점 테스트:
#
# AS_OF_DATE = "2026-08-31"
# ------------------------------------------------------------

AS_OF_DATE = None


# Walk-forward OOS test
TEST_QUARTERS = 12


# 최소 training history
MIN_TRAIN_QUARTERS = 16


# Ridge alpha 후보
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

def check_config():

    if (
        not EIA_API_KEY
        or "YOUR_EIA" in EIA_API_KEY
    ):
        raise ValueError(
            "EIA_API_KEY를 입력해줘."
        )

    if (
        not BEA_API_KEY
        or "YOUR_BEA" in BEA_API_KEY
    ):
        raise ValueError(
            "BEA_API_KEY를 입력해줘."
        )

    if (
        not EDGAR_IDENTITY
        or "your_email" in EDGAR_IDENTITY
    ):
        raise ValueError(
            "EDGAR_IDENTITY를 "
            "'이름 email@example.com' 형태로 입력해줘."
        )


def resolve_as_of_date():

    if AS_OF_DATE is None:
        return pd.Timestamp(
            date.today()
        )

    return pd.Timestamp(
        AS_OF_DATE
    )


check_config()

AS_OF = resolve_as_of_date()

set_identity(
    EDGAR_IDENTITY
)

print(
    f"AS OF DATE: "
    f"{AS_OF.date()}"
)


# ============================================================
# 2. COMMON HELPERS
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
    )

    # (123) -> -123
    if (
        s.startswith("(")
        and s.endswith(")")
    ):
        s = "-" + s[1:-1]

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
        & (lagged > 0)
    )

    result.loc[valid] = (
        np.log(
            series.loc[valid]
            / lagged.loc[valid]
        )
        * 100
    )

    return result


# ============================================================
# 3. EIA API
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
        params["start"] = start

    response = requests.get(
        url,
        params=params,
        timeout=60,
    )

    response.raise_for_status()

    js = response.json()

    try:

        rows = (
            js["response"]["data"]
        )

    except Exception:

        raise ValueError(
            f"EIA 응답 구조 이상:\n"
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

    # --------------------------------------------------------
    # 날짜
    # --------------------------------------------------------

    df["date"] = pd.to_datetime(
        df["period"],
        errors="coerce",
    )

    # --------------------------------------------------------
    # value column 찾기
    # --------------------------------------------------------

    if "value" in df.columns:

        value_col = "value"

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
                or str(col).endswith(
                    "-units"
                )
            ):
                continue

            test = pd.to_numeric(
                df[col],
                errors="coerce",
            )

            if (
                test.notna().sum()
                > 0
            ):
                value_col = col
                break

        if value_col is None:

            raise ValueError(
                f"EIA numeric field "
                f"찾기 실패: "
                f"{df.columns.tolist()}"
            )

    df["value"] = pd.to_numeric(
        df[value_col],
        errors="coerce",
    )

    series = (
        df[
            [
                "date",
                "value",
            ]
        ]
        .dropna()
        .drop_duplicates(
            "date"
        )
        .set_index(
            "date"
        )
        .sort_index()
        ["value"]
    )

    # AS_OF 이후 제거
    series = series.loc[
        series.index
        <= AS_OF
    ]

    return series


# ============================================================
# 4. ENERGY EIA DATA
# ============================================================

def get_energy_eia():

    print(
        "\nDownloading EIA..."
    )

    # --------------------------------------------------------
    # Daily prices
    # --------------------------------------------------------

    wti = get_eia_series(
        "PET.RWTC.D",
        start=f"{START_YEAR}-01-01",
    )

    wti.name = "wti"


    henry = get_eia_series(
        "NG.RNGWHHD.D",
        start=f"{START_YEAR}-01-01",
    )

    henry.name = "henry_hub"


    # --------------------------------------------------------
    # Monthly production
    # --------------------------------------------------------

    crude_prod = get_eia_series(
        "PET.MCRFPUS2.M",
        start=str(
            START_YEAR
        ),
    )

    crude_prod.name = (
        "crude_prod"
    )


    gas_prod = get_eia_series(
        "NG.N9070US2.M",
        start=str(
            START_YEAR
        ),
    )

    gas_prod.name = (
        "gas_prod"
    )

    return {
        "wti":
            wti,

        "henry_hub":
            henry,

        "crude_prod":
            crude_prod,

        "gas_prod":
            gas_prod,
    }


# ============================================================
# 5. BEA GROSS OUTPUT
# ============================================================

def get_bea_gross_output():

    print(
        "\nDownloading BEA "
        "Oil & Gas Gross Output..."
    )

    # --------------------------------------------------------
    # GDPbyIndustry
    #
    # TableID 15
    # Gross Output by Industry
    #
    # Industry 211
    # Oil and gas extraction
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

    # BEA quarter
    # I II III IV
    qmap = {
        "I": 1,
        "II": 2,
        "III": 3,
        "IV": 4,

        "1": 1,
        "2": 2,
        "3": 3,
        "4": 4,
    }

    df["q_num"] = (
        df["Quarter"]
        .astype(str)
        .map(qmap)
    )

    df = df.dropna(
        subset=[
            "q_num",
            "gross_output",
        ]
    )

    df["quarter"] = (
        pd.PeriodIndex(

            df["Year"]
            .astype(str)

            + "Q"

            + df["q_num"]
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

    # AS_OF 이후 제거
    as_of_q = AS_OF.to_period(
        "Q"
    )

    result = result.loc[
        result.index <= as_of_q
    ]

    return result


# ============================================================
# 6. MACRO QUARTERLY FEATURES
# ============================================================

def complete_quarter_mean(
    series
):

    q = (
        series.index
        .to_period("Q")
    )

    mean = (
        series
        .groupby(q)
        .mean()
    )

    count = (
        series
        .groupby(q)
        .count()
    )

    # 월간 데이터는
    # 3개월 모두 있어야 complete
    mean.loc[
        count < 3
    ] = np.nan

    return mean


def make_macro_features():

    eia = get_energy_eia()

    bea = get_bea_gross_output()

    # --------------------------------------------------------
    # Daily price
    # -> quarterly average
    #
    # 현재 진행 중 분기는
    # 지금까지의 평균을 그대로 사용
    # --------------------------------------------------------

    wti_q = (
        eia["wti"]
        .groupby(
            eia["wti"]
            .index
            .to_period("Q")
        )
        .mean()
        .rename("wti")
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

    # --------------------------------------------------------
    # Monthly production
    # -> quarterly average
    # --------------------------------------------------------

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

    bea_q = (
        bea[
            "gross_output"
        ]
    )

    # --------------------------------------------------------
    # Full quarterly index
    # --------------------------------------------------------

    start_q = pd.Period(
        f"{START_YEAR}Q1",
        freq="Q",
    )

    end_q = AS_OF.to_period(
        "Q"
    )

    idx = pd.period_range(
        start=start_q,
        end=end_q,
        freq="Q",
    )

    macro = pd.DataFrame(
        index=idx
    )

    macro["wti"] = (
        wti_q
    )

    macro["henry_hub"] = (
        henry_q
    )

    macro["crude_prod"] = (
        crude_q
    )

    macro["gas_prod"] = (
        gas_q
    )

    macro[
        "bea_gross_output"
    ] = bea_q


    # --------------------------------------------------------
    # YoY
    # --------------------------------------------------------

    macro["wti_yoy"] = (
        log_growth(
            macro["wti"],
            4,
        )
    )

    macro["henry_yoy"] = (
        log_growth(
            macro["henry_hub"],
            4,
        )
    )

    crude_yoy = log_growth(
        macro["crude_prod"],
        4,
    )

    gas_yoy = log_growth(
        macro["gas_prod"],
        4,
    )

    bea_yoy = log_growth(
        macro[
            "bea_gross_output"
        ],
        4,
    )


    # --------------------------------------------------------
    # Production / BEA는
    # 발표 lag 때문에 1 quarter lag
    # --------------------------------------------------------

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

    return macro


# ============================================================
# 7. EDGAR PERIOD PARSER
# ============================================================

def parse_edgar_period_column(
    col
):

    s = str(
        col
    ).strip()

    # --------------------------------------------------------
    # YYYY-MM-DD
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

    m = re.fullmatch(
        r"Q([1-4])\s+(\d{4})",
        s,
        flags=re.IGNORECASE,
    )

    if m:

        return pd.Period(
            f"{m.group(2)}"
            f"Q{m.group(1)}",
            freq="Q",
        )


    # --------------------------------------------------------
    # 2025Q1
    # --------------------------------------------------------

    m = re.fullmatch(
        r"(\d{4})Q([1-4])",
        s,
        flags=re.IGNORECASE,
    )

    if m:

        return pd.Period(
            f"{m.group(1)}"
            f"Q{m.group(2)}",
            freq="Q",
        )


    return None


# ============================================================
# 8. GENERIC EDGAR STATEMENT EXTRACTOR
# ============================================================

def extract_statement_series(
    stmt_df,
    standard_concepts=None,
    raw_concepts=None,
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


    # --------------------------------------------------------
    # 기간 columns
    # --------------------------------------------------------

    period_cols = []

    for col in stmt_df.columns:

        q = (
            parse_edgar_period_column(
                col
            )
        )

        if q is not None:

            period_cols.append(
                col
            )


    if not period_cols:

        return pd.Series(
            dtype=float
        )


    rows = pd.DataFrame()


    # --------------------------------------------------------
    # 1. standardized concept
    # --------------------------------------------------------

    if (
        standard_concepts
        and
        "standard_concept"
        in stmt_df.columns
    ):

        mask = (
            stmt_df[
                "standard_concept"
            ]
            .astype(str)
            .str.strip()
            .isin(
                standard_concepts
            )
        )

        rows = stmt_df.loc[
            mask
        ]


    # --------------------------------------------------------
    # 2. raw XBRL concept fallback
    # --------------------------------------------------------

    if (
        rows.empty
        and raw_concepts
    ):

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


        if concept_col:

            values = (
                stmt_df[
                    concept_col
                ]
                .astype(str)
            )

            mask = pd.Series(
                False,
                index=stmt_df.index,
            )

            for concept in (
                raw_concepts
            ):

                mask = (
                    mask
                    |
                    values.str.endswith(
                        concept,
                        na=False,
                    )
                )

            rows = stmt_df.loc[
                mask
            ]


    # --------------------------------------------------------
    # 3. label fallback
    # --------------------------------------------------------

    if (
        rows.empty
        and label_regex
        and "label"
        in stmt_df.columns
    ):

        mask = (
            stmt_df[
                "label"
            ]
            .astype(str)
            .str.contains(
                label_regex,
                case=False,
                regex=True,
                na=False,
            )
        )

        rows = stmt_df.loc[
            mask
        ]


    if rows.empty:

        return pd.Series(
            dtype=float
        )


    # --------------------------------------------------------
    # 여러 행이면 가장 많은 기간을 가진 행
    # --------------------------------------------------------

    coverage = (
        rows[
            period_cols
        ]
        .notna()
        .sum(
            axis=1
        )
    )

    best_idx = (
        coverage.idxmax()
    )

    row = rows.loc[
        best_idx
    ]


    if verbose:

        label = row.get(
            "label",
            ""
        )

        std = row.get(
            "standard_concept",
            ""
        )

        print(
            f"  selected: "
            f"{label} "
            f"[{std}]"
        )


    values = {}

    for col in period_cols:

        quarter = (
            parse_edgar_period_column(
                col
            )
        )

        value = safe_numeric(
            row[col]
        )

        if (
            quarter is not None
            and pd.notna(value)
        ):

            values[
                quarter
            ] = float(
                value
            )


    if not values:

        return pd.Series(
            dtype=float
        )


    result = pd.Series(
        values,
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
# 9. SEC FINANCIAL FEATURES
# ============================================================

def get_sec_financial_features(
    ticker,
    periods=56,
):

    print(
        f"\nSEC Financials: "
        f"{ticker}"
    )

    company = Company(
        ticker
    )

    facts = (
        company.get_facts()
    )


    # --------------------------------------------------------
    # Income Statement
    # --------------------------------------------------------

    income = (
        facts
        .income_statement(
            periods=periods,
            annual=False,
            as_dataframe=True,
        )
    )


    # --------------------------------------------------------
    # Balance Sheet
    # --------------------------------------------------------

    balance = (
        facts
        .balance_sheet(
            periods=periods,
            annual=False,
            as_dataframe=True,
        )
    )


    print(
        f"  income shape : "
        f"{income.shape}"
    )

    print(
        f"  balance shape: "
        f"{balance.shape}"
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

            label_regex=(
                r"^total revenue$|"
                r"^total revenues$|"
                r"revenues|"
                r"sales revenue"
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
    # Total Assets
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

            label_regex=(
                r"^total assets$"
            ),
        )
    )


    # ========================================================
    # PPE
    #
    # E&P의 생산자산 / 광구 규모 변화 proxy
    # ========================================================

    ppe = (
        extract_statement_series(

            balance,

            standard_concepts=[
                (
                    "PlantProperty"
                    "EquipmentNet"
                ),
            ],

            raw_concepts=[
                (
                    "PropertyPlantAnd"
                    "EquipmentNet"
                ),

                (
                    "PropertyPlantAnd"
                    "EquipmentAndFinance"
                    "LeaseRightOfUseAsset"
                    "AfterAccumulated"
                    "DepreciationAndAmortization"
                ),
            ],

            label_regex=(
                r"property.*plant.*"
                r"equipment|"
                r"oil.*gas.*propert"
            ),
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

            label_regex=(
                r"^goodwill$"
            ),
        )
    )


    # ========================================================
    # Long-term Debt
    # ========================================================

    long_debt = (
        extract_statement_series(

            balance,

            standard_concepts=[
                "LongTermDebt",
            ],

            raw_concepts=[
                (
                    "LongTermDebt"
                    "Noncurrent"
                ),

                (
                    "LongTermDebtAnd"
                    "FinanceLeaseObligations"
                    "Noncurrent"
                ),
            ],

            label_regex=(
                r"long.term debt|"
                r"long.term borrow"
            ),
        )
    )


    # ========================================================
    # Current Debt
    # ========================================================

    short_debt = (
        extract_statement_series(

            balance,

            standard_concepts=[
                "ShortTermDebt",
            ],

            raw_concepts=[
                (
                    "ShortTerm"
                    "Borrowings"
                ),

                (
                    "LongTermDebt"
                    "Current"
                ),

                (
                    "LongTermDebtAnd"
                    "FinanceLeaseObligations"
                    "Current"
                ),
            ],

            label_regex=(
                r"short.term debt|"
                r"current portion.*debt|"
                r"current debt"
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
    # Weighted Average Shares
    #
    # Stock-financed M&A proxy
    # ========================================================

    shares_income = (
        extract_statement_series(

            income,

            standard_concepts=[
                "SharesAverage",
            ],

            raw_concepts=[
                (
                    "WeightedAverageNumber"
                    "OfDilutedSharesOutstanding"
                ),

                (
                    "WeightedAverageNumber"
                    "OfSharesOutstandingBasic"
                ),
            ],

            label_regex=(
                r"weighted average.*"
                r"shares"
            ),
        )
    )


    # balance sheet shares fallback
    shares_balance = (
        extract_statement_series(

            balance,

            raw_concepts=[
                (
                    "CommonStockShares"
                    "Outstanding"
                ),
            ],

            label_regex=(
                r"common.*shares.*"
                r"outstanding"
            ),
        )
    )


    shares = (
        shares_income
        .combine_first(
            shares_balance
        )
    )


    # ========================================================
    # Unified index
    # ========================================================

    series_list = [
        revenue,
        assets,
        ppe,
        goodwill,
        debt,
        shares,
    ]

    valid_series = [
        s
        for s in series_list
        if not s.empty
    ]

    idx = valid_series[
        0
    ].index

    for s in (
        valid_series[1:]
    ):

        idx = idx.union(
            s.index
        )

    idx = idx.sort_values()


    df = pd.DataFrame(
        index=idx
    )

    df["revenue"] = (
        revenue
    )

    df["assets"] = (
        assets
    )

    df["ppe"] = (
        ppe
    )

    df["goodwill"] = (
        goodwill
    )

    df["debt"] = (
        debt
    )

    df["shares"] = (
        shares
    )


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
    # Financial YoY
    # ========================================================

    df["assets_yoy"] = (
        log_growth(
            df["assets"],
            4,
        )
    )

    df["ppe_yoy"] = (
        log_growth(
            df["ppe"],
            4,
        )
    )

    df["debt_yoy"] = (
        log_growth(
            df["debt"],
            4,
        )
    )

    df["shares_yoy"] = (
        log_growth(
            df["shares"],
            4,
        )
    )


    # ========================================================
    # QoQ
    #
    # M&A가 닫히면 갑자기 튀는 변수들
    # ========================================================

    df["assets_qoq"] = (
        log_growth(
            df["assets"],
            1,
        )
    )

    df["ppe_qoq"] = (
        log_growth(
            df["ppe"],
            1,
        )
    )

    df["debt_qoq"] = (
        log_growth(
            df["debt"],
            1,
        )
    )

    df["shares_qoq"] = (
        log_growth(
            df["shares"],
            1,
        )
    )


    # ========================================================
    # Goodwill Jump
    #
    # 단순 % growth가 아니라
    #
    # ΔGoodwill / prior assets
    #
    # 로 측정
    # ========================================================

    prior_assets = (
        df["assets"]
        .shift(1)
    )

    df[
        "goodwill_jump"
    ] = (
        (
            df["goodwill"]
            - df["goodwill"]
            .shift(1)
        )
        /
        prior_assets
        * 100
    )


    # ========================================================
    # M&A Scale Proxy
    #
    # 자산 / PPE / 부채 / 주식수가
    # 갑자기 얼마나 커졌는가?
    #
    # + Goodwill
    # ========================================================

    ma_components = pd.concat(
        [
            df[
                "assets_qoq"
            ].clip(
                lower=0,
                upper=100,
            ),

            df[
                "ppe_qoq"
            ].clip(
                lower=0,
                upper=100,
            ),

            df[
                "debt_qoq"
            ].clip(
                lower=0,
                upper=100,
            ),

            df[
                "shares_qoq"
            ].clip(
                lower=0,
                upper=100,
            ),

            df[
                "goodwill_jump"
            ].clip(
                lower=0,
                upper=100,
            ),
        ],
        axis=1,
    )

    df[
        "ma_scale_proxy"
    ] = (
        ma_components.max(
            axis=1,
            skipna=True,
        )
    )


    # SEC가 현재 AS_OF보다
    # 미래 period를 담고 있으면 제거
    as_of_q = AS_OF.to_period(
        "Q"
    )

    df = df.loc[
        df.index <= as_of_q
    ]

    print(
        f"  Revenue quarters: "
        f"{df['revenue'].notna().sum()}"
    )

    return df


# ============================================================
# 10. 8-K M&A EVENT FEATURES
#
# Item 2.01 =
# Completion of Acquisition or Disposition
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

    try:

        filings = (
            company
            .get_filings(
                form="8-K"
            )
        )

        filings = filings.filter(
            filing_date=(
                f"{start_date}:"
                f"{end_date}"
            )
        )

        filing_df = (
            filings
            .to_pandas()
        )

    except Exception as e:

        print(
            f"  ⚠️ {ticker} "
            f"8-K 로딩 실패: {e}"
        )

        filing_df = (
            pd.DataFrame()
        )


    result = pd.DataFrame(
        index=full_index
    )

    result[
        "ma_event"
    ] = 0.0


    if (
        filing_df is None
        or filing_df.empty
        or "items"
        not in filing_df.columns
    ):

        result[
            "ma_5q_window"
        ] = 0.0

        return result


    # --------------------------------------------------------
    # Item 2.01
    # --------------------------------------------------------

    mask = (
        filing_df["items"]
        .astype(str)
        .str.contains(
            "2.01",
            regex=False,
            na=False,
        )
    )

    events = (
        filing_df.loc[
            mask
        ]
        .copy()
    )


    if events.empty:

        result[
            "ma_5q_window"
        ] = 0.0

        return result


    # --------------------------------------------------------
    # Event date
    # --------------------------------------------------------

    report_col = None

    for c in [
        "reportDate",
        "report_date",
        "period_of_report",
    ]:

        if c in events.columns:

            report_col = c
            break


    if report_col:

        event_date = (
            pd.to_datetime(
                events[
                    report_col
                ],
                errors="coerce",
            )
        )

    else:

        event_date = (
            pd.Series(
                pd.NaT,
                index=events.index,
            )
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
        event_date
        .fillna(
            filing_date
        )
    )


    event_quarters = (
        event_date
        .dropna()
        .dt.to_period(
            "Q"
        )
    )


    for q in event_quarters:

        if q in result.index:

            result.loc[
                q,
                "ma_event"
            ] = 1.0


    # ========================================================
    # M&A YoY base distortion
    #
    # acquisition quarter
    # +
    # 다음 4 quarters
    # ========================================================

    result[
        "ma_5q_window"
    ] = 0.0

    for lag in range(
        5
    ):

        result[
            "ma_5q_window"
        ] += (
            result[
                "ma_event"
            ]
            .shift(
                lag
            )
            .fillna(0)
        )


    result[
        "ma_5q_window"
    ] = (
        result[
            "ma_5q_window"
        ]
        .clip(
            0,
            1,
        )
    )


    print(
        f"  {ticker} Item 2.01 "
        f"events: "
        f"{int(result['ma_event'].sum())}"
    )

    return result


# ============================================================
# 11. COMPANY DATASET
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


    # --------------------------------------------------------
    # M&A Events
    # --------------------------------------------------------

    ma = get_ma_8k_features(
        ticker,
        idx,
    )


    df = (
        macro
        .reindex(
            idx
        )
        .copy()
    )


    # --------------------------------------------------------
    # Target
    # --------------------------------------------------------

    df["revenue"] = (
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
    # 직전 분기 재무자료만 사용
    #
    # CURRENT Q revenue를 맞힐 때
    # CURRENT Q 10-Q를 사용하면
    # look-ahead
    # ========================================================

    financial_cols = [
        "revenue_yoy",
        "assets_yoy",
        "ppe_yoy",
        "debt_yoy",
        "shares_yoy",
        "goodwill_jump",
        "ma_scale_proxy",
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


    # --------------------------------------------------------
    # M&A event
    # --------------------------------------------------------

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
        "ma_5q_window"
    ] = (
        ma[
            "ma_5q_window"
        ]
        .reindex(idx)
        .fillna(0)
    )


    # ========================================================
    # M&A structural growth interaction
    #
    # 최근 M&A가 있고,
    # 자산/PPE/주식수가 전년보다 크게 늘었다면
    # Revenue YoY base가 바뀌었다고 판단
    # ========================================================

    size_candidates = pd.concat(
        [
            df[
                "assets_yoy_l1"
            ],

            df[
                "ppe_yoy_l1"
            ],

            df[
                "shares_yoy_l1"
            ],
        ],
        axis=1,
    )


    df[
        "size_growth_proxy_l1"
    ] = (
        size_candidates.max(
            axis=1,
            skipna=True,
        )
        .clip(
            lower=-100,
            upper=150,
        )
    )


    df[
        "ma_base_distortion"
    ] = (
        df[
            "ma_5q_window"
        ]
        *
        df[
            "size_growth_proxy_l1"
        ]
    )


    df["ticker"] = (
        ticker
    )

    df["quarter"] = (
        df.index
    )

    return df


# ============================================================
# 12. V2 FEATURES
# ============================================================

FEATURES_V2 = [

    # ========================================================
    # 가격
    # ========================================================

    "wti_yoy",

    "henry_yoy",


    # ========================================================
    # 산업 물량
    # ========================================================

    "crude_prod_yoy_l1",

    "gas_prod_yoy_l1",


    # ========================================================
    # BEA 산업 baseline
    # ========================================================

    "bea_go_yoy_l1",


    # ========================================================
    # 회사 momentum
    # ========================================================

    "revenue_yoy_l1",


    # ========================================================
    # 회사 덩치 / M&A
    # ========================================================

    "assets_yoy_l1",

    "ppe_yoy_l1",

    "debt_yoy_l1",

    "shares_yoy_l1",

    "goodwill_jump_l1",

    "ma_scale_proxy_l1",


    # ========================================================
    # 8-K M&A
    # ========================================================

    "ma_event",

    "ma_5q_window",


    # ========================================================
    # M&A × 재무 구조 변화
    # ========================================================

    "ma_base_distortion",
]


# ============================================================
# 13. PANEL DATASET
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
                f"DATA ERROR:"
            )

            print(
                repr(e)
            )


    if not frames:

        raise ValueError(
            "사용 가능한 종목 "
            "데이터가 없어."
        )


    panel = pd.concat(
        frames,
        axis=0,
        ignore_index=True,
    )


    panel["quarter"] = (
        pd.PeriodIndex(
            panel["quarter"],
            freq="Q",
        )
    )


    panel = panel.sort_values(
        [
            "quarter",
            "ticker",
        ]
    ).reset_index(
        drop=True
    )


    return panel


# ============================================================
# 14. MODEL DESIGN MATRIX
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


    # --------------------------------------------------------
    # ticker fixed effect
    #
    # 첫 ticker는 기준
    # --------------------------------------------------------

    base_ticker = (
        TICKERS[0]
    )

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


def fill_missing_from_train(
    X_train,
    X_test,
):

    X_train = (
        X_train
        .copy()
    )

    X_test = (
        X_test
        .copy()
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
    )


# ============================================================
# 15. RIDGE
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
# 16. TIME-SERIES ALPHA SELECTION
#
# Random CV 사용 안 함
# ============================================================

def select_alpha(
    train_df,
    features,
):

    quarters = sorted(
        train_df[
            "quarter"
        ]
        .unique()
    )


    # history 부족하면
    # 적당한 regularization
    if len(quarters) < 10:

        return 10.0


    # 최근 최대 4분기를
    # 내부 validation
    validation_quarters = (
        quarters[
            -min(
                4,
                len(quarters) - 6,
            ):
        ]
    )


    best_alpha = (
        10.0
    )

    best_mae = (
        np.inf
    )


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


            error = (
                mean_absolute_error(
                    y_test,
                    pred,
                )
            )

            errors.append(
                error
            )


        if not errors:

            continue


        avg_mae = (
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
# 17. WALK-FORWARD PANEL VALIDATION
# ============================================================

def walk_forward_validation(
    panel,
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
            "Walk-forward용 "
            "history가 부족해."
        )


    start_test_pos = max(
        MIN_TRAIN_QUARTERS,
        len(quarters)
        - TEST_QUARTERS,
    )


    test_quarters = (
        quarters[
            start_test_pos:
        ]
    )


    records = []


    print(
        "\n"
        + "=" * 80
    )

    print(
        "PANEL WALK-FORWARD VALIDATION"
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


        alpha = select_alpha(
            train,
            FEATURES_V2,
        )


        X_train = (
            make_design_matrix(
                train,
                FEATURES_V2,
            )
        )

        X_test = (
            make_design_matrix(
                test,
                FEATURES_V2,
            )
        )


        (
            X_train,
            X_test,
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


        pred = (
            model.predict(
                X_test
            )
        )


        for (
            (_, row),
            prediction
        ) in zip(
            test.iterrows(),
            pred,
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
                            prediction
                        ),

                    # Revenue YoY = 0%
                    # naive benchmark
                    "naive":
                        0.0,

                    "alpha":
                        alpha,
                }
            )


    result = pd.DataFrame(
        records
    )


    if result.empty:

        raise ValueError(
            "Validation 결과 없음"
        )


    # ========================================================
    # Overall metrics
    # ========================================================

    mae = (
        mean_absolute_error(
            result[
                "actual"
            ],
            result[
                "predicted"
            ],
        )
    )


    rmse = np.sqrt(
        mean_squared_error(
            result[
                "actual"
            ],
            result[
                "predicted"
            ],
        )
    )


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


    improvement = (
        (
            naive_mae
            - mae
        )
        /
        naive_mae
        * 100
    )


    print(
        f"\nOverall V2 MAE  : "
        f"{mae:.2f} pp"
    )

    print(
        f"Overall V2 RMSE : "
        f"{rmse:.2f} pp"
    )

    print(
        f"Naive MAE       : "
        f"{naive_mae:.2f} pp"
    )

    print(
        f"MAE improvement : "
        f"{improvement:+.1f}%"
    )


    # ========================================================
    # By ticker
    # ========================================================

    ticker_metrics = []


    for ticker, group in (
        result.groupby(
            "ticker"
        )
    ):

        t_mae = (
            mean_absolute_error(
                group[
                    "actual"
                ],
                group[
                    "predicted"
                ],
            )
        )


        t_rmse = np.sqrt(
            mean_squared_error(
                group[
                    "actual"
                ],
                group[
                    "predicted"
                ],
            )
        )


        t_naive = (
            mean_absolute_error(
                group[
                    "actual"
                ],
                group[
                    "naive"
                ],
            )
        )


        ticker_metrics.append(
            {
                "ticker":
                    ticker,

                "V2_MAE":
                    t_mae,

                "V2_RMSE":
                    t_rmse,

                "Naive_MAE":
                    t_naive,

                "improvement_pct":
                    (
                        (
                            t_naive
                            - t_mae
                        )
                        /
                        t_naive
                        * 100
                    ),
            }
        )


    metrics_df = (
        pd.DataFrame(
            ticker_metrics
        )
        .set_index(
            "ticker"
        )
    )


    print(
        "\n===== BY TICKER ====="
    )

    print(
        metrics_df.round(
            2
        )
    )


    print(
        "\n===== LAST VALIDATION ROWS ====="
    )

    print(
        result.tail(
            20
        ).round(
            2
        )
    )


    return (
        result,
        metrics_df,
    )


# ============================================================
# 18. FINAL MODEL + NOWCAST
# ============================================================

def fit_final_and_nowcast(
    panel,
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


    # --------------------------------------------------------
    # time CV alpha
    # --------------------------------------------------------

    alpha = (
        select_alpha(
            history,
            FEATURES_V2,
        )
    )


    print(
        f"\nFinal Ridge alpha: "
        f"{alpha}"
    )


    X_train = (
        make_design_matrix(
            history,
            FEATURES_V2,
        )
    )


    # training median
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
            axis=0
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
    # Nowcast rows
    # ========================================================

    nowcast_rows = []


    for ticker in TICKERS:

        ticker_df = (
            panel[
                panel[
                    "ticker"
                ]
                == ticker
            ]
            .copy()
        )


        actual_revenue = (
            ticker_df[
                ticker_df[
                    "revenue"
                ]
                .notna()
            ]
        )


        if actual_revenue.empty:

            print(
                f"⚠️ {ticker}: "
                f"Revenue 없음"
            )

            continue


        last_actual_q = (
            actual_revenue[
                "quarter"
            ]
            .max()
        )


        nowcast_q = (
            last_actual_q
            + 1
        )


        row = (
            ticker_df[
                ticker_df[
                    "quarter"
                ]
                == nowcast_q
            ]
        )


        if row.empty:

            print(
                f"⚠️ {ticker}: "
                f"{nowcast_q} "
                f"feature 없음"
            )

            continue


        row = row.iloc[
            0
        ].copy()


        row[
            "nowcast_quarter"
        ] = nowcast_q


        nowcast_rows.append(
            row
        )


    if not nowcast_rows:

        raise ValueError(
            "Nowcast 가능한 "
            "종목 없음"
        )


    now_df = pd.DataFrame(
        nowcast_rows
    )


    # --------------------------------------------------------
    # Design
    # --------------------------------------------------------

    X_now = (
        make_design_matrix(
            now_df,
            FEATURES_V2,
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


    predictions = (
        model.predict(
            X_now
        )
    )


    now_df[
        "predicted_revenue_yoy"
    ] = predictions


    # ========================================================
    # Revenue level
    #
    # same quarter last year × exp(YoY)
    # ========================================================

    revenue_estimates = []


    for _, row in (
        now_df.iterrows()
    ):

        ticker = (
            row["ticker"]
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
            or pd.isna(
                base.iloc[
                    0
                ][
                    "revenue"
                ]
            )
        ):

            revenue_estimates.append(
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


        estimate = (
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


        revenue_estimates.append(
            estimate
        )


    now_df[
        "predicted_revenue"
    ] = (
        revenue_estimates
    )


    # ========================================================
    # Output
    # ========================================================

    output = (
        now_df[
            [
                "ticker",
                "nowcast_quarter",

                "predicted_revenue_yoy",
                "predicted_revenue",

                "wti_yoy",
                "henry_yoy",

                "assets_yoy_l1",
                "ppe_yoy_l1",

                "ma_scale_proxy_l1",
                "ma_event",
                "ma_5q_window",

                "ma_base_distortion",
            ]
        ]
        .copy()
    )


    output[
        "predicted_revenue_B"
    ] = (
        output[
            "predicted_revenue"
        ]
        /
        1e9
    )


    print(
        "\n"
        + "=" * 80
    )

    print(
        "🚀 ENERGY REVENUE V2 NOWCAST"
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

        "assets_yoy_l1",
        "ppe_yoy_l1",

        "ma_event",
        "ma_5q_window",

        "ma_base_distortion",
    ]


    print(
        output[
            display_cols
        ].round(
            2
        ).to_string(
            index=False
        )
    )


    # ========================================================
    # Coefficients
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


    return (
        model,
        output,
        coefficients,
    )


# ============================================================
# 19. MAIN
# ============================================================

if __name__ == "__main__":

    # ========================================================
    # A. Macro
    # ========================================================

    print(
        "\n"
        + "=" * 80
    )

    print(
        "1. DOWNLOADING MACRO DATA"
    )

    print(
        "=" * 80
    )


    macro = (
        make_macro_features()
    )


    print(
        "\n===== MACRO FEATURES ====="
    )


    macro_cols = [
        "wti_yoy",
        "henry_yoy",
        "crude_prod_yoy_l1",
        "gas_prod_yoy_l1",
        "bea_go_yoy_l1",
    ]


    print(
        macro[
            macro_cols
        ]
        .tail(
            12
        )
        .round(
            2
        )
    )


    # ========================================================
    # B. SEC + M&A
    # ========================================================

    print(
        "\n"
        + "=" * 80
    )

    print(
        "2. BUILDING COMPANY PANEL"
    )

    print(
        "=" * 80
    )


    panel = build_panel(
        macro
    )


    print(
        "\nPanel shape:",
        panel.shape,
    )


    print(
        "\nRevenue observations "
        "by ticker:"
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
    # C. Walk-forward
    # ========================================================

    validation, metrics = (
        walk_forward_validation(
            panel
        )
    )


    # ========================================================
    # D. Final nowcast
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
    # E. Save results
    # ========================================================

    macro.to_csv(
        "energy_v2_macro.csv"
    )


    panel.to_csv(
        "energy_v2_panel.csv",
        index=False,
    )


    validation.to_csv(
        "energy_v2_validation.csv",
        index=False,
    )


    metrics.to_csv(
        "energy_v2_metrics.csv"
    )


    nowcast.to_csv(
        "energy_v2_nowcast.csv",
        index=False,
    )


    coefficients.to_csv(
        "energy_v2_coefficients.csv",
        header=[
            "coefficient"
        ],
    )


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
        "\nSaved:"
    )

    print(
        "energy_v2_macro.csv"
    )

    print(
        "energy_v2_panel.csv"
    )

    print(
        "energy_v2_validation.csv"
    )

    print(
        "energy_v2_metrics.csv"
    )

    print(
        "energy_v2_nowcast.csv"
    )

    print(
        "energy_v2_coefficients.csv"
    )
