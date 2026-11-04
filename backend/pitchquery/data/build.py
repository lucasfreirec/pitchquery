"""Build data/events.parquet and data/values.json from StatsBomb open data.

    python -m pitchquery.data.build [--competition 43] [--season 106]

Downloads are cached in data/raw/; the Parquet file and value index are always rebuilt.
"""

import argparse
import json
import tempfile
import time
from pathlib import Path
from typing import Any

import duckdb

from pitchquery.data.download import fetch, fetch_all
from pitchquery.data.flatten import COLUMNS, MatchContext, flatten_event
from pitchquery.data.paths import DataPaths
from pitchquery.data.values import build_value_index

WORLD_CUP_2022 = (43, 106)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _nicknames(lineups: list[dict[str, Any]]) -> dict[int, str]:
    return {
        player["player_id"]: player["player_nickname"]
        for team in lineups
        for player in team["lineup"]
        if player["player_nickname"]
    }


def _match_context(match: dict[str, Any]) -> MatchContext:
    return MatchContext(
        match_id=match["match_id"],
        competition=match["competition"]["competition_name"],
        season=match["season"]["season_name"],
        home_team=match["home_team"]["home_team_name"],
        away_team=match["away_team"]["away_team_name"],
    )


def _write_parquet(ndjson: Path, out: Path) -> int:
    columns = ", ".join(f"'{name}': '{col_type}'" for name, col_type in COLUMNS.items())
    con = duckdb.connect()
    try:
        con.execute(
            f"""
            COPY (
                SELECT * FROM read_json(?, format = 'newline_delimited', columns = {{{columns}}})
                ORDER BY match_id, event_index
            ) TO '{out}' (FORMAT parquet, COMPRESSION zstd)
            """,
            [str(ndjson)],
        )
        row = con.execute("SELECT count(*) FROM read_parquet(?)", [str(out)]).fetchone()
    finally:
        con.close()
    assert row is not None
    count: int = row[0]
    return count


def build(paths: DataPaths, competition_id: int, season_id: int) -> None:
    started = time.perf_counter()
    paths.root.mkdir(parents=True, exist_ok=True)

    matches = _load(fetch(f"matches/{competition_id}/{season_id}.json", paths.raw))
    ids = [m["match_id"] for m in matches]
    print(f"{len(ids)} matches; downloading events and lineups (cached in {paths.raw})")
    fetch_all([f"events/{i}.json" for i in ids] + [f"lineups/{i}.json" for i in ids], paths.raw)

    with tempfile.TemporaryDirectory() as tmp:
        ndjson = Path(tmp) / "events.ndjson"
        with ndjson.open("w", encoding="utf-8") as out:
            for match in matches:
                context = _match_context(match)
                nicknames = _nicknames(_load(paths.raw / f"lineups/{context.match_id}.json"))
                for event in _load(paths.raw / f"events/{context.match_id}.json"):
                    row = flatten_event(event, context, nicknames)
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
        count = _write_parquet(ndjson, paths.events_parquet)

    build_value_index(paths.events_parquet, paths.values_json)
    elapsed = time.perf_counter() - started
    print(f"Wrote {count:,} events to {paths.events_parquet} in {elapsed:.1f}s")
    print(f"Wrote value index to {paths.values_json}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--competition", type=int, default=WORLD_CUP_2022[0])
    parser.add_argument("--season", type=int, default=WORLD_CUP_2022[1])
    args = parser.parse_args()
    build(DataPaths.default(), args.competition, args.season)


if __name__ == "__main__":
    main()
