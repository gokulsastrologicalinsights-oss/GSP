"""Focused tests for YouTube OAuth 2.0 flow, channel retrieval, token refresh, and token security."""
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient

import database
from main import app
from youtube_service import YouTubeService

client = TestClient(app)


def test_youtube_oauth_dialog_url_and_login_redirect():
    YouTubeService.save_credentials("google_client_123.apps.googleusercontent.com", "super_secret_google_key")
    url = YouTubeService.get_oauth_dialog_url()
    assert "youtube.force-ssl" in url
    assert "accounts.google.com" in url
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    assert "/api/youtube/callback" in url

    res = client.get("/api/youtube/login", follow_redirects=False)
    assert res.status_code in (302, 307)
    assert "accounts.google.com" in res.headers["location"]
    assert "youtube.force-ssl" in res.headers["location"]


def test_youtube_oauth_callback_cancel_and_missing_code():
    res_cancel = client.get(
        "/api/youtube/callback?error=access_denied&error_description=User+denied",
        follow_redirects=False,
    )
    assert res_cancel.status_code in (302, 307)
    assert "yt_error=" in res_cancel.headers["location"]

    res_no_code = client.get("/api/youtube/callback", follow_redirects=False)
    assert res_no_code.status_code in (302, 307)
    assert "yt_error=" in res_no_code.headers["location"]


def test_youtube_oauth_callback_channel_retrieval_and_selection():
    YouTubeService.save_credentials("google_client_123.apps.googleusercontent.com", "super_secret_google_key")

    mock_token_res = MagicMock()
    mock_token_res.json.return_value = {
        "access_token": "ya29.google_access_token_xyz",
        "refresh_token": "1//google_refresh_token_abc",
        "expires_in": 3600,
    }

    mock_channel_res = MagicMock()
    mock_channel_res.json.return_value = {
        "items": [
            {
                "id": "UC_gokul_channel_123",
                "snippet": {
                    "title": "Gokul Tech Channel",
                    "customUrl": "@gokultech",
                },
                "contentDetails": {
                    "relatedPlaylists": {
                        "uploads": "UU_gokul_channel_123",
                    }
                },
            }
        ]
    }

    with patch("requests.post", return_value=mock_token_res), \
         patch("requests.get", return_value=mock_channel_res):
        cb_res = client.get("/api/youtube/callback?code=auth_code_yt_123", follow_redirects=False)

    assert cb_res.status_code in (302, 307)
    location = cb_res.headers["location"]
    assert "yt_session=yt_" in location
    session_id = location.split("yt_session=")[1]

    # Verify session-channels never exposes access_token or refresh_token
    sess_res = client.get(f"/api/youtube/session-channels?session_id={session_id}")
    assert sess_res.status_code == 200
    channels = sess_res.json()["channels"]
    assert len(channels) == 1
    assert channels[0]["id"] == "UC_gokul_channel_123"
    assert channels[0]["title"] == "Gokul Tech Channel"
    assert "access_token" not in channels[0]
    assert "refresh_token" not in channels[0]

    # Select channel
    sel_res = client.post(
        "/api/youtube/select-channel",
        json={"session_id": session_id, "channel_id": "UC_gokul_channel_123"},
    )
    assert sel_res.status_code == 200
    assert sel_res.json()["success"] is True

    # Verify status & token security (tokens NEVER exposed)
    status_res = client.get("/api/youtube/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["connected"] is True
    assert status_data["account"]["account_id"] == "UC_gokul_channel_123"
    assert status_data["account"]["account_name"] == "Gokul Tech Channel"
    assert "access_token" not in status_data["account"]
    assert "refresh_token" not in status_data["account"]

    # Verify /api/youtube/config never exposes client secret
    cfg_res = client.get("/api/youtube/config")
    assert cfg_res.status_code == 200
    assert "super_secret_google_key" not in cfg_res.text
    assert cfg_res.json()["configured"] is True

    # Verify /api/accounts never exposes access_token or refresh_token
    acc_res = client.get("/api/accounts")
    assert acc_res.status_code == 200
    assert "ya29.google_access_token_xyz" not in acc_res.text
    assert "1//google_refresh_token_abc" not in acc_res.text


def test_youtube_token_refresh():
    YouTubeService.save_credentials("google_client_123.apps.googleusercontent.com", "super_secret_google_key")
    YouTubeService.connect_account(
        account_id="UC_gokul_channel_123",
        account_name="Gokul Tech Channel",
        access_token="expired_token_111",
        refresh_token="valid_refresh_token_222",
    )

    mock_refresh_res = MagicMock()
    mock_refresh_res.json.return_value = {
        "access_token": "ya29.newly_refreshed_access_token_333",
        "expires_in": 3600,
        "token_type": "Bearer",
    }

    with patch("requests.post", return_value=mock_refresh_res):
        ref_res = YouTubeService.refresh_access_token("valid_refresh_token_222")

    assert "access_token" in ref_res
    assert ref_res["access_token"] == "ya29.newly_refreshed_access_token_333"

    # Update account token
    YouTubeService.update_account_access_token("UC_gokul_channel_123", ref_res["access_token"])
    updated_data = YouTubeService.get_account_token_data("UC_gokul_channel_123")
    assert updated_data["access_token"] == "ya29.newly_refreshed_access_token_333"
    assert updated_data["refresh_token"] == "valid_refresh_token_222"


def test_youtube_disconnect():
    YouTubeService.connect_account(
        account_id="UC_gokul_channel_123",
        account_name="Gokul Tech Channel",
        access_token="token_xyz",
    )
    status_before = client.get("/api/youtube/status").json()
    assert status_before["connected"] is True

    disc_res = client.post("/api/youtube/disconnect")
    assert disc_res.status_code == 200
    assert disc_res.json()["success"] is True

    status_after = client.get("/api/youtube/status").json()
    assert status_after["connected"] is False


def test_youtube_connect_preserves_existing_refresh_token_when_omitted():
    YouTubeService.connect_account(
        account_id="UC_gokul_channel_123",
        account_name="Gokul Tech Channel",
        access_token="access_1",
        refresh_token="refresh_keep_me",
        uploads_playlist_id="UU_123",
    )
    # Reconnect without refresh_token (e.g. Google omitted it on re-consent)
    YouTubeService.connect_account(
        account_id="UC_gokul_channel_123",
        account_name="Gokul Tech Channel",
        access_token="access_2",
        refresh_token="",
    )
    stored = YouTubeService.get_account_token_data("UC_gokul_channel_123")
    assert stored["access_token"] == "access_2"
    assert stored["refresh_token"] == "refresh_keep_me"
    assert stored["uploads_playlist_id"] == "UU_123"


def test_youtube_oauth_callback_csrf_state_mismatch_and_failure():
    import database
    database.set_setting("yt_oauth_csrf_state", "expected_state_abc")

    bad_state_res = client.get("/api/youtube/callback?code=some_code&state=wrong_state", follow_redirects=False)
    assert bad_state_res.status_code in (302, 307)
    assert "Invalid+OAuth+state" in bad_state_res.headers["location"]

    with patch("youtube_service.YouTubeService.exchange_code_for_token", return_value={"error": {"message": "bad_code"}}):
        fail_res = client.get("/api/youtube/callback?code=bad_code&state=expected_state_abc", follow_redirects=False)
        assert fail_res.status_code in (302, 307)
        assert "bad_code" in fail_res.headers["location"]


def test_youtube_oauth_callback_without_refresh_token_succeeds():
    import database
    database.set_setting("yt_oauth_csrf_state", "state_no_ref")
    YouTubeService.save_credentials("google_client_123.apps.googleusercontent.com", "super_secret_google_key")

    mock_token_res = MagicMock()
    mock_token_res.json.return_value = {"access_token": "ya29.only_access", "expires_in": 3600}
    mock_channel_res = MagicMock()
    mock_channel_res.json.return_value = {
        "items": [{"id": "UC_no_ref", "snippet": {"title": "NoRef Channel"}, "contentDetails": {"relatedPlaylists": {"uploads": "UU_no_ref"}}}]
    }
    with patch("requests.post", return_value=mock_token_res), patch("requests.get", return_value=mock_channel_res):
        cb_res = client.get("/api/youtube/callback?code=ok_code&state=state_no_ref", follow_redirects=False)
    assert cb_res.status_code in (302, 307)
    assert "yt_session=yt_" in cb_res.headers["location"]
