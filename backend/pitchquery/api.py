"""HTTP API (FastAPI). Run with `make dev`, or: uvicorn pitchquery.api:app

    POST /query     run a query        -> columns, rows, diagnostics, elapsed_ms, truncated
    POST /validate  check a query      -> diagnostics (for live error underlining)
    POST /complete  suggest at cursor  -> suggestions
    GET  /schema    entities, fields, operators, keywords
    GET  /health    liveness + number of events loaded

Status codes for /query: 200 the query ran (maybe with warnings); 400 it has errors and
did not run; 504 it was stopped by the timeout. The body has the same shape in all three
cases, with every diagnostic and its span. /validate and /complete always answer 200:
invalid input is their normal case. Malformed requests get FastAPI's standard 422.
"""

import os
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal, Self

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from pitchquery.engine import Engine
from pitchquery.lang.analyzer import check
from pitchquery.lang.ast import ENTITIES
from pitchquery.lang.complete import Suggestion, complete
from pitchquery.lang.diagnostics import Diagnostic
from pitchquery.lang.schema import ENTITY_EVENT_TYPES, FIELDS, FieldType
from pitchquery.lang.span import Span
from pitchquery.lang.tokens import KEYWORDS

MAX_QUERY_LENGTH = 2_000
DEFAULT_CORS_ORIGINS = ["http://localhost:5173"]  # the Vite dev server

# --- Models -----------------------------------------------------------------------------


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QueryRequest(_Request):
    query: str = Field(max_length=MAX_QUERY_LENGTH, examples=["shots where xg > 0.3"])


class CompleteRequest(QueryRequest):
    cursor: int = Field(ge=0, description="Offset in `query`, 0 to len(query).")

    @model_validator(mode="after")
    def _cursor_in_query(self) -> Self:
        if self.cursor > len(self.query):
            raise ValueError(f"cursor {self.cursor} is past the end of the query")
        return self


class SpanModel(BaseModel):
    start: int
    end: int

    @classmethod
    def of(cls, span: Span) -> "SpanModel":
        return cls(start=span.start, end=span.end)


class DiagnosticModel(BaseModel):
    severity: Literal["error", "warning"]
    message: str
    span: SpanModel
    suggestions: list[str]

    @classmethod
    def of(cls, diagnostic: Diagnostic) -> "DiagnosticModel":
        return cls(
            severity=diagnostic.severity.value,
            message=diagnostic.message,
            span=SpanModel.of(diagnostic.span),
            suggestions=list(diagnostic.suggestions),
        )


def _diagnostics(diagnostics: Iterable[Diagnostic]) -> list[DiagnosticModel]:
    return [DiagnosticModel.of(d) for d in diagnostics]


class QueryResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    diagnostics: list[DiagnosticModel]
    elapsed_ms: float
    truncated: bool = Field(description="True if rows were cut at the row cap.")


class ValidateResponse(BaseModel):
    diagnostics: list[DiagnosticModel]


class SuggestionModel(BaseModel):
    label: str
    kind: Literal["entity", "field", "operator", "value", "keyword"]
    span: SpanModel
    detail: str | None

    @classmethod
    def of(cls, suggestion: Suggestion) -> "SuggestionModel":
        return cls(
            label=suggestion.label,
            kind=suggestion.kind.value,
            span=SpanModel.of(suggestion.span),
            detail=suggestion.detail,
        )


class CompleteResponse(BaseModel):
    suggestions: list[SuggestionModel]


class EntityModel(BaseModel):
    name: str
    event_type: str | None


class FieldModel(BaseModel):
    name: str
    type: Literal["string", "number", "boolean"]
    description: str
    entities: list[str] | None = Field(description="Entities that have it; null for all.")


class SchemaResponse(BaseModel):
    entities: list[EntityModel]
    fields: list[FieldModel]
    operators: dict[str, list[str]]
    keywords: list[str]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    events: int


# --- App --------------------------------------------------------------------------------


def _cors_origins_from_env() -> list[str]:
    raw = os.environ.get("PITCHQUERY_CORS_ORIGINS")
    if raw is None:
        return DEFAULT_CORS_ORIGINS
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def get_engine(request: Request) -> Engine:
    engine: Engine = request.app.state.engine
    return engine


EngineDep = Annotated[Engine, Depends(get_engine)]


def create_app(engine: Engine | None = None, *, cors_origins: list[str] | None = None) -> FastAPI:
    """Build the app. Without an engine, one is loaded from the data directory at startup."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        owned = engine is None
        app.state.engine = Engine.from_data_dir() if engine is None else engine
        yield
        if owned:
            app.state.engine.close()

    app = FastAPI(
        title="PitchQuery",
        version="0.1.0",
        description="A search language for football match events (StatsBomb open data).",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins if cors_origins is not None else _cors_origins_from_env(),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health")
    def health(engine: EngineDep) -> HealthResponse:
        rows = engine.execute_sql("SELECT count(*) FROM events", ())[1]
        return HealthResponse(status="ok", events=rows[0][0])

    @app.get("/schema")
    def schema() -> SchemaResponse:
        return SchemaResponse(
            entities=[
                EntityModel(name=name, event_type=ENTITY_EVENT_TYPES[name]) for name in ENTITIES
            ],
            fields=[
                FieldModel(
                    name=spec.name,
                    type=spec.type.label,
                    description=spec.description,
                    entities=list(spec.entities) if spec.entities else None,
                )
                for spec in FIELDS.values()
            ],
            operators={
                field_type.label: list(field_type.operators)
                for field_type in (FieldType.STRING, FieldType.INT, FieldType.BOOL)
            },
            keywords=list(KEYWORDS),
        )

    @app.post(
        "/query",
        response_model=QueryResponse,
        responses={
            400: {"model": QueryResponse, "description": "The query has errors."},
            504: {"model": QueryResponse, "description": "The query timed out."},
        },
    )
    def query(request: QueryRequest, engine: EngineDep) -> QueryResponse | JSONResponse:
        result = engine.run(request.query)
        body = QueryResponse(
            columns=result.columns,
            rows=[list(row) for row in result.rows],
            diagnostics=_diagnostics(result.diagnostics),
            elapsed_ms=result.elapsed_ms,
            truncated=result.truncated,
        )
        if result.timed_out:
            return JSONResponse(body.model_dump(), status_code=504)
        if not result.ok:
            return JSONResponse(body.model_dump(), status_code=400)
        return body

    @app.post("/validate")
    def validate(request: QueryRequest, engine: EngineDep) -> ValidateResponse:
        analysis = check(request.query, engine.values)
        return ValidateResponse(diagnostics=_diagnostics(analysis.diagnostics))

    @app.post("/complete")
    def complete_(request: CompleteRequest, engine: EngineDep) -> CompleteResponse:
        suggestions = complete(request.query, request.cursor, engine.values)
        return CompleteResponse(suggestions=[SuggestionModel.of(s) for s in suggestions])

    return app


app = create_app()
