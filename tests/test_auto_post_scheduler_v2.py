from datetime import datetime, timedelta
from fastapi.testclient import TestClient

import main
import scheduler_service


def test_tamil_and_english_filename_detection():
    samples = [
        ("மேஷம்.mp4", 1),
        ("Mesham_weekly.mp4", 1),
        ("Aries.mp4", 1),
        ("ரிஷபம்.mp4", 2),
        ("Rishabam.mp4", 2),
        ("Taurus.mp4", 2),
        ("மிதுனம்.mp4", 3),
        ("Gemini.mp4", 3),
        ("கடகம்.mp4", 4),
        ("Cancer.mp4", 4),
        ("சிம்மம்.mp4", 5),
        ("Leo.mp4", 5),
        ("கன்னி.mp4", 6),
        ("Virgo.mp4", 6),
        ("துலாம்.mp4", 7),
        ("Libra.mp4", 7),
        ("விருச்சிகம்.mp4", 8),
        ("Scorpio.mp4", 8),
        ("தனுசு.mp4", 9),
        ("Sagittarius.mp4", 9),
        ("மகரம்.mp4", 10),
        ("Capricorn.mp4", 10),
        ("கும்பம்.mp4", 11),
        ("Aquarius.mp4", 11),
        ("மீனம்.mp4", 12),
        ("Pisces.mp4", 12),
    ]
    for fname, expected_idx in samples:
        res = scheduler_service.detect_zodiac_from_filename(fname)
        assert res is not None, f"Failed to detect {fname}"
        assert res["index"] == expected_idx


def test_zodiac_sorting_and_missing_duplicate_detection():
    items = [
        {"original_filename": "Pisces.mp4", "zodiac_index": 12},
        {"original_filename": "Aries.mp4", "zodiac_index": 1},
        {"original_filename": "Mesham.mp4", "zodiac_index": 1},
    ]
    analysis = scheduler_service.analyze_batch_items(items)
    assert [i["zodiac_index"] for i in analysis["items"]] == [1, 1, 12]
    assert len(analysis["duplicate_signs"]) == 1
    assert analysis["duplicate_signs"][0]["index"] == 1
    assert len(analysis["missing_signs"]) == 10
    assert analysis["is_complete_12"] is False


def test_deterministic_caption_generation():
    for cat in scheduler_service.BATCH_CATEGORIES:
        gen = scheduler_service.generate_caption_and_hashtags(1, cat)
        assert "மேஷம்" in gen["caption"]
        assert "Aries" in gen["caption"]
        assert "#மேஷம்" in gen["hashtags"]
        assert "#Aries" in gen["hashtags"]


def test_platform_media_validation():
    ok_fb, _ = scheduler_service.validate_platform_media("facebook", "aries.mp4", 1024)
    assert ok_fb is True

    ok_ig, err_ig = scheduler_service.validate_platform_media("instagram", "aries.avi", 1024)
    assert ok_ig is False
    assert "Instagram" in err_ig

    ok_ig_dur, err_ig_dur = scheduler_service.validate_platform_media("instagram", "aries.mp4", 1024, duration_seconds=120.0)
    assert ok_ig_dur is False
    assert "90s" in err_ig_dur


def test_bulk_upload_schedule_reschedule_and_persistence(tmp_path):
    client = TestClient(main.app)

    # 1. Configure posting slots for facebook:page_1
    slots_res = client.post(
        "/api/auto-post/slots",
        json={
            "account_key": "facebook:page_1",
            "slots": [
                {"day_of_week": -1, "slot_time": "11:00"},
                {"day_of_week": -1, "slot_time": "14:00"},
            ],
        },
    )
    assert slots_res.status_code == 200
    assert len(slots_res.json()["slots"]) == 2

    # 2. Bulk upload 12 videos (out of order, mixed Tamil/English)
    filenames = [
        "Pisces.mp4",
        "மேஷம்.mp4",
        "Taurus.mp4",
        "மிதுனம்.mp4",
        "Cancer.mp4",
        "Leo.mp4",
        "Kanni.mp4",
        "Libra.mp4",
        "Viruchigam.mp4",
        "Dhanusu.mp4",
        "Magaram.mp4",
        "Kumbam.mp4",
    ]
    files = [("files", (fn, b"fake-video-bytes", "video/mp4")) for fn in filenames]
    up_res = client.post("/api/auto-post/upload-batch?category=Weekly%20Rasi%20Palan", files=files)
    assert up_res.status_code == 200
    up_data = up_res.json()
    assert up_data["is_complete_12"] is True
    assert [i["zodiac_index"] for i in up_data["items"]] == list(range(1, 13))

    # 3. One-click schedule all 12 videos
    sched_res = client.post(
        "/api/auto-post/schedule-batch",
        json={
            "account_key": "facebook:page_1",
            "platform": "facebook",
            "category": "Weekly Rasi Palan",
            "batch_id": up_data["batch_id"],
            "items": up_data["items"],
        },
    )
    assert sched_res.status_code == 200
    sched_data = sched_res.json()
    assert sched_data["scheduled_count"] == 12
    posts = sched_data["posts"]

    # 4. Account-specific queue separation: instagram:ig_1 has 0 posts
    ig_posts = client.get("/api/auto-post/posts?account_key=instagram:ig_1").json()["posts"]
    assert len(ig_posts) == 0

    # 5. Drag-and-drop rescheduling & slot conflict detection
    post1 = posts[0]
    post2 = posts[1]
    conflict_res = client.put(
        f"/api/auto-post/posts/{post2['id']}/reschedule",
        json={"scheduled_at": post1["scheduled_at"]},
    )
    assert conflict_res.status_code == 409

    free_time = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%dT10:00:00")
    ok_res = client.put(
        f"/api/auto-post/posts/{post2['id']}/reschedule",
        json={"scheduled_at": free_time},
    )
    assert ok_res.status_code == 200
    assert ok_res.json()["post"]["scheduled_at"] == free_time

    # 6. Persistent background scheduler + duplicate job prevention
    future_now = datetime.now() + timedelta(days=40)
    run1 = scheduler_service.run_pending_scheduled_posts(now=future_now)
    assert run1["processed"] == 12
    assert run1["safe_mode"] is True

    # Running again must process 0 (no duplicate publishing)
    run2 = scheduler_service.run_pending_scheduled_posts(now=future_now)
    assert run2["processed"] == 0
