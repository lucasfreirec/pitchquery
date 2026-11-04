from pitchquery.lang.span import Span


class ParseError(Exception):
    """A lexing or parsing error: what went wrong and where.

    `suggestions` is empty for now; the analyzer (M3) adds "did you mean" candidates.
    """

    def __init__(self, message: str, span: Span, suggestions: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.message = message
        self.span = span
        self.suggestions = suggestions

    def __repr__(self) -> str:
        return f"ParseError({self.message!r}, {self.span!r})"
