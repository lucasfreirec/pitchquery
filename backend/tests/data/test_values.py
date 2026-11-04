"""Unit tests for the value index, built from a tiny in-memory Parquet file."""

from pathlib import Path

import duckdb

from pitchquery.data.values import STRING_FIELDS, build_value_index, load_value_index


def write_parquet(path: Path) -> None:
    con = duckdb.connect()
    columns = ", ".join(f"NULL::VARCHAR AS {field}" for field in STRING_FIELDS)
    con.execute(f"CREATE TABLE events AS SELECT {columns} FROM range(0)")
    con.execute(
        "INSERT INTO events (team, player) VALUES "
        "('France', 'Kylian Mbappé'), ('France', 'Kylian Mbappé'), "
        "('Argentina', 'Lionel Messi'), ('France', NULL)"
    )
    con.execute(f"COPY events TO '{path}' (FORMAT parquet)")
    con.close()


def test_build_and_load_round_trip(tmp_path: Path) -> None:
    parquet = tmp_path / "events.parquet"
    out = tmp_path / "values.json"
    write_parquet(parquet)

    build_value_index(parquet, out)
    index = load_value_index(out)

    assert set(index) == set(STRING_FIELDS)
    assert index["team"] == [
        {"value": "France", "count": 3},
        {"value": "Argentina", "count": 1},
    ]
    # NULLs are not values a user can type.
    assert index["player"] == [
        {"value": "Kylian Mbappé", "count": 2},
        {"value": "Lionel Messi", "count": 1},
    ]
    assert index["outcome"] == []
