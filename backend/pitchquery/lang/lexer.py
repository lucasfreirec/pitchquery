"""Lexer: query source text -> list of tokens. See docs/grammar.md, section 1.

A single left-to-right pass. At each position, the current character decides which kind
of token starts there; a helper reads to the end of that token and returns it. Errors are
raised immediately as ParseError with the exact span of the offending text.
"""

from pitchquery.lang.errors import ParseError
from pitchquery.lang.span import Span
from pitchquery.lang.tokens import KEYWORDS, Token, TokenKind

_PUNCTUATION: dict[str, TokenKind] = {
    "|": TokenKind.PIPE,
    "(": TokenKind.LPAREN,
    ")": TokenKind.RPAREN,
    ",": TokenKind.COMMA,
    "=": TokenKind.EQ,
}

# Operators that may be followed by `=`: (kind alone, kind with `=`).
_COMPARISONS: dict[str, tuple[TokenKind, TokenKind]] = {
    "<": (TokenKind.LT, TokenKind.LE),
    ">": (TokenKind.GT, TokenKind.GE),
}


def tokenize(source: str) -> list[Token]:
    """Split `source` into tokens, ending with an EOF token.

    Raises:
        ParseError: on an invalid character, number or string (see docs/grammar.md §4).
    """
    return _Lexer(source).run()


def _is_digit(char: str) -> bool:
    # str.isdigit() also accepts characters like "²" or "٣"; the grammar only has 0-9.
    return "0" <= char <= "9"


def _is_ident_start(char: str) -> bool:
    return char == "_" or "a" <= char <= "z" or "A" <= char <= "Z"


def _is_ident_char(char: str) -> bool:
    return _is_ident_start(char) or _is_digit(char)


class _Lexer:
    def __init__(self, source: str) -> None:
        self.source = source
        self.pos = 0

    def run(self) -> list[Token]:
        tokens: list[Token] = []
        while True:
            self._skip_whitespace()
            if self._at_end():
                end = len(self.source)
                tokens.append(Token(TokenKind.EOF, "", Span(end, end)))
                return tokens
            tokens.append(self._next_token())

    # --- Helpers ------------------------------------------------------------------------

    def _at_end(self) -> bool:
        return self.pos >= len(self.source)

    def _peek(self, offset: int = 0) -> str:
        """The character `offset` positions ahead, or "" past the end of the input."""
        index = self.pos + offset
        return self.source[index] if index < len(self.source) else ""

    def _skip_whitespace(self) -> None:
        while not self._at_end() and self.source[self.pos].isspace():
            self.pos += 1

    def _token(self, kind: TokenKind, start: int) -> Token:
        """A token whose text is the source slice from `start` to the current position."""
        return Token(kind, self.source[start : self.pos], Span(start, self.pos))

    # --- Dispatch -----------------------------------------------------------------------

    def _next_token(self) -> Token:
        char = self._peek()
        if _is_ident_start(char):
            return self._identifier()
        if _is_digit(char) or char == "-":
            return self._number()
        if char == '"':
            return self._string()
        return self._operator()

    def _identifier(self) -> Token:
        start = self.pos
        while _is_ident_char(self._peek()):
            self.pos += 1
        # Keywords are identifiers with a reserved spelling, matched case-insensitively.
        # The token keeps the text as written, so errors can quote the user's input.
        kind = KEYWORDS.get(self.source[start : self.pos].lower(), TokenKind.IDENT)
        return self._token(kind, start)

    def _number(self) -> Token:
        start = self.pos
        if self._peek() == "-":
            self.pos += 1
            if not _is_digit(self._peek()):
                raise ParseError("Expected a digit after `-`.", Span(start, self.pos))
        self._digits()
        if self._peek() == ".":
            self.pos += 1
            if not _is_digit(self._peek()):
                raise ParseError("Expected a digit after `.`.", Span(start, self.pos))
            self._digits()
        return self._token(TokenKind.NUMBER, start)

    def _digits(self) -> None:
        while _is_digit(self._peek()):
            self.pos += 1

    def _string(self) -> Token:
        start = self.pos
        self.pos += 1  # opening quote
        chars: list[str] = []
        while True:
            char = self._peek()
            if char == "":
                raise ParseError(
                    f"Unterminated string starting at column {start + 1}.",
                    Span(start, len(self.source)),
                )
            if char == '"':
                self.pos += 1  # closing quote
                # The text is the decoded value; the span still covers both quotes.
                return Token(TokenKind.STRING, "".join(chars), Span(start, self.pos))
            if char == "\\":
                chars.append(self._escape(start))
            else:
                chars.append(char)
                self.pos += 1

    def _escape(self, string_start: int) -> str:
        """Decode the escape sequence at the current position (a backslash)."""
        escaped = self._peek(1)
        if escaped == "":
            # A backslash as the last character: the closing quote can never come.
            raise ParseError(
                f"Unterminated string starting at column {string_start + 1}.",
                Span(string_start, len(self.source)),
            )
        if escaped not in ('"', "\\"):
            raise ParseError(
                f"Unknown escape sequence `\\{escaped}`. "
                'Use `\\"` for a quote or `\\\\` for a backslash.',
                Span(self.pos, self.pos + 2),
            )
        self.pos += 2
        return escaped

    def _operator(self) -> Token:
        start = self.pos
        char = self._peek()
        self.pos += 1

        if char in _COMPARISONS:
            # Longest match: `<=` is one token, not `<` then `=`.
            alone, with_equals = _COMPARISONS[char]
            if self._peek() == "=":
                self.pos += 1
                return self._token(with_equals, start)
            return self._token(alone, start)

        if char == "!":
            if self._peek() != "=":
                raise ParseError("Expected `=` after `!`.", Span(start, self.pos))
            self.pos += 1
            return self._token(TokenKind.NE, start)

        if char in _PUNCTUATION:
            return self._token(_PUNCTUATION[char], start)

        raise ParseError(f"Unexpected character `{char}`.", Span(start, self.pos))
