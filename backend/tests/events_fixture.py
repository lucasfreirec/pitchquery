"""A tiny events table with the real schema, for engine tests that must not need `make data`."""

from pathlib import Path
from typing import Any

import duckdb

from pitchquery.data.flatten import COLUMNS

_DEFAULTS: dict[str, Any] = {
    "competition": "FIFA World Cup",
    "season": "2022",
    "player_id": None,
    "position": None,
    "second": 0,
    "period": 1,
    "x": 60.0,
    "y": 40.0,
    "end_x": None,
    "end_y": None,
    "outcome": None,
    "xg": None,
    "body_part": None,
    "under_pressure": False,
    "play_pattern": "Regular Play",
}


def _event(
    match_id: int, index: int, team: str, player: str | None, type_: str, minute: int, **extra: Any
) -> dict[str, Any]:
    opponent = "France" if team == "Argentina" else "Argentina"
    return {
        **_DEFAULTS,
        "id": f"{match_id}-{index}",
        "match_id": match_id,
        "event_index": index,
        "team": team,
        "opponent": opponent,
        "player": player,
        "type": type_,
        "minute": minute,
        **extra,
    }


MESSI = "Lionel Messi"
MBAPPE = "Kylian Mbappé"
ALVAREZ = "Julián Álvarez"
DE_PAUL = "Rodrigo De Paul"

# 8 events over 2 matches. Argentina: 5, France: 3. Shots: 4 (Messi 1, Mbappé 2, Álvarez 1).
# fmt: off
EVENTS: list[dict[str, Any]] = [
    _event(1, 1, "Argentina", MESSI, "Shot", 10, xg=0.4, outcome="Goal", end_x=120.0, end_y=40.0),
    _event(1, 2, "Argentina", MESSI, "Pass", 12, outcome="Complete", under_pressure=True),
    _event(1, 3, "France", MBAPPE, "Shot", 30, xg=0.1, outcome="Saved", under_pressure=True),
    _event(1, 4, "France", MBAPPE, "Shot", 85, xg=0.8, outcome="Goal"),
    _event(1, 5, "France", None, "Half End", 45),
    _event(2, 1, "Argentina", ALVAREZ, "Shot", 81, xg=0.35, outcome="Off T"),
    _event(2, 2, "Argentina", MESSI, "Carry", 82, end_x=90.0, end_y=20.0),
    _event(2, 3, "Argentina", DE_PAUL, "Pass", 83, outcome="Incomplete"),
]
# fmt: on


def write_events(path: Path, events: list[dict[str, Any]] = EVENTS) -> Path:
    con = duckdb.connect()
    try:
        columns = ", ".join(f'"{name}" {col_type}' for name, col_type in COLUMNS.items())
        con.execute(f"CREATE TABLE events ({columns})")
        placeholders = ", ".join("?" for _ in COLUMNS)
        con.executemany(
            f"INSERT INTO events VALUES ({placeholders})",
            [[event[name] for name in COLUMNS] for event in events],
        )
        con.execute(f"COPY events TO '{path}' (FORMAT parquet)")
    finally:
        con.close()
    return path
