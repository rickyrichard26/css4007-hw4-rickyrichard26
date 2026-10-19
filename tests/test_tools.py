import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import calculate, lookup, run_tool  # noqa: E402


# ------------------------- calculate -------------------------
def test_calculate_required_example():
    assert calculate("48317 * 1.0947")["result"] == pytest.approx(48317 * 1.0947)


def test_calculate_basic_and_precedence():
    assert calculate("2 + 3 * 4")["result"] == 14
    assert calculate("(2 + 3) * 4")["result"] == 20
    assert calculate("-5 + 2")["result"] == -3


def test_calculate_division_by_zero():
    assert "error" in calculate("1 / 0")


def test_calculate_invalid_syntax():
    assert "error" in calculate("2 +")


def test_calculate_refuses_import_call():
    assert "error" in calculate("__import__('os').system('echo hi')")


def test_calculate_refuses_attribute_access():
    assert "error" in calculate("(1).__class__")


def test_calculate_refuses_huge_power():
    assert "error" in calculate("9**9**9")


def test_calculate_refuses_names_and_strings():
    assert "error" in calculate("abs(-1)")
    assert "error" in calculate("'a' * 3")


def test_calculate_refuses_too_long_and_non_string():
    assert "error" in calculate("1+" * 300 + "1")
    assert "error" in calculate(123)  # type: ignore[arg-type]


def test_calculate_refuses_booleans():
    assert "error" in calculate("True + 1")


# ------------------------- lookup -------------------------
# TODO: fill in real expected values AFTER lookup works (check them against the
# documents, never copy from questions.json answers into a prompt).
todo = pytest.mark.skip(reason="fill in after lookup is implemented")


@todo
def test_lookup_finds_2025_number():
    r = lookup("Brightwater", "population")
    assert r["value"] == 0  # TODO real value
    assert r["source"].startswith("NR-")


@todo
def test_lookup_misspelled_name():
    r = lookup("Brigthwater", "population")  # typo on purpose
    assert "error" in r and "did you mean" in r["error"]


@todo
def test_lookup_two_similar_names():
    a, b = lookup("TODO_name_1", "population"), lookup("TODO_name_2", "population")
    assert a["value"] != b["value"]


@todo
def test_lookup_archived_profile_not_used():
    r = lookup("TODO_archived_district", "population")
    assert r.get("note", "") or "error" in r  # must not silently return the old value


@todo
def test_lookup_unknown_field():
    assert "error" in lookup("Brightwater", "colour_of_sky")


def test_lookup_never_raises_on_bad_types():
    assert "error" in lookup(None, 5)  # type: ignore[arg-type]


def test_run_tool_rejects_bad_arguments():
    assert "error" in run_tool("calculate", {"wrong": "x"})
    assert "error" in run_tool("nope", {})
    assert "error" in run_tool("lookup", "not a dict")