"""Focused tests for Priority 2D: Safe Publishing Workflow."""
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
    """Isolate database state for each Priority 2D test."""
    database.init_db()
    conn = database.get_connection()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM publishing_attempts")
        c.execute("DELETE FROM approval_activity_log")
        c.execute("DELETE FROM approval_queue")
        c.execute("DELETE FROM activities")
        c.execute("DELETE FROM reply_rate_log")
        c.execute("DELETE FROM accounts")
        conn.commit()
    finally:
        conn.close()

    database.set_setting("global_kill_switch", "false")
    database.set_setting("safe_test_mode", "true")
    database.set_setting("auto_reply_enabled", "true")
    database.set_setting("ig_auto_reply_enabled", "true")
    database.set_setting("yt_auto_reply_enabled", "true")
    yield
    conn = database.get_connection()
    try:
        conn.execute("DELETE FROM reply_rate_log")
        conn.commit()
    finally:
        conn.close()


def _seed_account(platform="facebook", account_id="page_1", token="secret_oauth_tok_123", active=1):
    conn = database.get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO accounts (platform, account_id, account_name, access_token, is_active)
            VALUES (?, ?, ?, ?, ?)
            """,
            (platform, account_id, f"{platform}_acct", token, active),
        )
        conn.commit()
    finally:
        conn.close()


def _enqueue_and_approve(
    platform="facebook",
    account_id="page_1",
    comment_id="c_1",
    commenter="Arun",
    suggested_reply="Please DM us for fee details.",
):
    qid = database.enqueue_approval_item(
        platform=platform,
        account_id=account_id,
        comment_id=comment_id,
        commenter_name=commenter,
        comment_text="What is the fee?",
        detected_language="en",
        detected_intent="fee_enquiry",
        suggested_reply=suggested_reply,
        review_reason="consultation_fee_enquiry",
    )
    database.approve_approval_item(qid)
    return qid


@pytest.mark.parametrize(
    "platform,account_id,expected_target",
    [
        ("facebook", "fb_page_1", "facebook_page"),
        ("instagram", "ig_prof_1", "instagram_professional_account"),
        ("youtube", "yt_chan_1", "youtube_channel"),
    ],
)
def test_1_successful_test_mode_preparation(platform, account_id, expected_target):
    _seed_account(platform=platform, account_id=account_id)
    qid = _enqueue_and_approve(platform=platform, account_id=account_id, comment_id=f"{platform}_c1")

    resp = client.post(f"/api/approval-queue/{qid}/prepare-publish")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["attempt_status"] == "test_prepared"
    assert data["dispatched"] is False
    assert data["safe_test_mode"] is True
    assert data["prepared_payload"]["target_type"] == expected_target
    assert data["prepared_payload"]["dispatch_enabled"] is False


def test_2_safe_testing_mode_blocks_external_dispatch():
    _seed_account()
    qid = _enqueue_and_approve()
    with patch("requests.post") as post_mock:
        resp = client.post(f"/api/approval-queue/{qid}/prepare-publish")
        assert resp.status_code == 200
        assert resp.json()["dispatched"] is False
        post_mock.assert_not_called()


def test_3_global_kill_switch_blocks_preparation():
    _seed_account()
    qid = _enqueue_and_approve()
    database.set_setting("global_kill_switch", "true")

    resp = client.post(f"/api/approval-queue/{qid}/prepare-publish")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["attempt_status"] == "blocked"
    assert data["reason"] == "global_kill_switch_active"


def test_4_individual_platform_toggle_blocks_preparation():
    _seed_account(platform="instagram", account_id="ig_1")
    qid = _enqueue_and_approve(platform="instagram", account_id="ig_1")
    database.set_setting("ig_auto_reply_enabled", "false")

    resp = client.post(f"/api/approval-queue/{qid}/prepare-publish")
    data = resp.json()
    assert data["success"] is False
    assert data["attempt_status"] == "blocked"
    assert data["reason"] == "platform_auto_reply_disabled_instagram"


def test_5_disconnected_account_blocks_preparation():
    qid = _enqueue_and_approve(platform="facebook", account_id="missing_page")
    resp = client.post(f"/api/approval-queue/{qid}/prepare-publish")
    data = resp.json()
    assert data["success"] is False
    assert data["attempt_status"] == "blocked"
    assert data["reason"] == "account_disconnected_or_invalid_facebook"


def test_6_invalid_comment_id_blocks_preparation():
    _seed_account()
    qid = _enqueue_and_approve(comment_id="   ")
    resp = client.post(f"/api/approval-queue/{qid}/prepare-publish")
    data = resp.json()
    assert data["success"] is False
    assert data["attempt_status"] == "blocked"
    assert data["reason"] == "invalid_comment_id"


def test_7_empty_reply_blocks_preparation():
    _seed_account()
    qid = _enqueue_and_approve(suggested_reply="   ")
    resp = client.post(f"/api/approval-queue/{qid}/prepare-publish")
    data = resp.json()
    assert data["success"] is False
    assert data["attempt_status"] == "blocked"
    assert data["reason"] == "empty_reply_text"


def test_8_rate_limit_enforcement():
    _seed_account()
    qid = _enqueue_and_approve(commenter="Arun")
    now = time.time()
    conn = database.get_connection()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO reply_rate_log (platform, commenter_key, comment_id, replied_at) VALUES (?, ?, ?, ?)",
            ("facebook", "facebook:OtherUser", "other_c", now - 20),
        )
        conn.commit()
    finally:
        conn.close()

    res = database.prepare_publishing_for_item(qid, now_ts=now)
    assert res["success"] is False
    assert res["attempt_status"] == "blocked"
    assert res["reason"] == "rate_limit_min_interval_120s"


def test_9_duplicate_attempt_prevention():
    _seed_account()
    qid = _enqueue_and_approve()
    r1 = client.post(f"/api/approval-queue/{qid}/prepare-publish").json()
    r2 = client.post(f"/api/approval-queue/{qid}/prepare-publish").json()
    assert r1["success"] is True
    assert r1["attempt_status"] == "test_prepared"
    assert r2["success"] is False
    assert r2["reason"] == "duplicate_publishing_attempt"


def test_10_concurrent_preparation_requests():
    _seed_account()
    qid = _enqueue_and_approve()

    with ThreadPoolExecutor(max_workers=5) as ex:
        results = list(ex.map(lambda _: database.prepare_publishing_for_item(qid), range(5)))

    prepared = [r for r in results if r["attempt_status"] == "test_prepared"]
    blocked = [r for r in results if r["attempt_status"] == "blocked"]
    assert len(prepared) == 1
    assert len(blocked) == 4


def test_11_already_replied_or_rejected_items_blocked():
    _seed_account()
    qid_rej = database.enqueue_approval_item(
        platform="facebook",
        account_id="page_1",
        comment_id="c_rej",
        commenter_name="Arun",
        comment_text="Fee?",
        detected_language="en",
        detected_intent="fee_enquiry",
        suggested_reply="DM us",
        review_reason="fee",
    )
    database.reject_approval_item(qid_rej, reason="No")
    r_rej = client.post(f"/api/approval-queue/{qid_rej}/prepare-publish").json()
    assert r_rej["success"] is False
    assert r_rej["reason"] == "invalid_status_rejected"

    qid_rep = _enqueue_and_approve(comment_id="c_rep")
    conn = database.get_connection()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO activities (platform, comment_id, comment_text, status) VALUES ('facebook', 'c_rep', 'Fee?', 'replied')"
        )
        conn.commit()
    finally:
        conn.close()
    r_rep = client.post(f"/api/approval-queue/{qid_rep}/prepare-publish").json()
    assert r_rep["success"] is False
    assert r_rep["reason"] == "comment_already_replied"


def test_12_persistent_attempt_history_and_status_endpoints():
    _seed_account()
    qid = _enqueue_and_approve()
    client.post(f"/api/approval-queue/{qid}/prepare-publish")

    hist = client.get(f"/api/publishing-attempts?approval_queue_id={qid}")
    assert hist.status_code == 200
    assert hist.json()["count"] == 1
    assert hist.json()["attempts"][0]["attempt_status"] == "test_prepared"

    status = client.get(f"/api/approval-queue/{qid}/publishing-status")
    assert status.status_code == 200
    assert status.json()["latest_attempt"]["attempt_status"] == "test_prepared"


def test_13_no_external_publishing_api_calls():
    _seed_account()
    qid = _enqueue_and_approve()
    with patch("requests.post") as post_mock:
        client.post(f"/api/approval-queue/{qid}/prepare-publish")
        post_mock.assert_not_called()


def test_14_no_oauth_secrets_in_logs_or_api_responses():
    _seed_account(token="super_secret_oauth_token_xyz")
    qid = _enqueue_and_approve()
    prep = client.post(f"/api/approval-queue/{qid}/prepare-publish").json()
    hist = client.get(f"/api/publishing-attempts?approval_queue_id={qid}").json()
    act = client.get(f"/api/approval-queue/activity-log/entries?approval_queue_id={qid}").json()

    for payload in (prep, hist, act):
        assert "super_secret_oauth_token_xyz" not in str(payload)
