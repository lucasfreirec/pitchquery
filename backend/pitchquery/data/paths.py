"""Where the dataset lives on disk.

Defaults to `<repo>/data`. Set PITCHQUERY_DATA_DIR to override it (e.g. in Docker).
"""

import os
from dataclasses import dataclass
from pathlib import Path

# backend/pitchquery/data/paths.py -> parents[3] is the repository root.
_REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class DataPaths:
    root: Path

    @classmethod
    def default(cls) -> "DataPaths":
        override = os.environ.get("PITCHQUERY_DATA_DIR")
        return cls(Path(override) if override else _REPO_ROOT / "data")

    @property
    def raw(self) -> Path:
        """Cache of the downloaded StatsBomb JSON, mirroring the open-data repo layout."""
        return self.root / "raw"

    @property
    def events_parquet(self) -> Path:
        return self.root / "events.parquet"

    @property
    def values_json(self) -> Path:
        return self.root / "values.json"
