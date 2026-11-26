from datetime import datetime, timedelta
import os
import sqlite3
import tempfile
import pytest

import database
import scheduler_service


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_multichannel.db"
    monkeypatch.setenv("GSP_DB_PATH", str(db_file))
    database.init_db()
    return str(db_file)


def _make_12_items():
    names = [
        "aries.mp4", "taurus.mp4", "gemini.mp4", "cancer.mp4",
        "leo.mp4", "virgo.mp4", "libra.mp4", "scorpio.mp4",
        "sagittarius.mp4", "capricorn.mp4", "aquarius.mp4", "pisces.mp4",
    ]
    return [
        {
            "original_filename": n,
            "media_path": f"/tmp/{n}",
            "file_size_bytes": 1024 * 1024,
        }
        for n in names
    ]


def test_12_videos_1_2_3_channels_and_shared_timestamps(isolated_db):
    items = _make_12_items()
    start = datetime(2026, 12, 1, 8, 0, 0)

    # 1 channel -> 12 jobs
    r1 = scheduler_service.schedule_multichannel_batch(
        accounts=[{"account_key": "facebook:p1", "platform": "facebook"}],
        category="Weekly Rasi Palan",
        items=items,
        start_from=start,
    )
    assert r1["videos_count"] == 12
    assert r1["channels_count"] == 1
    assert r1["scheduled_count"] == 12

    # 2 channels -> 24 jobs
    r2 = scheduler_service.schedule_multichannel_batch(
        accounts=[
            {"account_key": "facebook:p2", "platform": "facebook"},
            {"account_key": "instagram:i2", "platform": "instagram"},
        ],
        category="Weekly Rasi Palan",
        items=items,
        start_from=start,
    )
    assert r2["scheduled_count"] == 24

    # 3 channels -> 36 jobs, identical timestamps per video
    r3 = scheduler_service.schedule_multichannel_batch(
        accounts=[
            {"account_key": "facebook:p3", "platform": "facebook"},
            {"account_key": "instagram:i3", "platform": "instagram"},
            {"account_key": "youtube:y3", "platform": "youtube"},
        ],
        category="Weekly Rasi Palan",
        items=items,
        start_from=start,
    )
    assert r3["scheduled_count"] == 36
    by_video = {}
    for p in r3["posts"]:
        by_video.setdefault(p["video_id"], set()).add(p["scheduled_at"])
    assert len(by_video) == 12
    for vid, times in by_video.items():
        assert len(times) == 1, f"Video {vid} had non-identical timestamps: {times}"


def test_duplicate_prevention_and_shared_reschedule_and_restart_persistence(isolated_db):
    items = [{"original_filename": "aries.mp4", "media_path": "/tmp/aries.mp4", "file_size_bytes": 1000, "video_id": "vid_aries_1"}]
    accounts = [
        {"account_key": "facebook:p1", "platform": "facebook"},
        {"account_key": "instagram:i1", "platform": "instagram"},
        {"account_key": "youtube:y1", "platform": "youtube"},
    ]
    start = datetime(2026, 12, 2, 8, 0, 0)
    r1 = scheduler_service.schedule_multichannel_batch(accounts=accounts, category="Weekly Rasi Palan", items=items, start_from=start)
    assert r1["scheduled_count"] == 3

    # Duplicate video_id + account_key should be prevented
    r_dup = scheduler_service.schedule_multichannel_batch(accounts=accounts, category="Weekly Rasi Palan", items=items, start_from=start)
    assert r_dup["scheduled_count"] == 0

    # Mark one job published_safe_mode, reschedule video -> published job must NOT change
    conn = database.get_connection()
    conn.execute("UPDATE scheduled_posts SET status = 'published_safe_mode' WHERE video_id = 'vid_aries_1' AND platform = 'facebook'")
    conn.commit()
    conn.close()

    updated, err = scheduler_service.reschedule_video("vid_aries_1", "2026-12-05T15:00:00")
    assert err is None
    by_plat = {p["platform"]: p for p in updated}
    assert by_plat["facebook"]["status"] == "published_safe_mode"
    assert by_plat["facebook"]["scheduled_at"] != "2026-12-05T15:00:00"
    assert by_plat["instagram"]["scheduled_at"] == "2026-12-05T15:00:00"
    assert by_plat["youtube"]["scheduled_at"] == "2026-12-05T15:00:00"

    # Restart persistence: re-query from fresh connection
    posts = scheduler_service.get_scheduled_posts()
    assert len(posts) == 3


def test_failure_isolation_and_safe_mode_publishing(isolated_db, monkeypatch):
    items = [{"original_filename": "taurus.mp4", "media_path": "/tmp/taurus.mp4", "file_size_bytes": 1000, "video_id": "vid_taurus_1"}]
    accounts = [
        {"account_key": "facebook:p1", "platform": "facebook"},
        {"account_key": "instagram:i1", "platform": "instagram"},
    ]
    past_start = datetime(2026, 1, 1, 8, 0, 0)
    scheduler_service.schedule_multichannel_batch(accounts=accounts, category="Weekly Rasi Palan", items=items, start_from=past_start)

    # Make instagram adapter fail, facebook succeed
    orig_ig_publish = scheduler_service.PLATFORM_ADAPTERS["instagram"].publish

    def fail_ig(post, safe_mode=True):
        raise RuntimeError("Simulated IG error")

    monkeypatch.setattr(scheduler_service.PLATFORM_ADAPTERS["instagram"], "publish", fail_ig)
    res = scheduler_service.run_pending_scheduled_posts(now=datetime(2026, 1, 2, 12, 0, 0))
    assert res["processed"] == 2
    assert res["safe_mode"] is True

    posts = {p["platform"]: p for p in scheduler_service.get_scheduled_posts()}
    assert posts["facebook"]["status"] == "published_safe_mode"
    assert posts["facebook"]["external_post_id"] is not None
    assert posts["facebook"]["attempt_count"] == 1
    assert posts["instagram"]["status"] == "retry_waiting"
    assert "Simulated IG error" in posts["instagram"]["error_message"]
    assert posts["instagram"]["attempt_count"] == 1

    monkeypatch.setattr(scheduler_service.PLATFORM_ADAPTERS["instagram"], "publish", orig_ig_publish)
