"""Request handling for the public full-area analysis: checks, run token, rate limit, Earth Engine login.

`handle(body, client)` returns (HTTP status, JSON-able dict). The Vercel function (api/area.py) and the
local dev server (analysis.dev_server) both call it.
"""

import hashlib
import json
import logging
import os
from typing import Any, Callable

import ee

from analysis import config
from analysis.area_pass import run_buildings, run_history, run_latest, run_routes, run_streets
from analysis.area_request import AreaError, RateLimiter, check_token, issue_token, validate_ring

log = logging.getLogger(__name__)

KEY_ENV = "EE_SERVICE_ACCOUNT_KEY"     # the service account's JSON key, stored as a Vercel secret
SECRET_ENV = "AREA_TOKEN_SECRET"       # optional; otherwise derived from the key
LOCAL_DEV_ENV = "AREA_LOCAL_DEV"       # "1": use this computer's own Earth Engine login
RUNS_PER_WINDOW = 3
STEPS_PER_WINDOW = 30                  # a run is 5 steps; this stops one token being replayed endlessly
WINDOW_S = 600
EE_DEADLINE_MS = 120_000
MAX_BODY_BYTES = 2_000_000
FIRST_STEP = "history"

STEPS: dict[str, Callable[[dict[str, Any], list[list[float]]], dict[str, Any]]] = {
    "history": lambda body, ring: run_history(ring),
    "latest": lambda body, ring: run_latest(ring),
    "routes": lambda body, ring: run_routes(ring, body.get("recurrent"), body.get("latest")),
    "buildings": lambda body, ring: run_buildings(ring, body.get("sites"), body.get("routed")),
    "streets": lambda body, ring: run_streets(ring, body.get("sites"), body.get("routed")),
}

limiter = RateLimiter(RUNS_PER_WINDOW, WINDOW_S)
step_limiter = RateLimiter(STEPS_PER_WINDOW, WINDOW_S)
_ee_ready = False


def ensure_earth_engine() -> bool:
    """Log in to Earth Engine once per server instance; False when no credentials are configured."""
    global _ee_ready
    if _ee_ready:
        return True
    key = os.environ.get(KEY_ENV)
    if key:
        info = json.loads(key)
        credentials = ee.ServiceAccountCredentials(info["client_email"], key_data=key)
        ee.Initialize(credentials, project=info.get("project_id", config.EE_PROJECT))
    elif os.environ.get(LOCAL_DEV_ENV) == "1":
        ee.Initialize(project=config.EE_PROJECT)
    else:
        return False
    ee.data.setDeadline(EE_DEADLINE_MS)
    _ee_ready = True
    return True


def status() -> dict[str, Any]:
    """Whether the full analysis is configured on this server (the page hides it when not)."""
    return {"enabled": bool(os.environ.get(KEY_ENV)) or os.environ.get(LOCAL_DEV_ENV) == "1"}


def token_secret() -> bytes:
    if os.environ.get(SECRET_ENV):
        return os.environ[SECRET_ENV].encode()
    key = os.environ.get(KEY_ENV)
    if key:
        return hashlib.sha256(b"area-token:" + key.encode()).digest()
    return b"local-development-only"


def _error(status: int, message: str) -> tuple[int, dict[str, Any]]:
    return status, {"error": message}


def handle(body: bytes, client: str) -> tuple[int, dict[str, Any]]:
    try:
        request = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return _error(400, "Could not read the request.")
    if not isinstance(request, dict):
        return _error(400, "Could not read the request.")
    step = request.get("step")
    if step not in STEPS:
        return _error(400, "Unknown analysis step.")
    try:
        ring = validate_ring(request.get("ring"))
    except AreaError as exc:
        return _error(400, str(exc))
    busy = f"Too many full analyses from this connection; please try again in {WINDOW_S // 60} minutes."
    if not step_limiter.allow(client):
        return _error(429, busy)
    secret = token_secret()
    if step == FIRST_STEP:
        if not limiter.allow(client):
            return _error(429, busy)
    elif not check_token(request.get("token"), ring, secret):
        return _error(403, "This analysis has expired or does not match the drawn area; please run it again.")
    if not ensure_earth_engine():
        return _error(503, "The full analysis is not switched on yet.")
    try:
        result = STEPS[step](request, ring)
    except AreaError as exc:
        return _error(400, str(exc))
    except Exception:  # noqa: BLE001 — anything from Earth Engine/Overpass; details go to the log only
        log.exception("Step %s failed", step)
        return _error(502, "The analysis service is busy or failed; please try again in a few minutes.")
    if step == FIRST_STEP:
        result = {**result, "token": issue_token(ring, secret)}
    return 200, result
