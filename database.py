"""Database setup and SQLite schema for Gokul Social Publisher."""
import sqlite3
import os
import time
import threading
from typing import Dict, Any, Optional, Tuple, List

_rate_limit_lock = threading.Lock()

MAX_REPLIES_PER_HOUR = 30
MAX_REPLIES_PER_DAY = 100
COMMENTER_COOLDOWN_SECONDS = 24 * 3600
MIN_REPLY_INTERVAL_SECONDS = 120

def get_db_path() -> str:
    return os.environ.get("GSP_DB_PATH") or os.path.join(os.path.dirname(__file__), "gsp.db")

def get_connection():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Settings table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """)
    
    # Accounts table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT NOT NULL,
        account_id TEXT NOT NULL UNIQUE,
        account_name TEXT NOT NULL,
        access_token TEXT,
        is_active INTEGER DEFAULT 1,
        connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Activity log table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS activities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT NOT NULL,
        post_id TEXT,
        comment_id TEXT NOT NULL UNIQUE,
        author_name TEXT,
        comment_text TEXT NOT NULL,
        detected_language TEXT,
        detected_intent TEXT,
        reply_text TEXT,
        status TEXT NOT NULL, -- 'replied', 'review_required', 'skipped'
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # OAuth temporary sessions table for secure page selection
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS oauth_sessions (
        session_id TEXT PRIMARY KEY,
        pages_data TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Insert default settings if not exists
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_reply_enabled', 'false')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('ig_auto_reply_enabled', 'false')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('yt_auto_reply_enabled', 'false')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('safe_test_mode', 'true')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('global_kill_switch', 'false')")
    for _p_prefix in ("fb", "ig", "yt"):
        cursor.execute(f"INSERT OR IGNORE INTO settings (key, value) VALUES ('{_p_prefix}_praise_enabled', 'true')")
        cursor.execute(f"INSERT OR IGNORE INTO settings (key, value) VALUES ('{_p_prefix}_emoji_enabled', 'true')")
        cursor.execute(f"INSERT OR IGNORE INTO settings (key, value) VALUES ('{_p_prefix}_manual_queue_enabled', 'true')")
        cursor.execute(
            f"INSERT OR IGNORE INTO settings (key, value) VALUES ('{_p_prefix}_enabled_templates', ?)",
            ('["ta_1", "ta_2", "en_1", "en_2", "tanglish_1", "tanglish_2"]',),
        )

    # Ensure Activity Log has extended audit columns
    cursor.execute("PRAGMA table_info(activities)")
    existing_cols = {row["name"] for row in cursor.fetchall()}
    for col_name, col_type in [
        ("account_id", "TEXT"),
        ("template_id", "TEXT"),
        ("reason", "TEXT"),
        ("api_error", "TEXT"),
    ]:
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE activities ADD COLUMN {col_name} {col_type}")

    # Rate-limit log table (persists published reply timestamps across restarts)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reply_rate_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT NOT NULL,
        account_id TEXT,
        comment_id TEXT NOT NULL,
        commenter_key TEXT NOT NULL,
        template_id TEXT,
        replied_at REAL NOT NULL
    )
    """)

    # Controlled library of 6 approved templates
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS approved_templates (
        template_id TEXT PRIMARY KEY,
        language TEXT NOT NULL,
        template_text TEXT NOT NULL
    )
    """)

    # Approval queue table for Hybrid Auto Reply
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS approval_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT NOT NULL,
        account_id TEXT NOT NULL,
        comment_id TEXT NOT NULL,
        commenter_name TEXT,
        comment_text TEXT NOT NULL,
        detected_language TEXT,
        detected_intent TEXT,
        suggested_reply TEXT,
        edited_reply TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        review_reason TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        approved_at TIMESTAMP,
        rejected_at TIMESTAMP,
        published_at TIMESTAMP,
        publishing_error TEXT,
        UNIQUE(platform, comment_id)
    )
    """)

    cursor.execute("PRAGMA table_info(approval_queue)")
    aq_cols = {row["name"] for row in cursor.fetchall()}
    if "rejected_at" not in aq_cols:
        cursor.execute("ALTER TABLE approval_queue ADD COLUMN rejected_at TIMESTAMP")

    # Approval workflow activity log (records every edit, approve, reject, and validation)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS approval_activity_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        approval_queue_id INTEGER NOT NULL,
        platform TEXT NOT NULL,
        comment_id TEXT NOT NULL,
        comment_text TEXT NOT NULL,
        suggested_reply TEXT,
        edited_reply TEXT,
        final_reply TEXT,
        approved_at TIMESTAMP,
        rejected_at TIMESTAMP,
        user_action TEXT NOT NULL,
        validation_result TEXT,
        blocked_reason TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    # Publishing attempts history (Priority 2D)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS publishing_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        approval_queue_id INTEGER NOT NULL,
        platform TEXT NOT NULL,
        account_id TEXT NOT NULL,
        comment_id TEXT NOT NULL,
        final_reply TEXT NOT NULL,
        attempt_status TEXT NOT NULL,
        validation_result TEXT NOT NULL,
        blocked_reason TEXT,
        error_details TEXT,
        target_type TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # In-app notifications table (Priority 2F)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_key TEXT NOT NULL UNIQUE,
        event_type TEXT NOT NULL,
        platform TEXT,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        link_tab TEXT DEFAULT 'activity',
        related_id INTEGER,
        is_read INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_read_created ON notifications (is_read, created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_activities_platform_status ON activities (platform, status, created_at DESC)")

    # Smart Lead Management (V2.0 Phase 2.0A)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_type TEXT NOT NULL,
        platform TEXT NOT NULL,
        account_id TEXT NOT NULL,
        source_comment_id TEXT NOT NULL,
        customer_name TEXT,
        customer_username TEXT,
        customer_contact TEXT,
        enquiry_category TEXT NOT NULL,
        original_message TEXT NOT NULL,
        detected_language TEXT,
        lead_status TEXT NOT NULL DEFAULT 'New',
        priority TEXT NOT NULL DEFAULT 'Medium',
        internal_notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_contacted_at TIMESTAMP,
        next_follow_up_at TIMESTAMP,
        converted_at TIMESTAMP,
        UNIQUE(platform, account_id, source_comment_id)
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_business_status ON leads (business_type, lead_status, created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_business_platform ON leads (business_type, platform, created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_business_category ON leads (business_type, enquiry_category, created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_follow_up ON leads (business_type, next_follow_up_at)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lead_activity_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL,
        business_type TEXT NOT NULL,
        event_type TEXT NOT NULL,
        old_value TEXT,
        new_value TEXT,
        details TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_lead_history_lead_id ON lead_activity_history (lead_id, created_at DESC)")

    # Auto Post Scheduler V2 tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS posting_slots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_key TEXT NOT NULL,
        day_of_week INTEGER NOT NULL DEFAULT -1,
        slot_time TEXT NOT NULL,
        slot_order INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_posting_slots_account ON posting_slots (account_key, is_active, slot_order)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scheduled_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id TEXT,
        video_id TEXT,
        account_key TEXT NOT NULL,
        platform TEXT NOT NULL,
        zodiac_index INTEGER NOT NULL,
        zodiac_tamil TEXT NOT NULL,
        zodiac_english TEXT NOT NULL,
        category TEXT NOT NULL,
        original_filename TEXT NOT NULL,
        media_path TEXT NOT NULL,
        thumbnail_path TEXT,
        caption TEXT NOT NULL,
        hashtags TEXT NOT NULL,
        scheduled_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'scheduled',
        external_post_id TEXT,
        permalink TEXT,
        error_message TEXT,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        published_at TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    for col_def in [
        "ALTER TABLE scheduled_posts ADD COLUMN video_id TEXT",
        "ALTER TABLE scheduled_posts ADD COLUMN external_post_id TEXT",
        "ALTER TABLE scheduled_posts ADD COLUMN permalink TEXT",
        "ALTER TABLE scheduled_posts ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE scheduled_posts ADD COLUMN upload_session_url TEXT",
        "ALTER TABLE scheduled_posts ADD COLUMN upload_progress_pct REAL NOT NULL DEFAULT 0",
        "ALTER TABLE scheduled_posts ADD COLUMN bytes_uploaded INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE scheduled_posts ADD COLUMN total_file_size INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE scheduled_posts ADD COLUMN last_attempt_at TEXT",
        "ALTER TABLE scheduled_posts ADD COLUMN next_retry_at TEXT",
        "ALTER TABLE scheduled_posts ADD COLUMN error_category TEXT",
    ]:
        try:
            cursor.execute(col_def)
        except Exception:
            pass
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_posts_status_time ON scheduled_posts (status, scheduled_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_posts_account_time ON scheduled_posts (account_key, scheduled_at, status)")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_scheduled_posts_video_account ON scheduled_posts (video_id, account_key) WHERE video_id IS NOT NULL")

    from nlp_detector import APPROVED_TEMPLATES
    for lang, items in APPROVED_TEMPLATES.items():
        for item in items:
            cursor.execute(
                "INSERT OR REPLACE INTO approved_templates (template_id, language, template_text) VALUES (?, ?, ?)",
                (item["id"], lang, item["text"]),
            )
    
    conn.commit()
    conn.close()

def get_settings() -> Dict[str, str]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    conn.close()
    return {row["key"]: row["value"] for row in rows}

def set_setting(key: str, value: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def save_oauth_session(session_id: str, pages_data_json: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO oauth_sessions (session_id, pages_data) VALUES (?, ?)", (session_id, pages_data_json))
    conn.commit()
    conn.close()

def get_oauth_session(session_id: str) -> Optional[str]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT pages_data FROM oauth_sessions WHERE session_id = ?", (session_id,))
    row = c.fetchone()
    conn.close()
    return row["pages_data"] if row else None

def delete_oauth_session(session_id: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM oauth_sessions WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()

def get_last_template_for_commenter(commenter_key: str) -> Optional[str]:
    """Returns the most recent template_id sent to a commenter, if any."""
    if not commenter_key:
        return None
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT template_id FROM activities WHERE author_name = ? AND template_id IS NOT NULL ORDER BY id DESC LIMIT 1",
        (commenter_key,),
    )
    row = c.fetchone()
    conn.close()
    return row["template_id"] if row else None

def check_and_reserve_rate_limit(
    platform: str,
    account_id: str,
    comment_id: str,
    commenter_key: str,
    template_id: Optional[str] = None,
    now_ts: Optional[float] = None,
) -> Tuple[bool, Optional[str]]:
    """Atomically checks all 4 backend rate limits and reserves a slot if allowed.
    Returns (allowed, reason_if_blocked).
    """
    now = now_ts if now_ts is not None else time.time()
    with _rate_limit_lock:
        conn = get_connection()
        c = conn.cursor()
        try:
            # 1. Minimum 120-second interval between replies
            c.execute("SELECT MAX(replied_at) AS last_ts FROM reply_rate_log")
            row = c.fetchone()
            if row and row["last_ts"] is not None and (now - row["last_ts"]) < MIN_REPLY_INTERVAL_SECONDS:
                return (False, "rate_limit_min_interval_120s")

            # 2. Maximum 30 replies per hour
            c.execute("SELECT COUNT(*) AS cnt FROM reply_rate_log WHERE replied_at >= ?", (now - 3600,))
            if c.fetchone()["cnt"] >= MAX_REPLIES_PER_HOUR:
                return (False, "rate_limit_hourly_30")

            # 3. Maximum 100 replies per day
            c.execute("SELECT COUNT(*) AS cnt FROM reply_rate_log WHERE replied_at >= ?", (now - 86400,))
            if c.fetchone()["cnt"] >= MAX_REPLIES_PER_DAY:
                return (False, "rate_limit_daily_100")

            # 4. Same commenter 24-hour cooldown
            c.execute(
                "SELECT COUNT(*) AS cnt FROM reply_rate_log WHERE commenter_key = ? AND replied_at >= ?",
                (commenter_key, now - COMMENTER_COOLDOWN_SECONDS),
            )
            if c.fetchone()["cnt"] >= 1:
                return (False, "rate_limit_commenter_24h")

            # Reserve slot
            c.execute(
                """
                INSERT INTO reply_rate_log (platform, account_id, comment_id, commenter_key, template_id, replied_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (platform, account_id, comment_id, commenter_key, template_id, now),
            )
            conn.commit()
            return (True, None)
        finally:
            conn.close()

def release_rate_limit_reservation(comment_id: str):
    """Releases a reserved rate-limit slot if the live API call failed."""
    with _rate_limit_lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM reply_rate_log WHERE comment_id = ?", (comment_id,))
        conn.commit()
        conn.close()


VALID_QUEUE_STATUSES = {"pending", "approved", "rejected", "publishing", "replied", "failed"}


def enqueue_approval_item(
    platform: str,
    account_id: str,
    comment_id: str,
    commenter_name: Optional[str],
    comment_text: str,
    detected_language: Optional[str],
    detected_intent: Optional[str],
    suggested_reply: Optional[str],
    review_reason: Optional[str],
) -> Optional[int]:
    """Inserts a comment into approval_queue if not already present for (platform, comment_id).
    Returns the new queue ID, or None if a duplicate already exists.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT OR IGNORE INTO approval_queue (
            platform, account_id, comment_id, commenter_name, comment_text,
            detected_language, detected_intent, suggested_reply, status, review_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """,
        (
            platform,
            account_id or "",
            comment_id,
            commenter_name,
            comment_text,
            detected_language,
            detected_intent,
            suggested_reply,
            review_reason,
        ),
    )
    conn.commit()
    inserted_id = c.lastrowid if c.rowcount > 0 else None
    conn.close()
    return inserted_id


def get_approval_queue(
    status: Optional[str] = "pending",
    platform: Optional[str] = None,
    limit: int = 100,
) -> list:
    """Retrieves approval queue items filtered by status and/or platform."""
    conn = get_connection()
    c = conn.cursor()
    query = "SELECT * FROM approval_queue WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if platform:
        query += " AND platform = ?"
        params.append(platform)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    c.execute(query, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_approval_queue_history(
    platform: Optional[str] = None,
    limit: int = 100,
) -> list:
    """Retrieves non-pending approval queue items."""
    conn = get_connection()
    c = conn.cursor()
    query = "SELECT * FROM approval_queue WHERE status != 'pending'"
    params = []
    if platform:
        query += " AND platform = ?"
        params.append(platform)
    query += " ORDER BY updated_at DESC, id DESC LIMIT ?"
    params.append(limit)
    c.execute(query, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_approval_queue_item(queue_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves a single approval queue item by ID."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM approval_queue WHERE id = ?", (queue_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


_approval_lock = threading.Lock()


def _log_approval_activity_with_cursor(
    cursor,
    item: Dict[str, Any],
    user_action: str,
    validation_result: Optional[str] = None,
    blocked_reason: Optional[str] = None,
):
    """Inserts an audit entry into approval_activity_log without exposing secrets."""
    final_reply = (item.get("edited_reply") or item.get("suggested_reply") or "").strip() or None
    cursor.execute(
        """
        INSERT INTO approval_activity_log (
            approval_queue_id, platform, comment_id, comment_text,
            suggested_reply, edited_reply, final_reply,
            approved_at, rejected_at, user_action, validation_result, blocked_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item["id"],
            item["platform"],
            item["comment_id"],
            item["comment_text"],
            item.get("suggested_reply"),
            item.get("edited_reply"),
            final_reply,
            item.get("approved_at"),
            item.get("rejected_at"),
            user_action,
            validation_result,
            blocked_reason,
        ),
    )


def get_approval_activity_log(
    approval_queue_id: Optional[int] = None,
    platform: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Retrieves approval workflow activity log entries."""
    conn = get_connection()
    c = conn.cursor()
    query = "SELECT * FROM approval_activity_log WHERE 1=1"
    params: List[Any] = []
    if approval_queue_id is not None:
        query += " AND approval_queue_id = ?"
        params.append(approval_queue_id)
    if platform:
        query += " AND platform = ?"
        params.append(platform)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    c.execute(query, tuple(params))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def update_approval_reply(
    queue_id: int, edited_reply: str
) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """Edits the reply text for a pending or approved queue item."""
    with _approval_lock:
        conn = get_connection()
        c = conn.cursor()
        try:
            c.execute("BEGIN IMMEDIATE")
            c.execute(
                """
                UPDATE approval_queue
                SET edited_reply = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status IN ('pending', 'approved')
                """,
                (edited_reply, queue_id),
            )
            if c.rowcount == 0:
                c.execute("SELECT * FROM approval_queue WHERE id = ?", (queue_id,))
                row = c.fetchone()
                conn.rollback()
                if not row:
                    return (False, "not_found", None)
                return (False, f"cannot_edit_in_status_{row['status']}", dict(row))

            c.execute("SELECT * FROM approval_queue WHERE id = ?", (queue_id,))
            updated = dict(c.fetchone())
            _log_approval_activity_with_cursor(c, updated, user_action="edit")
            conn.commit()
            return (True, None, updated)
        finally:
            conn.close()


def approve_approval_item(
    queue_id: int, edited_reply: Optional[str] = None
) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """Atomically approves a pending queue item without publishing."""
    with _approval_lock:
        conn = get_connection()
        c = conn.cursor()
        try:
            c.execute("BEGIN IMMEDIATE")
            if edited_reply is not None:
                c.execute(
                    """
                    UPDATE approval_queue
                    SET status = 'approved',
                        edited_reply = ?,
                        approved_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = 'pending'
                    """,
                    (edited_reply, queue_id),
                )
            else:
                c.execute(
                    """
                    UPDATE approval_queue
                    SET status = 'approved',
                        approved_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = 'pending'
                    """,
                    (queue_id,),
                )
            if c.rowcount == 0:
                c.execute("SELECT * FROM approval_queue WHERE id = ?", (queue_id,))
                row = c.fetchone()
                conn.rollback()
                if not row:
                    return (False, "not_found", None)
                return (False, f"invalid_transition_from_{row['status']}_to_approved", dict(row))

            c.execute("SELECT * FROM approval_queue WHERE id = ?", (queue_id,))
            updated = dict(c.fetchone())
            _log_approval_activity_with_cursor(c, updated, user_action="approve")
            conn.commit()
            return (True, None, updated)
        finally:
            conn.close()


def reject_approval_item(
    queue_id: int, reason: Optional[str] = None
) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """Atomically rejects a pending queue item."""
    with _approval_lock:
        conn = get_connection()
        c = conn.cursor()
        try:
            c.execute("BEGIN IMMEDIATE")
            if reason is not None:
                c.execute(
                    """
                    UPDATE approval_queue
                    SET status = 'rejected',
                        review_reason = ?,
                        rejected_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = 'pending'
                    """,
                    (reason, queue_id),
                )
            else:
                c.execute(
                    """
                    UPDATE approval_queue
                    SET status = 'rejected',
                        rejected_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = 'pending'
                    """,
                    (queue_id,),
                )
            if c.rowcount == 0:
                c.execute("SELECT * FROM approval_queue WHERE id = ?", (queue_id,))
                row = c.fetchone()
                conn.rollback()
                if not row:
                    return (False, "not_found", None)
                return (False, f"invalid_transition_from_{row['status']}_to_rejected", dict(row))

            c.execute("SELECT * FROM approval_queue WHERE id = ?", (queue_id,))
            updated = dict(c.fetchone())
            _log_approval_activity_with_cursor(
                c, updated, user_action="reject", blocked_reason=reason
            )
            conn.commit()
            return (True, None, updated)
        finally:
            conn.close()


_PLATFORM_AUTO_REPLY_SETTING = {
    "facebook": "auto_reply_enabled",
    "instagram": "ig_auto_reply_enabled",
    "youtube": "yt_auto_reply_enabled",
}

_PLATFORM_TARGET_TYPE = {
    "facebook": "facebook_page",
    "instagram": "instagram_professional_account",
    "youtube": "youtube_channel",
}


def validate_approved_item_for_publishing(
    queue_id: int, now_ts: Optional[float] = None
) -> Dict[str, Any]:
    """Validates whether an approved queue item is eligible for future publishing.

    Does NOT call any public reply API and does NOT mutate queue status or rate-limit state.
    """
    now = now_ts if now_ts is not None else time.time()
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM approval_queue WHERE id = ?", (queue_id,))
        row = c.fetchone()
        if not row:
            return {
                "eligible": False,
                "reason": "not_found",
                "queue_id": queue_id,
            }
        item = dict(row)
        platform = item["platform"]
        account_id = item["account_id"]
        comment_id = item["comment_id"]
        commenter_key = f"{platform}:{item.get('commenter_name') or 'unknown'}"
        final_reply = (item.get("edited_reply") or item.get("suggested_reply") or "").strip()

        c.execute("SELECT key, value FROM settings")
        settings = {r["key"]: r["value"] for r in c.fetchall()}

        blocked_reason: Optional[str] = None

        # 1. Global emergency kill switch is OFF
        if settings.get("global_kill_switch", "false") == "true":
            blocked_reason = "global_kill_switch_active"
        # 2. Safe Testing Mode is OFF before any future public publishing
        elif settings.get("safe_test_mode", "true") == "true":
            blocked_reason = "safe_testing_mode_active"
        # 3. Relevant platform Auto Reply control is enabled
        elif platform not in _PLATFORM_AUTO_REPLY_SETTING:
            blocked_reason = f"unsupported_platform_{platform}"
        elif settings.get(_PLATFORM_AUTO_REPLY_SETTING[platform], "false") != "true":
            blocked_reason = f"platform_auto_reply_disabled_{platform}"
        else:
            # 4. Account remains connected and valid
            c.execute(
                """
                SELECT account_id, account_name, access_token, is_active
                FROM accounts
                WHERE platform = ? AND account_id = ? AND is_active = 1
                """,
                (platform, account_id),
            )
            acct = c.fetchone()
            if not acct or not (acct["access_token"] or "").strip():
                blocked_reason = f"account_disconnected_or_invalid_{platform}"
            # 5. Comment ID is valid
            elif not comment_id or not str(comment_id).strip():
                blocked_reason = "invalid_comment_id"
            # 6. Queue item is approved
            elif item["status"] != "approved":
                blocked_reason = f"invalid_status_{item['status']}"
            else:
                # 7. Comment has not already been replied to
                c.execute(
                    "SELECT 1 FROM activities WHERE comment_id = ? AND status = 'replied' LIMIT 1",
                    (comment_id,),
                )
                if c.fetchone():
                    blocked_reason = "comment_already_replied"
                # 8. Final reply text is not empty
                elif not final_reply:
                    blocked_reason = "empty_reply_text"
                else:
                    # 9. Rate limits (30/hour, 100/day)
                    c.execute(
                        "SELECT COUNT(*) AS cnt FROM reply_rate_log WHERE replied_at >= ?",
                        (now - 3600,),
                    )
                    if c.fetchone()["cnt"] >= MAX_REPLIES_PER_HOUR:
                        blocked_reason = "rate_limit_hourly_30"
                    else:
                        c.execute(
                            "SELECT COUNT(*) AS cnt FROM reply_rate_log WHERE replied_at >= ?",
                            (now - 86400,),
                        )
                        if c.fetchone()["cnt"] >= MAX_REPLIES_PER_DAY:
                            blocked_reason = "rate_limit_daily_100"
                        else:
                            # 10. 24-hour commenter cooldown
                            c.execute(
                                "SELECT COUNT(*) AS cnt FROM reply_rate_log WHERE commenter_key = ? AND replied_at >= ?",
                                (commenter_key, now - COMMENTER_COOLDOWN_SECONDS),
                            )
                            if c.fetchone()["cnt"] >= 1:
                                blocked_reason = "rate_limit_commenter_24h"
                            else:
                                # 11. Minimum 120-second interval
                                c.execute("SELECT MAX(replied_at) AS last_ts FROM reply_rate_log")
                                last_row = c.fetchone()
                                if (
                                    last_row
                                    and last_row["last_ts"] is not None
                                    and (now - last_row["last_ts"]) < MIN_REPLY_INTERVAL_SECONDS
                                ):
                                    blocked_reason = "rate_limit_min_interval_120s"

        eligible = blocked_reason is None
        validation_result = "eligible" if eligible else "blocked"
        _log_approval_activity_with_cursor(
            c,
            item,
            user_action="validate_publish",
            validation_result=validation_result,
            blocked_reason=blocked_reason,
        )
        conn.commit()

        return {
            "eligible": eligible,
            "reason": blocked_reason,
            "queue_id": queue_id,
            "platform": platform,
            "target_type": _PLATFORM_TARGET_TYPE.get(platform, "unknown"),
            "account_id": account_id,
            "comment_id": comment_id,
            "final_reply": final_reply,
        }
    finally:
        conn.close()


# --- Priority 2D: Safe Publishing Workflow & Platform Adapters ---

def _prepare_facebook_reply_adapter(
    account_id: str, comment_id: str, final_reply: str
) -> Dict[str, Any]:
    """Isolated Facebook Page comment reply preparation adapter (no external dispatch)."""
    return {
        "platform": "facebook",
        "target_type": "facebook_page",
        "account_id": account_id,
        "comment_id": comment_id,
        "reply_text": final_reply,
        "dispatch_enabled": False,
    }


def _prepare_instagram_reply_adapter(
    account_id: str, comment_id: str, final_reply: str
) -> Dict[str, Any]:
    """Isolated Instagram Professional account reply preparation adapter (no external dispatch)."""
    return {
        "platform": "instagram",
        "target_type": "instagram_professional_account",
        "account_id": account_id,
        "comment_id": comment_id,
        "reply_text": final_reply,
        "dispatch_enabled": False,
    }


def _prepare_youtube_reply_adapter(
    account_id: str, comment_id: str, final_reply: str
) -> Dict[str, Any]:
    """Isolated YouTube channel comment reply preparation adapter (no external dispatch)."""
    return {
        "platform": "youtube",
        "target_type": "youtube_channel",
        "account_id": account_id,
        "comment_id": comment_id,
        "reply_text": final_reply,
        "dispatch_enabled": False,
    }


_PLATFORM_PREPARE_ADAPTERS = {
    "facebook": _prepare_facebook_reply_adapter,
    "instagram": _prepare_instagram_reply_adapter,
    "youtube": _prepare_youtube_reply_adapter,
}


def _record_publishing_attempt_with_cursor(
    c: sqlite3.Cursor,
    *,
    approval_queue_id: int,
    platform: str,
    account_id: str,
    comment_id: str,
    final_reply: str,
    attempt_status: str,
    validation_result: str,
    blocked_reason: Optional[str] = None,
    error_details: Optional[str] = None,
    target_type: Optional[str] = None,
) -> int:
    """Inserts a publishing attempt record without storing any OAuth secrets."""
    c.execute(
        """
        INSERT INTO publishing_attempts (
            approval_queue_id, platform, account_id, comment_id, final_reply,
            attempt_status, validation_result, blocked_reason, error_details, target_type
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            approval_queue_id,
            platform,
            account_id,
            comment_id,
            final_reply,
            attempt_status,
            validation_result,
            blocked_reason,
            error_details,
            target_type,
        ),
    )
    return c.lastrowid


def prepare_publishing_for_item(
    queue_id: int, now_ts: Optional[float] = None
) -> Dict[str, Any]:
    """Executes the Priority 2D safe publishing preparation pipeline.

    Revalidates every safety condition immediately before dispatch, atomically
    reserves rate-limit capacity when eligible, and stops before any external
    API call in Safe Testing Mode (recording `test_prepared`).
    """
    now = now_ts if now_ts is not None else time.time()
    with _approval_lock:
        conn = get_connection()
        c = conn.cursor()
        try:
            c.execute("BEGIN IMMEDIATE")
            c.execute("SELECT * FROM approval_queue WHERE id = ?", (queue_id,))
            row = c.fetchone()
            if not row:
                conn.rollback()
                return {
                    "success": False,
                    "attempt_status": "not_found",
                    "reason": "not_found",
                    "queue_id": queue_id,
                    "dispatched": False,
                }

            item = dict(row)
            platform = item["platform"]
            account_id = item["account_id"]
            comment_id = item["comment_id"]
            commenter_key = f"{platform}:{item.get('commenter_name') or 'unknown'}"
            final_reply = (item.get("edited_reply") or item.get("suggested_reply") or "").strip()
            target_type = _PLATFORM_TARGET_TYPE.get(platform, "unknown")

            # Duplicate attempt prevention
            c.execute(
                """
                SELECT id, attempt_status FROM publishing_attempts
                WHERE approval_queue_id = ? AND attempt_status IN ('test_prepared', 'replied')
                ORDER BY id DESC LIMIT 1
                """,
                (queue_id,),
            )
            existing_attempt = c.fetchone()
            if existing_attempt:
                conn.rollback()
                return {
                    "success": False,
                    "attempt_status": "blocked",
                    "reason": "duplicate_publishing_attempt",
                    "queue_id": queue_id,
                    "existing_attempt_id": existing_attempt["id"],
                    "dispatched": False,
                }

            c.execute("SELECT key, value FROM settings")
            settings = {r["key"]: r["value"] for r in c.fetchall()}

            blocked_reason: Optional[str] = None
            if settings.get("global_kill_switch", "false") == "true":
                blocked_reason = "global_kill_switch_active"
            elif platform not in _PLATFORM_AUTO_REPLY_SETTING:
                blocked_reason = f"unsupported_platform_{platform}"
            elif settings.get(_PLATFORM_AUTO_REPLY_SETTING[platform], "false") != "true":
                blocked_reason = f"platform_auto_reply_disabled_{platform}"
            else:
                c.execute(
                    """
                    SELECT account_id, account_name, access_token, is_active
                    FROM accounts
                    WHERE platform = ? AND account_id = ? AND is_active = 1
                    """,
                    (platform, account_id),
                )
                acct = c.fetchone()
                if not acct or not (acct["access_token"] or "").strip():
                    blocked_reason = f"account_disconnected_or_invalid_{platform}"
                elif not comment_id or not str(comment_id).strip():
                    blocked_reason = "invalid_comment_id"
                elif item["status"] != "approved":
                    blocked_reason = f"invalid_status_{item['status']}"
                else:
                    c.execute(
                        "SELECT 1 FROM activities WHERE comment_id = ? AND status = 'replied' LIMIT 1",
                        (comment_id,),
                    )
                    if c.fetchone():
                        blocked_reason = "comment_already_replied"
                    elif not final_reply:
                        blocked_reason = "empty_reply_text"
                    else:
                        c.execute(
                            "SELECT COUNT(*) AS cnt FROM reply_rate_log WHERE replied_at >= ?",
                            (now - 3600,),
                        )
                        if c.fetchone()["cnt"] >= MAX_REPLIES_PER_HOUR:
                            blocked_reason = "rate_limit_hourly_30"
                        else:
                            c.execute(
                                "SELECT COUNT(*) AS cnt FROM reply_rate_log WHERE replied_at >= ?",
                                (now - 86400,),
                            )
                            if c.fetchone()["cnt"] >= MAX_REPLIES_PER_DAY:
                                blocked_reason = "rate_limit_daily_100"
                            else:
                                c.execute(
                                    "SELECT COUNT(*) AS cnt FROM reply_rate_log WHERE commenter_key = ? AND replied_at >= ?",
                                    (commenter_key, now - COMMENTER_COOLDOWN_SECONDS),
                                )
                                if c.fetchone()["cnt"] >= 1:
                                    blocked_reason = "rate_limit_commenter_24h"
                                else:
                                    c.execute("SELECT MAX(replied_at) AS last_ts FROM reply_rate_log")
                                    last_row = c.fetchone()
                                    if (
                                        last_row
                                        and last_row["last_ts"] is not None
                                        and (now - last_row["last_ts"]) < MIN_REPLY_INTERVAL_SECONDS
                                    ):
                                        blocked_reason = "rate_limit_min_interval_120s"

            if blocked_reason is not None:
                attempt_id = _record_publishing_attempt_with_cursor(
                    c,
                    approval_queue_id=queue_id,
                    platform=platform,
                    account_id=account_id,
                    comment_id=comment_id or "",
                    final_reply=final_reply,
                    attempt_status="blocked",
                    validation_result="blocked",
                    blocked_reason=blocked_reason,
                    target_type=target_type,
                )
                _log_approval_activity_with_cursor(
                    c,
                    item,
                    user_action="prepare_publish",
                    validation_result="blocked",
                    blocked_reason=blocked_reason,
                )
                conn.commit()
                return {
                    "success": False,
                    "attempt_id": attempt_id,
                    "attempt_status": "blocked",
                    "reason": blocked_reason,
                    "queue_id": queue_id,
                    "platform": platform,
                    "target_type": target_type,
                    "dispatched": False,
                }

            # Atomically reserve rate-limit capacity
            c.execute(
                """
                INSERT INTO reply_rate_log (platform, commenter_key, comment_id, replied_at)
                VALUES (?, ?, ?, ?)
                """,
                (platform, commenter_key, comment_id, now),
            )

            safe_test_mode = settings.get("safe_test_mode", "true") == "true"
            if not safe_test_mode:
                # Priority 2D: external dispatch remains disabled and unreachable
                attempt_id = _record_publishing_attempt_with_cursor(
                    c,
                    approval_queue_id=queue_id,
                    platform=platform,
                    account_id=account_id,
                    comment_id=comment_id,
                    final_reply=final_reply,
                    attempt_status="blocked",
                    validation_result="blocked",
                    blocked_reason="external_dispatch_disabled_in_priority_2d",
                    target_type=target_type,
                )
                _log_approval_activity_with_cursor(
                    c,
                    item,
                    user_action="prepare_publish",
                    validation_result="blocked",
                    blocked_reason="external_dispatch_disabled_in_priority_2d",
                )
                conn.commit()
                return {
                    "success": False,
                    "attempt_id": attempt_id,
                    "attempt_status": "blocked",
                    "reason": "external_dispatch_disabled_in_priority_2d",
                    "queue_id": queue_id,
                    "platform": platform,
                    "target_type": target_type,
                    "dispatched": False,
                }

            adapter_fn = _PLATFORM_PREPARE_ADAPTERS[platform]
            prepared_payload = adapter_fn(account_id, comment_id, final_reply)
            attempt_id = _record_publishing_attempt_with_cursor(
                c,
                approval_queue_id=queue_id,
                platform=platform,
                account_id=account_id,
                comment_id=comment_id,
                final_reply=final_reply,
                attempt_status="test_prepared",
                validation_result="eligible",
                blocked_reason="safe_testing_mode_active",
                target_type=target_type,
            )
            _log_approval_activity_with_cursor(
                c,
                item,
                user_action="prepare_publish",
                validation_result="eligible",
                blocked_reason="safe_testing_mode_active",
            )
            conn.commit()
            return {
                "success": True,
                "attempt_id": attempt_id,
                "attempt_status": "test_prepared",
                "reason": "safe_testing_mode_active",
                "queue_id": queue_id,
                "platform": platform,
                "target_type": target_type,
                "dispatched": False,
                "safe_test_mode": True,
                "prepared_payload": prepared_payload,
            }
        finally:
            conn.close()


def get_publishing_attempts(
    approval_queue_id: Optional[int] = None,
    platform: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Retrieves publishing attempt history without exposing any OAuth secrets."""
    conn = get_connection()
    c = conn.cursor()
    query = "SELECT * FROM publishing_attempts WHERE 1=1"
    params: list = []
    if approval_queue_id is not None:
        query += " AND approval_queue_id = ?"
        params.append(approval_queue_id)
    if platform:
        query += " AND platform = ?"
        params.append(platform)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    c.execute(query, tuple(params))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_latest_publishing_status(queue_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves the latest publishing attempt status for a queue item."""
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM publishing_attempts WHERE approval_queue_id = ? ORDER BY id DESC LIMIT 1",
        (queue_id,),
    )
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


# --- Priority 2E: Platform-specific Hybrid Controls ---

APPROVED_TEMPLATE_IDS = ("ta_1", "ta_2", "en_1", "en_2", "tanglish_1", "tanglish_2")
_PLATFORM_PREFIX = {"facebook": "fb", "instagram": "ig", "youtube": "yt"}


def get_platform_hybrid_settings(platform: str) -> Dict[str, Any]:
    """Retrieves independent hybrid auto-reply settings for a single platform."""
    if platform not in _PLATFORM_PREFIX:
        raise ValueError(f"Unsupported platform: {platform}")
    prefix = _PLATFORM_PREFIX[platform]
    settings = get_settings()
    raw_templates = settings.get(
        f"{prefix}_enabled_templates",
        '["ta_1", "ta_2", "en_1", "en_2", "tanglish_1", "tanglish_2"]',
    )
    import json
    try:
        parsed = json.loads(raw_templates)
        enabled_templates = [t for t in parsed if t in APPROVED_TEMPLATE_IDS]
    except Exception:
        enabled_templates = list(APPROVED_TEMPLATE_IDS)

    return {
        "platform": platform,
        "auto_reply_enabled": settings.get(_PLATFORM_AUTO_REPLY_SETTING[platform], "false") == "true",
        "praise_enabled": settings.get(f"{prefix}_praise_enabled", "true") == "true",
        "emoji_enabled": settings.get(f"{prefix}_emoji_enabled", "true") == "true",
        "manual_queue_enabled": settings.get(f"{prefix}_manual_queue_enabled", "true") == "true",
        "enabled_templates": enabled_templates,
    }


def get_all_platform_hybrid_settings() -> Dict[str, Dict[str, Any]]:
    """Retrieves independent hybrid settings for Facebook, Instagram, and YouTube."""
    return {p: get_platform_hybrid_settings(p) for p in ("facebook", "instagram", "youtube")}


def update_platform_hybrid_settings(
    platform: str,
    *,
    auto_reply_enabled: Optional[bool] = None,
    praise_enabled: Optional[bool] = None,
    emoji_enabled: Optional[bool] = None,
    manual_queue_enabled: Optional[bool] = None,
    enabled_templates: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Updates hybrid auto-reply settings for one platform without affecting others."""
    if platform not in _PLATFORM_PREFIX:
        raise ValueError(f"Unsupported platform: {platform}")
    prefix = _PLATFORM_PREFIX[platform]
    if auto_reply_enabled is not None:
        set_setting(_PLATFORM_AUTO_REPLY_SETTING[platform], "true" if auto_reply_enabled else "false")
    if praise_enabled is not None:
        set_setting(f"{prefix}_praise_enabled", "true" if praise_enabled else "false")
    if emoji_enabled is not None:
        set_setting(f"{prefix}_emoji_enabled", "true" if emoji_enabled else "false")
    if manual_queue_enabled is not None:
        set_setting(f"{prefix}_manual_queue_enabled", "true" if manual_queue_enabled else "false")
    if enabled_templates is not None:
        invalid = [t for t in enabled_templates if t not in APPROVED_TEMPLATE_IDS]
        if invalid:
            raise ValueError(f"Unapproved template IDs: {invalid}")
        import json
        set_setting(f"{prefix}_enabled_templates", json.dumps(enabled_templates))
    return get_platform_hybrid_settings(platform)


def pick_approved_template_for_platform(
    platform: str, language: str, comment_id: str
) -> Optional[str]:
    """Picks an approved template for `language` filtered by the platform's enabled templates."""
    from nlp_detector import APPROVED_TEMPLATES
    candidates = APPROVED_TEMPLATES.get(language, [])
    if not candidates:
        return None
    cfg = get_platform_hybrid_settings(platform)
    enabled = set(cfg["enabled_templates"])
    filtered = [t for t in candidates if t["id"] in enabled]
    if not filtered:
        return None
    idx = sum(ord(ch) for ch in (comment_id or "")) % len(filtered)
    return filtered[idx]["text"]


# --- Priority 2F: Unified Activity, Notifications & Dashboard Summary ---

def create_notification(
    *,
    event_key: str,
    event_type: str,
    title: str,
    message: str,
    platform: Optional[str] = None,
    link_tab: str = "activity",
    related_id: Optional[int] = None,
) -> Optional[int]:
    """Creates a persistent in-app notification, deduplicated by `event_key`."""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        c.execute(
            """
            INSERT OR IGNORE INTO notifications (
                event_key, event_type, platform, title, message, link_tab, related_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (event_key, event_type, platform, title, message, link_tab, related_id),
        )
        conn.commit()
        return c.lastrowid if c.rowcount > 0 else None
    finally:
        conn.close()


def get_notifications(unread_only: bool = False, limit: int = 50) -> Dict[str, Any]:
    """Retrieves notifications newest-first along with the unread count."""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) AS cnt FROM notifications WHERE is_read = 0")
        unread_count = c.fetchone()["cnt"]
        query = "SELECT * FROM notifications"
        if unread_only:
            query += " WHERE is_read = 0"
        query += " ORDER BY id DESC LIMIT ?"
        c.execute(query, (limit,))
        items = [dict(r) for r in c.fetchall()]
        return {"notifications": items, "unread_count": unread_count}
    finally:
        conn.close()


def mark_notification_read(notification_id: int) -> bool:
    """Marks a single notification as read."""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        c.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notification_id,))
        changed = c.rowcount > 0
        conn.commit()
        return changed
    finally:
        conn.close()


def mark_all_notifications_read() -> int:
    """Marks all unread notifications as read and returns the count updated."""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        c.execute("UPDATE notifications SET is_read = 1 WHERE is_read = 0")
        updated = c.rowcount
        conn.commit()
        return updated
    finally:
        conn.close()


_STATUS_FILTER_MAP = {
    "prepared": {"test_prepared", "replied"},
    "pending_approval": {"review_required", "pending"},
    "approved": {"approved"},
    "rejected": {"rejected"},
    "blocked": {"blocked", "skipped_rate_limit"},
    "failed": {"failed"},
}


def get_unified_activity_timeline(
    platform: Optional[str] = None,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Returns a unified, newest-first activity timeline from activities, approval_activity_log, and publishing_attempts."""
    conn = get_connection()
    try:
        c = conn.cursor()
        entries: List[Dict[str, Any]] = []

        c.execute(
            """
            SELECT id, platform, account_id, comment_id, author_name AS commenter_name,
                   comment_text, detected_language, detected_intent, reply_text,
                   status, reason, api_error, created_at
            FROM activities
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        )
        for r in c.fetchall():
            d = dict(r)
            entries.append({
                "source": "activity",
                "source_id": d["id"],
                "platform": d["platform"],
                "comment_id": d["comment_id"],
                "commenter_name": d["commenter_name"] or "Anonymous",
                "comment_text": d["comment_text"] or "",
                "detected_language": d["detected_language"],
                "detected_intent": d["detected_intent"],
                "suggested_reply": d["reply_text"],
                "final_reply": d["reply_text"],
                "status": d["status"],
                "reason": d["reason"] or d["api_error"],
                "created_at": d["created_at"],
            })

        c.execute(
            """
            SELECT l.id, l.approval_queue_id, l.platform, l.comment_id, l.comment_text,
                   l.suggested_reply, l.edited_reply, l.user_action, l.validation_result,
                   l.blocked_reason, l.created_at,
                   q.commenter_name, q.detected_language, q.detected_intent, q.status AS queue_status
            FROM approval_activity_log l
            LEFT JOIN approval_queue q ON q.id = l.approval_queue_id
            ORDER BY l.id DESC LIMIT ?
            """,
            (limit,),
        )
        for r in c.fetchall():
            d = dict(r)
            entries.append({
                "source": "approval_log",
                "source_id": d["id"],
                "platform": d["platform"],
                "comment_id": d["comment_id"],
                "commenter_name": d["commenter_name"] or "Anonymous",
                "comment_text": d["comment_text"] or "",
                "detected_language": d["detected_language"],
                "detected_intent": d["detected_intent"],
                "suggested_reply": d["suggested_reply"],
                "final_reply": d["edited_reply"] or d["suggested_reply"],
                "status": d["queue_status"] or d["user_action"],
                "reason": d["blocked_reason"] or d["user_action"],
                "created_at": d["created_at"],
            })

        c.execute(
            """
            SELECT p.id, p.approval_queue_id, p.platform, p.comment_id, p.final_reply,
                   p.attempt_status, p.blocked_reason, p.error_details, p.created_at,
                   q.commenter_name, q.comment_text, q.detected_language, q.detected_intent, q.suggested_reply
            FROM publishing_attempts p
            LEFT JOIN approval_queue q ON q.id = p.approval_queue_id
            ORDER BY p.id DESC LIMIT ?
            """,
            (limit,),
        )
        for r in c.fetchall():
            d = dict(r)
            entries.append({
                "source": "publishing_attempt",
                "source_id": d["id"],
                "platform": d["platform"],
                "comment_id": d["comment_id"],
                "commenter_name": d["commenter_name"] or "Anonymous",
                "comment_text": d["comment_text"] or "",
                "detected_language": d["detected_language"],
                "detected_intent": d["detected_intent"],
                "suggested_reply": d["suggested_reply"],
                "final_reply": d["final_reply"],
                "status": d["attempt_status"],
                "reason": d["blocked_reason"] or d["error_details"],
                "created_at": d["created_at"],
            })

        # Filter
        if platform and platform != "all":
            entries = [e for e in entries if e["platform"] == platform]
        if status_filter and status_filter != "all":
            allowed = _STATUS_FILTER_MAP.get(status_filter.lower(), {status_filter.lower()})
            entries = [e for e in entries if (e["status"] or "").lower() in allowed]
        if search and search.strip():
            q_low = search.strip().lower()
            entries = [
                e for e in entries
                if q_low in (e["comment_text"] or "").lower()
                or q_low in (e["commenter_name"] or "").lower()
            ]

        entries.sort(key=lambda e: (e["created_at"] or "", e["source_id"]), reverse=True)
        return entries[:limit]
    finally:
        conn.close()


def get_dashboard_summary() -> Dict[str, Any]:
    """Computes live operational summary counts from SQLite."""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) AS cnt FROM approval_queue WHERE status = 'pending'")
        pending_approvals = c.fetchone()["cnt"]

        c.execute("SELECT COUNT(*) AS cnt FROM publishing_attempts WHERE attempt_status = 'test_prepared'")
        test_prepared_attempts = c.fetchone()["cnt"]
        c.execute("SELECT COUNT(*) AS cnt FROM activities WHERE status = 'test_prepared'")
        test_prepared_activities = c.fetchone()["cnt"]

        c.execute("SELECT COUNT(*) AS cnt FROM publishing_attempts WHERE attempt_status = 'blocked'")
        blocked_attempts = c.fetchone()["cnt"]

        c.execute("SELECT COUNT(*) AS cnt FROM publishing_attempts WHERE attempt_status = 'failed'")
        failed_attempts = c.fetchone()["cnt"]
        c.execute("SELECT COUNT(*) AS cnt FROM activities WHERE status = 'failed'")
        failed_activities = c.fetchone()["cnt"]

        c.execute("SELECT COUNT(*) AS cnt FROM notifications WHERE is_read = 0")
        unread_notifications = c.fetchone()["cnt"]

        return {
            "pending_approvals": pending_approvals,
            "test_prepared_replies": test_prepared_attempts + test_prepared_activities,
            "blocked_attempts": blocked_attempts,
            "recent_failures": failed_attempts + failed_activities,
            "unread_notifications": unread_notifications,
        }
    finally:
        conn.close()


# ==============================================================================
# Smart Lead Management (GSP V2.0 - Phase 2.0A)
# ==============================================================================

VALID_BUSINESS_TYPES = ("Astrology", "Vivaham")
VALID_ENQUIRY_CATEGORIES = (
    "Astrology consultation",
    "Horoscope analysis",
    "Horoscope matching",
    "Marriage enquiry",
    "Numerology",
    "General enquiry",
    "Other",
)
VALID_LEAD_STATUSES = (
    "New",
    "Contacted",
    "Interested",
    "Converted",
    "Not Interested",
    "Follow-up Required",
)
VALID_LEAD_PRIORITIES = ("High", "Medium", "Low")
VALID_LEAD_PLATFORMS = ("facebook", "instagram", "youtube")


def _record_lead_history(
    cursor: sqlite3.Cursor,
    lead_id: int,
    business_type: str,
    event_type: str,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    details: Optional[str] = None,
) -> None:
    """Append an immutable activity history record for a lead."""
    cursor.execute(
        """
        INSERT INTO lead_activity_history
        (lead_id, business_type, event_type, old_value, new_value, details)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (lead_id, business_type, event_type, old_value, new_value, details),
    )


def create_lead(data: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Create a new lead with duplicate prevention and initial history entry.

    Returns (lead_dict, error_message). If duplicate, error_message is 'duplicate'.
    """
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute(
            """
            INSERT INTO leads (
                business_type, platform, account_id, source_comment_id,
                customer_name, customer_username, customer_contact,
                enquiry_category, original_message, detected_language,
                lead_status, priority, internal_notes, next_follow_up_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["business_type"],
                data["platform"].lower(),
                data["account_id"],
                data["source_comment_id"],
                data.get("customer_name"),
                data.get("customer_username"),
                data.get("customer_contact"),
                data["enquiry_category"],
                data["original_message"],
                data.get("detected_language"),
                data.get("lead_status", "New"),
                data.get("priority", "Medium"),
                data.get("internal_notes"),
                data.get("next_follow_up_at"),
            ),
        )
        lead_id = c.lastrowid
        _record_lead_history(
            c,
            lead_id=lead_id,
            business_type=data["business_type"],
            event_type="lead_created",
            new_value=data.get("lead_status", "New"),
            details=f"Lead created for {data['business_type']} ({data['enquiry_category']})",
        )
        conn.commit()
        c.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
        row = c.fetchone()
        return (dict(row) if row else None, None)
    except sqlite3.IntegrityError:
        conn.rollback()
        return (None, "duplicate")
    finally:
        conn.close()


def get_leads(
    business_type: Optional[str] = None,
    platform: Optional[str] = None,
    lead_status: Optional[str] = None,
    enquiry_category: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Retrieve leads with optional business, platform, status, and category filters."""
    conn = get_connection()
    c = conn.cursor()
    try:
        clauses = []
        params: List[Any] = []
        if business_type:
            clauses.append("business_type = ?")
            params.append(business_type)
        if platform:
            clauses.append("platform = ?")
            params.append(platform.lower())
        if lead_status:
            clauses.append("lead_status = ?")
            params.append(lead_status)
        if enquiry_category:
            clauses.append("enquiry_category = ?")
            params.append(enquiry_category)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        c.execute(
            f"SELECT * FROM leads {where_sql} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            tuple(params),
        )
        return [dict(r) for r in c.fetchall()]
    finally:
        conn.close()


def get_lead_by_id(lead_id: int, business_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve a single lead by ID, optionally enforcing business_type isolation."""
    conn = get_connection()
    c = conn.cursor()
    try:
        if business_type:
            c.execute("SELECT * FROM leads WHERE id = ? AND business_type = ?", (lead_id, business_type))
        else:
            c.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
        row = c.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_lead(
    lead_id: int,
    updates: Dict[str, Any],
    business_type: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Update a lead and record immutable history entries for each changed field."""
    conn = get_connection()
    c = conn.cursor()
    try:
        if business_type:
            c.execute("SELECT * FROM leads WHERE id = ? AND business_type = ?", (lead_id, business_type))
        else:
            c.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
        existing = c.fetchone()
        if not existing:
            return None
        existing_dict = dict(existing)
        lead_business = existing_dict["business_type"]

        set_clauses = ["updated_at = CURRENT_TIMESTAMP"]
        params: List[Any] = []

        updatable_fields = (
            "lead_status",
            "priority",
            "internal_notes",
            "customer_contact",
            "next_follow_up_at",
            "last_contacted_at",
            "converted_at",
            "enquiry_category",
        )
        for field in updatable_fields:
            if field in updates and updates[field] is not None:
                set_clauses.append(f"{field} = ?")
                params.append(updates[field])

        # Automatically set converted_at when transitioning to Converted
        if updates.get("lead_status") == "Converted" and not existing_dict.get("converted_at") and "converted_at" not in updates:
            set_clauses.append("converted_at = CURRENT_TIMESTAMP")

        # Automatically set last_contacted_at when transitioning to Contacted
        if updates.get("lead_status") == "Contacted" and "last_contacted_at" not in updates:
            set_clauses.append("last_contacted_at = CURRENT_TIMESTAMP")

        params.append(lead_id)
        c.execute(f"UPDATE leads SET {', '.join(set_clauses)} WHERE id = ?", tuple(params))

        # Record history events
        if "lead_status" in updates and updates["lead_status"] is not None and updates["lead_status"] != existing_dict["lead_status"]:
            _record_lead_history(
                c,
                lead_id=lead_id,
                business_type=lead_business,
                event_type="status_changed",
                old_value=existing_dict["lead_status"],
                new_value=updates["lead_status"],
                details=f"Status changed from {existing_dict['lead_status']} to {updates['lead_status']}",
            )
        if "priority" in updates and updates["priority"] is not None and updates["priority"] != existing_dict["priority"]:
            _record_lead_history(
                c,
                lead_id=lead_id,
                business_type=lead_business,
                event_type="priority_changed",
                old_value=existing_dict["priority"],
                new_value=updates["priority"],
                details=f"Priority changed from {existing_dict['priority']} to {updates['priority']}",
            )
        if "internal_notes" in updates and updates["internal_notes"] is not None and updates["internal_notes"] != existing_dict.get("internal_notes"):
            _record_lead_history(
                c,
                lead_id=lead_id,
                business_type=lead_business,
                event_type="notes_added",
                old_value=existing_dict.get("internal_notes"),
                new_value=updates["internal_notes"],
                details="Internal notes updated",
            )
        if "customer_contact" in updates and updates["customer_contact"] is not None and updates["customer_contact"] != existing_dict.get("customer_contact"):
            _record_lead_history(
                c,
                lead_id=lead_id,
                business_type=lead_business,
                event_type="contact_updated",
                old_value=existing_dict.get("customer_contact"),
                new_value=updates["customer_contact"],
                details="Customer contact updated",
            )
        if "next_follow_up_at" in updates and updates["next_follow_up_at"] is not None and updates["next_follow_up_at"] != existing_dict.get("next_follow_up_at"):
            _record_lead_history(
                c,
                lead_id=lead_id,
                business_type=lead_business,
                event_type="follow_up_scheduled",
                old_value=existing_dict.get("next_follow_up_at"),
                new_value=updates["next_follow_up_at"],
                details=f"Follow-up scheduled for {updates['next_follow_up_at']}",
            )
        if updates.get("follow_up_completed"):
            _record_lead_history(
                c,
                lead_id=lead_id,
                business_type=lead_business,
                event_type="follow_up_completed",
                new_value=updates.get("lead_status") or existing_dict["lead_status"],
                details="Follow-up marked as completed",
            )

        conn.commit()
        c.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
        row = c.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_lead_history(lead_id: int, business_type: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
    """Retrieve immutable activity history for a lead, enforcing business_type if provided."""
    lead = get_lead_by_id(lead_id, business_type=business_type)
    if not lead:
        return None
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute(
            "SELECT * FROM lead_activity_history WHERE lead_id = ? ORDER BY created_at DESC, id DESC",
            (lead_id,),
        )
        return [dict(r) for r in c.fetchall()]
    finally:
        conn.close()


def get_leads_summary(business_type: Optional[str] = None) -> Dict[str, Any]:
    """Return lead count summary grouped by business_type, status, and platform."""
    conn = get_connection()
    c = conn.cursor()
    try:
        where_sql = "WHERE business_type = ?" if business_type else ""
        params = (business_type,) if business_type else ()

        c.execute(f"SELECT COUNT(*) AS cnt FROM leads {where_sql}", params)
        total = c.fetchone()["cnt"]

        c.execute(f"SELECT business_type, COUNT(*) AS cnt FROM leads {where_sql} GROUP BY business_type", params)
        by_business = {r["business_type"]: r["cnt"] for r in c.fetchall()}

        c.execute(f"SELECT lead_status, COUNT(*) AS cnt FROM leads {where_sql} GROUP BY lead_status", params)
        by_status = {r["lead_status"]: r["cnt"] for r in c.fetchall()}

        c.execute(f"SELECT platform, COUNT(*) AS cnt FROM leads {where_sql} GROUP BY platform", params)
        by_platform = {r["platform"]: r["cnt"] for r in c.fetchall()}

        fu_where = f"{where_sql} AND" if where_sql else "WHERE"
        c.execute(
            f"SELECT COUNT(*) AS cnt FROM leads {fu_where} next_follow_up_at IS NOT NULL AND lead_status NOT IN ('Converted', 'Lost')",
            params,
        )
        pending_follow_ups = c.fetchone()["cnt"]

        c.execute(
            f"SELECT COUNT(*) AS cnt FROM leads {fu_where} next_follow_up_at IS NOT NULL AND next_follow_up_at < strftime('%Y-%m-%dT%H:%M:%S', 'now') AND lead_status NOT IN ('Converted', 'Lost')",
            params,
        )
        overdue_follow_ups = c.fetchone()["cnt"]

        return {
            "total": total,
            "by_business": by_business,
            "by_status": by_status,
            "by_platform": by_platform,
            "pending_follow_ups": pending_follow_ups,
            "overdue_follow_ups": overdue_follow_ups,
        }
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized.")
