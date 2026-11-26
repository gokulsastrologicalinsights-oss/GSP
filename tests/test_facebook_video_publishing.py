from datetime import datetime
import os
import pytest
import requests

import database
import scheduler_service
from facebook_service import FacebookService


@pytest.fixture()
def isolated_fb_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_fb_pub.db"
    monkeypatch.setenv("GSP_DB_PATH", str(db_file))
    database.init_db()
    return tmp_path


def _create_dummy_video(tmp_path, name="aries.mp4"):
    p = tmp_path / name
    p.write_bytes(b"FAKE_MP4_VIDEO_BYTES")
    return str(p)


def test_safe_testing_mode_blocks_real_upload(isolated_fb_db, monkeypatch):
    video_path = _create_dummy_video(isolated_fb_db)
    called = []

    def fail_if_called(*args, **kwargs):
        called.append(True)
        raise AssertionError("Real HTTP request should not be made in Safe Testing Mode")

    monkeypatch.setattr(requests, "post", fail_if_called)
    database.set_setting("safe_test_mode", "true")

    scheduler_service.schedule_multichannel_batch(
        accounts=[{"account_key": "facebook:page1", "platform": "facebook"}],
        category="Weekly Rasi Palan",
        items=[{"original_filename": "aries.mp4", "media_path": video_path, "file_size_bytes": 20, "video_id": "v_safe"}],
        start_from=datetime(2026, 1, 1, 8, 0, 0),
    )
    res = scheduler_service.run_pending_scheduled_posts(now=datetime(2026, 1, 2, 12, 0, 0))
    assert res["processed"] == 1
    assert called == []
    posts = scheduler_service.get_scheduled_posts()
    assert posts[0]["status"] == "published_safe_mode"
    assert os.path.exists(video_path)


def test_successful_mocked_upload_and_caption_and_local_file_preserved(isolated_fb_db, monkeypatch):
    video_path = _create_dummy_video(isolated_fb_db)
    FacebookService.connect_page("page_123", "Gokul Astro", "tok_valid_123")
    database.set_setting("safe_test_mode", "false")

    captured = {}

    class MockResp:
        status_code = 200
        text = '{"id": "fb_vid_999"}'

        def json(self):
            return {"id": "fb_vid_999"}

    def mock_post(url, data=None, files=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        captured["has_file"] = "source" in (files or {})
        return MockResp()

    monkeypatch.setattr(requests, "post", mock_post)

    scheduler_service.schedule_multichannel_batch(
        accounts=[{"account_key": "facebook:page_123", "platform": "facebook"}],
        category="Weekly Rasi Palan",
        items=[{
            "original_filename": "aries.mp4",
            "media_path": video_path,
            "file_size_bytes": 20,
            "video_id": "v_ok",
            "caption": "Aries Weekly",
            "hashtags": "#Aries #Astrology",
        }],
        start_from=datetime(2026, 1, 1, 8, 0, 0),
    )
    res = scheduler_service.run_pending_scheduled_posts(now=datetime(2026, 1, 2, 12, 0, 0))
    assert res["processed"] == 1
    assert captured["url"] == "https://graph-video.facebook.com/v27.0/page_123/videos"
    assert "v19.0" not in captured["url"]
    assert "Aries Weekly" in captured["data"]["description"]
    assert "#Aries #Astrology" in captured["data"]["description"]
    assert captured["has_file"] is True

    post = scheduler_service.get_scheduled_posts()[0]
    assert post["status"] == "published"
    assert post["external_post_id"] == "fb_vid_999"
    assert post["permalink"] == "https://www.facebook.com/page_123/videos/fb_vid_999/"
    assert post["attempt_count"] == 1
    assert os.path.exists(video_path)


def test_missing_file_and_token_error_and_retry(isolated_fb_db, monkeypatch):
    FacebookService.connect_page("page_123", "Gokul Astro", "tok_expired")
    database.set_setting("safe_test_mode", "false")

    # 1. Missing local file
    scheduler_service.schedule_multichannel_batch(
        accounts=[{"account_key": "facebook:page_123", "platform": "facebook"}],
        category="Weekly Rasi Palan",
        items=[{"original_filename": "aries.mp4", "media_path": "D:/nonexistent/aries.mp4", "file_size_bytes": 20, "video_id": "v_miss"}],
        start_from=datetime(2026, 1, 1, 8, 0, 0),
    )
    scheduler_service.run_pending_scheduled_posts(now=datetime(2026, 1, 2, 12, 0, 0))
    p_miss = scheduler_service.get_scheduled_posts()[0]
    assert p_miss["status"] == "failed"
    assert "missing or unreadable" in p_miss["error_message"].lower()

    # 2. Token expiry / network error + retry
    video_path = _create_dummy_video(isolated_fb_db, "taurus.mp4")

    class ErrResp:
        status_code = 400
        text = '{"error": {"message": "Error validating access token: Session has expired", "code": 190}}'

        def json(self):
            return {"error": {"message": "Error validating access token: Session has expired", "code": 190}}

    monkeypatch.setattr(requests, "post", lambda *a, **kw: ErrResp())

    scheduler_service.schedule_multichannel_batch(
        accounts=[{"account_key": "facebook:page_123", "platform": "facebook"}],
        category="Weekly Rasi Palan",
        items=[{"original_filename": "taurus.mp4", "media_path": video_path, "file_size_bytes": 20, "video_id": "v_retry"}],
        start_from=datetime(2026, 1, 1, 8, 0, 0),
    )
    scheduler_service.run_pending_scheduled_posts(now=datetime(2026, 1, 3, 12, 0, 0))
    p_fail = [p for p in scheduler_service.get_scheduled_posts() if p["video_id"] == "v_retry"][0]
    assert p_fail["status"] == "auth_required"
    assert "expired" in p_fail["error_message"].lower()
    assert p_fail["attempt_count"] == 1

    # Retry via reschedule_video
    scheduler_service.reschedule_video("v_retry", "2026-01-04T09:00:00")
    p_re = [p for p in scheduler_service.get_scheduled_posts() if p["video_id"] == "v_retry"][0]
    assert p_re["status"] == "scheduled"
