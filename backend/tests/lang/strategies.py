"""Hypothesis strategies that generate random, syntactically valid PitchQuery ASTs."""

from hypothesis import strategies as st

from pitchquery.lang.ast import (
    ENTITIES,
    And,
    Between,
    BoolLit,
    CmpOp,
    Comparison,
    Contains,
    CountStage,
    Entity,
    Expr,
    Field,
    InList,
    LimitStage,
    Literal,
    Not,
    NumberLit,
    Or,
    Query,
    SelectStage,
    SortDirection,
    SortStage,
    Stage,
    StringLit,
)
from pitchquery.lang.tokens import KEYWORDS

identifiers = st.from_regex(r"[A-Za-z_][A-Za-z0-9_]{0,11}", fullmatch=True).filter(
    lambda name: name.lower() not in KEYWORDS
)
fields = identifiers.map(Field)
entities = st.sampled_from(ENTITIES).map(Entity)

# Floats are rounded to 3 decimals and bounded so that repr() never uses exponent
# notation, which the grammar does not have.
numbers = st.one_of(
    st.integers(min_value=-10_000, max_value=10_000),
    st.floats(min_value=-10_000, max_value=10_000, allow_nan=False).map(lambda f: round(f, 3)),
).map(NumberLit)
# Any text, including quotes, backslashes and keywords, must survive the round trip.
strings = st.text(max_size=12).map(StringLit)
bools = st.booleans().map(BoolLit)
literals: st.SearchStrategy[Literal] = st.one_of(strings, numbers, bools)

predicates: st.SearchStrategy[Expr] = st.one_of(
    st.builds(Comparison, fields, st.sampled_from(CmpOp), literals),
    st.builds(InList, fields, st.lists(literals, min_size=1, max_size=4).map(tuple)),
    st.builds(Contains, fields, strings),
    st.builds(Between, fields, numbers, numbers),
)


def _extend(children: st.SearchStrategy[Expr]) -> st.SearchStrategy[Expr]:
    return st.one_of(
        st.builds(Not, children),
        st.builds(And, children, children),
        st.builds(Or, children, children),
    )


expressions: st.SearchStrategy[Expr] = st.recursive(predicates, _extend, max_leaves=8)

stages: st.SearchStrategy[Stage] = st.one_of(
    st.builds(CountStage, st.none() | fields),
    st.builds(SortStage, st.sampled_from(SortDirection), st.none() | fields),
    st.builds(LimitStage, st.integers(min_value=0, max_value=100_000)),
    st.builds(SelectStage, st.lists(fields, min_size=1, max_size=4).map(tuple)),
)

queries: st.SearchStrategy[Query] = st.builds(
    Query,
    entities,
    st.none() | expressions,
    st.lists(stages, max_size=4).map(tuple),
)
