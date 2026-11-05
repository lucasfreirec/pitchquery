"""Edit distance and "did you mean" suggestions."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pitchquery.lang.suggest import damerau_levenshtein, did_you_mean, suggest


@pytest.mark.parametrize(
    ("a", "b", "distance"),
    [
        ("", "", 0),
        ("xg", "xg", 0),
        ("", "abc", 3),  # 3 insertions
        ("abc", "", 3),  # 3 deletions
        ("xgg", "xg", 1),  # deletion
        ("mnute", "minute", 1),  # insertion
        ("tean", "team", 1),  # substitution
        ("shtos", "shots", 1),  # transposition: plain Levenshtein would say 2
        ("adn", "and", 1),
        ("kitten", "sitting", 3),
        ("ca", "abc", 3),  # optimal string alignment: no edits of a transposed pair
    ],
)
def test_damerau_levenshtein(a: str, b: str, distance: int) -> None:
    assert damerau_levenshtein(a, b) == distance
    assert damerau_levenshtein(b, a) == distance


def test_suggest_finds_close_candidates() -> None:
    assert suggest("xgg", ["minute", "xg", "x"]) == ["xg"]  # "x" is 2 edits away: too far


def test_suggest_is_case_insensitive_and_returns_candidates_as_written() -> None:
    assert suggest("argentna", ["Argentina", "Brazil"]) == ["Argentina"]


def test_suggest_threshold_grows_with_word_length() -> None:
    # Short words allow 1 edit, longer words len // 3.
    assert suggest("ab", ["xy"]) == []
    assert suggest("ab", ["ax"]) == ["ax"]
    assert suggest("Argntna", ["Argentina"]) == ["Argentina"]  # 2 edits, length 7


def test_suggest_ranks_by_distance_then_candidate_order() -> None:
    # Candidates come in frequency order; on equal distance, the first one wins.
    assert suggest("tem", ["time", "team", "temp"]) == ["team", "temp"]  # time: 2 edits


def test_suggest_limit() -> None:
    assert suggest("a", ["b", "c", "d", "e"], limit=2) == ["b", "c"]


def test_suggest_falls_back_to_substring_match() -> None:
    # "Lewandow" is 3 edits from the word "Lewandowski": too far, but it is contained.
    players = ["Robert Lewandowski", "Kylian Mbappé", "Lewandowska Anna"]
    assert suggest("Lewandow", players) == ["Robert Lewandowski", "Lewandowska Anna"]


def test_suggest_ignores_accents() -> None:
    assert suggest("Mbape", ["Kylian Mbappé", "Lionel Messi"]) == ["Kylian Mbappé"]
    assert suggest("Modric", ["Luka Modrić"]) == ["Luka Modrić"]


def test_suggest_matches_single_words_of_multi_word_candidates() -> None:
    # "Griezman" is 1 edit from the word "Griezmann", far from the full name.
    assert suggest("Griezman", ["Antoine Griezmann", "Olivier Giroud"]) == ["Antoine Griezmann"]


def test_an_exact_word_ranks_before_a_near_whole_match() -> None:
    assert suggest("Silva", ["Silvo", "Bernardo Silva"]) == ["Bernardo Silva", "Silvo"]


def test_substring_fallback_needs_three_characters() -> None:
    assert suggest("me", ["Lionel Messi"]) == []


def test_no_match() -> None:
    assert suggest("zzzz", ["shots", "passes"]) == []


def test_did_you_mean() -> None:
    assert did_you_mean([]) == ""
    assert did_you_mean(["xg"]) == " Did you mean `xg`?"
    assert did_you_mean(["xg", "x"]) == " Did you mean `xg`?"


def test_bounded_distance_stops_early_but_reports_too_far() -> None:
    assert damerau_levenshtein("abcdef", "uvwxyz", max_distance=2) == 3
    assert damerau_levenshtein("kitten", "sitting", max_distance=2) == 3


def test_bounded_distance_is_exact_within_the_bound() -> None:
    for a, b in [("shtos", "shots"), ("kitten", "sitting"), ("ca", "abc"), ("", "ab")]:
        assert damerau_levenshtein(a, b, max_distance=3) == damerau_levenshtein(a, b)


@given(st.text("abcd", max_size=8), st.text("abcd", max_size=8), st.integers(0, 4))
def test_bounded_distance_matches_the_full_table(a: str, b: str, bound: int) -> None:
    # A small alphabet makes matches, near-misses and transpositions common.
    assert damerau_levenshtein(a, b, bound) == min(damerau_levenshtein(a, b), bound + 1)
