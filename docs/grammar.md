# PitchQuery grammar (v1)

PitchQuery is a small pipeline language for filtering and aggregating football match
events. A query names an **entity**, optionally filters it with a **`where`** expression,
then runs zero or more **stages** separated by `|`.

```
shots where xg > 0.3 and team = "Argentina" and minute >= 80
passes where player = "Lionel Messi" and outcome = "Complete" and end_x > 102
events where type in ("Shot", "Dribble") and under_pressure = true
shots where team = "France" | count by player | sort desc | limit 5
```

This document is the contract for `lexer.py` and `parser.py`. The tests in
`backend/tests/lang/` check every rule and every error message listed here.

---

## 1. Lexical structure

The lexer turns the source text into a list of tokens and always ends it with an `EOF`
token. Whitespace (spaces, tabs, newlines) separates tokens and is otherwise ignored.
Tokens do not need whitespace between them: `xg>0.3` is three tokens.

| Token        | Rule                                                        | Examples                    |
|--------------|-------------------------------------------------------------|-----------------------------|
| identifier   | `[A-Za-z_][A-Za-z0-9_]*`, not a keyword                     | `xg`, `end_x`, `shots`      |
| keyword      | an identifier whose lowercase form is in the keyword list   | `where`, `AND`, `Desc`      |
| number       | `-?[0-9]+(\.[0-9]+)?`                                       | `80`, `0.3`, `-1`, `120.0`  |
| string       | `"` … `"`, with escapes `\"` and `\\` only                  | `"Argentina"`, `"say \"hi\""` |
| operator     | `=` `!=` `<` `<=` `>` `>=`                                  |                             |
| punctuation  | `\|` `(` `)` `,`                                            |                             |

**Keywords** (case-insensitive): `where and or not in contains between true false count by
sort asc desc limit select`. Because they are reserved, no field can be named after one.

**Entities are identifiers, not keywords.** The parser checks them against the entity list.
This keeps the token set small and lets a misspelt entity produce a precise error.

**Longest match** for operators: `<=` is one token, not `<` then `=`.

### Token values

A token is `Token(kind, text, span)`.

- For every token except strings, `text` is exactly the source slice
  `source[span.start:span.end]` (so `WHERE` keeps its case).
- For **strings**, `text` is the decoded value without quotes (`"say \"hi\""` → `say "hi"`),
  while `span` covers the quotes.
- The `EOF` token has empty text and a zero-width span at the end of the input.

### Numbers

Integers parse to `int`, numbers with a `.` to `float`. There is no exponent syntax and no
leading `.` (`.5` is an error). A `-` is only valid directly before a digit.

---

## 2. Syntax (EBNF)

```ebnf
query       = entity [ "where" expr ] { "|" stage } EOF ;
entity      = identifier ;            (* one of: events shots passes dribbles carries pressures *)

expr        = or_expr ;
or_expr     = and_expr { "or" and_expr } ;
and_expr    = not_expr { "and" not_expr } ;
not_expr    = [ "not" ] primary ;
primary     = comparison | "(" expr ")" ;
comparison  = field ( cmp_op value
                    | "in" "(" value { "," value } ")"
                    | "contains" string
                    | "between" number "and" number ) ;
cmp_op      = "=" | "!=" | "<" | "<=" | ">" | ">=" ;

stage       = "count" [ "by" field ]
            | "sort" ( "asc" | "desc" ) [ field ]
            | "limit" integer
            | "select" field { "," field } ;

field       = identifier ;
value       = string | number | "true" | "false" ;
integer     = number without "." and without "-" ;
```

### Precedence and associativity

From tightest to loosest: `not`, `and`, `or`. `and` and `or` are **left-associative**.

| Input                              | Parsed as                         |
|------------------------------------|-----------------------------------|
| `a = 1 or b = 2 and c = 3`         | `a = 1 or (b = 2 and c = 3)`      |
| `not a = 1 and b = 2`              | `(not a = 1) and b = 2`           |
| `a = 1 or b = 2 or c = 3`          | `(a = 1 or b = 2) or c = 3`       |

`not` applies to a single `primary`, so `not not a = 1` is an error; write
`not (not a = 1)`.

### `between … and …`

`and` is both the boolean operator and part of `between`. There is no ambiguity in a
recursive descent parser: once `comparison` sees `between`, it consumes `number and
number` itself, before `and_expr` can see that `and`.

```
minute between 80 and 90 and team = "France"
→ (minute between 80 and 90) and (team = "France")
```

`between` is inclusive on both ends.

### Stages

| Stage                 | Meaning                                                            |
|-----------------------|--------------------------------------------------------------------|
| `count`               | Number of matching events (one row).                               |
| `count by field`      | One row per distinct value of `field`, with its count.             |
| `sort asc\|desc`      | After `count`: sort by the count. Otherwise: by event order.       |
| `sort asc\|desc field`| Sort by `field`.                                                    |
| `limit n`             | Keep the first `n` rows.                                           |
| `select f1, f2, …`    | Keep only these columns.                                           |

The parser only checks syntax. Whether a stage makes sense where it appears (for example
`select` after `count`) is checked by the analyzer (M3).

---

## 3. AST

Defined in `backend/pitchquery/lang/ast.py`. Every node has a `span`.

```
Query(entity: Entity, where: Expr | None, stages: tuple[Stage, ...])

Expr  = Comparison(field, op: CmpOp, value: Literal)
      | InList(field, values: tuple[Literal, ...])
      | Contains(field, value: StringLit)
      | Between(field, low: NumberLit, high: NumberLit)
      | Not(operand) | And(left, right) | Or(left, right)

Literal = StringLit(str) | NumberLit(int | float) | BoolLit(bool)

Stage = CountStage(by: Field | None)
      | SortStage(direction: SortDirection, field: Field | None)
      | LimitStage(count: int)
      | SelectStage(fields: tuple[Field, ...])
```

Notes:

- Entity names are stored **lowercase** (`SHOTS` → `Entity("shots")`). Field names are
  stored **as written**; the analyzer resolves them against the schema, ignoring case.
- Parentheses do not create a node. They only affect the tree shape and the span.
- **Spans are excluded from equality** (`compare=False`). Two ASTs are equal when they have
  the same structure and values, wherever they came from. The round-trip test relies on
  this, and span tests check spans explicitly.

### Spans

A span is a half-open range of character offsets `[start, end)`, 0-based. Error messages
show 1-based columns (`column = start + 1`).

| Node                     | Span covers                                                       |
|--------------------------|-------------------------------------------------------------------|
| `Entity`, `Field`, literal | its token (string literals include their quotes)                |
| `Comparison` etc.        | from the field to the end of the value / `)`                      |
| `And`, `Or`              | from the start of `left` to the end of `right`                    |
| `Not`                    | from `not` to the end of the operand                              |
| parenthesised expression | the expression's node span is widened to include the parentheses |
| stage                    | from its keyword to its last token                                |
| `Query`                  | from the entity to the last token before `EOF`                    |

---

## 4. Errors

Lexing and parsing stop at the **first** error and raise `ParseError(message, span)`.
(The analyzer in M3 collects several diagnostics; syntax errors are one at a time.)

In messages, a token is shown as it was written, in backticks: `` `where` ``,
`` `>` ``, `` `"Shot"` ``. The end of the input is shown as `end of query`. Below,
`<got>` is the offending token described that way, and `<prev>` is the token just before
it.

**The span of a parse error is the offending token's span.** At the end of the input
that is the zero-width `EOF` span.

### Lexer errors

| Situation                  | Message                                                       | Span                     |
|----------------------------|---------------------------------------------------------------|--------------------------|
| unknown character          | ``Unexpected character `@`.``                                 | the character            |
| `!` not followed by `=`    | ``Expected `=` after `!`.``                                   | the `!`                  |
| `-` not followed by digit  | ``Expected a digit after `-`.``                               | the `-`                  |
| `.` not followed by digit  | ``Expected a digit after `.`.``                               | the number so far, incl. `.` |
| string never closed        | ``Unterminated string starting at column 20.``                | opening quote → end of input |
| unknown escape             | ``Unknown escape sequence `\n`. Use `\"` for a quote or `\\` for a backslash.`` | the two characters |

### Parser errors

| Where                               | Message                                                                 |
|-------------------------------------|-------------------------------------------------------------------------|
| start, not an identifier            | ``Expected an entity (events, shots, passes, dribbles, carries, pressures), got <got>.`` |
| start, unknown identifier           | ``Unknown entity `shtos`. Did you mean `shots`?``, or without a close match ``Unknown entity `goals`. Expected one of: events, shots, passes, dribbles, carries, pressures.`` |
| after the entity                    | ``Expected `where`, `\|` or end of query, got <got>.``                  |
| start of a primary                  | ``Expected a field name or `(` after <prev>, got <got>.``               |
| after a field                       | ``Expected an operator after <prev>, got <got>.``                       |
| after `=` `!=` `<` `<=` `>` `>=`    | ``Expected a value after <prev>, got <got>.``                           |
| after `in`                          | ``Expected `(` after `in`, got <got>.``                                 |
| inside `in ( … )`, value expected   | ``Expected a value after <prev>, got <got>.``                           |
| inside `in ( … )`, after a value    | ``Expected `,` or `)`, got <got>.``                                     |
| after `contains`                    | ``Expected a string after `contains`, got <got>.``                      |
| after `between`                     | ``Expected a number after `between`, got <got>.``                       |
| after `between n`                   | ``Expected `and` to complete `between`, got <got>.``                    |
| after `between n and`               | ``Expected a number after `and`, got <got>.``                           |
| unclosed `(`                        | ``Expected `)` to close `(` at column 13, got <got>.``                  |
| after a complete `where` expression | ``Expected `and`, `or`, `\|` or end of query, got <got>.``              |
| after `\|`                          | ``Expected a stage (count, sort, limit, select) after `\|`, got <got>.``|
| after `count by`                    | ``Expected a field name after `by`, got <got>.``                        |
| after `sort`                        | ``Expected `asc` or `desc` after `sort`, got <got>.``                   |
| after `limit`                       | ``Expected a non-negative integer after `limit`, got <got>.``           |
| after `select` or `,` in `select`   | ``Expected a field name after <prev>, got <got>.``                      |
| after a complete stage              | ``Expected `\|` or end of query, got <got>.``                           |

Examples:

```
shots where minute >          Expected a value after `>`, got end of query.
shots where xg > 0.3 team     Expected `and`, `or`, `|` or end of query, got `team`.
shots where (xg > 0.3         Expected `)` to close `(` at column 13, got end of query.
shots | limit 2.5             Expected a non-negative integer after `limit`, got `2.5`.
```

### Misspelt keywords

When the offending token is an identifier close to a keyword that would be valid at that
point, the message ends with a suggestion and `ParseError.suggestions` holds it:

```
shots wher xg > 0.3           Expected `where`, `|` or end of query, got `wher`. Did you mean `where`?
shots | cont by team          Expected a stage (count, sort, limit, select) after `|`, got `cont`. Did you mean `count`?
shots where type inn ("Shot") Expected an operator after `type`, got `inn`. Did you mean `in`?
```

"Close" is defined in section 5 (*Suggestions*).

Unknown fields, type mismatches and unknown values are **not** syntax errors. They come
from the analyzer.

---

## 5. Semantic checks (analyzer)

`analyzer.check(source, values)` parses the query, then checks it against the schema
(`schema.py`) and the value index (`data/values.json`). It returns **every** problem,
in source order, as a `Diagnostic(severity, message, span, suggestions)`. A syntax error
becomes a single error diagnostic.

- **Errors** mean the query cannot run.
- **Warnings** mean it runs but probably not as intended (it will return nothing).

### Case

Keywords, entities, field names **and string values** are case-insensitive:
`Team = "FRANCE"` is the same as `team = "France"`. Accents are significant when
matching values, but ignored when suggesting them.

### Fields

| Field            | Type    | Only on                     |
|------------------|---------|-----------------------------|
| `match_id`       | number  |                             |
| `competition`, `season`, `team`, `opponent`, `player`, `position`, `type`, `play_pattern` | string | |
| `minute`, `second`, `period` | number |                   |
| `x`, `y`         | number  |                             |
| `end_x`, `end_y` | number  | `shots`, `passes`, `carries`|
| `outcome`        | string  | `shots`, `passes`, `dribbles` |
| `xg`             | number  | `shots`                     |
| `body_part`      | string  | `shots`, `passes`           |
| `under_pressure` | boolean |                             |

"Only on" comes from the data: these columns are empty for every other event type.
`events` contains all types, so every field is valid on it.

### Operators by type

| Type    | Operators                                     |
|---------|-----------------------------------------------|
| string  | `=` `!=` `in` `contains`                      |
| number  | `=` `!=` `<` `<=` `>` `>=` `in` `between`     |
| boolean | `=` `!=`                                      |

An integer field accepts any number (`minute > 80.5`).

### Messages

| Check                         | Severity | Message                                                            | Span |
|-------------------------------|----------|--------------------------------------------------------------------|------|
| unknown field                 | error    | ``Unknown field `xgg`. Did you mean `xg`?``                         | field |
| field not on this entity      | error    | ``` `xg` only exists for `shots`. ```                              | field |
| operator not valid for type   | error    | ``` `>` does not apply to `team`, which is a string. Use one of: `=`, `!=`, `in`, `contains`. ``` | predicate |
| value of the wrong type       | error    | ``` `xg` is a number; expected a number, got a string. ```         | value |
| field gone after a stage      | error    | ``` `xg` is not available after `count by player`. Available: `player`. ``` | field |
| unknown string value          | warning  | ``No team `Argentna` in the data. Did you mean `Argentina`?``      | value |
| empty `between` range         | warning  | ``Empty range: the lower bound 90 is greater than the upper bound 80.`` | predicate |

Notes:

- An unknown field stops the checks of its predicate, so `xgg > "high"` gives one error,
  not two. A field on the wrong entity still has its operator and values checked.
- Values are checked for `=`, `!=` and `in`, not for `contains` (its argument is part of a
  value). Fields missing from the value index are not checked.
- After `count`, only the `count by` field remains; after `select`, only the selected
  fields. `count` itself is a keyword and cannot be referenced.

### Suggestions

`suggest.py`. A candidate is suggested if it, **or one of its words**, is within
`max(1, len(word) // 3)` edits of the input, using Damerau–Levenshtein distance (optimal
string alignment): insertions, deletions, substitutions and swaps of adjacent characters
each cost 1, so `shtos` → `shots` is one edit. Case and accents are ignored.

Ranking is by distance, then by candidate order: values are passed most frequent first,
so the common answer wins ties. If nothing is close enough, candidates containing the
input are suggested instead (`Lewandow` → `Robert Lewandowski`).

---

## 6. Execution (compiler and engine)

`compiler.py` turns an analyzed query into one DuckDB SQL statement; `engine.py` runs it
on an in-memory copy of `events.parquet`.

### Safety

- **Values are always parameters** (`$1`, `$2`, …), never part of the SQL text. A value
  like `"'; DROP TABLE events; --"` is just a string that matches nothing.
- **Column names come from the schema**, not from the query text. Field names are only
  used to look fields up; anything unknown raises `CompileError`.
- `contains` uses DuckDB's `contains()`, not `LIKE`, so `%` and `_` are literal.
- Each query runs with a **timeout** (5 s) and returns at most **5,000 rows**; the result
  says whether rows were cut (`truncated`).

### Semantics

| Rule | Example |
|------|---------|
| String comparisons (`=`, `!=`, `in`, `contains`) ignore case. | `team = "france"` matches `France` |
| A predicate on a missing value is **false**. | `events where xg <= 0.3` only returns shots |
| `!=` is exactly `not =`, so it **includes** missing values. | `player != "Lionel Messi"` includes events with no player |
| `not` negates a predicate, missing values included. | `events where not xg > 0.3` includes every non-shot |
| `between a and b` is inclusive. | `minute between 80 and 90` includes 80 and 90 |

### Row order and stages

Without stages, rows come in **event order** (match, then event index) with every schema
field as a column.

| Stage | Result |
|-------|--------|
| `count` | one row, column `count` |
| `count by f` | columns `f`, `count`; most frequent first, ties by `f` ascending |
| `sort asc\|desc f` | sorted by `f`; missing values last in both directions; stable |
| `sort asc\|desc` | by `count` if the rows have one, otherwise by the current order (`sort desc` = latest events first) |
| `limit n` | the first `n` rows in the current order |
| `select f, …` | only these columns, in this order (duplicates dropped) |

Stages apply left to right: `limit 2 | sort asc xg` sorts the two kept rows, while
`sort asc xg | limit 2` keeps the two lowest.

Implementation note: every stage is a subquery around the previous one. SQL does not
promise that a subquery's `ORDER BY` survives the outer query, so the compiler carries the
order in a hidden `_ord` column (`row_number()`), and only the final query sorts by it.

### Performance

See [performance.md](performance.md) (`make bench`). Every example query runs end to end
in under 10 ms on the full World Cup dataset.
