"""Lexer contract. See docs/grammar.md, sections 1 and 4."""

import pytest

from pitchquery.lang.errors import ParseError
from pitchquery.lang.lexer import tokenize
from pitchquery.lang.span import Span
from pitchquery.lang.tokens import Token, TokenKind

K = TokenKind


def kinds(source: str) -> list[TokenKind]:
    """Token kinds, without the final EOF."""
    tokens = tokenize(source)
    assert tokens[-1].kind is K.EOF
    return [t.kind for t in tokens[:-1]]


def single(source: str) -> Token:
    """The one token in `source` (besides EOF)."""
    tokens = tokenize(source)
    assert len(tokens) == 2, tokens
    return tokens[0]


def lex_error(source: str) -> ParseError:
    with pytest.raises(ParseError) as info:
        tokenize(source)
    return info.value


# --- Basics -----------------------------------------------------------------------------


def test_empty_input_is_just_eof() -> None:
    assert tokenize("") == [Token(K.EOF, "", Span(0, 0))]


def test_whitespace_only_is_just_eof_at_the_end() -> None:
    assert tokenize("  \t\n ") == [Token(K.EOF, "", Span(5, 5))]


def test_full_query_with_spans() -> None:
    assert tokenize("shots where xg > 0.3 | limit 5") == [
        Token(K.IDENT, "shots", Span(0, 5)),
        Token(K.WHERE, "where", Span(6, 11)),
        Token(K.IDENT, "xg", Span(12, 14)),
        Token(K.GT, ">", Span(15, 16)),
        Token(K.NUMBER, "0.3", Span(17, 20)),
        Token(K.PIPE, "|", Span(21, 22)),
        Token(K.LIMIT, "limit", Span(23, 28)),
        Token(K.NUMBER, "5", Span(29, 30)),
        Token(K.EOF, "", Span(30, 30)),
    ]


def test_tokens_need_no_whitespace_between_them() -> None:
    assert kinds("xg>0.3") == [K.IDENT, K.GT, K.NUMBER]
    assert kinds("minute>=80") == [K.IDENT, K.GE, K.NUMBER]
    assert kinds('type in("Shot","Pass")') == [
        K.IDENT, K.IN, K.LPAREN, K.STRING, K.COMMA, K.STRING, K.RPAREN,
    ]  # fmt: skip


def test_all_whitespace_kinds_are_skipped() -> None:
    assert kinds("shots\twhere\n  xg\r\n> 1") == [K.IDENT, K.WHERE, K.IDENT, K.GT, K.NUMBER]


def test_text_is_the_source_slice_for_non_string_tokens() -> None:
    source = "SHOTS Where end_x >= -12.5 | Sort DESC xg | select a, b"
    for token in tokenize(source):
        assert source[token.span.start : token.span.end] == token.text


# --- Identifiers and keywords -----------------------------------------------------------


@pytest.mark.parametrize("name", ["xg", "end_x", "under_pressure", "_private", "a1", "Team"])
def test_identifiers(name: str) -> None:
    assert single(name) == Token(K.IDENT, name, Span(0, len(name)))


@pytest.mark.parametrize(
    ("word", "kind"),
    [
        ("where", K.WHERE),
        ("and", K.AND),
        ("or", K.OR),
        ("not", K.NOT),
        ("in", K.IN),
        ("contains", K.CONTAINS),
        ("between", K.BETWEEN),
        ("true", K.TRUE),
        ("false", K.FALSE),
        ("count", K.COUNT),
        ("by", K.BY),
        ("sort", K.SORT),
        ("asc", K.ASC),
        ("desc", K.DESC),
        ("limit", K.LIMIT),
        ("select", K.SELECT),
    ],
)
def test_keywords(word: str, kind: TokenKind) -> None:
    assert single(word).kind is kind


@pytest.mark.parametrize("word", ["WHERE", "Where", "wHeRe"])
def test_keywords_are_case_insensitive_and_keep_their_text(word: str) -> None:
    assert single(word) == Token(K.WHERE, word, Span(0, 5))


def test_entities_are_identifiers_not_keywords() -> None:
    for entity in ["events", "shots", "passes", "dribbles", "carries", "pressures"]:
        assert single(entity).kind is K.IDENT


def test_keyword_prefix_is_still_an_identifier() -> None:
    assert single("wherever").kind is K.IDENT
    assert single("order").kind is K.IDENT  # contains "or"
    assert single("index").kind is K.IDENT  # starts with "in"


# --- Numbers ----------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["0", "7", "80", "120", "0.3", "102.5", "120.0", "-1", "-0.25"])
def test_numbers(text: str) -> None:
    assert single(text) == Token(K.NUMBER, text, Span(0, len(text)))


def test_number_followed_by_dot_is_an_error() -> None:
    error = lex_error("shots | limit 5.")
    assert error.message == "Expected a digit after `.`."
    assert error.span == Span(14, 16)


def test_minus_without_digit_is_an_error() -> None:
    error = lex_error("minute > - 5")
    assert error.message == "Expected a digit after `-`."
    assert error.span == Span(9, 10)


def test_leading_dot_is_an_unexpected_character() -> None:
    error = lex_error("xg > .5")
    assert error.message == "Unexpected character `.`."
    assert error.span == Span(5, 6)


# --- Strings ----------------------------------------------------------------------------


def test_string_text_is_decoded_and_span_covers_quotes() -> None:
    assert single('"Argentina"') == Token(K.STRING, "Argentina", Span(0, 11))


def test_empty_string() -> None:
    assert single('""') == Token(K.STRING, "", Span(0, 2))


def test_escaped_quote_and_backslash() -> None:
    assert single(r'"say \"hi\""') == Token(K.STRING, 'say "hi"', Span(0, 12))
    assert single(r'"a\\b"') == Token(K.STRING, "a\\b", Span(0, 6))
    assert single(r'"\\"') == Token(K.STRING, "\\", Span(0, 4))


def test_string_keeps_unicode_and_inner_whitespace() -> None:
    assert single('"Kylian  Mbappé"').text == "Kylian  Mbappé"


def test_keywords_and_symbols_inside_strings_are_plain_text() -> None:
    assert single('"a | b where (c)"').text == "a | b where (c)"


def test_unterminated_string() -> None:
    source = 'shots where team = "Argentina'
    error = lex_error(source)
    assert error.message == "Unterminated string starting at column 20."
    assert error.span == Span(19, len(source))


def test_unterminated_string_ending_in_backslash() -> None:
    error = lex_error('"abc\\')
    assert error.message == "Unterminated string starting at column 1."
    assert error.span == Span(0, 5)


def test_unknown_escape() -> None:
    error = lex_error(r'team = "a\nb"')
    assert error.message == (
        r"Unknown escape sequence `\n`. Use `\"` for a quote or `\\` for a backslash."
    )
    assert error.span == Span(9, 11)


# --- Operators and punctuation ----------------------------------------------------------


def test_operators() -> None:
    assert tokenize("= != < <= > >=") == [
        Token(K.EQ, "=", Span(0, 1)),
        Token(K.NE, "!=", Span(2, 4)),
        Token(K.LT, "<", Span(5, 6)),
        Token(K.LE, "<=", Span(7, 9)),
        Token(K.GT, ">", Span(10, 11)),
        Token(K.GE, ">=", Span(12, 14)),
        Token(K.EOF, "", Span(14, 14)),
    ]


def test_operators_use_longest_match() -> None:
    assert kinds("<==") == [K.LE, K.EQ]
    assert kinds("< =") == [K.LT, K.EQ]


def test_punctuation() -> None:
    assert kinds("|(),") == [K.PIPE, K.LPAREN, K.RPAREN, K.COMMA]


def test_bang_without_equals() -> None:
    error = lex_error('team ! "x"')
    assert error.message == "Expected `=` after `!`."
    assert error.span == Span(5, 6)


@pytest.mark.parametrize(("source", "char", "offset"), [("xg @ 1", "@", 3), ("a;", ";", 1)])
def test_unexpected_character(source: str, char: str, offset: int) -> None:
    error = lex_error(source)
    assert error.message == f"Unexpected character `{char}`."
    assert error.span == Span(offset, offset + 1)


def test_single_quotes_are_not_strings() -> None:
    error = lex_error("team = 'France'")
    assert error.message == "Unexpected character `'`."
    assert error.span == Span(7, 8)
