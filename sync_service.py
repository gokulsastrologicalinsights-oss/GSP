"""30-Minute Automatic Comment Sync & Account-Wise Smart Auto Reply Service."""
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import database
import nlp_detector
import reply_suggester

logger = logging.getLogger(__name__)

DEFAULT_SYNC_INTERVAL_MINUTES = 30
VALID_REPLY_MODES = ("MANUAL_APPROVAL", "AUTOMATIC_REPLY", "DISABLED")

ELIGIBLE_AUTO_REPLY_INTENTS = {
    "Appreciation",
    "Greeting",
    "General enquiry",
    "Consultation enquiry",
}

MANDATORY_MANUAL_REVIEW_INTENTS = {
    "Complaint",
    "Negative feedback",
    "Spam",
    "Abusive content",
    "Threat",
    "Sensitive personal information",
}

IST_TZ = timezone(timedelta(hours=5, minutes=30))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(dt: Optional[datetime] = None) -> str:
    return (dt or _utc_now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        cleaned = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def to_ist_display(ts: Optional[str]) -> Optional[str]:
    dt = _parse_iso(ts)
    if not dt:
        return ts
    return dt.astimezone(IST_TZ).strftime("%Y-%m-%d %H:%M:%S IST")


def ensure_account_sync_states() -> List[Dict[str, Any]]:
    """Ensure every active connected account has a row in account_sync_state.
    New accounts default to MANUAL_APPROVAL and 30-minute auto-sync enabled.
    Existing accounts preserve their current reply_mode.
    """
    conn = database.get_connection()
    try:
        accounts = conn.execute(
            "SELECT platform, account_id, account_name FROM accounts WHERE is_active = 1"
        ).fetchall()
        now_str = _iso_utc()
        for acc in accounts:
            conn.execute(
                """
                INSERT OR IGNORE INTO account_sync_state (
                    platform, account_id, account_name,
                    auto_sync_enabled, sync_interval_minutes, reply_mode,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 1, ?, 'MANUAL_APPROVAL', ?, ?)
                """,
                (
                    acc["platform"],
                    acc["account_id"],
                    acc["account_name"],
                    DEFAULT_SYNC_INTERVAL_MINUTES,
                    now_str,
                    now_str,
                ),
            )
            conn.execute(
                "UPDATE account_sync_state SET account_name = ?, updated_at = ? WHERE platform = ? AND account_id = ?",
                (acc["account_name"], now_str, acc["platform"], acc["account_id"]),
            )
        conn.commit()
        return get_account_sync_states()
    finally:
        conn.close()


def get_account_sync_states() -> List[Dict[str, Any]]:
    conn = database.get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM account_sync_state ORDER BY platform, account_name"
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["last_successful_sync_ist"] = to_ist_display(d.get("last_successful_sync_at"))
            d["next_sync_ist"] = to_ist_display(d.get("next_sync_at"))
            result.append(d)
        return result
    finally:
        conn.close()


def update_account_sync_settings(
    platform: str,
    account_id: str,
    auto_sync_enabled: Optional[bool] = None,
    reply_mode: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Update sync or reply_mode for a single account without affecting others."""
    if reply_mode is not None and reply_mode not in VALID_REPLY_MODES:
        raise ValueError(f"Invalid reply_mode: {reply_mode}. Must be one of {VALID_REPLY_MODES}")

    ensure_account_sync_states()
    conn = database.get_connection()
    try:
        updates = ["updated_at = ?"]
        params: List[Any] = [_iso_utc()]
        if auto_sync_enabled is not None:
            updates.append("auto_sync_enabled = ?")
            params.append(1 if auto_sync_enabled else 0)
        if reply_mode is not None:
            updates.append("reply_mode = ?")
            params.append(reply_mode)
        params.extend([platform, account_id])
        conn.execute(
            f"UPDATE account_sync_state SET {', '.join(updates)} WHERE platform = ? AND account_id = ?",
            params,
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM account_sync_state WHERE platform = ? AND account_id = ?",
            (platform, account_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def claim_account_sync(platform: str, account_id: str) -> bool:
    """Atomically claim an account for syncing to prevent overlapping syncs."""
    now = _utc_now()
    stale_cutoff = _iso_utc(now - timedelta(minutes=15))
    conn = database.get_connection()
    try:
        cur = conn.execute(
            """
            UPDATE account_sync_state
            SET is_syncing = 1, sync_claimed_at = ?, updated_at = ?
            WHERE platform = ? AND account_id = ?
              AND (is_syncing = 0 OR sync_claimed_at IS NULL OR sync_claimed_at < ?)
            """,
            (_iso_utc(now), _iso_utc(now), platform, account_id, stale_cutoff),
        )
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


def release_account_sync(
    platform: str,
    account_id: str,
    sync_type: str,
    success: bool,
    cursor: Optional[str] = None,
    error: Optional[str] = None,
    comments_fetched: int = 0,
    comments_new: int = 0,
    auto_replies_sent: int = 0,
    manual_review_flagged: int = 0,
) -> None:
    now = _utc_now()
    now_str = _iso_utc(now)
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT sync_interval_minutes, failed_sync_count FROM account_sync_state WHERE platform = ? AND account_id = ?",
            (platform, account_id),
        ).fetchone()
        interval = (row["sync_interval_minutes"] if row else None) or DEFAULT_SYNC_INTERVAL_MINUTES
        prev_failures = (row["failed_sync_count"] if row else 0) or 0

        if success:
            next_sync = _iso_utc(now + timedelta(minutes=interval))
            conn.execute(
                """
                UPDATE account_sync_state
                SET is_syncing = 0,
                    sync_claimed_at = NULL,
                    last_sync_at = ?,
                    last_successful_sync_at = ?,
                    next_sync_at = ?,
                    cursor = COALESCE(?, cursor),
                    failed_sync_count = 0,
                    backoff_until = NULL,
                    last_error = NULL,
                    comments_processed = comments_processed + ?,
                    auto_replies_sent = auto_replies_sent + ?,
                    manual_review_count = manual_review_count + ?,
                    updated_at = ?
                WHERE platform = ? AND account_id = ?
                """,
                (
                    now_str,
                    now_str,
                    next_sync,
                    cursor,
                    comments_new,
                    auto_replies_sent,
                    manual_review_flagged,
                    now_str,
                    platform,
                    account_id,
                ),
            )
        else:
            failures = prev_failures + 1
            backoff_mins = min(interval * (2 ** (failures - 1)), 240)
            backoff_until = _iso_utc(now + timedelta(minutes=backoff_mins))
            conn.execute(
                """
                UPDATE account_sync_state
                SET is_syncing = 0,
                    sync_claimed_at = NULL,
                    last_sync_at = ?,
                    failed_sync_count = ?,
                    backoff_until = ?,
                    last_error = ?,
                    updated_at = ?
                WHERE platform = ? AND account_id = ?
                """,
                (now_str, failures, backoff_until, (error or "")[:500], now_str, platform, account_id),
            )

        conn.execute(
            """
            INSERT INTO sync_history (
                platform, account_id, sync_type, status,
                comments_fetched, comments_new, auto_replies_sent,
                manual_review_flagged, error_message, started_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                platform,
                account_id,
                sync_type,
                "success" if success else "failed",
                comments_fetched,
                comments_new,
                auto_replies_sent,
                manual_review_flagged,
                error,
                now_str,
                now_str,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def classify_comment_intent(comment_text: str) -> Tuple[str, str, float]:
    """Return (language, intent, confidence) for a comment."""
    text = (comment_text or "").strip()
    lower = text.lower()
    lang = nlp_detector.detect_language(text)
    if lang not in ("Tamil", "Tanglish", "English"):
        lang = "English"

    # High-risk / Mandatory Manual Review checks first
    if any(w in lower for w in ("kill", "murder", "threat", "destroy you", "beat you", "bomb")):
        return lang, "Threat", 0.95
    if any(w in lower for w in ("idiot", "stupid", "fraud", "scam", "cheat", "useless", "nonsense", "fuck", "shit")):
        return lang, "Abusive content", 0.92
    if re.search(r"\b\d{10}\b", text) or "@" in text and "." in text:
        return lang, "Sensitive personal information", 0.90
    if any(w in lower for w in ("buy followers", "http://", "https://", "whatsapp me at", "crypto", "earn money fast")):
        return lang, "Spam", 0.90
    if any(w in lower for w in ("complaint", "refund", "worst", "disappointed", "bad service", "not working", "cheated")):
        return lang, "Complaint", 0.88
    if any(w in lower for w in ("bad", "boring", "wrong", "disagree", "waste of time")):
        return lang, "Negative feedback", 0.82

    # Eligible low-risk categories
    if any(w in lower for w in ("consult", "appointment", "booking", "jathagam", "horoscope", "fees", "contact", "price")):
        return lang, "Consultation enquiry", 0.90
    if any(w in lower for w in ("?", "how", "when", "what", "where", "which", "eppadi", "eppo", "enna")):
        return lang, "General enquiry", 0.85
    if any(w in lower for w in ("hi", "hello", "vanakkam", "namaste", "good morning", "good evening")):
        return lang, "Greeting", 0.92
    if any(w in lower for w in ("thank", "thanks", "nandri", "super", "nice", "good", "great", "awesome", "love", "bless")):
        return lang, "Appreciation", 0.92

    # Fallback to nlp_detector
    detected = nlp_detector.analyze_comment_detailed(text)
    intent = detected.get("intent") or "General enquiry"
    return lang, intent, 0.70


def is_eligible_for_auto_reply(intent: str, confidence: float, comment_text: str) -> Tuple[bool, str]:
    """Determine if a comment is eligible for automatic reply."""
    if intent in MANDATORY_MANUAL_REVIEW_INTENTS:
        return False, f"Mandatory manual review for intent: {intent}"
    if intent not in ELIGIBLE_AUTO_REPLY_INTENTS:
        return False, f"Intent {intent} not in eligible auto-reply categories"
    if confidence < 0.75:
        return False, f"Low confidence ({confidence:.2f})"
    lower = (comment_text or "").lower()
    if any(w in lower for w in ("medical", "doctor", "legal", "court", "lawsuit", "stock", "invest", "loan")):
        return False, "Sensitive advice request requires manual review"
    if any(w in lower for w in ("my dob", "date of birth", "birth time", "predict my")):
        return False, "Personalized astrological prediction requires manual review"
    return True, "Eligible low-risk comment"


def _dispatch_platform_sync(platform: str) -> Dict[str, Any]:
    if platform == "facebook":
        from facebook_service import FacebookService
        return FacebookService.sync_facebook_comments()
    if platform == "instagram":
        from instagram_service import InstagramService
        return InstagramService.sync_instagram_comments()
    if platform == "youtube":
        from youtube_service import YouTubeService
        return YouTubeService.sync_youtube_comments()
    return {"success": False, "error": f"Unsupported platform: {platform}"}


def sync_account(platform: str, account_id: str, sync_type: str = "scheduled") -> Dict[str, Any]:
    """Synchronize a single account, process new comments, and respect reply_mode."""
    ensure_account_sync_states()
    if not claim_account_sync(platform, account_id):
        return {"success": False, "skipped": True, "reason": "Sync already in progress"}

    try:
        res = _dispatch_platform_sync(platform)
        if not res.get("success", True) and res.get("error"):
            release_account_sync(platform, account_id, sync_type=sync_type, success=False, error=res.get("error"))
            return {"success": False, "error": res.get("error")}

        comments_fetched = int(res.get("fetched", res.get("synced", 0)) or 0)
        comments_new = int(res.get("new", res.get("synced", 0)) or 0)
        cursor = res.get("cursor")
        release_account_sync(
            platform,
            account_id,
            sync_type=sync_type,
            success=True,
            cursor=cursor,
            comments_fetched=comments_fetched,
            comments_new=comments_new,
        )
        return {"success": True, "platform": platform, "account_id": account_id, "new": comments_new}
    except Exception as e:
        logger.exception("Sync failed for %s/%s: %s", platform, account_id, e)
        release_account_sync(platform, account_id, sync_type=sync_type, success=False, error=str(e))
        return {"success": False, "error": str(e)}


def run_due_syncs() -> List[Dict[str, Any]]:
    """Run scheduled 30-minute syncs for all due accounts."""
    states = ensure_account_sync_states()
    now = _utc_now()
    results = []
    for st in states:
        if not st.get("auto_sync_enabled"):
            continue
        backoff_until = _parse_iso(st.get("backoff_until"))
        if backoff_until and backoff_until > now:
            continue
        next_sync = _parse_iso(st.get("next_sync_at"))
        if next_sync is None or next_sync <= now:
            results.append(sync_account(st["platform"], st["account_id"], sync_type="scheduled"))
    return results


def run_startup_sync_recovery() -> List[Dict[str, Any]]:
    """Clear stale locks and run immediate catch-up sync for overdue accounts."""
    conn = database.get_connection()
    try:
        conn.execute("UPDATE account_sync_state SET is_syncing = 0, sync_claimed_at = NULL WHERE is_syncing = 1")
        conn.commit()
    finally:
        conn.close()

    states = ensure_account_sync_states()
    now = _utc_now()
    results = []
    for st in states:
        if not st.get("auto_sync_enabled"):
            continue
        next_sync = _parse_iso(st.get("next_sync_at"))
        last_ok = _parse_iso(st.get("last_successful_sync_at"))
        overdue = (next_sync is not None and next_sync <= now) or (
            last_ok is not None and (now - last_ok) >= timedelta(minutes=DEFAULT_SYNC_INTERVAL_MINUTES)
        )
        if overdue:
            results.append(sync_account(st["platform"], st["account_id"], sync_type="startup_recovery"))
    return results


def get_sync_history(limit: int = 50) -> List[Dict[str, Any]]:
    conn = database.get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM sync_history ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
