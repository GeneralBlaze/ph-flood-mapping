"""Otsu's method on a pre-computed histogram.

Earth Engine returns histograms as (bucket means, counts); computing the split
client-side keeps the threshold inspectable and unit-testable.
"""

from typing import Sequence


def otsu_threshold(counts: Sequence[float], bucket_means: Sequence[float]) -> float:
    """Return the value that maximises between-class variance.

    The threshold is the midpoint between the last bucket of the lower class
    and the first bucket of the upper class.
    """
    if len(counts) != len(bucket_means):
        raise ValueError("counts and bucket_means must be the same length")
    total = float(sum(counts))
    if total <= 0 or len(counts) < 2:
        raise ValueError("histogram is empty")

    grand_sum = sum(c * m for c, m in zip(counts, bucket_means))
    best_split, best_variance = 0, -1.0
    weight_low, sum_low = 0.0, 0.0

    for i in range(len(counts) - 1):
        weight_low += counts[i]
        sum_low += counts[i] * bucket_means[i]
        weight_high = total - weight_low
        if weight_low == 0 or weight_high == 0:
            continue
        mean_low = sum_low / weight_low
        mean_high = (grand_sum - sum_low) / weight_high
        variance = weight_low * weight_high * (mean_low - mean_high) ** 2
        if variance > best_variance:
            best_split, best_variance = i, variance

    return (bucket_means[best_split] + bucket_means[best_split + 1]) / 2.0
