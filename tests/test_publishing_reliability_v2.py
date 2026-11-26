from datetime import datetime
import pytest

import database
import scheduler_service


@pytest.fixture()
def isolated_rel_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_rel.db"
    monkeypatch.setenv("GSP_DB_PATH", str(db_file))
    database.init_db()
    return tmp_path


def test_error_classification_and_retry_backoff_and_exhaustion(isolated_rel_db, monkeypatch):
    database.set_setting("safe_test_mode", "false")
    scheduler_service.schedule_multichannel_batch(
        accounts=[{"account_key": "facebook:p1", "platform": "facebook"}],
        category="Weekly Rasi Palan",
        items=[{"original_filename": "aries.mp4", "media_path": "/tmp/aries.mp4", "file_size_bytes": 100, "video_id": "v_rel_1"}],
        start_from=datetime(2026, 1, 1, 8, 0, 0),
    )

    # Simulate transient network error -> retry_waiting with next_retry_at
    monkeypatch.setattr(
        scheduler_service.PLATFORM_ADAPTERS["facebook"],
        "publish",
        lambda post, safe_mode=True: {"success": False, "status": "failed", "error": "Connection timeout"},
    )
    scheduler_service.run_pending_scheduled_posts(now=datetime(2026, 1, 2, 12, 0, 0))
    p = scheduler_service.get_scheduled_posts()[0]
    assert p["status"] == "retry_waiting"
    assert p["error_category"] == "network_error"
    assert p["attempt_count"] == 1
    assert p["next_retry_at"] is not None

    # Simulate auth_expired -> auth_required (no retry)
    monkeypatch.setattr(
        scheduler_service.PLATFORM_ADAPTERS["facebook"],
        "publish",
        lambda post, safe_mode=True: {"success": False, "status": "failed", "error": "Session has expired (code 190)"},
    )
    scheduler_service.retry_scheduled_post(p["id"])
    scheduler_service.run_pending_scheduled_posts(now=datetime(2026, 1, 2, 13, 0, 0))
    p2 = scheduler_service.get_scheduled_posts()[0]
    assert p2["status"] == "auth_required"
    assert p2["error_category"] == "auth_expired"


def test_restart_recovery_and_cancelled_protection(isolated_rel_db):
    scheduler_service.schedule_multichannel_batch(
        accounts=[
            {"account_key": "facebook:p1", "platform": "facebook"},
            {"account_key": "instagram:i1", "platform": "instagram"},
            {"account_key": "youtube:y1", "platform": "youtube"},
        ],
        category="Weekly Rasi Palan",
        items=[{"original_filename": "taurus.mp4", "media_path": "/tmp/taurus.mp4", "file_size_bytes": 100, "video_id": "v_rec_1"}],
        start_from=datetime(2026, 1, 1, 8, 0, 0),
    )
    posts = {p["platform"]: p for p in scheduler_service.get_scheduled_posts()}

    conn = database.get_connection()
    conn.execute("UPDATE scheduled_posts SET status = 'uploading' WHERE id = ?", (posts["facebook"]["id"],))
    conn.execute("UPDATE scheduled_posts SET status = 'cancelled' WHERE id = ?", (posts["instagram"]["id"],))
    conn.execute("UPDATE scheduled_posts SET status = 'published_safe_mode' WHERE id = ?", (posts["youtube"]["id"],))
    conn.commit()
    conn.close()

    rec = scheduler_service.recover_interrupted_jobs(now=datetime(2026, 1, 2, 10, 0, 0))
    assert rec["recovered"] == 1

    after = {p["platform"]: p for p in scheduler_service.get_scheduled_posts()}
    assert after["facebook"]["status"] == "retry_waiting"
    assert after["instagram"]["status"] == "cancelled"
    assert after["youtube"]["status"] == "published_safe_mode"
