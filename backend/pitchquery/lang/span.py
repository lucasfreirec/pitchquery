from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Span:
    """A half-open range of character offsets `[start, end)` in the query source."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if not 0 <= self.start <= self.end:
            raise ValueError(f"invalid span [{self.start}, {self.end})")

    @property
    def column(self) -> int:
        """1-based column of the start, as shown to users. Queries are a single line."""
        return self.start + 1

    def to(self, other: "Span") -> "Span":
        """The span from the start of this one to the end of `other`."""
        return Span(self.start, other.end)


# Placeholder for nodes built by hand (tests, generators). Spans never affect equality.
NO_SPAN = Span(0, 0)
