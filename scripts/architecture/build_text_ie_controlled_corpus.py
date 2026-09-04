from __future__ import annotations

import json
from pathlib import Path

from equity_platform.paths import PROJECT_ROOT


OUTPUT = PROJECT_ROOT / "data-lake/gold/parser/text_ie/controlled_semantic_frames.jsonl"


def _row(
    example_id: str,
    text: str,
    expected_frames: list[dict[str, object]],
    *,
    year: int,
    heading: str | None = None,
    facts: int = 0,
    claims: int = 0,
    reviews: int = 0,
    relations: int = 0,
) -> dict[str, object]:
    return {
        "example_id": example_id,
        "entity": "CONTROLLED",
        "document_period": str(year),
        "heading": heading,
        "text": text,
        "expected_frames": expected_frames,
        "expected_fact_count": facts,
        "expected_claim_count": claims,
        "expected_review_count": reviews,
        "expected_relation_count": relations,
        "annotation_source": "CONTROLLED_TEMPLATE_V1",
    }


def build_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    money_metrics = (
        ("Total backlog", "BACKLOG"),
        ("Revenue", "REVENUE"),
        ("Capital expenditures", "CAPEX"),
    )
    for index in range(25):
        year = 2021 + index % 5
        label, concept = money_metrics[index % len(money_metrics)]
        value = round(1.0 + index / 10.0, 1)
        pct = 5 + index % 20
        rows.append(
            _row(
                f"controlled.change_to.{index:02d}",
                f"{label} increased {pct}% to ${value:.1f} billion at year-end.",
                [{"concept": concept, "frame": "CHANGE_TO", "value": value * 1e9, "change": float(pct), "scope": "AEROSPACE", "period": str(year)}],
                year=year,
                heading="Aerospace",
                facts=1,
            )
        )
        rows.append(
            _row(
                f"controlled.absolute.{index:02d}",
                f"{label} was ${value:.1f} billion.",
                [{"concept": concept, "frame": "ABSOLUTE_VALUE", "value": value * 1e9, "period": str(year)}],
                year=year,
                facts=1,
            )
        )
        high = value + 0.5
        rows.append(
            _row(
                f"controlled.range.{index:02d}",
                f"Revenue is expected between ${value:.1f} billion and ${high:.1f} billion in {year + 1}.",
                [{"concept": "REVENUE_GUIDANCE", "frame": "RANGE_GUIDANCE", "value": (value + high) / 2 * 1e9, "period": str(year + 1)}],
                year=year,
                facts=2,
            )
        )
        basis_points = 10 + index * 5
        rows.append(
            _row(
                f"controlled.change_by.{index:02d}",
                f"Operating margin declined by {basis_points}bp.",
                [{"concept": "OPERATING_MARGIN_CHANGE", "frame": "CHANGE_BY", "value": float(basis_points)}],
                year=year,
                facts=1,
            )
        )
        deliveries = 20 + index
        rows.append(
            _row(
                f"controlled.count.{index:02d}",
                f"Aircraft deliveries totaled {deliveries} aircraft during the quarter.",
                [{"concept": "DELIVERIES", "frame": "COUNT_ACTIVITY", "value": float(deliveries)}],
                year=year,
                facts=1,
            )
        )
        rate = round(0.8 + index / 20.0, 2)
        rows.append(
            _row(
                f"controlled.rate.{index:02d}",
                f"Book-to-bill was {rate:.2f}x.",
                [{"concept": "BOOK_TO_BILL", "frame": "RATE", "value": rate}],
                year=year,
                facts=1,
            )
        )
        rows.append(
            _row(
                f"controlled.cause_negated.{index:02d}",
                "We do not expect supply chain constraints to materially affect deliveries.",
                [{"concept": "SUPPLY_CONSTRAINT", "frame": "CAUSE_EFFECT", "polarity": "NEGATED"}, {"concept": "DELIVERIES", "frame": "CAUSE_EFFECT", "polarity": "NEGATED"}],
                year=year,
                claims=2,
                relations=1,
            )
        )
        rows.append(
            _row(
                f"controlled.cause_positive.{index:02d}",
                "Higher aircraft deliveries increased revenue.",
                [{"concept": "DELIVERIES", "frame": "CAUSE_EFFECT", "polarity": "POSITIVE"}, {"concept": "REVENUE", "frame": "CAUSE_EFFECT", "polarity": "POSITIVE"}],
                year=year,
                claims=2,
                relations=1,
            )
        )
        total = round(10.0 + index, 1)
        excluded = round(2.0 + index / 10.0, 1)
        rows.append(
            _row(
                f"controlled.context.{index:02d}",
                f"Total backlog at year-end was ${total:.1f} billion. Of this amount, ${excluded:.1f} billion is not expected to be filled in {year + 1}.",
                [{"concept": "BACKLOG", "frame": "ABSOLUTE_VALUE", "value": total * 1e9, "scope": "MARINE_SYSTEMS", "period": str(year)}, {"concept": "BACKLOG_NOT_EXPECTED", "frame": "NOT_EXPECTED", "value": excluded * 1e9, "scope": "MARINE_SYSTEMS", "period": str(year + 1)}],
                year=year,
                heading="Marine Systems",
                facts=2,
            )
        )
        if index % 2 == 0:
            rows.append(
                _row(
                    f"controlled.ambiguous.{index:02d}",
                    f"Revenue and backlog increased {pct}% to ${value:.1f} billion.",
                    [],
                    year=year,
                    reviews=1,
                )
            )
        else:
            rows.append(
                _row(
                    f"controlled.negative.{index:02d}",
                    "The board discussed market conditions during the quarter.",
                    [],
                    year=year,
                )
            )
    return rows


def main() -> int:
    rows = build_rows()
    if len(rows) != 250:
        raise ValueError(f"Expected 250 controlled examples, received {len(rows)}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(f"wrote {len(rows)} examples to {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

