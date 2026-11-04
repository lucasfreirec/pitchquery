"""Property-based tests for the parser.

1. Round trip: for any valid AST, parse(to_source(ast)) == ast.
2. Robustness: on any input whatsoever, parse() returns a Query or raises ParseError,
   never anything else (no IndexError, no infinite loop...).
"""

import contextlib

from hypothesis import example, given
from hypothesis import strategies as st

from pitchquery.lang.ast import Query
from pitchquery.lang.errors import ParseError
from pitchquery.lang.parser import parse
from pitchquery.lang.printer import to_source
from tests.lang.strategies import queries

# Single characters (including invalid ones) plus whole keywords and values, so random
# inputs get deep into the grammar instead of failing on the first token.
QUERY_CHARS = st.sampled_from(
    [
        *'abcdefghijklmnopqrstuvwxyz_0123456789.- \t"\\|(),=!<>@',
        *("shots", "where", "and", "or", "not", "in", "between", "contains", "count"),
        *("by", "sort", "desc", "limit", "select", "true", " xg ", " 0.3 ", '"Messi"'),
    ]
)


@given(queries)
def test_print_then_parse_round_trips(query: Query) -> None:
    source = to_source(query)
    assert parse(source) == query, source


@given(queries)
def test_printing_is_stable(query: Query) -> None:
    # Printing a parsed query gives back the same text: the printer is canonical.
    source = to_source(query)
    assert to_source(parse(source)) == source


@given(st.lists(QUERY_CHARS, max_size=30).map("".join))
@example("shots where (((")
@example('shots where team = "')
@example("shots | limit 99999999999999999999999")
def test_parse_never_crashes(source: str) -> None:
    try:
        result = parse(source)
    except ParseError as error:
        assert 0 <= error.span.start <= error.span.end <= len(source)
    else:
        assert isinstance(result, Query)


@given(st.text(max_size=40))
def test_parse_never_crashes_on_arbitrary_text(source: str) -> None:
    with contextlib.suppress(ParseError):
        parse(source)
