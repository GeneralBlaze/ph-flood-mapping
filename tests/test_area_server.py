import json

import pytest

from analysis import area_server
from analysis.area_request import RateLimiter, issue_token

SQUARE = [[4.80, 7.00], [4.80, 7.01], [4.81, 7.01], [4.81, 7.00]]
SECRET = b"s3cret"


@pytest.fixture
def server(monkeypatch):
    calls = []

    def fake(name):
        def step(*args):
            calls.append((name, args))
            return {"step": name}
        return step

    monkeypatch.setattr(area_server, "STEPS", {
        "history": lambda body, ring: fake("history")(ring),
        "latest": lambda body, ring: fake("latest")(ring),
        "routes": lambda body, ring: fake("routes")(ring, body.get("recurrent"), body.get("latest")),
    })
    monkeypatch.setattr(area_server, "ensure_earth_engine", lambda: True)
    monkeypatch.setattr(area_server, "token_secret", lambda: SECRET)
    monkeypatch.setattr(area_server, "limiter", RateLimiter(max_runs=2, window_s=600))
    monkeypatch.setattr(area_server, "step_limiter", RateLimiter(max_runs=6, window_s=600))
    return calls


def post(payload, client="1.1.1.1"):
    status, body = area_server.handle(json.dumps(payload).encode(), client)
    return status, body


def test_history_runs_and_issues_a_token(server):
    status, body = post({"step": "history", "ring": SQUARE})
    assert status == 200
    assert body["step"] == "history"
    assert body["token"]
    assert server[0][0] == "history"


def test_later_steps_need_the_token_for_the_same_area(server):
    _, first = post({"step": "history", "ring": SQUARE})

    assert post({"step": "latest", "ring": SQUARE})[0] == 403
    assert post({"step": "latest", "ring": SQUARE, "token": "1.bad"})[0] == 403
    other = [[lat + 0.001, lon] for lat, lon in SQUARE]
    assert post({"step": "latest", "ring": other, "token": first["token"]})[0] == 403

    status, body = post({"step": "routes", "ring": SQUARE, "token": first["token"], "recurrent": [], "latest": []})
    assert status == 200 and body["step"] == "routes"


def test_runs_are_rate_limited_per_client(server):
    assert post({"step": "history", "ring": SQUARE})[0] == 200
    assert post({"step": "history", "ring": SQUARE})[0] == 200
    status, body = post({"step": "history", "ring": SQUARE})
    assert status == 429
    assert "minutes" in body["error"]
    assert post({"step": "history", "ring": SQUARE}, client="2.2.2.2")[0] == 200


@pytest.mark.parametrize("raw, status, text", [
    (b"not json", 400, "request"),
    (json.dumps({"step": "nope", "ring": SQUARE}).encode(), 400, "step"),
    (json.dumps({"step": "history", "ring": [[6.5, 3.3], [6.5, 3.31], [6.51, 3.31]]}).encode(), 400, "Rivers State"),
    (json.dumps(["list"]).encode(), 400, "request"),
])
def test_bad_requests_get_a_clear_message(server, raw, status, text):
    code, body = area_server.handle(raw, "1.1.1.1")
    assert code == status
    assert text in body["error"]


def test_switched_off_without_earth_engine_credentials(server, monkeypatch):
    monkeypatch.setattr(area_server, "ensure_earth_engine", lambda: False)
    status, body = post({"step": "history", "ring": SQUARE})
    assert status == 503
    assert "not switched on" in body["error"]


def test_step_failures_are_reported_without_internal_detail(server, monkeypatch):
    def broken(body, ring):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(area_server, "STEPS", {"history": broken})
    status, body = post({"step": "history", "ring": SQUARE})
    assert status == 502
    assert "secret" not in body["error"]
    assert "try again" in body["error"]


def test_token_secret_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("AREA_TOKEN_SECRET", "abc")
    monkeypatch.delenv("EE_SERVICE_ACCOUNT_KEY", raising=False)
    assert area_server.token_secret() == b"abc"
    monkeypatch.delenv("AREA_TOKEN_SECRET")
    monkeypatch.setenv("EE_SERVICE_ACCOUNT_KEY", '{"private_key": "x"}')
    derived = area_server.token_secret()
    assert len(derived) == 32 and derived != b"abc"
    token = issue_token(SQUARE, derived)
    assert token


def test_steps_are_capped_too_so_a_token_cannot_be_replayed(server):
    _, first = post({"step": "history", "ring": SQUARE})
    codes = [post({"step": "latest", "ring": SQUARE, "token": first["token"]})[0] for _ in range(6)]
    assert codes == [200] * 5 + [429]


def test_status_reports_whether_the_analysis_is_switched_on(monkeypatch):
    monkeypatch.delenv("EE_SERVICE_ACCOUNT_KEY", raising=False)
    monkeypatch.delenv("AREA_LOCAL_DEV", raising=False)
    assert area_server.status() == {"enabled": False}
    monkeypatch.setenv("EE_SERVICE_ACCOUNT_KEY", "{}")
    assert area_server.status() == {"enabled": True}


FEDERATION = {
    "GCP_PROJECT_NUMBER": "123456789",
    "GCP_SERVICE_ACCOUNT_EMAIL": "ph-flood-server@ph-flood-mapping.iam.gserviceaccount.com",
    "GCP_WORKLOAD_IDENTITY_POOL_ID": "vercel",
    "GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID": "vercel",
    "AREA_TOKEN_SECRET": "run-token-secret",
}


def test_keyless_setup_switches_the_analysis_on(monkeypatch):
    monkeypatch.delenv("EE_SERVICE_ACCOUNT_KEY", raising=False)
    monkeypatch.delenv("AREA_LOCAL_DEV", raising=False)
    for name, value in FEDERATION.items():
        monkeypatch.setenv(name, value)
    assert area_server.status() == {"enabled": True}
    monkeypatch.delenv("AREA_TOKEN_SECRET")  # run tokens must be signed with a real secret
    assert area_server.status() == {"enabled": False}


def test_federated_credentials_exchange_the_latest_vercel_token(monkeypatch):
    for name, value in FEDERATION.items():
        monkeypatch.setenv(name, value)
    credentials = area_server.federated_credentials()
    assert credentials._audience == (
        "//iam.googleapis.com/projects/123456789/locations/global/workloadIdentityPools/vercel/providers/vercel")
    assert credentials.service_account_email == FEDERATION["GCP_SERVICE_ACCOUNT_EMAIL"]

    area_server.remember_oidc_token("header-token")
    assert area_server.VercelTokenSupplier().get_subject_token(None, None) == "header-token"


def test_token_supplier_fails_clearly_without_a_token(monkeypatch):
    from google.auth.exceptions import RefreshError

    monkeypatch.setattr(area_server, "_oidc_token", None)
    monkeypatch.delenv("VERCEL_OIDC_TOKEN", raising=False)
    import pytest as _pytest
    with _pytest.raises(RefreshError):
        area_server.VercelTokenSupplier().get_subject_token(None, None)
