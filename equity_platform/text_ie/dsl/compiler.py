from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import json
from pathlib import Path
import re

from equity_platform.ir import AuthorityLevel

from ..model import AmbiguityPolicy, QuantityKind, SemanticFrame


class MatcherBackend(StrEnum):
    PHRASE = "PHRASE"
    SEQUENCE = "SEQUENCE"
    DEPENDENCY = "DEPENDENCY"
    CONTEXT = "CONTEXT"


@dataclass(frozen=True)
class PatternExprIR:
    operator: str
    attribute: str | None = None
    value: str | bool | None = None
    children: tuple["PatternExprIR", ...] = ()


@dataclass(frozen=True)
class SemanticVarIR:
    name: str
    expression: PatternExprIR


@dataclass(frozen=True)
class PatternStepIR:
    label: str
    variable: str
    expression: PatternExprIR
    optional: bool = False
    minimum: int = 1
    maximum: int = 1


@dataclass(frozen=True)
class FrameRoleIR:
    name: str
    role_type: str
    optional: bool


@dataclass(frozen=True)
class FrameSchemaIR:
    frame: SemanticFrame
    roles: tuple[FrameRoleIR, ...]


@dataclass(frozen=True)
class TextRuleProgramIR:
    variables: tuple[SemanticVarIR, ...]
    frames: tuple[FrameSchemaIR, ...]
    rules: tuple["TextRuleIR", ...]
    source_sha256: str


@dataclass(frozen=True)
class TextRuleIR:
    rule_id: str
    version: int
    frame: SemanticFrame
    triggers: tuple[str, ...]
    concepts: tuple[str, ...]
    quantity_kinds: tuple[QuantityKind, ...]
    relation_words: tuple[str, ...]
    require_metric: bool
    require_value: bool
    require_unique_metric: bool
    require_unique_value: bool
    allow_context_metric: bool
    qualitative: bool
    output_metric_suffix: str
    authority: AuthorityLevel
    ambiguity: AmbiguityPolicy
    priority: int
    source_sha256: str
    pattern: tuple[PatternStepIR, ...] = ()
    backends: tuple[MatcherBackend, ...] = (MatcherBackend.SEQUENCE,)
    operations: tuple[str, ...] = ()
    relation: str | None = None

    def validate(self) -> None:
        if not self.rule_id or self.version < 1:
            raise ValueError("Text rules require an id and positive version")
        if not self.triggers:
            raise ValueError("Text rules require at least one trigger")
        if self.authority >= AuthorityLevel.TERMINAL_INPUT:
            raise ValueError("Text rules cannot directly grant terminal authority")
        if self.require_value and self.qualitative:
            raise ValueError("A qualitative rule cannot require a numeric value")
        if self.pattern and not self.backends:
            raise ValueError("Pattern rules require at least one execution backend")


ALLOWED_KEYS = {
    "version",
    "frame",
    "triggers",
    "concepts",
    "quantity_kinds",
    "relation_words",
    "require_metric",
    "require_value",
    "require_unique_metric",
    "require_unique_value",
    "allow_context_metric",
    "qualitative",
    "output_metric_suffix",
    "authority",
    "ambiguity",
    "priority",
    "pattern",
    "backends",
    "operations",
    "relation",
}

PURE_OPERATIONS = {
    "normalize_money",
    "normalize_percent",
    "normalize_count",
    "resolve_period",
    "resolve_scope",
    "assert_unique",
    "emit_frame",
    "emit_relation",
}
TOKEN_ATTRIBUTES = {
    "lower",
    "lemma",
    "pos",
    "ent_type",
    "shape",
    "like_num",
    "concept",
    "quantity",
}


class TextDslCompileError(ValueError):
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


def _blocks(text: str, kind: str = "text_rule") -> tuple[tuple[str, str], ...]:
    clean = _strip_comments(text)
    pattern = re.compile(rf'\b{re.escape(kind)}\s+"([A-Za-z0-9_.-]+)"\s*\{{')
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
            elif char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            index += 1
        if depth:
            raise TextDslCompileError(f"Unclosed {kind}: {match.group(1)}")
        blocks.append((match.group(1), clean[match.end() : index - 1]))
        cursor = index
    if not blocks and kind == "text_rule":
        raise TextDslCompileError("No text_rule blocks found")
    return tuple(blocks)


def _statements(body: str) -> tuple[str, ...]:
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
        elif char in {"\n", ";"} and bracket_depth == 0:
            statement = body[start:index].strip()
            if statement:
                statements.append(statement)
            start = index + 1
    tail = body[start:].strip()
    if tail:
        statements.append(tail)
    if bracket_depth or in_string:
        raise TextDslCompileError("Unclosed string or list")
    return tuple(statements)


def _mapping(
    body: str,
    allowed_keys: set[str] = ALLOWED_KEYS,
) -> dict[str, object]:
    values: dict[str, object] = {}
    for statement in _statements(body):
        if "=" not in statement:
            raise TextDslCompileError(f"Expected key = value: {statement}")
        key, raw = (part.strip() for part in statement.split("=", 1))
        if key not in allowed_keys:
            raise TextDslCompileError(f"Unknown or forbidden text DSL key: {key}")
        if key in values:
            raise TextDslCompileError(f"Duplicate text DSL key: {key}")
        try:
            values[key] = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TextDslCompileError(f"Values must be JSON literals: {raw}") from exc
    return values


def _strings(value: object | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TextDslCompileError("Expected a list of strings")
    return tuple(value)


def _pattern_expr(value: object) -> PatternExprIR:
    if not isinstance(value, dict) or len(value) != 1:
        raise TextDslCompileError("Pattern expressions require one attribute or logical operator")
    key, operand = next(iter(value.items()))
    if key in {"any", "all"}:
        if not isinstance(operand, list) or not operand:
            raise TextDslCompileError(f"{key} requires a non-empty expression list")
        return PatternExprIR(key.upper(), children=tuple(_pattern_expr(item) for item in operand))
    if key == "not":
        return PatternExprIR("NOT", children=(_pattern_expr(operand),))
    if key not in TOKEN_ATTRIBUTES or not isinstance(operand, (str, bool)):
        raise TextDslCompileError(f"Unsupported token predicate: {key}")
    return PatternExprIR("TOKEN", attribute=key, value=operand)


def _variables(text: str) -> tuple[SemanticVarIR, ...]:
    variables: list[SemanticVarIR] = []
    for name, body in _blocks(text, "var"):
        values = _mapping(body, {"expression"})
        if "expression" not in values:
            raise TextDslCompileError(f"Variable {name} requires expression")
        variables.append(SemanticVarIR(name, _pattern_expr(values["expression"])))
    names = [item.name for item in variables]
    if len(names) != len(set(names)):
        raise TextDslCompileError("Semantic variable names must be unique")
    return tuple(variables)


def _frame_schemas(text: str) -> tuple[FrameSchemaIR, ...]:
    schemas: list[FrameSchemaIR] = []
    for name, body in _blocks(text, "frame"):
        values = _mapping(body, {"roles"})
        roles = _strings(values.get("roles"))
        compiled_roles: list[FrameRoleIR] = []
        for role in roles:
            if ":" not in role:
                raise TextDslCompileError(f"Invalid frame role: {role}")
            role_name, role_type = role.split(":", 1)
            optional = role_type.endswith("?")
            compiled_roles.append(
                FrameRoleIR(role_name, role_type.removesuffix("?"), optional)
            )
        try:
            schemas.append(FrameSchemaIR(SemanticFrame(name), tuple(compiled_roles)))
        except ValueError as exc:
            raise TextDslCompileError(f"Unknown semantic frame schema: {name}") from exc
    frame_ids = [schema.frame for schema in schemas]
    if len(frame_ids) != len(set(frame_ids)):
        raise TextDslCompileError("Frame schemas must be unique")
    return tuple(schemas)


def _pattern_steps(
    value: object | None,
    variables: dict[str, SemanticVarIR],
) -> tuple[PatternStepIR, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise TextDslCompileError("pattern must be a list of labeled variable references")
    steps: list[PatternStepIR] = []
    for item in value:
        if not isinstance(item, dict):
            raise TextDslCompileError("Pattern steps must be objects")
        unknown = set(item) - {"label", "var", "optional", "min", "max"}
        if unknown:
            raise TextDslCompileError(f"Unknown pattern step keys: {sorted(unknown)}")
        label, variable = item.get("label"), item.get("var")
        if not isinstance(label, str) or not isinstance(variable, str):
            raise TextDslCompileError("Pattern steps require string label and var")
        if variable not in variables:
            raise TextDslCompileError(f"Unknown semantic variable: {variable}")
        minimum = int(item.get("min", 0 if item.get("optional", False) else 1))
        maximum = int(item.get("max", 1))
        if minimum < 0 or maximum < minimum:
            raise TextDslCompileError("Pattern repetition bounds must be ordered")
        steps.append(
            PatternStepIR(
                label=label,
                variable=variable,
                expression=variables[variable].expression,
                optional=bool(item.get("optional", False)),
                minimum=minimum,
                maximum=maximum,
            )
        )
    labels = [step.label for step in steps]
    if len(labels) != len(set(labels)):
        raise TextDslCompileError("Pattern labels must be unique within a rule")
    return tuple(steps)


def compile_text_program(text: str) -> TextRuleProgramIR:
    digest = sha256(text.encode("utf-8")).hexdigest()
    variables = _variables(text)
    variable_map = {item.name: item for item in variables}
    schemas = _frame_schemas(text)
    declared_frames = {schema.frame for schema in schemas}
    rules: list[TextRuleIR] = []
    for rule_id, body in _blocks(text):
        values = _mapping(body)
        required = {"version", "frame", "triggers"}
        missing = required - values.keys()
        if missing:
            raise TextDslCompileError(f"{rule_id} is missing keys: {sorted(missing)}")
        try:
            frame = SemanticFrame(str(values["frame"]))
            if declared_frames and frame not in declared_frames:
                raise ValueError(f"Frame {frame.value} has no declared schema")
            operations = _strings(values.get("operations"))
            forbidden_operations = set(operations) - PURE_OPERATIONS
            if forbidden_operations:
                raise ValueError(
                    f"Unregistered operation(s): {sorted(forbidden_operations)}"
                )
            rule = TextRuleIR(
                rule_id=rule_id,
                version=int(values["version"]),
                frame=frame,
                triggers=_strings(values["triggers"]),
                concepts=_strings(values.get("concepts")),
                quantity_kinds=tuple(
                    QuantityKind(item) for item in _strings(values.get("quantity_kinds"))
                ),
                relation_words=_strings(values.get("relation_words")),
                require_metric=bool(values.get("require_metric", True)),
                require_value=bool(values.get("require_value", True)),
                require_unique_metric=bool(values.get("require_unique_metric", True)),
                require_unique_value=bool(values.get("require_unique_value", True)),
                allow_context_metric=bool(values.get("allow_context_metric", False)),
                qualitative=bool(values.get("qualitative", False)),
                output_metric_suffix=str(values.get("output_metric_suffix", "")),
                authority=AuthorityLevel[str(values.get("authority", "RESEARCH_EVIDENCE"))],
                ambiguity=AmbiguityPolicy(str(values.get("ambiguity", "REVIEW"))),
                priority=int(values.get("priority", 100)),
                source_sha256=digest,
                pattern=_pattern_steps(values.get("pattern"), variable_map),
                backends=tuple(
                    MatcherBackend(item)
                    for item in _strings(values.get("backends"))
                )
                or (MatcherBackend.SEQUENCE,),
                operations=operations,
                relation=(
                    str(values["relation"])
                    if values.get("relation") is not None
                    else None
                ),
            )
            rule.validate()
        except (KeyError, TypeError, ValueError) as exc:
            raise TextDslCompileError(f"Invalid text rule {rule_id}: {exc}") from exc
        rules.append(rule)
    ids = [rule.rule_id for rule in rules]
    if len(ids) != len(set(ids)):
        raise TextDslCompileError("Text rule ids must be unique")
    return TextRuleProgramIR(
        variables=variables,
        frames=schemas,
        rules=tuple(sorted(rules, key=lambda rule: (rule.priority, rule.rule_id))),
        source_sha256=digest,
    )


def compile_text_rules(text: str) -> tuple[TextRuleIR, ...]:
    return compile_text_program(text).rules


def compile_text_rule_file(path: Path) -> tuple[TextRuleIR, ...]:
    return compile_text_rules(path.read_text(encoding="utf-8"))


def compile_text_program_file(path: Path) -> TextRuleProgramIR:
    return compile_text_program(path.read_text(encoding="utf-8"))
