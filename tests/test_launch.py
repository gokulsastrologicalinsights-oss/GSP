"""Focused verification test for Phase 1 application launch."""
import pytest
from starlette.testclient import TestClient
from main import app

client = TestClient(app)

def test_home_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "Gokul Social Publisher" in response.text
    assert "Dashboard" in response.text

def test_status_endpoint():
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "stats" in data
    assert "auto_reply_enabled" in data

def test_toggle_setting():
    # Toggle setting
    response = client.post("/api/settings", json={"key": "auto_reply_enabled", "value": "true"})
    assert response.status_code == 200
    
    # Check update reflected in status
    response = client.get("/api/status")
    assert response.json()["auto_reply_enabled"] is True

    # Revert
    client.post("/api/settings", json={"key": "auto_reply_enabled", "value": "false"})
    response = client.get("/api/status")
    assert response.json()["auto_reply_enabled"] is False

def test_accounts_and_activities_endpoints():
    res_accounts = client.get("/api/accounts")
    assert res_accounts.status_code == 200
    assert "accounts" in res_accounts.json()

    res_activities = client.get("/api/activities")
    assert res_activities.status_code == 200
    assert "activities" in res_activities.json()
