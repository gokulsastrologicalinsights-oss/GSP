"""Focused tests for Facebook OAuth configuration, login flow, and Page selection."""
import json
import pytest
from starlette.testclient import TestClient
from main import app
import database
from facebook_service import FacebookService

client = TestClient(app, follow_redirects=False)

@pytest.fixture(autouse=True)
def setup_db():
    database.init_db()
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM activities")
    c.execute("DELETE FROM accounts")
    c.execute("DELETE FROM oauth_sessions")
    conn.commit()
    conn.close()

def test_meta_app_config_endpoint():
    # Save credentials via API
    res = client.post("/api/facebook/config", json={
        "app_id": "123456789012345",
        "app_secret": "my_super_secret_key_999",
        "redirect_uri": "http://localhost:8088/api/facebook/callback"
    })
    assert res.status_code == 200
    assert res.json()["success"] is True

    # Check config status
    get_res = client.get("/api/facebook/config")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["configured"] is True
    assert data["app_id_configured"] is True
    assert data["app_secret_configured"] is True
    # STRICT SECURITY: App Secret must NEVER be present anywhere in the response
    assert "my_super_secret_key_999" not in str(data)
    assert "app_secret" not in data

def test_facebook_login_redirect_url_and_scopes():
    FacebookService.save_credentials("123456789012345", "my_super_secret_key_999")
    
    # Request login redirect
    res = client.get("/api/facebook/login")
    assert res.status_code == 307
    redirect_url = res.headers["location"]
    
    # Verify Meta Graph OAuth dialog format
    assert "https://www.facebook.com/v19.0/dialog/oauth" in redirect_url
    assert "client_id=123456789012345" in redirect_url
    assert "scope=pages_show_list%2Cpages_read_engagement%2Cpages_manage_posts" in redirect_url or \
           "scope=pages_show_list,pages_read_engagement,pages_manage_posts" in redirect_url
    assert "response_type=code" in redirect_url

def test_facebook_callback_error_handling():
    # Simulate user cancelling or denying permissions
    res = client.get("/api/facebook/callback?error=access_denied&error_description=Permissions+were+denied+by+user")
    assert res.status_code == 307
    loc = res.headers["location"]
    assert "fb_error=" in loc
    assert "Permissions" in loc

def test_oauth_session_and_page_selection():
    # Simulate retrieved authorized pages from Meta /me/accounts
    mock_pages = [
        {
            "id": "page_fb_101",
            "name": "Gokul Tech Media",
            "access_token": "EAAB_SECRET_PAGE_ACCESS_TOKEN_1",
            "category": "Media"
        },
        {
            "id": "page_fb_102",
            "name": "Gokul Personal Blog",
            "access_token": "EAAB_SECRET_PAGE_ACCESS_TOKEN_2",
            "category": "Blog"
        }
    ]
    session_id = "test_session_xyz"
    database.save_oauth_session(session_id, json.dumps(mock_pages))

    # 1. Fetch authorized pages for selection modal
    res = client.get(f"/api/facebook/session-pages?session_id={session_id}")
    assert res.status_code == 200
    pages = res.json()["pages"]
    assert len(pages) == 2
    assert pages[0]["id"] == "page_fb_101"
    assert pages[0]["name"] == "Gokul Tech Media"
    # STRICT SECURITY: Access tokens must be stripped from public session-pages response
    for p in pages:
        assert "access_token" not in p

    # 2. User selects "Gokul Tech Media"
    select_res = client.post("/api/facebook/select-page", json={
        "session_id": session_id,
        "page_id": "page_fb_101"
    })
    assert select_res.status_code == 200
    assert select_res.json()["success"] is True

    # 3. Verify session was cleaned up
    assert database.get_oauth_session(session_id) is None

    # 4. Verify account is connected in database and visible in status
    status_res = client.get("/api/facebook/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["connected"] is True
    assert status_data["page"]["account_name"] == "Gokul Tech Media"
    assert status_data["page"]["account_id"] == "page_fb_101"
    assert "access_token" not in status_data["page"]
