"""When a share is shown as a rate (owner decision D7). Pure: no database, no I/O.

Below MIN_RATE_N in the denominator one result swings a rate by five points or more, so a
caller sends the counts ("1 of 3") and no rate. From MIN_RATE_N up a rate carries its Wilson
95% range, the likely true rate.
"""

from math import sqrt

MIN_RATE_N = 20
# The two-sided 95% normal quantile.
Z95 = 1.959963984540054


def wilson(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval: safe at small n and near 0 or 1 (Brown, Cai and DasGupta, 2001)."""
    if n <= 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def rate(successes: int, n: int) -> dict:
    """A rate only from MIN_RATE_N in the denominator (owner D7); below it, counts alone."""
    if n < MIN_RATE_N:
        return {"count": successes, "of": n, "rate": None, "low": None, "high": None}
    low, high = wilson(successes, n)
    return {"count": successes, "of": n, "rate": successes / n, "low": low, "high": high}
