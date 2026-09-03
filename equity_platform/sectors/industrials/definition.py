from equity_platform.domain import AnchorDefinition, SectorDefinition


INDUSTRIALS_V1 = SectorDefinition(
    sector="Industrials",
    subindustry="Machinery",
    tickers=("CAT",),
    anchors=(
        AnchorDefinition(
            name="ORDERS_BACKLOG_SHIPMENTS",
            unit="USD",
            financial_targets=("REVENUE", "OPERATING_MARGIN"),
            source_concepts=("RevenueRemainingPerformanceObligation",),
        ),
    ),
)
