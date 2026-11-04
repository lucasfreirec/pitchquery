"""Unit tests for flattening raw StatsBomb events into table rows. No network, no files."""

from typing import Any

import pytest

from pitchquery.data.flatten import MatchContext, flatten_event

MATCH = MatchContext(
    match_id=3869685,
    competition="FIFA World Cup",
    season="2022",
    home_team="Argentina",
    away_team="France",
)
NICKNAMES = {5503: "Lionel Messi"}


def make_event(type_name: str, **extra: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "id": "e1",
        "index": 7,
        "period": 1,
        "minute": 22,
        "second": 31,
        "type": {"id": 0, "name": type_name},
        "team": {"id": 779, "name": "Argentina"},
        "play_pattern": {"id": 1, "name": "Regular Play"},
        "player": {"id": 5503, "name": "Lionel Andrés Messi Cuccittini"},
        "position": {"id": 17, "name": "Right Wing"},
        "location": [60.5, 40.1],
    }
    event.update(extra)
    return event


def test_common_fields() -> None:
    row = flatten_event(make_event("Pressure"), MATCH, NICKNAMES)
    assert row["id"] == "e1"
    assert row["match_id"] == 3869685
    assert row["event_index"] == 7
    assert row["competition"] == "FIFA World Cup"
    assert row["season"] == "2022"
    assert row["team"] == "Argentina"
    assert row["opponent"] == "France"
    assert row["player_id"] == 5503
    assert row["position"] == "Right Wing"
    assert row["type"] == "Pressure"
    assert (row["period"], row["minute"], row["second"]) == (1, 22, 31)
    assert (row["x"], row["y"]) == (60.5, 40.1)
    assert row["play_pattern"] == "Regular Play"


def test_opponent_for_away_team() -> None:
    event = make_event("Pressure", team={"id": 771, "name": "France"})
    assert flatten_event(event, MATCH, NICKNAMES)["opponent"] == "Argentina"


def test_player_uses_lineup_nickname() -> None:
    assert flatten_event(make_event("Pressure"), MATCH, NICKNAMES)["player"] == "Lionel Messi"


def test_player_falls_back_to_full_name_without_nickname() -> None:
    event = make_event("Pressure", player={"id": 1, "name": "Some Full Name"})
    assert flatten_event(event, MATCH, NICKNAMES)["player"] == "Some Full Name"


def test_missing_player_location_and_position_are_none() -> None:
    event = make_event("Half Start")
    for key in ("player", "position", "location"):
        del event[key]
    row = flatten_event(event, MATCH, NICKNAMES)
    assert row["player"] is None
    assert row["player_id"] is None
    assert row["position"] is None
    assert row["x"] is None
    assert row["y"] is None


def test_under_pressure_defaults_to_false() -> None:
    assert flatten_event(make_event("Pass"), MATCH, NICKNAMES)["under_pressure"] is False
    event = make_event("Pass", under_pressure=True)
    assert flatten_event(event, MATCH, NICKNAMES)["under_pressure"] is True


def test_shot() -> None:
    event = make_event(
        "Shot",
        shot={
            "statsbomb_xg": 0.76,
            "end_location": [118.0, 38.2, 0.5],
            "outcome": {"id": 97, "name": "Goal"},
            "body_part": {"id": 40, "name": "Left Foot"},
        },
    )
    row = flatten_event(event, MATCH, NICKNAMES)
    assert row["xg"] == 0.76
    assert (row["end_x"], row["end_y"]) == (118.0, 38.2)
    assert row["outcome"] == "Goal"
    assert row["body_part"] == "Left Foot"


def test_pass_without_outcome_is_complete() -> None:
    event = make_event(
        "Pass",
        **{"pass": {"end_location": [80.0, 20.0], "body_part": {"id": 40, "name": "Right Foot"}}},
    )
    row = flatten_event(event, MATCH, NICKNAMES)
    assert row["outcome"] == "Complete"
    assert (row["end_x"], row["end_y"]) == (80.0, 20.0)
    assert row["body_part"] == "Right Foot"
    assert row["xg"] is None


def test_pass_with_outcome_keeps_it() -> None:
    event = make_event(
        "Pass",
        **{"pass": {"end_location": [80.0, 20.0], "outcome": {"id": 9, "name": "Incomplete"}}},
    )
    assert flatten_event(event, MATCH, NICKNAMES)["outcome"] == "Incomplete"


def test_carry_end_location() -> None:
    event = make_event("Carry", carry={"end_location": [65.0, 41.0]})
    row = flatten_event(event, MATCH, NICKNAMES)
    assert (row["end_x"], row["end_y"]) == (65.0, 41.0)
    assert row["outcome"] is None


def test_dribble_outcome() -> None:
    event = make_event("Dribble", dribble={"outcome": {"id": 8, "name": "Complete"}})
    assert flatten_event(event, MATCH, NICKNAMES)["outcome"] == "Complete"


@pytest.mark.parametrize(
    ("type_name", "detail_key"),
    [("Goal Keeper", "goalkeeper"), ("Ball Receipt*", "ball_receipt"), ("50/50", "50_50")],
)
def test_irregular_detail_keys(type_name: str, detail_key: str) -> None:
    event = make_event(type_name, **{detail_key: {"outcome": {"id": 1, "name": "Success"}}})
    assert flatten_event(event, MATCH, NICKNAMES)["outcome"] == "Success"


def test_type_name_drops_statsbomb_asterisk() -> None:
    assert flatten_event(make_event("Ball Receipt*"), MATCH, NICKNAMES)["type"] == "Ball Receipt"
