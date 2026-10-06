import pytest

from analysis.area_request import (
    AreaError,
    RateLimiter,
    area_km2,
    bbox_with_margin,
    check_token,
    issue_token,
    ring_key,
    validate_ring,
)

# ~1.1 km square in Obio/Akpor, as [lat, lon]
SQUARE = [[4.80, 7.00], [4.80, 7.01], [4.81, 7.01], [4.81, 7.00]]
SECRET = b"test-secret"


def test_area_km2_of_a_hundredth_degree_square():
    assert area_km2(SQUARE) == pytest.approx(1.226, abs=0.02)


def test_validate_ring_accepts_and_rounds_a_good_area():
    ring = validate_ring([[4.800001234, 7.0], [4.80, 7.01], [4.81, 7.01], [4.81, 7.00]])
    assert ring[0] == [4.8, 7.0]
    assert len(ring) == 4


@pytest.mark.parametrize("ring, message", [
    ("not a list", "corners"),
    ([[4.8, 7.0], [4.8, 7.01]], "at least 3"),
    ([[4.8, 7.0]] * 61, "at most 60"),
    ([[4.8, "x"], [4.8, 7.01], [4.81, 7.01]], "numbers"),
    ([[float("nan"), 7.0], [4.8, 7.01], [4.81, 7.01]], "numbers"),
    ([[6.5, 3.3], [6.5, 3.31], [6.51, 3.31]], "Rivers State"),          # Lagos
    ([[4.80, 7.00], [4.80, 7.05], [4.85, 7.05], [4.85, 7.00]], "10 km²"),  # ~30 km²
    ([[4.80, 7.00], [4.80, 7.00001], [4.80001, 7.0]], "too small"),
])
def test_validate_ring_rejects_bad_input(ring, message):
    with pytest.raises(AreaError, match=message):
        validate_ring(ring)


def test_ring_key_is_stable_and_order_sensitive():
    assert ring_key(SQUARE) == ring_key([list(p) for p in SQUARE])
    assert ring_key(SQUARE) != ring_key(SQUARE[::-1])


def test_token_round_trip_and_tamper_checks():
    token = issue_token(SQUARE, SECRET, now=1000)
    assert check_token(token, SQUARE, SECRET, now=1500)
    assert not check_token(token, SQUARE, SECRET, now=1000 + 3601)           # expired
    assert not check_token(token, SQUARE[::-1], SECRET, now=1500)            # other area
    assert not check_token(token, SQUARE, b"other-secret", now=1500)         # forged
    assert not check_token("garbage", SQUARE, SECRET, now=1500)
    assert not check_token(None, SQUARE, SECRET, now=1500)


def test_rate_limiter_allows_a_few_runs_per_window_per_client():
    limiter = RateLimiter(max_runs=2, window_s=600)
    assert limiter.allow("1.2.3.4", now=0)
    assert limiter.allow("1.2.3.4", now=10)
    assert not limiter.allow("1.2.3.4", now=20)
    assert limiter.allow("5.6.7.8", now=20)          # other client unaffected
    assert limiter.allow("1.2.3.4", now=601)         # window passed


def test_bbox_with_margin_widens_the_ring_bounds():
    south, west, north, east = bbox_with_margin(SQUARE, 1000)
    assert south == pytest.approx(4.80 - 1000 / 110_574)
    assert north == pytest.approx(4.81 + 1000 / 110_574)
    assert west < 7.00 - 0.008 and east > 7.01 + 0.008
