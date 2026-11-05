"""Semantic analysis. See docs/grammar.md, section 5."""

import pytest

from pitchquery.data.values import ValueIndex
from pitchquery.lang.analyzer import check
from pitchquery.lang.diagnostics import Diagnostic, Severity
from pitchquery.lang.span import Span

ERROR, WARNING = Severity.ERROR, Severity.WARNING

# A small value index, values in frequency order like the real one.
VALUES: ValueIndex = {
    "team": [
        {"value": "Argentina", "count": 300},
        {"value": "France", "count": 250},
        {"value": "Australia", "count": 100},
    ],
    "player": [
        {"value": "Lionel Messi", "count": 90},
        {"value": "Kylian Mbappé", "count": 80},
    ],
    "outcome": [
        {"value": "Complete", "count": 500},
        {"value": "Incomplete", "count": 100},
        {"value": "Goal", "count": 10},
    ],
    "type": [
        {"value": "Pass", "count": 1000},
        {"value": "Shot", "count": 50},
        {"value": "Dribble", "count": 40},
    ],
}


def diagnostics(source: str, values: ValueIndex | None = VALUES) -> list[Diagnostic]:
    return list(check(source, values).diagnostics)


def only(source: str, values: ValueIndex | None = VALUES) -> Diagnostic:
    found = diagnostics(source, values)
    assert len(found) == 1, found
    return found[0]


# --- The error table from the plan (M3 "done when") --------------------------------------


def test_table_unknown_field() -> None:
    assert only("shots where xgg > 0.3") == Diagnostic(
        ERROR, "Unknown field `xgg`. Did you mean `xg`?", Span(12, 15), ("xg",)
    )


def test_table_wrong_value_type() -> None:
    assert only('shots where xg > "high"') == Diagnostic(
        ERROR, "`xg` is a number; expected a number, got a string.", Span(17, 23)
    )


def test_table_field_not_valid_for_entity() -> None:
    assert only("passes where xg > 0.3") == Diagnostic(
        ERROR, "`xg` only exists for `shots`.", Span(13, 15)
    )


def test_table_unterminated_string() -> None:
    assert only('shots where team = "Argentina') == Diagnostic(
        ERROR, "Unterminated string starting at column 20.", Span(19, 29)
    )


def test_table_missing_value() -> None:
    assert only("shots where minute >") == Diagnostic(
        ERROR, "Expected a value after `>`, got end of query.", Span(20, 20)
    )


def test_table_unknown_value_is_a_warning() -> None:
    assert only('shots where team = "Argentna"') == Diagnostic(
        WARNING,
        "No team `Argentna` in the data. Did you mean `Argentina`?",
        Span(19, 29),
        ("Argentina",),
    )


# --- Valid queries ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "shots",
        'shots where xg > 0.3 and team = "Argentina" and minute >= 80',
        'passes where player = "Lionel Messi" and outcome = "complete" and end_x > 102',
        'events where type in ("Shot", "Dribble") and under_pressure = true',
        'shots where team = "France" | count by player | sort desc | limit 5',
        "events where xg > 0.5",  # `events` includes shots
        'carries where end_x between 102 and 120 and not team = "France"',
        'shots where player contains "mess"',  # contains is not checked against values
        "shots where minute > 80.5",  # an int field accepts any number
        'shots where Team = "FRANCE"',  # field names and values are case-insensitive
        "shots | count by player | select player",
        "passes | select player, end_x, end_y | sort desc end_x",
    ],
)
def test_valid_queries_have_no_diagnostics(source: str) -> None:
    result = check(source, VALUES)
    assert result.diagnostics == ()
    assert result.ok
    assert result.query is not None


# --- Fields -----------------------------------------------------------------------------


def test_unknown_field_without_suggestion() -> None:
    assert only("shots where foo = 1") == Diagnostic(ERROR, "Unknown field `foo`.", Span(12, 15))


def test_restricted_field_lists_all_its_entities() -> None:
    diagnostic = only("dribbles where end_x > 100")
    assert diagnostic.message == "`end_x` only exists for `shots`, `passes` and `carries`."
    assert diagnostic.span == Span(15, 20)


def test_restricted_field_with_two_entities() -> None:
    assert only('pressures where body_part = "Head"').message == (
        "`body_part` only exists for `shots` and `passes`."
    )


# --- Operators and types ----------------------------------------------------------------


def test_ordering_operator_on_a_string_field() -> None:
    assert only('shots where team > "A"') == Diagnostic(
        ERROR,
        "`>` does not apply to `team`, which is a string. Use one of: `=`, `!=`, `in`, `contains`.",
        Span(12, 22),
    )


def test_contains_on_a_number_field() -> None:
    assert only('shots where minute contains "8"').message == (
        "`contains` does not apply to `minute`, which is a number. "
        "Use one of: `=`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `between`."
    )


def test_between_on_a_boolean_field() -> None:
    assert only("shots where under_pressure between 0 and 1").message == (
        "`between` does not apply to `under_pressure`, which is a boolean. Use one of: `=`, `!=`."
    )


def test_boolean_field_with_a_string() -> None:
    assert only('shots where under_pressure = "yes"') == Diagnostic(
        ERROR, "`under_pressure` is a boolean; expected a boolean, got a string.", Span(29, 34)
    )


def test_string_field_with_a_number() -> None:
    assert only("shots where team = 5").message == (
        "`team` is a string; expected a string, got a number."
    )


def test_string_field_with_a_boolean() -> None:
    assert only("shots where team = true").message == (
        "`team` is a string; expected a string, got a boolean."
    )


def test_every_wrong_value_in_a_list_is_reported() -> None:
    found = diagnostics('shots where type in ("Shot", 5, true)')
    assert [(d.message, d.span) for d in found] == [
        ("`type` is a string; expected a string, got a number.", Span(29, 30)),
        ("`type` is a string; expected a string, got a boolean.", Span(32, 36)),
    ]


def test_reversed_between_is_a_warning() -> None:
    assert only("shots where minute between 90 and 80") == Diagnostic(
        WARNING,
        "Empty range: the lower bound 90 is greater than the upper bound 80.",
        Span(12, 36),
    )


# --- Values -----------------------------------------------------------------------------


def test_unknown_value_without_suggestion() -> None:
    assert only('shots where team = "Atlantis"') == Diagnostic(
        WARNING, "No team `Atlantis` in the data.", Span(19, 29)
    )


def test_unknown_value_with_not_equal() -> None:
    assert only('shots where team != "Argentna"').severity is WARNING


def test_unknown_value_in_a_list() -> None:
    diagnostic = only('shots where team in ("France", "Argentna")')
    assert diagnostic.span == Span(31, 41)
    assert diagnostic.suggestions == ("Argentina",)


def test_value_suggestion_by_substring() -> None:
    assert only('shots where player = "Messi"').message == (
        "No player `Messi` in the data. Did you mean `Lionel Messi`?"
    )


def test_value_suggestions_are_ranked_by_frequency_on_ties() -> None:
    # "Irax" is 1 edit from both; the index lists values most frequent first.
    iran_first: ValueIndex = {
        "team": [{"value": "Iran", "count": 9}, {"value": "Iraq", "count": 1}]
    }
    iraq_first: ValueIndex = {
        "team": [{"value": "Iraq", "count": 9}, {"value": "Iran", "count": 1}]
    }
    assert only('shots where team = "Irax"', iran_first).suggestions == ("Iran", "Iraq")
    assert only('shots where team = "Irax"', iraq_first).suggestions == ("Iraq", "Iran")


def test_values_are_not_checked_without_an_index() -> None:
    assert diagnostics('shots where team = "Atlantis"', values=None) == []


def test_fields_missing_from_the_index_are_not_checked() -> None:
    assert diagnostics('shots where position = "Goalkeeper"') == []


# --- Several diagnostics at once --------------------------------------------------------


def test_all_problems_are_reported_in_source_order() -> None:
    found = diagnostics('passes where xgg > 0.3 and team = 5 or xg > 1 and team = "Frnce"')
    assert [(d.severity, d.message) for d in found] == [
        (ERROR, "Unknown field `xgg`. Did you mean `xg`?"),
        (ERROR, "`team` is a string; expected a string, got a number."),
        (ERROR, "`xg` only exists for `shots`."),
        (WARNING, "No team `Frnce` in the data. Did you mean `France`?"),
    ]


def test_unknown_field_does_not_cascade_into_type_errors() -> None:
    assert len(diagnostics('shots where xgg > "high"')) == 1


# --- Stages -----------------------------------------------------------------------------


def test_unknown_field_in_count_by() -> None:
    assert only("shots | count by plyer") == Diagnostic(
        ERROR, "Unknown field `plyer`. Did you mean `player`?", Span(17, 22), ("player",)
    )


def test_restricted_field_in_a_stage() -> None:
    assert only("passes | sort desc xg").message == "`xg` only exists for `shots`."


def test_field_not_available_after_count_by() -> None:
    assert only("shots | count by player | sort desc xg") == Diagnostic(
        ERROR, "`xg` is not available after `count by player`. Available: `player`.", Span(36, 38)
    )


def test_field_not_available_after_select() -> None:
    assert only("shots | select player, minute | select xg").message == (
        "`xg` is not available after `select player, minute`. Available: `player`, `minute`."
    )


def test_nothing_available_after_plain_count() -> None:
    assert only("shots | count | select team").message == ("`team` is not available after `count`.")


def test_available_fields_are_case_insensitive() -> None:
    assert diagnostics("shots | count by Player | sort asc PLAYER") == []


# --- check() ----------------------------------------------------------------------------


def test_check_returns_the_query_even_with_warnings() -> None:
    result = check('shots where team = "Atlantis"', VALUES)
    assert result.query is not None
    assert result.ok  # warnings do not block running the query


def test_check_with_errors_is_not_ok() -> None:
    result = check("shots where xgg > 1", VALUES)
    assert result.query is not None
    assert not result.ok


def test_check_with_a_syntax_error_has_no_query() -> None:
    result = check("shots where", VALUES)
    assert result.query is None
    assert not result.ok
    assert result.diagnostics[0].severity is ERROR
