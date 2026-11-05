"""Golden queries on the real World Cup 2022 data (M4 "done when").

Expected values are either football facts or counts computed with independent,
hand-written SQL over the Parquet file, never with the compiler under test.
"""

import os
from collections.abc import Iterator

import duckdb
import pytest

from pitchquery.data.paths import DataPaths
from pitchquery.data.values import load_value_index
from pitchquery.engine import Engine

PATHS = DataPaths.default()

if not PATHS.events_parquet.exists():
    if os.environ.get("PITCHQUERY_REQUIRE_DATA") == "1":
        raise RuntimeError(f"{PATHS.events_parquet} is missing; run `make data`")
    pytest.skip("dataset not built; run `make data`", allow_module_level=True)


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    engine = Engine(PATHS.events_parquet, load_value_index(PATHS.values_json))
    yield engine
    engine.close()


def run(engine: Engine, source: str) -> list[tuple[object, ...]]:
    result = engine.run(source)
    assert result.ok, result.diagnostics
    return result.rows


def independent_rows(sql: str) -> list[tuple[object, ...]]:
    """Run hand-written SQL against the Parquet file, exposed as the view `e`."""
    con = duckdb.connect()
    try:
        con.execute(f"CREATE VIEW e AS SELECT * FROM read_parquet('{PATHS.events_parquet}')")
        return con.execute(sql).fetchall()
    finally:
        con.close()


def independent(sql: str) -> object:
    return independent_rows(sql)[0][0]


# --- Football facts ---------------------------------------------------------------------

GOALS = 'shots where outcome = "Goal" and period < 5'  # period 5 is the penalty shootout


@pytest.mark.parametrize(
    ("player", "goals"),
    [("Kylian Mbappé", 8), ("Lionel Messi", 7), ("Julián Álvarez", 4), ("Olivier Giroud", 4)],
)
def test_top_scorers(engine: Engine, player: str, goals: int) -> None:
    assert run(engine, f'{GOALS} and player = "{player}" | count') == [(goals,)]


def test_golden_boot_pipeline(engine: Engine) -> None:
    assert run(engine, f"{GOALS} | count by player | sort desc | limit 2") == [
        ("Kylian Mbappé", 8),
        ("Lionel Messi", 7),
    ]


def test_the_final_was_3_3(engine: Engine) -> None:
    final = 3869685
    assert sorted(run(engine, f"{GOALS} and match_id = {final} | count by team")) == [
        ("Argentina", 3),
        ("France", 3),
    ]


def test_hat_trick_in_the_final(engine: Engine) -> None:
    source = f'{GOALS} and match_id = 3869685 and player = "Mbappe" | count'
    # "Mbappe" without the accent is not a known value: a warning, and no rows match.
    result = engine.run(source)
    assert result.ok
    assert result.diagnostics[0].suggestions[0] == "Kylian Mbappé"
    assert run(engine, f'{GOALS} and match_id = 3869685 and player contains "mbapp" | count') == [
        (3,)
    ]


# --- Engine vs. hand-written SQL --------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "sql"),
    [
        ("shots", "SELECT count(*) FROM e WHERE type = 'Shot'"),
        ("events where under_pressure = true", "SELECT count(*) FROM e WHERE under_pressure"),
        (
            'passes where player = "Lionel Messi" and outcome = "complete" and end_x > 102',
            "SELECT count(*) FROM e WHERE type = 'Pass' AND player = 'Lionel Messi'"
            " AND outcome = 'Complete' AND end_x > 102",
        ),
        (
            'events where type in ("Shot", "Dribble") and under_pressure = true',
            "SELECT count(*) FROM e WHERE type IN ('Shot', 'Dribble') AND under_pressure",
        ),
        (
            'shots where xg > 0.3 and team = "Argentina" and minute >= 80',
            "SELECT count(*) FROM e WHERE type = 'Shot' AND xg > 0.3"
            " AND team = 'Argentina' AND minute >= 80",
        ),
        (
            'carries where end_x between 102 and 120 and not team = "France"',
            "SELECT count(*) FROM e WHERE type = 'Carry' AND end_x BETWEEN 102 AND 120"
            " AND team IS DISTINCT FROM 'France'",
        ),
        (
            'events where player != "Lionel Messi"',
            "SELECT count(*) FROM e WHERE player IS DISTINCT FROM 'Lionel Messi'",
        ),
    ],
)
def test_counts_match_hand_written_sql(engine: Engine, source: str, sql: str) -> None:
    assert run(engine, f"{source} | count") == [(independent(sql),)]


def test_count_by_matches_hand_written_sql(engine: Engine) -> None:
    got = run(engine, 'shots where team = "France" | count by player | sort desc | limit 5')
    expected = independent_rows(
        "SELECT player, count(*) AS n FROM e WHERE type = 'Shot' AND team = 'France'"
        " GROUP BY player ORDER BY n DESC, player LIMIT 5"
    )
    assert got == expected
