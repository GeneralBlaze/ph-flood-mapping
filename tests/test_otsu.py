import pytest

from analysis.otsu import otsu_threshold


def test_splits_two_separated_modes_between_them():
    # Arrange: water mode around -8 dB drop, land mode around 0 dB
    bucket_means = [-10, -9, -8, -7, -6, -2, -1, 0, 1, 2]
    counts = [5, 20, 40, 20, 5, 10, 40, 80, 40, 10]

    # Act
    threshold = otsu_threshold(counts, bucket_means)

    # Assert
    assert -6 <= threshold <= -2


def test_handles_unequal_class_sizes():
    bucket_means = [-12, -11, -10, 0, 1, 2]
    counts = [2, 3, 2, 500, 900, 500]

    threshold = otsu_threshold(counts, bucket_means)

    assert -10 <= threshold < 0


def test_rejects_mismatched_inputs():
    with pytest.raises(ValueError):
        otsu_threshold([1, 2, 3], [0, 1])


def test_rejects_empty_histogram():
    with pytest.raises(ValueError):
        otsu_threshold([0, 0, 0], [0, 1, 2])
