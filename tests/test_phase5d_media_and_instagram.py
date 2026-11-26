"""Phase 5D mocked tests: temporary media token security, media-only server, and Instagram adapter."""
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import database
import media_server
import scheduler_service
import temp_media_service
from instagram_service import InstagramService


@pytest.fixture
def sample_media(tmp_path):
    root = tmp_path / "media_storage"
    root.mkdir()
    vid = root / "test_reel.mp4"
    vid.write_bytes(b"0123456789ABCDEF" * 4)
    return root, vid


def test_temp_media_token_security_and_lifecycle(sample_media):
    root, vid = sample_media
    tok = temp_media_service.create_temp_media_token(job_id=42, media_path=str(vid), ttl_seconds=60, allowed_root=str(root))
    assert temp_media_service.validate_temp_media_token(tok, expected_job_id=42) == str(vid.resolve())

    # Job mismatch, tampered, invalid
    assert temp_media_service.validate_temp_media_token(tok, expected_job_id=99) is None
    assert temp_media_service.validate_temp_media_token(tok + "x") is None
    assert temp_media_service.validate_temp_media_token("bad.token") is None

    # Idempotent revocation
    assert temp_media_service.revoke_temp_media_token(tok) is True
    assert temp_media_service.revoke_temp_media_token(tok) is True
    assert temp_media_service.validate_temp_media_token(tok) is None

    # Path traversal & missing file rejected
    with pytest.raises(ValueError):
        temp_media_service.create_temp_media_token(job_id=1, media_path=str(root / ".." / "secret.mp4"), allowed_root=str(root))
    with pytest.raises(ValueError):
        temp_media_service.create_temp_media_token(job_id=1, media_path=str(root / "missing.mp4"), allowed_root=str(root))

    # Expired token & cleanup
    exp_tok = temp_media_service.create_temp_media_token(job_id=7, media_path=str(vid), ttl_seconds=1, allowed_root=str(root))
    assert temp_media_service.cleanup_expired_tokens(now_ts=int(time.time()) + 100) >= 2
    assert temp_media_service.validate_temp_media_token(exp_tok) is None


def test_media_only_server_isolation_get_head_and_range(sample_media):
    root, vid = sample_media
    tok = temp_media_service.create_temp_media_token(job_id=10, media_path=str(vid), ttl_seconds=60, allowed_root=str(root))
    client = TestClient(media_server.media_app)

    # Isolation: no unrelated GSP routes exposed
    assert client.get("/").status_code == 404
    assert client.get("/api/status").status_code == 404
    assert client.get("/api/accounts/health").status_code == 404

    # HEAD
    h = client.head(f"/api/media/temp/{tok}")
    assert h.status_code == 200
    assert h.headers.get("accept-ranges") == "bytes"
    assert h.headers.get("content-length") == "64"

    # GET
    g = client.get(f"/api/media/temp/{tok}")
    assert g.status_code == 200
    assert g.content == b"0123456789ABCDEF" * 4

    # Range request
    r = client.get(f"/api/media/temp/{tok}", headers={"Range": "bytes=0-15"})
    assert r.status_code == 206
    assert r.content == b"0123456789ABCDEF"
    assert r.headers.get("content-range") == "bytes 0-15/64"

    # Revoked -> 403
    temp_media_service.revoke_temp_media_token(tok)
    assert client.get(f"/api/media/temp/{tok}").status_code == 403
    assert client.get("/api/media/temp/invalid.tok").status_code == 403


def test_instagram_adapter_uses_temp_https_url_polls_and_revokes(sample_media, monkeypatch):
    root, vid = sample_media
    monkeypatch.setattr(temp_media_service, "MEDIA_STORAGE_ROOT", str(root.resolve()))
    InstagramService.connect_account("ig_123", "IG Pro", "ig_tok")
    database.set_setting("safe_test_mode", "false")
    adapter = scheduler_service.InstagramProfessionalAdapter()
    post = {
        "id": 55,
        "platform": "instagram",
        "account_key": "instagram:ig_123",
        "media_path": str(vid),
        "original_filename": "test_reel.mp4",
        "caption": "Test Reel",
        "hashtags": "#test",
    }

    # Rejects missing / localhost base URL
    monkeypatch.delenv("GSP_PUBLIC_MEDIA_BASE_URL", raising=False)
    database.set_setting("public_media_base_url", "")
    r_missing = adapter.publish(post, safe_mode=False)
    assert r_missing["success"] is False
    assert "GSP_PUBLIC_MEDIA_BASE_URL" in r_missing["error"]

    monkeypatch.setenv("GSP_PUBLIC_MEDIA_BASE_URL", "https://localhost:8088")
    r_local = adapter.publish(post, safe_mode=False)
    assert r_local["success"] is False

    # Valid HTTPS base URL -> container -> poll FINISHED -> publish -> token revoked
    monkeypatch.setenv("GSP_PUBLIC_MEDIA_BASE_URL", "https://media.example.com")
    captured_urls = []

    def fake_post(url, data=None, timeout=None):
        if url.endswith("/media"):
            captured_urls.append(data["video_url"])
            return MagicMock(status_code=200, json=lambda: {"id": "cont_1"}, text='{"id":"cont_1"}')
        if url.endswith("/media_publish"):
            return MagicMock(status_code=200, json=lambda: {"id": "ig_med_1"}, text='{"id":"ig_med_1"}')
        raise AssertionError(url)

    def fake_get(url, params=None, timeout=None):
        if "cont_1" in url:
            return MagicMock(status_code=200, json=lambda: {"status_code": "FINISHED"}, text='{"status_code":"FINISHED"}')
        return MagicMock(status_code=200, json=lambda: {"permalink": "https://instagram.com/reel/ig_med_1"}, text="{}")

    with patch("requests.post", side_effect=fake_post), patch("requests.get", side_effect=fake_get):
        res = adapter.publish(post, safe_mode=False)

    assert res["success"] is True
    assert res["external_post_id"] == "ig_med_1"
    assert len(captured_urls) == 1
    assert captured_urls[0].startswith("https://media.example.com/api/media/temp/")
    tok = captured_urls[0].rsplit("/", 1)[-1]
    assert temp_media_service.validate_temp_media_token(tok) is None


def test_temp_media_token_survives_restart_and_stays_revoked(sample_media):
    import importlib
    root, vid = sample_media
    active_tok = temp_media_service.create_temp_media_token(job_id=101, media_path=str(vid), ttl_seconds=120, allowed_root=str(root))
    revoked_tok = temp_media_service.create_temp_media_token(job_id=102, media_path=str(vid), ttl_seconds=120, allowed_root=str(root))
    temp_media_service.revoke_temp_media_token(revoked_tok)

    # Simulate process restart by reloading temp_media_service
    importlib.reload(temp_media_service)

    assert temp_media_service.validate_temp_media_token(active_tok, expected_job_id=101) == str(vid.resolve())
    assert temp_media_service.validate_temp_media_token(revoked_tok, expected_job_id=102) is None


def test_instagram_polling_delays_429_timeout_and_container_reuse(sample_media, monkeypatch):
    root, vid = sample_media
    monkeypatch.setattr(temp_media_service, "MEDIA_STORAGE_ROOT", str(root.resolve()))
    InstagramService.connect_account("ig_123", "IG Pro", "ig_tok")
    database.set_setting("safe_test_mode", "false")
    monkeypatch.setenv("GSP_PUBLIC_MEDIA_BASE_URL", "https://media.example.com")

    adapter = scheduler_service.InstagramProfessionalAdapter()
    monkeypatch.setattr(adapter, "POLL_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(adapter, "POLL_TIMEOUT_SECONDS", 5)

    # 1. Existing container_id reused (no duplicate /media POST), IN_PROGRESS -> 429 -> FINISHED -> publish
    post_reuse = {
        "id": 77,
        "platform": "instagram",
        "account_key": "instagram:ig_123",
        "media_path": str(vid),
        "original_filename": "test_reel.mp4",
        "external_post_id": "existing_cont_77",
        "caption": "Reuse",
        "hashtags": "",
    }
    poll_seq = [
        MagicMock(status_code=200, json=lambda: {"status_code": "IN_PROGRESS"}, text='{"status_code":"IN_PROGRESS"}'),
        MagicMock(status_code=429, json=lambda: {"error": {"message": "rate limit"}}, text='{"error":{}}'),
        MagicMock(status_code=200, json=lambda: {"status_code": "FINISHED"}, text='{"status_code":"FINISHED"}'),
    ]
    post_calls = []

    def fake_post(url, data=None, timeout=None):
        post_calls.append(url)
        if url.endswith("/media_publish"):
            assert data["creation_id"] == "existing_cont_77"
            return MagicMock(status_code=200, json=lambda: {"id": "ig_pub_77"}, text='{"id":"ig_pub_77"}')
        raise AssertionError(f"Should not create new container: {url}")

    def fake_get(url, params=None, timeout=None):
        if "existing_cont_77" in url:
            return poll_seq.pop(0)
        return MagicMock(status_code=200, json=lambda: {"permalink": "https://instagram.com/reel/ig_pub_77"}, text="{}")

    with patch("requests.post", side_effect=fake_post), patch("requests.get", side_effect=fake_get):
        res = adapter.publish(post_reuse, safe_mode=False)
    assert res["success"] is True
    assert res["external_post_id"] == "ig_pub_77"
    assert len(post_calls) == 1

    # 2. Polling timeout -> no media_publish called
    monkeypatch.setattr(adapter, "POLL_TIMEOUT_SECONDS", 0)
    post_timeout = {**post_reuse, "id": 78, "external_post_id": "cont_timeout_78"}
    with patch("requests.post", side_effect=AssertionError("Must not publish on timeout")), \
         patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: {"status_code": "IN_PROGRESS"}, text='{"status_code":"IN_PROGRESS"}')):
        res_to = adapter.publish(post_timeout, safe_mode=False)
    assert res_to["success"] is False
    assert "timed out" in res_to["error"].lower()
    assert res_to["external_post_id"] == "cont_timeout_78"
