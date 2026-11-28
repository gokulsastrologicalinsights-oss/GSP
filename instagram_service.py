"""Meta Instagram Graph API integration service for Gokul Social Publisher.
Handles Instagram Professional (Business/Creator) OAuth, comment synchronization,
deterministic replies via nlp_detector, duplicate prevention, and Safe Testing Mode.
"""
import os
import uuid
import logging
import requests
from typing import Dict, Any, List, Optional

import database
import nlp_detector
from facebook_service import FacebookService, GRAPH_API_VERSION, GRAPH_API_BASE
from nlp_detector import analyze_comment_detailed

logger = logging.getLogger(__name__)

DEFAULT_IG_REDIRECT_URI = "http://localhost:8088/api/instagram/callback"
IG_OAUTH_SCOPES = "instagram_basic,instagram_manage_comments,pages_show_list,pages_read_engagement"


class InstagramService:
    @staticmethod
    def get_credentials() -> Dict[str, Optional[str]]:
        """Reuses Meta App ID/Secret from FacebookService with an Instagram-specific redirect URI."""
        fb_creds = FacebookService.get_credentials()
        settings = database.get_settings()
        ig_redirect_uri = (
            os.getenv("META_IG_REDIRECT_URI")
            or settings.get("meta_ig_redirect_uri")
            or DEFAULT_IG_REDIRECT_URI
        )
        return {
            "app_id": fb_creds.get("app_id"),
            "app_secret": fb_creds.get("app_secret"),
            "redirect_uri": ig_redirect_uri,
        }

    @staticmethod
    def get_oauth_dialog_url(redirect_uri: Optional[str] = None, state: Optional[str] = None) -> str:
        """Constructs official Meta OAuth dialog URL with Instagram Professional permissions."""
        creds = InstagramService.get_credentials()
        app_id = creds["app_id"]
        if not app_id:
            raise ValueError("Meta App ID is not configured.")

        r_uri = redirect_uri or creds["redirect_uri"]
        csrf_state = state or str(uuid.uuid4())
        database.set_setting("ig_oauth_csrf_state", csrf_state)

        return (
            f"https://www.facebook.com/{GRAPH_API_VERSION}/dialog/oauth?"
            f"client_id={app_id}&redirect_uri={r_uri}&state={csrf_state}"
            f"&scope={IG_OAUTH_SCOPES}&response_type=code"
        )

    @staticmethod
    def exchange_code_for_token(code: str, redirect_uri: Optional[str] = None) -> Dict[str, Any]:
        """Exchanges OAuth authorization code for a User Access Token."""
        creds = InstagramService.get_credentials()
        r_uri = redirect_uri or creds["redirect_uri"]
        return FacebookService.exchange_code_for_token(code, redirect_uri=r_uri)

    @staticmethod
    def _format_api_error(error_obj: Dict[str, Any]) -> str:
        """Formats Meta Graph API errors clearly, highlighting expired tokens and permission errors."""
        code = error_obj.get("code")
        subcode = error_obj.get("error_subcode")
        msg = error_obj.get("message", "Unknown Meta API error.")
        if code == 190:
            return f"Access token expired or invalid (code 190{f', subcode {subcode}' if subcode else ''}). Please reconnect Instagram."
        if code in (10, 200, 299):
            return f"Missing Instagram permission (code {code}): {msg}"
        return f"Meta API error{f' (code {code})' if code else ''}: {msg}"

    @staticmethod
    def get_instagram_accounts(user_access_token: str) -> Dict[str, Any]:
        """Retrieves Instagram Professional accounts linked to the user's Facebook Pages."""
        url = f"{GRAPH_API_BASE}/me/accounts"
        params = {
            "access_token": user_access_token,
            "fields": "id,name,access_token,instagram_business_account{id,username,name}",
        }
        try:
            res = requests.get(url, params=params, timeout=10)
            data = res.json()
        except Exception as e:
            logger.error(f"Failed to fetch Instagram accounts: {e}")
            return {"accounts": [], "error": f"Network error fetching Instagram accounts: {str(e)}"}

        if "error" in data:
            return {"accounts": [], "error": InstagramService._format_api_error(data["error"])}

        ig_accounts: List[Dict[str, Any]] = []
        for page in data.get("data", []):
            ig = page.get("instagram_business_account")
            if ig and ig.get("id"):
                username = ig.get("username", "")
                display_name = ig.get("name") or (f"@{username}" if username else f"IG {ig['id']}")
                if username and ig.get("name"):
                    display_name = f"{ig['name']} (@{username})"
                ig_accounts.append({
                    "id": ig["id"],
                    "username": username,
                    "name": display_name,
                    "page_id": page.get("id"),
                    "page_name": page.get("name", ""),
                    "access_token": page.get("access_token") or user_access_token,
                })

        return {"accounts": ig_accounts, "error": None}

    @staticmethod
    def connect_account(account_id: str, account_name: str, access_token: str) -> Dict[str, Any]:
        """Saves or updates an Instagram Professional account securely in SQLite."""
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("""
            INSERT INTO accounts (platform, account_id, account_name, access_token, is_active)
            VALUES ('instagram', ?, ?, ?, 1)
            ON CONFLICT(account_id) DO UPDATE SET
                account_name = excluded.account_name,
                access_token = excluded.access_token,
                is_active = 1
        """, (account_id, account_name, access_token))
        conn.commit()
        conn.close()
        return {"success": True, "account_id": account_id, "account_name": account_name}

    @staticmethod
    def disconnect_account(account_id: str) -> Dict[str, Any]:
        """Disconnects an Instagram Professional account."""
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("UPDATE accounts SET is_active = 0 WHERE platform = 'instagram' AND account_id = ?", (account_id,))
        conn.commit()
        conn.close()
        return {"success": True}

    @staticmethod
    def get_connected_account() -> Optional[Dict[str, Any]]:
        """Returns the active Instagram account details (excluding access_token)."""
        conn = database.get_connection()
        c = conn.cursor()
        c.execute(
            "SELECT id, platform, account_id, account_name, is_active, connected_at "
            "FROM accounts WHERE platform = 'instagram' AND is_active = 1 LIMIT 1"
        )
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get_account_token(account_id: str) -> Optional[str]:
        """Retrieves stored access token for internal API calls only."""
        conn = database.get_connection()
        c = conn.cursor()
        c.execute(
            "SELECT access_token FROM accounts WHERE platform = 'instagram' AND account_id = ? AND is_active = 1",
            (account_id,),
        )
        row = c.fetchone()
        conn.close()
        return row["access_token"] if row else None

    @staticmethod
    def _extract_username(account_name: str) -> Optional[str]:
        """Extracts @username from stored account_name if formatted as 'Name (@username)' or '@username'."""
        if not account_name:
            return None
        if "@" in account_name:
            part = account_name.split("@")[-1].rstrip(") ").strip()
            return part or None
        return None

    @staticmethod
    def fetch_recent_comments(ig_user_id: str, access_token: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetches comments from recent eligible Instagram media (posts and Reels)."""
        media_url = f"{GRAPH_API_BASE}/{ig_user_id}/media"
        params = {
            "access_token": access_token,
            "limit": 20,
            "fields": "id,caption,media_type,timestamp",
        }
        media_res = requests.get(media_url, params=params, timeout=10)
        media_data = media_res.json()
        if "error" in media_data:
            raise RuntimeError(InstagramService._format_api_error(media_data["error"]))

        media_items = media_data.get("data", [])
        all_comments: List[Dict[str, Any]] = []

        for media in media_items:
            media_id = media.get("id")
            if not media_id:
                continue
            try:
                database.upsert_social_post(
                    platform="instagram",
                    account_id=ig_user_id,
                    post_id=media_id,
                    caption=media.get("caption") or "",
                    thumbnail_url=media.get("thumbnail_url") or media.get("media_url") or "",
                    permalink=media.get("permalink") or "",
                    media_type=media.get("media_type") or "",
                    post_date=media.get("timestamp") or "",
                )
            except Exception:
                pass
            comments_url = f"{GRAPH_API_BASE}/{media_id}/comments"
            c_params = {
                "access_token": access_token,
                "fields": "id,text,username,timestamp,from",
                "limit": limit,
            }
            c_res = requests.get(comments_url, params=c_params, timeout=10)
            c_data = c_res.json()
            if "error" in c_data:
                raise RuntimeError(InstagramService._format_api_error(c_data["error"]))

            for c in c_data.get("data", []):
                c["post_id"] = media_id
                c["media_type"] = media.get("media_type", "")
                all_comments.append(c)

        return all_comments

    @staticmethod
    def send_reply(comment_id: str, reply_text: str, access_token: str) -> Dict[str, Any]:
        """Publishes a reply to an Instagram comment via official POST /{ig_comment_id}/replies."""
        url = f"{GRAPH_API_BASE}/{comment_id}/replies"
        payload = {
            "message": reply_text,
            "access_token": access_token,
        }
        res = requests.post(url, data=payload, timeout=10)
        return res.json()

    @staticmethod
    def process_and_reply_comment(
        comment_data: Dict[str, Any],
        ig_user_id: str,
        ig_username: Optional[str] = None,
        access_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Processes an Instagram comment through deterministic NLP, safety checks, and reply execution."""
        comment_id = comment_data.get("id")
        post_id = comment_data.get("post_id", "")
        message = comment_data.get("text") if comment_data.get("text") is not None else comment_data.get("message", "")
        from_user = comment_data.get("from") or {}
        author_id = from_user.get("id", "")
        author_name = (
            comment_data.get("username")
            or from_user.get("username")
            or from_user.get("name")
            or "Instagram User"
        )

        # Self-comment exclusion (by IG user ID or username)
        if author_id and author_id == ig_user_id:
            return {"status": "skipped", "reason": "self_comment", "comment_id": comment_id}
        if ig_username and author_name and author_name.lower() == ig_username.lower():
            return {"status": "skipped", "reason": "self_comment", "comment_id": comment_id}

        # Duplicate prevention
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT id FROM activities WHERE comment_id = ? AND status != 'skipped_rate_limit'", (comment_id,))
        if c.fetchone():
            conn.close()
            return {"status": "skipped", "reason": "already_processed", "comment_id": comment_id}

        settings = database.get_settings()
        is_auto_reply_enabled = settings.get("ig_auto_reply_enabled", "false") == "true"
        is_safe_test_mode = settings.get("safe_test_mode", "true") == "true"
        is_kill_switch = settings.get("global_kill_switch", "false") == "true"

        # Deterministic language & intent analysis (reusing nlp_detector.py)
        last_tpl = database.get_last_template_for_commenter(author_name)
        lang, intent, reply_text, action_status, template_id, reason = nlp_detector.classify_for_auto_reply(
            message, author_name=author_name, last_template_id=last_tpl
        )
        platform_cfg = database.get_platform_hybrid_settings("instagram")

        final_status = "skipped"
        api_error = None
        if action_status == "review_required":
            final_status = "review_required"
        elif action_status == "reply_ready":
            if is_kill_switch:
                final_status = "review_required"
                reason = "global_kill_switch"
            elif not is_auto_reply_enabled:
                final_status = "review_required"
                reason = "platform_auto_reply_off"
            elif (acct_mode := database.get_account_reply_mode("instagram", ig_user_id)) == "DISABLED":
                final_status = "skipped"
                reason = "account_reply_disabled"
            elif acct_mode == "MANUAL_APPROVAL":
                final_status = "review_required"
                reason = "account_manual_approval"
            elif intent in ("positive_praise", "praise") and not platform_cfg["praise_enabled"]:
                final_status = "review_required"
                reason = "platform_praise_disabled"
            elif intent == "emoji_appreciation" and not platform_cfg["emoji_enabled"]:
                final_status = "review_required"
                reason = "platform_emoji_disabled"
            else:
                if template_id and template_id not in platform_cfg["enabled_templates"]:
                    reply_text = database.pick_approved_template_for_platform("instagram", lang, comment_id)
                if not reply_text:
                    final_status = "review_required"
                    reason = "no_enabled_template_for_language"
                elif is_safe_test_mode:
                    final_status = "test_prepared"
                else:
                    allowed, rl_reason = database.check_and_reserve_rate_limit(
                        "instagram", ig_user_id, comment_id, author_name, template_id
                    )
                    if not allowed:
                        final_status = "skipped_rate_limit"
                        reason = rl_reason
                    elif access_token:
                        try:
                            api_res = InstagramService.send_reply(comment_id, reply_text, access_token)
                            if "id" in api_res:
                                final_status = "replied"
                            else:
                                database.release_rate_limit_reservation(comment_id)
                                err_obj = api_res.get("error")
                                api_error = InstagramService._format_api_error(err_obj) if isinstance(err_obj, dict) else "Reply rejected by Instagram API."
                                logger.error(f"Instagram reply failed for {comment_id}: {api_error}")
                                final_status = "failed"
                        except Exception as e:
                            database.release_rate_limit_reservation(comment_id)
                            api_error = str(e)
                            logger.error(f"Error publishing reply to Instagram: {e}")
                            final_status = "failed"
                    else:
                        database.release_rate_limit_reservation(comment_id)
                        final_status = "review_required"
                        reason = "missing_access_token"

        c.execute("""
            INSERT OR REPLACE INTO activities (
                platform, account_id, post_id, comment_id, author_name, comment_text,
                detected_language, detected_intent, template_id, reply_text, status, reason, api_error
            ) VALUES ('instagram', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ig_user_id, post_id, comment_id, author_name, message,
            lang, intent, template_id, reply_text, final_status, reason, api_error,
        ))
        conn.commit()
        conn.close()

        if final_status == "review_required" and platform_cfg["manual_queue_enabled"]:
            database.enqueue_approval_item(
                platform="instagram",
                account_id=ig_user_id,
                comment_id=comment_id,
                commenter_name=author_name,
                comment_text=message,
                detected_language=lang,
                detected_intent=intent,
                suggested_reply=reply_text,
                review_reason=reason,
            )

        result = {
            "comment_id": comment_id,
            "language": lang,
            "intent": intent,
            "reply_text": reply_text,
            "status": final_status,
        }
        if final_status == "review_required" and not platform_cfg["manual_queue_enabled"]:
            result["manual_queue_disabled"] = True
        if api_error:
            result["error"] = api_error
        return result

    @classmethod
    def sync_instagram_comments(cls) -> Dict[str, Any]:
        """Runs synchronization for connected Instagram Professional account comments."""
        account = cls.get_connected_account()
        if not account:
            return {"success": False, "error": "No active Instagram Professional account connected"}

        ig_user_id = account["account_id"]
        ig_username = cls._extract_username(account.get("account_name", ""))
        token = cls.get_account_token(ig_user_id)
        if not token:
            return {"success": False, "error": "Missing access token for connected Instagram account"}

        try:
            comments = cls.fetch_recent_comments(ig_user_id, token)
        except Exception as e:
            logger.error(f"Instagram comment sync failed: {e}")
            return {"success": False, "error": str(e)}

        results = []
        for comment in comments:
            res = cls.process_and_reply_comment(
                comment,
                ig_user_id=ig_user_id,
                ig_username=ig_username,
                access_token=token,
            )
            results.append(res)

        return {"success": True, "processed_count": len(results), "details": results}
