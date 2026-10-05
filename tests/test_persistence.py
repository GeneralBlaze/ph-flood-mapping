import pytest

from analysis.persistence import DRAINED, NEW, NOT_IMAGED, STANDING, hectares_by_class, site_status


def test_hectares_by_class_names_each_group_and_converts_m2():
    groups = [{"class": DRAINED, "sum": 25_000.0}, {"class": STANDING, "sum": 10_000.0}, {"class": NEW, "sum": 500.0}]

    assert hectares_by_class(groups) == {"drained": 2.5, "standing": 1.0, "new": 0.1, "not_imaged": 0.0}


def test_hectares_by_class_fills_missing_classes_with_zero():
    assert hectares_by_class([{"class": STANDING, "sum": 20_000.0}]) == {"drained": 0.0, "standing": 2.0, "new": 0.0, "not_imaged": 0.0}


def test_hectares_by_class_ignores_background():
    assert hectares_by_class([{"class": 0, "sum": 9e9}])["standing"] == 0.0


@pytest.mark.parametrize(
    ("before", "after", "status"),
    [
        (0.6, 0.4, "standing"),   # still under water after the dry spell
        (0.0, 0.3, "standing"),   # wet now even if missed on the first date
        (0.5, 0.02, "drained"),   # was flooded, now clear
        (0.03, 0.01, "dry"),      # not flooded on either radar date
    ],
)
def test_site_status(before, after, status):
    assert site_status(before, after, covered=1.0, min_frac=0.1) == status


def test_hectares_by_class_reports_area_not_imaged():
    assert hectares_by_class([{"class": NOT_IMAGED, "sum": 30_000.0}])["not_imaged"] == 3.0


def test_site_outside_radar_swath_is_not_called_dry():
    assert site_status(0.0, 0.0, covered=0.2, min_frac=0.1) == "not_imaged"
