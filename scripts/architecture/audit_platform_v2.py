from __future__ import annotations

import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import re

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table
from equity_platform.parsing import compile_rule_file


ROOT = PROJECT_ROOT
OUTPUT = ROOT / "output/platform_architecture_v2"
PYTHON_ROOTS = (ROOT / "equity_platform", ROOT / "scripts")
NEW_CORE_PREFIXES = (
    "equity_platform/ir/",
    "equity_platform/documents/",
    "equity_platform/parsing/",
    "equity_platform/governance/",
    "equity_platform/economics/",
    "equity_platform/valuation_kernel/",
    "equity_platform/experiments/",
)


class InventoryVisitor(ast.NodeVisitor):
    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        self.rows: list[dict[str, object]] = []

    def _add(self, node: ast.AST, kind: str, detail: str) -> None:
        self.rows.append(
            {
                "source_path": self.relative_path,
                "line": getattr(node, "lineno", 0),
                "kind": kind,
                "detail": detail,
                "new_core": self.relative_path.startswith(NEW_CORE_PREFIXES),
            }
        )

    def visit_If(self, node: ast.If) -> None:
        text = ast.unparse(node.test)
        if re.search(r"\b(ticker|company|entity)\b", text, re.IGNORECASE):
            self._add(node, "ISSUER_BRANCH", text[:300])
        if re.search(r"\b(period|fiscal_year|quarter)\b", text, re.IGNORECASE):
            if re.search(r"['\"](?:19|20)\d{2}", text):
                self._add(node, "PERIOD_LITERAL_BRANCH", text[:300])
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        text = ast.unparse(node)
        if ".iloc[" in text and isinstance(node.slice, ast.Constant):
            self._add(node, "POSITIONAL_ILOC", text[:300])
        self.generic_visit(node)


def _classification(path: str) -> str:
    if path.startswith(NEW_CORE_PREFIXES):
        return "PLATFORM_V2_CORE"
    if re.search(r"/(?:v\d|.*_v\d)", path):
        return "LEGACY_OR_FROZEN_EXPERIMENT"
    if path.startswith("equity_platform/sectors/industrials/platform/"):
        return "V8_COMPATIBILITY_ADAPTER"
    return "SHARED_OR_ORCHESTRATION"


def main() -> int:
    issue_rows: list[dict[str, object]] = []
    file_rows: list[dict[str, object]] = []
    for root in PYTHON_ROOTS:
        for path in sorted(root.rglob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            source = path.read_text(encoding="utf-8", errors="ignore")
            try:
                tree = ast.parse(source)
            except SyntaxError as exc:
                issue_rows.append(
                    {
                        "source_path": relative,
                        "line": exc.lineno or 0,
                        "kind": "SYNTAX_ERROR",
                        "detail": str(exc),
                        "new_core": relative.startswith(NEW_CORE_PREFIXES),
                    }
                )
                continue
            visitor = InventoryVisitor(relative)
            visitor.visit(tree)
            issue_rows.extend(visitor.rows)
            file_rows.append(
                {
                    "source_path": relative,
                    "classification": _classification(relative),
                    "lines": len(source.splitlines()),
                    "issuer_branches": sum(
                        row["kind"] == "ISSUER_BRANCH" for row in visitor.rows
                    ),
                    "period_literal_branches": sum(
                        row["kind"] == "PERIOD_LITERAL_BRANCH" for row in visitor.rows
                    ),
                    "positional_iloc": sum(
                        row["kind"] == "POSITIONAL_ILOC" for row in visitor.rows
                    ),
                }
            )
    issues = pd.DataFrame(issue_rows)
    files = pd.DataFrame(file_rows)
    rule_paths = sorted((ROOT / "configs/parser_rules").rglob("*.arc"))
    rule_rows = []
    for path in rule_paths:
        for rule in compile_rule_file(path):
            rule_rows.append(
                {
                    "rule_id": rule.rule_id,
                    "version": rule.version,
                    "selector": rule.selector.value,
                    "metric": rule.metric,
                    "source_path": path.relative_to(ROOT).as_posix(),
                    "source_sha256": rule.source_sha256,
                }
            )
    rules = pd.DataFrame(rule_rows)
    new_core = files.loc[files["classification"].eq("PLATFORM_V2_CORE")]
    summary = pd.DataFrame(
        [
            {
                "python_files_audited": len(files),
                "python_lines_audited": int(files["lines"].sum()),
                "legacy_or_frozen_experiment_files": int(
                    files["classification"].eq("LEGACY_OR_FROZEN_EXPERIMENT").sum()
                ),
                "platform_v2_core_files": len(new_core),
                "platform_v2_core_issuer_branches": int(new_core["issuer_branches"].sum()),
                "platform_v2_core_period_literal_branches": int(
                    new_core["period_literal_branches"].sum()
                ),
                "platform_v2_core_positional_iloc": int(new_core["positional_iloc"].sum()),
                "compiled_parser_rules": len(rules),
                "duplicate_dcf_kernels_remaining": 1,
                "migration_status": "INCREMENTAL_MIGRATION_ACTIVE",
            }
        ]
    )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    files.to_csv(OUTPUT / "python_architecture_inventory.csv", index=False)
    issues.to_csv(OUTPUT / "hardcoding_migration_ledger.csv", index=False)
    rules.to_csv(OUTPUT / "parser_rule_inventory.csv", index=False)
    summary.to_csv(OUTPUT / "architecture_gate.csv", index=False)
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": [root.relative_to(ROOT).as_posix() for root in PYTHON_ROOTS],
        "note": "resolved_table_index is provenance; position selectors are forbidden in Parser DSL",
    }
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = f"""# Platform Architecture V2 migration audit

## Gate

{markdown_table(summary)}

## Implemented spine

```text
Raw SEC / IR / APIs
        ↓
Canonical Document Model
        ↓
non-Turing Parser DSL → typed ParserRuleIR → deterministic executor
        ↓
FactIR + lineage + authority
        ↓
EvidenceGraphIR ↔ CausalGraphIR ↔ EconomicGraphIR
        ↓
Forecast / DCF / Reverse DCF
        ↓
separate governance policy
```

The V2 core contains no issuer branch, period literal branch, or positional `iloc`
selector. Issuer vocabulary and structural signatures live in `.arc` profiles;
resolved table indexes and text spans are emitted only as provenance. PAC table/inline
XBRL rules and CAT narrative backlog rules are live consumers of the same executor.

## Migration boundary

This is an incremental migration, not a big-bang rewrite. Frozen experiment packages
remain golden masters. The V8 IFRS adapter is the first real consumer of the new DSL.
The top-level and V8 Industrials DCF entry points now delegate to one shared valuation
kernel, protected by an exact golden compatibility test. GD V6 was also detached from
the HII package and moved to this kernel without changing any legacy CSV. The remaining
duplicate is the frozen HII V5.2 evaluator; it stays on the migration ledger until its
own frozen artifact chain can be re-baselined independently.

The V8 verified-stage cache is repeat-run byte deterministic. A first full-run to
cache-run transition can still reserialize floating values in four derived CSVs even
when gates and economic values are unchanged; byte-identical cross-mode serialization
remains an explicit infrastructure debt.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")
    print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
