"""Compiler + engine semantics, on a tiny fixture table (no `make data` needed)."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from pitchquery.data.values import ValueIndex
from pitchquery.engine import Engine, QueryTimeout
from pitchquery.lang.ast import CmpOp, Comparison, Entity, Field, Query, StringLit
from pitchquery.lang.compiler import CompileError, compile_query
from pitchquery.lang.diagnostics import Severity
from pitchquery.lang.parser import parse
from pitchquery.lang.schema import FIELDS
from tests.events_fixture import ALVAREZ, DE_PAUL, MBAPPE, MESSI, write_events

VALUES: ValueIndex = {"team": [{"value": "Argentina", "count": 5}, {"value": "France", "count": 3}]}


@pytest.fixture(scope="module")
def parquet(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return write_events(tmp_path_factory.mktemp("events") / "events.parquet")


@pytest.fixture(scope="module")
def engine(parquet: Path) -> Iterator[Engine]:
    engine = Engine(parquet, VALUES)
    yield engine
    engine.close()


def rows(engine: Engine, source: str) -> list[tuple[Any, ...]]:
    result = engine.run(source)
    assert result.ok, result.diagnostics
    return result.rows


def count(engine: Engine, source: str) -> int:
    result = rows(engine, f"{source} | count")
    assert len(result) == 1
    value: int = result[0][0]
    return value


# --- Filtering --------------------------------------------------------------------------


def test_entities_filter_by_event_type(engine: Engine) -> None:
    assert count(engine, "events") == 8
    assert count(engine, "shots") == 4
    assert count(engine, "passes") == 2
    assert count(engine, "carries") == 1
    assert count(engine, "dribbles") == 0


def test_string_equality_is_case_insensitive(engine: Engine) -> None:
    assert count(engine, 'shots where team = "argentina"') == 2
    assert count(engine, 'events where TYPE = "SHOT"') == 4


def test_not_equal_is_the_negation_of_equal_and_includes_missing_values(engine: Engine) -> None:
    # 8 events, 3 by Messi; the "Half End" event has no player and is included.
    assert count(engine, f'events where player != "{MESSI}"') == 5


def test_comparisons_on_missing_values_are_false(engine: Engine) -> None:
    assert count(engine, "events where xg <= 0.3") == 1  # only the 0.1 shot
    assert count(engine, "events where xg > 0.3") == 3


def test_not_is_two_valued(engine: Engine) -> None:
    # Events without an xg are "not xg > 0.3": 8 - 3.
    assert count(engine, "events where not xg > 0.3") == 5


def test_and_or_precedence(engine: Engine) -> None:
    # or(and(Argentina, minute > 80), France) -> Álvarez, Messi carry, De Paul + 3 France
    assert count(engine, 'events where team = "Argentina" and minute > 80 or team = "France"') == 6
    assert (
        count(engine, 'events where team = "Argentina" and (minute > 80 or team = "France")') == 3
    )


def test_in_with_strings_is_case_insensitive(engine: Engine) -> None:
    assert count(engine, 'events where type in ("shot", "CARRY")') == 5


def test_in_with_numbers(engine: Engine) -> None:
    assert count(engine, "events where minute in (10, 85)") == 2


def test_contains_is_case_insensitive(engine: Engine) -> None:
    assert count(engine, 'events where player contains "MESSI"') == 3


def test_contains_treats_like_wildcards_literally(engine: Engine) -> None:
    assert count(engine, 'events where player contains "%"') == 0
    assert count(engine, 'events where player contains "_"') == 0


def test_between_is_inclusive(engine: Engine) -> None:
    assert count(engine, "events where minute between 81 and 85") == 4


def test_booleans(engine: Engine) -> None:
    assert count(engine, "events where under_pressure = true") == 2
    assert count(engine, "events where under_pressure != true") == 6


# --- Columns and order ------------------------------------------------------------------


def test_default_columns_are_the_schema_fields(engine: Engine) -> None:
    result = engine.run("shots | limit 1")
    assert result.columns == list(FIELDS)


def test_default_order_is_event_order(engine: Engine) -> None:
    assert rows(engine, "events | select match_id, minute") == [
        (1, 10), (1, 12), (1, 30), (1, 85), (1, 45), (2, 81), (2, 82), (2, 83),
    ]  # fmt: skip


def test_select(engine: Engine) -> None:
    result = engine.run("shots | select player, xg")
    assert result.columns == ["player", "xg"]
    assert result.rows == [(MESSI, 0.4), (MBAPPE, 0.1), (MBAPPE, 0.8), (ALVAREZ, 0.35)]


def test_select_uses_canonical_field_names(engine: Engine) -> None:
    assert engine.run("shots | select PLAYER | limit 1").columns == ["player"]


def test_sort_by_field_is_stable(engine: Engine) -> None:
    # Two Argentina shots and two France shots: ties keep event order.
    assert rows(engine, "shots | sort asc team | select team, minute") == [
        ("Argentina", 10), ("Argentina", 81), ("France", 30), ("France", 85),
    ]  # fmt: skip


def test_sort_desc_by_field(engine: Engine) -> None:
    assert rows(engine, "shots | sort desc xg | select xg") == [(0.8,), (0.4,), (0.35,), (0.1,)]


def test_missing_values_sort_last_both_ways(engine: Engine) -> None:
    ascending = rows(engine, "events | sort asc xg | select xg")
    descending = rows(engine, "events | sort desc xg | select xg")
    assert ascending == [(0.1,), (0.35,), (0.4,), (0.8,)] + [(None,)] * 4
    assert descending == [(0.8,), (0.4,), (0.35,), (0.1,)] + [(None,)] * 4


def test_sort_without_field_reverses_event_order(engine: Engine) -> None:
    assert rows(engine, "events | sort desc | limit 2 | select match_id, minute") == [
        (2, 83), (2, 82),
    ]  # fmt: skip


def test_limit(engine: Engine) -> None:
    assert len(rows(engine, "events | limit 3")) == 3
    assert rows(engine, "events | limit 0") == []


def test_limit_then_sort_sorts_the_kept_rows(engine: Engine) -> None:
    # The first 2 shots are Messi (0.4) and Mbappé (0.1); sorting happens after the limit.
    assert rows(engine, "shots | limit 2 | sort asc xg | select xg") == [(0.1,), (0.4,)]


# --- Aggregation ------------------------------------------------------------------------


def test_count(engine: Engine) -> None:
    result = engine.run("shots | count")
    assert result.columns == ["count"]
    assert result.rows == [(4,)]


def test_count_by_orders_by_count_then_value(engine: Engine) -> None:
    result = engine.run("events | count by team")
    assert result.columns == ["team", "count"]
    assert result.rows == [("Argentina", 5), ("France", 3)]


def test_count_by_then_sort_without_field_sorts_by_count(engine: Engine) -> None:
    assert rows(engine, "events | count by team | sort asc") == [("France", 3), ("Argentina", 5)]


def test_count_by_then_sort_by_the_field(engine: Engine) -> None:
    assert rows(engine, "events | count by player | sort asc player") == [
        (ALVAREZ, 1), (MBAPPE, 2), (MESSI, 3), (DE_PAUL, 1), (None, 1),
    ]  # fmt: skip


def test_top_scorer_pipeline(engine: Engine) -> None:
    # Messi and Mbappé both have 1 goal: ties go to the value, alphabetically.
    source = 'shots where outcome = "goal" | count by player | sort desc | limit 1'
    assert rows(engine, source) == [(MBAPPE, 1)]
    assert rows(engine, "shots | count by player | sort desc | limit 1") == [(MBAPPE, 2)]


def test_select_after_count_by(engine: Engine) -> None:
    result = engine.run("events | count by team | select team")
    assert result.columns == ["team"]
    assert result.rows == [("Argentina",), ("France",)]


def test_sort_without_field_after_select_drops_back_to_row_order(engine: Engine) -> None:
    assert rows(engine, "events | count by team | select team | sort desc") == [
        ("France",), ("Argentina",),
    ]  # fmt: skip


# --- Diagnostics, row cap, timeout ------------------------------------------------------


def test_errors_prevent_running(engine: Engine) -> None:
    result = engine.run("shots where xgg > 1")
    assert not result.ok
    assert result.rows == [] and result.columns == []
    assert result.diagnostics[0].message == "Unknown field `xgg`. Did you mean `xg`?"


def test_syntax_errors_prevent_running(engine: Engine) -> None:
    result = engine.run("shots where")
    assert not result.ok
    assert result.rows == []


def test_warnings_do_not_prevent_running(engine: Engine) -> None:
    result = engine.run('shots where team = "Atlantis"')
    assert result.ok
    assert result.diagnostics[0].severity is Severity.WARNING
    assert result.rows == []
    assert result.columns == list(FIELDS)


def test_row_cap_truncates(parquet: Path) -> None:
    engine = Engine(parquet, row_cap=3)
    try:
        capped = engine.run("events")
        assert len(capped.rows) == 3
        assert capped.truncated
        exact = engine.run("events | limit 3")
        assert len(exact.rows) == 3
        assert not exact.truncated
    finally:
        engine.close()


def test_elapsed_time_is_reported(engine: Engine) -> None:
    assert engine.run("shots").elapsed_ms > 0


def test_slow_queries_time_out(parquet: Path) -> None:
    engine = Engine(parquet, timeout_s=0.2)
    try:
        with pytest.raises(QueryTimeout):
            engine.execute_sql("SELECT sum(i * i) FROM range(100000000000) t(i)", ())
    finally:
        engine.close()


def test_timeout_becomes_an_error_diagnostic(
    parquet: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = Engine(parquet, timeout_s=0.2)

    def slow(sql: str, params: tuple[object, ...], max_rows: int | None = None) -> None:
        raise QueryTimeout

    monkeypatch.setattr(engine, "execute_sql", slow)
    try:
        result = engine.run("events")
        assert not result.ok
        assert result.diagnostics[0].message == "The query took longer than 0.2 s and was stopped."
    finally:
        engine.close()


# --- SQL injection ----------------------------------------------------------------------

INJECTIONS = [
    "'; DROP TABLE events; --",
    "' OR '1'='1",
    '" OR 1=1 --',
    "Messi') UNION SELECT * FROM duckdb_tables() --",
    "? OR 1=1",
]


@pytest.mark.parametrize("payload", INJECTIONS)
def test_injection_through_string_values_is_inert(engine: Engine, payload: str) -> None:
    quoted = payload.replace("\\", "\\\\").replace('"', '\\"')
    for source in [
        f'events where player = "{quoted}"',
        f'events where player != "{quoted}" | count',
        f'events where player in ("{quoted}", "x")',
        f'events where player contains "{quoted}"',
    ]:
        result = engine.run(source)
        assert result.ok, (source, result.diagnostics)
    assert count(engine, "events") == 8  # the table is intact


@pytest.mark.parametrize("payload", INJECTIONS)
def test_values_never_appear_in_the_sql(payload: str) -> None:
    quoted = payload.replace("\\", "\\\\").replace('"', '\\"')
    compiled = compile_query(parse(f'events where player = "{quoted}"'))
    assert payload not in compiled.sql
    assert payload in compiled.params


def test_unknown_fields_are_never_compiled() -> None:
    # The parser only allows [A-Za-z0-9_] in names and the compiler only emits schema
    # names, but it must also refuse anything it was not given by the analyzer.
    query = Query(Entity("events"), Comparison(Field('x" OR 1=1 --'), CmpOp.EQ, StringLit("a")))
    with pytest.raises(CompileError):
        compile_query(query)
