"""Autocompletion: what can be typed at a cursor position.

Approach: parser-driven, not a separate state machine. The text before the cursor (minus
the word being typed) is parsed as a query prefix; the parser records every token kind
it checked for when it reached the end (see parser.parse_prefix). That set *is* what the
grammar allows next, so completion can never disagree with the parser. The parser's
context (entity, current field, stages so far) then narrows identifiers and values:

- an identifier at the start is an entity; elsewhere it is a field, limited to fields
  the entity has, or to the columns left by `count` / `select`;
- after a field, only operators valid for its type;
- in a value position, the field's known values (from the value index), ranked by
  prefix match, then word-prefix match, then substring match, then frequency.

Incomplete input is the normal case, and costs nothing extra: the parser stops at the
end of the prefix whether the query is complete or not.
"""

from dataclasses import dataclass
from enum import Enum

from pitchquery.data.values import ValueCount, ValueIndex
from pitchquery.lang.analyzer import columns_after
from pitchquery.lang.ast import ENTITIES
from pitchquery.lang.errors import ParseError
from pitchquery.lang.parser import PrefixState, parse_prefix
from pitchquery.lang.schema import ENTITY_EVENT_TYPES, FIELDS, FieldType, lookup
from pitchquery.lang.span import Span
from pitchquery.lang.suggest import normalize
from pitchquery.lang.tokens import TokenKind, quote_string


class SuggestionKind(Enum):
    ENTITY = "entity"
    FIELD = "field"
    OPERATOR = "operator"
    VALUE = "value"
    KEYWORD = "keyword"


@dataclass(frozen=True, slots=True)
class Suggestion:
    label: str  # the text to insert
    kind: SuggestionKind
    span: Span  # the source range the label replaces
    detail: str | None = None  # extra info for the UI, e.g. a field's type


K = TokenKind

_OPERATORS: list[tuple[TokenKind, str]] = [
    (K.EQ, "="),
    (K.NE, "!="),
    (K.LT, "<"),
    (K.LE, "<="),
    (K.GT, ">"),
    (K.GE, ">="),
    (K.IN, "in"),
    (K.CONTAINS, "contains"),
    (K.BETWEEN, "between"),
]
_KEYWORDS: list[tuple[TokenKind, str]] = [
    (K.WHERE, "where"),
    (K.NOT, "not"),
    (K.AND, "and"),
    (K.OR, "or"),
    (K.BY, "by"),
    (K.ASC, "asc"),
    (K.DESC, "desc"),
    (K.COUNT, "count"),
    (K.SORT, "sort"),
    (K.LIMIT, "limit"),
    (K.SELECT, "select"),
]
_PUNCTUATION: list[tuple[TokenKind, str]] = [
    (K.PIPE, "|"),
    (K.COMMA, ","),
    (K.RPAREN, ")"),
    (K.LPAREN, "("),
]


def _is_word_char(char: str) -> bool:
    return char == "_" or (char.isascii() and char.isalnum())


def complete(
    source: str, cursor: int, values: ValueIndex | None = None, limit: int = 50
) -> list[Suggestion]:
    """Suggestions for the cursor position (0 <= cursor <= len(source)), best first."""
    if not 0 <= cursor <= len(source):
        raise ValueError(f"cursor {cursor} outside 0..{len(source)}")

    prefix = source[:cursor]
    string = _open_string(prefix)
    if string is not None:
        # Inside a string: only values, replacing the whole string literal.
        start, partial = string
        text_before, span = prefix[:start], Span(start, _string_end(source, cursor))
    else:
        start = cursor
        while start > 0 and _is_word_char(source[start - 1]):
            start -= 1
        end = cursor
        while end < len(source) and _is_word_char(source[end]):
            end += 1
        partial, text_before, span = source[start:cursor], source[:start], Span(start, end)

    try:
        state = parse_prefix(text_before)
    except ParseError:
        return []  # the text before the cursor does not even tokenize
    if state is None:
        return []

    suggestions = _Builder(state, partial, span, values, inside_string=string is not None)
    return suggestions.build()[:limit]


def _open_string(prefix: str) -> tuple[int, str] | None:
    """If `prefix` ends inside a string literal: (opening quote offset, decoded text)."""
    start: int | None = None
    i = 0
    while i < len(prefix):
        char = prefix[i]
        if start is None:
            if char == '"':
                start = i
        elif char == "\\":
            i += 1  # skip the escaped character
        elif char == '"':
            start = None
        i += 1
    if start is None:
        return None
    body = prefix[start + 1 :]
    return start, body.replace('\\"', '"').replace("\\\\", "\\")


def _string_end(source: str, cursor: int) -> int:
    """End of the string literal the cursor is in: after its closing quote, if any."""
    i = cursor
    while i < len(source):
        if source[i] == "\\":
            i += 2
            continue
        if source[i] == '"':
            return i + 1
        i += 1
    return cursor


class _Builder:
    def __init__(
        self,
        state: PrefixState,
        partial: str,
        span: Span,
        values: ValueIndex | None,
        *,
        inside_string: bool,
    ) -> None:
        self.state = state
        self.expected = state.expected
        self.partial = partial
        self.span = span
        self.values = values or {}
        self.inside_string = inside_string
        self.out: list[Suggestion] = []

    def build(self) -> list[Suggestion]:
        if not self.inside_string:
            self._identifiers()
        self._values()
        if not self.inside_string:
            self._operators()
            self._fixed(_KEYWORDS, SuggestionKind.KEYWORD)
            self._punctuation()
        return self.out

    def _add(self, label: str, kind: SuggestionKind, detail: str | None = None) -> None:
        self.out.append(Suggestion(label, kind, self.span, detail))

    def _matches(self, label: str) -> bool:
        return label.lower().startswith(self.partial.lower())

    # --- Entities and fields ------------------------------------------------------------

    def _identifiers(self) -> None:
        if K.IDENT not in self.expected:
            return
        if self.state.entity is None:
            for entity in ENTITIES:
                if self._matches(entity):
                    event_type = ENTITY_EVENT_TYPES[entity]
                    detail = f"{event_type} events" if event_type else "All events"
                    self._add(entity, SuggestionKind.ENTITY, detail)
            return
        for name in self._available_fields(self.state.entity):
            spec = FIELDS[name]
            if self._matches(name):
                self._add(name, SuggestionKind.FIELD, f"{spec.type.label} · {spec.description}")

    def _available_fields(self, entity: str) -> list[str]:
        columns: list[str] | None = None
        for stage in self.state.stages:
            columns = columns_after(stage, columns)
        if columns is not None:
            return [c for c in columns if c in FIELDS]
        return [name for name, spec in FIELDS.items() if spec.applies_to(entity)]

    # --- Operators ----------------------------------------------------------------------

    def _operators(self) -> None:
        spec = lookup(self.state.field) if self.state.field else None
        allowed = spec.type.operators if spec else None  # unknown field: offer them all
        for kind, label in _OPERATORS:
            valid_here = kind in self.expected and (allowed is None or label in allowed)
            if valid_here and self._matches(label):
                self._add(label, SuggestionKind.OPERATOR)

    # --- Values -------------------------------------------------------------------------

    def _values(self) -> None:
        # A value position accepts every literal kind. `contains` only takes a string,
        # and is meant for partial text, so it gets no value suggestions.
        if not {K.STRING, K.TRUE} <= self.expected or self.state.field is None:
            return
        spec = lookup(self.state.field)
        if spec is None:
            return
        if spec.type is FieldType.BOOL:
            for label in ("true", "false"):
                if self._matches(label):
                    self._add(label, SuggestionKind.VALUE)
        elif spec.type is FieldType.STRING:
            for entry in _rank_values(self.partial, self.values.get(spec.name, [])):
                detail = f"{entry['count']:,} events"
                self._add(quote_string(entry["value"]), SuggestionKind.VALUE, detail)

    # --- Keywords and punctuation -------------------------------------------------------

    def _fixed(self, table: list[tuple[TokenKind, str]], kind: SuggestionKind) -> None:
        for token_kind, label in table:
            if token_kind in self.expected and self._matches(label):
                self._add(label, kind)

    def _punctuation(self) -> None:
        for token_kind, label in _PUNCTUATION:
            # `(` is only worth suggesting where it is the only option (after `in`); where
            # a field could go, the fields are the useful suggestions.
            if token_kind is K.LPAREN and K.IDENT in self.expected:
                continue
            if token_kind in self.expected and self._matches(label):
                self._add(label, SuggestionKind.OPERATOR, _PUNCTUATION_DETAIL.get(label))


_PUNCTUATION_DETAIL = {"|": "then count, sort, limit or select"}


def _rank_values(partial: str, entries: list[ValueCount]) -> list[ValueCount]:
    """Values matching `partial`: whole-value prefix, then a word prefix, then substring.

    Entries arrive most frequent first and Python's sort is stable, so frequency breaks
    ties within each group. Case and accents are ignored.
    """
    needle = normalize(partial)
    if not needle:
        return list(entries)
    ranked: list[tuple[int, ValueCount]] = []
    for entry in entries:
        value = normalize(entry["value"])
        if value.startswith(needle):
            ranked.append((0, entry))
        elif any(word.startswith(needle) for word in value.split()):
            ranked.append((1, entry))
        elif needle in value:
            ranked.append((2, entry))
    ranked.sort(key=lambda pair: pair[0])
    return [entry for _, entry in ranked]
