from dataclasses import dataclass
from enum import Enum

from pitchquery.lang.span import Span


class Severity(Enum):
    ERROR = "error"  # the query cannot run
    WARNING = "warning"  # the query runs, but probably not as intended


@dataclass(frozen=True, slots=True)
class Diagnostic:
    severity: Severity
    message: str
    span: Span
    suggestions: tuple[str, ...] = ()
