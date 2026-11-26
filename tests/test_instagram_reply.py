"""Focused tests for Instagram comment detection, NLP classification, safety, and reply API."""
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient

import database
from main import app
from instagram_service import InstagramService

client = TestClient(app)


def _setup_ig_account(auto_reply="true", safe_mode="true"):
    database.set_setting("ig_auto_reply_enabled", auto_reply)
    database.set_setting("safe_test_mode", safe_mode)
    InstagramService.connect_account("17841400000123456", "Gokul Brand (@gokul_brand)", "ig_token_secret")


def test_instagram_tamil_english_tanglish_classification_and_safe_mode():
    _setup_ig_account(auto_reply="true", safe_mode="true")

    comments = [
        {"id": "ig_c_ta", "post_id": "media_1", "text": "அருமை நன்றி", "username": "fan_tamil", "from": {"id": "u1"}},
        {"id": "ig_c_tg", "post_id": "media_1", "text": "Super bro vera level", "username": "fan_tg", "from": {"id": "u2"}},
        {"id": "ig_c_en", "post_id": "media_1", "text": "Awesome post, thank you!", "username": "fan_en", "from": {"id": "u3"}},
        {"id": "ig_c_q", "post_id": "media_1", "text": "Price details please?", "username": "buyer_1", "from": {"id": "u4"}},
    ]

    with patch.object(InstagramService, "send_reply") as mock_send:
        results = [
            InstagramService.process_and_reply_comment(c, "17841400000123456", "gokul_brand", "ig_token_secret")
            for c in comments
        ]
        mock_send.assert_not_called()

    assert results[0]["language"] == "ta"
    assert results[0]["status"] == "test_prepared"
    assert results[1]["language"] == "tanglish"
    assert results[1]["status"] == "test_prepared"
    assert results[2]["language"] == "en"
    assert results[2]["status"] == "test_prepared"
    assert results[3]["intent"] == "fee_enquiry"
    assert results[3]["status"] == "review_required"


def test_instagram_duplicate_prevention_and_self_comment_exclusion():
    _setup_ig_account(auto_reply="true", safe_mode="true")

    # Self-comment by ID
    self_by_id = {"id": "ig_self_1", "post_id": "m1", "text": "Super!", "from": {"id": "17841400000123456"}}
    res1 = InstagramService.process_and_reply_comment(self_by_id, "17841400000123456", "gokul_brand")
    assert res1["status"] == "skipped"
    assert res1["reason"] == "self_comment"

    # Self-comment by username
    self_by_name = {"id": "ig_self_2", "post_id": "m1", "text": "Thanks!", "username": "gokul_brand"}
    res2 = InstagramService.process_and_reply_comment(self_by_name, "17841400000123456", "gokul_brand")
    assert res2["status"] == "skipped"
    assert res2["reason"] == "self_comment"

    # Duplicate comment ID
    comment = {"id": "ig_dup_1", "post_id": "m1", "text": "Great reel!", "username": "viewer_1"}
    first = InstagramService.process_and_reply_comment(comment, "17841400000123456", "gokul_brand")
    assert first["status"] == "test_prepared"

    second = InstagramService.process_and_reply_comment(comment, "17841400000123456", "gokul_brand")
    assert second["status"] == "skipped"
    assert second["reason"] == "already_processed"


def test_instagram_complaint_and_abuse_protection():
    _setup_ig_account(auto_reply="true", safe_mode="false")

    abusive_comments = [
        {"id": "ig_bad_1", "post_id": "m1", "text": "This is a scam and fraud!", "username": "angry_user"},
        {"id": "ig_bad_2", "post_id": "m1", "text": "Romba mosam waste", "username": "angry_tg"},
        {"id": "ig_uncertain", "post_id": "m1", "text": "asdfghjkl", "username": "random_user"},
    ]

    with patch.object(InstagramService, "send_reply") as mock_send:
        for c in abusive_comments:
            res = InstagramService.process_and_reply_comment(c, "17841400000123456", "gokul_brand", "ig_token_secret")
            assert res["status"] == "review_required"
            assert res["reply_text"] is None
        mock_send.assert_not_called()


def test_instagram_sync_posts_and_reels_and_reply_endpoint():
    _setup_ig_account(auto_reply="true", safe_mode="false")
    conn = database.get_connection()
    conn.execute("DELETE FROM reply_rate_log")
    conn.commit()
    conn.close()

    media_resp = MagicMock()
    media_resp.json.return_value = {
        "data": [
            {"id": "ig_media_reel_1", "media_type": "VIDEO", "caption": "My Reel"},
        ]
    }
    comments_resp = MagicMock()
    comments_resp.json.return_value = {
        "data": [
            {"id": "ig_comment_999", "text": "Semma reel bro!", "username": "reel_fan"},
            {"id": "ig_comment_self", "text": "Thanks!", "username": "gokul_brand"},
        ]
    }
    reply_resp = MagicMock()
    reply_resp.json.return_value = {"id": "ig_reply_1000"}

    with patch("instagram_service.requests.get", side_effect=[media_resp, comments_resp]), \
         patch("instagram_service.requests.post", return_value=reply_resp) as mock_post:
        sync_res = client.post("/api/instagram/sync")

    assert sync_res.status_code == 200
    data = sync_res.json()
    assert data["success"] is True
    assert data["processed_count"] == 2
    assert data["details"][0]["status"] == "replied"
    assert data["details"][1]["reason"] == "self_comment"

    # Verify official Instagram /{comment_id}/replies endpoint was called (not /comments)
    called_url = mock_post.call_args[0][0]
    assert called_url.endswith("/ig_comment_999/replies")


def test_instagram_api_error_handling_without_crashing():
    _setup_ig_account(auto_reply="true", safe_mode="false")

    # 1. Expired token during sync
    expired_resp = MagicMock()
    expired_resp.json.return_value = {"error": {"code": 190, "message": "Token expired"}}
    with patch("instagram_service.requests.get", return_value=expired_resp):
        sync_res = client.post("/api/instagram/sync")
    assert sync_res.status_code == 200
    assert sync_res.json()["success"] is False
    assert "expired" in sync_res.json()["error"].lower()

    # 2. Network exception during send_reply (clear rate limit log from prior test)
    conn = database.get_connection()
    conn.execute("DELETE FROM reply_rate_log")
    conn.commit()
    conn.close()
    comment = {"id": "ig_err_1", "post_id": "m1", "text": "Awesome!", "username": "fan_err"}
    with patch("instagram_service.requests.post", side_effect=ConnectionError("Network down")):
        res = InstagramService.process_and_reply_comment(comment, "17841400000123456", "gokul_brand", "ig_token_secret")
    assert res["status"] == "failed"
    assert "Network down" in res["error"]
