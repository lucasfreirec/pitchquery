"""Recursive descent parser: query source text -> AST. See docs/grammar.md, sections 2-4.

Each grammar rule is one method, and the call structure mirrors the precedence levels:

    query -> or_expr -> and_expr -> not_expr -> primary -> predicate

A looser operator calls the next tighter one for its operands, so tighter operators end
up deeper in the tree. `and` and `or` are parsed with a loop that folds to the left,
which makes them left-associative (`a or b or c` is `(a or b) or c`).

The parser stops at the first error and raises ParseError with the span of the
offending token.
"""

from dataclasses import replace

from pitchquery.lang.ast import (
    ENTITIES,
    And,
    Between,
    BoolLit,
    CmpOp,
    Comparison,
    Contains,
    CountStage,
    Entity,
    Expr,
    Field,
    InList,
    LimitStage,
    Literal,
    Not,
    NumberLit,
    Or,
    Query,
    SelectStage,
    SortDirection,
    SortStage,
    Stage,
    StringLit,
)
from pitchquery.lang.errors import ParseError
from pitchquery.lang.lexer import tokenize
from pitchquery.lang.suggest import did_you_mean, suggest
from pitchquery.lang.tokens import Token, TokenKind, describe

_COMPARISON_OPS: dict[TokenKind, CmpOp] = {
    TokenKind.EQ: CmpOp.EQ,
    TokenKind.NE: CmpOp.NE,
    TokenKind.LT: CmpOp.LT,
    TokenKind.LE: CmpOp.LE,
    TokenKind.GT: CmpOp.GT,
    TokenKind.GE: CmpOp.GE,
}

_ENTITY_LIST = ", ".join(ENTITIES)


def parse(source: str) -> Query:
    """Parse a whole query.

    Raises:
        ParseError: on the first lexing or syntax error, with the offending span.
    """
    return _Parser(tokenize(source)).query()


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens  # always ends with EOF, so peeking never runs off the end
        self.pos = 0

    # --- Token helpers ------------------------------------------------------------------

    def _peek(self) -> Token:
        return self.tokens[self.pos]

    def _previous(self) -> Token:
        return self.tokens[self.pos - 1]

    def _check(self, *kinds: TokenKind) -> bool:
        return self._peek().kind in kinds

    def _advance(self) -> Token:
        token = self.tokens[self.pos]
        if token.kind is not TokenKind.EOF:
            self.pos += 1
        return token

    def _error(self, expected: str, keywords: tuple[str, ...] = ()) -> ParseError:
        """`Expected <expected>, got <current token>.`, pointing at the current token.

        If the current token is an identifier close to one of the `keywords` that would
        be valid here (`wher` for `where`), the error suggests it.
        """
        token = self._peek()
        message = f"Expected {expected}, got {describe(token)}."
        suggestions: list[str] = []
        if keywords and token.kind is TokenKind.IDENT:
            suggestions = suggest(token.text, keywords)
            message += did_you_mean(suggestions)
        return ParseError(message, token.span, tuple(suggestions))

    def _after_previous(self) -> str:
        """`after `>``: names the last consumed token, for context in error messages."""
        return f"after {describe(self._previous())}"

    # --- query = entity [ "where" expr ] { "|" stage } EOF ------------------------------

    def query(self) -> Query:
        entity = self._entity()

        where: Expr | None = None
        if self._check(TokenKind.WHERE):
            self._advance()
            where = self._or_expr()
            if not self._check(TokenKind.PIPE, TokenKind.EOF):
                raise self._error("`and`, `or`, `|` or end of query", ("and", "or"))
        elif not self._check(TokenKind.PIPE, TokenKind.EOF):
            raise self._error("`where`, `|` or end of query", ("where",))

        stages: list[Stage] = []
        while self._check(TokenKind.PIPE):
            self._advance()
            stage = self._stage()
            stages.append(stage)
            if not self._check(TokenKind.PIPE, TokenKind.EOF):
                # `count` is the only stage with an optional keyword after it.
                keywords = ("by",) if isinstance(stage, CountStage) and stage.by is None else ()
                raise self._error("`|` or end of query", keywords)

        # From the entity to the last real token, so surrounding whitespace is excluded.
        span = entity.span.to(self._previous().span)
        return Query(entity, where, tuple(stages), span=span)

    def _entity(self) -> Entity:
        token = self._peek()
        if token.kind is not TokenKind.IDENT:
            raise self._error(f"an entity ({_ENTITY_LIST})")
        name = token.text.lower()
        if name not in ENTITIES:
            suggestions = tuple(suggest(token.text, ENTITIES))
            hint = did_you_mean(suggestions) or f" Expected one of: {_ENTITY_LIST}."
            raise ParseError(f"Unknown entity `{token.text}`.{hint}", token.span, suggestions)
        self._advance()
        return Entity(name, span=token.span)

    # --- Boolean expressions, loosest to tightest ----------------------------------------

    def _or_expr(self) -> Expr:
        # or_expr = and_expr { "or" and_expr }
        left = self._and_expr()
        while self._check(TokenKind.OR):
            self._advance()
            right = self._and_expr()
            left = Or(left, right, span=left.span.to(right.span))
        return left

    def _and_expr(self) -> Expr:
        # and_expr = not_expr { "and" not_expr }
        left = self._not_expr()
        while self._check(TokenKind.AND):
            self._advance()
            right = self._not_expr()
            left = And(left, right, span=left.span.to(right.span))
        return left

    def _not_expr(self) -> Expr:
        # not_expr = [ "not" ] primary
        if self._check(TokenKind.NOT):
            keyword = self._advance()
            operand = self._primary()
            return Not(operand, span=keyword.span.to(operand.span))
        return self._primary()

    def _primary(self) -> Expr:
        # primary = predicate | "(" expr ")"
        if self._check(TokenKind.LPAREN):
            return self._parenthesised()
        if self._check(TokenKind.IDENT):
            return self._predicate()
        raise self._error(f"a field name or `(` {self._after_previous()}")

    def _parenthesised(self) -> Expr:
        open_paren = self._advance()
        inner = self._or_expr()
        if not self._check(TokenKind.RPAREN):
            raise self._error(f"`)` to close `(` at column {open_paren.span.column}")
        close_paren = self._advance()
        # Parentheses create no node; they only widen the inner node's span.
        return replace(inner, span=open_paren.span.to(close_paren.span))

    # --- Predicates: field followed by an operator ---------------------------------------

    def _predicate(self) -> Expr:
        field = self._field()
        operator = self._peek()

        if operator.kind in _COMPARISON_OPS:
            self._advance()
            value = self._value()
            op = _COMPARISON_OPS[operator.kind]
            return Comparison(field, op, value, span=field.span.to(value.span))

        if operator.kind is TokenKind.IN:
            self._advance()
            return self._in_list(field)

        if operator.kind is TokenKind.CONTAINS:
            self._advance()
            if not self._check(TokenKind.STRING):
                raise self._error("a string after `contains`")
            token = self._advance()
            value = StringLit(token.text, span=token.span)
            return Contains(field, value, span=field.span.to(token.span))

        if operator.kind is TokenKind.BETWEEN:
            self._advance()
            low = self._number("a number after `between`")
            # This `and` belongs to `between`. Because we consume it here, _and_expr never
            # sees it, which is what resolves the ambiguity with the boolean `and`.
            if not self._check(TokenKind.AND):
                raise self._error("`and` to complete `between`", ("and",))
            self._advance()
            high = self._number("a number after `and`")
            return Between(field, low, high, span=field.span.to(high.span))

        raise self._error(f"an operator {self._after_previous()}", ("in", "contains", "between"))

    def _in_list(self, field: Field) -> InList:
        # "in" "(" value { "," value } ")"
        if not self._check(TokenKind.LPAREN):
            raise self._error("`(` after `in`")
        self._advance()
        values = [self._value()]
        while self._check(TokenKind.COMMA):
            self._advance()
            values.append(self._value())
        if not self._check(TokenKind.RPAREN):
            raise self._error("`,` or `)`")
        close_paren = self._advance()
        return InList(field, tuple(values), span=field.span.to(close_paren.span))

    # --- Leaves -------------------------------------------------------------------------

    def _field(self) -> Field:
        if not self._check(TokenKind.IDENT):
            raise self._error(f"a field name {self._after_previous()}")
        token = self._advance()
        return Field(token.text, span=token.span)

    def _value(self) -> Literal:
        # value = string | number | "true" | "false"
        token = self._peek()
        if token.kind is TokenKind.STRING:
            self._advance()
            return StringLit(token.text, span=token.span)
        if token.kind is TokenKind.NUMBER:
            self._advance()
            return NumberLit(_number_value(token.text), span=token.span)
        if token.kind in (TokenKind.TRUE, TokenKind.FALSE):
            self._advance()
            return BoolLit(token.kind is TokenKind.TRUE, span=token.span)
        raise self._error(f"a value {self._after_previous()}")

    def _number(self, expected: str) -> NumberLit:
        if not self._check(TokenKind.NUMBER):
            raise self._error(expected)
        token = self._advance()
        return NumberLit(_number_value(token.text), span=token.span)

    # --- Stages -------------------------------------------------------------------------

    def _stage(self) -> Stage:
        keyword = self._peek()
        if keyword.kind is TokenKind.COUNT:
            return self._count_stage()
        if keyword.kind is TokenKind.SORT:
            return self._sort_stage()
        if keyword.kind is TokenKind.LIMIT:
            return self._limit_stage()
        if keyword.kind is TokenKind.SELECT:
            return self._select_stage()
        raise self._error(
            "a stage (count, sort, limit, select) after `|`", ("count", "sort", "limit", "select")
        )

    def _count_stage(self) -> CountStage:
        # "count" [ "by" field ]
        keyword = self._advance()
        by: Field | None = None
        if self._check(TokenKind.BY):
            self._advance()
            by = self._field()
        return CountStage(by, span=keyword.span.to(self._previous().span))

    def _sort_stage(self) -> SortStage:
        # "sort" ( "asc" | "desc" ) [ field ]
        keyword = self._advance()
        if not self._check(TokenKind.ASC, TokenKind.DESC):
            raise self._error("`asc` or `desc` after `sort`", ("asc", "desc"))
        direction_token = self._advance()
        direction = (
            SortDirection.ASC if direction_token.kind is TokenKind.ASC else SortDirection.DESC
        )
        field = self._field() if self._check(TokenKind.IDENT) else None
        return SortStage(direction, field, span=keyword.span.to(self._previous().span))

    def _limit_stage(self) -> LimitStage:
        # "limit" integer, where integer is a NUMBER with no sign and no decimal point
        keyword = self._advance()
        token = self._peek()
        if token.kind is not TokenKind.NUMBER or not token.text.isdigit():
            raise self._error("a non-negative integer after `limit`")
        self._advance()
        return LimitStage(int(token.text), span=keyword.span.to(token.span))

    def _select_stage(self) -> SelectStage:
        # "select" field { "," field }
        keyword = self._advance()
        fields = [self._field()]
        while self._check(TokenKind.COMMA):
            self._advance()
            fields.append(self._field())
        return SelectStage(tuple(fields), span=keyword.span.to(self._previous().span))


def _number_value(text: str) -> int | float:
    """`80` -> 80 (int), `0.3` -> 0.3 (float). The lexer guarantees the text is valid."""
    return float(text) if "." in text else int(text)
