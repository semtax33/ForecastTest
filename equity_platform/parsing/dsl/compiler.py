from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re

from equity_platform.ir import AuthorityLevel, EvidenceStatus, FactOrigin, RelationType
from equity_platform.parsing.rule_ir import (
    CombineMode,
    FailurePolicy,
    ParserRuleIR,
    PeriodMode,
    SelectorKind,
)


ALLOWED_KEYS = {
    "version",
    "source",
    "document",
    "selector",
    "period_mode",
    "period_patterns",
    "table_headers_all",
    "row_labels",
    "capture_column",
    "fact_names",
    "text_patterns",
    "capture_group",
    "full_year_only",
    "dimensions",
    "combine",
    "metric",
    "scope",
    "unit",
    "origin",
    "relation",
    "evidence",
    "authority",
    "min_value",
    "max_value",
    "finite",
    "assertions",
    "ambiguity",
    "missing",
}


class DslCompileError(ValueError):
    pass


def _strip_comments(text: str) -> str:
    output: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char == "#" or text[index : index + 2] == "//":
            newline = text.find("\n", index)
            if newline < 0:
                break
            output.append("\n")
            index = newline + 1
            continue
        output.append(char)
        index += 1
    return "".join(output)


def _rule_blocks(text: str) -> list[tuple[str, str]]:
    clean = _strip_comments(text)
    pattern = re.compile(r'\brule\s+"([A-Za-z0-9_.-]+)"\s*\{')
    blocks: list[tuple[str, str]] = []
    cursor = 0
    while match := pattern.search(clean, cursor):
        depth = 1
        index = match.end()
        in_string = False
        escaped = False
        while index < len(clean) and depth:
            char = clean[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            else:
                if char == '"':
                    in_string = True
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
            index += 1
        if depth:
            raise DslCompileError(f"Unclosed rule block: {match.group(1)}")
        blocks.append((match.group(1), clean[match.end() : index - 1]))
        cursor = index
    if not blocks:
        raise DslCompileError("No rule blocks found")
    return blocks


def _statements(body: str) -> list[str]:
    statements: list[str] = []
    start = 0
    bracket_depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(body):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth -= 1
            if bracket_depth < 0:
                raise DslCompileError("Unexpected closing list bracket")
        elif char in {"\n", ";"} and bracket_depth == 0:
            statement = body[start:index].strip()
            if statement:
                statements.append(statement)
            start = index + 1
    tail = body[start:].strip()
    if tail:
        statements.append(tail)
    if bracket_depth or in_string:
        raise DslCompileError("Unclosed string or list")
    return statements


def _value(raw: str) -> object:
    raw = raw.strip()
    if raw == "null":
        return None
    if raw in {"true", "false"}:
        return raw == "true"
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DslCompileError(f"Values must be JSON literals: {raw}") from exc


def _mapping(body: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for statement in _statements(body):
        if "=" not in statement:
            raise DslCompileError(f"Expected key = value: {statement}")
        key, raw = statement.split("=", 1)
        key = key.strip()
        if key not in ALLOWED_KEYS:
            raise DslCompileError(f"Unknown or forbidden DSL key: {key}")
        if key in result:
            raise DslCompileError(f"Duplicate DSL key: {key}")
        result[key] = _value(raw)
    return result


def _strings(value: object | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise DslCompileError("Expected a list of strings")
    return tuple(value)


def compile_rules(text: str) -> tuple[ParserRuleIR, ...]:
    source_sha = sha256(text.encode("utf-8")).hexdigest()
    compiled: list[ParserRuleIR] = []
    for rule_id, body in _rule_blocks(text):
        values = _mapping(body)
        required = {
            "version",
            "source",
            "document",
            "selector",
            "period_mode",
            "combine",
            "metric",
            "scope",
            "unit",
        }
        missing = required - values.keys()
        if missing:
            raise DslCompileError(f"{rule_id} is missing keys: {sorted(missing)}")
        try:
            rule = ParserRuleIR(
                rule_id=rule_id,
                version=int(values["version"]),
                source=str(values["source"]),
                document=str(values["document"]),
                selector=SelectorKind(str(values["selector"])),
                period_mode=PeriodMode(str(values["period_mode"])),
                period_patterns=_strings(values.get("period_patterns")),
                table_headers_all=_strings(values.get("table_headers_all")),
                row_labels=_strings(values.get("row_labels")),
                capture_column=(
                    str(values["capture_column"])
                    if values.get("capture_column") is not None
                    else None
                ),
                fact_names=_strings(values.get("fact_names")),
                text_patterns=_strings(values.get("text_patterns")),
                capture_group=(
                    str(values["capture_group"])
                    if values.get("capture_group") is not None
                    else None
                ),
                full_year_only=bool(values.get("full_year_only", False)),
                dimensions=str(values.get("dimensions", "ANY")),
                combine=CombineMode(str(values["combine"])),
                metric=str(values["metric"]),
                scope=str(values["scope"]),
                unit=str(values["unit"]),
                origin=FactOrigin(str(values.get("origin", "OBSERVED"))),
                relation=RelationType(str(values.get("relation", "STRUCTURAL"))),
                evidence=EvidenceStatus(str(values.get("evidence", "PIT"))),
                authority=AuthorityLevel[str(values.get("authority", "RESEARCH_EVIDENCE"))],
                min_value=(float(values["min_value"]) if values.get("min_value") is not None else None),
                max_value=(float(values["max_value"]) if values.get("max_value") is not None else None),
                finite=bool(values.get("finite", True)),
                assertions=_strings(values.get("assertions")),
                ambiguity=FailurePolicy(str(values.get("ambiguity", "FAIL"))),
                missing=FailurePolicy(str(values.get("missing", "FAIL"))),
                source_sha256=source_sha,
            )
            rule.validate()
            for pattern in rule.period_patterns:
                compiled_pattern = re.compile(pattern)
                if not {"month", "year"}.issubset(compiled_pattern.groupindex):
                    raise DslCompileError(
                        f"{rule_id} period patterns require named month/year captures"
                    )
            for pattern in rule.text_patterns:
                compiled_pattern = re.compile(pattern)
                if rule.capture_group not in compiled_pattern.groupindex:
                    raise DslCompileError(
                        f"{rule_id} text pattern lacks capture group {rule.capture_group!r}"
                    )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, DslCompileError):
                raise
            raise DslCompileError(f"Invalid rule {rule_id}: {exc}") from exc
        compiled.append(rule)
    ids = [rule.rule_id for rule in compiled]
    if len(ids) != len(set(ids)):
        raise DslCompileError("Rule ids must be unique")
    return tuple(compiled)


def compile_rule_file(path: Path) -> tuple[ParserRuleIR, ...]:
    return compile_rules(path.read_text(encoding="utf-8"))
