import pytest

from analysis.terrain_classes import describe_position


@pytest.mark.parametrize(
    ("hand_m", "hollow_m", "expected"),
    [
        (0.5, 0.0, "beside a drainage channel"),
        (2.5, 0.0, "slightly above the nearest channel"),
        (6.0, 0.0, "well above the nearest channel"),
        (6.0, -1.2, "well above the nearest channel, in a local hollow"),
    ],
)
def test_describe_position(hand_m, hollow_m, expected):
    assert describe_position(hand_m, hollow_m) == expected


def test_describe_position_rejects_negative_hand():
    with pytest.raises(ValueError):
        describe_position(-1.0, 0.0)
