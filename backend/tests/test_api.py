"""HTTP API, through FastAPI's test client, on the tiny fixture table."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pitchquery.api import MAX_QUERY_LENGTH, create_app
from pitchquery.data.values import ValueIndex
from pitchquery.engine import Engine, QueryTimeout
from tests.events_fixture import MBAPPE, MESSI, write_events

VALUES: ValueIndex = {
    "team": [{"value": "Argentina", "count": 5}, {"value": "France", "count": 3}],
    "player": [{"value": MESSI, "count": 3}, {"value": MBAPPE, "count": 2}],
}
DEV_ORIGIN = "http://localhost:5173"


@pytest.fixture(scope="module")
def parquet(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return write_events(tmp_path_factory.mktemp("api") / "events.parquet")


@pytest.fixture(scope="module")
def engine(parquet: Path) -> Iterator[Engine]:
    engine = Engine(parquet, VALUES)
    yield engine
    engine.close()


@pytest.fixture(scope="module")
def client(engine: Engine) -> Iterator[TestClient]:
    with TestClient(create_app(engine, cors_origins=[DEV_ORIGIN])) as client:
        yield client


# --- /health and /schema ----------------------------------------------------------------


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "events": 8}


def test_schema(client: TestClient) -> None:
    body = client.get("/schema").json()
    assert [e["name"] for e in body["entities"]] == [
        "events", "shots", "passes", "dribbles", "carries", "pressures",
    ]  # fmt: skip
    assert body["entities"][1] == {"name": "shots", "event_type": "Shot"}
    fields = {f["name"]: f for f in body["fields"]}
    assert len(fields) == 20
    assert fields["xg"] == {
        "name": "xg",
        "type": "number",
        "description": "StatsBomb expected goals of a shot",
        "entities": ["shots"],
    }
    assert fields["team"]["entities"] is None
    assert body["operators"]["boolean"] == ["=", "!="]
    assert "contains" in body["operators"]["string"]
    assert "where" in body["keywords"]


# --- /query -----------------------------------------------------------------------------


def test_query_returns_rows_and_columns(client: TestClient) -> None:
    response = client.post("/query", json={"query": "shots | select player, xg | limit 2"})
    assert response.status_code == 200
    body = response.json()
    assert body["columns"] == ["player", "xg"]
    assert body["rows"] == [[MESSI, 0.4], [MBAPPE, 0.1]]
    assert body["diagnostics"] == []
    assert body["truncated"] is False
    assert body["elapsed_ms"] > 0


def test_query_aggregation(client: TestClient) -> None:
    body = client.post("/query", json={"query": "events | count by team"}).json()
    assert body["columns"] == ["team", "count"]
    assert body["rows"] == [["Argentina", 5], ["France", 3]]


def test_missing_values_are_null(client: TestClient) -> None:
    body = client.post("/query", json={"query": "events | select xg | limit 2"}).json()
    assert body["rows"] == [[0.4], [None]]


def test_query_with_warnings_still_runs(client: TestClient) -> None:
    response = client.post("/query", json={"query": 'shots where team = "Frnace"'})
    assert response.status_code == 200
    body = response.json()
    assert body["rows"] == []
    assert body["diagnostics"] == [
        {
            "severity": "warning",
            "message": "No team `Frnace` in the data. Did you mean `France`?",
            "span": {"start": 19, "end": 27},
            "suggestions": ["France"],
        }
    ]


def test_query_with_errors_is_a_400_with_spans(client: TestClient) -> None:
    response = client.post("/query", json={"query": "shots where xgg > 1"})
    assert response.status_code == 400
    body = response.json()
    assert body["rows"] == [] and body["columns"] == []
    assert body["diagnostics"] == [
        {
            "severity": "error",
            "message": "Unknown field `xgg`. Did you mean `xg`?",
            "span": {"start": 12, "end": 15},
            "suggestions": ["xg"],
        }
    ]


def test_syntax_error_is_a_400(client: TestClient) -> None:
    response = client.post("/query", json={"query": "shots where"})
    assert response.status_code == 400
    assert response.json()["diagnostics"][0]["span"] == {"start": 11, "end": 11}


def test_timeout_is_a_504(
    client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def slow(sql: str, params: tuple[object, ...], max_rows: int | None = None) -> None:
        raise QueryTimeout

    monkeypatch.setattr(engine, "execute_sql", slow)
    response = client.post("/query", json={"query": "events"})
    assert response.status_code == 504
    assert "took longer than" in response.json()["diagnostics"][0]["message"]


def test_truncated_results(parquet: Path) -> None:
    capped = Engine(parquet, row_cap=3)
    try:
        with TestClient(create_app(capped)) as client:
            body = client.post("/query", json={"query": "events"}).json()
    finally:
        capped.close()
    assert len(body["rows"]) == 3
    assert body["truncated"] is True


# --- /validate --------------------------------------------------------------------------


def test_validate_valid_query(client: TestClient) -> None:
    response = client.post("/validate", json={"query": 'shots where team = "France"'})
    assert response.status_code == 200
    assert response.json() == {"diagnostics": []}


def test_validate_returns_every_diagnostic_with_200(client: TestClient) -> None:
    response = client.post("/validate", json={"query": "passes where xgg > 1 and xg > 1"})
    assert response.status_code == 200
    messages = [d["message"] for d in response.json()["diagnostics"]]
    assert messages == ["Unknown field `xgg`. Did you mean `xg`?", "`xg` only exists for `shots`."]


# --- /complete --------------------------------------------------------------------------


def test_complete(client: TestClient) -> None:
    response = client.post("/complete", json={"query": "shots wh", "cursor": 8})
    assert response.status_code == 200
    assert response.json() == {
        "suggestions": [
            {"label": "where", "kind": "keyword", "span": {"start": 6, "end": 8}, "detail": None}
        ]
    }


def test_complete_values_use_the_value_index(client: TestClient) -> None:
    body = client.post("/complete", json={"query": "shots where team = ", "cursor": 19}).json()
    assert [s["label"] for s in body["suggestions"]] == ['"Argentina"', '"France"']
    assert body["suggestions"][0]["kind"] == "value"


@pytest.mark.parametrize("cursor", [-1, 9])
def test_complete_cursor_out_of_range_is_a_422(client: TestClient, cursor: int) -> None:
    response = client.post("/complete", json={"query": "shots wh", "cursor": cursor})
    assert response.status_code == 422


# --- Request validation -----------------------------------------------------------------


@pytest.mark.parametrize("path", ["/query", "/validate"])
def test_missing_query_is_a_422(client: TestClient, path: str) -> None:
    assert client.post(path, json={}).status_code == 422


@pytest.mark.parametrize("path", ["/query", "/validate"])
def test_unknown_request_fields_are_a_422(client: TestClient, path: str) -> None:
    assert client.post(path, json={"query": "shots", "sql": "DROP"}).status_code == 422


def test_query_length_is_limited(client: TestClient) -> None:
    too_long = "shots" + " " * MAX_QUERY_LENGTH
    assert client.post("/query", json={"query": too_long}).status_code == 422


# --- CORS -------------------------------------------------------------------------------


def test_cors_allows_the_dev_frontend(client: TestClient) -> None:
    response = client.options(
        "/query",
        headers={"Origin": DEV_ORIGIN, "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == DEV_ORIGIN


def test_cors_rejects_other_origins(client: TestClient) -> None:
    response = client.post(
        "/query", json={"query": "shots"}, headers={"Origin": "https://evil.example"}
    )
    assert "access-control-allow-origin" not in response.headers
