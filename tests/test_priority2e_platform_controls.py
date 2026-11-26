"""Focused tests for Priority 2E: Platform-specific Hybrid Controls."""
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
        c.execute("DELETE FROM approval_queue")
        c.execute("DELETE FROM activities")
        c.execute("DELETE FROM reply_rate_log")
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


def test_1_independent_platform_settings():
    r = client.put(
        "/api/platform-settings/facebook",
        json={"auto_reply_enabled": False, "praise_enabled": False},
    )
    assert r.status_code == 200
    all_cfg = client.get("/api/platform-settings").json()["platforms"]
    assert all_cfg["facebook"]["auto_reply_enabled"] is False
    assert all_cfg["facebook"]["praise_enabled"] is False
    assert all_cfg["instagram"]["auto_reply_enabled"] is True
    assert all_cfg["youtube"]["auto_reply_enabled"] is True


def test_2_settings_persistence_after_db_reinit():
    client.put(
        "/api/platform-settings/instagram",
        json={"emoji_enabled": False, "enabled_templates": ["en_1", "ta_1"]},
    )
    database.init_db()
    cfg = database.get_platform_hybrid_settings("instagram")
    assert cfg["emoji_enabled"] is False
    assert cfg["enabled_templates"] == ["en_1", "ta_1"]


def test_3_disabling_one_platform_does_not_affect_others():
    client.put("/api/platform-settings/youtube", json={"auto_reply_enabled": False})
    fb_res = FacebookService.process_and_reply_comment(
        {"id": "fb_p1", "post_id": "p1", "message": "Superb video!", "from": {"id": "u1", "name": "Arun"}},
        page_id="page_1",
        access_token=None,
    )
    yt_res = YouTubeService.process_and_reply_comment(
        {"id": "yt_p1", "video_id": "v1", "text": "Superb video!", "author_name": "Arun", "author_channel_id": "UC1"},
        channel_id="chan_1",
        access_token=None,
    )
    assert fb_res["status"] == "test_prepared"
    assert yt_res["status"] == "review_required"


def test_4_main_platform_toggle_blocks_auto_reply():
    client.put("/api/platform-settings/facebook", json={"auto_reply_enabled": False})
    res = FacebookService.process_and_reply_comment(
        {"id": "fb_off_1", "post_id": "p1", "message": "Great post!", "from": {"id": "u1", "name": "Arun"}},
        page_id="page_1",
        access_token=None,
    )
    assert res["status"] == "review_required"


def test_5_praise_toggle_independent():
    client.put("/api/platform-settings/facebook", json={"praise_enabled": False, "emoji_enabled": True})
    praise_res = FacebookService.process_and_reply_comment(
        {"id": "fb_pr_1", "post_id": "p1", "message": "Awesome content, very helpful!", "from": {"id": "u1", "name": "Arun"}},
        page_id="page_1",
        access_token=None,
    )
    emoji_res = FacebookService.process_and_reply_comment(
        {"id": "fb_em_1", "post_id": "p1", "message": "🙏🙏❤️", "from": {"id": "u2", "name": "Priya"}},
        page_id="page_1",
        access_token=None,
    )
    assert praise_res["status"] == "review_required"
    assert emoji_res["status"] == "test_prepared"


def test_6_emoji_toggle_independent():
    client.put("/api/platform-settings/instagram", json={"emoji_enabled": False, "praise_enabled": True})
    emoji_res = InstagramService.process_and_reply_comment(
        {"id": "ig_em_1", "media_id": "m1", "text": "❤️❤️🙏", "username": "priya"},
        ig_user_id="ig_1",
        access_token=None,
    )
    assert emoji_res["status"] == "review_required"


def test_7_manual_approval_queue_toggle_safe():
    client.put("/api/platform-settings/facebook", json={"manual_queue_enabled": False})
    res = FacebookService.process_and_reply_comment(
        {"id": "fb_mq_1", "post_id": "p1", "message": "What is the consultation fee?", "from": {"id": "u1", "name": "Arun"}},
        page_id="page_1",
        access_token=None,
    )
    assert res["status"] == "review_required"
    assert res.get("manual_queue_disabled") is True
    assert len(database.get_approval_queue(status="pending", platform="facebook")) == 0


def test_8_template_selection_platform_specific_and_unapproved_rejected():
    bad = client.put("/api/platform-settings/facebook", json={"enabled_templates": ["custom_free_text"]})
    assert bad.status_code == 400

    client.put("/api/platform-settings/facebook", json={"enabled_templates": ["en_1"]})
    fb_cfg = database.get_platform_hybrid_settings("facebook")
    ig_cfg = database.get_platform_hybrid_settings("instagram")
    assert fb_cfg["enabled_templates"] == ["en_1"]
    assert len(ig_cfg["enabled_templates"]) == 6


def test_9_language_matching_enforced():
    client.put("/api/platform-settings/facebook", json={"enabled_templates": ["ta_1"]})
    # English praise when only ta_1 is enabled -> no English template enabled -> held for review
    res = FacebookService.process_and_reply_comment(
        {"id": "fb_lang_1", "post_id": "p1", "message": "Awesome video!", "from": {"id": "u1", "name": "Arun"}},
        page_id="page_1",
        access_token=None,
    )
    assert res["status"] == "review_required"


def test_10_complaints_abuse_spam_remain_manual_review():
    for cid, msg in [("c_comp", "Worst service ever, terrible!"), ("c_spam", "Buy crypto now http://spam.com")]:
        res = FacebookService.process_and_reply_comment(
            {"id": cid, "post_id": "p1", "message": msg, "from": {"id": "u1", "name": "Arun"}},
            page_id="page_1",
            access_token=None,
        )
        assert res["status"] == "review_required"


def test_11_global_kill_switch_overrides_platform_settings():
    database.set_setting("global_kill_switch", "true")
    res = FacebookService.process_and_reply_comment(
        {"id": "fb_ks_1", "post_id": "p1", "message": "Awesome!", "from": {"id": "u1", "name": "Arun"}},
        page_id="page_1",
        access_token=None,
    )
    assert res["status"] == "review_required"


def test_12_safe_testing_mode_remains_on_and_no_public_api_calls():
    assert database.get_settings().get("safe_test_mode") == "true"
    with patch("requests.post") as post_mock:
        FacebookService.process_and_reply_comment(
            {"id": "fb_safe_1", "post_id": "p1", "message": "Awesome!", "from": {"id": "u1", "name": "Arun"}},
            page_id="page_1",
            access_token="tok",
        )
        post_mock.assert_not_called()
