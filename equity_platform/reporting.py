from __future__ import annotations

from pathlib import Path
from typing import Mapping

import pandas as pd


def markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows._"
    values = frame.copy().fillna("").astype(str)
    header = "| " + " | ".join(values.columns) + " |"
    separator = "| " + " | ".join("---" for _ in values.columns) + " |"
    rows = [
        "| " + " | ".join(value.replace("|", "\\|") for value in row) + " |"
        for row in values.itertuples(index=False, name=None)
    ]
    return "\n".join([header, separator, *rows])


def write_csv_artifacts(
    output_directory: Path,
    artifacts: Mapping[str, pd.DataFrame],
) -> list[Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for name, frame in artifacts.items():
        target = output_directory / f"{name}.csv"
        frame.to_csv(target, index=False)
        paths.append(target)
    return paths
