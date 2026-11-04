from dataclasses import dataclass
from enum import Enum, auto

from pitchquery.lang.span import Span


class TokenKind(Enum):
    # Values
    IDENT = auto()
    STRING = auto()
    NUMBER = auto()

    # Keywords
    WHERE = auto()
    AND = auto()
    OR = auto()
    NOT = auto()
    IN = auto()
    CONTAINS = auto()
    BETWEEN = auto()
    TRUE = auto()
    FALSE = auto()
    COUNT = auto()
    BY = auto()
    SORT = auto()
    ASC = auto()
    DESC = auto()
    LIMIT = auto()
    SELECT = auto()

    # Comparison operators
    EQ = auto()  # =
    NE = auto()  # !=
    LT = auto()  # <
    LE = auto()  # <=
    GT = auto()  # >
    GE = auto()  # >=

    # Punctuation
    PIPE = auto()  # |
    LPAREN = auto()  # (
    RPAREN = auto()  # )
    COMMA = auto()  # ,

    EOF = auto()


# Lowercase spelling -> kind. Keywords are matched case-insensitively.
KEYWORDS: dict[str, TokenKind] = {
    "where": TokenKind.WHERE,
    "and": TokenKind.AND,
    "or": TokenKind.OR,
    "not": TokenKind.NOT,
    "in": TokenKind.IN,
    "contains": TokenKind.CONTAINS,
    "between": TokenKind.BETWEEN,
    "true": TokenKind.TRUE,
    "false": TokenKind.FALSE,
    "count": TokenKind.COUNT,
    "by": TokenKind.BY,
    "sort": TokenKind.SORT,
    "asc": TokenKind.ASC,
    "desc": TokenKind.DESC,
    "limit": TokenKind.LIMIT,
    "select": TokenKind.SELECT,
}


@dataclass(frozen=True, slots=True)
class Token:
    """A lexical token.

    `text` is the exact source slice, except for STRING tokens, where it is the decoded
    value without quotes (the span still covers the quotes). EOF has empty text and a
    zero-width span at the end of the input.
    """

    kind: TokenKind
    text: str
    span: Span


def quote_string(value: str) -> str:
    """Write `value` as a PitchQuery string literal, escaping `\\` and `"`."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def describe(token: Token) -> str:
    """How a token is shown in error messages: `where`, `"Shot"`, or end of query."""
    if token.kind is TokenKind.EOF:
        return "end of query"
    if token.kind is TokenKind.STRING:
        return f"`{quote_string(token.text)}`"
    return f"`{token.text}`"
