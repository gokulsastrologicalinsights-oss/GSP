"""Phase 5A tests: startup recovery integration, Safe Testing Mode UI, and publishing filters."""
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import database
import main
import scheduler_service


def _insert_post(status: str, platform: str = "facebook", attempt_count: int = 0) -> int:
    conn = database.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO scheduled_posts (
                original_filename, media_path,
                zodiac_index, zodiac_tamil, zodiac_english, category,
                caption, hashtags, scheduled_at, status, platform, account_key, attempt_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "test_video.mp4",
                "uploads/test_video.mp4",
                0,
                "மேஷம்",
                "Aries",
                "daily",
                "Test caption",
                "#test",
                "2026-01-01T09:00:00",
                status,
                platform,
                "default",
                attempt_count,
            ),
        )
        post_id = cursor.lastrowid
        conn.commit()
        return post_id
    finally:
        conn.close()


def test_startup_recovery_executes_once_after_init_and_before_scheduler(monkeypatch):
    call_order = []

    orig_init_db = database.init_db
    orig_recover = scheduler_service.recover_interrupted_jobs

    def tracked_init_db():
        call_order.append("init_db")
        return orig_init_db()

    def tracked_recover(*args, **kwargs):
        call_order.append("recover_interrupted_jobs")
        return orig_recover(*args, **kwargs)

    async def fake_loop():
        call_order.append("scheduler_loop")

    monkeypatch.setattr(database, "init_db", tracked_init_db)
    monkeypatch.setattr(scheduler_service, "recover_interrupted_jobs", tracked_recover)
    monkeypatch.setattr(main, "_auto_post_scheduler_loop", fake_loop)

    with TestClient(main.app) as client:
        res = client.get("/api/status")
        assert res.status_code == 200

    assert call_order.count("recover_interrupted_jobs") == 1
    assert call_order.index("init_db") < call_order.index("recover_interrupted_jobs")
    assert call_order.index("recover_interrupted_jobs") < call_order.index("scheduler_loop")


def test_startup_recovery_handles_exception_safely(monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise RuntimeError("simulated recovery failure")

    monkeypatch.setattr(scheduler_service, "recover_interrupted_jobs", boom)

    with caplog.at_level("ERROR"):
        with TestClient(main.app) as client:
            res = client.get("/api/status")
            assert res.status_code == 200

    assert "Startup recovery failed" in caplog.text


def test_startup_recovery_preserves_published_and_cancelled_jobs():
    pub_id = _insert_post("published")
    safe_pub_id = _insert_post("published_safe_mode")
    cancel_id = _insert_post("cancelled")
    interrupted_id = _insert_post("uploading", attempt_count=1)

    with TestClient(main.app) as client:
        assert client.get("/api/status").status_code == 200

    conn = database.get_connection()
    rows = {
        r["id"]: r["status"]
        for r in conn.execute("SELECT id, status FROM scheduled_posts").fetchall()
    }
    conn.close()

    assert rows[pub_id] == "published"
    assert rows[safe_pub_id] == "published_safe_mode"
    assert rows[cancel_id] == "cancelled"
    assert rows[interrupted_id] == "retry_waiting"


def test_safe_testing_mode_banner_reflects_backend_config():
    database.set_setting("safe_test_mode", "true")
    with TestClient(main.app) as client:
        assert client.get("/api/status").json()["safe_test_mode"] is True

    database.set_setting("safe_test_mode", "false")
    with TestClient(main.app) as client:
        assert client.get("/api/status").json()["safe_test_mode"] is False

    database.set_setting("safe_test_mode", "true")

    html = Path("static/index.html").read_text(encoding="utf-8")
    js = Path("static/app.js").read_text(encoding="utf-8")
    assert "scheduler-safe-mode-banner" in html
    assert "SAFE TESTING MODE – LIVE PUBLISHING DISABLED" in html
    assert "SAFE TESTING MODE – LIVE PUBLISHING DISABLED" in js
    assert "LIVE PUBLISHING ENABLED – POSTS WILL BE SENT TO CONNECTED PLATFORMS" in js


def test_publishing_filters_retry_waiting_and_auth_required():
    rw_id = _insert_post("retry_waiting", platform="facebook")
    ar_id = _insert_post("auth_required", platform="instagram")
    sched_id = _insert_post("scheduled", platform="youtube")

    with TestClient(main.app) as client:
        rw_res = client.get("/api/auto-post/posts", params={"status": "retry_waiting"})
        assert rw_res.status_code == 200
        rw_ids = [p["id"] for p in rw_res.json()["posts"]]
        assert rw_id in rw_ids
        assert ar_id not in rw_ids
        assert sched_id not in rw_ids

        ar_res = client.get("/api/auto-post/posts", params={"status": "auth_required"})
        assert ar_res.status_code == 200
        ar_ids = [p["id"] for p in ar_res.json()["posts"]]
        assert ar_id in ar_ids
        assert rw_id not in ar_ids
        assert sched_id not in ar_ids

    html = Path("static/index.html").read_text(encoding="utf-8")
    assert 'value="retry_waiting"' in html
    assert 'value="auth_required"' in html
    assert "summary-count-retry-waiting" in html
    assert "summary-count-auth-required" in html
