"""What users can query: fields, their types, operators, and which entities have them.

Field and entity names are matched case-insensitively.
"""

from dataclasses import dataclass
from enum import Enum

from pitchquery.lang.ast import ENTITIES


class FieldType(Enum):
    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"

    @property
    def described(self) -> str:
        """How the type reads in messages: "a string", "a number", "a boolean"."""
        return _DESCRIBED[self]

    @property
    def operators(self) -> tuple[str, ...]:
        """Operators that apply to this type, in the order messages list them."""
        return _OPERATORS[self]


_DESCRIBED = {
    FieldType.STRING: "a string",
    FieldType.INT: "a number",
    FieldType.FLOAT: "a number",
    FieldType.BOOL: "a boolean",
}

_NUMBER_OPS = ("=", "!=", "<", "<=", ">", ">=", "in", "between")
_OPERATORS = {
    FieldType.STRING: ("=", "!=", "in", "contains"),
    FieldType.INT: _NUMBER_OPS,
    FieldType.FLOAT: _NUMBER_OPS,
    FieldType.BOOL: ("=", "!="),
}


@dataclass(frozen=True, slots=True)
class FieldSpec:
    name: str
    type: FieldType
    description: str
    # Entities whose events have this field. None means all. `events` always qualifies:
    # it contains every event type.
    entities: tuple[str, ...] | None = None

    def applies_to(self, entity: str) -> bool:
        return self.entities is None or entity == "events" or entity in self.entities


STR, INT, FLOAT, BOOL = FieldType.STRING, FieldType.INT, FieldType.FLOAT, FieldType.BOOL
_END = ("shots", "passes", "carries")

FIELDS: dict[str, FieldSpec] = {
    spec.name: spec
    for spec in [
        FieldSpec("match_id", INT, "StatsBomb match id"),
        FieldSpec("competition", STR, "Competition name"),
        FieldSpec("season", STR, "Season name"),
        FieldSpec("team", STR, "Team of the player making the event"),
        FieldSpec("opponent", STR, "The other team in the match"),
        FieldSpec("player", STR, "Player making the event"),
        FieldSpec("position", STR, "Player's position at the time"),
        FieldSpec("type", STR, "Event type, e.g. Shot, Pass, Dribble"),
        FieldSpec("minute", INT, "Match minute (0-127, extra time included)"),
        FieldSpec("second", INT, "Second within the minute"),
        FieldSpec("period", INT, "1-2 halves, 3-4 extra time, 5 penalty shootout"),
        FieldSpec("x", FLOAT, "Start x, 0-120 towards the opponent's goal"),
        FieldSpec("y", FLOAT, "Start y, 0-80 from the left touchline"),
        FieldSpec("end_x", FLOAT, "End x of a shot, pass or carry", _END),
        FieldSpec("end_y", FLOAT, "End y of a shot, pass or carry", _END),
        FieldSpec("outcome", STR, "Result, e.g. Goal, Complete", ("shots", "passes", "dribbles")),
        FieldSpec("xg", FLOAT, "StatsBomb expected goals of a shot", ("shots",)),
        FieldSpec("body_part", STR, "Body part used", ("shots", "passes")),
        FieldSpec("under_pressure", BOOL, "Whether an opponent was pressing"),
        FieldSpec("play_pattern", STR, "How the possession started"),
    ]
}

# Entity -> the StatsBomb event type it selects (None: all events).
ENTITY_EVENT_TYPES: dict[str, str | None] = {
    "events": None,
    "shots": "Shot",
    "passes": "Pass",
    "dribbles": "Dribble",
    "carries": "Carry",
    "pressures": "Pressure",
}
assert tuple(ENTITY_EVENT_TYPES) == ENTITIES


def lookup(name: str) -> FieldSpec | None:
    return FIELDS.get(name.lower())
