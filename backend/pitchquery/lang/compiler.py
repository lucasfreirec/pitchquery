"""Compiler: analyzed AST -> parameterised DuckDB SQL.

Safety:
- Values are **never** written into the SQL text. Each one becomes a numbered parameter
  (`$1`, `$2`, ...) and is passed to DuckDB separately.
- Column names cannot be parameters, so they are taken from the schema, never from the
  user's text: the AST's field name is only used to look the field up. Unknown names
  raise CompileError.

Semantics (docs/grammar.md, section 6):
- String comparisons ignore case. `contains` is a plain substring test (no wildcards).
- A predicate on a missing value is false, so `not` and `!=` behave like plain negation:
  `player != "Messi"` includes events without a player.

Pipeline: every stage wraps the previous query in a subquery. SQL does not guarantee
that a subquery's ORDER BY survives the outer query, so each step carries its row order
explicitly in a hidden `_ord` column (1, 2, 3, ...), and the final query orders by it.
"""

from dataclasses import dataclass

from pitchquery.lang.ast import (
    And,
    Between,
    Comparison,
    Contains,
    CountStage,
    Expr,
    Field,
    InList,
    LimitStage,
    Literal,
    Not,
    Or,
    Query,
    SelectStage,
    SortDirection,
    SortStage,
    Stage,
)
from pitchquery.lang.schema import ENTITY_EVENT_TYPES, FIELDS, FieldSpec, FieldType, lookup

# Default row order: the order events happened in.
_EVENT_ORDER = "match_id, event_index"


class CompileError(Exception):
    """The AST is not valid for compilation. The analyzer should have reported it."""


@dataclass(frozen=True, slots=True)
class CompiledQuery:
    sql: str
    params: tuple[object, ...]


def compile_query(query: Query) -> CompiledQuery:
    return _Compiler().compile(query)


def _quote(name: str) -> str:
    # Only ever called with schema names ([a-z_]+), so quoting cannot be escaped from.
    # Quoting matters anyway: `type`, `second` and `position` are SQL keywords.
    return f'"{name}"'


class _Compiler:
    def __init__(self) -> None:
        self.params: list[object] = []
        self.has_count = False  # whether the current relation has a `count` column

    def compile(self, query: Query) -> CompiledQuery:
        conditions: list[str] = []
        event_type = ENTITY_EVENT_TYPES[query.entity.name]
        if event_type is not None:
            conditions.append(f'"type" = {self._param(event_type)}')
        if query.where is not None:
            conditions.append(self._expr(query.where))
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""

        columns = ", ".join(_quote(name) for name in FIELDS)
        sql = (
            f"SELECT {columns}, row_number() OVER (ORDER BY {_EVENT_ORDER}) AS _ord "
            f"FROM events{where}"
        )
        for stage in query.stages:
            sql = self._stage(stage, sql)

        final = f"SELECT * EXCLUDE (_ord) FROM ({sql}) ORDER BY _ord"
        return CompiledQuery(final, tuple(self.params))

    # --- Helpers ------------------------------------------------------------------------

    def _param(self, value: object) -> str:
        self.params.append(value)
        return f"${len(self.params)}"

    def _spec(self, field: Field) -> FieldSpec:
        spec = lookup(field.name)
        if spec is None:
            raise CompileError(f"unknown field {field.name!r}")
        return spec

    def _column(self, field: Field) -> str:
        return _quote(self._spec(field).name)

    # --- Where expression ---------------------------------------------------------------

    def _expr(self, expr: Expr) -> str:
        match expr:
            case And(left, right):
                return f"({self._expr(left)} AND {self._expr(right)})"
            case Or(left, right):
                return f"({self._expr(left)} OR {self._expr(right)})"
            case Not(operand):
                return f"(NOT {self._expr(operand)})"
            case Comparison(field, op, value):
                spec = self._spec(field)
                if op.value == "!=":
                    # Defined as `not (field = value)`, so missing values are included.
                    return f"(NOT {self._predicate(spec, '=', [value])})"
                return self._predicate(spec, op.value, [value])
            case InList(field, values):
                return self._predicate(self._spec(field), "IN", list(values))
            case Contains(field, value):
                column = self._column(field)
                return (
                    f"coalesce(contains(lower({column}), lower({self._param(value.value)})), false)"
                )
            case Between(field, low, high):
                column, lo, hi = (
                    self._column(field),
                    self._param(low.value),
                    self._param(high.value),
                )
                return f"coalesce({column} BETWEEN {lo} AND {hi}, false)"

    def _predicate(self, spec: FieldSpec, operator: str, values: list[Literal]) -> str:
        """`column <operator> value(s)`, case-insensitive for strings, false on NULL."""
        column = _quote(spec.name)
        placeholders = [self._param(value.value) for value in values]
        if spec.type is FieldType.STRING:
            column = f"lower({column})"
            placeholders = [f"lower({p})" for p in placeholders]
        right = f"({', '.join(placeholders)})" if operator == "IN" else placeholders[0]
        # Comparing with NULL gives NULL; coalesce makes it false, so NOT works as expected.
        return f"coalesce({column} {operator} {right}, false)"

    # --- Stages -------------------------------------------------------------------------

    def _stage(self, stage: Stage, sql: str) -> str:
        match stage:
            case CountStage(None):
                self.has_count = True
                return f'SELECT count(*) AS "count", 1 AS _ord FROM ({sql})'

            case CountStage(by) if by is not None:
                self.has_count = True
                column = self._column(by)
                # Most frequent first; ties alphabetical, so results are deterministic.
                order = f"count(*) DESC, {column} ASC NULLS LAST"
                return (
                    f'SELECT {column}, count(*) AS "count", '
                    f"row_number() OVER (ORDER BY {order}) AS _ord "
                    f"FROM ({sql}) GROUP BY {column}"
                )

            case SortStage(direction, field):
                if field is not None:
                    key = self._column(field)
                elif self.has_count:
                    key = '"count"'
                else:
                    key = "_ord"  # current row order, e.g. `sort desc` = latest events first
                dir_sql = "ASC" if direction is SortDirection.ASC else "DESC"
                # `_ord` as the tie-breaker makes the sort stable.
                return (
                    f"SELECT * EXCLUDE (_ord), "
                    f"row_number() OVER (ORDER BY {key} {dir_sql} NULLS LAST, _ord) AS _ord "
                    f"FROM ({sql})"
                )

            case LimitStage(count):
                # `_ord` is always 1..n, so the first `count` rows are those with _ord <= count.
                return f"SELECT * FROM ({sql}) WHERE _ord <= {self._param(count)}"

            case SelectStage(fields):
                # De-duplicated, in the order written: `select a, b, a` gives a, b.
                columns = list(dict.fromkeys(self._column(f) for f in fields))
                self.has_count = False  # `count` is a keyword: it can never be selected
                return f"SELECT {', '.join(columns)}, _ord FROM ({sql})"

        raise CompileError(f"unknown stage {stage!r}")
