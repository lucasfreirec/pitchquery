"""AST node types. See docs/grammar.md, section 3.

Every node has a keyword-only `span` that is excluded from equality, so expected trees can
be written without spans: `Comparison(Field("xg"), CmpOp.GT, NumberLit(0.3))`.
"""

from dataclasses import dataclass, field
from enum import Enum

from pitchquery.lang.span import NO_SPAN, Span


def _span() -> Span:
    return field(default=NO_SPAN, compare=False, kw_only=True)


ENTITIES: tuple[str, ...] = ("events", "shots", "passes", "dribbles", "carries", "pressures")


@dataclass(frozen=True, slots=True)
class Entity:
    name: str  # lowercase, one of ENTITIES
    span: Span = _span()


@dataclass(frozen=True, slots=True)
class Field:
    name: str  # as written; not checked against the schema by the parser
    span: Span = _span()


# --- Literals ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StringLit:
    value: str
    span: Span = _span()


@dataclass(frozen=True, slots=True)
class NumberLit:
    value: int | float
    span: Span = _span()


@dataclass(frozen=True, slots=True)
class BoolLit:
    value: bool
    span: Span = _span()


Literal = StringLit | NumberLit | BoolLit


# --- Expressions ------------------------------------------------------------------------


class CmpOp(Enum):
    EQ = "="
    NE = "!="
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="


@dataclass(frozen=True, slots=True)
class Comparison:
    field: Field
    op: CmpOp
    value: Literal
    span: Span = _span()


@dataclass(frozen=True, slots=True)
class InList:
    field: Field
    values: tuple[Literal, ...]
    span: Span = _span()


@dataclass(frozen=True, slots=True)
class Contains:
    field: Field
    value: StringLit
    span: Span = _span()


@dataclass(frozen=True, slots=True)
class Between:
    field: Field
    low: NumberLit
    high: NumberLit
    span: Span = _span()


@dataclass(frozen=True, slots=True)
class Not:
    operand: "Expr"
    span: Span = _span()


@dataclass(frozen=True, slots=True)
class And:
    left: "Expr"
    right: "Expr"
    span: Span = _span()


@dataclass(frozen=True, slots=True)
class Or:
    left: "Expr"
    right: "Expr"
    span: Span = _span()


Predicate = Comparison | InList | Contains | Between
Expr = Comparison | InList | Contains | Between | Not | And | Or


# --- Stages -----------------------------------------------------------------------------


class SortDirection(Enum):
    ASC = "asc"
    DESC = "desc"


@dataclass(frozen=True, slots=True)
class CountStage:
    by: Field | None = None
    span: Span = _span()


@dataclass(frozen=True, slots=True)
class SortStage:
    direction: SortDirection
    field: Field | None = None
    span: Span = _span()


@dataclass(frozen=True, slots=True)
class LimitStage:
    count: int
    span: Span = _span()


@dataclass(frozen=True, slots=True)
class SelectStage:
    fields: tuple[Field, ...]
    span: Span = _span()


Stage = CountStage | SortStage | LimitStage | SelectStage


# --- Query ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Query:
    entity: Entity
    where: Expr | None = None
    stages: tuple[Stage, ...] = ()
    span: Span = _span()
