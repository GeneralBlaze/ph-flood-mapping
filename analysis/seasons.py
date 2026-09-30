"""Season windows for Rivers State.

Dry season (harmattan) runs December–February and gives the baseline.
The rainy season is taken as May–October, covering both rainfall peaks.
"""

import argparse
from dataclasses import dataclass

# Sentinel-1A began routine acquisitions in late 2014; 2015 is the first full year.
FIRST_YEAR = 2015
LAST_YEAR = 2100


@dataclass(frozen=True)
class SeasonWindows:
    dry: tuple[str, str]
    wet: tuple[str, str]


def season_windows(year: int) -> SeasonWindows:
    return SeasonWindows(
        dry=(f"{year - 1}-12-01", f"{year}-03-01"),
        wet=(f"{year}-05-01", f"{year}-11-01"),
    )


def parse_years(value: str) -> list[int]:
    """'2021-2026' or '2025' -> list of years."""
    try:
        parts = [int(p) for p in value.split("-")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected YEAR or YEAR-YEAR, got {value!r}") from exc
    if len(parts) == 1:
        parts = parts * 2
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Expected YEAR or YEAR-YEAR, got {value!r}")
    start, end = parts
    if not FIRST_YEAR <= start <= end <= LAST_YEAR:
        raise argparse.ArgumentTypeError(f"Years must be ascending and from {FIRST_YEAR}, got {value!r}")
    return list(range(start, end + 1))
