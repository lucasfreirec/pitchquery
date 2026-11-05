"""Runs PitchQuery queries on DuckDB: check -> compile -> execute, with a timeout and a row cap."""

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from pitchquery.data.paths import DataPaths
from pitchquery.data.values import ValueIndex, load_value_index
from pitchquery.lang.analyzer import check
from pitchquery.lang.compiler import compile_query
from pitchquery.lang.diagnostics import Diagnostic, Severity
from pitchquery.lang.span import Span

DEFAULT_ROW_CAP = 5_000
DEFAULT_TIMEOUT_S = 5.0


class QueryTimeout(Exception):
    """The query ran longer than the engine's timeout and was interrupted."""


@dataclass(frozen=True, slots=True)
class QueryResult:
    columns: list[str]
    rows: list[tuple[Any, ...]]
    diagnostics: tuple[Diagnostic, ...]
    elapsed_ms: float  # check + compile + execute
    truncated: bool  # True if rows were cut at the row cap

    @property
    def ok(self) -> bool:
        """True if the query ran. It may still have warnings."""
        return not any(d.severity is Severity.ERROR for d in self.diagnostics)


class Engine:
    """Holds the events table in an in-memory DuckDB database.

    Safe to share between threads: each query runs on its own cursor.
    """

    def __init__(
        self,
        events_parquet: Path,
        values: ValueIndex | None = None,
        *,
        row_cap: int = DEFAULT_ROW_CAP,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self.values = values
        self.row_cap = row_cap
        self.timeout_s = timeout_s
        self._con = duckdb.connect()
        # Loaded into memory once (~235k rows): queries then never touch the disk.
        self._con.execute(
            "CREATE TABLE events AS SELECT * FROM read_parquet($1)", [str(events_parquet)]
        )

    @classmethod
    def from_data_dir(cls, paths: DataPaths | None = None) -> "Engine":
        paths = paths or DataPaths.default()
        return cls(paths.events_parquet, load_value_index(paths.values_json))

    def close(self) -> None:
        self._con.close()

    def run(self, source: str) -> QueryResult:
        started = time.perf_counter()

        def result(
            columns: list[str],
            rows: list[tuple[Any, ...]],
            diagnostics: tuple[Diagnostic, ...],
            truncated: bool = False,
        ) -> QueryResult:
            elapsed_ms = (time.perf_counter() - started) * 1000
            return QueryResult(columns, rows, diagnostics, elapsed_ms, truncated)

        analysis = check(source, self.values)
        if analysis.query is None or not analysis.ok:
            return result([], [], analysis.diagnostics)

        compiled = compile_query(analysis.query)
        try:
            # One extra row tells us whether the cap cut anything off.
            columns, rows = self.execute_sql(compiled.sql, compiled.params, self.row_cap + 1)
        except QueryTimeout:
            message = f"The query took longer than {self.timeout_s:g} s and was stopped."
            timeout = Diagnostic(Severity.ERROR, message, Span(0, len(source)))
            return result([], [], (*analysis.diagnostics, timeout))

        truncated = len(rows) > self.row_cap
        return result(columns, rows[: self.row_cap], analysis.diagnostics, truncated)

    def execute_sql(
        self, sql: str, params: tuple[object, ...], max_rows: int | None = None
    ) -> tuple[list[str], list[tuple[Any, ...]]]:
        """Run SQL on a fresh cursor, interrupting it after `timeout_s`."""
        cursor = self._con.cursor()
        timer = threading.Timer(self.timeout_s, cursor.interrupt)
        timer.start()
        try:
            cursor.execute(sql, list(params))
            columns = [column[0] for column in cursor.description or []]
            rows = cursor.fetchall() if max_rows is None else cursor.fetchmany(max_rows)
        except duckdb.InterruptException:
            raise QueryTimeout from None
        finally:
            timer.cancel()
            cursor.close()
        return columns, rows
