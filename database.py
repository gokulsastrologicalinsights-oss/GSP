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
    conn = sqlite3.connect(get_db_path(), timeout=15.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=15000;")
    except sqlite3.OperationalError:
        pass
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
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('ui_theme', 'dark')")
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
    # Deduplicate any legacy duplicate posting_slots before enforcing uniqueness
    cursor.execute("""
    DELETE FROM posting_slots
    WHERE id NOT IN (
        SELECT MIN(id) FROM posting_slots GROUP BY account_key, day_of_week, slot_time
    )
    """)
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_posting_slots_unique ON posting_slots (account_key, day_of_week, slot_time)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS posting_schedule_settings (
        account_key TEXT PRIMARY KEY,
        timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
        weekly_goal INTEGER NOT NULL DEFAULT 14,
        enabled_days TEXT NOT NULL DEFAULT '[0,1,2,3,4,5,6]',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

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

    # Community Inbox: Post metadata cache (idempotent upsert)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS social_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT NOT NULL,
        account_id TEXT NOT NULL,
        post_id TEXT NOT NULL,
        caption TEXT,
        thumbnail_url TEXT,
        permalink TEXT,
        media_type TEXT,
        post_date TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(platform, post_id)
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_social_posts_platform_date ON social_posts (platform, post_date DESC)")

    # Community Inbox: 3-level reply suggestions per comment
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inbox_suggestions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT NOT NULL,
        comment_id TEXT NOT NULL,
        language TEXT,
        sentiment TEXT,
        intent TEXT,
        short_reply TEXT,
        medium_reply TEXT,
        detailed_reply TEXT,
        selected_level TEXT,
        reason TEXT,
        recommend_no_reply INTEGER DEFAULT 0,
        manual_review_required INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(platform, comment_id)
    )
    """)

    # Extend activities with optional metadata columns if not present
    cursor.execute("PRAGMA table_info(activities)")
    act_cols = {row["name"] for row in cursor.fetchall()}
    for col_name, col_type in [
        ("author_avatar", "TEXT"),
        ("comment_timestamp", "TEXT"),
        ("sentiment", "TEXT"),
        ("replied_at", "TEXT"),
    ]:
        if col_name not in act_cols:
            cursor.execute(f"ALTER TABLE activities ADD COLUMN {col_name} {col_type}")

    # Account-level 30-minute automatic sync & reply mode state
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS account_sync_state (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT NOT NULL,
        account_id TEXT NOT NULL,
        account_name TEXT,
        auto_sync_enabled INTEGER DEFAULT 1,
        sync_interval_minutes INTEGER DEFAULT 30,
        reply_mode TEXT DEFAULT 'MANUAL_APPROVAL',
        last_sync_at TEXT,
        last_successful_sync_at TEXT,
        next_sync_at TEXT,
        cursor TEXT,
        is_syncing INTEGER DEFAULT 0,
        sync_claimed_at TEXT,
        failed_sync_count INTEGER DEFAULT 0,
        backoff_until TEXT,
        last_error TEXT,
        comments_processed INTEGER DEFAULT 0,
        auto_replies_sent INTEGER DEFAULT 0,
        manual_review_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(platform, account_id)
    )
    """)

    # Sync & recovery audit history
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sync_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT NOT NULL,
        account_id TEXT NOT NULL,
        sync_type TEXT NOT NULL,
        status TEXT NOT NULL,
        comments_fetched INTEGER DEFAULT 0,
        comments_new INTEGER DEFAULT 0,
        auto_replies_sent INTEGER DEFAULT 0,
        manual_review_flagged INTEGER DEFAULT 0,
        error_message TEXT,
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP
    )
    """)

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


def ensure_approval_queue_columns() -> None:
    """Safely add smart-reply columns to approval_queue if missing."""
    conn = get_connection()
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(approval_queue)").fetchall()}
        if "sentiment" not in cols:
            conn.execute("ALTER TABLE approval_queue ADD COLUMN sentiment TEXT DEFAULT 'neutral'")
        if "generation_method" not in cols:
            conn.execute("ALTER TABLE approval_queue ADD COLUMN generation_method TEXT DEFAULT 'local_contextual'")
        if "activity_id" not in cols:
            conn.execute("ALTER TABLE approval_queue ADD COLUMN activity_id INTEGER")
        conn.commit()
    finally:
        conn.close()


def _update_queue_status_simple(
    queue_id: int, new_status: str, user_action: str
) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    with _approval_lock:
        conn = get_connection()
        c = conn.cursor()
        try:
            c.execute("BEGIN IMMEDIATE")
            c.execute(
                """
                UPDATE approval_queue
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status IN ('pending', 'manual_followup')
                """,
                (new_status, queue_id),
            )
            if c.rowcount == 0:
                c.execute("SELECT * FROM approval_queue WHERE id = ?", (queue_id,))
                row = c.fetchone()
                conn.rollback()
                if not row:
                    return (False, "not_found", None)
                return (False, f"invalid_transition_from_{row['status']}_to_{new_status}", dict(row))
            c.execute("SELECT * FROM approval_queue WHERE id = ?", (queue_id,))
            updated = dict(c.fetchone())
            _log_approval_activity_with_cursor(c, updated, user_action=user_action)
            conn.commit()
            return (True, None, updated)
        finally:
            conn.close()


def ignore_approval_item(queue_id: int) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """Mark a pending or manual_followup queue item as ignored."""
    return _update_queue_status_simple(queue_id, "ignored", "ignore")


def mark_manual_followup_item(queue_id: int) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """Mark a pending queue item for manual follow-up."""
    return _update_queue_status_simple(queue_id, "manual_followup", "manual_followup")


def regenerate_approval_item(queue_id: int) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """Regenerate a personalized reply suggestion for a pending/manual_followup item."""
    import reply_suggester

    ensure_approval_queue_columns()
    with _approval_lock:
        conn = get_connection()
        c = conn.cursor()
        try:
            c.execute("SELECT * FROM approval_queue WHERE id = ?", (queue_id,))
            row = c.fetchone()
            if not row:
                return (False, "not_found", None)
            item = dict(row)
            if item["status"] not in ("pending", "manual_followup"):
                return (False, f"cannot_regenerate_status_{item['status']}", item)

            acc_row = c.execute(
                "SELECT account_name FROM accounts WHERE platform = ? AND account_id = ? LIMIT 1",
                (item["platform"], item["account_id"]),
            ).fetchone()
            account_name = acc_row["account_name"] if acc_row else None

            suggestion = reply_suggester.generate_reply_suggestion(
                comment_text=item.get("comment_text") or "",
                commenter_name=item.get("commenter_name"),
                account_name=account_name,
                platform=item.get("platform"),
            )
            c.execute(
                """
                UPDATE approval_queue
                SET suggested_reply = ?,
                    edited_reply = NULL,
                    detected_language = ?,
                    detected_intent = ?,
                    sentiment = ?,
                    review_reason = ?,
                    generation_method = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    suggestion["suggested_reply"],
                    suggestion["language"],
                    suggestion["intent"],
                    suggestion["sentiment"],
                    suggestion["reason"],
                    suggestion["generation_method"],
                    queue_id,
                ),
            )
            c.execute("SELECT * FROM approval_queue WHERE id = ?", (queue_id,))
            updated = dict(c.fetchone())
            conn.commit()
            return (True, None, updated)
        finally:
            conn.close()


def sync_review_required_to_approval_queue() -> Dict[str, int]:
    """Idempotently backfill eligible review_required activities into approval_queue."""
    import reply_suggester

    ensure_approval_queue_columns()
    with _approval_lock:
        conn = get_connection()
        c = conn.cursor()
        try:
            rows = c.execute(
                """
                SELECT a.id, a.platform, COALESCE(a.account_id, '') AS account_id,
                       a.comment_id, a.author_name, a.comment_text,
                       a.detected_language, a.detected_intent, a.reply_text,
                       a.reason, a.created_at
                FROM activities a
                WHERE a.status = 'review_required'
                  AND NOT EXISTS (
                      SELECT 1 FROM approval_queue q
                      WHERE q.platform = a.platform AND q.comment_id = a.comment_id
                  )
                """
            ).fetchall()
            inserted = 0
            for r in rows:
                suggestion = reply_suggester.generate_reply_suggestion(
                    comment_text=r["comment_text"] or "",
                    commenter_name=r["author_name"],
                    platform=r["platform"],
                )
                suggested_reply = (r["reply_text"] or "").strip() or suggestion["suggested_reply"]
                reason = (r["reason"] or "").strip() or suggestion["reason"]
                c.execute(
                    """
                    INSERT INTO approval_queue (
                        platform, account_id, comment_id, commenter_name, comment_text,
                        detected_language, detected_intent, sentiment, suggested_reply,
                        status, review_reason, generation_method, activity_id,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)
                    """,
                    (
                        r["platform"],
                        r["account_id"],
                        r["comment_id"],
                        r["author_name"],
                        r["comment_text"],
                        r["detected_language"] or suggestion["language"],
                        r["detected_intent"] or suggestion["intent"],
                        suggestion["sentiment"],
                        suggested_reply,
                        reason,
                        suggestion["generation_method"],
                        r["id"],
                        r["created_at"],
                        r["created_at"],
                    ),
                )
                inserted += 1
            conn.commit()
            pending = c.execute(
                "SELECT COUNT(id) FROM approval_queue WHERE status = 'pending'"
            ).fetchone()[0]
            return {"inserted": inserted, "pending": pending}
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


def ensure_approval_queue_columns() -> None:
    """Safely add smart-reply columns to approval_queue if missing."""
    conn = get_connection()
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(approval_queue)").fetchall()}
        if "sentiment" not in cols:
            conn.execute("ALTER TABLE approval_queue ADD COLUMN sentiment TEXT DEFAULT 'neutral'")
        if "generation_method" not in cols:
            conn.execute("ALTER TABLE approval_queue ADD COLUMN generation_method TEXT DEFAULT 'local_contextual'")
        if "activity_id" not in cols:
            conn.execute("ALTER TABLE approval_queue ADD COLUMN activity_id INTEGER")
        conn.commit()
    finally:
        conn.close()


def _update_queue_status_simple(
    queue_id: int, new_status: str, user_action: str
) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    with _approval_lock:
        conn = get_connection()
        c = conn.cursor()
        try:
            c.execute("BEGIN IMMEDIATE")
            c.execute(
                """
                UPDATE approval_queue
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status IN ('pending', 'manual_followup')
                """,
                (new_status, queue_id),
            )
            if c.rowcount == 0:
                c.execute("SELECT * FROM approval_queue WHERE id = ?", (queue_id,))
                row = c.fetchone()
                conn.rollback()
                if not row:
                    return (False, "not_found", None)
                return (False, f"invalid_transition_from_{row['status']}_to_{new_status}", dict(row))
            c.execute("SELECT * FROM approval_queue WHERE id = ?", (queue_id,))
            updated = dict(c.fetchone())
            _log_approval_activity_with_cursor(c, updated, user_action=user_action)
            conn.commit()
            return (True, None, updated)
        finally:
            conn.close()


def ignore_approval_item(queue_id: int) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """Mark a pending or manual_followup queue item as ignored."""
    return _update_queue_status_simple(queue_id, "ignored", "ignore")


def mark_manual_followup_item(queue_id: int) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """Mark a pending queue item for manual follow-up."""
    return _update_queue_status_simple(queue_id, "manual_followup", "manual_followup")


def regenerate_approval_item(queue_id: int) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """Regenerate a personalized reply suggestion for a pending/manual_followup item."""
    import reply_suggester

    ensure_approval_queue_columns()
    with _approval_lock:
        conn = get_connection()
        c = conn.cursor()
        try:
            c.execute("SELECT * FROM approval_queue WHERE id = ?", (queue_id,))
            row = c.fetchone()
            if not row:
                return (False, "not_found", None)
            item = dict(row)
            if item["status"] not in ("pending", "manual_followup"):
                return (False, f"cannot_regenerate_status_{item['status']}", item)

            acc_row = c.execute(
                "SELECT account_name FROM accounts WHERE platform = ? AND account_id = ? LIMIT 1",
                (item["platform"], item["account_id"]),
            ).fetchone()
            account_name = acc_row["account_name"] if acc_row else None

            suggestion = reply_suggester.generate_reply_suggestion(
                comment_text=item.get("comment_text") or "",
                commenter_name=item.get("commenter_name"),
                account_name=account_name,
                platform=item.get("platform"),
            )
            c.execute(
                """
                UPDATE approval_queue
                SET suggested_reply = ?,
                    edited_reply = NULL,
                    detected_language = ?,
                    detected_intent = ?,
                    sentiment = ?,
                    review_reason = ?,
                    generation_method = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    suggestion["suggested_reply"],
                    suggestion["language"],
                    suggestion["intent"],
                    suggestion["sentiment"],
                    suggestion["reason"],
                    suggestion["generation_method"],
                    queue_id,
                ),
            )
            c.execute("SELECT * FROM approval_queue WHERE id = ?", (queue_id,))
            updated = dict(c.fetchone())
            conn.commit()
            return (True, None, updated)
        finally:
            conn.close()


def sync_review_required_to_approval_queue() -> Dict[str, int]:
    """Idempotently backfill eligible review_required activities into approval_queue."""
    import reply_suggester

    ensure_approval_queue_columns()
    with _approval_lock:
        conn = get_connection()
        c = conn.cursor()
        try:
            rows = c.execute(
                """
                SELECT a.id, a.platform, COALESCE(a.account_id, '') AS account_id,
                       a.comment_id, a.author_name, a.comment_text,
                       a.detected_language, a.detected_intent, a.reply_text,
                       a.reason, a.created_at
                FROM activities a
                WHERE a.status = 'review_required'
                  AND NOT EXISTS (
                      SELECT 1 FROM approval_queue q
                      WHERE q.platform = a.platform AND q.comment_id = a.comment_id
                  )
                """
            ).fetchall()
            inserted = 0
            for r in rows:
                suggestion = reply_suggester.generate_reply_suggestion(
                    comment_text=r["comment_text"] or "",
                    commenter_name=r["author_name"],
                    platform=r["platform"],
                )
                suggested_reply = (r["reply_text"] or "").strip() or suggestion["suggested_reply"]
                reason = (r["reason"] or "").strip() or suggestion["reason"]
                c.execute(
                    """
                    INSERT INTO approval_queue (
                        platform, account_id, comment_id, commenter_name, comment_text,
                        detected_language, detected_intent, sentiment, suggested_reply,
                        status, review_reason, generation_method, activity_id,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)
                    """,
                    (
                        r["platform"],
                        r["account_id"],
                        r["comment_id"],
                        r["author_name"],
                        r["comment_text"],
                        r["detected_language"] or suggestion["language"],
                        r["detected_intent"] or suggestion["intent"],
                        suggestion["sentiment"],
                        suggested_reply,
                        reason,
                        suggestion["generation_method"],
                        r["id"],
                        r["created_at"],
                        r["created_at"],
                    ),
                )
                inserted += 1
            conn.commit()
            pending = c.execute(
                "SELECT COUNT(id) FROM approval_queue WHERE status = 'pending'"
            ).fetchone()[0]
            return {"inserted": inserted, "pending": pending}
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


def ensure_approval_queue_columns() -> None:
    """Safely add smart-reply columns to approval_queue if missing."""
    conn = get_connection()
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(approval_queue)").fetchall()}
        if "sentiment" not in cols:
            conn.execute("ALTER TABLE approval_queue ADD COLUMN sentiment TEXT DEFAULT 'neutral'")
        if "generation_method" not in cols:
            conn.execute("ALTER TABLE approval_queue ADD COLUMN generation_method TEXT DEFAULT 'local_contextual'")
        if "activity_id" not in cols:
            conn.execute("ALTER TABLE approval_queue ADD COLUMN activity_id INTEGER")
        conn.commit()
    finally:
        conn.close()


def _update_queue_status_simple(
    queue_id: int, new_status: str, user_action: str
) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    with _approval_lock:
        conn = get_connection()
        c = conn.cursor()
        try:
            c.execute("BEGIN IMMEDIATE")
            c.execute(
                """
                UPDATE approval_queue
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status IN ('pending', 'manual_followup')
                """,
                (new_status, queue_id),
            )
            if c.rowcount == 0:
                c.execute("SELECT * FROM approval_queue WHERE id = ?", (queue_id,))
                row = c.fetchone()
                conn.rollback()
                if not row:
                    return (False, "not_found", None)
                return (False, f"invalid_transition_from_{row['status']}_to_{new_status}", dict(row))
            c.execute("SELECT * FROM approval_queue WHERE id = ?", (queue_id,))
            updated = dict(c.fetchone())
            _log_approval_activity_with_cursor(c, updated, user_action=user_action)
            conn.commit()
            return (True, None, updated)
        finally:
            conn.close()


def ignore_approval_item(queue_id: int) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """Mark a pending or manual_followup queue item as ignored."""
    return _update_queue_status_simple(queue_id, "ignored", "ignore")


def mark_manual_followup_item(queue_id: int) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """Mark a pending queue item for manual follow-up."""
    return _update_queue_status_simple(queue_id, "manual_followup", "manual_followup")


def regenerate_approval_item(queue_id: int) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """Regenerate a personalized reply suggestion for a pending/manual_followup item."""
    import reply_suggester

    ensure_approval_queue_columns()
    with _approval_lock:
        conn = get_connection()
        c = conn.cursor()
        try:
            c.execute("SELECT * FROM approval_queue WHERE id = ?", (queue_id,))
            row = c.fetchone()
            if not row:
                return (False, "not_found", None)
            item = dict(row)
            if item["status"] not in ("pending", "manual_followup"):
                return (False, f"cannot_regenerate_status_{item['status']}", item)

            acc_row = c.execute(
                "SELECT account_name FROM accounts WHERE platform = ? AND account_id = ? LIMIT 1",
                (item["platform"], item["account_id"]),
            ).fetchone()
            account_name = acc_row["account_name"] if acc_row else None

            suggestion = reply_suggester.generate_reply_suggestion(
                comment_text=item.get("comment_text") or "",
                commenter_name=item.get("commenter_name"),
                account_name=account_name,
                platform=item.get("platform"),
            )
            c.execute(
                """
                UPDATE approval_queue
                SET suggested_reply = ?,
                    edited_reply = NULL,
                    detected_language = ?,
                    detected_intent = ?,
                    sentiment = ?,
                    review_reason = ?,
                    generation_method = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    suggestion["suggested_reply"],
                    suggestion["language"],
                    suggestion["intent"],
                    suggestion["sentiment"],
                    suggestion["reason"],
                    suggestion["generation_method"],
                    queue_id,
                ),
            )
            c.execute("SELECT * FROM approval_queue WHERE id = ?", (queue_id,))
            updated = dict(c.fetchone())
            conn.commit()
            return (True, None, updated)
        finally:
            conn.close()


def sync_review_required_to_approval_queue() -> Dict[str, int]:
    """Idempotently backfill eligible review_required activities into approval_queue."""
    import reply_suggester

    ensure_approval_queue_columns()
    with _approval_lock:
        conn = get_connection()
        c = conn.cursor()
        try:
            rows = c.execute(
                """
                SELECT a.id, a.platform, COALESCE(a.account_id, '') AS account_id,
                       a.comment_id, a.author_name, a.comment_text,
                       a.detected_language, a.detected_intent, a.reply_text,
                       a.reason, a.created_at
                FROM activities a
                WHERE a.status = 'review_required'
                  AND NOT EXISTS (
                      SELECT 1 FROM approval_queue q
                      WHERE q.platform = a.platform AND q.comment_id = a.comment_id
                  )
                """
            ).fetchall()
            inserted = 0
            for r in rows:
                suggestion = reply_suggester.generate_reply_suggestion(
                    comment_text=r["comment_text"] or "",
                    commenter_name=r["author_name"],
                    platform=r["platform"],
                )
                suggested_reply = (r["reply_text"] or "").strip() or suggestion["suggested_reply"]
                reason = (r["reason"] or "").strip() or suggestion["reason"]
                c.execute(
                    """
                    INSERT INTO approval_queue (
                        platform, account_id, comment_id, commenter_name, comment_text,
                        detected_language, detected_intent, sentiment, suggested_reply,
                        status, review_reason, generation_method, activity_id,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)
                    """,
                    (
                        r["platform"],
                        r["account_id"],
                        r["comment_id"],
                        r["author_name"],
                        r["comment_text"],
                        r["detected_language"] or suggestion["language"],
                        r["detected_intent"] or suggestion["intent"],
                        suggestion["sentiment"],
                        suggested_reply,
                        reason,
                        suggestion["generation_method"],
                        r["id"],
                        r["created_at"],
                        r["created_at"],
                    ),
                )
                inserted += 1
            conn.commit()
            pending = c.execute(
                "SELECT COUNT(id) FROM approval_queue WHERE status = 'pending'"
            ).fetchone()[0]
            return {"inserted": inserted, "pending": pending}
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


# =============================================================================
# Community Inbox (Post-Centric Comment Management & 3-Level Reply Workflow)
# =============================================================================

def upsert_social_post(
    platform: str,
    account_id: str,
    post_id: str,
    caption: str = "",
    thumbnail_url: str = "",
    permalink: str = "",
    media_type: str = "",
    post_date: str = "",
) -> None:
    """Idempotently insert or update post metadata in social_posts."""
    if not platform or not post_id:
        return
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute(
            """
            INSERT INTO social_posts (
                platform, account_id, post_id, caption, thumbnail_url, permalink, media_type, post_date, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(platform, post_id) DO UPDATE SET
                account_id = COALESCE(NULLIF(excluded.account_id, ''), social_posts.account_id),
                caption = COALESCE(NULLIF(excluded.caption, ''), social_posts.caption),
                thumbnail_url = COALESCE(NULLIF(excluded.thumbnail_url, ''), social_posts.thumbnail_url),
                permalink = COALESCE(NULLIF(excluded.permalink, ''), social_posts.permalink),
                media_type = COALESCE(NULLIF(excluded.media_type, ''), social_posts.media_type),
                post_date = COALESCE(NULLIF(excluded.post_date, ''), social_posts.post_date),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                platform.lower(),
                account_id or "",
                post_id,
                caption or "",
                thumbnail_url or "",
                permalink or "",
                media_type or "",
                post_date or "",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_inbox_posts(
    platform: Optional[str] = None,
    status_filter: str = "all",
    date_filter: str = "all",
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """Return posts that have received comments, sorted by most recent activity."""
    conn = get_connection()
    c = conn.cursor()
    try:
        where_clauses = ["a.post_id IS NOT NULL AND TRIM(a.post_id) != ''"]
        params: List[Any] = []

        if platform and platform.lower() in ("facebook", "instagram", "youtube"):
            where_clauses.append("LOWER(a.platform) = ?")
            params.append(platform.lower())

        if date_filter == "today":
            where_clauses.append("date(COALESCE(NULLIF(a.comment_timestamp, ''), a.created_at)) >= date('now', 'localtime')")
        elif date_filter == "7d":
            where_clauses.append("datetime(COALESCE(NULLIF(a.comment_timestamp, ''), a.created_at)) >= datetime('now', '-7 days')")
        elif date_filter == "30d":
            where_clauses.append("datetime(COALESCE(NULLIF(a.comment_timestamp, ''), a.created_at)) >= datetime('now', '-30 days')")

        where_sql = " AND ".join(where_clauses)

        having_clauses = []
        if status_filter == "unanswered":
            having_clauses.append("unanswered_count > 0")
        if search and search.strip():
            like_term = f"%{search.strip().lower()}%"
            having_clauses.append(
                "(LOWER(COALESCE(caption, '')) LIKE ? OR LOWER(a.post_id) LIKE ? OR LOWER(COALESCE(account_name, '')) LIKE ?)"
            )
            params.extend([like_term, like_term, like_term])

        having_sql = f"HAVING {' AND '.join(having_clauses)}" if having_clauses else ""

        query = f"""
            SELECT
                LOWER(a.platform) AS platform,
                a.post_id AS post_id,
                COALESCE(MAX(NULLIF(a.account_id, '')), MAX(sp.account_id), '') AS account_id,
                COALESCE(
                    MAX(acc.account_name),
                    (SELECT acc2.account_name FROM accounts acc2 WHERE LOWER(acc2.platform) = LOWER(a.platform) AND acc2.is_active = 1 LIMIT 1),
                    UPPER(a.platform) || ' Account'
                ) AS account_name,
                COALESCE(MAX(sp.caption), '') AS caption,
                COALESCE(MAX(sp.thumbnail_url), '') AS thumbnail_url,
                COALESCE(MAX(sp.permalink), '') AS permalink,
                COALESCE(MAX(sp.media_type), '') AS media_type,
                COALESCE(MAX(NULLIF(sp.post_date, '')), MIN(a.created_at)) AS post_date,
                COUNT(*) AS total_comments,
                SUM(CASE WHEN a.status = 'replied' THEN 1 ELSE 0 END) AS replied_count,
                SUM(CASE WHEN a.status = 'test_prepared' AND COALESCE(TRIM(a.reply_text), '') != '' THEN 1 ELSE 0 END) AS test_prepared_count,
                SUM(CASE WHEN a.status = 'replied' OR (a.status = 'test_prepared' AND COALESCE(TRIM(a.reply_text), '') != '') THEN 1 ELSE 0 END) AS answered_count,
                SUM(CASE WHEN NOT (a.status = 'replied' OR (a.status = 'test_prepared' AND COALESCE(TRIM(a.reply_text), '') != '')) THEN 1 ELSE 0 END) AS unanswered_count,
                MAX(COALESCE(NULLIF(a.comment_timestamp, ''), a.created_at)) AS last_activity_at
            FROM activities a
            LEFT JOIN social_posts sp
                ON LOWER(sp.platform) = LOWER(a.platform) AND sp.post_id = a.post_id
            LEFT JOIN accounts acc
                ON LOWER(acc.platform) = LOWER(a.platform) AND acc.account_id = a.account_id
            WHERE {where_sql}
            GROUP BY LOWER(a.platform), a.post_id
            {having_sql}
            ORDER BY last_activity_at DESC
            LIMIT ? OFFSET ?
        """
        c.execute(query, tuple(params + [limit, offset]))
        rows = [dict(r) for r in c.fetchall()]

        # Compute summary counts across all matching posts (without pagination)
        count_query = f"""
            SELECT
                LOWER(a.platform) AS platform,
                a.post_id AS post_id,
                COALESCE(
                    MAX(acc.account_name),
                    (SELECT acc2.account_name FROM accounts acc2 WHERE LOWER(acc2.platform) = LOWER(a.platform) AND acc2.is_active = 1 LIMIT 1),
                    ''
                ) AS account_name,
                COALESCE(MAX(sp.caption), '') AS caption,
                SUM(CASE WHEN NOT (a.status = 'replied' OR (a.status = 'test_prepared' AND COALESCE(TRIM(a.reply_text), '') != '')) THEN 1 ELSE 0 END) AS unanswered_count
            FROM activities a
            LEFT JOIN social_posts sp
                ON LOWER(sp.platform) = LOWER(a.platform) AND sp.post_id = a.post_id
            LEFT JOIN accounts acc
                ON LOWER(acc.platform) = LOWER(a.platform) AND acc.account_id = a.account_id
            WHERE {where_sql}
            GROUP BY LOWER(a.platform), a.post_id
            {having_sql}
        """
        c.execute(count_query, tuple(params))
        total_posts = len(c.fetchall())

        for row in rows:
            total = row["total_comments"] or 0
            answered = row["answered_count"] or 0
            row["progress_pct"] = round((answered / total) * 100) if total > 0 else 0
            if not row["caption"]:
                row["caption"] = f"{row['platform'].capitalize()} Post ({row['post_id']})"

        return {"posts": rows, "total_posts": total_posts}
    finally:
        conn.close()


def _ensure_comment_suggestions_with_cursor(
    c: sqlite3.Cursor,
    platform: str,
    comment_row: Dict[str, Any],
    post_caption: str = "",
    account_name: str = "",
    force_regenerate: bool = False,
) -> Dict[str, Any]:
    """Return cached 3-level suggestions for a comment, generating and persisting if missing."""
    import reply_suggester

    comment_id = comment_row["comment_id"]
    if not force_regenerate:
        c.execute(
            "SELECT * FROM inbox_suggestions WHERE LOWER(platform) = ? AND comment_id = ?",
            (platform.lower(), comment_id),
        )
        existing = c.fetchone()
        if existing:
            ex = dict(existing)
            return {
                "language": ex.get("language") or "en",
                "sentiment": ex.get("sentiment") or "neutral",
                "intent": ex.get("intent") or "neutral",
                "short": ex.get("short_reply") or "",
                "medium": ex.get("medium_reply") or "",
                "detailed": ex.get("detailed_reply") or "",
                "selected_level": ex.get("selected_level"),
                "recommend_no_reply": bool(ex.get("recommend_no_reply")),
                "manual_review_required": bool(ex.get("manual_review_required")),
                "reason": ex.get("reason") or "",
            }

    gen = reply_suggester.generate_three_level_suggestions(
        comment_text=comment_row.get("comment_text") or "",
        commenter_name=comment_row.get("author_name") or "",
        account_name=account_name,
        platform=platform,
        post_caption=post_caption,
    )

    c.execute(
        """
        INSERT INTO inbox_suggestions (
            platform, comment_id, language, sentiment, intent,
            short_reply, medium_reply, detailed_reply,
            reason, recommend_no_reply, manual_review_required, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(platform, comment_id) DO UPDATE SET
            language = excluded.language,
            sentiment = excluded.sentiment,
            intent = excluded.intent,
            short_reply = excluded.short_reply,
            medium_reply = excluded.medium_reply,
            detailed_reply = excluded.detailed_reply,
            reason = excluded.reason,
            recommend_no_reply = excluded.recommend_no_reply,
            manual_review_required = excluded.manual_review_required,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            platform.lower(),
            comment_id,
            gen["language"],
            gen["sentiment"],
            gen["intent"],
            gen["short"],
            gen["medium"],
            gen["detailed"],
            gen["reason"],
            1 if gen.get("recommend_no_reply") else 0,
            1 if gen.get("manual_review_required") else 0,
        ),
    )

    return {
        "language": gen["language"],
        "sentiment": gen["sentiment"],
        "intent": gen["intent"],
        "short": gen["short"],
        "medium": gen["medium"],
        "detailed": gen["detailed"],
        "selected_level": None,
        "recommend_no_reply": bool(gen.get("recommend_no_reply")),
        "manual_review_required": bool(gen.get("manual_review_required")),
        "reason": gen["reason"],
    }


def get_inbox_post_comments(
    platform: str,
    post_id: str,
    limit: int = 20,
    offset: int = 0,
    status_filter: str = "all",
) -> Optional[Dict[str, Any]]:
    """Return selected post metadata and paginated comments with 3-level suggestions."""
    conn = get_connection()
    c = conn.cursor()
    try:
        plat = platform.lower()
        c.execute(
            """
            SELECT
                LOWER(a.platform) AS platform,
                a.post_id AS post_id,
                COALESCE(MAX(NULLIF(a.account_id, '')), MAX(sp.account_id), '') AS account_id,
                COALESCE(
                    MAX(acc.account_name),
                    (SELECT acc2.account_name FROM accounts acc2 WHERE LOWER(acc2.platform) = ? AND acc2.is_active = 1 LIMIT 1),
                    UPPER(a.platform) || ' Account'
                ) AS account_name,
                COALESCE(MAX(sp.caption), '') AS caption,
                COALESCE(MAX(sp.thumbnail_url), '') AS thumbnail_url,
                COALESCE(MAX(sp.permalink), '') AS permalink,
                COALESCE(MAX(sp.media_type), '') AS media_type,
                COALESCE(MAX(NULLIF(sp.post_date, '')), MIN(a.created_at)) AS post_date,
                COUNT(*) AS total_comments,
                SUM(CASE WHEN a.status = 'replied' THEN 1 ELSE 0 END) AS replied_count,
                SUM(CASE WHEN a.status = 'test_prepared' AND COALESCE(TRIM(a.reply_text), '') != '' THEN 1 ELSE 0 END) AS test_prepared_count,
                SUM(CASE WHEN a.status = 'replied' OR (a.status = 'test_prepared' AND COALESCE(TRIM(a.reply_text), '') != '') THEN 1 ELSE 0 END) AS answered_count,
                SUM(CASE WHEN NOT (a.status = 'replied' OR (a.status = 'test_prepared' AND COALESCE(TRIM(a.reply_text), '') != '')) THEN 1 ELSE 0 END) AS unanswered_count
            FROM activities a
            LEFT JOIN social_posts sp
                ON LOWER(sp.platform) = LOWER(a.platform) AND sp.post_id = a.post_id
            LEFT JOIN accounts acc
                ON LOWER(acc.platform) = LOWER(a.platform) AND acc.account_id = a.account_id
            WHERE LOWER(a.platform) = ? AND a.post_id = ?
            GROUP BY LOWER(a.platform), a.post_id
            """,
            (plat, plat, post_id),
        )
        post_row = c.fetchone()
        if not post_row:
            return None

        post = dict(post_row)
        if not post["caption"]:
            post["caption"] = f"{post['platform'].capitalize()} Post ({post['post_id']})"
        total = post["total_comments"] or 0
        answered = post["answered_count"] or 0
        post["progress_pct"] = round((answered / total) * 100) if total > 0 else 0

        where_extra = ""
        if status_filter == "unanswered":
            where_extra = "AND NOT (a.status = 'replied' OR (a.status = 'test_prepared' AND COALESCE(TRIM(a.reply_text), '') != ''))"

        c.execute(
            f"""
            SELECT COUNT(*) AS cnt
            FROM activities a
            WHERE LOWER(a.platform) = ? AND a.post_id = ? {where_extra}
            """,
            (plat, post_id),
        )
        filtered_total = c.fetchone()["cnt"]

        c.execute(
            f"""
            SELECT
                a.*,
                aq.id AS approval_queue_id,
                aq.status AS approval_status,
                aq.edited_reply AS aq_edited_reply,
                aq.published_at AS aq_published_at,
                aq.review_reason AS aq_review_reason
            FROM activities a
            LEFT JOIN approval_queue aq
                ON LOWER(aq.platform) = LOWER(a.platform) AND aq.comment_id = a.comment_id
            WHERE LOWER(a.platform) = ? AND a.post_id = ? {where_extra}
            ORDER BY COALESCE(NULLIF(a.comment_timestamp, ''), a.created_at) DESC, a.id DESC
            LIMIT ? OFFSET ?
            """,
            (plat, post_id, limit, offset),
        )
        raw_comments = [dict(r) for r in c.fetchall()]

        comments: List[Dict[str, Any]] = []
        for row in raw_comments:
            sugg = _ensure_comment_suggestions_with_cursor(
                c,
                platform=plat,
                comment_row=row,
                post_caption=post["caption"],
                account_name=post["account_name"],
            )
            is_answered = (
                row.get("status") == "replied"
                or (row.get("status") == "test_prepared" and bool((row.get("reply_text") or "").strip()))
            )
            effective_reply = row.get("reply_text") or row.get("aq_edited_reply") or ""
            comments.append(
                {
                    "id": row["id"],
                    "platform": plat,
                    "post_id": post_id,
                    "account_id": row.get("account_id") or post["account_id"],
                    "account_name": post["account_name"],
                    "comment_id": row["comment_id"],
                    "author_name": row.get("author_name") or "Community Member",
                    "author_avatar": row.get("author_avatar") or "",
                    "comment_text": row.get("comment_text") or "",
                    "comment_timestamp": row.get("comment_timestamp") or row.get("created_at"),
                    "detected_language": sugg["language"],
                    "sentiment": row.get("sentiment") or sugg["sentiment"],
                    "detected_intent": sugg["intent"],
                    "reply_text": effective_reply if is_answered else "",
                    "status": row.get("status") or "review_required",
                    "replied_at": row.get("replied_at") or row.get("aq_published_at") or "",
                    "is_answered": is_answered,
                    "reason": row.get("reason") or row.get("aq_review_reason") or sugg["reason"],
                    "api_error": row.get("api_error") or "",
                    "approval_queue_id": row.get("approval_queue_id"),
                    "approval_status": row.get("approval_status"),
                    "suggestions": sugg,
                }
            )

        conn.commit()
        return {
            "post": post,
            "comments": comments,
            "total_filtered": filtered_total,
            "has_more": (offset + len(comments)) < filtered_total,
        }
    finally:
        conn.close()


def regenerate_inbox_comment_suggestions(platform: str, comment_id: str) -> Optional[Dict[str, Any]]:
    """Regenerate and persist 3-level suggestions for a single comment."""
    conn = get_connection()
    c = conn.cursor()
    try:
        plat = platform.lower()
        c.execute(
            "SELECT * FROM activities WHERE LOWER(platform) = ? AND comment_id = ?",
            (plat, comment_id),
        )
        row = c.fetchone()
        if not row:
            return None
        comment_row = dict(row)
        post_caption = ""
        account_name = ""
        if comment_row.get("post_id"):
            c.execute(
                "SELECT caption FROM social_posts WHERE LOWER(platform) = ? AND post_id = ?",
                (plat, comment_row["post_id"]),
            )
            sp = c.fetchone()
            if sp:
                post_caption = sp["caption"] or ""
        c.execute(
            "SELECT account_name FROM accounts WHERE LOWER(platform) = ? AND is_active = 1 LIMIT 1",
            (plat,),
        )
        acc = c.fetchone()
        if acc:
            account_name = acc["account_name"] or ""

        sugg = _ensure_comment_suggestions_with_cursor(
            c,
            platform=plat,
            comment_row=comment_row,
            post_caption=post_caption,
            account_name=account_name,
            force_regenerate=True,
        )
        conn.commit()
        return sugg
    finally:
        conn.close()


def _reconcile_platform_reply(
    platform: str,
    account_id: str,
    post_id: str,
    comment_id: str,
    reply_text: str,
    access_token: str,
) -> bool:
    """Best-effort check after uncertain network outcome to see if reply already exists on platform."""
    try:
        import requests
        plat = platform.lower()
        if plat == "facebook":
            url = f"https://graph.facebook.com/v19.0/{comment_id}/comments"
            res = requests.get(url, params={"access_token": access_token, "fields": "id,message,from", "limit": 10}, timeout=8)
            data = res.json().get("data", [])
            return any((d.get("message") or "").strip() == reply_text.strip() for d in data)
        if plat == "instagram":
            url = f"https://graph.facebook.com/v19.0/{comment_id}/replies"
            res = requests.get(url, params={"access_token": access_token, "fields": "id,text", "limit": 10}, timeout=8)
            data = res.json().get("data", [])
            return any((d.get("text") or "").strip() == reply_text.strip() for d in data)
        if plat == "youtube":
            url = "https://www.googleapis.com/youtube/v3/comments"
            res = requests.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                params={"part": "snippet", "parentId": comment_id, "maxResults": 10},
                timeout=8,
            )
            items = res.json().get("items", [])
            return any((it.get("snippet", {}).get("textOriginal") or "").strip() == reply_text.strip() for it in items)
    except Exception:
        return False
    return False


def send_inbox_reply(
    platform: str,
    comment_id: str,
    reply_text: str,
    selected_level: str = "custom",
    now_ts: Optional[float] = None,
    from_queue: bool = False,
) -> Dict[str, Any]:
    """Explicitly send (or Safe-Test-record) a reply to a specific comment with full safety checks.

    1. Validate original comment ID.
    2. Verify connected account.
    3. Verify reply eligibility & non-empty text.
    4. Check whether a reply has already been sent (duplicate prevention).
    5. Apply existing rate limits and cooldowns.
    6. Send exactly once (or record test_prepared in Safe Testing Mode).
    7. Reconcile uncertain network outcomes before retrying.
    """
    plat = (platform or "").strip().lower()
    cid = (comment_id or "").strip()
    text = (reply_text or "").strip()
    now = now_ts if now_ts is not None else time.time()

    if not cid:
        return {"success": False, "reason": "invalid_comment_id", "error": "Comment ID is required."}
    if plat not in ("facebook", "instagram", "youtube"):
        return {"success": False, "reason": "unsupported_platform", "error": f"Unsupported platform: {platform}"}
    if not text:
        return {"success": False, "reason": "empty_reply_text", "error": "Reply text cannot be empty."}

    with _approval_lock:
        conn = get_connection()
        c = conn.cursor()
        try:
            c.execute("BEGIN IMMEDIATE")

            # 1. Validate original comment exists
            c.execute(
                "SELECT * FROM activities WHERE LOWER(platform) = ? AND comment_id = ?",
                (plat, cid),
            )
            act_row = c.fetchone()
            if not act_row:
                conn.rollback()
                return {"success": False, "reason": "comment_not_found", "error": "Original comment not found."}
            act = dict(act_row)

            # 2. Check global kill switch & settings
            c.execute("SELECT key, value FROM settings")
            settings = {r["key"]: r["value"] for r in c.fetchall()}
            if settings.get("global_kill_switch", "false") == "true":
                conn.rollback()
                return {"success": False, "reason": "global_kill_switch_active", "error": "Global kill switch is active."}

            safe_test_mode = settings.get("safe_test_mode", "true") == "true"

            # 3. Duplicate reply prevention
            if act.get("status") == "replied":
                conn.rollback()
                return {
                    "success": False,
                    "reason": "already_replied",
                    "duplicate_blocked": True,
                    "error": "A reply has already been sent to this comment.",
                }
            c.execute(
                """
                SELECT id, attempt_status FROM publishing_attempts
                WHERE LOWER(platform) = ? AND comment_id = ? AND attempt_status IN ('replied', 'test_prepared')
                ORDER BY id DESC LIMIT 1
                """,
                (plat, cid),
            )
            dup_att = c.fetchone()
            if dup_att:
                conn.rollback()
                return {
                    "success": False,
                    "reason": "duplicate_publishing_attempt",
                    "duplicate_blocked": True,
                    "error": "A reply or safe-test send has already been recorded for this comment.",
                }

            # 4. Verify connected account
            account_id = act.get("account_id") or ""
            if account_id:
                c.execute(
                    "SELECT account_id, account_name, access_token FROM accounts WHERE LOWER(platform) = ? AND account_id = ? AND is_active = 1",
                    (plat, account_id),
                )
                acct = c.fetchone()
            else:
                acct = None
            if not acct:
                c.execute(
                    "SELECT account_id, account_name, access_token FROM accounts WHERE LOWER(platform) = ? AND is_active = 1 LIMIT 1",
                    (plat,),
                )
                acct = c.fetchone()

            if not acct or not (acct["access_token"] or "").strip():
                conn.rollback()
                return {
                    "success": False,
                    "reason": f"account_disconnected_{plat}",
                    "error": f"No active {plat.capitalize()} account with valid token connected.",
                }
            resolved_account_id = acct["account_id"]
            access_token = acct["access_token"]

            # 5. Rate limits check
            commenter_key = f"{plat}:{act.get('author_name') or 'unknown'}"
            c.execute("SELECT COUNT(*) AS cnt FROM reply_rate_log WHERE replied_at >= ?", (now - 3600,))
            if c.fetchone()["cnt"] >= MAX_REPLIES_PER_HOUR:
                conn.rollback()
                return {"success": False, "reason": "rate_limit_hourly_30", "error": "Hourly reply rate limit reached (30/hr)."}
            c.execute("SELECT COUNT(*) AS cnt FROM reply_rate_log WHERE replied_at >= ?", (now - 86400,))
            if c.fetchone()["cnt"] >= MAX_REPLIES_PER_DAY:
                conn.rollback()
                return {"success": False, "reason": "rate_limit_daily_100", "error": "Daily reply rate limit reached (100/day)."}
            c.execute("SELECT MAX(replied_at) AS last_ts FROM reply_rate_log")
            last_row = c.fetchone()
            if last_row and last_row["last_ts"] is not None and (now - last_row["last_ts"]) < MIN_REPLY_INTERVAL_SECONDS:
                if from_queue:
                    conn.rollback()
                    return {"success": False, "queued_waiting": True, "reason": "rate_limit_interval_120s", "error": "Waiting for 120s interval."}
                c.execute(
                    """
                    CREATE TABLE IF NOT EXISTS queued_manual_replies (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        platform TEXT NOT NULL,
                        comment_id TEXT NOT NULL UNIQUE,
                        reply_text TEXT NOT NULL,
                        selected_level TEXT DEFAULT 'custom',
                        status TEXT NOT NULL DEFAULT 'queued',
                        error_message TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        dispatched_at TIMESTAMP
                    )
                    """
                )
                c.execute(
                    """
                    INSERT INTO queued_manual_replies (platform, comment_id, reply_text, selected_level, status, error_message)
                    VALUES (?, ?, ?, ?, 'queued', NULL)
                    ON CONFLICT(comment_id) DO UPDATE SET
                        platform = excluded.platform,
                        reply_text = excluded.reply_text,
                        selected_level = excluded.selected_level,
                        status = 'queued',
                        error_message = NULL,
                        created_at = CURRENT_TIMESTAMP
                    """,
                    (plat, cid, text, selected_level),
                )
                c.execute(
                    "UPDATE activities SET reply_text = ?, status = 'queued', reason = 'queued_120s_interval' WHERE id = ?",
                    (text, act["id"]),
                )
                c.execute(
                    "SELECT id FROM approval_queue WHERE LOWER(platform) = ? AND comment_id = ?",
                    (plat, cid),
                )
                existing_aq = c.fetchone()
                if existing_aq:
                    c.execute(
                        "UPDATE approval_queue SET edited_reply = ?, status = 'approved', approved_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (text, existing_aq["id"]),
                    )
                else:
                    c.execute(
                        """
                        INSERT INTO approval_queue (
                            platform, account_id, comment_id, commenter_name, comment_text,
                            detected_language, detected_intent, suggested_reply, edited_reply, status, approved_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'approved', CURRENT_TIMESTAMP)
                        """,
                        (
                            plat,
                            resolved_account_id,
                            cid,
                            act.get("author_name"),
                            act.get("comment_text") or "",
                            act.get("detected_language"),
                            act.get("detected_intent"),
                            text,
                            text,
                        ),
                    )
                conn.commit()
                return {
                    "success": True,
                    "queued": True,
                    "safe_test_mode": False,
                    "dispatched": False,
                    "status": "queued",
                    "platform": plat,
                    "comment_id": cid,
                    "reply_text": text,
                    "selected_level": selected_level,
                    "message": "Queued for automatic background delivery (120s anti-spam interval).",
                }

            # Ensure approval_queue row exists for audit/publishing_attempts linkage
            c.execute(
                "SELECT id FROM approval_queue WHERE LOWER(platform) = ? AND comment_id = ?",
                (plat, cid),
            )
            aq_row = c.fetchone()
            if aq_row:
                aq_id = aq_row["id"]
            else:
                c.execute(
                    """
                    INSERT INTO approval_queue (
                        platform, account_id, comment_id, commenter_name, comment_text,
                        detected_language, detected_intent, suggested_reply, edited_reply, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                    """,
                    (
                        plat,
                        resolved_account_id,
                        cid,
                        act.get("author_name"),
                        act.get("comment_text") or "",
                        act.get("detected_language"),
                        act.get("detected_intent"),
                        text,
                        text,
                    ),
                )
                aq_id = c.lastrowid

            # 6. Safe Testing Mode: record without external API call
            if safe_test_mode:
                c.execute(
                    """
                    UPDATE activities
                    SET reply_text = ?, status = 'test_prepared', reason = 'manual_safe_test_send',
                        api_error = NULL, replied_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (text, act["id"]),
                )
                c.execute(
                    """
                    UPDATE approval_queue
                    SET edited_reply = ?, status = 'approved', approved_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (text, aq_id),
                )
                _record_publishing_attempt_with_cursor(
                    c,
                    approval_queue_id=aq_id,
                    platform=plat,
                    account_id=resolved_account_id,
                    comment_id=cid,
                    final_reply=text,
                    attempt_status="test_prepared",
                    validation_result="passed",
                    target_type=_PLATFORM_TARGET_TYPE.get(plat, "unknown"),
                )
                _log_approval_activity_with_cursor(
                    c,
                    item={
                        "id": aq_id,
                        "platform": plat,
                        "comment_id": cid,
                        "comment_text": act.get("comment_text") or "",
                        "suggested_reply": text,
                        "edited_reply": text,
                    },
                    user_action="inbox_send_safe_test",
                    validation_result="passed",
                )
                c.execute(
                    "UPDATE inbox_suggestions SET selected_level = ?, updated_at = CURRENT_TIMESTAMP WHERE LOWER(platform) = ? AND comment_id = ?",
                    (selected_level, plat, cid),
                )
                conn.commit()
                return {
                    "success": True,
                    "safe_test_mode": True,
                    "dispatched": False,
                    "status": "test_prepared",
                    "platform": plat,
                    "comment_id": cid,
                    "reply_text": text,
                    "selected_level": selected_level,
                    "message": "Reply recorded in Safe Testing Mode (no live API call made).",
                }

            # 7. Live Mode: reserve rate limit and dispatch via platform adapter
            c.execute(
                """
                INSERT INTO reply_rate_log (platform, account_id, comment_id, commenter_key, template_id, replied_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (plat, resolved_account_id, cid, commenter_key, selected_level, now),
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            return {"success": False, "reason": "db_error", "error": str(e)}
        finally:
            conn.close()

    # Outside lock: execute single live API call
    api_res: Optional[Dict[str, Any]] = None
    network_error: Optional[str] = None
    reconciled_sent = False

    try:
        if plat == "facebook":
            from facebook_service import FacebookService
            api_res = FacebookService.send_reply(cid, text, access_token)
        elif plat == "instagram":
            from instagram_service import InstagramService
            api_res = InstagramService.send_reply(cid, text, access_token)
        elif plat == "youtube":
            from youtube_service import YouTubeService
            valid_token = YouTubeService.get_valid_access_token(resolved_account_id) or access_token
            api_res = YouTubeService.send_reply(cid, text, valid_token)
            access_token = valid_token
    except Exception as exc:
        network_error = str(exc)
        reconciled_sent = _reconcile_platform_reply(
            plat, resolved_account_id, act.get("post_id") or "", cid, text, access_token
        )

    with _approval_lock:
        conn = get_connection()
        c = conn.cursor()
        try:
            is_confirmed = bool((api_res and "id" in api_res) or reconciled_sent)
            if is_confirmed:
                c.execute(
                    """
                    UPDATE activities
                    SET reply_text = ?, status = 'replied', reason = 'manual_inbox_reply',
                        api_error = NULL, replied_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (text, act["id"]),
                )
                c.execute(
                    """
                    UPDATE approval_queue
                    SET edited_reply = ?, status = 'replied', published_at = CURRENT_TIMESTAMP,
                        publishing_error = NULL, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (text, aq_id),
                )
                _record_publishing_attempt_with_cursor(
                    c,
                    approval_queue_id=aq_id,
                    platform=plat,
                    account_id=resolved_account_id,
                    comment_id=cid,
                    final_reply=text,
                    attempt_status="replied",
                    validation_result="passed",
                    target_type=_PLATFORM_TARGET_TYPE.get(plat, "unknown"),
                )
                _log_approval_activity_with_cursor(
                    c,
                    item={
                        "id": aq_id,
                        "platform": plat,
                        "comment_id": cid,
                        "comment_text": act.get("comment_text") or "",
                        "suggested_reply": text,
                        "edited_reply": text,
                    },
                    user_action="inbox_send_live",
                    validation_result="passed",
                )
                c.execute(
                    "UPDATE inbox_suggestions SET selected_level = ?, updated_at = CURRENT_TIMESTAMP WHERE LOWER(platform) = ? AND comment_id = ?",
                    (selected_level, plat, cid),
                )
                conn.commit()
                return {
                    "success": True,
                    "safe_test_mode": False,
                    "dispatched": True,
                    "reconciled": reconciled_sent,
                    "status": "replied",
                    "platform": plat,
                    "comment_id": cid,
                    "reply_text": text,
                    "selected_level": selected_level,
                    "platform_response": api_res or {},
                }

            # Uncertain network outcome vs explicit API rejection
            c.execute("DELETE FROM reply_rate_log WHERE comment_id = ?", (cid,))
            if network_error:
                c.execute(
                    """
                    UPDATE activities
                    SET status = 'reconciliation_required', api_error = ?, reason = 'uncertain_network_outcome'
                    WHERE id = ?
                    """,
                    (network_error, act["id"]),
                )
                _record_publishing_attempt_with_cursor(
                    c,
                    approval_queue_id=aq_id,
                    platform=plat,
                    account_id=resolved_account_id,
                    comment_id=cid,
                    final_reply=text,
                    attempt_status="uncertain_network",
                    validation_result="passed",
                    error_details=network_error,
                    target_type=_PLATFORM_TARGET_TYPE.get(plat, "unknown"),
                )
                conn.commit()
                return {
                    "success": False,
                    "safe_test_mode": False,
                    "dispatched": False,
                    "reconciliation_required": True,
                    "status": "reconciliation_required",
                    "reason": "uncertain_network_outcome",
                    "error": f"Network outcome uncertain ({network_error}). Platform state checked; manual verification required before retrying.",
                }

            err_msg = str((api_res or {}).get("error") or "Platform API rejected reply")
            c.execute(
                "UPDATE activities SET status = 'failed', api_error = ? WHERE id = ?",
                (err_msg, act["id"]),
            )
            c.execute(
                "UPDATE approval_queue SET status = 'failed', publishing_error = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (err_msg, aq_id),
            )
            _record_publishing_attempt_with_cursor(
                c,
                approval_queue_id=aq_id,
                platform=plat,
                account_id=resolved_account_id,
                comment_id=cid,
                final_reply=text,
                attempt_status="failed",
                validation_result="passed",
                error_details=err_msg,
                target_type=_PLATFORM_TARGET_TYPE.get(plat, "unknown"),
            )
            conn.commit()
            return {
                "success": False,
                "safe_test_mode": False,
                "dispatched": False,
                "status": "failed",
                "reason": "platform_api_error",
                "error": err_msg,
            }
        finally:
            conn.close()


def get_account_reply_mode(platform: str, account_id: str) -> Optional[str]:
    """Return the account's configured reply_mode ('AUTOMATIC_REPLY', 'MANUAL_APPROVAL', 'DISABLED') or None if unset."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT reply_mode FROM account_sync_state WHERE platform = ? AND account_id = ?",
            (platform, account_id),
        ).fetchone()
        return row["reply_mode"] if row else None
    except Exception:
        return None
    finally:
        conn.close()


def process_queued_manual_replies() -> Dict[str, Any]:
    """Dispatch the oldest queued manual reply if the 120s interval has elapsed."""
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS queued_manual_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                comment_id TEXT NOT NULL UNIQUE,
                reply_text TEXT NOT NULL,
                selected_level TEXT DEFAULT 'custom',
                status TEXT NOT NULL DEFAULT 'queued',
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                dispatched_at TIMESTAMP
            )
            """
        )
        row = conn.execute(
            "SELECT * FROM queued_manual_replies WHERE status = 'queued' ORDER BY id ASC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return {"processed": 0}

    item = dict(row)
    res = send_inbox_reply(
        platform=item["platform"],
        comment_id=item["comment_id"],
        reply_text=item["reply_text"],
        selected_level=item.get("selected_level") or "custom",
        from_queue=True,
    )
    if res.get("queued_waiting"):
        return {"processed": 0, "waiting": True}

    conn = get_connection()
    try:
        if res.get("success") or res.get("duplicate_blocked"):
            conn.execute(
                "UPDATE queued_manual_replies SET status = 'sent', dispatched_at = CURRENT_TIMESTAMP, error_message = NULL WHERE id = ?",
                (item["id"],),
            )
        else:
            conn.execute(
                "UPDATE queued_manual_replies SET status = 'failed', error_message = ? WHERE id = ?",
                ((res.get("error") or res.get("reason") or "Unknown error")[:500], item["id"]),
            )
        conn.commit()
    finally:
        conn.close()
    return {"processed": 1, "result": res}


def get_comment_analytics(platform: Optional[str] = None, period: str = "day") -> Dict[str, Any]:
    """Return comment counts (total, auto_replied, manual_replied, pending_approval, queued)
    with day/week/month database breakdown and per-platform breakdown.
    """
    plat_filter = (platform or "").strip().lower()
    if plat_filter not in ("facebook", "instagram", "youtube"):
        plat_filter = ""

    period_key = (period or "day").strip().lower()
    if period_key == "week":
        period_expr = "strftime('%Y-W%W', created_at)"
    elif period_key == "month":
        period_expr = "strftime('%Y-%m', created_at)"
    else:
        period_key = "day"
        period_expr = "strftime('%Y-%m-%d', created_at)"

    where_clause = "WHERE LOWER(platform) = ?" if plat_filter else ""
    params: Tuple[Any, ...] = (plat_filter,) if plat_filter else ()

    agg_sql = """
        COUNT(*) AS total_comments,
        SUM(CASE WHEN status = 'replied' AND (reason IS NULL OR reason NOT IN ('manual_inbox_reply', 'approved_manual_reply')) THEN 1 ELSE 0 END) AS auto_replied,
        SUM(CASE WHEN status = 'replied' AND reason IN ('manual_inbox_reply', 'approved_manual_reply') THEN 1 ELSE 0 END) AS manual_replied,
        SUM(CASE WHEN status = 'review_required' THEN 1 ELSE 0 END) AS pending_approval,
        SUM(CASE WHEN status = 'queued' THEN 1 ELSE 0 END) AS queued_replies,
        SUM(CASE WHEN status = 'test_prepared' THEN 1 ELSE 0 END) AS safe_test_replies
    """

    conn = get_connection()
    try:
        summary_row = conn.execute(
            f"SELECT {agg_sql} FROM activities {where_clause}",
            params,
        ).fetchone()
        summary = {
            "total_comments": int((summary_row["total_comments"] if summary_row else 0) or 0),
            "auto_replied": int((summary_row["auto_replied"] if summary_row else 0) or 0),
            "manual_replied": int((summary_row["manual_replied"] if summary_row else 0) or 0),
            "pending_approval": int((summary_row["pending_approval"] if summary_row else 0) or 0),
            "queued_replies": int((summary_row["queued_replies"] if summary_row else 0) or 0),
            "safe_test_replies": int((summary_row["safe_test_replies"] if summary_row else 0) or 0),
        }

        # Live approval_queue pending count (respecting platform filter)
        aq_where = "WHERE status = 'pending'" + (" AND LOWER(platform) = ?" if plat_filter else "")
        aq_row = conn.execute(f"SELECT COUNT(*) AS cnt FROM approval_queue {aq_where}", params).fetchone()
        summary["approval_queue_pending"] = int((aq_row["cnt"] if aq_row else 0) or 0)

        # Period + Platform breakdown (database table view)
        rows = conn.execute(
            f"""
            SELECT
                {period_expr} AS period_label,
                LOWER(platform) AS platform,
                {agg_sql}
            FROM activities
            {where_clause}
            GROUP BY period_label, LOWER(platform)
            ORDER BY period_label DESC, platform ASC
            LIMIT 120
            """,
            params,
        ).fetchall()
        breakdown = [
            {
                "period": r["period_label"] or "Unknown",
                "platform": r["platform"],
                "total_comments": int(r["total_comments"] or 0),
                "auto_replied": int(r["auto_replied"] or 0),
                "manual_replied": int(r["manual_replied"] or 0),
                "pending_approval": int(r["pending_approval"] or 0),
                "queued_replies": int(r["queued_replies"] or 0),
            }
            for r in rows
        ]

        # Per-platform totals (always unfiltered across all 3 platforms for quick comparison)
        plat_rows = conn.execute(
            f"""
            SELECT LOWER(platform) AS platform, {agg_sql}
            FROM activities
            GROUP BY LOWER(platform)
            ORDER BY platform ASC
            """
        ).fetchall()
        by_platform = [
            {
                "platform": r["platform"],
                "total_comments": int(r["total_comments"] or 0),
                "auto_replied": int(r["auto_replied"] or 0),
                "manual_replied": int(r["manual_replied"] or 0),
                "pending_approval": int(r["pending_approval"] or 0),
                "queued_replies": int(r["queued_replies"] or 0),
            }
            for r in plat_rows
        ]

        return {
            "platform": plat_filter or "all",
            "period": period_key,
            "summary": summary,
            "by_platform": by_platform,
            "breakdown": breakdown,
        }
    finally:
        conn.close()
