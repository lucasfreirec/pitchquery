"""Edit distance and "did you mean" suggestions."""

import unicodedata
from collections.abc import Iterable, Sequence
from functools import lru_cache


def damerau_levenshtein(a: str, b: str, max_distance: int | None = None) -> int:
    """Edits to turn `a` into `b`: insert, delete, substitute, or swap two adjacent chars.

    This is the "optimal string alignment" variant: a transposed pair is not edited
    again afterwards. It is what typo correction needs, and stays a simple O(len(a) *
    len(b)) table. `dist[i][j]` is the distance between the first i chars of `a` and the
    first j chars of `b`.

    With `max_distance`, stops as soon as the result must exceed it and returns
    `max_distance + 1`. Results within the bound are exact.
    """
    dist = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        dist[i][0] = i  # delete all of a[:i]
    for j in range(len(b) + 1):
        dist[0][j] = j  # insert all of b[:j]

    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dist[i][j] = min(
                dist[i - 1][j] + 1,  # deletion
                dist[i][j - 1] + 1,  # insertion
                dist[i - 1][j - 1] + cost,  # substitution (or match)
            )
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                dist[i][j] = min(dist[i][j], dist[i - 2][j - 2] + 1)  # transposition
        # Row i only reads rows i-1 and i-2, and a cell is never smaller than the cells
        # it reads (edits cost 0 or 1). So once two consecutive rows are entirely over
        # the bound, every later row is too, and so is the result.
        if (
            max_distance is not None
            and min(dist[i]) > max_distance
            and min(dist[i - 1]) > max_distance
        ):
            return max_distance + 1
    result = dist[len(a)][len(b)]
    return result if max_distance is None else min(result, max_distance + 1)


@lru_cache(maxsize=4096)  # value lists are re-normalized on every check otherwise
def normalize(text: str) -> str:
    """Lowercase and strip accents, so "Mbappé" and "mbappe" compare equal."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def suggest(word: str, candidates: Iterable[str], limit: int = 3) -> list[str]:
    """Candidates close to `word`, best first. Ignores case and accents.

    A candidate qualifies if it, or one of its words ("Mbappé" in "Kylian Mbappé"), is
    at most max(1, len(word) // 3) edits away: short words allow one typo, longer ones a
    few. Ranking is by distance; ties keep the candidates' order, so pass them
    most-relevant first (e.g. by frequency).

    If nothing is close, fall back to candidates containing `word` (at least 3 chars), so
    "Cristiano" finds "Cristiano Ronaldo".
    """
    needle = normalize(word)
    max_distance = max(1, len(needle) // 3)
    candidate_list = list(candidates)

    scored: list[tuple[int, int, str]] = []
    for order, candidate in enumerate(candidate_list):
        normalized = normalize(candidate)
        options = [normalized, *normalized.split()] if " " in normalized else [normalized]
        distance = min(_bounded_distance(needle, option, max_distance) for option in options)
        if distance <= max_distance:
            scored.append((distance, order, candidate))
    if scored:
        scored.sort()
        return [candidate for _, _, candidate in scored[:limit]]

    if len(needle) >= 3:
        return [c for c in candidate_list if needle in normalize(c)][:limit]
    return []


def _bounded_distance(a: str, b: str, max_distance: int) -> int:
    # The distance is at least the length difference: skip the O(n * m) table when that
    # alone is too far. This keeps suggestions over ~700 player names to a few ms.
    if abs(len(a) - len(b)) > max_distance:
        return max_distance + 1
    return damerau_levenshtein(a, b, max_distance)


def did_you_mean(suggestions: Sequence[str]) -> str:
    """The message suffix for the best suggestion, or "" if there is none."""
    return f" Did you mean `{suggestions[0]}`?" if suggestions else ""
