"""Checks for public drawn-area requests: the area itself, a signed run token, and a per-client limit.

The first step of a run (radar) is rate limited and issues a token for that exact area; the later
steps only run with a valid token, so one allowed run cannot be stretched into many.
"""

import base64
import hashlib
import hmac
import math
import time
from collections import defaultdict, deque

METRES_PER_DEG_LAT = 110_574.0
METRES_PER_DEG_LON_EQUATOR = 111_320.0
MIN_CORNERS = 3
MAX_CORNERS = 60
MAX_AREA_KM2 = 10.0
MIN_AREA_KM2 = 0.01
COORD_DECIMALS = 5                       # ~1 m: enough for a hand-drawn outline
RIVERS_BBOX = (4.15, 6.30, 5.80, 7.65)   # (south, west, north, east), generous around Rivers State
TOKEN_TTL_S = 3600


class AreaError(ValueError):
    """The drawn area cannot be analysed; the message is shown to the person who drew it."""


def area_km2(ring: list[list[float]]) -> float:
    lat0 = sum(p[0] for p in ring) / len(ring)
    kx = METRES_PER_DEG_LON_EQUATOR * math.cos(math.radians(lat0))
    total = 0.0
    for (lat_a, lon_a), (lat_b, lon_b) in zip(ring, ring[1:] + ring[:1]):
        total += lon_a * kx * lat_b * METRES_PER_DEG_LAT - lon_b * kx * lat_a * METRES_PER_DEG_LAT
    return abs(total) / 2 / 1e6


def _corner(point: object) -> list[float]:
    if not isinstance(point, (list, tuple)) or len(point) != 2:
        raise AreaError("Each corner must be a [latitude, longitude] pair.")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in point):
        raise AreaError("Corner coordinates must be numbers.")
    return [round(float(point[0]), COORD_DECIMALS), round(float(point[1]), COORD_DECIMALS)]


def validate_ring(ring: object) -> list[list[float]]:
    """Returns the ring as rounded [lat, lon] corners, or raises AreaError."""
    if not isinstance(ring, list):
        raise AreaError("The area must be a list of corners.")
    if len(ring) < MIN_CORNERS:
        raise AreaError(f"Draw at least {MIN_CORNERS} corners.")
    if len(ring) > MAX_CORNERS:
        raise AreaError(f"Draw at most {MAX_CORNERS} corners.")
    corners = [_corner(p) for p in ring]
    south, west, north, east = RIVERS_BBOX
    if not all(south <= lat <= north and west <= lon <= east for lat, lon in corners):
        raise AreaError("The full analysis covers Rivers State only.")
    size = area_km2(corners)
    if size > MAX_AREA_KM2:
        raise AreaError(f"Please draw a smaller area for the full analysis (up to {MAX_AREA_KM2:.0f} km²; "
                        f"this one is {size:.0f} km²).")
    if size < MIN_AREA_KM2:
        raise AreaError("The drawn area is too small to analyse.")
    return corners


def ring_key(ring: list[list[float]]) -> str:
    text = ";".join(f"{lat:.{COORD_DECIMALS}f},{lon:.{COORD_DECIMALS}f}" for lat, lon in ring)
    return hashlib.sha256(text.encode()).hexdigest()[:32]


def _signature(key: str, expires: int, secret: bytes) -> str:
    digest = hmac.new(secret, f"{key}.{expires}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def issue_token(ring: list[list[float]], secret: bytes, now: float | None = None) -> str:
    expires = int((time.time() if now is None else now) + TOKEN_TTL_S)
    return f"{expires}.{_signature(ring_key(ring), expires, secret)}"


def check_token(token: object, ring: list[list[float]], secret: bytes, now: float | None = None) -> bool:
    if not isinstance(token, str) or "." not in token:
        return False
    expires_text, signature = token.split(".", 1)
    if not expires_text.isdigit() or int(expires_text) < (time.time() if now is None else now):
        return False
    return hmac.compare_digest(signature, _signature(ring_key(ring), int(expires_text), secret))


class RateLimiter:
    """Runs per client per window, kept in this server instance's memory.

    A backstop only: instances come and go, so the Vercel firewall rule is the main limit.
    """

    def __init__(self, max_runs: int, window_s: float) -> None:
        self.max_runs = max_runs
        self.window_s = window_s
        self._runs: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, client: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        runs = self._runs[client]
        while runs and runs[0] <= now - self.window_s:
            runs.popleft()
        if len(runs) >= self.max_runs:
            return False
        runs.append(now)
        return True


def bbox_with_margin(ring: list[list[float]], margin_m: float) -> tuple[float, float, float, float]:
    """(south, west, north, east) of the ring, widened by margin_m on every side."""
    lats, lons = [p[0] for p in ring], [p[1] for p in ring]
    mid = (min(lats) + max(lats)) / 2
    d_lat = margin_m / METRES_PER_DEG_LAT
    d_lon = margin_m / (METRES_PER_DEG_LON_EQUATOR * math.cos(math.radians(mid)))
    return min(lats) - d_lat, min(lons) - d_lon, max(lats) + d_lat, max(lons) + d_lon
