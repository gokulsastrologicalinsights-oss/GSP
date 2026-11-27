from datetime import datetime
import os
import pytest
import requests

import database
import scheduler_service
from youtube_service import YouTubeService


@pytest.fixture()
def isolated_yt_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_yt_pub.db"
    monkeypatch.setenv("GSP_DB_PATH", str(db_file))
    database.init_db()
    return tmp_path


def _create_dummy_video(tmp_path, name="aries.mp4"):
    p = tmp_path / name
    p.write_bytes(b"FAKE_YT_VIDEO_BYTES")
    return str(p)


def test_yt_safe_testing_mode_blocks_real_requests(isolated_yt_db, monkeypatch):
    video_path = _create_dummy_video(isolated_yt_db)
    called = []

    def fail_if_called(*args, **kwargs):
        called.append(True)
        raise AssertionError("Real HTTP request should not be made in Safe Testing Mode")

    monkeypatch.setattr(requests, "post", fail_if_called)
    monkeypatch.setattr(requests, "put", fail_if_called)
    database.set_setting("safe_test_mode", "true")

    scheduler_service.schedule_multichannel_batch(
        accounts=[{"account_key": "youtube:ch_1", "platform": "youtube"}],
        category="Weekly Rasi Palan",
        items=[{"original_filename": "aries.mp4", "media_path": video_path, "file_size_bytes": 19, "video_id": "yt_safe"}],
        start_from=datetime(2026, 1, 1, 8, 0, 0),
    )
    res = scheduler_service.run_pending_scheduled_posts(now=datetime(2026, 1, 2, 12, 0, 0))
    assert res["processed"] == 1
    assert called == []
    assert scheduler_service.get_scheduled_posts()[0]["status"] == "published_safe_mode"
    assert os.path.exists(video_path)


def test_yt_resumable_upload_default_private_and_metadata(isolated_yt_db, monkeypatch):
    video_path = _create_dummy_video(isolated_yt_db)
    YouTubeService.connect_account("ch_123", "Gokul Astro YT", "yt_access_tok", "yt_refresh_tok")
    database.set_setting("safe_test_mode", "false")

    adapter = scheduler_service.get_platform_adapter("youtube")
    captured = {}

    class MockInitResp:
        status_code = 200
        headers = {"Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=sess_1"}
        text = ""

    class MockPutResp:
        status_code = 200
        text = '{"id": "yt_vid_777"}'

        def json(self):
            return {"id": "yt_vid_777"}

    def mock_post(url, params=None, headers=None, json=None, timeout=None):
        captured["init_url"] = url
        captured["params"] = params
        captured["metadata"] = json
        return MockInitResp()

    def mock_put(url, headers=None, data=None, timeout=None):
        captured["put_url"] = url
        captured["put_headers"] = headers
        return MockPutResp()

    monkeypatch.setattr(requests, "post", mock_post)
    monkeypatch.setattr(requests, "put", mock_put)

    res = adapter.publish(
        {
            "id": 1,
            "account_key": "youtube:ch_123",
            "media_path": video_path,
            "original_filename": "aries.mp4",
            "zodiac_tamil": "மேஷம்",
            "zodiac_english": "Aries",
            "category": "Weekly Rasi Palan",
            "caption": "Aries Weekly",
            "hashtags": "#Aries #Astrology",
        },
        safe_mode=False,
    )
    assert res["success"] is True
    assert res["status"] == "published"
    assert res["external_post_id"] == "yt_vid_777"
    assert res["permalink"] == "https://www.youtube.com/watch?v=yt_vid_777"
    assert captured["metadata"]["status"]["privacyStatus"] == "public"
    assert "Aries" in captured["metadata"]["snippet"]["tags"]
    assert "Aries Weekly" in captured["metadata"]["snippet"]["description"]
    assert os.path.exists(video_path)


def test_yt_quota_error_and_missing_file(isolated_yt_db, monkeypatch):
    YouTubeService.connect_account("ch_123", "Gokul Astro YT", "yt_access_tok", "yt_refresh_tok")
    database.set_setting("safe_test_mode", "false")
    adapter = scheduler_service.get_platform_adapter("youtube")

    r_miss = adapter.publish({"id": 1, "account_key": "youtube:ch_123", "media_path": "D:/missing/yt.mp4"}, safe_mode=False)
    assert r_miss["success"] is False
    assert "missing or unreadable" in r_miss["error"].lower()

    video_path = _create_dummy_video(isolated_yt_db, "taurus.mp4")

    class QuotaResp:
        status_code = 403
        text = '{"error": {"message": "The request cannot be completed because you have exceeded your quota."}}'

    monkeypatch.setattr(requests, "post", lambda *a, **kw: QuotaResp())
    r_quota = adapter.publish({"id": 2, "account_key": "youtube:ch_123", "media_path": video_path, "original_filename": "taurus.mp4"}, safe_mode=False)
    assert r_quota["success"] is False
    assert "403" in r_quota["error"]


def test_yt_resumable_session_recovery_after_restart(isolated_yt_db, monkeypatch):
    video_path = _create_dummy_video(isolated_yt_db, "gemini.mp4")
    YouTubeService.connect_account("ch_123", "Gokul Astro YT", "yt_access_tok", "yt_refresh_tok")
    database.set_setting("safe_test_mode", "false")
    adapter = scheduler_service.get_platform_adapter("youtube")

    # Simulate persisted session URL where server already completed upload (200)
    class CompletedStatusResp:
        status_code = 200

        def json(self):
            return {"id": "yt_recovered_888"}

    monkeypatch.setattr(requests, "put", lambda *a, **kw: CompletedStatusResp())
    res = adapter.publish(
        {
            "id": 99,
            "account_key": "youtube:ch_123",
            "media_path": video_path,
            "original_filename": "gemini.mp4",
            "upload_session_url": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=old_sess",
        },
        safe_mode=False,
    )
    assert res["success"] is True
    assert res["external_post_id"] == "yt_recovered_888"
    assert res["permalink"] == "https://www.youtube.com/watch?v=yt_recovered_888"
