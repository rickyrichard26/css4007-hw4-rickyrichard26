import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import FIELDS, calculate, lookup, run_tool  # noqa: E402

DISTRICTS = ["Ossbridge", "Ossford", "Tarnvale", "Kelmarsh", "Brightwater", "Stonecairn",
             "Harrowfield", "Lindenmoor", "Redfen", "Ashgrove", "Millbrook", "Coldharbour"]


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
# Expected values below were read by hand from data/corpus.jsonl.
def test_lookup_finds_2025_number():
    r = lookup("Brightwater", "population_2025")
    assert r["value"] == 44675
    assert r["source"] == "NR-05"


def test_lookup_is_case_insensitive():
    assert lookup("brightwater", "population_2025")["value"] == 44675


def test_lookup_applies_correction_notice():
    r = lookup("Brightwater", "area_km2")  # NR-05 says 912.4, NR-16 corrects to 921.4
    assert r["value"] == 921.4
    assert r["source"] == "NR-16"
    assert "corrected" in r["note"]


def test_lookup_misspelled_name():
    r = lookup("Ossbrige", "population_2025")
    assert "error" in r and "Ossbridge" in r["error"]


def test_lookup_two_similar_names_stay_separate():
    a = lookup("Ossbridge", "population_2025")
    b = lookup("Ossford", "population_2025")
    assert (a["value"], b["value"]) == (52904, 30982)
    r = lookup("Oss", "population_2025")  # ambiguous prefix: error naming both
    assert "error" in r and "Ossbridge" in r["error"] and "Ossford" in r["error"]


def test_lookup_ignores_archived_profiles():
    assert lookup("Tarnvale", "population_2025")["value"] == 71388   # not 65,030 (NR-13)
    assert lookup("Kelmarsh", "population_2025")["value"] == 24117   # not 22,110 (NR-14)
    assert lookup("Tarnvale", "population_2025")["source"] == "NR-03"


def test_lookup_water_unit_differs_for_lindenmoor():
    r = lookup("Lindenmoor", "water_use")
    assert r["value"] == 2151400 and r["unit"] == "cubic metres"
    assert lookup("Ossford", "water_use")["unit"] == "megalitres"


def test_lookup_handles_missing_spaces_in_profiles():
    assert lookup("Harrowfield", "population_2025")["value"] == 90212  # "recorded90,212"
    assert lookup("Kelmarsh", "area_km2")["value"] == 593.8            # "593.8square"
    assert lookup("Lindenmoor", "pupils")["value"] == 4115             # "4,115pupils"
    assert lookup("Redfen", "founded_year")["value"] == 1932           # "in1932"


def test_lookup_uses_numbers_not_wording():
    # NR-06 says "up from 15,473" but 14,926 is lower: values are read by position
    assert lookup("Stonecairn", "population_2025")["value"] == 14926
    assert lookup("Stonecairn", "population_2020")["value"] == 15473


def test_lookup_water_tariff():
    r = lookup("Region", "water_tariff_2025")
    assert r["value"] == 142.35 and r["source"] == "NR-15"
    assert lookup("Region", "m3_per_megalitre")["value"] == 1000


def test_lookup_unknown_field_and_wrong_scope():
    assert "error" in lookup("Brightwater", "colour_of_sky")
    assert "error" in lookup("Brightwater", "water_tariff_2025")
    assert "error" in lookup("Region", "schools")


@pytest.mark.parametrize("district", DISTRICTS)
def test_lookup_every_field_parses_for_every_district(district):
    for field in FIELDS:
        assert "error" not in lookup(district, field), (district, field)


def test_lookup_never_raises_on_bad_types():
    assert "error" in lookup(None, 5)  # type: ignore[arg-type]


def test_run_tool_rejects_bad_arguments():
    assert "error" in run_tool("calculate", {"wrong": "x"})
    assert "error" in run_tool("nope", {})
    assert "error" in run_tool("lookup", "not a dict")