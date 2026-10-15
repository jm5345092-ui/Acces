"""GET /api/settings/server-info — where the server is actually hosted
(IP/region/country), used by the frontend to show a country flag next to
the server banner. Looked up via a third-party geolocation API, so these
tests stub `httpx.get` rather than hitting the real network."""
from __future__ import annotations

import app.api.settings as settings_api
from fastapi.testclient import TestClient

from app.main import app


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _reset_cache():
    settings_api._server_info_cache = None
    settings_api._server_info_cached_at = 0.0


def test_returns_country_and_ip_on_success(monkeypatch):
    _reset_cache()
    monkeypatch.setattr(
        settings_api.httpx,
        "get",
        lambda *a, **k: _FakeResponse(
            {
                "status": "success",
                "country": "Honduras",
                "countryCode": "HN",
                "regionName": "Francisco Morazán",
                "city": "Tegucigalpa",
                "isp": "Some ISP",
                "query": "1.2.3.4",
            }
        ),
    )
    with TestClient(app) as client:
        resp = client.get("/api/settings/server-info")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["country_code"] == "HN"
    assert body["ip"] == "1.2.3.4"


def test_falls_back_gracefully_when_lookup_fails(monkeypatch):
    _reset_cache()

    def _raise(*a, **k):
        raise RuntimeError("network unreachable")

    monkeypatch.setattr(settings_api.httpx, "get", _raise)
    with TestClient(app) as client:
        resp = client.get("/api/settings/server-info")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["country_code"] == ""


def test_result_is_cached_and_does_not_call_the_api_twice(monkeypatch):
    _reset_cache()
    calls = {"n": 0}

    def _get(*a, **k):
        calls["n"] += 1
        return _FakeResponse(
            {
                "status": "success",
                "country": "Panamá",
                "countryCode": "PA",
                "regionName": "Panamá",
                "city": "Panamá City",
                "isp": "Some ISP",
                "query": "5.6.7.8",
            }
        )

    monkeypatch.setattr(settings_api.httpx, "get", _get)
    with TestClient(app) as client:
        first = client.get("/api/settings/server-info")
        second = client.get("/api/settings/server-info")
    assert first.json() == second.json()
    assert calls["n"] == 1
