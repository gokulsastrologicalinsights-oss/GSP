"""Focused tests for Priority 2C: Approval Workflow & Publishing Validation."""
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import database
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_state():
    """Isolate database state for each Priority 2C test."""
    database.init_db()
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM approval_queue")
    c.execute("DELETE FROM approval_activity_log")
    c.execute("DELETE FROM activities")
    c.execute("DELETE FROM reply_rate_log")
    c.execute("DELETE FROM accounts")
    conn.commit()
    conn.close()

    database.set_setting("global_kill_switch", "false")
    database.set_setting("safe_test_mode", "true")
    database.set_setting("auto_reply_enabled", "true")
    database.set_setting("ig_auto_reply_enabled", "true")
    database.set_setting("yt_auto_reply_enabled", "true")
    yield


def _seed_account(platform="facebook", account_id="page_1", token="tok_123", active=1):
    conn = database.get_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO accounts (platform, account_id, account_name, access_token, is_active)
        VALUES (?, ?, ?, ?, ?)
        """,
        (platform, account_id, f"{platform}_acct", token, active),
    )
    conn.commit()
    conn.close()


def _enqueue(platform="facebook", account_id="page_1", comment_id="c_1", commenter="Arun"):
    return database.enqueue_approval_item(
        platform=platform,
        account_id=account_id,
        comment_id=comment_id,
        commenter_name=commenter,
        comment_text="What is the fee?",
        detected_language="en",
        detected_intent="fee_enquiry",
        suggested_reply="Please DM us for fee details.",
        review_reason="consultation_fee_enquiry",
    )


def test_1_pending_to_approved():
    qid = _enqueue()
    resp = client.post(f"/api/approval-queue/{qid}/approve")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["published"] is False
    assert data["item"]["status"] == "approved"
    assert data["item"]["approved_at"] is not None


def test_2_pending_to_rejected():
    qid = _enqueue()
    resp = client.post(f"/api/approval-queue/{qid}/reject", json={"reason": "Out of scope"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["item"]["status"] == "rejected"
    assert data["item"]["rejected_at"] is not None
    assert data["item"]["review_reason"] == "Out of scope"


def test_3_edited_reply_persistence():
    qid = _enqueue()
    resp = client.put(
        f"/api/approval-queue/{qid}/edit",
        json={"edited_reply": "Custom edited reply"},
    )
    assert resp.status_code == 200
    fetched = database.get_approval_queue_item(qid)
    assert fetched["edited_reply"] == "Custom edited reply"


def test_4_original_comment_preservation():
    qid = _enqueue()
    client.put(f"/api/approval-queue/{qid}/edit", json={"edited_reply": "Edited"})
    client.post(f"/api/approval-queue/{qid}/approve")
    fetched = database.get_approval_queue_item(qid)
    assert fetched["comment_text"] == "What is the fee?"
    assert fetched["suggested_reply"] == "Please DM us for fee details."
    assert fetched["edited_reply"] == "Edited"


def test_5_duplicate_approval_prevention():
    qid = _enqueue()
    r1 = client.post(f"/api/approval-queue/{qid}/approve")
    r2 = client.post(f"/api/approval-queue/{qid}/approve")
    assert r1.status_code == 200
    assert r2.status_code == 400
    assert "invalid_transition_from_approved_to_approved" in r2.json()["detail"]


def test_6_rejected_item_cannot_be_approved():
    qid = _enqueue()
    r1 = client.post(f"/api/approval-queue/{qid}/reject")
    r2 = client.post(f"/api/approval-queue/{qid}/approve")
    assert r1.status_code == 200
    assert r2.status_code == 400
    assert "invalid_transition_from_rejected_to_approved" in r2.json()["detail"]


def test_7_already_replied_item_cannot_be_republished():
    _seed_account()
    qid = _enqueue(comment_id="c_replied")
    database.approve_approval_item(qid)
    database.set_setting("safe_test_mode", "false")

    conn = database.get_connection()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO activities (platform, comment_id, comment_text, status) VALUES ('facebook', 'c_replied', 'What is the fee?', 'replied')"
        )
        conn.commit()
    finally:
        conn.close()

    res = database.validate_approved_item_for_publishing(qid)
    assert res["eligible"] is False
    assert res["reason"] == "comment_already_replied"


def test_8_concurrent_approval_requests():
    qid = _enqueue()

    def _approve(_):
        return database.approve_approval_item(qid)

    with ThreadPoolExecutor(max_workers=5) as ex:
        results = list(ex.map(_approve, range(5)))

    successes = [ok for ok, _, _ in results if ok]
    failures = [ok for ok, _, _ in results if not ok]
    assert len(successes) == 1
    assert len(failures) == 4


def test_9_account_disconnection_validation():
    qid = _enqueue(platform="facebook", account_id="missing_page")
    database.approve_approval_item(qid)
    database.set_setting("safe_test_mode", "false")

    res = database.validate_approved_item_for_publishing(qid)
    assert res["eligible"] is False
    assert res["reason"] == "account_disconnected_or_invalid_facebook"


def test_10_global_kill_switch_validation():
    _seed_account()
    qid = _enqueue()
    database.approve_approval_item(qid)
    database.set_setting("safe_test_mode", "false")
    database.set_setting("global_kill_switch", "true")

    res = database.validate_approved_item_for_publishing(qid)
    assert res["eligible"] is False
    assert res["reason"] == "global_kill_switch_active"


def test_11_safe_testing_mode_validation():
    _seed_account()
    qid = _enqueue()
    database.approve_approval_item(qid)
    database.set_setting("safe_test_mode", "true")

    res = database.validate_approved_item_for_publishing(qid)
    assert res["eligible"] is False
    assert res["reason"] == "safe_testing_mode_active"


@pytest.mark.parametrize(
    "platform,account_id,expected_target",
    [
        ("facebook", "fb_page_1", "facebook_page"),
        ("instagram", "ig_prof_1", "instagram_professional_account"),
        ("youtube", "yt_chan_1", "youtube_channel"),
    ],
)
def test_12_platform_specific_validation(platform, account_id, expected_target):
    _seed_account(platform=platform, account_id=account_id)
    qid = _enqueue(platform=platform, account_id=account_id, comment_id=f"{platform}_c1")
    database.approve_approval_item(qid)
    database.set_setting("safe_test_mode", "false")

    res = database.validate_approved_item_for_publishing(qid)
    assert res["eligible"] is True
    assert res["reason"] is None
    assert res["target_type"] == expected_target
    assert res["account_id"] == account_id


def test_13_rate_limit_validation():
    _seed_account()
    qid = _enqueue(commenter="Arun")
    database.approve_approval_item(qid)
    database.set_setting("safe_test_mode", "false")

    now = time.time()
    conn = database.get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO reply_rate_log (platform, commenter_key, comment_id, replied_at) VALUES (?, ?, ?, ?)",
        ("facebook", "facebook:OtherUser", "other_c", now - 30),
    )
    conn.commit()
    conn.close()

    res = database.validate_approved_item_for_publishing(qid, now_ts=now)
    assert res["eligible"] is False
    assert res["reason"] == "rate_limit_min_interval_120s"


def test_14_activity_log_consistency():
    _seed_account()
    qid = _enqueue()
    client.put(f"/api/approval-queue/{qid}/edit", json={"edited_reply": "Edited text"})
    client.post(f"/api/approval-queue/{qid}/approve")
    client.post(f"/api/approval-queue/{qid}/validate-publish")

    resp = client.get(f"/api/approval-queue/activity-log/entries?approval_queue_id={qid}")
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    actions = [e["user_action"] for e in entries]
    assert "edit" in actions
    assert "approve" in actions
    assert "validate_publish" in actions
    for entry in entries:
        assert "access_token" not in str(entry)


def test_15_database_persistence_after_restart():
    qid = _enqueue()
    client.put(f"/api/approval-queue/{qid}/edit", json={"edited_reply": "Persisted reply"})
    client.post(f"/api/approval-queue/{qid}/approve")

    # Simulate app restart by re-initializing DB and reading with a fresh connection
    database.init_db()
    item = database.get_approval_queue_item(qid)
    assert item["status"] == "approved"
    assert item["edited_reply"] == "Persisted reply"
    assert item["comment_text"] == "What is the fee?"


def test_16_public_reply_api_never_called():
    _seed_account()
    qid = _enqueue()
    database.approve_approval_item(qid)

    with patch("requests.post") as post_mock:
        client.post(f"/api/approval-queue/{qid}/validate-publish")
        post_mock.assert_not_called()
