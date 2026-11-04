"""Turn one nested StatsBomb event into one flat row of the `events` table."""

from dataclasses import dataclass
from typing import Any

# Column name -> DuckDB type, in table order. The single source of truth for the schema
# of events.parquet.
COLUMNS: dict[str, str] = {
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

# StatsBomb puts type-specific details under a key derived from the type name, but not
# always predictably. Types missing here simply have no details we use.
_DETAIL_KEYS: dict[str, str] = {
    "50/50": "50_50",
    "Ball Receipt*": "ball_receipt",
    "Ball Recovery": "ball_recovery",
    "Bad Behaviour": "bad_behaviour",
    "Block": "block",
    "Carry": "carry",
    "Clearance": "clearance",
    "Dribble": "dribble",
    "Duel": "duel",
    "Foul Committed": "foul_committed",
    "Foul Won": "foul_won",
    "Goal Keeper": "goalkeeper",
    "Interception": "interception",
    "Miscontrol": "miscontrol",
    "Pass": "pass",
    "Shot": "shot",
    "Substitution": "substitution",
}


@dataclass(frozen=True)
class MatchContext:
    """Match-level facts that every event row repeats."""

    match_id: int
    competition: str
    season: str
    home_team: str
    away_team: str

    def opponent_of(self, team: str) -> str:
        return self.away_team if team == self.home_team else self.home_team


Row = dict[str, Any]


def _name(obj: dict[str, Any] | None) -> str | None:
    return obj["name"] if obj else None


def _xy(location: list[float] | None) -> tuple[float | None, float | None]:
    # Shot end locations are [x, y, z]; we keep x and y only.
    if not location:
        return None, None
    return location[0], location[1]


def flatten_event(event: dict[str, Any], match: MatchContext, nicknames: dict[int, str]) -> Row:
    """Flatten a StatsBomb event.

    `nicknames` maps player_id to the short name from the lineups ("Lionel Messi" rather
    than "Lionel Andrés Messi Cuccittini"); players without one keep their full name.
    """
    raw_type: str = event["type"]["name"]
    details: dict[str, Any] = event.get(_DETAIL_KEYS.get(raw_type, ""), {})
    team: str = event["team"]["name"]

    player = event.get("player")
    player_id: int | None = player["id"] if player else None
    player_name = nicknames.get(player["id"], player["name"]) if player else None

    x, y = _xy(event.get("location"))
    end_x, end_y = _xy(details.get("end_location"))

    outcome = _name(details.get("outcome"))
    if raw_type == "Pass" and outcome is None:
        # StatsBomb omits the outcome of a completed pass.
        outcome = "Complete"

    return {
        "id": event["id"],
        "match_id": match.match_id,
        "event_index": event["index"],
        "competition": match.competition,
        "season": match.season,
        "team": team,
        "opponent": match.opponent_of(team),
        "player": player_name,
        "player_id": player_id,
        "position": _name(event.get("position")),
        "type": raw_type.rstrip("*"),
        "minute": event["minute"],
        "second": event["second"],
        "period": event["period"],
        "x": x,
        "y": y,
        "end_x": end_x,
        "end_y": end_y,
        "outcome": outcome,
        "xg": details.get("statsbomb_xg"),
        "body_part": _name(details.get("body_part")),
        "under_pressure": bool(event.get("under_pressure", False)),
        "play_pattern": _name(event.get("play_pattern")),
    }
