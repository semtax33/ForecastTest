import os
import re
import requests
import numpy as np
import pandas as pd
import beaapi

from edgar import Company, set_identity

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import RidgeCV
from sklearn.metrics import (
    mean_absolute_error,
    root_mean_squared_error
)


# ============================================================
# 설정
# ============================================================

EIA_API_KEY = os.getenv("EIA_API_KEY")
BEA_API_KEY = os.getenv("BEA_API_KEY")
EDGAR_IDENTITY = os.getenv("EDGAR_IDENTITY")


if not EIA_API_KEY:
    raise ValueError("EIA_API_KEY 환경변수를 설정해줘.")

if not BEA_API_KEY:
    raise ValueError("BEA_API_KEY 환경변수를 설정해줘.")

if not EDGAR_IDENTITY:
    raise ValueError("EDGAR_IDENTITY 환경변수를 설정해줘.")


set_identity(EDGAR_IDENTITY)


START_YEAR = 2014


# 순수 E&P 위주로 먼저 시작
TICKERS = [
    "COP",
    "EOG",
    "FANG",
    "DVN",
]


# ============================================================
# 1. EIA API
# ============================================================

def get_eia_series(
    series_id,
    api_key,
    start=None,
    length=5000
):
    """
    EIA API v2 Series ID wrapper

    반환:
        DatetimeIndex + value
    """

    url = (
        f"https://api.eia.gov/v2/"
        f"seriesid/{series_id}"
    )

    params = {
        "api_key": api_key,
        "length": length,
    }

    if start is not None:
        params["start"] = start

    r = requests.get(
        url,
        params=params,
        timeout=30
    )

    r.raise_for_status()

    js = r.json()

    try:
        rows = js["response"]["data"]
    except (KeyError, TypeError):
        raise ValueError(
            f"EIA response 이상함:\n{js}"
        )

    df = pd.DataFrame(rows)

    if df.empty:
        raise ValueError(
            f"EIA 데이터 없음: {series_id}"
        )

    # ----------------------------------------
    # 날짜
    # ----------------------------------------

    df["date"] = pd.to_datetime(
        df["period"],
        errors="coerce"
    )

    # ----------------------------------------
    # 숫자 value 컬럼 찾기
    # ----------------------------------------

    if "value" in df.columns:

        value_col = "value"

    else:

        skip = {
            "period",
            "series",
            "series-description",
            "units"
        }

        value_col = None

        for col in df.columns:

            if (
                col in skip
                or col.endswith("-units")
            ):
                continue

            numeric = pd.to_numeric(
                df[col],
                errors="coerce"
            )

            if numeric.notna().sum() > 0:
                value_col = col
                break

        if value_col is None:
            raise ValueError(
                f"EIA numeric column 찾기 실패: "
                f"{df.columns.tolist()}"
            )

    df["value"] = pd.to_numeric(
        df[value_col],
        errors="coerce"
    )

    return (
        df[["date", "value"]]
        .dropna()
        .drop_duplicates("date")
        .set_index("date")
        .sort_index()["value"]
    )


# ============================================================
# 2. EIA Energy 데이터
# ============================================================

def get_energy_eia():

    # --------------------------
    # 가격: Daily
    # --------------------------

    wti = get_eia_series(
        "PET.RWTC.D",
        EIA_API_KEY,
        start=f"{START_YEAR}-01-01"
    )

    henry = get_eia_series(
        "NG.RNGWHHD.D",
        EIA_API_KEY,
        start=f"{START_YEAR}-01-01"
    )

    # --------------------------
    # 생산량: Monthly
    # --------------------------

    crude_prod = get_eia_series(
        "PET.MCRFPUS2.M",
        EIA_API_KEY,
        start=str(START_YEAR)
    )

    gas_prod = get_eia_series(
        "NG.N9070US2.M",
        EIA_API_KEY,
        start=str(START_YEAR)
    )

    wti.name = "wti"
    henry.name = "henry_hub"

    crude_prod.name = "crude_prod"
    gas_prod.name = "gas_prod"

    return {
        "wti": wti,
        "henry_hub": henry,
        "crude_prod": crude_prod,
        "gas_prod": gas_prod,
    }


# ============================================================
# 3. BEA Gross Output
# ============================================================

def get_bea_oil_gas_gross_output():

    """
    GDPbyIndustry에서

    Gross Output by Industry
    Industry = 211
    Oil and gas extraction

    quarterly data
    """

    # ----------------------------------------
    # Table ID를 하드코딩하지 않고
    # BEA metadata에서 찾음
    # ----------------------------------------

    tables = beaapi.get_parameter_values(
        BEA_API_KEY,
        "GDPbyIndustry",
        "TableID"
    )

    mask = (
        tables["Desc"]
        .astype(str)
        .str.match(
            r"^Gross Output by Industry",
            case=False,
            na=False
        )
    )

    candidates = tables.loc[mask]

    if candidates.empty:

        print(tables)

        raise ValueError(
            "BEA Gross Output table을 "
            "찾지 못했어."
        )

    table_id = candidates.iloc[0]["Key"]

    print(
        "BEA Gross Output TableID:",
        table_id
    )

    print(
        "Description:",
        candidates.iloc[0]["Desc"]
    )

    # ----------------------------------------
    # Oil & Gas Extraction = 211
    # ----------------------------------------

    df = beaapi.get_data(
        BEA_API_KEY,
        "GDPbyIndustry",
        TableID=table_id,
        Frequency="Q",
        Year="ALL",
        Industry="211",
    )

    df = df.copy()

    df["DataValue"] = (
        df["DataValue"]
        .astype(str)
        .str.replace(",", "", regex=False)
    )

    df["gross_output"] = pd.to_numeric(
        df["DataValue"],
        errors="coerce"
    )

    # BEA Quarter:
    # I / II / III / IV
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
        subset=["q_num", "gross_output"]
    )

    df["quarter"] = pd.PeriodIndex(
        df["Year"].astype(str)
        + "Q"
        + df["q_num"].astype(int).astype(str),
        freq="Q"
    )

    result = (
        df[
            [
                "quarter",
                "gross_output"
            ]
        ]
        .drop_duplicates("quarter")
        .set_index("quarter")
        .sort_index()
    )

    return result


# ============================================================
# 4. EdgarTools: quarterly Revenue
# ============================================================

def parse_edgar_quarter_label(label):
    """
    EdgarTools statement column:

        Q1 2024
        Q2 2024

    -> pandas Period
    """

    label = str(label).strip()

    match = re.search(
        r"Q([1-4])\s+(\d{4})",
        label,
        flags=re.IGNORECASE
    )

    if not match:
        return None

    q = int(match.group(1))
    year = int(match.group(2))

    return pd.Period(
        f"{year}Q{q}",
        freq="Q"
    )


def parse_edgar_period_column(col):
    """
    EdgarTools의 기간 컬럼을 pandas Period('2025Q1') 형태로 변환.

    지원 예:
        2025-03-31
        2025-06-30
        Q1 2025
        Q2 2025
        2025Q1
    """

    s = str(col).strip()

    # -----------------------------------
    # 1) YYYY-MM-DD
    # -----------------------------------

    if re.fullmatch(
        r"\d{4}-\d{2}-\d{2}",
        s
    ):

        dt = pd.to_datetime(
            s,
            errors="coerce"
        )

        if pd.notna(dt):
            return dt.to_period("Q")

    # -----------------------------------
    # 2) Q1 2025
    # -----------------------------------

    m = re.fullmatch(
        r"Q([1-4])\s+(\d{4})",
        s,
        flags=re.IGNORECASE
    )

    if m:

        q = int(m.group(1))
        year = int(m.group(2))

        return pd.Period(
            f"{year}Q{q}",
            freq="Q"
        )

    # -----------------------------------
    # 3) 2025Q1
    # -----------------------------------

    m = re.fullmatch(
        r"(\d{4})Q([1-4])",
        s,
        flags=re.IGNORECASE
    )

    if m:

        year = int(m.group(1))
        q = int(m.group(2))

        return pd.Period(
            f"{year}Q{q}",
            freq="Q"
        )

    return None


def clean_financial_number(value):

    if pd.isna(value):
        return np.nan

    if isinstance(
        value,
        (int, float, np.integer, np.floating)
    ):
        return float(value)

    s = str(value).strip()

    # $, comma 제거
    s = (
        s
        .replace("$", "")
        .replace(",", "")
        .strip()
    )

    # (123) → -123
    if (
        s.startswith("(")
        and s.endswith(")")
    ):
        s = "-" + s[1:-1]

    return pd.to_numeric(
        s,
        errors="coerce"
    )


def get_quarterly_revenue(
    ticker,
    periods=48
):

    print(
        f"\nSEC downloading: {ticker}"
    )

    company = Company(ticker)

    facts = company.get_facts()

    # ========================================================
    # 핵심 수정
    #
    # as_dataframe=True
    #
    # MultiPeriodStatement를 직접 다루지 않고
    # 처음부터 pandas DataFrame으로 받음
    # ========================================================

    stmt_df = facts.income_statement(
        periods=periods,
        annual=False,
        as_dataframe=True
    )

    # 이제 진짜 pandas DataFrame이므로
    # .empty 사용 가능
    if (
        stmt_df is None
        or stmt_df.empty
    ):

        raise ValueError(
            f"{ticker}: income statement 없음"
        )

    # ----------------------------------------
    # 디버깅용
    # ----------------------------------------

    print(
        f"{ticker} statement shape:",
        stmt_df.shape
    )

    # ========================================================
    # 기간 column 찾기
    # ========================================================

    period_cols = []

    for col in stmt_df.columns:

        quarter = parse_edgar_period_column(
            col
        )

        if quarter is not None:
            period_cols.append(col)

    if not period_cols:

        print(
            "\nStatement columns:"
        )

        print(
            stmt_df.columns.tolist()
        )

        raise ValueError(
            f"{ticker}: 분기 column을 찾지 못했어."
        )

    # ========================================================
    # Revenue row 찾기
    #
    # 최신 EdgarTools는
    # standard_concept = Revenue
    # 형태를 제공
    # ========================================================

    revenue_rows = None

    if "standard_concept" in stmt_df.columns:

        revenue_rows = stmt_df[
            stmt_df[
                "standard_concept"
            ]
            .astype(str)
            .str.strip()
            .eq("Revenue")
        ]

    # ----------------------------------------
    # fallback 1:
    # standard_concept가 없을 경우
    # label에서 revenue / sales 탐색
    # ----------------------------------------

    if (
        revenue_rows is None
        or revenue_rows.empty
    ):

        if "label" in stmt_df.columns:

            revenue_rows = stmt_df[
                stmt_df["label"]
                .astype(str)
                .str.contains(
                    r"revenue|sales",
                    case=False,
                    regex=True,
                    na=False
                )
            ]

    # ----------------------------------------
    # fallback 2:
    # index 자체가 Revenue인 구조
    # ----------------------------------------

    if (
        revenue_rows is None
        or revenue_rows.empty
    ):

        index_str = (
            stmt_df.index
            .astype(str)
        )

        mask = (
            index_str
            .str.contains(
                r"revenue|sales",
                case=False,
                regex=True
            )
        )

        revenue_rows = (
            stmt_df.loc[mask]
        )

    if revenue_rows.empty:

        print(
            "\nAvailable concepts:"
        )

        show_cols = [
            c
            for c in [
                "label",
                "concept",
                "standard_concept"
            ]
            if c in stmt_df.columns
        ]

        if show_cols:

            print(
                stmt_df[
                    show_cols
                ].head(100)
            )

        else:

            print(
                stmt_df.head(50)
            )

        raise ValueError(
            f"{ticker}: Revenue row 찾기 실패"
        )

    # ========================================================
    # Revenue 후보가 여러 개일 수도 있음
    #
    # 데이터가 가장 많이 채워진 행을
    # consolidated revenue 후보로 선택
    # ========================================================

    if len(revenue_rows) > 1:

        coverage = (
            revenue_rows[
                period_cols
            ]
            .notna()
            .sum(axis=1)
        )

        best_idx = coverage.idxmax()

        revenue_row = (
            revenue_rows.loc[
                best_idx
            ]
        )

    else:

        revenue_row = (
            revenue_rows.iloc[0]
        )

    # ----------------------------------------
    # 어떤 revenue를 선택했는지 확인
    # ----------------------------------------

    if "label" in revenue_row.index:

        print(
            f"{ticker} revenue label:",
            revenue_row["label"]
        )

    if (
        "standard_concept"
        in revenue_row.index
    ):

        print(
            f"{ticker} standard concept:",
            revenue_row[
                "standard_concept"
            ]
        )

    # ========================================================
    # wide → quarterly time series
    # ========================================================

    records = []

    for col in period_cols:

        quarter = (
            parse_edgar_period_column(
                col
            )
        )

        value = clean_financial_number(
            revenue_row[col]
        )

        if (
            quarter is not None
            and pd.notna(value)
        ):

            records.append(
                {
                    "quarter": quarter,
                    "revenue": float(value)
                }
            )

    result = pd.DataFrame(
        records
    )

    if result.empty:

        raise ValueError(
            f"{ticker}: Revenue 값은 찾았는데 "
            f"숫자 데이터 parsing 실패"
        )

    result = (
        result
        .sort_values("quarter")
        .drop_duplicates(
            "quarter",
            keep="last"
        )
        .set_index("quarter")
    )

    print(
        f"{ticker}: "
        f"{len(result)} quarters loaded"
    )

    print(
        result.tail(8)
    )

    return result


# ============================================================
# 5. Macro → Quarterly feature
# ============================================================

def make_macro_features():

    eia = get_energy_eia()

    # ----------------------------------------
    # 가격:
    #
    # daily → quarterly average
    #
    # 현재 분기가 아직 끝나지 않았다면
    # 현재까지의 평균 가격 자체가
    # partial-quarter nowcast가 됨.
    # ----------------------------------------

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
        .rename("henry_hub")
    )

    # ----------------------------------------
    # 생산량:
    #
    # monthly → quarterly average
    #
    # 3개월이 모두 있는 완성된 분기만
    # 정상 quarterly observation으로 사용
    # ----------------------------------------

    def complete_quarter_mean(series):

        periods = (
            series
            .index
            .to_period("Q")
        )

        mean = series.groupby(
            periods
        ).mean()

        count = series.groupby(
            periods
        ).count()

        # 3개월 미만이면 incomplete
        mean[count < 3] = np.nan

        return mean

    crude_q = (
        complete_quarter_mean(
            eia["crude_prod"]
        )
        .rename("crude_prod")
    )

    gas_q = (
        complete_quarter_mean(
            eia["gas_prod"]
        )
        .rename("gas_prod")
    )

    # ----------------------------------------
    # BEA
    # ----------------------------------------

    bea_q = (
        get_bea_oil_gas_gross_output()
        ["gross_output"]
    )

    # ----------------------------------------
    # 전체 quarter index
    # ----------------------------------------

    start = max(
        wti_q.index.min(),
        henry_q.index.min(),
        pd.Period(
            f"{START_YEAR}Q1",
            freq="Q"
        )
    )

    end = max(
        wti_q.index.max(),
        henry_q.index.max()
    )

    idx = pd.period_range(
        start=start,
        end=end,
        freq="Q"
    )

    macro = pd.DataFrame(
        index=idx
    )

    macro["wti"] = wti_q
    macro["henry_hub"] = henry_q
    macro["crude_prod"] = crude_q
    macro["gas_prod"] = gas_q
    macro["bea_gross_output"] = bea_q

    # ========================================
    # YoY growth
    #
    # log growth를 쓰는 이유:
    # raw level regression의 허위상관 감소
    # ========================================

    def yoy_log(series):

        return (
            np.log(
                series
                / series.shift(4)
            )
            * 100
        )

    macro["wti_yoy"] = yoy_log(
        macro["wti"]
    )

    macro["henry_yoy"] = yoy_log(
        macro["henry_hub"]
    )

    crude_yoy = yoy_log(
        macro["crude_prod"]
    )

    gas_yoy = yoy_log(
        macro["gas_prod"]
    )

    bea_yoy = yoy_log(
        macro["bea_gross_output"]
    )

    # ========================================
    # 중요한 부분
    #
    # 생산량과 BEA는 발표가 느림.
    #
    # current-quarter revenue를
    # 예측하면서 current-quarter BEA를
    # 넣으면 미래를 본 꼴이 될 수 있음.
    #
    # 따라서 V1에서는 1Q lag.
    # ========================================

    macro["crude_prod_yoy_l1"] = (
        crude_yoy
        .shift(1)
        .ffill()
    )

    macro["gas_prod_yoy_l1"] = (
        gas_yoy
        .shift(1)
        .ffill()
    )

    macro["bea_go_yoy_l1"] = (
        bea_yoy
        .shift(1)
        .ffill()
    )

    return macro


# ============================================================
# 6. 회사별 학습 데이터 만들기
# ============================================================

FEATURES = [
    "wti_yoy",
    "henry_yoy",
    "crude_prod_yoy_l1",
    "gas_prod_yoy_l1",
    "bea_go_yoy_l1",
]


def make_company_dataset(
    ticker,
    macro
):

    revenue = get_quarterly_revenue(
        ticker
    )

    # Revenue YoY
    revenue["revenue_yoy"] = (
        np.log(
            revenue["revenue"]
            / revenue["revenue"].shift(4)
        )
        * 100
    )

    df = revenue.join(
        macro,
        how="left"
    )

    return df


# ============================================================
# 7. Regression
# ============================================================

def fit_energy_revenue_model(
    ticker,
    macro
):

    df = make_company_dataset(
        ticker,
        macro
    )

    train = (
        df[
            ["revenue_yoy"]
            + FEATURES
        ]
        .dropna()
        .copy()
    )

    if len(train) < 16:

        raise ValueError(
            f"{ticker}: 학습 데이터가 "
            f"너무 적음 ({len(train)} quarters)"
        )

    X = train[FEATURES]
    y = train["revenue_yoy"]

    # ----------------------------------------
    # 마지막 4개 분기 hold-out
    #
    # Random split 절대 안 함.
    # 시계열은 과거 → 미래로 검증.
    # ----------------------------------------

    test_size = min(
        4,
        max(
            1,
            len(train) // 5
        )
    )

    X_train = X.iloc[:-test_size]
    y_train = y.iloc[:-test_size]

    X_test = X.iloc[-test_size:]
    y_test = y.iloc[-test_size:]

    # ----------------------------------------
    # Ridge
    #
    # WTI, Gross Output, 생산량 등이
    # 서로 상관성이 높기 때문에
    # plain OLS보다 V1에서는 안정적.
    # ----------------------------------------

    model = Pipeline(
        [
            (
                "scale",
                StandardScaler()
            ),
            (
                "ridge",
                RidgeCV(
                    alphas=np.logspace(
                        -3,
                        3,
                        100
                    )
                )
            ),
        ]
    )

    model.fit(
        X_train,
        y_train
    )

    pred = model.predict(
        X_test
    )

    mae = mean_absolute_error(
        y_test,
        pred
    )

    rmse = root_mean_squared_error(
        y_test,
        pred
    )

    print(
        f"\n{'=' * 60}"
    )

    print(
        f"{ticker} validation"
    )

    print(
        f"{'=' * 60}"
    )

    print(
        f"Training observations : "
        f"{len(X_train)}"
    )

    print(
        f"Test observations     : "
        f"{len(X_test)}"
    )

    print(
        f"MAE                   : "
        f"{mae:.2f} %-point"
    )

    print(
        f"RMSE                  : "
        f"{rmse:.2f} %-point"
    )

    # ----------------------------------------
    # 테스트 예측 확인
    # ----------------------------------------

    compare = pd.DataFrame(
        {
            "actual_yoy":
                y_test,

            "predicted_yoy":
                pred,
        },
        index=y_test.index
    )

    print(
        "\nHoldout:"
    )

    print(
        compare.round(2)
    )

    # ========================================
    # Nowcast
    # ========================================

    # 최신 actual revenue quarter
    last_actual_q = (
        df["revenue"]
        .dropna()
        .index
        .max()
    )

    nowcast_q = (
        last_actual_q + 1
    )

    if nowcast_q not in macro.index:

        print(
            f"\n{ticker}: "
            f"{nowcast_q} macro data가 "
            f"아직 없어."
        )

        return {
            "ticker": ticker,
            "model": model,
            "data": df,
            "mae": mae,
            "rmse": rmse,
        }

    X_now = (
        macro.loc[
            [nowcast_q],
            FEATURES
        ]
    )

    if X_now.isna().any().any():

        print(
            "\nNowcast feature missing:"
        )

        print(
            X_now.T
        )

        return {
            "ticker": ticker,
            "model": model,
            "data": df,
            "mae": mae,
            "rmse": rmse,
        }

    # ----------------------------------------
    # 전체 history로 재학습
    # ----------------------------------------

    final_model = Pipeline(
        [
            (
                "scale",
                StandardScaler()
            ),
            (
                "ridge",
                RidgeCV(
                    alphas=np.logspace(
                        -3,
                        3,
                        100
                    )
                )
            ),
        ]
    )

    final_model.fit(
        X,
        y
    )

    pred_yoy = float(
        final_model.predict(
            X_now
        )[0]
    )

    # ----------------------------------------
    # YoY growth → Revenue level
    #
    # 이번 분기 매출
    # =
    # 작년 같은 분기 매출
    # × exp(predicted growth)
    # ----------------------------------------

    base_q = (
        nowcast_q - 4
    )

    if base_q in df.index:

        base_revenue = (
            df.loc[
                base_q,
                "revenue"
            ]
        )

        predicted_revenue = (
            base_revenue
            * np.exp(
                pred_yoy / 100
            )
        )

    else:

        predicted_revenue = np.nan

    # ----------------------------------------
    # coefficient
    # StandardScaler 이후 coefficient라
    # 상대적인 중요도 해석용
    # ----------------------------------------

    ridge = final_model.named_steps[
        "ridge"
    ]

    coef = pd.Series(
        ridge.coef_,
        index=FEATURES
    ).sort_values(
        key=np.abs,
        ascending=False
    )

    print(
        f"\n🚀 {ticker} "
        f"{nowcast_q} NOWCAST"
    )

    print(
        f"Revenue YoY estimate : "
        f"{pred_yoy:+.2f}%"
    )

    if pd.notna(
        predicted_revenue
    ):

        print(
            f"Revenue estimate     : "
            f"${predicted_revenue / 1e9:,.2f}B"
        )

    print(
        "\nStandardized coefficients:"
    )

    print(
        coef.round(3)
    )

    return {
        "ticker": ticker,
        "model": final_model,
        "data": df,
        "mae": mae,
        "rmse": rmse,
        "nowcast_quarter": nowcast_q,
        "revenue_yoy_nowcast": pred_yoy,
        "revenue_nowcast":
            predicted_revenue,
        "coefficients": coef,
    }


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print(
        "Downloading macro data..."
    )

    macro = make_macro_features()

    print(
        "\n===== MACRO FEATURES ====="
    )

    print(
        macro[
            FEATURES
        ]
        .tail(12)
        .round(2)
    )

    results = {}

    for ticker in TICKERS:

        try:

            result = (
                fit_energy_revenue_model(
                    ticker,
                    macro
                )
            )

            results[ticker] = result

        except Exception as e:

            print(
                f"\n❌ {ticker} ERROR:"
            )

            print(e)
