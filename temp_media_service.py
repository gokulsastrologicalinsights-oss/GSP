"""Secure temporary media token management for Instagram Reels delivery."""
import hashlib
import hmac
import os
import secrets
import threading
import time
from typing import Any, Dict, Optional

import database

DEFAULT_TTL_SECONDS = 15 * 60  # 15 minutes
MEDIA_STORAGE_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "media_storage"))

_lock = threading.Lock()


def _ensure_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS temp_media_tokens (
            token_hash TEXT PRIMARY KEY,
            job_id INTEGER NOT NULL,
            media_path TEXT NOT NULL,
            allowed_root TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0
        )
        """
    )


def _get_hmac_secret() -> bytes:
    env_secret = os.environ.get("GSP_TEMP_MEDIA_SECRET", "").strip()
    if env_secret:
        return env_secret.encode("utf-8")
    settings = database.get_settings()
    stored = (settings.get("temp_media_hmac_secret") or "").strip()
    if not stored:
        stored = secrets.token_hex(32)
        database.set_setting("temp_media_hmac_secret", stored)
    return stored.encode("utf-8")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _sign_payload(raw_id: str, job_id: int, expires_at: int) -> str:
    msg = f"{raw_id}:{job_id}:{expires_at}".encode("utf-8")
    return hmac.new(_get_hmac_secret(), msg, hashlib.sha256).hexdigest()


def _is_safe_media_path(media_path: str, allowed_root: Optional[str] = None) -> Optional[str]:
    if not media_path:
        return None
    root = os.path.realpath(allowed_root or MEDIA_STORAGE_ROOT)
    real_path = os.path.realpath(media_path)
    try:
        if os.path.commonpath([root, real_path]) != root:
            return None
    except ValueError:
        return None
    if not os.path.isfile(real_path) or not os.access(real_path, os.R_OK):
        return None
    return real_path


def create_temp_media_token(
    job_id: int,
    media_path: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    allowed_root: Optional[str] = None,
) -> str:
    """Create a job-scoped, HMAC-signed temporary media token."""
    real_path = _is_safe_media_path(media_path, allowed_root=allowed_root)
    if not real_path:
        raise ValueError("Invalid or unauthorized media path")

    raw_id = secrets.token_urlsafe(24)
    expires_at = int(time.time()) + max(1, int(ttl_seconds))
    sig = _sign_payload(raw_id, int(job_id), expires_at)
    token = f"{raw_id}.{int(job_id)}.{expires_at}.{sig}"
    t_hash = _token_hash(token)

    with _lock:
        conn = database.get_connection()
        try:
            _ensure_table(conn)
            conn.execute(
                """
                INSERT OR REPLACE INTO temp_media_tokens
                    (token_hash, job_id, media_path, allowed_root, expires_at, revoked)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (t_hash, int(job_id), real_path, os.path.realpath(allowed_root or MEDIA_STORAGE_ROOT), expires_at),
            )
            conn.commit()
        finally:
            conn.close()
    return token


def validate_temp_media_token(token: str, expected_job_id: Optional[int] = None) -> Optional[str]:
    """Validate token signature, expiry, revocation, job binding, and file path. Returns real_path or None."""
    if not token or token.count(".") != 3:
        return None
    raw_id, job_str, exp_str, sig = token.split(".", 3)
    try:
        job_id = int(job_str)
        expires_at = int(exp_str)
    except ValueError:
        return None

    if expected_job_id is not None and job_id != int(expected_job_id):
        return None

    expected_sig = _sign_payload(raw_id, job_id, expires_at)
    if not hmac.compare_digest(sig, expected_sig):
        return None

    if int(time.time()) > expires_at:
        return None

    t_hash = _token_hash(token)
    with _lock:
        conn = database.get_connection()
        try:
            _ensure_table(conn)
            row = conn.execute(
                "SELECT job_id, media_path, allowed_root, expires_at, revoked FROM temp_media_tokens WHERE token_hash = ?",
                (t_hash,),
            ).fetchone()
        finally:
            conn.close()
        if not row or row["revoked"]:
            return None
        if row["job_id"] != job_id or int(time.time()) > row["expires_at"]:
            return None
        return _is_safe_media_path(row["media_path"], allowed_root=row["allowed_root"])


def revoke_temp_media_token(token: Optional[str]) -> bool:
    """Idempotently revoke a temporary media token."""
    if not token:
        return False
    t_hash = _token_hash(token)
    with _lock:
        conn = database.get_connection()
        try:
            _ensure_table(conn)
            cur = conn.execute("UPDATE temp_media_tokens SET revoked = 1 WHERE token_hash = ?", (t_hash,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def cleanup_expired_tokens(now_ts: Optional[int] = None) -> int:
    """Remove expired or revoked tokens from SQLite."""
    now_val = int(now_ts if now_ts is not None else time.time())
    with _lock:
        conn = database.get_connection()
        try:
            _ensure_table(conn)
            cur = conn.execute("DELETE FROM temp_media_tokens WHERE revoked = 1 OR expires_at < ?", (now_val,))
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()
