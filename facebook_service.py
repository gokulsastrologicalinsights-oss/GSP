"""Meta Facebook Graph API integration service for Gokul Social Publisher.
Handles Page OAuth, comment synchronization, deterministic replies, duplicate prevention, and Safe Testing Mode.
"""
import os
import json
import uuid
import requests
import logging
from typing import Dict, Any, List, Optional
import database
from nlp_detector import analyze_comment_detailed

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v19.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
DEFAULT_REDIRECT_URI = "http://localhost:8088/api/facebook/callback"

class FacebookService:
    @staticmethod
    def get_credentials() -> Dict[str, Optional[str]]:
        """Retrieves Meta App ID and Secret from env vars or database settings."""
        settings = database.get_settings()
        app_id = os.getenv("META_APP_ID") or settings.get("meta_app_id")
        app_secret = os.getenv("META_APP_SECRET") or settings.get("meta_app_secret")
        redirect_uri = os.getenv("META_REDIRECT_URI") or settings.get("meta_redirect_uri") or DEFAULT_REDIRECT_URI
        return {
            "app_id": app_id,
            "app_secret": app_secret,
            "redirect_uri": redirect_uri
        }

    @staticmethod
    def save_credentials(app_id: str, app_secret: str, redirect_uri: Optional[str] = None):
        """Saves Meta App credentials securely in settings."""
        if app_id:
            database.set_setting("meta_app_id", app_id.strip())
        if app_secret:
            database.set_setting("meta_app_secret", app_secret.strip())
        if redirect_uri:
            database.set_setting("meta_redirect_uri", redirect_uri.strip())

    @staticmethod
    def get_oauth_dialog_url(redirect_uri: Optional[str] = None, state: Optional[str] = None) -> str:
        """Constructs official Meta OAuth dialog URL for Facebook Login with required permissions."""
        creds = FacebookService.get_credentials()
        app_id = creds["app_id"]
        if not app_id:
            raise ValueError("Meta App ID is not configured.")
            
        r_uri = redirect_uri or creds["redirect_uri"]
        csrf_state = state or str(uuid.uuid4())
        # Store state for CSRF validation
        database.set_setting("oauth_csrf_state", csrf_state)
        
        # Necessary permissions only: pages_show_list, pages_read_engagement, pages_manage_posts
        scopes = "pages_show_list,pages_read_engagement,pages_manage_posts"
        return (
            f"https://www.facebook.com/{GRAPH_API_VERSION}/dialog/oauth?"
            f"client_id={app_id}&redirect_uri={r_uri}&state={csrf_state}&scope={scopes}&response_type=code"
        )

    @staticmethod
    def exchange_code_for_token(code: str, redirect_uri: Optional[str] = None) -> Dict[str, Any]:
        """Exchanges authorization code for a User Access Token."""
        creds = FacebookService.get_credentials()
        app_id = creds["app_id"]
        app_secret = creds["app_secret"]
        r_uri = redirect_uri or creds["redirect_uri"]

        if not app_id or not app_secret:
            return {"error": {"message": "Meta App ID and Secret must be configured."}}

        url = f"{GRAPH_API_BASE}/oauth/access_token"
        params = {
            "client_id": app_id,
            "client_secret": app_secret,
            "redirect_uri": r_uri,
            "code": code
        }
        try:
            res = requests.get(url, params=params, timeout=10)
            return res.json()
        except Exception as e:
            logger.error(f"Failed to exchange OAuth code: {e}")
            return {"error": {"message": f"Network error during token exchange: {str(e)}"}}

    @staticmethod
    def get_user_pages(user_access_token: str) -> List[Dict[str, Any]]:
        """Retrieves user's Facebook Pages with Page Access Tokens."""
        url = f"{GRAPH_API_BASE}/me/accounts"
        params = {
            "access_token": user_access_token,
            "fields": "id,name,access_token,category"
        }
        try:
            res = requests.get(url, params=params, timeout=10)
            data = res.json()
            return data.get("data", [])
        except Exception as e:
            logger.error(f"Failed to fetch user pages: {e}")
            return []

    @staticmethod
    def connect_page(page_id: str, page_name: str, access_token: str) -> Dict[str, Any]:
        """Saves or updates Facebook Page account securely in the SQLite database."""
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("""
            INSERT INTO accounts (platform, account_id, account_name, access_token, is_active)
            VALUES ('facebook', ?, ?, ?, 1)
            ON CONFLICT(account_id) DO UPDATE SET
                account_name = excluded.account_name,
                access_token = excluded.access_token,
                is_active = 1
        """, (page_id, page_name, access_token))
        conn.commit()
        conn.close()
        return {"success": True, "page_id": page_id, "page_name": page_name}

    @staticmethod
    def disconnect_page(page_id: str) -> Dict[str, Any]:
        """Disconnects Facebook Page."""
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("UPDATE accounts SET is_active = 0 WHERE platform = 'facebook' AND account_id = ?", (page_id,))
        conn.commit()
        conn.close()
        return {"success": True}

    @staticmethod
    def get_connected_page() -> Optional[Dict[str, Any]]:
        """Returns the active Facebook Page details (excluding token from public disclosure)."""
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT id, platform, account_id, account_name, is_active, connected_at FROM accounts WHERE platform = 'facebook' AND is_active = 1 LIMIT 1")
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get_page_token(page_id: str) -> Optional[str]:
        """Retrieves stored access token for the given page ID (internal use only)."""
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT access_token FROM accounts WHERE platform = 'facebook' AND account_id = ? AND is_active = 1", (page_id,))
        row = c.fetchone()
        conn.close()
        return row["access_token"] if row else None

    @staticmethod
    def fetch_recent_comments(page_id: str, access_token: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetches comments from published posts on the Facebook Page via Meta Graph API."""
        # 1. Get recent posts on page
        posts_url = f"{GRAPH_API_BASE}/{page_id}/posts"
        params = {
            "access_token": access_token,
            "limit": 5,
            "fields": "id,message,created_time"
        }
        posts_res = requests.get(posts_url, params=params, timeout=10)
        posts_data = posts_res.json()
        posts = posts_data.get("data", [])

        all_comments = []
        for post in posts:
            post_id = post["id"]
            try:
                database.upsert_social_post(
                    platform="facebook",
                    account_id=page_id,
                    post_id=post_id,
                    caption=post.get("message") or "",
                    thumbnail_url=post.get("full_picture") or "",
                    permalink=post.get("permalink_url") or "",
                    post_date=post.get("created_time") or "",
                )
            except Exception:
                pass
            comments_url = f"{GRAPH_API_BASE}/{post_id}/comments"
            c_params = {
                "access_token": access_token,
                "fields": "id,from,message,created_time,parent",
                "limit": limit
            }
            c_res = requests.get(comments_url, params=c_params, timeout=10)
            c_data = c_res.json()
            comments = c_data.get("data", [])
            for c in comments:
                c["post_id"] = post_id
                all_comments.append(c)

        return all_comments

    @staticmethod
    def send_reply(comment_id: str, reply_text: str, access_token: str) -> Dict[str, Any]:
        """Publishes a reply comment using Meta Graph API."""
        url = f"{GRAPH_API_BASE}/{comment_id}/comments"
        payload = {
            "message": reply_text,
            "access_token": access_token
        }
        res = requests.post(url, data=payload, timeout=10)
        return res.json()

    @staticmethod
    def process_and_reply_comment(comment_data: Dict[str, Any], page_id: str, access_token: Optional[str] = None) -> Dict[str, Any]:
        """Core comment handler.
        1. Excludes self-comments (posted by the page itself).
        2. Prevents duplicate replies (checks activity log).
        3. Deterministically detects language and intent.
        4. In Safe Testing Mode: logs prepared reply without calling Meta API.
        5. In Live Mode: sends reply via Meta API if action is reply_ready.
        6. Logs result in SQLite.
        """
        comment_id = comment_data.get("id")
        post_id = comment_data.get("post_id", "")
        message = comment_data.get("message", "")
        from_user = comment_data.get("from", {})
        author_id = from_user.get("id", "")
        author_name = from_user.get("name", "Facebook User")

        settings = database.get_settings()
        is_auto_reply_enabled = settings.get("auto_reply_enabled") == "true"
        is_safe_test_mode = settings.get("safe_test_mode") == "true"
        is_kill_switch = settings.get("global_kill_switch", "false") == "true"

        # Check for self-comment
        if author_id and author_id == page_id:
            return {"status": "skipped", "reason": "self_comment", "comment_id": comment_id}

        # Check duplicate reply prevention
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT id, status, reply_text FROM activities WHERE comment_id = ?", (comment_id,))
        existing = c.fetchone()
        if existing:
            conn.close()
            return {"status": "skipped", "reason": "already_processed", "comment_id": comment_id}

        # Language and Intent Analysis
        last_tpl = database.get_last_template_for_commenter(author_name)
        lang, intent, reply_text, action_status, template_id, reason = analyze_comment_detailed(message, last_tpl)
        platform_cfg = database.get_platform_hybrid_settings("facebook")

        final_status = "skipped"
        api_error = None
        if action_status == "review_required":
            final_status = "review_required"
        elif action_status == "reply_ready":
            if is_kill_switch:
                final_status = "review_required"
                reason = "global_kill_switch"
            elif not is_auto_reply_enabled:
                final_status = "review_required"  # Held for review when master switch is off
                reason = "platform_auto_reply_off"
            elif intent in ("positive_praise", "praise") and not platform_cfg["praise_enabled"]:
                final_status = "review_required"
                reason = "platform_praise_disabled"
            elif intent == "emoji_appreciation" and not platform_cfg["emoji_enabled"]:
                final_status = "review_required"
                reason = "platform_emoji_disabled"
            else:
                if template_id and template_id not in platform_cfg["enabled_templates"]:
                    reply_text = database.pick_approved_template_for_platform("facebook", lang, comment_id)
                if not reply_text:
                    final_status = "review_required"
                    reason = "no_enabled_template_for_language"
                elif is_safe_test_mode:
                    final_status = "test_prepared"  # Safe testing mode
                else:
                    # Live mode: enforce backend rate limits
                    allowed, rl_reason = database.check_and_reserve_rate_limit(
                        "facebook", page_id, comment_id, author_name, template_id
                    )
                    if not allowed:
                        final_status = "skipped_rate_limit"
                        reason = rl_reason
                    elif access_token:
                        try:
                            api_res = FacebookService.send_reply(comment_id, reply_text, access_token)
                            if "id" in api_res:
                                final_status = "replied"
                            else:
                                database.release_rate_limit_reservation(comment_id)
                                api_error = str(api_res.get("error", "Reply rejected by Facebook API"))
                                final_status = "failed"
                        except Exception as e:
                            database.release_rate_limit_reservation(comment_id)
                            api_error = str(e)
                            logger.error(f"Error publishing reply to Facebook: {e}")
                            final_status = "failed"
                    else:
                        database.release_rate_limit_reservation(comment_id)
                        final_status = "review_required"
                        reason = "missing_access_token"

        # Save activity to SQLite
        c.execute("""
            INSERT OR REPLACE INTO activities (
                platform, account_id, post_id, comment_id, author_name, comment_text,
                detected_language, detected_intent, template_id, reply_text, status, reason, api_error
            ) VALUES ('facebook', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            page_id, post_id, comment_id, author_name, message,
            lang, intent, template_id, reply_text, final_status, reason, api_error
        ))
        conn.commit()
        conn.close()

        if final_status == "review_required" and platform_cfg["manual_queue_enabled"]:
            database.enqueue_approval_item(
                platform="facebook",
                account_id=page_id,
                comment_id=comment_id,
                commenter_name=author_name,
                comment_text=message,
                detected_language=lang,
                detected_intent=intent,
                suggested_reply=reply_text,
                review_reason=reason,
            )

        res_dict = {
            "comment_id": comment_id,
            "language": lang,
            "intent": intent,
            "reply_text": reply_text,
            "status": final_status
        }
        if final_status == "review_required" and not platform_cfg["manual_queue_enabled"]:
            res_dict["manual_queue_disabled"] = True
        return res_dict

    @classmethod
    def sync_facebook_comments(cls) -> Dict[str, Any]:
        """Runs background sync for connected Facebook Page comments."""
        page = cls.get_connected_page()
        if not page:
            return {"success": False, "error": "No active Facebook page connected"}

        page_id = page["account_id"]
        token = cls.get_page_token(page_id)
        if not token:
            return {"success": False, "error": "Missing access token for connected page"}

        try:
            comments = cls.fetch_recent_comments(page_id, token)
        except Exception as e:
            return {"success": False, "error": str(e)}

        results = []
        for c in comments:
            res = cls.process_and_reply_comment(c, page_id, token)
            results.append(res)

        return {"success": True, "processed_count": len(results), "details": results}
