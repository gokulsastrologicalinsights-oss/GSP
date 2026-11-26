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
    FacebookService.connect_page("page_123", "Gokul Astro", "tok_valid")
    database.set_setting("safe_test_mode", "false")
    video_path = _create_dummy_video(isolated_fb_db, "gemini.mp4")
    adapter = scheduler_service.FacebookPageAdapter()
    post = {
        "id": 1,
        "platform": "facebook",
        "account_key": "facebook:page_123",
        "media_path": video_path,
        "original_filename": "gemini.mp4",
        "caption": "Test",
        "hashtags": "",
    }

    # 1. Empty 200 response -> uncertain outcome, no JSONDecodeError
    class Empty200:
        status_code = 200
        text = ""
        headers = {"Content-Type": "application/json"}
        def json(self):
            raise ValueError("Expecting value: line 1 column 1 (char 0)")

    monkeypatch.setattr(requests, "post", lambda *a, **kw: Empty200())
    res1 = adapter.publish(post, safe_mode=False)
    assert res1["success"] is False
    assert "uncertain" in res1["error"].lower()
    assert "empty response body" in res1["error"].lower()

    # 2. Empty 500 error response
    class Empty500:
        status_code = 500
        text = "   "
        headers = {"Content-Type": "text/plain"}
        def json(self):
            raise ValueError("Expecting value")

    monkeypatch.setattr(requests, "post", lambda *a, **kw: Empty500())
    res2 = adapter.publish(post, safe_mode=False)
    assert res2["success"] is False
    assert "http 500" in res2["error"].lower()

    # 3. Non-JSON HTML response
    class HtmlResp:
        status_code = 502
        text = "<html>Bad Gateway</html>"
        headers = {"Content-Type": "text/html"}
        def json(self):
            raise ValueError("Expecting value")

    monkeypatch.setattr(requests, "post", lambda *a, **kw: HtmlResp())
    res3 = adapter.publish(post, safe_mode=False)
    assert res3["success"] is False
    assert "non-json response" in res3["error"].lower()
    assert "http 502" in res3["error"].lower()

    # 4. Timeout exception
    def raise_timeout(*a, **kw):
        raise requests.exceptions.Timeout("read timed out")

    monkeypatch.setattr(requests, "post", raise_timeout)
    res4 = adapter.publish(post, safe_mode=False)
    assert res4["success"] is False
    assert "timed out" in res4["error"].lower()


def test_facebook_108mb_chunked_resumable_upload_flow(isolated_fb_db, monkeypatch):
    FacebookService.connect_page("page_123", "Gokul Astro", "tok_valid")
    database.set_setting("safe_test_mode", "false")
    video_path = _create_dummy_video(isolated_fb_db, "viruchigam_large.mp4")
    adapter = scheduler_service.FacebookPageAdapter()
    # Simulate 108 MB file size without allocating 108 MB on disk
    monkeypatch.setattr(os.path, "getsize", lambda p: 112_992_203)

    phases = []

    class FakeResp:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.text = str(payload)
            self.headers = {"Content-Type": "application/json"}

        def json(self):
            return self._payload

    def fake_post(url, data=None, files=None, timeout=None):
        phase = (data or {}).get("upload_phase")
        phases.append(phase)
        if phase == "start":
            return FakeResp(200, {"upload_session_id": "sess_108", "video_id": "fb_vid_108", "start_offset": "0", "end_offset": "50000000"})
        if phase == "transfer":
            off = int(data["start_offset"])
            if off == 0:
                return FakeResp(200, {"start_offset": "50000000", "end_offset": "112992203"})
            return FakeResp(200, {"start_offset": "112992203", "end_offset": "112992203"})
        if phase == "finish":
            assert data.get("title") == "GSP Phase 5C Facebook Publishing Test"
            return FakeResp(200, {"success": True})
        raise AssertionError(f"Unexpected phase: {phase}")

    monkeypatch.setattr(requests, "post", fake_post)
    res = adapter.publish(
        {
            "id": 2,
            "platform": "facebook",
            "account_key": "facebook:page_123",
            "media_path": video_path,
            "original_filename": "viruchigam_large.mp4",
            "title": "GSP Phase 5C Facebook Publishing Test",
            "caption": "Controlled Facebook publishing verification.",
            "hashtags": "",
        },
        safe_mode=False,
    )
    assert res["success"] is True
    assert res["external_post_id"] == "fb_vid_108"
    assert res["permalink"] == "https://www.facebook.com/page_123/videos/fb_vid_108/"
    assert phases == ["start", "transfer", "finish"]
