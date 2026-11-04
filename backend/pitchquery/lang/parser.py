"""Recursive descent parser: query source text -> AST. See docs/grammar.md, sections 2-4.

TO IMPLEMENT (Lucas). The contract is tested in tests/lang/test_parser.py and
tests/lang/test_roundtrip.py.
"""

from pitchquery.lang.ast import Query


def parse(source: str) -> Query:
    """Parse a whole query.

    Raises:
        ParseError: on the first lexing or syntax error, with the offending span.
    """
    raise NotImplementedError("parser not implemented yet")
