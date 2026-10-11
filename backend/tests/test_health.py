"""Tests for GET /api/health."""

from __future__ import annotations

from datetime import datetime


def test_health_ok(client) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "GuitarTab AI"
    assert body["environment"] == "test"
    assert body["version"]
    # `time` must be a real, parseable ISO-8601 timestamp.
    datetime.fromisoformat(body["time"].replace("Z", "+00:00"))


def test_health_reports_actual_time(client) -> None:
    first = client.get("/api/health").json()["time"]
    second = client.get("/api/health").json()["time"]
    assert first == second or abs(datetime.fromisoformat(second) - datetime.fromisoformat(first)).total_seconds() < 120