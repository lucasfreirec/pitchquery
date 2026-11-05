"""Print an AST back to canonical PitchQuery source.

Used by the parser round-trip test, and later by the query formatter. The output uses
lowercase keywords, single spaces, and only the parentheses the tree shape needs.
"""

from pitchquery.lang.ast import (
    And,
    Between,
    BoolLit,
    Comparison,
    Contains,
    CountStage,
    Expr,
    InList,
    LimitStage,
    Literal,
    Not,
    NumberLit,
    Or,
    Query,
    SelectStage,
    SortStage,
    Stage,
    StringLit,
)
from pitchquery.lang.tokens import quote_string

# Binding strength; higher binds tighter. Predicates are primaries.
_OR, _AND, _NOT, _PRIMARY = 1, 2, 3, 4


def to_source(query: Query) -> str:
    parts = [query.entity.name]
    if query.where is not None:
        parts.append(f"where {_expr(query.where)}")
    text = " ".join(parts)
    for stage in query.stages:
        text += f" | {_stage(stage)}"
    return text


def _precedence(expr: Expr) -> int:
    match expr:
        case Or():
            return _OR
        case And():
            return _AND
        case Not():
            return _NOT
        case _:
            return _PRIMARY


def _wrap(expr: Expr, needs_parens: bool) -> str:
    text = _expr(expr)
    return f"({text})" if needs_parens else text


def _expr(expr: Expr) -> str:
    match expr:
        case Or(left, right):
            return _binary(left, "or", right, _OR)
        case And(left, right):
            return _binary(left, "and", right, _AND)
        case Not(operand):
            # `not` takes a primary, so anything that is not a predicate is parenthesised.
            return f"not {_wrap(operand, _precedence(operand) < _PRIMARY)}"
        case Comparison(field, op, value):
            return f"{field.name} {op.value} {_literal(value)}"
        case InList(field, values):
            return f"{field.name} in ({', '.join(_literal(v) for v in values)})"
        case Contains(field, value):
            return f"{field.name} contains {_literal(value)}"
        case Between(field, low, high):
            return f"{field.name} between {_literal(low)} and {_literal(high)}"


def _binary(left: Expr, keyword: str, right: Expr, precedence: int) -> str:
    # Left-associative: a left operand of the same precedence prints as is, a right one
    # needs parentheses (`a or (b or c)` is a different tree from `a or b or c`).
    left_text = _wrap(left, _precedence(left) < precedence)
    right_text = _wrap(right, _precedence(right) <= precedence)
    return f"{left_text} {keyword} {right_text}"


def _literal(literal: Literal) -> str:
    match literal:
        case StringLit(value):
            return quote_string(value)
        case BoolLit(value):
            return "true" if value else "false"
        case NumberLit(value):
            # repr() gives the shortest text that round-trips a float, e.g. 0.3 not 0.299999.
            return repr(value)


def stage_to_source(stage: Stage) -> str:
    """One stage as source, e.g. `count by player`. Used in analyzer messages."""
    return _stage(stage)


def _stage(stage: Stage) -> str:
    match stage:
        case CountStage(by):
            return "count" if by is None else f"count by {by.name}"
        case SortStage(direction, field):
            text = f"sort {direction.value}"
            return text if field is None else f"{text} {field.name}"
        case LimitStage(count):
            return f"limit {count}"
        case SelectStage(fields):
            return f"select {', '.join(f.name for f in fields)}"
