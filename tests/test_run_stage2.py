import argparse

import pytest

from analysis.run_stage2 import parse_pass, slugify


def test_parse_pass_splits_date_and_orbit():
    assert parse_pass("2026-09-29:22") == ("2026-09-29", 22)


@pytest.mark.parametrize("bad", ["2026-09-29", "2026-09-29:x", "29/09/2026:22", ":22"])
def test_parse_pass_rejects_malformed(bad):
    with pytest.raises(argparse.ArgumentTypeError):
        parse_pass(bad)


def test_slugify_lga_names():
    assert slugify("Obio/Akpor") == "obio-akpor"
    assert slugify("Port-Harcourt") == "port-harcourt"
