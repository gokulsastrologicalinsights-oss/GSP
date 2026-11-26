from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import database
import scheduler_service


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_schedule.db"
    monkeypatch.setenv("GSP_DB_PATH", str(db_file))
    database.init_db()
    return db_file


def test_default_settings_and_persistence(isolated_db):
    settings = scheduler_service.get_posting_schedule_settings("facebook:default")
    assert settings["timezone"] == "Asia/Kolkata"
    assert settings["weekly_goal"] == 14
    assert settings["enabled_days"] == [0, 1, 2, 3, 4, 5, 6]

    updated = scheduler_service.save_posting_schedule_settings(
        "facebook:default",
        timezone="America/New_York",
        weekly_goal=25,
        enabled_days=[0, 2, 4],
    )
    assert updated["timezone"] == "America/New_York"
    assert updated["weekly_goal"] == 25
    assert updated["enabled_days"] == [0, 2, 4]

    # Re-read from DB to verify persistence
    reloaded = scheduler_service.get_posting_schedule_settings("facebook:default")
    assert reloaded == updated


def test_add_remove_slots_and_duplicate_prevention(isolated_db):
    scheduler_service.add_posting_slot("facebook:default", 0, "09:00")
    scheduler_service.add_posting_slot("facebook:default", 0, "09:00")  # duplicate
    slots = scheduler_service.get_posting_slots("facebook:default")
    assert len(slots) == 1
    assert slots[0]["day_of_week"] == 0
    assert slots[0]["slot_time"] == "09:00"

    assert scheduler_service.delete_posting_slot(slots[0]["id"]) is True
    assert scheduler_service.get_posting_slots("facebook:default") == []


def test_every_day_respects_enabled_days(isolated_db):
    scheduler_service.save_posting_schedule_settings(
        "instagram:default", enabled_days=[0, 1, 2]
    )
    slots = scheduler_service.add_posting_slot("instagram:default", -1, "18:30")
    assert sorted(s["day_of_week"] for s in slots) == [0, 1, 2]


def test_generate_posting_slots_modes(isolated_db):
    scheduler_service.save_posting_schedule_settings(
        "youtube:default", weekly_goal=10, enabled_days=[0, 1, 2, 3, 4]
    )
    even = scheduler_service.generate_posting_slots("youtube:default", "even")
    assert len(even) == 10  # 5 days * 2 slots

    periods = scheduler_service.generate_posting_slots("youtube:default", "periods")
    assert len(periods) == 15  # 5 days * 3 slots

    goal_slots = scheduler_service.generate_posting_slots("youtube:default", "goal")
    assert len(goal_slots) == 10

    cleared = scheduler_service.generate_posting_slots("youtube:default", "clear")
    assert cleared == []


def test_scheduler_skips_disabled_days_and_respects_weekly_goal_and_week_boundary(isolated_db):
    # Enable only Monday (0) and Tuesday (1), weekly goal = 2
    scheduler_service.save_posting_schedule_settings(
        "facebook:default",
        timezone="Asia/Kolkata",
        weekly_goal=2,
        enabled_days=[0, 1],
    )
    scheduler_service.save_posting_slots(
        "facebook:default",
        [
            {"day_of_week": 0, "slot_time": "09:00"},
            {"day_of_week": 0, "slot_time": "18:00"},
            {"day_of_week": 1, "slot_time": "09:00"},
        ],
    )
    # Start on Sunday 2026-11-29 23:30 IST (across midnight to Monday 2026-11-30)
    start = datetime(2026, 11, 29, 23, 30, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assigned = scheduler_service._compute_shared_available_slots(
        ["facebook:default"], count=3, start_from=start
    )
    # First 2 slots in week of Nov 30 (Mon 09:00, Mon 18:00), 3rd rolls over to next week (Mon Dec 7 09:00)
    assert assigned == [
        "2026-11-30T09:00:00",
        "2026-11-30T18:00:00",
        "2026-12-07T09:00:00",
    ]
