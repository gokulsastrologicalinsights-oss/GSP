import sqlite3
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import database
import main


def _make_mock_db(rows_by_platform):
    """Return a fake sqlite3-like connection that serves active account rows by platform."""

    class FakeConn:
        def execute(self, query, params=()):
            plat = params[0] if params else None
            row = rows_by_platform.get(plat)
            cur = MagicMock()
            cur.fetchone.return_value = row
            return cur

        def close(self):
            pass

    return FakeConn()


@pytest.fixture
def client():
    return TestClient(main.app)


def test_health_all_platforms_connected_and_authorized(client):
    rows = {
        "facebook": {
            "account_id": "fb_1",
            "account_name": "FB Page",
            "access_token": "fb_tok",
            "refresh_token": "",
            "token_expires_at": None,
            "is_active": 1,
        },
        "instagram": {
            "account_id": "ig_1",
            "account_name": "IG Pro",
            "access_token": "ig_tok",
            "refresh_token": "",
            "token_expires_at": None,
            "is_active": 1,
        },
        "youtube": {
            "account_id": "yt_1",
            "account_name": "YT Channel",
            "access_token": "yt_tok",
            "refresh_token": "yt_ref",
            "token_expires_at": None,
            "is_active": 1,
        },
    }
    ok_resp = MagicMock(status_code=200)
    with patch.object(database, "get_connection", side_effect=lambda: _make_mock_db(rows)), \
         patch.object(main.YouTubeService, "get_account_token_data", return_value={"access_token": "yt_tok", "refresh_token": "yt_ref"}), \
         patch("requests.get", return_value=ok_resp):
        res = client.get("/api/accounts/health")

    assert res.status_code == 200
    accounts = res.json()["accounts"]
    for plat in ("facebook", "instagram", "youtube"):
        assert accounts[plat]["account_connection"] == "Connected"
        assert accounts[plat]["authorization"] == "Valid"
        assert accounts[plat]["publishing_readiness"] == "Ready"
        assert accounts[plat]["last_checked"]


def test_health_individual_platform_and_token_expired(client):
    rows = {
        "facebook": {
            "account_id": "fb_1",
            "account_name": "FB Page",
            "access_token": "fb_tok",
            "refresh_token": "",
            "token_expires_at": "2020-01-01T00:00:00",
            "is_active": 1,
        }
    }
    with patch.object(database, "get_connection", side_effect=lambda: _make_mock_db(rows)):
        res = client.get("/api/accounts/health?platform=facebook")

    assert res.status_code == 200
    accounts = res.json()["accounts"]
    assert list(accounts.keys()) == ["facebook"]
    assert accounts["facebook"]["account_connection"] == "Connected"
    assert accounts["facebook"]["authorization"] == "Expired"
    assert accounts["facebook"]["publishing_readiness"] == "Blocked"
    assert "expired" in accounts["facebook"]["detail"].lower()
    assert accounts["facebook"]["last_checked"]


def test_health_permission_missing_403(client):
    rows = {
        "instagram": {
            "account_id": "ig_1",
            "account_name": "IG Pro",
            "access_token": "ig_tok",
            "refresh_token": "",
            "token_expires_at": None,
            "is_active": 1,
        }
    }
    resp_403 = MagicMock(status_code=403)
    with patch.object(database, "get_connection", side_effect=lambda: _make_mock_db(rows)), \
         patch("requests.get", return_value=resp_403):
        res = client.get("/api/accounts/health?platform=instagram")

    assert res.status_code == 200
    ig = res.json()["accounts"]["instagram"]
    assert ig["account_connection"] == "Connected"
    assert ig["authorization"] == "Expired"
    assert ig["publishing_readiness"] == "Blocked"
    assert "403" in ig["detail"]


def test_health_rate_limit_429_and_network_failure(client):
    rows = {
        "facebook": {
            "account_id": "fb_1",
            "account_name": "FB Page",
            "access_token": "fb_tok",
            "refresh_token": "",
            "token_expires_at": None,
            "is_active": 1,
        }
    }
    resp_429 = MagicMock(status_code=429)
    with patch.object(database, "get_connection", side_effect=lambda: _make_mock_db(rows)), \
         patch("requests.get", return_value=resp_429):
        res = client.get("/api/accounts/health?platform=facebook")

    assert res.status_code == 200
    fb = res.json()["accounts"]["facebook"]
    assert fb["account_connection"] == "Connected"
    assert fb["authorization"] == "Authorization Check Failed"
    assert fb["publishing_readiness"] == "Not Verified"
    assert "429" in fb["detail"]

    with patch.object(database, "get_connection", side_effect=lambda: _make_mock_db(rows)), \
         patch("requests.get", side_effect=ConnectionError("network down")):
        res_net = client.get("/api/accounts/health?platform=facebook")

    assert res_net.status_code == 200
    fb_net = res_net.json()["accounts"]["facebook"]
    assert fb_net["account_connection"] == "Connected"
    assert fb_net["authorization"] == "Authorization Check Failed"
    assert fb_net["publishing_readiness"] == "Not Verified"


def test_health_youtube_refresh_success(client):
    rows = {
        "youtube": {
            "account_id": "yt_1",
            "account_name": "YT Channel",
            "access_token": "yt_tok_new",
            "refresh_token": "yt_ref",
            "token_expires_at": None,
            "is_active": 1,
        }
    }
    ok_resp = MagicMock(status_code=200)
    with patch.object(main.YouTubeService, "get_connected_account", return_value={"account_id": "yt_1"}), \
         patch.object(main.YouTubeService, "refresh_access_token", return_value="yt_tok_new"), \
         patch.object(database, "get_connection", side_effect=lambda: _make_mock_db(rows)), \
         patch.object(main.YouTubeService, "get_account_token_data", return_value={"access_token": "yt_tok_new", "refresh_token": "yt_ref"}), \
         patch("requests.get", return_value=ok_resp):
        res = client.post("/api/accounts/health/refresh?platform=youtube")

    assert res.status_code == 200
    yt = res.json()["account"]
    assert yt["account_connection"] == "Connected"
    assert yt["authorization"] == "Valid"
    assert yt["publishing_readiness"] == "Ready"
    assert yt["can_refresh"] is True
