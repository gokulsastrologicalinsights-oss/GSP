"""Focused tests for Instagram OAuth flow, account retrieval, and token security."""
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient

from main import app
from facebook_service import FacebookService
from instagram_service import InstagramService

client = TestClient(app)


def test_instagram_oauth_dialog_url_and_login_redirect():
    FacebookService.save_credentials("123456789012345", "super_secret_val")
    url = InstagramService.get_oauth_dialog_url()
    assert "instagram_basic" in url
    assert "instagram_manage_comments" in url
    assert "pages_show_list" in url
    assert "pages_read_engagement" in url
    assert "/api/instagram/callback" in url

    res = client.get("/api/instagram/login", follow_redirects=False)
    assert res.status_code in (302, 307)
    assert "facebook.com" in res.headers["location"]
    assert "instagram_manage_comments" in res.headers["location"]


def test_instagram_oauth_callback_cancel_and_missing_code():
    res_cancel = client.get(
        "/api/instagram/callback?error=access_denied&error_description=User+denied",
        follow_redirects=False,
    )
    assert res_cancel.status_code in (302, 307)
    assert "ig_error=" in res_cancel.headers["location"]

    res_no_code = client.get("/api/instagram/callback", follow_redirects=False)
    assert res_no_code.status_code in (302, 307)
    assert "ig_error=" in res_no_code.headers["location"]


def test_instagram_oauth_callback_account_retrieval_and_selection():
    FacebookService.save_credentials("123456789012345", "super_secret_val")

    mock_token_res = MagicMock()
    mock_token_res.json.return_value = {"access_token": "user_token_xyz"}

    mock_accounts_res = MagicMock()
    mock_accounts_res.json.return_value = {
        "data": [
            {
                "id": "page_111",
                "name": "Gokul Brand Page",
                "access_token": "page_token_secret_123",
                "instagram_business_account": {
                    "id": "17841400000123456",
                    "username": "gokul_brand",
                    "name": "Gokul Brand",
                },
            }
        ]
    }

    with patch("requests.get", side_effect=[mock_token_res, mock_accounts_res]):
        cb_res = client.get("/api/instagram/callback?code=auth_code_123", follow_redirects=False)

    assert cb_res.status_code in (302, 307)
    location = cb_res.headers["location"]
    assert "ig_session=ig_" in location
    session_id = location.split("ig_session=")[1]

    # Verify session-accounts never exposes access_token
    sess_res = client.get(f"/api/instagram/session-accounts?session_id={session_id}")
    assert sess_res.status_code == 200
    accounts = sess_res.json()["accounts"]
    assert len(accounts) == 1
    assert accounts[0]["id"] == "17841400000123456"
    assert "access_token" not in accounts[0]

    # Select account
    sel_res = client.post(
        "/api/instagram/select-account",
        json={"session_id": session_id, "account_id": "17841400000123456"},
    )
    assert sel_res.status_code == 200
    assert sel_res.json()["success"] is True

    # Verify status & token security
    status_res = client.get("/api/instagram/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["connected"] is True
    assert status_data["account"]["account_id"] == "17841400000123456"
    assert "access_token" not in status_data["account"]

    # Verify /api/instagram/config never exposes app_secret
    cfg_res = client.get("/api/instagram/config")
    assert cfg_res.status_code == 200
    assert "super_secret_val" not in cfg_res.text
    assert cfg_res.json()["configured"] is True

    # Verify /api/accounts never exposes access_token
    acc_res = client.get("/api/accounts")
    assert acc_res.status_code == 200
    assert "page_token_secret_123" not in acc_res.text


def test_instagram_account_retrieval_api_errors():
    mock_expired = MagicMock()
    mock_expired.json.return_value = {
        "error": {"code": 190, "error_subcode": 463, "message": "Session has expired"}
    }
    with patch("instagram_service.requests.get", return_value=mock_expired):
        res = InstagramService.get_instagram_accounts("expired_token")
    assert res["accounts"] == []
    assert "expired" in res["error"].lower()
    assert "190" in res["error"]

    mock_perm = MagicMock()
    mock_perm.json.return_value = {
        "error": {"code": 200, "message": "Permissions error"}
    }
    with patch("instagram_service.requests.get", return_value=mock_perm):
        res2 = InstagramService.get_instagram_accounts("limited_token")
    assert res2["accounts"] == []
    assert "permission" in res2["error"].lower()
