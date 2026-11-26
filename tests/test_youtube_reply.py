"""Focused tests for YouTube video/comment retrieval, NLP classification, safety, duplicate prevention, and reply API."""
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient

import database
from main import app
from youtube_service import YouTubeService

client = TestClient(app)

CHANNEL_ID = "UC_gokul_channel_123"
CHANNEL_TITLE = "Gokul Tech Channel"


def _setup_youtube_account(auto_reply="true", safe_mode="true"):
    database.set_setting("yt_auto_reply_enabled", auto_reply)
    database.set_setting("safe_test_mode", safe_mode)
    YouTubeService.connect_account(
        account_id=CHANNEL_ID,
        account_name=CHANNEL_TITLE,
        access_token="ya29.sample_token_xyz",
        refresh_token="1//sample_refresh_abc",
        uploads_playlist_id="UU_gokul_channel_123",
    )


def test_youtube_tamil_english_tanglish_classification_and_safe_mode():
    _setup_youtube_account(auto_reply="true", safe_mode="true")

    comments = [
        {"id": "yt_c_ta", "post_id": "vid_101", "text": "அருமை நன்றி", "author_name": "tamil_viewer", "author_channel_id": "UC_viewer_1"},
        {"id": "yt_c_tg", "post_id": "vid_101", "text": "Super bro vera level", "author_name": "tanglish_viewer", "author_channel_id": "UC_viewer_2"},
        {"id": "yt_c_en", "post_id": "vid_101", "text": "Awesome video, keep it up!", "author_name": "english_viewer", "author_channel_id": "UC_viewer_3"},
        {"id": "yt_c_q", "post_id": "vid_101", "text": "Price details please?", "author_name": "buyer_viewer", "author_channel_id": "UC_viewer_4"},
    ]

    with patch.object(YouTubeService, "send_reply") as mock_send:
        results = [
            YouTubeService.process_and_reply_comment(c, CHANNEL_ID, CHANNEL_TITLE, "ya29.sample_token_xyz")
            for c in comments
        ]
        # In Safe Testing Mode, live reply API must NEVER be called
        mock_send.assert_not_called()

    assert results[0]["language"] == "ta"
    assert results[0]["status"] == "test_prepared"
    assert results[0]["reply_text"] is not None

    assert results[1]["language"] == "tanglish"
    assert results[1]["status"] == "test_prepared"
    assert results[1]["reply_text"] is not None

    assert results[2]["language"] == "en"
    assert results[2]["status"] == "test_prepared"
    assert results[2]["reply_text"] is not None

    assert results[3]["intent"] == "fee_enquiry"
    assert results[3]["status"] == "review_required"
    assert results[3]["reply_text"] is None


def test_youtube_duplicate_prevention_and_self_comment_exclusion():
    _setup_youtube_account(auto_reply="true", safe_mode="true")

    # 1. Self-comment by channel ID
    self_by_id = {
        "id": "yt_self_1",
        "post_id": "vid_101",
        "text": "Thanks for watching everyone!",
        "author_channel_id": CHANNEL_ID,
        "author_name": "Some Display Name",
    }
    res1 = YouTubeService.process_and_reply_comment(self_by_id, CHANNEL_ID, CHANNEL_TITLE)
    assert res1["status"] == "skipped"
    assert res1["reason"] == "self_comment"

    # 2. Self-comment by channel title
    self_by_title = {
        "id": "yt_self_2",
        "post_id": "vid_101",
        "text": "Link is in the description!",
        "author_channel_id": "UC_some_other_id",
        "author_name": CHANNEL_TITLE,
    }
    res2 = YouTubeService.process_and_reply_comment(self_by_title, CHANNEL_ID, CHANNEL_TITLE)
    assert res2["status"] == "skipped"
    assert res2["reason"] == "self_comment"

    # 3. Duplicate comment prevention
    comment = {
        "id": "yt_dup_1",
        "post_id": "vid_101",
        "text": "Super video bro!",
        "author_channel_id": "UC_user_99",
        "author_name": "Fan99",
    }
    first = YouTubeService.process_and_reply_comment(comment, CHANNEL_ID, CHANNEL_TITLE)
    assert first["status"] == "test_prepared"

    second = YouTubeService.process_and_reply_comment(comment, CHANNEL_ID, CHANNEL_TITLE)
    assert second["status"] == "skipped"
    assert second["reason"] == "already_processed"


def test_youtube_complaint_and_abuse_handling():
    _setup_youtube_account(auto_reply="true", safe_mode="false")

    sensitive_comments = [
        {"id": "yt_abuse_1", "post_id": "vid_101", "text": "This is total scam and fraud video", "author_name": "angry_user"},
        {"id": "yt_abuse_2", "post_id": "vid_101", "text": "Romba mosam waste content", "author_name": "angry_tg"},
        {"id": "yt_uncertain", "post_id": "vid_101", "text": "qwertyuiop123", "author_name": "random_user"},
    ]

    with patch.object(YouTubeService, "send_reply") as mock_send:
        for c in sensitive_comments:
            res = YouTubeService.process_and_reply_comment(c, CHANNEL_ID, CHANNEL_TITLE, "ya29.sample_token_xyz")
            assert res["status"] == "review_required"
            assert res["reply_text"] is None
        mock_send.assert_not_called()


def test_youtube_video_and_comment_retrieval_and_live_reply_operation():
    _setup_youtube_account(auto_reply="true", safe_mode="false")

    # Mock playlistItems.list response (uploads playlist)
    playlist_resp = MagicMock()
    playlist_resp.json.return_value = {
        "items": [
            {
                "snippet": {"title": "My First Tech Video"},
                "contentDetails": {"videoId": "vid_tech_1"},
            }
        ]
    }

    # Mock commentThreads.list response
    comment_threads_resp = MagicMock()
    comment_threads_resp.json.return_value = {
        "items": [
            {
                "id": "yt_thread_1",
                "snippet": {
                    "videoId": "vid_tech_1",
                    "topLevelComment": {
                        "id": "yt_c_top_1",
                        "snippet": {
                            "authorDisplayName": "tech_fan",
                            "authorChannelId": {"value": "UC_viewer_fan"},
                            "textOriginal": "Awesome video, thank you!",
                            "publishedAt": "2026-11-26T12:00:00Z",
                        },
                    },
                },
            },
            {
                "id": "yt_thread_self",
                "snippet": {
                    "videoId": "vid_tech_1",
                    "topLevelComment": {
                        "id": "yt_c_top_self",
                        "snippet": {
                            "authorDisplayName": CHANNEL_TITLE,
                            "authorChannelId": {"value": CHANNEL_ID},
                            "textOriginal": "Thanks for watching!",
                            "publishedAt": "2026-11-26T12:05:00Z",
                        },
                    },
                },
            },
        ]
    }

    # Mock comments.insert response
    reply_resp = MagicMock()
    reply_resp.json.return_value = {
        "id": "yt_reply_id_888",
        "snippet": {
            "parentId": "yt_c_top_1",
            "textOriginal": "Thank you so much!",
        },
    }

    with patch("youtube_service.requests.get", side_effect=[playlist_resp, comment_threads_resp]), \
         patch("youtube_service.requests.post", return_value=reply_resp) as mock_post:
        sync_res = client.post("/api/youtube/sync")

    assert sync_res.status_code == 200
    data = sync_res.json()
    assert data["success"] is True
    assert data["processed_count"] == 2
    assert data["details"][0]["status"] == "replied"
    assert data["details"][1]["reason"] == "self_comment"

    # Verify official YouTube comments.insert operation was called with correct structure
    mock_post.assert_called_once()
    called_url = mock_post.call_args[0][0]
    assert "/comments?part=snippet" in called_url
    assert "commentThreads" not in called_url

    called_json = mock_post.call_args[1]["json"]
    assert "snippet" in called_json
    assert called_json["snippet"]["parentId"] == "yt_c_top_1"
    assert len(called_json["snippet"]["textOriginal"]) > 0


def test_youtube_quota_and_disabled_comments_graceful_handling():
    _setup_youtube_account(auto_reply="true", safe_mode="false")

    # 1. Quota error handling
    quota_resp = MagicMock()
    quota_resp.json.return_value = {
        "error": {
            "code": 403,
            "message": "The request cannot be completed because you have exceeded your quota.",
            "errors": [{"reason": "quotaExceeded"}],
        }
    }
    with patch("youtube_service.requests.get", return_value=quota_resp):
        sync_res = client.post("/api/youtube/sync")
    assert sync_res.status_code == 200
    assert sync_res.json()["success"] is False
    assert "quota" in sync_res.json()["error"].lower()

    # 2. Disabled comments on a video: should skip video gracefully without crashing
    playlist_resp = MagicMock()
    playlist_resp.json.return_value = {
        "items": [{"contentDetails": {"videoId": "vid_disabled"}}]
    }
    disabled_resp = MagicMock()
    disabled_resp.json.return_value = {
        "error": {
            "code": 403,
            "message": "The comment is disabled on this video.",
            "errors": [{"reason": "commentsDisabled"}],
        }
    }
    with patch("youtube_service.requests.get", side_effect=[playlist_resp, disabled_resp]):
        sync_res2 = client.post("/api/youtube/sync")
    assert sync_res2.status_code == 200
    assert sync_res2.json()["success"] is True
    assert sync_res2.json()["processed_count"] == 0

    # 3. Network failure during reply (clear rate limit log from prior test)
    conn = database.get_connection()
    conn.execute("DELETE FROM reply_rate_log")
    conn.commit()
    conn.close()
    comment = {
        "id": "yt_net_err_1",
        "post_id": "vid_101",
        "text": "Great video bro!",
        "author_channel_id": "UC_viewer_fail",
        "author_name": "FanFail",
    }
    with patch("youtube_service.requests.post", side_effect=ConnectionError("Connection lost")):
        res = YouTubeService.process_and_reply_comment(comment, CHANNEL_ID, CHANNEL_TITLE, "ya29.sample_token_xyz")
    assert res["status"] == "failed"
    assert "Connection lost" in res["error"]
