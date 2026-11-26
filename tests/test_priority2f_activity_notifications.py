"""Focused tests for Priority 2F: Activity and Notifications."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import database
from main import app
from facebook_service import FacebookService
from instagram_service import InstagramService
from youtube_service import YouTubeService

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_state():
    database.init_db()
    conn = database.get_connection()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM notifications")
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
    for p in ("facebook", "instagram", "youtube"):
        database.update_platform_hybrid_settings(
            p,
            auto_reply_enabled=True,
            praise_enabled=True,
            emoji_enabled=True,
            manual_queue_enabled=True,
            enabled_templates=list(database.APPROVED_TEMPLATE_IDS),
        )
    yield


def test_1_activity_records_from_all_three_platforms():
    FacebookService.process_and_reply_comment(
        {"id": "fb_1", "post_id": "p1", "message": "Awesome!", "from": {"id": "u1", "name": "Arun"}},
        page_id="page_1",
        access_token=None,
    )
    InstagramService.process_and_reply_comment(
        {"id": "ig_1", "media_id": "m1", "text": "Superb!", "username": "priya"},
        ig_user_id="ig_1",
        access_token=None,
    )
    YouTubeService.process_and_reply_comment(
        {"id": "yt_1", "video_id": "v1", "text": "Great video!", "author_name": "Karthik", "author_channel_id": "UC1"},
        channel_id="chan_1",
        access_token=None,
    )

    resp = client.get("/api/activity/timeline")
    assert resp.status_code == 200
    platforms = {e["platform"] for e in resp.json()["entries"]}
    assert {"facebook", "instagram", "youtube"}.issubset(platforms)


def test_2_newest_first_ordering():
    FacebookService.process_and_reply_comment(
        {"id": "fb_old", "post_id": "p1", "message": "Awesome!", "from": {"id": "u1", "name": "First"}},
        page_id="page_1",
        access_token=None,
    )
    FacebookService.process_and_reply_comment(
        {"id": "fb_new", "post_id": "p1", "message": "Superb!", "from": {"id": "u2", "name": "Second"}},
        page_id="page_1",
        access_token=None,
    )
    entries = client.get("/api/activity/timeline").json()["entries"]
    assert entries[0]["comment_id"] == "fb_new"


def test_3_platform_filtering():
    FacebookService.process_and_reply_comment(
        {"id": "fb_f1", "post_id": "p1", "message": "Awesome!", "from": {"id": "u1", "name": "Arun"}},
        page_id="page_1",
        access_token=None,
    )
    InstagramService.process_and_reply_comment(
        {"id": "ig_f1", "media_id": "m1", "text": "Superb!", "username": "priya"},
        ig_user_id="ig_1",
        access_token=None,
    )
    fb_only = client.get("/api/activity/timeline?platform=facebook").json()["entries"]
    assert len(fb_only) >= 1
    assert all(e["platform"] == "facebook" for e in fb_only)


def test_4_status_filtering():
    FacebookService.process_and_reply_comment(
        {"id": "fb_prep", "post_id": "p1", "message": "Awesome!", "from": {"id": "u1", "name": "Arun"}},
        page_id="page_1",
        access_token=None,
    )
    FacebookService.process_and_reply_comment(
        {"id": "fb_pend", "post_id": "p1", "message": "What is the fee?", "from": {"id": "u2", "name": "Meena"}},
        page_id="page_1",
        access_token=None,
    )
    prep = client.get("/api/activity/timeline?status=prepared").json()["entries"]
    assert any(e["comment_id"] == "fb_prep" for e in prep)
    assert all(e["comment_id"] != "fb_pend" for e in prep)


def test_5_search_by_commenter_and_comment():
    FacebookService.process_and_reply_comment(
        {"id": "fb_s1", "post_id": "p1", "message": "UniqueKeywordXYZ", "from": {"id": "u1", "name": "SpecialUser"}},
        page_id="page_1",
        access_token=None,
    )
    by_text = client.get("/api/activity/timeline?search=UniqueKeywordXYZ").json()["entries"]
    by_user = client.get("/api/activity/timeline?search=SpecialUser").json()["entries"]
    assert len(by_text) == 1
    assert len(by_user) == 1


def test_6_activity_detail_completeness():
    FacebookService.process_and_reply_comment(
        {"id": "fb_d1", "post_id": "p1", "message": "Awesome!", "from": {"id": "u1", "name": "Arun"}},
        page_id="page_1",
        access_token=None,
    )
    entry = client.get("/api/activity/timeline").json()["entries"][0]
    for key in ("platform", "commenter_name", "comment_text", "detected_language", "detected_intent", "status", "created_at"):
        assert key in entry


def test_7_and_8_notification_creation_and_duplicate_prevention():
    n1 = database.create_notification(
        event_key="pending_approval:1",
        event_type="pending_approval",
        platform="facebook",
        title="New comment awaiting approval",
        message="Arun asked a question",
        link_tab="autoreply",
        related_id=1,
    )
    n2 = database.create_notification(
        event_key="pending_approval:1",
        event_type="pending_approval",
        platform="facebook",
        title="New comment awaiting approval",
        message="Arun asked a question",
        link_tab="autoreply",
        related_id=1,
    )
    assert n1 is not None
    assert n2 is None
    assert client.get("/api/notifications").json()["unread_count"] == 1


def test_9_10_11_unread_count_mark_one_and_mark_all_read():
    n1 = database.create_notification(event_key="k1", event_type="info", title="T1", message="M1")
    database.create_notification(event_key="k2", event_type="info", title="T2", message="M2")
    assert client.get("/api/notifications").json()["unread_count"] == 2

    r1 = client.post(f"/api/notifications/{n1}/read")
    assert r1.status_code == 200
    assert client.get("/api/notifications").json()["unread_count"] == 1

    r_all = client.post("/api/notifications/read-all")
    assert r_all.status_code == 200
    assert client.get("/api/notifications").json()["unread_count"] == 0


def test_12_notification_persistence_after_restart():
    database.create_notification(event_key="persist_1", event_type="blocked", title="Blocked", message="Rate limit")
    database.init_db()
    data = client.get("/api/notifications").json()
    assert data["unread_count"] == 1
    assert data["notifications"][0]["event_key"] == "persist_1"


def test_13_dashboard_counts_from_database():
    database.enqueue_approval_item(
        platform="facebook",
        account_id="page_1",
        comment_id="c_dash_1",
        commenter_name="Arun",
        comment_text="Fee?",
        detected_language="en",
        detected_intent="fee_enquiry",
        suggested_reply="DM us",
        review_reason="fee",
    )
    database.create_notification(event_key="dash_n1", event_type="pending_approval", title="Pending", message="1")
    summary = client.get("/api/dashboard/summary").json()
    assert summary["pending_approvals"] == 1
    assert summary["unread_notifications"] == 1


def test_14_15_16_no_oauth_secrets_safe_mode_on_no_external_calls():
    assert database.get_settings().get("safe_test_mode") == "true"
    with patch("requests.post") as post_mock:
        act = client.get("/api/activity/timeline").json()
        notif = client.get("/api/notifications").json()
        post_mock.assert_not_called()
        assert "access_token" not in str(act)
        assert "access_token" not in str(notif)
