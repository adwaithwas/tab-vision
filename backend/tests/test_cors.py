"""Tests for CORS behaviour in local development."""

from __future__ import annotations


def test_allowed_origin_receives_cors_headers(client) -> None:
    resp = client.get(
        "/api/health",
        headers={"Origin": "http://localhost:5173"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_unknown_origin_not_echoed(client) -> None:
    resp = client.get(
        "/api/health",
        headers={"Origin": "http://evil.example.com"},
    )
    assert resp.status_code == 200
    allow = resp.headers.get("access-control-allow-origin")
    assert allow != "http://evil.example.com"
    assert allow is None or allow == "http://localhost:5173"


def test_options_preflight_allowed(client) -> None:
    resp = client.options(
        "/api/videos/upload",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"