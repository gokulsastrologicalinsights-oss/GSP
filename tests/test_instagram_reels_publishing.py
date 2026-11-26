from datetime import datetime
import os
import pytest
import requests

import database
import scheduler_service
from instagram_service import InstagramService


@pytest.fixture()
def isolated_ig_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_ig_pub.db"
    monkeypatch.setenv("GSP_DB_PATH", str(db_file))
    database.init_db()
    return tmp_path


def _create_dummy_video(tmp_path, name="aries.mp4"):
    p = tmp_path / name
    p.write_bytes(b"FAKE_IG_REEL_BYTES")
    return str(p)


def test_ig_safe_testing_mode_blocks_real_requests(isolated_ig_db, monkeypatch):
    video_path = _create_dummy_video(isolated_ig_db)
    called = []

    def fail_if_called(*args, **kwargs):
        called.append(True)
        raise AssertionError("Real HTTP request should not be made in Safe Testing Mode")

    monkeypatch.setattr(requests, "post", fail_if_called)
    monkeypatch.setattr(requests, "get", fail_if_called)
    database.set_setting("safe_test_mode", "true")

    scheduler_service.schedule_multichannel_batch(
        accounts=[{"account_key": "instagram:ig_1", "platform": "instagram"}],
        category="Weekly Rasi Palan",
        items=[{"original_filename": "aries.mp4", "media_path": video_path, "file_size_bytes": 18, "video_id": "ig_safe"}],
        start_from=datetime(2026, 1, 1, 8, 0, 0),
    )
    res = scheduler_service.run_pending_scheduled_posts(now=datetime(2026, 1, 2, 12, 0, 0))
    assert res["processed"] == 1
    assert called == []
    assert scheduler_service.get_scheduled_posts()[0]["status"] == "published_safe_mode"
    assert os.path.exists(video_path)


def test_ig_reels_mocked_container_poll_publish_and_permalink(isolated_ig_db, monkeypatch):
    video_path = _create_dummy_video(isolated_ig_db)
    InstagramService.connect_account("ig_999", "Gokul Astro IG", "ig_tok_valid")
    database.set_setting("safe_test_mode", "false")

    adapter = scheduler_service.get_platform_adapter("instagram")
    calls = []

    class MockResp:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.text = str(payload)

        def json(self):
            return self._payload

    def mock_post(url, data=None, timeout=None):
        calls.append(("POST", url, data))
        if url.endswith("/media"):
            return MockResp(200, {"id": "cont_111"})
        if url.endswith("/media_publish"):
            return MockResp(200, {"id": "ig_media_222"})
        raise AssertionError(f"Unexpected POST {url}")

    def mock_get(url, params=None, timeout=None):
        calls.append(("GET", url, params))
        if url.endswith("/cont_111"):
            return MockResp(200, {"status_code": "FINISHED"})
        if url.endswith("/ig_media_222"):
            return MockResp(200, {"permalink": "https://www.instagram.com/reel/ig_media_222/"})
        raise AssertionError(f"Unexpected GET {url}")

    monkeypatch.setattr(requests, "post", mock_post)
    monkeypatch.setattr(requests, "get", mock_get)

    result = adapter.publish(
        {
            "id": 1,
            "account_key": "instagram:ig_999",
            "media_path": video_path,
            "original_filename": "aries.mp4",
            "public_media_url": "https://cdn.example.com/aries.mp4",
            "caption": "Aries Reel",
            "hashtags": "#Aries #Reels",
        },
        safe_mode=False,
    )
    assert result["success"] is True
    assert result["status"] == "published"
    assert result["external_post_id"] == "ig_media_222"
    assert result["permalink"] == "https://www.instagram.com/reel/ig_media_222/"
    assert calls[0][1] == "https://graph.facebook.com/v27.0/ig_999/media"
    assert calls[0][2]["media_type"] == "REELS"
    assert "Aries Reel" in calls[0][2]["caption"]
    assert "#Aries #Reels" in calls[0][2]["caption"]
    assert os.path.exists(video_path)


def test_ig_validation_and_local_url_limitation_and_error_handling(isolated_ig_db, monkeypatch):
    InstagramService.connect_account("ig_999", "Gokul Astro IG", "ig_tok_valid")
    database.set_setting("safe_test_mode", "false")
    adapter = scheduler_service.get_platform_adapter("instagram")

    # Missing local file
    r_miss = adapter.publish({"id": 1, "account_key": "instagram:ig_999", "media_path": "D:/missing/reel.mp4"}, safe_mode=False)
    assert r_miss["success"] is False
    assert "missing or unreadable" in r_miss["error"].lower()

    # Local-only file without public_media_url
    video_path = _create_dummy_video(isolated_ig_db, "taurus.mp4")
    r_nourl = adapter.publish({"id": 2, "account_key": "instagram:ig_999", "media_path": video_path, "original_filename": "taurus.mp4"}, safe_mode=False)
    assert r_nourl["success"] is False
    assert "publicly accessible video_url" in r_nourl["error"].lower()
