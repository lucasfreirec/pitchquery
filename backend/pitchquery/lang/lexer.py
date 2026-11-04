"""Lexer: query source text -> list of tokens. See docs/grammar.md, section 1.

TO IMPLEMENT (Lucas). The contract is tested in tests/lang/test_lexer.py.
"""

from pitchquery.lang.tokens import Token


def tokenize(source: str) -> list[Token]:
    """Split `source` into tokens, ending with an EOF token.

    Raises:
        ParseError: on an invalid character, number or string (see docs/grammar.md §4).
    """
    raise NotImplementedError("lexer not implemented yet")
