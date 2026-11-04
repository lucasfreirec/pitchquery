"""Parser contract. See docs/grammar.md, sections 2-4.

Expected trees are written without spans (spans are excluded from equality); span tests
at the end of the file check them explicitly.
"""

import pytest

from pitchquery.lang.ast import (
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
    Not,
    NumberLit,
    Or,
    Query,
    SelectStage,
    SortDirection,
    SortStage,
    StringLit,
)
from pitchquery.lang.errors import ParseError
from pitchquery.lang.parser import parse
from pitchquery.lang.span import Span


def where(source: str) -> Expr:
    """Parse `shots where <source>` and return the expression."""
    query = parse(f"shots where {source}")
    assert query.where is not None
    return query.where


def cmp(name: str, op: str, value: str | int | float | bool) -> Comparison:
    """Shorthand for a comparison node: cmp("xg", ">", 0.3)."""
    literal: StringLit | NumberLit | BoolLit
    if isinstance(value, bool):
        literal = BoolLit(value)
    elif isinstance(value, str):
        literal = StringLit(value)
    else:
        literal = NumberLit(value)
    return Comparison(Field(name), CmpOp(op), literal)


def parse_error(source: str) -> ParseError:
    with pytest.raises(ParseError) as info:
        parse(source)
    return info.value


# --- Entities ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "entity", ["events", "shots", "passes", "dribbles", "carries", "pressures"]
)
def test_bare_entity(entity: str) -> None:
    assert parse(entity) == Query(Entity(entity))


def test_entity_is_case_insensitive_and_stored_lowercase() -> None:
    assert parse("SHOTS") == Query(Entity("shots"))
    assert parse("Passes") == Query(Entity("passes"))


def test_surrounding_whitespace_is_ignored() -> None:
    assert parse("  shots \n") == Query(Entity("shots"))


# --- Comparisons and literals -----------------------------------------------------------


@pytest.mark.parametrize("op", ["=", "!=", "<", "<=", ">", ">="])
def test_comparison_operators(op: str) -> None:
    assert where(f"minute {op} 80") == cmp("minute", op, 80)


def test_integer_literal_is_an_int() -> None:
    expr = where("minute >= 80")
    assert isinstance(expr, Comparison) and isinstance(expr.value, NumberLit)
    assert type(expr.value.value) is int


def test_decimal_literal_is_a_float() -> None:
    expr = where("xg > 0.3")
    assert isinstance(expr, Comparison) and isinstance(expr.value, NumberLit)
    assert expr.value.value == 0.3
    assert type(expr.value.value) is float


def test_negative_number() -> None:
    assert where("x > -1.5") == cmp("x", ">", -1.5)


def test_string_literal() -> None:
    assert where('team = "Argentina"') == cmp("team", "=", "Argentina")


def test_string_with_escapes() -> None:
    assert where(r'player = "a \"b\" \\ c"') == cmp("player", "=", 'a "b" \\ c')


@pytest.mark.parametrize(("text", "value"), [("true", True), ("FALSE", False)])
def test_bool_literal(text: str, value: bool) -> None:
    assert where(f"under_pressure = {text}") == cmp("under_pressure", "=", value)


def test_field_name_is_kept_as_written() -> None:
    # Unknown or oddly cased fields are the analyzer's problem, not the parser's.
    assert where("Team = 1") == cmp("Team", "=", 1)
    assert where("xgg > 0.3") == cmp("xgg", ">", 0.3)


def test_in_list() -> None:
    assert where('type in ("Shot", "Dribble")') == InList(
        Field("type"), (StringLit("Shot"), StringLit("Dribble"))
    )


def test_in_list_with_one_value() -> None:
    assert where("period in (5)") == InList(Field("period"), (NumberLit(5),))


def test_in_list_with_mixed_literals() -> None:
    # Type checking is the analyzer's job; the grammar accepts any value.
    assert where('x in (1, "a", true)') == InList(
        Field("x"), (NumberLit(1), StringLit("a"), BoolLit(True))
    )


def test_contains() -> None:
    assert where('player contains "Messi"') == Contains(Field("player"), StringLit("Messi"))


def test_between() -> None:
    assert where("minute between 80 and 90") == Between(
        Field("minute"), NumberLit(80), NumberLit(90)
    )


def test_between_followed_by_and() -> None:
    # The `and` inside `between` belongs to it; the next `and` is the boolean operator.
    assert where('minute between 80 and 90 and team = "France"') == And(
        Between(Field("minute"), NumberLit(80), NumberLit(90)),
        cmp("team", "=", "France"),
    )


def test_two_betweens_joined_by_and() -> None:
    assert where("x between 0 and 18 and y between 18 and 62") == And(
        Between(Field("x"), NumberLit(0), NumberLit(18)),
        Between(Field("y"), NumberLit(18), NumberLit(62)),
    )


# --- Boolean operators, precedence, parentheses -----------------------------------------

A, B, C = cmp("a", "=", 1), cmp("b", "=", 2), cmp("c", "=", 3)


def test_and() -> None:
    assert where("a = 1 and b = 2") == And(A, B)


def test_or() -> None:
    assert where("a = 1 or b = 2") == Or(A, B)


def test_not() -> None:
    assert where("not a = 1") == Not(A)


def test_and_binds_tighter_than_or() -> None:
    assert where("a = 1 or b = 2 and c = 3") == Or(A, And(B, C))
    assert where("a = 1 and b = 2 or c = 3") == Or(And(A, B), C)


def test_not_binds_tighter_than_and() -> None:
    assert where("not a = 1 and b = 2") == And(Not(A), B)


def test_and_is_left_associative() -> None:
    assert where("a = 1 and b = 2 and c = 3") == And(And(A, B), C)


def test_or_is_left_associative() -> None:
    assert where("a = 1 or b = 2 or c = 3") == Or(Or(A, B), C)


def test_parentheses_override_precedence() -> None:
    assert where("(a = 1 or b = 2) and c = 3") == And(Or(A, B), C)
    assert where("a = 1 and (b = 2 or c = 3)") == And(A, Or(B, C))


def test_parentheses_on_the_right_change_associativity() -> None:
    assert where("a = 1 or (b = 2 or c = 3)") == Or(A, Or(B, C))


def test_not_with_parentheses() -> None:
    assert where("not (a = 1 or b = 2)") == Not(Or(A, B))
    assert where("not (not a = 1)") == Not(Not(A))


def test_redundant_parentheses_add_no_nodes() -> None:
    assert where("((a = 1))") == A


def test_keywords_are_case_insensitive_in_expressions() -> None:
    assert where("a = 1 AND NOT b = 2 Or c = 3") == Or(And(A, Not(B)), C)


# --- Stages -----------------------------------------------------------------------------


def test_count() -> None:
    assert parse("shots | count").stages == (CountStage(),)


def test_count_by() -> None:
    assert parse("shots | count by player").stages == (CountStage(Field("player")),)


@pytest.mark.parametrize(
    ("text", "direction"), [("asc", SortDirection.ASC), ("DESC", SortDirection.DESC)]
)
def test_sort_without_field(text: str, direction: SortDirection) -> None:
    assert parse(f"shots | sort {text}").stages == (SortStage(direction),)


def test_sort_with_field() -> None:
    assert parse("shots | sort desc xg").stages == (SortStage(SortDirection.DESC, Field("xg")),)


def test_limit() -> None:
    assert parse("shots | limit 5").stages == (LimitStage(5),)


def test_limit_zero() -> None:
    assert parse("shots | limit 0").stages == (LimitStage(0),)


def test_select() -> None:
    assert parse("shots | select player, xg, minute").stages == (
        SelectStage((Field("player"), Field("xg"), Field("minute"))),
    )


def test_stages_without_where() -> None:
    assert parse("passes | count by team | sort desc") == Query(
        Entity("passes"),
        None,
        (CountStage(Field("team")), SortStage(SortDirection.DESC)),
    )


# --- The examples from the plan ---------------------------------------------------------


def test_example_late_big_chances() -> None:
    assert parse('shots where xg > 0.3 and team = "Argentina" and minute >= 80') == Query(
        Entity("shots"),
        And(
            And(cmp("xg", ">", 0.3), cmp("team", "=", "Argentina")),
            cmp("minute", ">=", 80),
        ),
    )


def test_example_messi_passes() -> None:
    source = 'passes where player = "Lionel Messi" and outcome = "complete" and end_x > 102'
    assert parse(source) == Query(
        Entity("passes"),
        And(
            And(cmp("player", "=", "Lionel Messi"), cmp("outcome", "=", "complete")),
            cmp("end_x", ">", 102),
        ),
    )


def test_example_shots_and_dribbles_under_pressure() -> None:
    source = 'events where type in ("Shot", "Dribble") and under_pressure = true'
    assert parse(source) == Query(
        Entity("events"),
        And(
            InList(Field("type"), (StringLit("Shot"), StringLit("Dribble"))),
            cmp("under_pressure", "=", True),
        ),
    )


def test_example_top_scorers_pipeline() -> None:
    source = 'shots where team = "France" | count by player | sort desc | limit 5'
    assert parse(source) == Query(
        Entity("shots"),
        cmp("team", "=", "France"),
        (CountStage(Field("player")), SortStage(SortDirection.DESC), LimitStage(5)),
    )


# --- Spans ------------------------------------------------------------------------------


def test_spans_of_a_simple_query() -> None:
    query = parse("shots where xg > 0.3")
    assert query.span == Span(0, 20)
    assert query.entity.span == Span(0, 5)
    expr = query.where
    assert isinstance(expr, Comparison)
    assert expr.span == Span(12, 20)
    assert expr.field.span == Span(12, 14)
    assert expr.value.span == Span(17, 20)


def test_query_span_excludes_surrounding_whitespace() -> None:
    assert parse("  shots  ").span == Span(2, 7)


def test_string_literal_span_includes_quotes() -> None:
    expr = where('team = "France"')  # offset 12 in "shots where ..."
    assert isinstance(expr, Comparison)
    assert expr.value.span == Span(19, 27)


def test_binary_and_not_spans() -> None:
    #                      0         1         2
    #                      0123456789012345678901234
    query = parse("shots where not a = 1 or b = 2")
    expr = query.where
    assert isinstance(expr, Or)
    assert expr.span == Span(12, 30)
    assert expr.left.span == Span(12, 21)  # not a = 1
    assert expr.right.span == Span(25, 30)


def test_parenthesised_expression_span_includes_parentheses() -> None:
    query = parse("shots where (a = 1) and b = 2")
    expr = query.where
    assert isinstance(expr, And)
    assert expr.left.span == Span(12, 19)
    assert expr.span == Span(12, 29)


def test_in_between_contains_spans_end_at_their_last_token() -> None:
    assert where("t in (1, 2)").span == Span(12, 23)
    assert where("m between 1 and 2").span == Span(12, 29)
    assert where('p contains "x"').span == Span(12, 26)


def test_stage_spans() -> None:
    #              0         1         2         3
    #              0123456789012345678901234567890123456
    query = parse("shots | count by team | limit 5")
    assert [s.span for s in query.stages] == [Span(8, 21), Span(24, 31)]
    assert query.span == Span(0, 31)


def test_select_span() -> None:
    query = parse("shots | select a, b")
    assert query.stages[0].span == Span(8, 19)


# --- Errors -----------------------------------------------------------------------------

ENTITY_LIST = "events, shots, passes, dribbles, carries, pressures"


# One row per error case; kept one-per-line so the table reads like docs/grammar.md §4.
# fmt: off
@pytest.mark.parametrize(
    ("source", "message", "span"),
    [
        # Entity
        ("", f"Expected an entity ({ENTITY_LIST}), got end of query.", (0, 0)),
        ('"shots"', f'Expected an entity ({ENTITY_LIST}), got `"shots"`.', (0, 7)),
        ("where", f"Expected an entity ({ENTITY_LIST}), got `where`.", (0, 5)),
        ("shtos", f"Unknown entity `shtos`. Expected one of: {ENTITY_LIST}.", (0, 5)),
        # After the entity
        ('shots team = "x"', "Expected `where`, `|` or end of query, got `team`.", (6, 10)),
        ("shots shots", "Expected `where`, `|` or end of query, got `shots`.", (6, 11)),
        # Primary
        ("shots where", "Expected a field name or `(` after `where`, got end of query.", (11, 11)),
        ("shots WHERE 5", "Expected a field name or `(` after `WHERE`, got `5`.", (12, 13)),
        ("shots where where", "Expected a field name or `(` after `where`, got `where`.", (12, 17)),
        ("shots where a = 1 and", "Expected a field name or `(` after `and`, got end of query.", (21, 21)),
        ("shots where a = 1 or )", "Expected a field name or `(` after `or`, got `)`.", (21, 22)),
        ("shots where not not a = 1", "Expected a field name or `(` after `not`, got `not`.", (16, 19)),
        ("shots where (", "Expected a field name or `(` after `(`, got end of query.", (13, 13)),
        # After a field
        ("shots where minute 80", "Expected an operator after `minute`, got `80`.", (19, 21)),
        ("shots where minute", "Expected an operator after `minute`, got end of query.", (18, 18)),
        ("shots where a and b = 1", "Expected an operator after `a`, got `and`.", (14, 17)),
        # After a comparison operator
        ("shots where minute >", "Expected a value after `>`, got end of query.", (20, 20)),
        ("shots where xg > > 1", "Expected a value after `>`, got `>`.", (17, 18)),
        ("shots where team = France", "Expected a value after `=`, got `France`.", (19, 25)),
        ("shots where a != (1)", "Expected a value after `!=`, got `(`.", (17, 18)),
        # in ( ... )
        ('shots where type in "Shot"', 'Expected `(` after `in`, got `"Shot"`.', (20, 26)),
        ("shots where type in ()", "Expected a value after `(`, got `)`.", (21, 22)),
        ('shots where type in ("Shot",', 'Expected a value after `,`, got end of query.', (28, 28)),
        ('shots where type in ("Shot" "Goal")', 'Expected `,` or `)`, got `"Goal"`.', (28, 34)),
        ('shots where type in ("Shot"', "Expected `,` or `)`, got end of query.", (27, 27)),
        # contains
        ("shots where player contains 5", "Expected a string after `contains`, got `5`.", (28, 29)),
        # between
        ('shots where m between "a" and 2', 'Expected a number after `between`, got `"a"`.', (22, 25)),
        ("shots where m between 80", "Expected `and` to complete `between`, got end of query.", (24, 24)),
        ("shots where m between 80 or 90", "Expected `and` to complete `between`, got `or`.", (25, 27)),
        ('shots where m between 1 and "b"', 'Expected a number after `and`, got `"b"`.', (28, 31)),
        ("shots where m between 1 and true", "Expected a number after `and`, got `true`.", (28, 32)),
        # Parentheses
        ("shots where (xg > 0.3", "Expected `)` to close `(` at column 13, got end of query.", (21, 21)),
        ("shots where ((a = 1) or b = 2", "Expected `)` to close `(` at column 13, got end of query.", (29, 29)),
        ("shots where (a = 1 b", "Expected `)` to close `(` at column 13, got `b`.", (19, 20)),
        # After a complete where expression
        ("shots where xg > 0.3)", "Expected `and`, `or`, `|` or end of query, got `)`.", (20, 21)),
        ('shots where xg > 0.3 team = "x"', "Expected `and`, `or`, `|` or end of query, got `team`.", (21, 25)),
        ("shots where a = 1 where", "Expected `and`, `or`, `|` or end of query, got `where`.", (18, 23)),
        # Stages
        ("shots |", "Expected a stage (count, sort, limit, select) after `|`, got end of query.", (7, 7)),
        ("shots | group by team", "Expected a stage (count, sort, limit, select) after `|`, got `group`.", (8, 13)),
        ("shots | | count", "Expected a stage (count, sort, limit, select) after `|`, got `|`.", (8, 9)),
        ("shots | count by", "Expected a field name after `by`, got end of query.", (16, 16)),
        ("shots | count by 5", "Expected a field name after `by`, got `5`.", (17, 18)),
        ("shots | sort", "Expected `asc` or `desc` after `sort`, got end of query.", (12, 12)),
        ("shots | sort xg desc", "Expected `asc` or `desc` after `sort`, got `xg`.", (13, 15)),
        ("shots | limit", "Expected a non-negative integer after `limit`, got end of query.", (13, 13)),
        ("shots | limit 2.5", "Expected a non-negative integer after `limit`, got `2.5`.", (14, 17)),
        ("shots | limit -1", "Expected a non-negative integer after `limit`, got `-1`.", (14, 16)),
        ('shots | limit "5"', 'Expected a non-negative integer after `limit`, got `"5"`.', (14, 17)),
        ("shots | select", "Expected a field name after `select`, got end of query.", (14, 14)),
        ("shots | select a,", "Expected a field name after `,`, got end of query.", (17, 17)),
        ("shots | select a, count", "Expected a field name after `,`, got `count`.", (18, 23)),
        # After a complete stage
        ("shots | limit 5 6", "Expected `|` or end of query, got `6`.", (16, 17)),
        ("shots | count where", "Expected `|` or end of query, got `where`.", (14, 19)),
        ("shots | sort desc xg 5", "Expected `|` or end of query, got `5`.", (21, 22)),
        ("shots | select a b", "Expected `|` or end of query, got `b`.", (17, 18)),
    ],
)
def test_syntax_errors(source: str, message: str, span: tuple[int, int]) -> None:
    error = parse_error(source)
    assert error.message == message
    assert error.span == Span(*span)
# fmt: on


def test_lexer_errors_surface_from_parse() -> None:
    error = parse_error('shots where team = "Argentina')
    assert error.message == "Unterminated string starting at column 20."
    assert error.span == Span(19, 29)


def test_where_after_stages_is_not_allowed() -> None:
    # `where` only comes right after the entity.
    error = parse_error("shots | limit 5 where xg > 0.3")
    assert error.message == "Expected `|` or end of query, got `where`."
