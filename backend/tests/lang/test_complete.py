"""Autocompletion. `‸` marks the cursor in each source."""

import pytest

from pitchquery.data.values import ValueIndex
from pitchquery.lang.ast import ENTITIES
from pitchquery.lang.complete import Suggestion, SuggestionKind, complete
from pitchquery.lang.schema import FIELDS
from pitchquery.lang.span import Span

CURSOR = "‸"

VALUES: ValueIndex = {
    "team": [
        {"value": "Argentina", "count": 300},
        {"value": "France", "count": 250},
        {"value": "Australia", "count": 100},
    ],
    "player": [
        {"value": "Lionel Messi", "count": 90},
        {"value": "Kylian Mbappé", "count": 80},
        {"value": "Messias", "count": 5},
    ],
    "type": [
        {"value": "Pass", "count": 1000},
        {"value": "Shot", "count": 50},
    ],
}

ALL_FIELDS = list(FIELDS)
PASS_FIELDS = [f for f in FIELDS if f != "xg"]
TEAMS = ['"Argentina"', '"France"', '"Australia"']
TYPES = ['"Pass"', '"Shot"']
NUMBER_OPS = ["=", "!=", "<", "<=", ">", ">=", "in", "between"]


def at(marked: str, values: ValueIndex | None = VALUES) -> list[Suggestion]:
    assert marked.count(CURSOR) == 1, marked
    cursor = marked.index(CURSOR)
    return complete(marked.replace(CURSOR, ""), cursor, values)


def labels(marked: str, values: ValueIndex | None = VALUES) -> list[str]:
    return [s.label for s in at(marked, values)]


# --- One row per position type ----------------------------------------------------------

POSITIONS = [
    # Entity
    ("start of input", "‸", list(ENTITIES)),
    ("partial entity", "sh‸", ["shots"]),
    ("partial entity, any case", "PA‸", ["passes"]),
    # After the entity
    ("after entity", "shots ‸", ["where", "|"]),
    ("partial keyword", "shots wh‸", ["where"]),
    # Field position
    ("after where", "shots where ‸", [*ALL_FIELDS, "not"]),
    ("fields depend on the entity", "passes where ‸", [*PASS_FIELDS, "not"]),
    ("partial field", "shots where mi‸", ["minute"]),
    ("after not", "shots where not ‸", ALL_FIELDS),
    ("after (", "shots where (‸", [*ALL_FIELDS, "not"]),
    ("after and", 'shots where team = "France" and ‸', [*ALL_FIELDS, "not"]),
    # Operator position
    ("operators for a number", "shots where xg ‸", NUMBER_OPS),
    ("operators for a string", "shots where team ‸", ["=", "!=", "in", "contains"]),
    ("operators for a boolean", "shots where under_pressure ‸", ["=", "!="]),
    ("operators, partial", "shots where team c‸", ["contains"]),
    ("operators for an unknown field", "shots where foo ‸", [*NUMBER_OPS[:6], "in", "contains", "between"]),
    # Value position
    ("string values by frequency", "shots where team = ‸", TEAMS),
    ("values after !=", "shots where team != ‸", TEAMS),
    ("partial quoted value", 'shots where team = "Fr‸', ['"France"']),
    ("partial unquoted value", "shots where team = Ar‸", ['"Argentina"']),
    ("prefix matches, then substring", 'shots where team = "a‸', ['"Argentina"', '"Australia"', '"France"']),
    ("full prefix before word prefix", 'shots where player = "mes‸', ['"Messias"', '"Lionel Messi"']),
    ("value matching ignores accents", 'shots where player = "mbappe‸', ['"Kylian Mbappé"']),
    ("boolean values", "shots where under_pressure = ‸", ["true", "false"]),
    ("no suggestions for numbers", "shots where xg > ‸", []),
    ("values in a list", "shots where type in (‸", TYPES),
    ("values after a comma", 'shots where type in ("Shot", ‸', TYPES),
    ("after in", "shots where type in ‸", ["("]),
    ("inside a list after a value", 'shots where type in ("Shot" ‸', [",", ")"]),
    ("between needs and", "shots where minute between 80 ‸", ["and"]),
    ("no suggestions for contains", "shots where player contains ‸", []),
    # After a complete predicate
    ("after a predicate", "shots where xg > 0.3 ‸", ["and", "or", "|"]),
    ("after a predicate in parentheses", "shots where (xg > 0.3 ‸", ["and", "or", ")"]),
    ("partial and", "shots where xg > 0.3 an‸", ["and"]),
    # Stages
    ("after |", "shots | ‸", ["count", "sort", "limit", "select"]),
    ("partial stage", "shots | co‸", ["count"]),
    ("after count", "shots | count ‸", ["by", "|"]),
    ("after count by", "shots | count by ‸", ALL_FIELDS),
    ("count by depends on the entity", "passes | count by ‸", PASS_FIELDS),
    ("after sort", "shots | sort ‸", ["asc", "desc"]),
    ("after sort desc: only remaining columns", "shots | count by player | sort desc ‸", ["player", "|"]),
    ("after select: only selected columns", "shots | select player, minute | sort asc ‸", ["player", "minute", "|"]),
    ("nothing left after count", "shots | count | select ‸", []),
    ("no suggestions for limit", "shots | limit ‸", []),
    ("after a complete stage", "shots | limit 5 ‸", ["|"]),
]  # fmt: skip


@pytest.mark.parametrize(("name", "marked", "expected"), POSITIONS, ids=[p[0] for p in POSITIONS])
def test_positions(name: str, marked: str, expected: list[str]) -> None:
    assert labels(marked) == expected


# --- Replacement spans ------------------------------------------------------------------


def test_span_is_empty_at_the_cursor_without_a_partial_word() -> None:
    assert all(s.span == Span(6, 6) for s in at("shots ‸"))


def test_span_covers_the_partial_word() -> None:
    assert at("shots wh‸")[0].span == Span(6, 8)


def test_span_covers_the_whole_word_when_the_cursor_is_inside_it() -> None:
    assert at("shots wh‸ere xg > 1")[0] == Suggestion("where", SuggestionKind.KEYWORD, Span(6, 11))


def test_span_of_a_partial_string_starts_at_the_quote() -> None:
    assert at('shots where team = "Fr‸')[0].span == Span(19, 22)


def test_span_includes_an_auto_closed_quote() -> None:
    assert at('shots where team = "Fr‸"')[0].span == Span(19, 23)


def test_span_covers_the_rest_of_a_string_the_cursor_is_inside() -> None:
    assert at('shots where team = "Fr‸ance" | count')[0].span == Span(19, 27)


def test_span_of_an_unquoted_partial_value() -> None:
    assert at("shots where team = Ar‸")[0].span == Span(19, 21)


# --- Kinds and details ------------------------------------------------------------------


def test_kinds() -> None:
    assert at("shots ‸")[0].kind is SuggestionKind.KEYWORD
    assert at("shots where mi‸")[0].kind is SuggestionKind.FIELD
    assert at("shots where xg ‸")[0].kind is SuggestionKind.OPERATOR
    assert at("shots where team = ‸")[0].kind is SuggestionKind.VALUE
    assert at("‸")[0].kind is SuggestionKind.ENTITY


def test_field_detail_shows_type_and_description() -> None:
    assert at("shots where mi‸")[0].detail == "number · Match minute (0-127, extra time included)"


def test_value_detail_shows_frequency() -> None:
    assert at("shots where team = ‸")[0].detail == "300 events"


# --- Robustness -------------------------------------------------------------------------


def test_text_after_the_cursor_is_ignored() -> None:
    assert labels("shots ‸ where xg > 1") == ["where", "|"]


def test_no_suggestions_after_a_syntax_error() -> None:
    assert labels("shots where where ‸") == []


def test_no_suggestions_after_a_lexer_error() -> None:
    assert labels("shots @ ‸") == []


def test_no_values_without_an_index() -> None:
    assert labels("shots where team = ‸", values=None) == []


def test_limit() -> None:
    assert len(complete("shots where ", 12, VALUES, limit=3)) == 3


@pytest.mark.parametrize("cursor", [-1, 6])
def test_cursor_out_of_range(cursor: int) -> None:
    with pytest.raises(ValueError):
        complete("shots", cursor)


def test_every_prefix_of_a_long_query_completes_without_error() -> None:
    source = (
        'events where (type in ("Shot", "Pass") or not team = "France") and minute '
        'between 80 and 90 and player contains "mes" | count by player | sort desc | limit 5'
    )
    for cursor in range(len(source) + 1):
        complete(source, cursor, VALUES)
