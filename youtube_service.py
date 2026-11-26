"""Official Google YouTube Data API v3 integration service for Gokul Social Publisher.
Handles YouTube OAuth 2.0 authentication, channel detection, comment synchronization,
deterministic replies via nlp_detector, duplicate prevention, and Safe Testing Mode.
"""
import os
import json
import uuid
import logging
from typing import Dict, Any, List, Optional
import requests

import database
from nlp_detector import analyze_comment_detailed

logger = logging.getLogger(__name__)

DEFAULT_YT_REDIRECT_URI = "http://localhost:8088/api/youtube/callback"
YOUTUBE_OAUTH_SCOPES = "https://www.googleapis.com/auth/youtube.force-ssl"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


class YouTubeService:
    @staticmethod
    def get_credentials() -> Dict[str, Optional[str]]:
        """Retrieves Google OAuth Client ID, Secret, and Redirect URI."""
        settings = database.get_settings()
        client_id = os.getenv("GOOGLE_CLIENT_ID") or settings.get("google_client_id")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET") or settings.get("google_client_secret")
        redirect_uri = (
            os.getenv("YOUTUBE_REDIRECT_URI")
            or settings.get("youtube_redirect_uri")
            or DEFAULT_YT_REDIRECT_URI
        )
        return {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        }

    @staticmethod
    def save_credentials(client_id: str, client_secret: str, redirect_uri: Optional[str] = None):
        """Saves Google OAuth Client ID, Secret, and Redirect URI securely in settings."""
        database.set_setting("google_client_id", client_id.strip())
        database.set_setting("google_client_secret", client_secret.strip())
        if redirect_uri:
            database.set_setting("youtube_redirect_uri", redirect_uri.strip())

    @staticmethod
    def get_oauth_dialog_url(redirect_uri: Optional[str] = None, state: Optional[str] = None) -> str:
        """Constructs official Google OAuth 2.0 authorization URL with youtube.force-ssl scope."""
        creds = YouTubeService.get_credentials()
        client_id = creds["client_id"]
        if not client_id:
            raise ValueError("Google Client ID is not configured.")

        r_uri = redirect_uri or creds["redirect_uri"]
        csrf_state = state or str(uuid.uuid4())
        database.set_setting("yt_oauth_csrf_state", csrf_state)

        params = {
            "client_id": client_id,
            "redirect_uri": r_uri,
            "response_type": "code",
            "scope": YOUTUBE_OAUTH_SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": csrf_state,
        }
        query_string = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
        return f"{GOOGLE_AUTH_URL}?{query_string}"

    @staticmethod
    def exchange_code_for_token(code: str, redirect_uri: Optional[str] = None) -> Dict[str, Any]:
        """Exchanges Google authorization code for access and refresh tokens."""
        creds = YouTubeService.get_credentials()
        client_id = creds["client_id"]
        client_secret = creds["client_secret"]
        if not client_id or not client_secret:
            return {"error": {"message": "Google Client ID or Secret is not configured."}}

        r_uri = redirect_uri or creds["redirect_uri"]
        payload = {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": r_uri,
            "grant_type": "authorization_code",
        }
        try:
            res = requests.post(GOOGLE_TOKEN_URL, data=payload, timeout=10)
            data = res.json()
        except Exception as e:
            logger.error(f"Failed to exchange Google OAuth code: {e}")
            return {"error": {"message": f"Network error during token exchange: {str(e)}"}}

        if "error" in data:
            err_desc = data.get("error_description") or data.get("error")
            return {"error": {"message": f"Google token exchange failed: {err_desc}"}}

        return data

    @staticmethod
    def refresh_access_token(refresh_token: str) -> Dict[str, Any]:
        """Refreshes an expired Google access token using the stored refresh token."""
        creds = YouTubeService.get_credentials()
        client_id = creds["client_id"]
        client_secret = creds["client_secret"]
        if not client_id or not client_secret:
            return {"error": {"message": "Google Client ID or Secret is not configured."}}

        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        try:
            res = requests.post(GOOGLE_TOKEN_URL, data=payload, timeout=10)
            data = res.json()
        except Exception as e:
            logger.error(f"Failed to refresh Google access token: {e}")
            return {"error": {"message": f"Network error during token refresh: {str(e)}"}}

        if "error" in data:
            err_desc = data.get("error_description") or data.get("error")
            return {"error": {"message": f"Token refresh failed: {err_desc}"}}

        return data

    @staticmethod
    def _format_api_error(error_obj: Dict[str, Any]) -> str:
        """Formats YouTube Data API v3 errors with specific guidance for quota, auth, and disabled comments."""
        if not isinstance(error_obj, dict):
            return str(error_obj)

        code = error_obj.get("code")
        msg = error_obj.get("message", "Unknown YouTube API error.")
        errors = error_obj.get("errors", [])
        first_reason = errors[0].get("reason", "") if errors and isinstance(errors[0], dict) else ""

        if code == 401 or first_reason in ("authError", "invalidCredentials"):
            return "Google access token expired or invalid. Please reconnect YouTube."
        if code == 403:
            if first_reason in ("quotaExceeded", "dailyLimitExceeded"):
                return "YouTube API quota limit reached. Please check Google Cloud quota limits."
            if first_reason == "commentsDisabled":
                return "Comments are disabled for this video."
            if first_reason in ("forbidden", "accessDenied", "insufficientPermissions"):
                return f"Missing required YouTube permissions: {msg}"
            return f"YouTube permission error (403, reason: {first_reason}): {msg}"
        if code == 404 or first_reason in ("commentNotFound", "videoNotFound"):
            return f"Resource not found on YouTube: {msg}"

        return f"YouTube API error (code {code}{f', {first_reason}' if first_reason else ''}): {msg}"

    @staticmethod
    def get_channel_details(access_token: str) -> Dict[str, Any]:
        """Retrieves authenticated YouTube channel ID, name, and uploads playlist ID."""
        url = f"{YOUTUBE_API_BASE}/channels"
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"part": "snippet,contentDetails", "mine": "true"}

        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            data = res.json()
        except Exception as e:
            logger.error(f"Failed to fetch YouTube channel details: {e}")
            return {"channels": [], "error": f"Network error fetching YouTube channel: {str(e)}"}

        if "error" in data:
            return {"channels": [], "error": YouTubeService._format_api_error(data["error"])}

        channels = []
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            content_details = item.get("contentDetails", {})
            related_playlists = content_details.get("relatedPlaylists", {})
            channels.append({
                "id": item.get("id"),
                "title": snippet.get("title", ""),
                "custom_url": snippet.get("customUrl", ""),
                "uploads_playlist_id": related_playlists.get("uploads", ""),
            })

        return {"channels": channels, "error": None}

    @staticmethod
    def connect_account(
        account_id: str,
        account_name: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        uploads_playlist_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Saves or updates a YouTube channel securely in SQLite accounts table, preserving existing refresh_token."""
        existing = YouTubeService.get_account_token_data(account_id) or {}
        effective_refresh = refresh_token if refresh_token else (existing.get("refresh_token") or "")
        effective_uploads = uploads_playlist_id if uploads_playlist_id else (existing.get("uploads_playlist_id") or "")
        token_payload = {
            "access_token": access_token,
            "refresh_token": effective_refresh,
            "uploads_playlist_id": effective_uploads,
        }
        stored_token = json.dumps(token_payload)

        conn = database.get_connection()
        c = conn.cursor()
        c.execute("""
            INSERT INTO accounts (platform, account_id, account_name, access_token, is_active)
            VALUES ('youtube', ?, ?, ?, 1)
            ON CONFLICT(account_id) DO UPDATE SET
                account_name = excluded.account_name,
                access_token = excluded.access_token,
                is_active = 1
        """, (account_id, account_name, stored_token))
        conn.commit()
        conn.close()
        return {"success": True, "account_id": account_id, "account_name": account_name}

    @staticmethod
    def disconnect_account(account_id: str) -> Dict[str, Any]:
        """Disconnects a YouTube channel."""
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("UPDATE accounts SET is_active = 0 WHERE platform = 'youtube' AND account_id = ?", (account_id,))
        conn.commit()
        conn.close()
        return {"success": True}

    @staticmethod
    def get_connected_account() -> Optional[Dict[str, Any]]:
        """Returns the active YouTube channel details (excluding tokens)."""
        conn = database.get_connection()
        c = conn.cursor()
        c.execute(
            "SELECT id, platform, account_id, account_name, is_active, connected_at "
            "FROM accounts WHERE platform = 'youtube' AND is_active = 1 LIMIT 1"
        )
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    @classmethod
    def get_account_token_data(cls, account_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves raw token payload for internal API calls."""
        conn = database.get_connection()
        c = conn.cursor()
        c.execute(
            "SELECT access_token FROM accounts WHERE platform = 'youtube' AND account_id = ? AND is_active = 1",
            (account_id,),
        )
        row = c.fetchone()
        conn.close()
        if not row or not row["access_token"]:
            return None

        raw = row["access_token"]
        try:
            return json.loads(raw)
        except Exception:
            return {"access_token": raw, "refresh_token": "", "uploads_playlist_id": ""}

    @classmethod
    def get_valid_access_token(cls, account_id: str) -> Optional[str]:
        """Returns a valid access token, automatically refreshing it if needed."""
        token_data = cls.get_account_token_data(account_id)
        if not token_data:
            return None

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        return access_token

    @classmethod
    def update_account_access_token(cls, account_id: str, new_access_token: str):
        """Updates stored access token after a refresh."""
        token_data = cls.get_account_token_data(account_id) or {}
        token_data["access_token"] = new_access_token
        conn = database.get_connection()
        c = conn.cursor()
        c.execute(
            "UPDATE accounts SET access_token = ? WHERE platform = 'youtube' AND account_id = ?",
            (json.dumps(token_data), account_id),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def fetch_recent_videos(
        channel_id: str,
        access_token: str,
        limit: int = 10,
        uploads_playlist_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieves recent videos from the channel via uploads playlist."""
        headers = {"Authorization": f"Bearer {access_token}"}

        # If uploads_playlist_id is not provided, fetch it from channels.list
        playlist_id = uploads_playlist_id
        if not playlist_id:
            ch_url = f"{YOUTUBE_API_BASE}/channels"
            ch_res = requests.get(ch_url, headers=headers, params={"part": "contentDetails", "id": channel_id}, timeout=10)
            ch_data = ch_res.json()
            items = ch_data.get("items", [])
            if items:
                playlist_id = items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")

        if playlist_id:
            pi_url = f"{YOUTUBE_API_BASE}/playlistItems"
            pi_params = {
                "part": "snippet,contentDetails",
                "playlistId": playlist_id,
                "maxResults": limit,
            }
            pi_res = requests.get(pi_url, headers=headers, params=pi_params, timeout=10)
            pi_data = pi_res.json()
            if "error" in pi_data:
                raise RuntimeError(YouTubeService._format_api_error(pi_data["error"]))

            videos = []
            for item in pi_data.get("items", []):
                vid = item.get("contentDetails", {}).get("videoId") or item.get("snippet", {}).get("resourceId", {}).get("videoId")
                if vid:
                    videos.append({
                        "video_id": vid,
                        "title": item.get("snippet", {}).get("title", ""),
                    })
            return videos

        # Fallback to search if uploads playlist could not be determined
        s_url = f"{YOUTUBE_API_BASE}/search"
        s_params = {
            "part": "snippet",
            "channelId": channel_id,
            "type": "video",
            "order": "date",
            "maxResults": limit,
        }
        s_res = requests.get(s_url, headers=headers, params=s_params, timeout=10)
        s_data = s_res.json()
        if "error" in s_data:
            raise RuntimeError(YouTubeService._format_api_error(s_data["error"]))

        videos = []
        for item in s_data.get("items", []):
            vid = item.get("id", {}).get("videoId")
            if vid:
                videos.append({
                    "video_id": vid,
                    "title": item.get("snippet", {}).get("title", ""),
                })
        return videos

    @classmethod
    def fetch_recent_comments(
        cls,
        channel_id: str,
        access_token: str,
        limit: int = 20,
        uploads_playlist_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieves comments from the channel's recent videos using YouTube commentThreads.list."""
        headers = {"Authorization": f"Bearer {access_token}"}
        all_comments: List[Dict[str, Any]] = []

        try:
            videos = cls.fetch_recent_videos(
                channel_id=channel_id,
                access_token=access_token,
                limit=5,
                uploads_playlist_id=uploads_playlist_id,
            )
        except Exception as e:
            logger.warning(f"Could not fetch channel videos, falling back to allThreadsRelatedToChannelId: {e}")
            videos = []

        if videos:
            for video in videos:
                vid = video["video_id"]
                ct_url = f"{YOUTUBE_API_BASE}/commentThreads"
                ct_params = {
                    "part": "snippet",
                    "videoId": vid,
                    "maxResults": limit,
                    "textFormat": "plainText",
                }
                res = requests.get(ct_url, headers=headers, params=ct_params, timeout=10)
                data = res.json()
                if "error" in data:
                    err = data["error"]
                    err_msg = cls._format_api_error(err)
                    # If comments are disabled on a specific video, skip it gracefully
                    if "disabled" in err_msg.lower():
                        logger.info(f"Skipping video {vid}: comments disabled.")
                        continue
                    raise RuntimeError(err_msg)

                for item in data.get("items", []):
                    top = item.get("snippet", {}).get("topLevelComment", {})
                    top_snip = top.get("snippet", {})
                    all_comments.append({
                        "id": top.get("id") or item.get("id"),
                        "comment_id": top.get("id") or item.get("id"),
                        "post_id": vid,
                        "video_id": vid,
                        "author_name": top_snip.get("authorDisplayName", "YouTube User"),
                        "author_channel_id": (top_snip.get("authorChannelId") or {}).get("value", ""),
                        "text": top_snip.get("textOriginal") or top_snip.get("textDisplay", ""),
                        "published_at": top_snip.get("publishedAt", ""),
                    })
        else:
            # Fallback direct channel comment query
            ct_url = f"{YOUTUBE_API_BASE}/commentThreads"
            ct_params = {
                "part": "snippet",
                "allThreadsRelatedToChannelId": channel_id,
                "maxResults": limit,
                "textFormat": "plainText",
            }
            res = requests.get(ct_url, headers=headers, params=ct_params, timeout=10)
            data = res.json()
            if "error" in data:
                raise RuntimeError(cls._format_api_error(data["error"]))

            for item in data.get("items", []):
                top = item.get("snippet", {}).get("topLevelComment", {})
                top_snip = top.get("snippet", {})
                vid = item.get("snippet", {}).get("videoId", "")
                all_comments.append({
                    "id": top.get("id") or item.get("id"),
                    "comment_id": top.get("id") or item.get("id"),
                    "post_id": vid,
                    "video_id": vid,
                    "author_name": top_snip.get("authorDisplayName", "YouTube User"),
                    "author_channel_id": (top_snip.get("authorChannelId") or {}).get("value", ""),
                    "text": top_snip.get("textOriginal") or top_snip.get("textDisplay", ""),
                    "published_at": top_snip.get("publishedAt", ""),
                })

        return all_comments

    @staticmethod
    def send_reply(comment_id: str, reply_text: str, access_token: str) -> Dict[str, Any]:
        """Publishes a reply to an existing comment using official YouTube Data API comments.insert.
        
        Requires:
        snippet.parentId: existing comment ID
        snippet.textOriginal: prepared reply text
        """
        url = f"{YOUTUBE_API_BASE}/comments?part=snippet"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "snippet": {
                "parentId": comment_id,
                "textOriginal": reply_text,
            }
        }
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        return res.json()

    @staticmethod
    def process_and_reply_comment(
        comment_data: Dict[str, Any],
        channel_id: str,
        channel_title: Optional[str] = None,
        access_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Processes a YouTube comment through deterministic NLP, safety checks, and reply execution."""
        comment_id = comment_data.get("comment_id") or comment_data.get("id")
        post_id = comment_data.get("post_id") or comment_data.get("video_id", "")
        message = comment_data.get("text") if comment_data.get("text") is not None else comment_data.get("message", "")
        author_name = comment_data.get("author_name") or comment_data.get("username") or "YouTube User"
        author_channel_id = comment_data.get("author_channel_id", "")

        # 1. Own-comment exclusion (channel's own comments)
        if author_channel_id and author_channel_id == channel_id:
            return {"status": "skipped", "reason": "self_comment", "comment_id": comment_id}
        if channel_title and author_name and author_name.strip().lower() == channel_title.strip().lower():
            return {"status": "skipped", "reason": "self_comment", "comment_id": comment_id}

        # 2. Duplicate prevention
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT id FROM activities WHERE comment_id = ?", (comment_id,))
        if c.fetchone():
            conn.close()
            return {"status": "skipped", "reason": "already_processed", "comment_id": comment_id}

        settings = database.get_settings()
        is_auto_reply_enabled = settings.get("yt_auto_reply_enabled", "false") == "true"
        is_safe_test_mode = settings.get("safe_test_mode", "true") == "true"
        is_kill_switch = settings.get("global_kill_switch", "false") == "true"

        # 3. Deterministic NLP analysis (Tamil, English, Tanglish)
        last_tpl = database.get_last_template_for_commenter(author_name)
        lang, intent, reply_text, action_status, template_id, reason = analyze_comment_detailed(message, last_tpl)
        platform_cfg = database.get_platform_hybrid_settings("youtube")

        final_status = "skipped"
        api_error = None

        # 4. Route complaints, abuse, or uncertain intent to manual review
        if action_status == "review_required":
            final_status = "review_required"
        elif action_status == "reply_ready":
            if is_kill_switch:
                final_status = "review_required"
                reason = "global_kill_switch"
            elif not is_auto_reply_enabled:
                final_status = "review_required"
                reason = "platform_auto_reply_off"
            elif intent in ("positive_praise", "praise") and not platform_cfg["praise_enabled"]:
                final_status = "review_required"
                reason = "platform_praise_disabled"
            elif intent == "emoji_appreciation" and not platform_cfg["emoji_enabled"]:
                final_status = "review_required"
                reason = "platform_emoji_disabled"
            else:
                if template_id and template_id not in platform_cfg["enabled_templates"]:
                    reply_text = database.pick_approved_template_for_platform("youtube", lang, comment_id)
                if not reply_text:
                    final_status = "review_required"
                    reason = "no_enabled_template_for_language"
                elif is_safe_test_mode:
                    # Safe Testing Mode: record test_prepared, do NOT call live reply API
                    final_status = "test_prepared"
                else:
                    allowed, rl_reason = database.check_and_reserve_rate_limit(
                        "youtube", channel_id, comment_id, author_name, template_id
                    )
                    if not allowed:
                        final_status = "skipped_rate_limit"
                        reason = rl_reason
                    elif access_token:
                        try:
                            api_res = YouTubeService.send_reply(comment_id, reply_text, access_token)
                            if "id" in api_res:
                                final_status = "replied"
                            else:
                                database.release_rate_limit_reservation(comment_id)
                                err_obj = api_res.get("error")
                                api_error = YouTubeService._format_api_error(err_obj) if isinstance(err_obj, dict) else "Reply rejected by YouTube API."
                                logger.error(f"YouTube reply failed for {comment_id}: {api_error}")
                                final_status = "failed"
                        except Exception as e:
                            database.release_rate_limit_reservation(comment_id)
                            api_error = str(e)
                            logger.error(f"Error publishing reply to YouTube: {e}")
                            final_status = "failed"
                    else:
                        database.release_rate_limit_reservation(comment_id)
                        final_status = "review_required"
                        reason = "missing_access_token"

        c.execute("""
            INSERT OR REPLACE INTO activities (
                platform, account_id, post_id, comment_id, author_name, comment_text,
                detected_language, detected_intent, template_id, reply_text, status, reason, api_error
            ) VALUES ('youtube', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            channel_id, post_id, comment_id, author_name, message,
            lang, intent, template_id, reply_text, final_status, reason, api_error,
        ))
        conn.commit()
        conn.close()

        if final_status == "review_required" and platform_cfg["manual_queue_enabled"]:
            database.enqueue_approval_item(
                platform="youtube",
                account_id=channel_id,
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
    def sync_youtube_comments(cls) -> Dict[str, Any]:
        """Runs synchronization for connected YouTube channel comments."""
        account = cls.get_connected_account()
        if not account:
            return {"success": False, "error": "No active YouTube channel connected"}

        channel_id = account["account_id"]
        channel_title = account.get("account_name", "")
        token_data = cls.get_account_token_data(channel_id)
        if not token_data or not token_data.get("access_token"):
            return {"success": False, "error": "Missing access token for connected YouTube channel"}

        access_token = token_data["access_token"]
        uploads_playlist_id = token_data.get("uploads_playlist_id")

        try:
            comments = cls.fetch_recent_comments(
                channel_id=channel_id,
                access_token=access_token,
                uploads_playlist_id=uploads_playlist_id,
            )
        except Exception as e:
            err_str = str(e)
            logger.error(f"YouTube comment sync failed: {err_str}")
            # Try token refresh if access token expired
            if "expired" in err_str.lower() and token_data.get("refresh_token"):
                refresh_res = cls.refresh_access_token(token_data["refresh_token"])
                if "access_token" in refresh_res:
                    new_token = refresh_res["access_token"]
                    cls.update_account_access_token(channel_id, new_token)
                    try:
                        comments = cls.fetch_recent_comments(
                            channel_id=channel_id,
                            access_token=new_token,
                            uploads_playlist_id=uploads_playlist_id,
                        )
                        access_token = new_token
                    except Exception as e2:
                        return {"success": False, "error": str(e2)}
                else:
                    return {"success": False, "error": f"Token expired and refresh failed: {refresh_res.get('error', {}).get('message', 'Unknown error')}"}
            else:
                return {"success": False, "error": err_str}

        results = []
        for comment in comments:
            res = cls.process_and_reply_comment(
                comment,
                channel_id=channel_id,
                channel_title=channel_title,
                access_token=access_token,
            )
            results.append(res)

        return {"success": True, "processed_count": len(results), "details": results}
