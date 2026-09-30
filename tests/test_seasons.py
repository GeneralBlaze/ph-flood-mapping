import argparse

import pytest

from analysis.seasons import parse_years, season_windows


def test_dry_season_starts_previous_december():
    windows = season_windows(2023)

    assert windows.dry == ("2022-12-01", "2023-03-01")
    assert windows.wet == ("2023-05-01", "2023-11-01")


def test_parse_years_range():
    assert parse_years("2021-2024") == [2021, 2022, 2023, 2024]


def test_parse_years_single():
    assert parse_years("2025") == [2025]


@pytest.mark.parametrize("bad", ["2024-2021", "abc", "2014-2016", "2021-"])
def test_parse_years_rejects_bad_ranges(bad):
    with pytest.raises(argparse.ArgumentTypeError):
        parse_years(bad)
