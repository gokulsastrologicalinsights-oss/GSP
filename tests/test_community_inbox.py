"""Tests for Buffer-style Post-Centric Community Inbox & 3-Level Reply Suggestions."""
import sys
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import database
import main
import reply_suggester


@pytest.fixture(autouse=True)
def clean_inbox_tables():
    conn = database.get_connection()
    c = conn.cursor()
    for tbl in (
        "social_posts",
        "inbox_suggestions",
        "approval_queue",
        "approval_activity_log",
        "publishing_attempts",
        "reply_rate_log",
    ):
        c.execute(f"DELETE FROM {tbl}")
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('safe_test_mode', 'true')")
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('global_kill_switch', 'false')")
    conn.commit()
    conn.close()


def _seed_account(platform: str, account_id: str, account_name: str, token: str = "mock_token"):
    conn = database.get_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT OR REPLACE INTO accounts (platform, account_id, account_name, access_token, is_active)
        VALUES (?, ?, ?, ?, 1)
        """,
        (platform, account_id, account_name, token),
    )
    conn.commit()
    conn.close()


def _seed_comment(
    platform: str,
    account_id: str,
    post_id: str,
    comment_id: str,
    author_name: str,
    comment_text: str,
    status: str = "review_required",
    reply_text: str = None,
    created_at: str = "2026-11-26 10:00:00",
):
    conn = database.get_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO activities (
            platform, account_id, post_id, comment_id, author_name, comment_text,
            detected_language, detected_intent, reply_text, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'en', 'neutral', ?, ?, ?)
        """,
        (platform, account_id, post_id, comment_id, author_name, comment_text, reply_text, status, created_at),
    )
    conn.commit()
    conn.close()


def test_three_level_suggestions_tamil_tanglish_english():
    cases = [
        ("ta", "மிகவும் அருமை! வாழ்த்துகள் 🙏", "positive"),
        ("tanglish", "Super bro vera level irukku!", "positive"),
        ("en", "Thank you for this helpful video!", "appreciation"),
        ("en", "Worst experience, my payment was delayed and no response!", "complaint"),
        ("en", "You are an idiot and scammer!", "abusive"),
        ("ta", "இந்த பதிவு நல்லா இல்ல, பயனில்லை", "negative"),
        ("en", "How much is the consultation fee?", "inquiry"),
    ]
    for expected_lang, text, expected_intent in cases:
        res = reply_suggester.generate_three_level_suggestions(
            comment_text=text,
            commenter_name="Karthik",
            account_name="Gokul's Astrological Insights",
            platform="instagram",
            post_caption="Weekly Rasi Palan Forecast",
        )
        assert res["language"] == expected_lang
        assert res["intent"] == expected_intent
        assert res["short"] and res["medium"] and res["detailed"]
        # Three genuinely different responses
        assert len({res["short"], res["medium"], res["detailed"]}) == 3
        assert len(res["short"]) < len(res["detailed"])


def test_spam_and_threatening_classification():
    spam = reply_suggester.generate_three_level_suggestions("Earn money fast! Visit https://spam.example.com")
    assert spam["intent"] == "spam"
    assert spam["recommend_no_reply"] is True
    assert spam["short"] == ""

    threat = reply_suggester.generate_three_level_suggestions("I will attack and sue you in court!")
    assert threat["intent"] == "threatening"
    assert threat["manual_review_required"] is True
    assert threat["short"] == ""


def test_inbox_posts_list_filters_and_pagination():
    _seed_account("facebook", "fb_1", "Gokul FB Page")
    _seed_account("instagram", "ig_1", "Gokul IG")
    _seed_account("youtube", "yt_1", "Gokul YT")

    database.upsert_social_post("facebook", "fb_1", "fb_post_1", caption="FB Horoscope Post")
    database.upsert_social_post("instagram", "ig_1", "ig_post_1", caption="IG Reel Post")
    database.upsert_social_post("youtube", "yt_1", "yt_vid_1", caption="YT Video Forecast")

    _seed_comment("facebook", "fb_1", "fb_post_1", "fc_1", "Arun", "Super post!", status="replied", reply_text="Thanks!", created_at="2026-11-26 09:00:00")
    _seed_comment("facebook", "fb_1", "fb_post_1", "fc_2", "Priya", "How much fee?", status="review_required", created_at="2026-11-26 11:00:00")
    _seed_comment("facebook", "fb_1", "fb_post_1", "fc_3", "Suresh", "Not good", status="review_required", created_at="2026-11-26 12:00:00")
    _seed_comment("instagram", "ig_1", "ig_post_1", "ic_1", "Meena", "அருமை!", status="replied", reply_text="நன்றி!", created_at="2026-11-26 08:00:00")
    _seed_comment("youtube", "yt_1", "yt_vid_1", "yc_1", "Vijay", "Nice video", status="review_required", created_at="2026-11-26 13:00:00")

    if True:
        client = TestClient(main.app)
        # All posts sorted by most recent activity
        res = client.get("/api/inbox/posts")
        assert res.status_code == 200
        posts = res.json()["posts"]
        assert len(posts) == 3
        assert posts[0]["post_id"] == "yt_vid_1"  # 13:00 most recent
        assert posts[1]["post_id"] == "fb_post_1"  # 12:00

        fb_post = posts[1]
        assert fb_post["total_comments"] == 3
        assert fb_post["answered_count"] == 1
        assert fb_post["unanswered_count"] == 2

        # Filter unanswered only
        unans = client.get("/api/inbox/posts?status=unanswered").json()["posts"]
        assert all(p["unanswered_count"] > 0 for p in unans)
        assert len(unans) == 2

        # Filter by platform
        ig_only = client.get("/api/inbox/posts?platform=instagram").json()["posts"]
        assert len(ig_only) == 1
        assert ig_only[0]["post_id"] == "ig_post_1"

        # Load post comments with pagination
        p1 = client.get("/api/inbox/posts/facebook/fb_post_1/comments?limit=2&offset=0")
        assert p1.status_code == 200
        d1 = p1.json()
        assert len(d1["comments"]) == 2
        assert d1["has_more"] is True
        assert d1["comments"][0]["suggestions"]["short"]
        assert d1["comments"][0]["suggestions"]["medium"]
        assert d1["comments"][0]["suggestions"]["detailed"]

        p2 = client.get("/api/inbox/posts/facebook/fb_post_1/comments?limit=2&offset=2")
        assert len(p2.json()["comments"]) == 1
        assert p2.json()["has_more"] is False


def test_explicit_send_safe_test_mode_and_duplicate_prevention():
    _seed_account("instagram", "ig_1", "Gokul IG")
    _seed_comment("instagram", "ig_1", "ig_post_1", "ic_safe_1", "Divya", "Vera level post bro!")

    if True:
        client = TestClient(main.app)
        # Regenerate suggestions
        regen = client.post("/api/inbox/comments/instagram/ic_safe_1/regenerate")
        assert regen.status_code == 200
        assert regen.json()["suggestions"]["medium"]

        # Explicit Send in Safe Testing Mode (no live API call)
        with patch("instagram_service.InstagramService.send_reply") as mock_send:
            send_res = client.post(
                "/api/inbox/comments/instagram/ic_safe_1/reply",
                json={"reply_text": "Romba nandri Divya!", "selected_level": "medium"},
            )
            assert send_res.status_code == 200
            body = send_res.json()
            assert body["success"] is True
            assert body["safe_test_mode"] is True
            assert body["dispatched"] is False
            assert body["status"] == "test_prepared"
            mock_send.assert_not_called()

        # Duplicate send blocked
        dup_res = client.post(
            "/api/inbox/comments/instagram/ic_safe_1/reply",
            json={"reply_text": "Duplicate attempt", "selected_level": "short"},
        )
        assert dup_res.status_code == 409


@pytest.mark.parametrize(
    "platform,account_id,comment_id,patch_target",
    [
        ("facebook", "fb_1", "fb_c_live", "facebook_service.FacebookService.send_reply"),
        ("instagram", "ig_1", "ig_c_live", "instagram_service.InstagramService.send_reply"),
        ("youtube", "yt_1", "yt_c_live", "youtube_service.YouTubeService.send_reply"),
    ],
)
def test_live_mode_mocked_platform_reply_routing(platform, account_id, comment_id, patch_target):
    _seed_account(platform, account_id, f"{platform} Account", token="live_mock_tok")
    _seed_comment(platform, account_id, f"{platform}_p1", comment_id, "Tester", "Awesome update!")
    database.set_setting("safe_test_mode", "false")

    if True:
        client = TestClient(main.app)
        with patch(patch_target, return_value={"id": "reply_ok_123"}) as mock_api:
            res = client.post(
                f"/api/inbox/comments/{platform}/{comment_id}/reply",
                json={"reply_text": "Thank you Tester!", "selected_level": "short"},
            )
            assert res.status_code == 200, res.text
            data = res.json()
            assert data["success"] is True, data
            assert data["dispatched"] is True
            assert data["status"] == "replied"
            mock_api.assert_called_once()
            args = mock_api.call_args[0]
            assert args[0] == comment_id
            assert args[1] == "Thank you Tester!"


def test_uncertain_network_outcome_reconciliation():
    _seed_account("facebook", "fb_1", "Gokul FB", token="tok_123")
    _seed_comment("facebook", "fb_1", "fb_p1", "fb_net_err", "Kiran", "Great post!")
    database.set_setting("safe_test_mode", "false")

    if True:
        client = TestClient(main.app)
        with patch("facebook_service.FacebookService.send_reply", side_effect=TimeoutError("Read timed out")), \
             patch("database._reconcile_platform_reply", return_value=False):
            res = client.post(
                "/api/inbox/comments/facebook/fb_net_err/reply",
                json={"reply_text": "Thanks Kiran!", "selected_level": "short"},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["success"] is False
            assert data["reconciliation_required"] is True
            assert data["status"] == "reconciliation_required"
