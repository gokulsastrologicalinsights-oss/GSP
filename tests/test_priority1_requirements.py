"""Focused tests for GSP Priority 1 Automatic Comment Reply Requirements."""
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import database
import nlp_detector
from facebook_service import FacebookService
from instagram_service import InstagramService
from youtube_service import YouTubeService


# --- A. Language Detection Tests ---
def test_language_detection_tamil_english_tanglish_mixed_emoji_unsupported():
    assert nlp_detector.detect_language("நல்ல பதிவு") == "ta"
    assert nlp_detector.detect_language("மிகவும் அருமை") == "ta"
    assert nlp_detector.detect_language("Good video") == "en"
    assert nlp_detector.detect_language("Very useful") == "en"
    assert nlp_detector.detect_language("Vanakkam romba nalla irukku") == "tanglish"
    assert nlp_detector.detect_language("Super ah irukku") == "tanglish"
    # Mixed Tamil-English
    assert nlp_detector.detect_language("நல்ல பதிவு super") == "ta"
    # Emoji-only appreciation
    assert nlp_detector.detect_language("🙏🙏❤️") == "emoji"
    # Unsupported languages (Hindi, Arabic, Cyrillic)
    assert nlp_detector.detect_language("बहुत अच्छा वीडियो") == "unsupported"
    assert nlp_detector.detect_language("جميل جدا") == "unsupported"


# --- B. Classification Tests ---
def test_classification_only_praise_and_emoji_reply_ready():
    # Eligible
    for msg in ["Good video", "நல்ல பதிவு", "Super ah irukku", "🙏🙏❤️"]:
        _, _, reply, status, tpl_id, _ = nlp_detector.analyze_comment_detailed(msg)
        assert status == "reply_ready", f"Expected reply_ready for {msg}"
        assert reply is not None
        assert tpl_id is not None

    # Must go to manual review
    review_cases = [
        "When will I get married? My rasi is Mesham",
        "என் ஜாதகம் பார்க்க கட்டணம் எவ்வளவு?",
        "Looking for bride matrimony alliance",
        "What is the consultation fee?",
        "How to contact you?",
        "This is a scam and fraud",
        "Worst video waste of time",
        "Very bad, not useful",
        "Check out https://spam.example.com",
        "बहुत अच्छा",
        "Okay",
    ]
    for msg in review_cases:
        _, _, reply, status, tpl_id, reason = nlp_detector.analyze_comment_detailed(msg)
        assert status == "review_required", f"Expected review_required for {msg}, got {status}"
        assert reply is None
        assert tpl_id is None
        assert reason is not None


# --- C. Six Approved Templates & Repetition Prevention ---
def test_six_approved_templates_and_no_repetition():
    all_templates = [t for group in nlp_detector.APPROVED_TEMPLATES.values() for t in group]
    assert len(all_templates) == 6

    # Language matching
    lang, _, reply_ta, _, tpl_ta, _ = nlp_detector.analyze_comment_detailed("நல்ல பதிவு")
    assert lang == "ta"
    assert tpl_ta.startswith("ta_")
    assert any("\u0b80" <= ch <= "\u0bff" for ch in reply_ta)

    lang, _, reply_en, _, tpl_en, _ = nlp_detector.analyze_comment_detailed("Good video")
    assert lang == "en"
    assert tpl_en.startswith("en_")
    assert not any("\u0b80" <= ch <= "\u0bff" for ch in reply_en)

    # Repetition prevention for same commenter
    _, _, _, _, second_tpl, _ = nlp_detector.analyze_comment_detailed("Good video", last_template_id=tpl_en)
    assert second_tpl != tpl_en


# --- D. Backend Rate Limits & Cooldowns ---
def test_rate_limits_interval_hourly_daily_cooldown_and_concurrency():
    conn = database.get_connection()
    conn.execute("DELETE FROM reply_rate_log")
    conn.commit()
    conn.close()

    now = 1_700_000_000.0

    # 1. First reply allowed
    ok, reason = database.check_and_reserve_rate_limit("facebook", "pg1", "c1", "user1", "en_1", now_ts=now)
    assert ok and reason is None

    # 2. Minimum 120s interval enforced
    ok, reason = database.check_and_reserve_rate_limit("facebook", "pg1", "c2", "user2", "en_1", now_ts=now + 60)
    assert not ok and reason == "rate_limit_min_interval_120s"

    # 3. Same commenter 24h cooldown enforced (even after 120s)
    ok, reason = database.check_and_reserve_rate_limit("facebook", "pg1", "c3", "user1", "en_2", now_ts=now + 200)
    assert not ok and reason == "rate_limit_commenter_24h"

    # 4. Hourly limit (30/hour): insert 29 more replies spaced 120s apart? 29*120 = 3480s < 3600s!
    conn = database.get_connection()
    c = conn.cursor()
    for i in range(2, 31):
        c.execute(
            "INSERT INTO reply_rate_log (platform, account_id, comment_id, commenter_key, template_id, replied_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("facebook", "pg1", f"ch_{i}", f"u_{i}", "en_1", now + i * 10),
        )
    conn.commit()
    conn.close()

    ok, reason = database.check_and_reserve_rate_limit("facebook", "pg1", "c31", "user31", "en_1", now_ts=now + 3500)
    assert not ok and reason == "rate_limit_hourly_30"

    # 5. Concurrent request protection: only 1 of 5 simultaneous requests should succeed
    conn = database.get_connection()
    conn.execute("DELETE FROM reply_rate_log")
    conn.commit()
    conn.close()

    def try_reserve(idx):
        return database.check_and_reserve_rate_limit("facebook", "pg1", f"conc_{idx}", f"cu_{idx}", "en_1", now_ts=now + 5000)

    with ThreadPoolExecutor(max_workers=5) as ex:
        results = list(ex.map(try_reserve, range(5)))
    successes = [r for r in results if r[0]]
    assert len(successes) == 1


# --- E. Safety Controls & Global Kill Switch ---
def test_global_kill_switch_and_safe_testing_mode():
    database.set_setting("auto_reply_enabled", "true")
    database.set_setting("ig_auto_reply_enabled", "true")
    database.set_setting("yt_auto_reply_enabled", "true")
    database.set_setting("safe_test_mode", "false")
    database.set_setting("global_kill_switch", "true")
    try:
        with patch.object(FacebookService, "send_reply") as mock_fb, \
             patch.object(InstagramService, "send_reply") as mock_ig, \
             patch.object(YouTubeService, "send_reply") as mock_yt:
            fb_res = FacebookService.process_and_reply_comment(
                {"id": "fb_ks_1", "post_id": "p1", "message": "Good video", "from": {"id": "u1", "name": "U1"}},
                "pg1", "tok"
            )
            ig_res = InstagramService.process_and_reply_comment(
                {"id": "ig_ks_1", "post_id": "p1", "text": "Good video", "from": {"id": "u1", "username": "U1"}},
                "ig1", "myig", "tok"
            )
            yt_res = YouTubeService.process_and_reply_comment(
                {"id": "yt_ks_1", "post_id": "v1", "text": "Good video", "author_name": "U1", "author_channel_id": "uc1"},
                "ch1", "MyCh", "tok"
            )
            assert fb_res["status"] == "review_required"
            assert ig_res["status"] == "review_required"
            assert yt_res["status"] == "review_required"
            mock_fb.assert_not_called()
            mock_ig.assert_not_called()
            mock_yt.assert_not_called()
    finally:
        database.set_setting("global_kill_switch", "false")
        database.set_setting("safe_test_mode", "true")
