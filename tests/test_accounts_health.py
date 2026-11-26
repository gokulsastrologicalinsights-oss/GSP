"""Tests for consolidated OAuth and publishing readiness health check."""
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import database
import main


def _insert_account(platform: str, account_id: str, account_name: str, access_token: str = "tok_secret_123"):
    conn = database.get_connection()
    try:
        conn.execute(
            """
            INSERT INTO accounts (platform, account_id, account_name, access_token, is_active)
            VALUES (?, ?, ?, ?, 1)
            """,
            (platform, account_id, account_name, access_token),
        )
        conn.commit()
    finally:
        conn.close()


def test_health_check_all_platforms_valid_and_no_tokens_exposed():
    _insert_account("facebook", "fb_1", "FB Page", "fb_secret_tok")
    _insert_account("instagram", "ig_1", "IG Pro", "ig_secret_tok")
    _insert_account("youtube", "yt_1", "YT Chan", "yt_secret_tok")

    ok_resp = MagicMock(status_code=200)
    with patch("requests.get", return_value=ok_resp):
        with TestClient(main.app) as client:
            res = client.get("/api/accounts/health")
            assert res.status_code == 200
            body = res.json()["accounts"]

    raw_text = str(body)
    assert "fb_secret_tok" not in raw_text
    assert "ig_secret_tok" not in raw_text
    assert "yt_secret_tok" not in raw_text

    for plat in ("facebook", "instagram", "youtube"):
        assert body[plat]["account_connection"] == "Connected"
        assert body[plat]["authorization"] == "Valid"
        assert body[plat]["publishing_readiness"] == "Ready"
        assert body[plat]["last_checked"]


def test_health_check_missing_and_expired_tokens_and_disconnected():
    _insert_account("facebook", "fb_missing", "FB Missing", "")
    _insert_account("instagram", "ig_expired", "IG Expired", "ig_old_tok")

    unauth_resp = MagicMock(status_code=401)
    with patch("requests.get", return_value=unauth_resp):
        with TestClient(main.app) as client:
            res = client.get("/api/accounts/health")
            assert res.status_code == 200
            body = res.json()["accounts"]

    assert body["facebook"]["account_connection"] == "Connected"
    assert body["facebook"]["authorization"] == "Expired"
    assert body["facebook"]["publishing_readiness"] == "Blocked"

    assert body["instagram"]["account_connection"] == "Connected"
    assert body["instagram"]["authorization"] == "Expired"
    assert body["instagram"]["publishing_readiness"] == "Blocked"

    assert body["youtube"]["account_connection"] == "Disconnected"
    assert body["youtube"]["authorization"] == "Unknown"
    assert body["youtube"]["publishing_readiness"] == "Blocked"


def test_health_check_api_failure_and_refresh_failure_preserve_account():
    _insert_account("youtube", "yt_err", "YT Err", "yt_tok")

    with patch("requests.get", side_effect=RuntimeError("network down")):
        with TestClient(main.app) as client:
            res = client.get("/api/accounts/health?platform=youtube")
            assert res.status_code == 200
            yt = res.json()["accounts"]["youtube"]
            assert yt["account_connection"] == "Connected"
            assert yt["authorization"] == "Authorization Check Failed"
            assert yt["publishing_readiness"] == "Not Verified"

            with patch.object(main.YouTubeService, "refresh_access_token", side_effect=RuntimeError("refresh failed")):
                ref_res = client.post("/api/accounts/health/refresh?platform=youtube")
                assert ref_res.status_code == 400
