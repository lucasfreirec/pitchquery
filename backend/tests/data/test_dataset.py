"""Checks on the real built dataset (`make data`).

Skipped when the data has not been built, unless PITCHQUERY_REQUIRE_DATA=1 (set in CI),
in which case a missing dataset is a failure.
"""

import os
from collections.abc import Iterator
from typing import Any

import duckdb
import pytest

from pitchquery.data.paths import DataPaths
from pitchquery.data.values import load_value_index

PATHS = DataPaths.default()
WORLD_CUP_2022_FINAL = 3869685

if not PATHS.events_parquet.exists():
    if os.environ.get("PITCHQUERY_REQUIRE_DATA") == "1":
        raise RuntimeError(f"{PATHS.events_parquet} is missing; run `make data`")
    pytest.skip("dataset not built; run `make data`", allow_module_level=True)


@pytest.fixture(scope="module")
def con() -> Iterator[duckdb.DuckDBPyConnection]:
    connection = duckdb.connect()
    connection.execute(
        f"CREATE VIEW events AS SELECT * FROM read_parquet('{PATHS.events_parquet}')"
    )
    yield connection
    connection.close()


def scalar(con: duckdb.DuckDBPyConnection, sql: str) -> Any:
    row = con.execute(sql).fetchone()
    assert row is not None
    return row[0]


EXPECTED_COLUMNS = {
    "id": "VARCHAR",
    "match_id": "INTEGER",
    "event_index": "INTEGER",
    "competition": "VARCHAR",
    "season": "VARCHAR",
    "team": "VARCHAR",
    "opponent": "VARCHAR",
    "player": "VARCHAR",
    "player_id": "INTEGER",
    "position": "VARCHAR",
    "type": "VARCHAR",
    "minute": "INTEGER",
    "second": "INTEGER",
    "period": "INTEGER",
    "x": "DOUBLE",
    "y": "DOUBLE",
    "end_x": "DOUBLE",
    "end_y": "DOUBLE",
    "outcome": "VARCHAR",
    "xg": "DOUBLE",
    "body_part": "VARCHAR",
    "under_pressure": "BOOLEAN",
    "play_pattern": "VARCHAR",
}


def test_column_types(con: duckdb.DuckDBPyConnection) -> None:
    rows = con.execute("DESCRIBE events").fetchall()
    assert {name: col_type for name, col_type, *_ in rows} == EXPECTED_COLUMNS


def test_all_64_matches_present(con: duckdb.DuckDBPyConnection) -> None:
    assert scalar(con, "SELECT count(DISTINCT match_id) FROM events") == 64


def test_event_ids_are_unique(con: duckdb.DuckDBPyConnection) -> None:
    assert scalar(con, "SELECT count(*) - count(DISTINCT id) FROM events") == 0


def test_final_has_argentina_and_france(con: duckdb.DuckDBPyConnection) -> None:
    rows = con.execute(
        f"SELECT DISTINCT team, opponent FROM events WHERE match_id = {WORLD_CUP_2022_FINAL}"
    ).fetchall()
    assert set(rows) == {("Argentina", "France"), ("France", "Argentina")}


def test_every_shot_has_an_xg(con: duckdb.DuckDBPyConnection) -> None:
    assert scalar(con, "SELECT count(*) FROM events WHERE type = 'Shot'") > 1000
    assert scalar(con, "SELECT count(*) FROM events WHERE type = 'Shot' AND xg IS NULL") == 0
    assert scalar(con, "SELECT count(*) FROM events WHERE xg < 0 OR xg > 1") == 0


def test_xg_only_on_shots(con: duckdb.DuckDBPyConnection) -> None:
    assert scalar(con, "SELECT count(*) FROM events WHERE type != 'Shot' AND xg IS NOT NULL") == 0


def test_every_pass_has_an_outcome(con: duckdb.DuckDBPyConnection) -> None:
    assert scalar(con, "SELECT count(*) FROM events WHERE type = 'Pass' AND outcome IS NULL") == 0


def test_coordinates_on_the_pitch(con: duckdb.DuckDBPyConnection) -> None:
    sql = """
        SELECT count(*) FROM events
        WHERE x NOT BETWEEN 0 AND 120 OR y NOT BETWEEN 0 AND 80
           OR end_x NOT BETWEEN 0 AND 120 OR end_y NOT BETWEEN 0 AND 80
    """
    assert scalar(con, sql) == 0


def test_messi_scored_twice_in_the_final_before_shootout(
    con: duckdb.DuckDBPyConnection,
) -> None:
    sql = f"""
        SELECT count(*) FROM events
        WHERE match_id = {WORLD_CUP_2022_FINAL} AND player = 'Lionel Messi'
          AND type = 'Shot' AND outcome = 'Goal' AND period < 5
    """
    assert scalar(con, sql) == 2


def test_value_index() -> None:
    index = load_value_index(PATHS.values_json)
    teams = {entry["value"] for entry in index["team"]}
    assert len(teams) == 32
    assert "Argentina" in teams
    assert "Lionel Messi" in {entry["value"] for entry in index["player"]}
    counts = [entry["count"] for entry in index["player"]]
    assert counts == sorted(counts, reverse=True)
