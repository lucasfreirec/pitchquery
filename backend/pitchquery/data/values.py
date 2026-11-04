"""The value index: distinct values of each string field, most frequent first.

Used by autocompletion (M5) and "did you mean" on values (M3).
"""

import json
from pathlib import Path
from typing import TypedDict

import duckdb

STRING_FIELDS: tuple[str, ...] = (
    "competition",
    "season",
    "team",
    "opponent",
    "player",
    "position",
    "type",
    "outcome",
    "body_part",
    "play_pattern",
)


class ValueCount(TypedDict):
    value: str
    count: int


ValueIndex = dict[str, list[ValueCount]]


def build_value_index(events_parquet: Path, out: Path) -> ValueIndex:
    con = duckdb.connect()
    try:
        index: ValueIndex = {}
        for field in STRING_FIELDS:
            # `field` comes from the constant above, never from user input.
            rows = con.execute(
                f"""
                SELECT {field}, count(*) AS n
                FROM read_parquet(?)
                WHERE {field} IS NOT NULL
                GROUP BY {field}
                ORDER BY n DESC, {field}
                """,
                [str(events_parquet)],
            ).fetchall()
            index[field] = [{"value": value, "count": count} for value, count in rows]
    finally:
        con.close()
    out.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    return index


def load_value_index(path: Path) -> ValueIndex:
    index: ValueIndex = json.loads(path.read_text(encoding="utf-8"))
    return index
