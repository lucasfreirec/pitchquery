"""The printer turns ASTs back into canonical source. Independent of the parser."""

from pitchquery.lang.ast import (
    And,
    Between,
    BoolLit,
    CmpOp,
    Comparison,
    Contains,
    CountStage,
    Entity,
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
from pitchquery.lang.printer import to_source

A = Comparison(Field("a"), CmpOp.EQ, NumberLit(1))
B = Comparison(Field("b"), CmpOp.EQ, NumberLit(2))
C = Comparison(Field("c"), CmpOp.EQ, NumberLit(3))


def shots_where(expr: And | Or | Not | Comparison) -> str:
    return to_source(Query(Entity("shots"), expr))


def test_bare_entity() -> None:
    assert to_source(Query(Entity("passes"))) == "passes"


def test_literals() -> None:
    assert shots_where(Comparison(Field("xg"), CmpOp.GT, NumberLit(0.3))) == "shots where xg > 0.3"
    assert shots_where(Comparison(Field("m"), CmpOp.GE, NumberLit(80))) == "shots where m >= 80"
    assert shots_where(Comparison(Field("x"), CmpOp.LT, NumberLit(-1.5))) == "shots where x < -1.5"
    assert shots_where(Comparison(Field("u"), CmpOp.EQ, BoolLit(True))) == "shots where u = true"


def test_strings_are_escaped() -> None:
    expr = Comparison(Field("p"), CmpOp.NE, StringLit('a "b" \\ c'))
    assert shots_where(expr) == r'shots where p != "a \"b\" \\ c"'


def test_predicates() -> None:
    query = Query(
        Entity("events"),
        And(
            And(
                InList(Field("type"), (StringLit("Shot"), StringLit("Pass"))),
                Contains(Field("player"), StringLit("Messi")),
            ),
            Between(Field("minute"), NumberLit(80), NumberLit(90)),
        ),
    )
    assert to_source(query) == (
        'events where type in ("Shot", "Pass") and player contains "Messi"'
        " and minute between 80 and 90"
    )


def test_left_associative_chains_need_no_parentheses() -> None:
    assert shots_where(And(And(A, B), C)) == "shots where a = 1 and b = 2 and c = 3"
    assert shots_where(Or(Or(A, B), C)) == "shots where a = 1 or b = 2 or c = 3"


def test_right_nested_same_operator_is_parenthesised() -> None:
    assert shots_where(And(A, And(B, C))) == "shots where a = 1 and (b = 2 and c = 3)"
    assert shots_where(Or(A, Or(B, C))) == "shots where a = 1 or (b = 2 or c = 3)"


def test_precedence() -> None:
    assert shots_where(Or(A, And(B, C))) == "shots where a = 1 or b = 2 and c = 3"
    assert shots_where(And(Or(A, B), C)) == "shots where (a = 1 or b = 2) and c = 3"
    assert shots_where(And(A, Or(B, C))) == "shots where a = 1 and (b = 2 or c = 3)"


def test_not() -> None:
    assert shots_where(Not(A)) == "shots where not a = 1"
    assert shots_where(And(Not(A), B)) == "shots where not a = 1 and b = 2"
    assert shots_where(Not(And(A, B))) == "shots where not (a = 1 and b = 2)"
    assert shots_where(Not(Not(A))) == "shots where not (not a = 1)"


def test_stages() -> None:
    query = Query(
        Entity("shots"),
        None,
        (
            CountStage(Field("player")),
            SortStage(SortDirection.DESC),
            SortStage(SortDirection.ASC, Field("xg")),
            LimitStage(5),
            SelectStage((Field("player"), Field("xg"))),
            CountStage(),
        ),
    )
    assert to_source(query) == (
        "shots | count by player | sort desc | sort asc xg | limit 5 | select player, xg | count"
    )
