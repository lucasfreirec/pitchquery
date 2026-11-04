"""Fetch raw StatsBomb JSON from the statsbomb/open-data GitHub repo, with an on-disk cache."""

import time
import urllib.request
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
_TIMEOUT_S = 60
_RETRIES = 3


def fetch(relative: str, raw_dir: Path) -> Path:
    """Download `BASE_URL/relative` to `raw_dir/relative` unless it is already cached."""
    target = raw_dir / relative
    if target.exists() and target.stat().st_size > 0:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, _RETRIES + 1):
        try:
            with urllib.request.urlopen(f"{BASE_URL}/{relative}", timeout=_TIMEOUT_S) as resp:
                body: bytes = resp.read()
            break
        except OSError:
            if attempt == _RETRIES:
                raise
            time.sleep(2**attempt)

    # Write then rename, so an interrupted download never leaves a truncated cached file.
    partial = target.with_suffix(target.suffix + ".part")
    partial.write_bytes(body)
    partial.replace(target)
    return target


def fetch_all(relatives: Iterable[str], raw_dir: Path, workers: int = 8) -> list[Path]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda rel: fetch(rel, raw_dir), relatives))
