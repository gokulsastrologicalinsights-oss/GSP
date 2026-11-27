"""Tests for 30-minute automatic comment sync & account-wise smart auto-reply."""
import os
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

import database
import sync_service


@pytest.fixture
def disposable_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_sync.db")
    monkeypatch.setenv("GSP_DB_PATH", db_path)
    database.init_db()
    conn = database.get_connection()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('global_kill_switch', 'true')")
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('safe_test_mode', 'false')")
    conn.execute(
        "INSERT INTO accounts (platform, account_id, account_name, access_token, is_active) VALUES (?, ?, ?, ?, 1)",
        ("facebook", "fb_1", "FB Page A", "tok_fb"),
    )
    conn.execute(
        "INSERT INTO accounts (platform, account_id, account_name, access_token, is_active) VALUES (?, ?, ?, ?, 1)",
        ("instagram", "ig_1", "IG Account A", "tok_ig"),
    )
    conn.execute(
        "INSERT INTO accounts (platform, account_id, account_name, access_token, is_active) VALUES (?, ?, ?, ?, 1)",
        ("youtube", "yt_1", "YT Channel A", "tok_yt"),
    )
    conn.commit()
    conn.close()
    return db_path


def test_default_manual_approval_and_30min_interval(disposable_db):
    states = sync_service.ensure_account_sync_states()
    assert len(states) == 3
    for st in states:
        assert st["reply_mode"] == "MANUAL_APPROVAL"
        assert st["auto_sync_enabled"] == 1
        assert st["sync_interval_minutes"] == 30


def test_account_isolation_reply_mode(disposable_db):
    sync_service.ensure_account_sync_states()
    updated = sync_service.update_account_sync_settings("facebook", "fb_1", reply_mode="AUTOMATIC_REPLY")
    assert updated["reply_mode"] == "AUTOMATIC_REPLY"

    states = { (s["platform"], s["account_id"]): s for s in sync_service.get_account_sync_states() }
    assert states[("facebook", "fb_1")]["reply_mode"] == "AUTOMATIC_REPLY"
    assert states[("instagram", "ig_1")]["reply_mode"] == "MANUAL_APPROVAL"
    assert states[("youtube", "yt_1")]["reply_mode"] == "MANUAL_APPROVAL"

    sync_service.update_account_sync_settings("instagram", "ig_1", reply_mode="DISABLED")
    states = { (s["platform"], s["account_id"]): s for s in sync_service.get_account_sync_states() }
    assert states[("instagram", "ig_1")]["reply_mode"] == "DISABLED"
    assert states[("facebook", "fb_1")]["reply_mode"] == "AUTOMATIC_REPLY"


def test_atomic_claim_prevents_overlapping_sync(disposable_db):
    sync_service.ensure_account_sync_states()
    assert sync_service.claim_account_sync("youtube", "yt_1") is True
    assert sync_service.claim_account_sync("youtube", "yt_1") is False
    sync_service.release_account_sync("youtube", "yt_1", sync_type="manual", success=True)
    assert sync_service.claim_account_sync("youtube", "yt_1") is True


def test_sync_cursor_persistence_and_platform_isolation(disposable_db):
    sync_service.ensure_account_sync_states()

    def fake_dispatch(platform):
        if platform == "facebook":
            return {"success": True, "fetched": 5, "new": 2, "cursor": "fb_cursor_2"}
        if platform == "instagram":
            raise ConnectionError("Network unreachable")
        return {"success": True, "fetched": 3, "new": 1, "cursor": "yt_cursor_1"}

    with mock.patch("sync_service._dispatch_platform_sync", side_effect=fake_dispatch):
        results = sync_service.run_due_syncs()

    assert len(results) == 3
    states = { (s["platform"], s["account_id"]): s for s in sync_service.get_account_sync_states() }
    assert states[("facebook", "fb_1")]["cursor"] == "fb_cursor_2"
    assert states[("facebook", "fb_1")]["comments_processed"] == 2
    assert states[("instagram", "ig_1")]["failed_sync_count"] == 1
    assert states[("instagram", "ig_1")]["backoff_until"] is not None
    assert states[("youtube", "yt_1")]["cursor"] == "yt_cursor_1"


def test_startup_recovery_catches_up_overdue_accounts(disposable_db):
    sync_service.ensure_account_sync_states()
    past = (datetime.now(timezone.utc) - timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = database.get_connection()
    conn.execute("UPDATE account_sync_state SET next_sync_at = ?, is_syncing = 1", (past,))
    conn.commit()
    conn.close()

    with mock.patch("sync_service._dispatch_platform_sync", return_value={"success": True, "fetched": 1, "new": 1}):
        res = sync_service.run_startup_sync_recovery()

    assert len(res) == 3
    assert all(r.get("success") for r in res)


def test_language_intent_and_auto_reply_eligibility():
    lang, intent, conf = sync_service.classify_comment_intent("Super video, thank you!")
    assert intent == "Appreciation"
    ok, _ = sync_service.is_eligible_for_auto_reply(intent, conf, "Super video, thank you!")
    assert ok is True

    for risky in [
        "I will destroy you",
        "You are a fraud and idiot",
        "Worst service, I want a refund complaint",
        "Call me at 9876543210",
    ]:
        _, r_intent, r_conf = sync_service.classify_comment_intent(risky)
        r_ok, _ = sync_service.is_eligible_for_auto_reply(r_intent, r_conf, risky)
        assert r_ok is False
