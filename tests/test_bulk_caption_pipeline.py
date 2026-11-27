import os
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

import database
import scheduler_service


ALL_12_RASIS = [
    (1, "Mesham.mp4", "மேஷம்", "Aries"),
    (2, "Rishabam.mp4", "ரிஷபம்", "Taurus"),
    (3, "Midhunam.mp4", "மிதுனம்", "Gemini"),
    (4, "Kadagam.mp4", "கடகம்", "Cancer"),
    (5, "Simmam.mp4", "சிம்மம்", "Leo"),
    (6, "Kanni.mp4", "கன்னி", "Virgo"),
    (7, "Thulam.mp4", "துலாம்", "Libra"),
    (8, "Viruchigam.mp4", "விருச்சிகம்", "Scorpio"),
    (9, "Dhanusu.mp4", "தனுசு", "Sagittarius"),
    (10, "Magaram.mp4", "மகரம்", "Capricorn"),
    (11, "Kumbam.mp4", "கும்பம்", "Aquarius"),
    (12, "Meenam.mp4", "மீனம்", "Pisces"),
]


class TestBulkCaptionPipeline(unittest.TestCase):
    def test_all_12_rasi_filename_mappings(self):
        for idx, filename, tamil, english in ALL_12_RASIS:
            detected = scheduler_service.detect_zodiac_from_filename(filename)
            self.assertIsNotNone(detected, f"Failed to detect {filename}")
            self.assertEqual(detected["index"], idx)
            self.assertEqual(detected["tamil"], tamil)
            self.assertEqual(detected["english"], english)

    def test_individual_caption_contact_and_hashtags(self):
        seen_hashtags = set()
        for idx, _fn, tamil, english in ALL_12_RASIS:
            res = scheduler_service.generate_caption_and_hashtags(idx, "Monthly Rasi Palan")
            cap = res["caption"]
            tags = res["hashtags"]

            self.assertIn(tamil, cap)
            self.assertIn(english, cap)
            self.assertIn("Gokul's Astrological Insights", cap)
            self.assertIn("+91 94445 59071", cap)
            self.assertNotIn("Vivaham", cap)
            self.assertIn("\n\n", cap)

            tag_list = tags.split()
            self.assertGreaterEqual(len(tag_list), 10)
            self.assertLessEqual(len(tag_list), 15)
            self.assertIn(f"#{tamil}", tag_list)
            self.assertIn(f"#{english}", tag_list)
            self.assertIn("#GokulsAstrologicalInsights", tag_list)
            seen_hashtags.add(tags)

        # All 12 Rasis must have distinct hashtag sets
        self.assertEqual(len(seen_hashtags), 12)

    def test_platform_specific_descriptions(self):
        res = scheduler_service.generate_caption_and_hashtags(1, "Monthly Rasi Palan")
        pd = res["platform_descriptions"]
        self.assertIn("youtube", pd)
        self.assertIn("facebook", pd)
        self.assertIn("instagram", pd)
        self.assertIn("+91 94445 59071", pd["youtube"])
        self.assertIn("#மேஷம்", pd["facebook"])
        self.assertLessEqual(len(pd["instagram"]), 2200)

        # Platform hashtag policy limits: FB <= 5, IG <= 15, YT <= 15
        fb_tags = [t for t in pd["facebook"].split() if t.startswith("#")]
        ig_tags = [t for t in pd["instagram"].split() if t.startswith("#")]
        yt_tags = [t for t in pd["youtube"].split() if t.startswith("#")]
        self.assertLessEqual(len(fb_tags), 5)
        self.assertLessEqual(len(ig_tags), 15)
        self.assertLessEqual(len(yt_tags), 15)

        # Long caption truncation only for Instagram
        long_cap = "அ" * 2500
        pd_long = scheduler_service.build_platform_descriptions(long_cap, "#மேஷம் #Aries")
        self.assertGreater(len(pd_long["youtube"]), 2500)
        self.assertLessEqual(len(pd_long["instagram"]), 2200)
        self.assertIn("#மேஷம்", pd_long["instagram"])

    def test_sqlite_persistence_and_no_overwrite_on_reschedule(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            def _get_conn():
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                return conn

            with patch.object(database, "get_connection", side_effect=_get_conn):
                conn = _get_conn()
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scheduled_posts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        batch_id TEXT,
                        account_key TEXT,
                        platform TEXT,
                        category TEXT,
                        original_filename TEXT,
                        media_path TEXT,
                        media_url TEXT,
                        zodiac_index INTEGER,
                        zodiac_tamil TEXT,
                        zodiac_english TEXT,
                        caption TEXT,
                        hashtags TEXT,
                        scheduled_at TEXT,
                        timezone TEXT DEFAULT 'Asia/Kolkata',
                        status TEXT DEFAULT 'scheduled',
                        error_message TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                gen = scheduler_service.generate_caption_and_hashtags(1, "Monthly Rasi Palan")
                conn.execute(
                    """
                    INSERT INTO scheduled_posts (
                        batch_id, account_key, platform, category, original_filename,
                        zodiac_index, zodiac_tamil, zodiac_english, caption, hashtags, scheduled_at, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "b1", "youtube:default", "youtube", "Monthly Rasi Palan", "Mesham.mp4",
                        1, "மேஷம்", "Aries", gen["caption"], gen["hashtags"], "2026-12-01T09:00:00", "scheduled"
                    ),
                )
                conn.commit()
                conn.close()

                custom_caption = "மேஷம் சிறப்பு பதிவு\n\nWhatsApp: +91 94445 59071"
                updated, err = scheduler_service.update_scheduled_post(1, {"caption": custom_caption})
                self.assertIsNone(err)
                self.assertEqual(updated["caption"], custom_caption)

                # Reschedule must not overwrite manually edited caption
                resched, err2 = scheduler_service.update_scheduled_post(1, {"scheduled_at": "2026-12-02T10:00:00"})
                self.assertIsNone(err2)
                self.assertEqual(resched["caption"], custom_caption)
                self.assertEqual(resched["scheduled_at"], "2026-12-02T10:00:00")
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_scheduling_performance_1_and_12_videos(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            def _get_conn():
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                return conn

            with patch.object(database, "get_connection", side_effect=_get_conn):
                conn = _get_conn()
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scheduled_posts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        batch_id TEXT,
                        account_key TEXT,
                        platform TEXT,
                        zodiac_index INTEGER,
                        zodiac_tamil TEXT,
                        zodiac_english TEXT,
                        category TEXT,
                        original_filename TEXT,
                        media_path TEXT,
                        thumbnail_path TEXT,
                        caption TEXT,
                        hashtags TEXT,
                        scheduled_at TEXT,
                        timezone TEXT DEFAULT 'Asia/Kolkata',
                        status TEXT DEFAULT 'scheduled',
                        error_message TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS posting_schedule_slots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        account_key TEXT,
                        day_of_week INTEGER,
                        time_slot TEXT,
                        enabled INTEGER DEFAULT 1
                    )
                    """
                )
                conn.commit()
                conn.close()

                with patch.object(
                    scheduler_service,
                    "_compute_next_available_slots",
                    side_effect=lambda ak, n, start_from=None: [f"2026-12-01T{9+i:02d}:00:00" for i in range(n)],
                ):
                    t0 = time.perf_counter()
                    res1 = scheduler_service.schedule_batch(
                        account_key="youtube:default",
                        platform="youtube",
                        category="Monthly Rasi Palan",
                        items=[{"original_filename": "Mesham.mp4", "media_path": "Mesham.mp4", "file_size_bytes": 1024}],
                    )
                    t1 = (time.perf_counter() - t0) * 1000
                    self.assertEqual(len(res1["posts"]), 1)

                    items12 = [
                        {"original_filename": fn, "media_path": fn, "file_size_bytes": 1024}
                        for _, fn, _, _ in ALL_12_RASIS
                    ]
                    t2 = time.perf_counter()
                    res12 = scheduler_service.schedule_batch(
                        account_key="youtube:default",
                        platform="youtube",
                        category="Monthly Rasi Palan",
                        items=items12,
                    )
                    t3 = (time.perf_counter() - t2) * 1000
                    self.assertEqual(len(res12["posts"]), 12)
                    print(f"\n[PERF] 1-post schedule_batch: {t1:.2f} ms | 12-post schedule_batch: {t3:.2f} ms")
                    self.assertLess(t1, 500)
                    self.assertLess(t3, 1000)
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)


if __name__ == "__main__":
    unittest.main()
