"""Semantic analysis: checks a parsed query against the schema and the data.

Unlike the parser, the analyzer does not stop at the first problem: it walks the whole
tree and returns every diagnostic, in source order, so the editor can underline all of
them at once. See docs/grammar.md, section 5.
"""

from dataclasses import dataclass

from pitchquery.data.values import ValueIndex
from pitchquery.lang.ast import (
    And,
    Between,
    BoolLit,
    Comparison,
    Contains,
    CountStage,
    Expr,
    Field,
    InList,
    Literal,
    Not,
    NumberLit,
    Or,
    Predicate,
    Query,
    SelectStage,
    SortStage,
    Stage,
    StringLit,
)
from pitchquery.lang.diagnostics import Diagnostic, Severity
from pitchquery.lang.errors import ParseError
from pitchquery.lang.parser import parse
from pitchquery.lang.printer import stage_to_source
from pitchquery.lang.schema import FIELDS, FieldSpec, FieldType, lookup
from pitchquery.lang.span import Span
from pitchquery.lang.suggest import did_you_mean, suggest


@dataclass(frozen=True, slots=True)
class Analysis:
    query: Query | None  # None if the query did not parse
    diagnostics: tuple[Diagnostic, ...]

    @property
    def ok(self) -> bool:
        """True if the query can run. Warnings do not prevent running."""
        return self.query is not None and not any(
            d.severity is Severity.ERROR for d in self.diagnostics
        )


def check(source: str, values: ValueIndex | None = None) -> Analysis:
    """Parse and analyze `source`. A syntax error becomes a single error diagnostic."""
    try:
        query = parse(source)
    except ParseError as error:
        diagnostic = Diagnostic(Severity.ERROR, error.message, error.span, error.suggestions)
        return Analysis(None, (diagnostic,))
    return Analysis(query, tuple(analyze(query, values)))


def analyze(query: Query, values: ValueIndex | None = None) -> list[Diagnostic]:
    """Every semantic problem in `query`. Known values are only checked if `values` is given."""
    return _Analyzer(query.entity.name, values).run(query)


def columns_after(stage: Stage, columns: list[str] | None) -> list[str] | None:
    """Field names still available after `stage`, given those available before it.

    None means "every schema field". `count` leaves only its `by` field (its own `count`
    column is a keyword, so it can never be referenced); `select` leaves the selected
    fields; other stages keep what they had.
    """
    match stage:
        case CountStage(by):
            return [by.name.lower()] if by else []
        case SelectStage(fields):
            return [f.name.lower() for f in fields]
        case _:
            return columns


def _literal_type(literal: Literal) -> str:
    match literal:
        case StringLit():
            return "a string"
        case NumberLit():
            return "a number"
        case BoolLit():
            return "a boolean"


def _accepts(field_type: FieldType, literal: Literal) -> bool:
    match literal:
        case StringLit():
            return field_type is FieldType.STRING
        case NumberLit():
            # An int field accepts any number: `minute > 80.5` is meaningful.
            return field_type in (FieldType.INT, FieldType.FLOAT)
        case BoolLit():
            return field_type is FieldType.BOOL


def _join(names: list[str]) -> str:
    """`a`, `a` and `b`, `a`, `b` and `c`."""
    quoted = [f"`{name}`" for name in names]
    return quoted[0] if len(quoted) == 1 else f"{', '.join(quoted[:-1])} and {quoted[-1]}"


class _Analyzer:
    def __init__(self, entity: str, values: ValueIndex | None) -> None:
        self.entity = entity
        self.diagnostics: list[Diagnostic] = []
        # field -> {lowercase value: value}, and the values in frequency order.
        self.known: dict[str, dict[str, str]] = {}
        self.ranked: dict[str, list[str]] = {}
        for field, entries in (values or {}).items():
            self.ranked[field] = [entry["value"] for entry in entries]
            self.known[field] = {value.lower(): value for value in self.ranked[field]}

    def run(self, query: Query) -> list[Diagnostic]:
        if query.where is not None:
            self._expr(query.where)
        self._stages(query.stages)
        return self.diagnostics

    def _report(
        self,
        severity: Severity,
        message: str,
        span: Span,
        suggestions: list[str] | tuple[str, ...] = (),
    ) -> None:
        self.diagnostics.append(Diagnostic(severity, message, span, tuple(suggestions)))

    # --- Fields -------------------------------------------------------------------------

    def _resolve(self, field: Field) -> FieldSpec | None:
        """The field's spec, reporting unknown fields and fields the entity lacks.

        Returns None only for unknown fields, so a field on the wrong entity still gets
        its operator and value checked.
        """
        spec = lookup(field.name)
        if spec is None:
            suggestions = suggest(field.name, FIELDS)
            message = f"Unknown field `{field.name}`.{did_you_mean(suggestions)}"
            self._report(Severity.ERROR, message, field.span, suggestions)
            return None
        if not spec.applies_to(self.entity):
            assert spec.entities is not None
            message = f"`{spec.name}` only exists for {_join(list(spec.entities))}."
            self._report(Severity.ERROR, message, field.span)
        return spec

    # --- Where expression ---------------------------------------------------------------

    def _expr(self, expr: Expr) -> None:
        match expr:
            case And(left, right) | Or(left, right):
                self._expr(left)
                self._expr(right)
            case Not(operand):
                self._expr(operand)
            case Comparison() | InList() | Contains() | Between():
                self._predicate(expr)

    def _predicate(self, predicate: Predicate) -> None:
        spec = self._resolve(predicate.field)
        if spec is None:
            return  # an unknown field has no type to check against

        operator, values = _operator_and_values(predicate)
        if operator not in spec.type.operators:
            allowed = ", ".join(f"`{op}`" for op in spec.type.operators)
            message = (
                f"`{operator}` does not apply to `{spec.name}`, which is "
                f"{spec.type.described}. Use one of: {allowed}."
            )
            self._report(Severity.ERROR, message, predicate.span)
            return

        well_typed = True
        for value in values:
            if not _accepts(spec.type, value):
                well_typed = False
                message = (
                    f"`{spec.name}` is {spec.type.described}; "
                    f"expected {spec.type.described}, got {_literal_type(value)}."
                )
                self._report(Severity.ERROR, message, value.span)
        if not well_typed:
            return

        if isinstance(predicate, Between) and predicate.low.value > predicate.high.value:
            message = (
                f"Empty range: the lower bound {predicate.low.value!r} is greater than "
                f"the upper bound {predicate.high.value!r}."
            )
            self._report(Severity.WARNING, message, predicate.span)

        # `contains` matches part of a value, so its argument is not a value itself.
        if operator in ("=", "!=", "in"):
            for value in values:
                if isinstance(value, StringLit):
                    self._check_known_value(spec.name, value)

    def _check_known_value(self, field: str, literal: StringLit) -> None:
        known = self.known.get(field)
        if known is None or literal.value.lower() in known:
            return
        suggestions = suggest(literal.value, self.ranked[field])
        message = f"No {field} `{literal.value}` in the data.{did_you_mean(suggestions)}"
        self._report(Severity.WARNING, message, literal.span, suggestions)

    # --- Stages -------------------------------------------------------------------------

    def _stages(self, stages: tuple[Stage, ...]) -> None:
        # Columns left by the last shaping stage (`count` or `select`); None while every
        # schema field is still available.
        columns: list[str] | None = None
        shaped_by: Stage | None = None

        for stage in stages:
            for field in _fields_of(stage):
                if columns is None:
                    self._resolve(field)
                elif field.name.lower() not in columns:
                    assert shaped_by is not None
                    message = (
                        f"`{field.name}` is not available after `{stage_to_source(shaped_by)}`."
                    )
                    if columns:
                        message += f" Available: {', '.join(f'`{c}`' for c in columns)}."
                    self._report(Severity.ERROR, message, field.span, suggest(field.name, columns))

            if isinstance(stage, CountStage | SelectStage):
                shaped_by = stage
            columns = columns_after(stage, columns)


def _operator_and_values(predicate: Predicate) -> tuple[str, list[Literal]]:
    match predicate:
        case Comparison(_, op, value):
            return op.value, [value]
        case InList(_, values):
            return "in", list(values)
        case Contains(_, value):
            return "contains", [value]
        case Between(_, low, high):
            return "between", [low, high]


def _fields_of(stage: Stage) -> list[Field]:
    match stage:
        case CountStage(by):
            return [by] if by else []
        case SortStage(_, field):
            return [field] if field else []
        case SelectStage(fields):
            return list(fields)
        case _:
            return []
