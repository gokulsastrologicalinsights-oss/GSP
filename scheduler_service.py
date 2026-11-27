import json
import os
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import database

ZODIAC_SIGNS: List[Dict[str, Any]] = [
    {
        "index": 1,
        "tamil": "மேஷம்",
        "english": "Aries",
        "aliases": ["மேஷம்", "mesham", "aries", "mesam"],
    },
    {
        "index": 2,
        "tamil": "ரிஷபம்",
        "english": "Taurus",
        "aliases": ["ரிஷபம்", "rishabam", "taurus", "rishabham", "risabam"],
    },
    {
        "index": 3,
        "tamil": "மிதுனம்",
        "english": "Gemini",
        "aliases": ["மிதுனம்", "mithunam", "gemini", "midhunam"],
    },
    {
        "index": 4,
        "tamil": "கடகம்",
        "english": "Cancer",
        "aliases": ["கடகம்", "kadagam", "cancer", "kadakam"],
    },
    {
        "index": 5,
        "tamil": "சிம்மம்",
        "english": "Leo",
        "aliases": ["சிம்மம்", "simmam", "leo", "simham"],
    },
    {
        "index": 6,
        "tamil": "கன்னி",
        "english": "Virgo",
        "aliases": ["கன்னி", "kanni", "virgo"],
    },
    {
        "index": 7,
        "tamil": "துலாம்",
        "english": "Libra",
        "aliases": ["துலாம்", "thulam", "libra", "tulam"],
    },
    {
        "index": 8,
        "tamil": "விருச்சிகம்",
        "english": "Scorpio",
        "aliases": ["விருச்சிகம்", "viruchigam", "scorpio", "viruchikam", "vrichigam"],
    },
    {
        "index": 9,
        "tamil": "தனுசு",
        "english": "Sagittarius",
        "aliases": ["தனுசு", "dhanusu", "sagittarius", "danusu", "thanusu"],
    },
    {
        "index": 10,
        "tamil": "மகரம்",
        "english": "Capricorn",
        "aliases": ["மகரம்", "magaram", "capricorn", "makaram"],
    },
    {
        "index": 11,
        "tamil": "கும்பம்",
        "english": "Aquarius",
        "aliases": ["கும்பம்", "kumbam", "aquarius", "kumbham"],
    },
    {
        "index": 12,
        "tamil": "மீனம்",
        "english": "Pisces",
        "aliases": ["மீனம்", "meenam", "pisces", "minam"],
    },
]

ZODIAC_BY_INDEX: Dict[int, Dict[str, Any]] = {z["index"]: z for z in ZODIAC_SIGNS}

BATCH_CATEGORIES = [
    "Weekly Rasi Palan",
    "Monthly Rasi Palan",
    "Zodiac Characteristics",
    "General Astrology",
]

PLATFORM_MEDIA_RULES: Dict[str, Dict[str, Any]] = {
    "facebook": {
        "extensions": {".mp4", ".mov", ".avi"},
        "max_bytes": 4 * 1024 * 1024 * 1024,
        "label": "Facebook Page",
    },
    "instagram": {
        "extensions": {".mp4", ".mov"},
        "max_bytes": 1 * 1024 * 1024 * 1024,
        "max_duration_seconds": 90.0,
        "label": "Instagram Professional",
    },
    "youtube": {
        "extensions": {".mp4", ".mov", ".webm", ".avi", ".mkv"},
        "max_bytes": 128 * 1024 * 1024 * 1024,
        "label": "YouTube Channel",
    },
}


class PlatformAdapter:
    """Base publishing adapter for a social platform."""

    platform: str = ""
    label: str = ""

    @staticmethod
    def _parse_json_response(resp) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Safely parse a Graph API response without raising JSONDecodeError on empty/non-JSON bodies."""
        body = (getattr(resp, "text", None) or "").strip()
        if not body:
            return None, f"Empty response body (HTTP {resp.status_code})"
        try:
            data = resp.json()
            if isinstance(data, dict):
                return data, None
            return None, f"Unexpected JSON type {type(data).__name__} (HTTP {resp.status_code})"
        except Exception:
            ctype = (getattr(resp, "headers", None) or {}).get("Content-Type", "unknown")
            return None, f"Non-JSON response (HTTP {resp.status_code}, Content-Type={ctype}, len={len(body)})"

    def publish(self, post: Dict[str, Any], safe_mode: bool = True) -> Dict[str, Any]:
        if safe_mode:
            ext_id = f"safe_{self.platform}_{post['id']}"
            return {
                "success": True,
                "status": "published_safe_mode",
                "external_post_id": ext_id,
                "permalink": f"https://safe-mode.local/{self.platform}/{ext_id}",
                "error": None,
            }
        return {
            "success": False,
            "status": "failed",
            "external_post_id": None,
            "permalink": None,
            "error": "Live publishing requires explicit Phase 3.0B authorization",
        }


class FacebookPageAdapter(PlatformAdapter):
    platform = "facebook"
    label = "Facebook Page"
    GRAPH_VIDEO_BASE = "https://graph-video.facebook.com/v27.0"
    CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB chunks for large-file resumable upload
    LARGE_FILE_THRESHOLD = 25 * 1024 * 1024  # 25 MB threshold to avoid HTTP 413 on multipart uploads

    @staticmethod
    def _parse_json_response(resp) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Safely parse a Graph API response without raising JSONDecodeError on empty/non-JSON bodies."""
        body = (getattr(resp, "text", None) or "").strip()
        if not body:
            return None, f"Empty response body (HTTP {resp.status_code})"
        try:
            data = resp.json()
            if isinstance(data, dict):
                return data, None
            return None, f"Unexpected JSON type {type(data).__name__} (HTTP {resp.status_code})"
        except Exception:
            ctype = (getattr(resp, "headers", None) or {}).get("Content-Type", "unknown")
            return None, f"Non-JSON response (HTTP {resp.status_code}, Content-Type={ctype}, len={len(body)})"

    def publish(self, post: Dict[str, Any], safe_mode: bool = True) -> Dict[str, Any]:
        # Explicit production publishing guard: never make real API calls when Safe Testing Mode is ON
        if safe_mode or database.get_settings().get("safe_test_mode", "true").lower() == "true":
            return super().publish(post, safe_mode=True)

        media_path = post.get("media_path") or ""
        if not media_path or not os.path.isfile(media_path) or not os.access(media_path, os.R_OK):
            return {
                "success": False,
                "status": "failed",
                "external_post_id": None,
                "permalink": None,
                "error": f"Local media file missing or unreadable: {media_path}",
            }

        from facebook_service import FacebookService
        page_id = None
        account_key = post.get("account_key") or ""
        if account_key.startswith("facebook:") and account_key != "facebook:default":
            page_id = account_key.split(":", 1)[1]
        if not page_id:
            connected = FacebookService.get_connected_page()
            if connected:
                page_id = connected.get("account_id")

        access_token = FacebookService.get_page_token(page_id) if page_id else None
        if not page_id or not access_token:
            return {
                "success": False,
                "status": "failed",
                "external_post_id": None,
                "permalink": None,
                "error": "No active Facebook Page or access token connected",
            }

        caption = (post.get("caption") or "").strip()
        hashtags = (post.get("hashtags") or "").strip()
        description = f"{caption}\n\n{hashtags}".strip() if hashtags else caption
        file_size = os.path.getsize(media_path)
        upload_url = f"{self.GRAPH_VIDEO_BASE}/{page_id}/videos"

        import requests
        try:
            if file_size > self.LARGE_FILE_THRESHOLD:
                start_resp = requests.post(
                    upload_url,
                    data={"upload_phase": "start", "file_size": file_size, "access_token": access_token},
                    timeout=60,
                )
                start_data, parse_err = self._parse_json_response(start_resp)
                if start_resp.status_code >= 400 or not start_data or "error" in start_data:
                    err_msg = (start_data or {}).get("error", {}).get("message") or parse_err or f"HTTP {start_resp.status_code}"
                    return {"success": False, "status": "failed", "external_post_id": None, "permalink": None, "error": f"Facebook upload start failed: {err_msg}"}
                session_id = start_data["upload_session_id"]
                video_id_from_start = str(start_data.get("video_id") or "")
                start_offset = int(start_data.get("start_offset", 0))
                end_offset = int(start_data.get("end_offset", 0))
                with open(media_path, "rb") as f:
                    while start_offset < file_size:
                        f.seek(start_offset)
                        chunk = f.read(max(1, end_offset - start_offset) if end_offset > start_offset else self.CHUNK_SIZE)
                        if not chunk:
                            break
                        t_resp = requests.post(
                            upload_url,
                            data={"upload_phase": "transfer", "upload_session_id": session_id, "start_offset": start_offset, "access_token": access_token},
                            files={"video_file_chunk": chunk},
                            timeout=120,
                        )
                        t_data, parse_err = self._parse_json_response(t_resp)
                        if t_resp.status_code >= 400 or not t_data or "error" in t_data:
                            err_msg = (t_data or {}).get("error", {}).get("message") or parse_err or f"HTTP {t_resp.status_code}"
                            return {"success": False, "status": "failed", "external_post_id": None, "permalink": None, "error": f"Facebook chunk transfer failed: {err_msg}"}
                        start_offset = int(t_data.get("start_offset", file_size))
                        end_offset = int(t_data.get("end_offset", file_size))
                fin_data = {"upload_phase": "finish", "upload_session_id": session_id, "description": description, "access_token": access_token}
                if post.get("title"):
                    fin_data["title"] = post["title"]
                fin_resp = requests.post(upload_url, data=fin_data, timeout=60)
                resp_data, parse_err = self._parse_json_response(fin_resp)
                status_code = fin_resp.status_code
                resp_text = fin_resp.text
            else:
                video_id_from_start = ""
                mp_data = {"description": description, "access_token": access_token}
                if post.get("title"):
                    mp_data["title"] = post["title"]
                with open(media_path, "rb") as f:
                    resp = requests.post(
                        upload_url,
                        data=mp_data,
                        files={"source": (os.path.basename(media_path), f, "video/mp4")},
                        timeout=120,
                    )
                resp_data, parse_err = self._parse_json_response(resp)
                status_code = resp.status_code
                resp_text = resp.text

            if status_code >= 400 or (resp_data and "error" in resp_data):
                err_msg = (resp_data or {}).get("error", {}).get("message") or parse_err or f"HTTP {status_code}"
                return {"success": False, "status": "failed", "external_post_id": None, "permalink": None, "error": f"Facebook API error: {err_msg}"}

            if not resp_data:
                return {
                    "success": False,
                    "status": "failed",
                    "external_post_id": None,
                    "permalink": None,
                    "error": f"Facebook upload outcome uncertain: {parse_err}",
                }

            ext_id = str(resp_data.get("id") or video_id_from_start or "")
            permalink = f"https://www.facebook.com/{page_id}/videos/{ext_id}/" if ext_id else None
            return {
                "success": True,
                "status": "published",
                "external_post_id": ext_id,
                "permalink": permalink,
                "error": None,
            }
        except Exception as exc:
            return {
                "success": False,
                "status": "failed",
                "external_post_id": None,
                "permalink": None,
                "error": f"Facebook upload exception: {exc}",
            }


class InstagramProfessionalAdapter(PlatformAdapter):
    platform = "instagram"
    label = "Instagram Professional"
    GRAPH_API_BASE = "https://graph.facebook.com/v27.0"
    POLL_INTERVAL_SECONDS = 5
    POLL_TIMEOUT_SECONDS = 180

    @staticmethod
    def _parse_json_response(resp) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Safely parse a Graph API response without raising JSONDecodeError on empty/non-JSON bodies."""
        body = (getattr(resp, "text", None) or "").strip()
        if not body:
            return None, f"Empty response body (HTTP {resp.status_code})"
        try:
            data = resp.json()
            if isinstance(data, dict):
                return data, None
            return None, f"Unexpected JSON type {type(data).__name__} (HTTP {resp.status_code})"
        except Exception:
            ctype = (getattr(resp, "headers", None) or {}).get("Content-Type", "unknown")
            return None, f"Non-JSON response (HTTP {resp.status_code}, Content-Type={ctype}, len={len(body)})"

    def publish(self, post: Dict[str, Any], safe_mode: bool = True) -> Dict[str, Any]:
        # Explicit production publishing guard: never make real API calls when Safe Testing Mode is ON
        if safe_mode or database.get_settings().get("safe_test_mode", "true").lower() == "true":
            return super().publish(post, safe_mode=True)

        media_path = post.get("media_path") or ""
        if not media_path or not os.path.isfile(media_path) or not os.access(media_path, os.R_OK):
            return {
                "success": False,
                "status": "failed",
                "external_post_id": None,
                "permalink": None,
                "error": f"Local media file missing or unreadable: {media_path}",
            }

        ok, err = validate_platform_media(
            platform="instagram",
            filename=post.get("original_filename") or os.path.basename(media_path),
            file_size_bytes=os.path.getsize(media_path),
            duration_seconds=post.get("duration_seconds"),
        )
        if not ok:
            return {
                "success": False,
                "status": "failed",
                "external_post_id": None,
                "permalink": None,
                "error": err,
            }

        from instagram_service import InstagramService
        ig_user_id = None
        account_key = post.get("account_key") or ""
        if account_key.startswith("instagram:") and account_key != "instagram:default":
            ig_user_id = account_key.split(":", 1)[1]
        if not ig_user_id:
            connected = InstagramService.get_connected_account()
            if connected:
                ig_user_id = connected.get("account_id")

        access_token = InstagramService.get_account_token(ig_user_id) if ig_user_id else None
        if not ig_user_id or not access_token:
            return {
                "success": False,
                "status": "failed",
                "external_post_id": None,
                "permalink": None,
                "error": "No active Instagram Professional account or access token connected",
            }

        import temp_media_service
        temp_token = None
        video_url = (post.get("public_media_url") or "").strip()
        if not video_url:
            base_url = (os.environ.get("GSP_PUBLIC_MEDIA_BASE_URL") or database.get_settings().get("public_media_base_url") or "").strip().rstrip("/")
            lower_base = base_url.lower()
            if not base_url or not lower_base.startswith("https://") or any(h in lower_base for h in ("localhost", "127.0.0.1", "::1")):
                return {
                    "success": False,
                    "status": "failed",
                    "external_post_id": None,
                    "permalink": None,
                    "error": "Instagram Reels requires a publicly accessible video_url via HTTPS GSP_PUBLIC_MEDIA_BASE_URL (non-localhost) or public_media_url",
                }
            try:
                temp_token = temp_media_service.create_temp_media_token(
                    job_id=int(post.get("id") or 0),
                    media_path=media_path,
                )
            except Exception as exc:
                return {
                    "success": False,
                    "status": "failed",
                    "external_post_id": None,
                    "permalink": None,
                    "error": f"Temporary media token creation failed: {exc}",
                }
            video_url = f"{base_url}/api/media/temp/{temp_token}"

        caption = (post.get("caption") or "").strip()
        hashtags = (post.get("hashtags") or "").strip()
        full_caption = f"{caption}\n\n{hashtags}".strip() if hashtags else caption

        import requests
        import time
        try:
            # 1. Reuse existing container_id if present (prevent duplicate container creation)
            container_id = str(post.get("external_post_id") or "").strip()
            if not container_id:
                c_resp = requests.post(
                    f"{self.GRAPH_API_BASE}/{ig_user_id}/media",
                    data={
                        "media_type": "REELS",
                        "video_url": video_url,
                        "caption": full_caption,
                        "access_token": access_token,
                    },
                    timeout=60,
                )
                c_data, c_err = self._parse_json_response(c_resp)
                if c_resp.status_code >= 400 or not c_data or "error" in c_data or "id" not in c_data:
                    temp_media_service.revoke_temp_media_token(temp_token)
                    err_msg = (c_data or {}).get("error", {}).get("message") or c_err or c_resp.text
                    return {"success": False, "status": "failed", "external_post_id": None, "permalink": None, "error": f"Instagram container creation failed: {err_msg}"}
                container_id = str(c_data["id"])

            # 2. Poll container status with bounded interval and timeout
            container_finished = False
            poll_start = time.monotonic()
            poll_attempts = 0
            while True:
                poll_attempts += 1
                try:
                    s_resp = requests.get(
                        f"{self.GRAPH_API_BASE}/{container_id}",
                        params={"fields": "status_code,status", "access_token": access_token},
                        timeout=30,
                    )
                    if s_resp.status_code == 429 or s_resp.status_code >= 500:
                        if time.monotonic() - poll_start >= self.POLL_TIMEOUT_SECONDS:
                            break
                        time.sleep(self.POLL_INTERVAL_SECONDS)
                        continue
                    s_data, _ = self._parse_json_response(s_resp)
                    status_code = (s_data or {}).get("status_code")
                    if status_code == "FINISHED":
                        container_finished = True
                        break
                    if status_code in ("ERROR", "EXPIRED"):
                        temp_media_service.revoke_temp_media_token(temp_token)
                        return {"success": False, "status": "failed", "external_post_id": container_id, "permalink": None, "error": f"Instagram container processing failed: {(s_data or {}).get('status', status_code)}"}
                except Exception:
                    if time.monotonic() - poll_start >= self.POLL_TIMEOUT_SECONDS:
                        break
                if time.monotonic() - poll_start >= self.POLL_TIMEOUT_SECONDS:
                    break
                time.sleep(self.POLL_INTERVAL_SECONDS)

            if not container_finished:
                return {"success": False, "status": "failed", "external_post_id": container_id, "permalink": None, "error": f"Instagram container processing timed out before FINISHED (attempts={poll_attempts})"}

            # 3. Publish container
            p_resp = requests.post(
                f"{self.GRAPH_API_BASE}/{ig_user_id}/media_publish",
                data={"creation_id": container_id, "access_token": access_token},
                timeout=60,
            )
            temp_media_service.revoke_temp_media_token(temp_token)
            p_data = p_resp.json()
            if p_resp.status_code >= 400 or "error" in p_data or "id" not in p_data:
                err_msg = p_data.get("error", {}).get("message", p_resp.text)
                return {"success": False, "status": "failed", "external_post_id": container_id, "permalink": None, "error": f"Instagram publish failed: {err_msg}"}
            media_id = str(p_data["id"])

            # 4. Fetch permalink
            permalink = None
            try:
                m_resp = requests.get(
                    f"{self.GRAPH_API_BASE}/{media_id}",
                    params={"fields": "permalink", "access_token": access_token},
                    timeout=30,
                )
                if m_resp.status_code < 400:
                    permalink = m_resp.json().get("permalink")
            except Exception:
                pass

            return {
                "success": True,
                "status": "published",
                "external_post_id": media_id,
                "permalink": permalink,
                "error": None,
            }
        except Exception as exc:
            return {
                "success": False,
                "status": "failed",
                "external_post_id": None,
                "permalink": None,
                "error": f"Instagram upload exception: {exc}",
            }


class YouTubeChannelAdapter(PlatformAdapter):
    platform = "youtube"
    label = "YouTube Channel"
    UPLOAD_INIT_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
    CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB streaming chunks

    @staticmethod
    def _parse_json_response(resp) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Safely parse a Graph API response without raising JSONDecodeError on empty/non-JSON bodies."""
        body = (getattr(resp, "text", None) or "").strip()
        if not body:
            return None, f"Empty response body (HTTP {resp.status_code})"
        try:
            data = resp.json()
            if isinstance(data, dict):
                return data, None
            return None, f"Unexpected JSON type {type(data).__name__} (HTTP {resp.status_code})"
        except Exception:
            ctype = (getattr(resp, "headers", None) or {}).get("Content-Type", "unknown")
            return None, f"Non-JSON response (HTTP {resp.status_code}, Content-Type={ctype}, len={len(body)})"

    def publish(self, post: Dict[str, Any], safe_mode: bool = True) -> Dict[str, Any]:
        # Explicit production publishing guard: never make real API calls when Safe Testing Mode is ON
        if safe_mode or database.get_settings().get("safe_test_mode", "true").lower() == "true":
            return super().publish(post, safe_mode=True)

        media_path = post.get("media_path") or ""
        if not media_path or not os.path.isfile(media_path) or not os.access(media_path, os.R_OK):
            return {
                "success": False,
                "status": "failed",
                "external_post_id": None,
                "permalink": None,
                "error": f"Local media file missing or unreadable: {media_path}",
            }

        file_size = os.path.getsize(media_path)
        ok, err = validate_platform_media(
            platform="youtube",
            filename=post.get("original_filename") or os.path.basename(media_path),
            file_size_bytes=file_size,
            duration_seconds=post.get("duration_seconds"),
        )
        if not ok:
            return {"success": False, "status": "failed", "external_post_id": None, "permalink": None, "error": err}

        from youtube_service import YouTubeService
        channel_id = None
        account_key = post.get("account_key") or ""
        if account_key.startswith("youtube:") and account_key != "youtube:default":
            channel_id = account_key.split(":", 1)[1]
        if not channel_id:
            connected = YouTubeService.get_connected_account()
            if connected:
                channel_id = connected.get("account_id")

        access_token = YouTubeService.get_valid_access_token(channel_id) if channel_id else None
        if not channel_id or not access_token:
            return {
                "success": False,
                "status": "failed",
                "external_post_id": None,
                "permalink": None,
                "error": "No active YouTube channel or valid access token connected",
            }

        caption = (post.get("caption") or "").strip()
        hashtags = (post.get("hashtags") or "").strip()
        description = f"{caption}\n\n{hashtags}".strip() if hashtags else caption
        title = (post.get("title") or f"{post.get('zodiac_tamil', '')} ({post.get('zodiac_english', '')}) - {post.get('category', 'Astrology')}".strip(" -"))[:100]
        tags = [t.lstrip("#").strip() for t in hashtags.split() if t.strip()]
        privacy_status = post.get("privacy_status") or "public"
        if privacy_status not in ("private", "unlisted", "public"):
            privacy_status = "public"

        metadata = {
            "snippet": {
                "title": title or "GSP Video",
                "description": description,
                "tags": tags,
                "categoryId": "22",
            },
            "status": {
                "privacyStatus": privacy_status,
            },
        }

        import requests
        try:
            upload_url = post.get("upload_session_url") or ""
            offset = 0

            # If we have a persisted session URL, query its status before deciding to resume or restart
            if upload_url:
                status_resp = requests.put(
                    upload_url,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Length": "0",
                        "Content-Range": f"bytes */{file_size}",
                    },
                    timeout=30,
                )
                if status_resp.status_code in (200, 201):
                    resp_data = status_resp.json()
                    vid_id = str(resp_data.get("id") or "")
                    if vid_id:
                        return {
                            "success": True,
                            "status": "published",
                            "external_post_id": vid_id,
                            "permalink": f"https://www.youtube.com/watch?v={vid_id}",
                            "error": None,
                        }
                elif status_resp.status_code == 308:
                    range_hdr = status_resp.headers.get("Range", "")
                    if "-" in range_hdr:
                        try:
                            offset = int(range_hdr.split("-")[-1]) + 1
                        except ValueError:
                            offset = int(post.get("bytes_uploaded") or 0)
                else:
                    # Expired or invalid session (404/410) -> start a new session
                    upload_url = ""

            if not upload_url:
                init_resp = requests.post(
                    self.UPLOAD_INIT_URL,
                    params={"uploadType": "resumable", "part": "snippet,status"},
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json; charset=UTF-8",
                        "X-Upload-Content-Length": str(file_size),
                        "X-Upload-Content-Type": "video/*",
                    },
                    json=metadata,
                    timeout=60,
                )
                if init_resp.status_code >= 400:
                    return {
                        "success": False,
                        "status": "failed",
                        "external_post_id": None,
                        "permalink": None,
                        "error": f"YouTube resumable init failed ({init_resp.status_code}): {init_resp.text}",
                    }

                upload_url = init_resp.headers.get("Location")
                if not upload_url:
                    return {
                        "success": False,
                        "status": "failed",
                        "external_post_id": None,
                        "permalink": None,
                        "error": "YouTube resumable init missing Location header",
                    }

                # Persist upload_session_url and total_file_size
                if post.get("id"):
                    conn = database.get_connection()
                    conn.execute(
                        "UPDATE scheduled_posts SET upload_session_url = ?, total_file_size = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (upload_url, file_size, post["id"]),
                    )
                    conn.commit()
                    conn.close()

            resp_data = None
            with open(media_path, "rb") as f:
                f.seek(offset)
                while offset < file_size:
                    chunk = f.read(self.CHUNK_SIZE)
                    if not chunk:
                        break
                    end = offset + len(chunk) - 1
                    put_resp = requests.put(
                        upload_url,
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Length": str(len(chunk)),
                            "Content-Range": f"bytes {offset}-{end}/{file_size}",
                        },
                        data=chunk,
                        timeout=120,
                    )
                    if put_resp.status_code in (200, 201):
                        resp_data = put_resp.json()
                        break
                    if put_resp.status_code == 308:
                        offset += len(chunk)
                        if post.get("id"):
                            pct = round((offset / file_size) * 100.0, 2) if file_size else 0.0
                            conn = database.get_connection()
                            conn.execute(
                                "UPDATE scheduled_posts SET bytes_uploaded = ?, upload_progress_pct = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                                (offset, pct, post["id"]),
                            )
                            conn.commit()
                            conn.close()
                        continue
                    return {
                        "success": False,
                        "status": "failed",
                        "external_post_id": None,
                        "permalink": None,
                        "error": f"YouTube chunk upload failed ({put_resp.status_code}): {put_resp.text}",
                    }

            if not resp_data or not resp_data.get("id"):
                return {
                    "success": False,
                    "status": "failed",
                    "external_post_id": None,
                    "permalink": None,
                    "error": "YouTube upload did not return a video ID",
                }

            vid_id = str(resp_data["id"])
            return {
                "success": True,
                "status": "published",
                "external_post_id": vid_id,
                "permalink": f"https://www.youtube.com/watch?v={vid_id}",
                "error": None,
            }
        except Exception as exc:
            return {
                "success": False,
                "status": "failed",
                "external_post_id": None,
                "permalink": None,
                "error": f"YouTube upload exception: {exc}",
            }


PLATFORM_ADAPTERS: Dict[str, PlatformAdapter] = {
    "facebook": FacebookPageAdapter(),
    "instagram": InstagramProfessionalAdapter(),
    "youtube": YouTubeChannelAdapter(),
}


def get_platform_adapter(platform: str) -> PlatformAdapter:
    key = (platform or "").lower().strip()
    adapter = PLATFORM_ADAPTERS.get(key)
    if not adapter:
        raise ValueError(f"Unsupported platform: {platform}")
    return adapter


def detect_zodiac_from_filename(filename: str) -> Optional[Dict[str, Any]]:
    """Detect zodiac sign from a video filename using Tamil or English aliases."""
    if not filename:
        return None
    stem = os.path.splitext(os.path.basename(filename))[0].strip()
    normalized = re.sub(r"[_\-\.\s]+", " ", stem).strip().lower()

    # Check Tamil exact/substring first
    for sign in ZODIAC_SIGNS:
        if sign["tamil"] in stem:
            return {
                "index": sign["index"],
                "tamil": sign["tamil"],
                "english": sign["english"],
            }

    # Check English/transliterated aliases as whole tokens first, then substring
    tokens = set(normalized.split())
    for sign in ZODIAC_SIGNS:
        for alias in sign["aliases"]:
            if alias in tokens:
                return {
                    "index": sign["index"],
                    "tamil": sign["tamil"],
                    "english": sign["english"],
                }

    for sign in ZODIAC_SIGNS:
        for alias in sign["aliases"]:
            if len(alias) >= 4 and alias in normalized:
                return {
                    "index": sign["index"],
                    "tamil": sign["tamil"],
                    "english": sign["english"],
                }

    return None


CONSULTATION_CONTACT_BLOCK = (
    "ஜோதிட ஆலோசனை மற்றும் ஆன்லைன் கன்சல்டேஷனுக்கு:\n"
    "📞 WhatsApp: +91 94445 59071"
)
ASTROLOGY_BRAND_NAME = "Gokul's Astrological Insights"
ASTROLOGY_BRAND_HASHTAG = "#GokulsAstrologicalInsights"


PLATFORM_HASHTAG_LIMITS: Dict[str, int] = {
    "facebook": 5,
    "instagram": 15,
    "youtube": 15,
}


def _limit_hashtags(hashtags: str, max_count: int) -> str:
    tags = [t for t in (hashtags or "").split() if t.startswith("#")]
    return " ".join(tags[:max_count])


def build_platform_descriptions(caption: str, hashtags: str) -> Dict[str, str]:
    """Build platform-ready descriptions for YouTube, Facebook, and Instagram."""
    clean_caption = (caption or "").strip()
    clean_hashtags = (hashtags or "").strip()

    yt_tags = _limit_hashtags(clean_hashtags, PLATFORM_HASHTAG_LIMITS["youtube"])
    fb_tags = _limit_hashtags(clean_hashtags, PLATFORM_HASHTAG_LIMITS["facebook"])
    ig_tags = _limit_hashtags(clean_hashtags, PLATFORM_HASHTAG_LIMITS["instagram"])

    yt_text = f"{clean_caption}\n\n{yt_tags}".strip() if yt_tags else clean_caption
    fb_text = f"{clean_caption}\n\n{fb_tags}".strip() if fb_tags else clean_caption
    ig_text = f"{clean_caption}\n\n{ig_tags}".strip() if ig_tags else clean_caption

    # Instagram caption limit is 2200 characters
    if len(ig_text) > 2200:
        if ig_tags and len(ig_tags) < 2000:
            max_cap = 2200 - len(ig_tags) - 5
            ig_text = f"{clean_caption[:max_cap].rstrip()}...\n\n{ig_tags}"
        else:
            ig_text = ig_text[:2197].rstrip() + "..."

    return {
        "youtube": yt_text,
        "facebook": fb_text,
        "instagram": ig_text,
    }


def generate_caption_and_hashtags(zodiac_index: int, category: str) -> Dict[str, Any]:
    """Generate detailed Tamil caption, contact info, and Rasi-specific hashtags."""
    sign = ZODIAC_BY_INDEX.get(zodiac_index)
    if not sign:
        raise ValueError(f"Invalid zodiac_index: {zodiac_index}")

    tamil = sign["tamil"]
    english = sign["english"]
    eng_tag = english.replace(" ", "")

    if category == "Weekly Rasi Palan":
        hook = f"✨ {tamil} ({english}) ராசி அன்பர்களே! இந்த வார ராசி பலன்! 🙏"
        intro = (
            f"{tamil} ({english}) ராசிக்காரர்களுக்கான இந்த வார ராசி பலன் பற்றிய "
            "முக்கிய தகவல்கள், கவனிக்க வேண்டிய விஷயங்கள் மற்றும் பொதுவான வழிகாட்டுதல்கள் "
            "இந்த வீடியோவில் பகிரப்பட்டுள்ளன."
        )
        cat_tags = ["#வாரராசிபலன்", "#WeeklyRasiPalan"]
    elif category == "Monthly Rasi Palan":
        hook = f"✨ {tamil} ({english}) ராசி அன்பர்களே! இந்த மாத ராசி பலன்! 🙏"
        intro = (
            f"{tamil} ({english}) ராசிக்காரர்களுக்கான இந்த மாத ராசி பலன் பற்றிய "
            "முக்கிய தகவல்கள், கவனிக்க வேண்டிய விஷயங்கள் மற்றும் பொதுவான வழிகாட்டுதல்கள் "
            "இந்த வீடியோவில் பகிரப்பட்டுள்ளன."
        )
        cat_tags = ["#மாதராசிபலன்", "#MonthlyRasiPalan"]
    elif category == "Zodiac Characteristics":
        hook = f"✨ {tamil} ({english}) ராசியின் சிறப்பம்சங்கள் மற்றும் குணநலன்கள்! 🙏"
        intro = (
            f"{tamil} ({english}) ராசிக்காரர்களின் இயல்பான குணநலன்கள், பலம் மற்றும் "
            "முக்கிய சிறப்பம்சங்கள் பற்றிய முழுமையான தகவல்கள் இந்த வீடியோவில் பகிரப்பட்டுள்ளன."
        )
        cat_tags = ["#ராசிகுணங்கள்", "#ZodiacCharacteristics"]
    else:
        hook = f"✨ {tamil} ({english}) ராசி அன்பர்களே! ஜோதிட சிறப்பு பதிவு! 🙏"
        intro = (
            f"{tamil} ({english}) ராசிக்காரர்களுக்கான பயனுள்ள ஜோதிடத் தகவல்கள் மற்றும் "
            "வழிகாட்டுதல்கள் இந்த வீடியோவில் பகிரப்பட்டுள்ளன."
        )
        cat_tags = ["#ஜோதிடம்", "#AstrologyInsights"]

    cta = "முழுமையான தகவல்களுக்கும் தெளிவான வழிகாட்டுதல்களுக்கும் வீடியோவை முழுமையாகப் பாருங்கள்! 🎥✨"
    brand_line = f"🌟 {ASTROLOGY_BRAND_NAME}"

    caption = "\n\n".join([hook, intro, cta, brand_line, CONSULTATION_CONTACT_BLOCK])

    tag_list = [
        f"#{tamil}",
        f"#{tamil}ராசி",
        f"#{tamil}ராசிபலன்",
        f"#{eng_tag}",
        f"#{eng_tag}Horoscope",
        *cat_tags,
        "#RasiPalan",
        "#TamilAstrology",
        "#VedicAstrology",
        ASTROLOGY_BRAND_HASHTAG,
    ]
    # Deduplicate while preserving order and cap at 15 hashtags
    seen = set()
    unique_tags = []
    for t in tag_list:
        if t not in seen:
            seen.add(t)
            unique_tags.append(t)
    hashtags = " ".join(unique_tags[:15])

    return {
        "caption": caption,
        "hashtags": hashtags,
        "platform_descriptions": build_platform_descriptions(caption, hashtags),
    }


def validate_platform_media(
    platform: str,
    filename: str,
    file_size_bytes: int,
    duration_seconds: Optional[float] = None,
) -> Tuple[bool, Optional[str]]:
    """Validate media file against platform-specific requirements."""
    plat = (platform or "").strip().lower()
    rules = PLATFORM_MEDIA_RULES.get(plat)
    if not rules:
        return False, f"Unsupported platform: {platform}"

    ext = os.path.splitext(filename)[1].lower()
    if ext not in rules["extensions"]:
        allowed = ", ".join(sorted(rules["extensions"]))
        return False, f"{rules['label']} requires video format in ({allowed}); got '{ext or 'none'}'"

    if file_size_bytes > rules["max_bytes"]:
        return False, f"File exceeds maximum size for {rules['label']}"

    max_dur = rules.get("max_duration_seconds")
    if max_dur is not None and duration_seconds is not None and duration_seconds > max_dur:
        return False, f"{rules['label']} Reels duration must be <= {int(max_dur)}s (got {duration_seconds:.1f}s)"

    return True, None


def analyze_batch_items(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Sort items in standard zodiac order and detect missing/duplicate signs."""
    detected_counts: Dict[int, int] = {}
    undetected: List[str] = []

    for item in items:
        z_idx = item.get("zodiac_index")
        if z_idx and z_idx in ZODIAC_BY_INDEX:
            detected_counts[z_idx] = detected_counts.get(z_idx, 0) + 1
        else:
            undetected.append(item.get("original_filename", "unknown"))

    missing_signs = [
        {"index": z["index"], "tamil": z["tamil"], "english": z["english"]}
        for z in ZODIAC_SIGNS
        if z["index"] not in detected_counts
    ]
    duplicate_signs = [
        {
            "index": idx,
            "tamil": ZODIAC_BY_INDEX[idx]["tamil"],
            "english": ZODIAC_BY_INDEX[idx]["english"],
            "count": count,
        }
        for idx, count in sorted(detected_counts.items())
        if count > 1
    ]

    sorted_items = sorted(
        items,
        key=lambda x: (x.get("zodiac_index") or 999, x.get("original_filename", "")),
    )

    return {
        "items": sorted_items,
        "missing_signs": missing_signs,
        "duplicate_signs": duplicate_signs,
        "undetected_files": undetected,
        "is_complete_12": len(missing_signs) == 0 and len(duplicate_signs) == 0 and len(undetected) == 0 and len(items) == 12,
    }


DEFAULT_TIMEZONE = "Asia/Kolkata"
DEFAULT_WEEKLY_GOAL = 14
DEFAULT_ENABLED_DAYS = [0, 1, 2, 3, 4, 5, 6]


def _safe_zoneinfo(tz_name: Optional[str]) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name or DEFAULT_TIMEZONE)
    except Exception:
        return ZoneInfo(DEFAULT_TIMEZONE)


def get_posting_schedule_settings(account_key: str = "facebook:default") -> Dict[str, Any]:
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT account_key, timezone, weekly_goal, enabled_days FROM posting_schedule_settings WHERE account_key = ?",
        (account_key,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {
            "account_key": account_key,
            "timezone": DEFAULT_TIMEZONE,
            "weekly_goal": DEFAULT_WEEKLY_GOAL,
            "enabled_days": list(DEFAULT_ENABLED_DAYS),
        }
    try:
        enabled = json.loads(row["enabled_days"])
        enabled = sorted({int(d) for d in enabled if 0 <= int(d) <= 6})
    except Exception:
        enabled = list(DEFAULT_ENABLED_DAYS)
    return {
        "account_key": row["account_key"],
        "timezone": row["timezone"] or DEFAULT_TIMEZONE,
        "weekly_goal": int(row["weekly_goal"]) if row["weekly_goal"] is not None else DEFAULT_WEEKLY_GOAL,
        "enabled_days": enabled,
    }


def save_posting_schedule_settings(
    account_key: str,
    timezone: Optional[str] = None,
    weekly_goal: Optional[int] = None,
    enabled_days: Optional[List[int]] = None,
) -> Dict[str, Any]:
    current = get_posting_schedule_settings(account_key)
    new_tz = current["timezone"]
    if timezone is not None:
        # Validate timezone
        ZoneInfo(timezone)
        new_tz = timezone
    new_goal = current["weekly_goal"]
    if weekly_goal is not None:
        new_goal = max(1, min(500, int(weekly_goal)))
    new_days = current["enabled_days"]
    if enabled_days is not None:
        new_days = sorted({int(d) for d in enabled_days if 0 <= int(d) <= 6})

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO posting_schedule_settings (account_key, timezone, weekly_goal, enabled_days, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(account_key) DO UPDATE SET
            timezone = excluded.timezone,
            weekly_goal = excluded.weekly_goal,
            enabled_days = excluded.enabled_days,
            updated_at = CURRENT_TIMESTAMP
        """,
        (account_key, new_tz, new_goal, json.dumps(new_days)),
    )
    conn.commit()
    conn.close()
    return get_posting_schedule_settings(account_key)


def get_posting_slots(account_key: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = database.get_connection()
    cursor = conn.cursor()
    if account_key:
        cursor.execute(
            "SELECT * FROM posting_slots WHERE account_key = ? AND is_active = 1 ORDER BY day_of_week ASC, slot_time ASC, slot_order ASC",
            (account_key,),
        )
    else:
        cursor.execute(
            "SELECT * FROM posting_slots WHERE is_active = 1 ORDER BY account_key ASC, day_of_week ASC, slot_time ASC, slot_order ASC"
        )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def save_posting_slots(account_key: str, slots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Replace active posting slots for an account_key, preventing duplicates."""
    seen = set()
    deduped: List[Tuple[int, str]] = []
    for slot in slots:
        day_of_week = int(slot.get("day_of_week", -1))
        slot_time = str(slot.get("slot_time", "09:00")).strip()
        key = (day_of_week, slot_time)
        if key not in seen:
            seen.add(key)
            deduped.append(key)

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM posting_slots WHERE account_key = ?", (account_key,))
    for idx, (day_of_week, slot_time) in enumerate(deduped):
        cursor.execute(
            """
            INSERT OR IGNORE INTO posting_slots (account_key, day_of_week, slot_time, slot_order, is_active)
            VALUES (?, ?, ?, ?, 1)
            """,
            (account_key, day_of_week, slot_time, idx),
        )
    conn.commit()
    conn.close()
    return get_posting_slots(account_key)


def add_posting_slot(account_key: str, day_of_week: int, slot_time: str) -> List[Dict[str, Any]]:
    """Add a posting slot to a specific day or to all enabled days (-1), preventing duplicates."""
    slot_time = str(slot_time).strip()
    if day_of_week == -1:
        settings = get_posting_schedule_settings(account_key)
        target_days = settings["enabled_days"] or list(DEFAULT_ENABLED_DAYS)
    else:
        target_days = [int(day_of_week)]

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COALESCE(MAX(slot_order), -1) FROM posting_slots WHERE account_key = ?",
        (account_key,),
    )
    max_order = int(cursor.fetchone()[0])
    for d in target_days:
        max_order += 1
        cursor.execute(
            """
            INSERT OR IGNORE INTO posting_slots (account_key, day_of_week, slot_time, slot_order, is_active)
            VALUES (?, ?, ?, ?, 1)
            """,
            (account_key, d, slot_time, max_order),
        )
    conn.commit()
    conn.close()
    return get_posting_slots(account_key)


def generate_posting_slots(
    account_key: str,
    mode: str,
    days: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """Generate posting slots according to mode: even, periods, goal, clear, regenerate_days."""
    settings = get_posting_schedule_settings(account_key)
    enabled_days = settings["enabled_days"] or list(DEFAULT_ENABLED_DAYS)

    if mode == "clear":
        return save_posting_slots(account_key, [])

    if mode == "even":
        times = ["09:00", "18:00"]
        new_slots = [{"day_of_week": d, "slot_time": t} for d in enabled_days for t in times]
        return save_posting_slots(account_key, new_slots)

    if mode == "periods":
        times = ["09:00", "14:00", "19:00"]
        new_slots = [{"day_of_week": d, "slot_time": t} for d in enabled_days for t in times]
        return save_posting_slots(account_key, new_slots)

    if mode == "goal":
        goal = max(1, int(settings.get("weekly_goal") or DEFAULT_WEEKLY_GOAL))
        candidate_times = [
            "09:00", "18:00", "12:00", "15:00", "20:00",
            "10:30", "13:30", "16:30", "21:00", "08:00",
            "11:00", "17:00", "19:30", "22:00",
        ]
        new_slots: List[Dict[str, Any]] = []
        idx = 0
        while len(new_slots) < goal and idx < goal * 2:
            d = enabled_days[idx % len(enabled_days)]
            t_idx = idx // len(enabled_days)
            t = candidate_times[t_idx % len(candidate_times)]
            new_slots.append({"day_of_week": d, "slot_time": t})
            idx += 1
        return save_posting_slots(account_key, new_slots)

    if mode == "regenerate_days":
        target_days = set(days if days is not None else enabled_days)
        existing = [s for s in get_posting_slots(account_key) if int(s["day_of_week"]) not in target_days]
        times = ["09:00", "18:00"]
        for d in sorted(target_days):
            for t in times:
                existing.append({"day_of_week": d, "slot_time": t})
        return save_posting_slots(account_key, existing)

    raise ValueError(f"Unsupported slot generation mode: {mode}")


def delete_posting_slot(slot_id: int) -> bool:
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM posting_slots WHERE id = ?", (slot_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def _compute_shared_available_slots(
    account_keys: List[str],
    count: int,
    start_from: Optional[datetime] = None,
) -> List[str]:
    """Assign next available shared slot timestamps across all selected accounts."""
    primary_key = account_keys[0] if account_keys else "facebook:default"
    settings = get_posting_schedule_settings(primary_key)
    tz = _safe_zoneinfo(settings.get("timezone"))
    if start_from is None:
        now = datetime.now(tz)
    elif start_from.tzinfo is None:
        now = start_from.replace(tzinfo=tz)
    else:
        now = start_from.astimezone(tz)

    enabled_days = set(settings.get("enabled_days") or DEFAULT_ENABLED_DAYS)
    weekly_goal = int(settings.get("weekly_goal") or 0)

    slots = get_posting_slots(primary_key)
    if not slots:
        slots = [
            {"day_of_week": -1, "slot_time": "09:00"},
            {"day_of_week": -1, "slot_time": "18:00"},
        ]

    conn = database.get_connection()
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in account_keys)
    cursor.execute(
        f"SELECT scheduled_at FROM scheduled_posts WHERE account_key IN ({placeholders}) AND status IN ('scheduled', 'publishing')",
        tuple(account_keys),
    )
    occupied = {row["scheduled_at"] for row in cursor.fetchall()}
    conn.close()

    # Count existing occupied posts per ISO week (year, week)
    week_counts: Dict[Tuple[int, int], int] = {}
    for ts in occupied:
        try:
            dt = datetime.fromisoformat(ts)
            iso_cal = dt.isocalendar()
            wk = (iso_cal.year, iso_cal.week)
            week_counts[wk] = week_counts.get(wk, 0) + 1
        except Exception:
            pass

    assigned: List[str] = []
    day_offset = 0
    while len(assigned) < count and day_offset < 180:
        candidate_date = (now + timedelta(days=day_offset)).date()
        weekday = candidate_date.weekday()
        if weekday not in enabled_days:
            day_offset += 1
            continue

        iso_cal = candidate_date.isocalendar()
        wk_key = (iso_cal.year, iso_cal.week)

        # Collect matching slots for this weekday, sorted chronologically
        day_slots = [
            s for s in slots
            if int(s.get("day_of_week", -1)) in (-1, weekday)
        ]
        day_slots.sort(key=lambda s: s.get("slot_time", "00:00"))

        for slot in day_slots:
            if len(assigned) >= count:
                break
            if weekly_goal > 0 and week_counts.get(wk_key, 0) >= weekly_goal:
                break
            hh_mm = slot["slot_time"]
            try:
                hour, minute = map(int, hh_mm.split(":"))
            except ValueError:
                continue
            candidate_dt = datetime(
                candidate_date.year, candidate_date.month, candidate_date.day, hour, minute, 0, tzinfo=tz
            )
            if candidate_dt <= now:
                continue
            iso_str = candidate_dt.strftime("%Y-%m-%dT%H:%M:00")
            if iso_str not in occupied and iso_str not in assigned:
                assigned.append(iso_str)
                week_counts[wk_key] = week_counts.get(wk_key, 0) + 1
                occupied.add(iso_str)
        day_offset += 1

    return assigned


def _compute_next_available_slots(
    account_key: str,
    count: int,
    start_from: Optional[datetime] = None,
) -> List[str]:
    """Assign next available slot timestamps for account_key, avoiding existing active posts."""
    return _compute_shared_available_slots([account_key], count, start_from=start_from)


def schedule_multichannel_batch(
    accounts: List[Dict[str, str]],
    category: str,
    items: List[Dict[str, Any]],
    batch_id: Optional[str] = None,
    start_from: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Schedule a batch of zodiac videos across multiple selected accounts with shared timestamps."""
    if not accounts:
        raise ValueError("Select at least one publishing channel")
    if category not in BATCH_CATEGORIES:
        raise ValueError(f"Unsupported category: {category}")
    if not items:
        raise ValueError("No videos provided in batch")

    for acc in accounts:
        get_platform_adapter(acc["platform"])
        for item in items:
            ok, err = validate_platform_media(
                platform=acc["platform"],
                filename=item["original_filename"],
                file_size_bytes=int(item.get("file_size_bytes", 0)),
                duration_seconds=item.get("duration_seconds"),
            )
            if not ok:
                raise ValueError(f"{item['original_filename']} ({acc['platform']}): {err}")

    for item in items:
        if not item.get("zodiac_index"):
            detected = detect_zodiac_from_filename(item.get("original_filename", ""))
            if detected:
                item["zodiac_index"] = detected["index"]
                item["zodiac_tamil"] = detected["tamil"]
                item["zodiac_english"] = detected["english"]

    analysis = analyze_batch_items(items)
    sorted_items = analysis["items"]
    for item in sorted_items:
        z_idx = item.get("zodiac_index")
        if not z_idx or z_idx not in ZODIAC_BY_INDEX:
            raise ValueError(f"Missing zodiac sign for file: {item.get('original_filename')}")

    account_keys = [a["account_key"] for a in accounts]
    slot_times = _compute_shared_available_slots(account_keys, len(sorted_items), start_from=start_from)
    if len(slot_times) < len(sorted_items):
        raise RuntimeError("Could not find enough available posting slots")

    final_batch_id = batch_id or str(uuid.uuid4())[:8]
    conn = database.get_connection()
    cursor = conn.cursor()
    created_posts: List[Dict[str, Any]] = []

    for item, scheduled_at in zip(sorted_items, slot_times):
        z_idx = int(item["zodiac_index"])
        sign = ZODIAC_BY_INDEX[z_idx]
        gen = generate_caption_and_hashtags(z_idx, category)
        caption = item.get("caption") or gen["caption"]
        hashtags = item.get("hashtags") or gen["hashtags"]
        video_id = item.get("video_id") or f"{final_batch_id}_{z_idx}_{str(uuid.uuid4())[:6]}"

        for acc in accounts:
            cursor.execute(
                "SELECT id FROM scheduled_posts WHERE video_id = ? AND account_key = ?",
                (video_id, acc["account_key"]),
            )
            if cursor.fetchone():
                continue
            cursor.execute(
                """
                INSERT INTO scheduled_posts (
                    batch_id, video_id, account_key, platform, zodiac_index, zodiac_tamil, zodiac_english,
                    category, original_filename, media_path, thumbnail_path,
                    caption, hashtags, scheduled_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'scheduled')
                """,
                (
                    final_batch_id,
                    video_id,
                    acc["account_key"],
                    acc["platform"].lower(),
                    z_idx,
                    sign["tamil"],
                    sign["english"],
                    category,
                    item["original_filename"],
                    item["media_path"],
                    item.get("thumbnail_path"),
                    caption,
                    hashtags,
                    scheduled_at,
                ),
            )
            post_id = cursor.lastrowid
            cursor.execute("SELECT * FROM scheduled_posts WHERE id = ?", (post_id,))
            created_posts.append(dict(cursor.fetchone()))

    conn.commit()
    conn.close()

    return {
        "batch_id": final_batch_id,
        "videos_count": len(sorted_items),
        "channels_count": len(accounts),
        "scheduled_count": len(created_posts),
        "posts": created_posts,
        "warnings": {
            "missing_signs": analysis["missing_signs"],
            "duplicate_signs": analysis["duplicate_signs"],
        },
    }


def schedule_batch(
    account_key: str,
    platform: str,
    category: str,
    items: List[Dict[str, Any]],
    batch_id: Optional[str] = None,
    start_from: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Validate, generate captions, assign slots, and persist a batch of scheduled posts."""
    if category not in BATCH_CATEGORIES:
        raise ValueError(f"Unsupported category: {category}")

    if not items:
        raise ValueError("No videos provided in batch")

    for item in items:
        ok, err = validate_platform_media(
            platform=platform,
            filename=item["original_filename"],
            file_size_bytes=int(item.get("file_size_bytes", 0)),
            duration_seconds=item.get("duration_seconds"),
        )
        if not ok:
            raise ValueError(f"{item['original_filename']}: {err}")

    for item in items:
        if not item.get("zodiac_index"):
            detected = detect_zodiac_from_filename(item.get("original_filename", ""))
            if detected:
                item["zodiac_index"] = detected["index"]
                item["zodiac_tamil"] = detected["tamil"]
                item["zodiac_english"] = detected["english"]

    analysis = analyze_batch_items(items)
    sorted_items = analysis["items"]

    for item in sorted_items:
        z_idx = item.get("zodiac_index")
        if not z_idx or z_idx not in ZODIAC_BY_INDEX:
            raise ValueError(f"Missing zodiac sign for file: {item.get('original_filename')}")

    slot_times = _compute_next_available_slots(account_key, len(sorted_items), start_from=start_from)
    if len(slot_times) < len(sorted_items):
        raise RuntimeError("Could not find enough available posting slots")

    final_batch_id = batch_id or str(uuid.uuid4())[:8]
    conn = database.get_connection()
    cursor = conn.cursor()
    created_posts: List[Dict[str, Any]] = []

    for item, scheduled_at in zip(sorted_items, slot_times):
        z_idx = int(item["zodiac_index"])
        sign = ZODIAC_BY_INDEX[z_idx]
        gen = generate_caption_and_hashtags(z_idx, category)
        caption = item.get("caption") or gen["caption"]
        hashtags = item.get("hashtags") or gen["hashtags"]

        cursor.execute(
            """
            INSERT INTO scheduled_posts (
                batch_id, account_key, platform, zodiac_index, zodiac_tamil, zodiac_english,
                category, original_filename, media_path, thumbnail_path,
                caption, hashtags, scheduled_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'scheduled')
            """,
            (
                final_batch_id,
                account_key,
                platform.lower(),
                z_idx,
                sign["tamil"],
                sign["english"],
                category,
                item["original_filename"],
                item["media_path"],
                item.get("thumbnail_path"),
                caption,
                hashtags,
                scheduled_at,
            ),
        )
        post_id = cursor.lastrowid
        cursor.execute("SELECT * FROM scheduled_posts WHERE id = ?", (post_id,))
        created_posts.append(dict(cursor.fetchone()))

    conn.commit()
    conn.close()

    return {
        "batch_id": final_batch_id,
        "scheduled_count": len(created_posts),
        "posts": created_posts,
        "warnings": {
            "missing_signs": analysis["missing_signs"],
            "duplicate_signs": analysis["duplicate_signs"],
        },
    }


def get_scheduled_posts(
    account_key: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    conn = database.get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM scheduled_posts WHERE 1=1"
    params: List[Any] = []
    if account_key:
        query += " AND account_key = ?"
        params.append(account_key)
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY scheduled_at ASC, zodiac_index ASC"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def reschedule_video(video_id: str, new_scheduled_at: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Reschedule all pending destination jobs for a video_id to a shared new_scheduled_at."""
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scheduled_posts WHERE video_id = ?", (video_id,))
    jobs = [dict(r) for r in cursor.fetchall()]
    if not jobs:
        conn.close()
        return [], "Video jobs not found"

    pending_jobs = [j for j in jobs if j["status"] in ("scheduled", "failed", "retry_waiting", "auth_required")]
    if not pending_jobs:
        conn.close()
        return [], "No pending jobs to reschedule for this video"

    for job in pending_jobs:
        cursor.execute(
            """
            SELECT id FROM scheduled_posts
            WHERE account_key = ? AND scheduled_at = ? AND video_id != ? AND status IN ('scheduled', 'publishing')
            """,
            (job["account_key"], new_scheduled_at, video_id),
        )
        conflict = cursor.fetchone()
        if conflict:
            conn.close()
            return [], f"Slot conflict: another post (ID {conflict['id']}) is already scheduled at {new_scheduled_at} for {job['account_key']}"

    cursor.execute(
        """
        UPDATE scheduled_posts
        SET scheduled_at = ?, status = 'scheduled', error_message = NULL, error_category = NULL, next_retry_at = NULL, updated_at = CURRENT_TIMESTAMP
        WHERE video_id = ? AND status IN ('scheduled', 'failed', 'retry_waiting', 'auth_required')
        """,
        (new_scheduled_at, video_id),
    )
    conn.commit()
    cursor.execute("SELECT * FROM scheduled_posts WHERE video_id = ? ORDER BY id ASC", (video_id,))
    updated = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return updated, None


def reschedule_post(post_id: int, new_scheduled_at: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Reschedule a post to new_scheduled_at, checking for account slot conflicts."""
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scheduled_posts WHERE id = ?", (post_id,))
    post = cursor.fetchone()
    if not post:
        conn.close()
        return None, "Scheduled post not found"

    if post["status"] not in ("scheduled", "failed", "retry_waiting", "draft", "pending_approval"):
        conn.close()
        return None, f"Cannot reschedule post in status '{post['status']}'"

    cursor.execute(
        """
        SELECT id FROM scheduled_posts
        WHERE account_key = ? AND scheduled_at = ? AND id != ? AND status IN ('scheduled', 'publishing')
        """,
        (post["account_key"], new_scheduled_at, post_id),
    )
    conflict = cursor.fetchone()
    if conflict:
        conn.close()
        return None, f"Slot conflict: another post (ID {conflict['id']}) is already scheduled at {new_scheduled_at} for {post['account_key']}"

    cursor.execute(
        """
        UPDATE scheduled_posts
        SET scheduled_at = ?, status = 'scheduled', error_message = NULL, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (new_scheduled_at, post_id),
    )
    conn.commit()
    cursor.execute("SELECT * FROM scheduled_posts WHERE id = ?", (post_id,))
    updated = dict(cursor.fetchone())
    conn.close()
    return updated, None


def cancel_scheduled_post(post_id: int) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scheduled_posts WHERE id = ?", (post_id,))
    post = cursor.fetchone()
    if not post:
        conn.close()
        return None, "Scheduled post not found"

    if post["status"] in ("published", "published_safe_mode", "cancelled"):
        conn.close()
        return None, f"Post is already '{post['status']}'"

    cursor.execute(
        "UPDATE scheduled_posts SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (post_id,),
    )
    conn.commit()
    cursor.execute("SELECT * FROM scheduled_posts WHERE id = ?", (post_id,))
    updated = dict(cursor.fetchone())
    conn.close()
    return updated, None


MAX_PUBLISH_ATTEMPTS = 5


def classify_publishing_error(error_msg: str) -> Tuple[str, bool]:
    """Classify an error message into (error_category, is_retryable)."""
    msg = (error_msg or "").lower()
    if any(k in msg for k in ("expired", "invalid oauth", "401", "code 190", "session has expired")):
        return "auth_expired", False
    if any(k in msg for k in ("permission", "not authorized", "code 10", "code 200")):
        return "permission_denied", False
    if any(k in msg for k in ("missing or unreadable", "not found")):
        return "missing_media", False
    if any(k in msg for k in ("unsupported", "invalid media", "publicly accessible video_url", "exceeds")):
        return "invalid_media", False
    if any(k in msg for k in ("rate limit", "quota", "429", "too many requests")):
        return "rate_limit", True
    if any(k in msg for k in ("timeout", "connection", "network", "500", "502", "503", "504", "exception")):
        return "network_error", True
    return "transient_error", True


def recover_interrupted_jobs(now: Optional[datetime] = None) -> Dict[str, Any]:
    """Recover jobs left in active upload/processing states after an unexpected restart."""
    current_dt = now or datetime.now()
    now_iso = current_dt.strftime("%Y-%m-%dT%H:%M:%S")
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, attempt_count, status FROM scheduled_posts WHERE status IN ('preparing', 'uploading', 'processing', 'publishing')"
    )
    rows = cursor.fetchall()
    recovered = 0
    exhausted = 0
    for row in rows:
        if row["attempt_count"] >= MAX_PUBLISH_ATTEMPTS:
            cursor.execute(
                "UPDATE scheduled_posts SET status = 'failed', error_category = 'retry_exhausted', error_message = 'Max retry attempts reached after interruption', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (row["id"],),
            )
            exhausted += 1
        else:
            cursor.execute(
                "UPDATE scheduled_posts SET status = 'retry_waiting', next_retry_at = ?, error_category = 'interrupted', error_message = 'Recovered after restart', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (now_iso, row["id"]),
            )
            recovered += 1
    conn.commit()
    conn.close()
    return {"recovered": recovered, "exhausted": exhausted, "checked_at": now_iso}


def retry_scheduled_post(post_id: int) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Manually reset a failed/retry_waiting/auth_required job to scheduled."""
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scheduled_posts WHERE id = ?", (post_id,))
    post = cursor.fetchone()
    if not post:
        conn.close()
        return None, "Scheduled post not found"
    if post["status"] in ("published", "published_safe_mode", "cancelled"):
        conn.close()
        return None, f"Cannot retry post in status '{post['status']}'"
    cursor.execute(
        """
        UPDATE scheduled_posts
        SET status = 'scheduled', next_retry_at = NULL, error_message = NULL, error_category = NULL, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (post_id,),
    )
    conn.commit()
    cursor.execute("SELECT * FROM scheduled_posts WHERE id = ?", (post_id,))
    updated = dict(cursor.fetchone())
    conn.close()
    return updated, None


def run_pending_scheduled_posts(now: Optional[datetime] = None) -> Dict[str, Any]:
    """Execute due scheduled and retry_waiting posts with atomic claim and controlled retry policy."""
    current_dt = now or datetime.now()
    now_iso = current_dt.strftime("%Y-%m-%dT%H:%M:%S")
    settings = database.get_settings()
    safe_mode = settings.get("safe_test_mode", "true").lower() == "true"

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id FROM scheduled_posts
        WHERE (status = 'scheduled' AND scheduled_at <= ?)
           OR (status = 'retry_waiting' AND (next_retry_at IS NULL OR next_retry_at <= ?))
        ORDER BY scheduled_at ASC
        """,
        (now_iso, now_iso),
    )
    due_ids = [row["id"] for row in cursor.fetchall()]
    conn.close()

    processed = 0
    for post_id in due_ids:
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE scheduled_posts
            SET status = 'publishing', attempt_count = attempt_count + 1, last_attempt_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status IN ('scheduled', 'retry_waiting')
            """,
            (now_iso, post_id),
        )
        conn.commit()
        if cursor.rowcount == 0:
            conn.close()
            continue

        cursor.execute("SELECT * FROM scheduled_posts WHERE id = ?", (post_id,))
        post = dict(cursor.fetchone())
        try:
            adapter = get_platform_adapter(post["platform"])
            result = adapter.publish(post, safe_mode=safe_mode)
            if result.get("success"):
                cursor.execute(
                    """
                    UPDATE scheduled_posts
                    SET status = ?, external_post_id = ?, permalink = ?, published_at = ?,
                        upload_progress_pct = 100.0, error_message = NULL, error_category = NULL,
                        next_retry_at = NULL, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        result.get("status", "published_safe_mode"),
                        result.get("external_post_id"),
                        result.get("permalink"),
                        now_iso,
                        post_id,
                    ),
                )
            else:
                err_msg = result.get("error") or "Publishing failed"
                cat, retryable = classify_publishing_error(err_msg)
                attempts = int(post.get("attempt_count") or 1)
                if cat == "auth_expired":
                    new_status = "auth_required"
                    next_retry = None
                elif retryable and attempts < MAX_PUBLISH_ATTEMPTS:
                    new_status = "retry_waiting"
                    backoff_sec = min(3600, (2 ** attempts) * 60)
                    next_retry = (current_dt + timedelta(seconds=backoff_sec)).strftime("%Y-%m-%dT%H:%M:%S")
                else:
                    new_status = "failed"
                    next_retry = None
                cursor.execute(
                    """
                    UPDATE scheduled_posts
                    SET status = ?, error_category = ?, error_message = ?, next_retry_at = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (new_status, cat, err_msg, next_retry, post_id),
                )
        except Exception as exc:
            err_msg = str(exc)
            cat, retryable = classify_publishing_error(err_msg)
            attempts = int(post.get("attempt_count") or 1)
            if retryable and attempts < MAX_PUBLISH_ATTEMPTS:
                new_status = "retry_waiting"
                backoff_sec = min(3600, (2 ** attempts) * 60)
                next_retry = (current_dt + timedelta(seconds=backoff_sec)).strftime("%Y-%m-%dT%H:%M:%S")
            else:
                new_status = "failed"
                next_retry = None
            cursor.execute(
                """
                UPDATE scheduled_posts
                SET status = ?, error_category = ?, error_message = ?, next_retry_at = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (new_status, cat, err_msg, next_retry, post_id),
            )
        conn.commit()
        conn.close()
        processed += 1

    return {"processed": processed, "safe_mode": safe_mode, "checked_at": now_iso}


# ---------------------------------------------------------------------------
# Publishing Workspace Helpers (Buffer-style Queue / Drafts / Approvals / Sent)
# ---------------------------------------------------------------------------

QUEUE_STATUSES = ("scheduled", "publishing", "uploading", "processing", "retry_waiting", "auth_required", "failed")
SENT_STATUSES = ("published", "published_safe_mode")
DRAFT_STATUSES = ("draft",)
APPROVAL_STATUSES = ("pending_approval",)

SAFE_STATUS_TRANSITIONS = {
    "draft": {"scheduled", "pending_approval", "cancelled"},
    "pending_approval": {"scheduled", "draft", "cancelled"},
    "scheduled": {"draft", "pending_approval", "cancelled"},
    "retry_waiting": {"scheduled", "draft", "cancelled"},
    "failed": {"scheduled", "draft", "cancelled"},
    "auth_required": {"scheduled", "draft", "cancelled"},
    "cancelled": {"draft", "scheduled"},
}


def get_publishing_workspace(account_key: Optional[str] = None) -> Dict[str, Any]:
    """Return channels, dynamic tab counts, and scheduled_posts for the Publishing Workspace."""
    conn = database.get_connection()
    cursor = conn.cursor()

    # Connected accounts from accounts table
    cursor.execute("SELECT platform, account_id, account_name, is_active FROM accounts WHERE is_active = 1")
    active_accounts = {row["platform"]: dict(row) for row in cursor.fetchall()}

    # Posting schedule settings per account_key
    cursor.execute("SELECT account_key, timezone, weekly_goal FROM posting_schedule_settings")
    settings_map = {row["account_key"]: dict(row) for row in cursor.fetchall()}

    # Fetch all posts (non-cancelled by default, or include all for counts)
    cursor.execute("SELECT * FROM scheduled_posts ORDER BY scheduled_at ASC, zodiac_index ASC, id ASC")
    all_posts = [dict(r) for r in cursor.fetchall()]
    conn.close()

    default_channels = [
        {"account_key": "facebook:default", "platform": "facebook", "default_name": "Facebook Page"},
        {"account_key": "instagram:default", "platform": "instagram", "default_name": "Instagram Professional"},
        {"account_key": "youtube:default", "platform": "youtube", "default_name": "YouTube Channel"},
    ]

    channels = []
    for ch in default_channels:
        ak = ch["account_key"]
        plat = ch["platform"]
        acc_info = active_accounts.get(plat)
        ch_settings = settings_map.get(ak, {})
        ch_posts = [p for p in all_posts if p.get("account_key") == ak]
        queued_count = sum(1 for p in ch_posts if p.get("status") in QUEUE_STATUSES)
        published_count = sum(1 for p in ch_posts if p.get("status") in SENT_STATUSES)
        draft_count = sum(1 for p in ch_posts if p.get("status") in DRAFT_STATUSES)
        approval_count = sum(1 for p in ch_posts if p.get("status") in APPROVAL_STATUSES)
        failed_count = sum(1 for p in ch_posts if p.get("status") in ("failed", "retry_waiting", "auth_required"))

        channels.append({
            "account_key": ak,
            "platform": plat,
            "name": (acc_info.get("account_name") if acc_info else None) or ch["default_name"],
            "connected": bool(acc_info),
            "queued_count": queued_count,
            "published_count": published_count,
            "draft_count": draft_count,
            "approval_count": approval_count,
            "failed_count": failed_count,
            "weekly_goal": int(ch_settings.get("weekly_goal") or 14),
            "weekly_progress": published_count,
            "timezone": ch_settings.get("timezone") or "Asia/Kolkata",
        })

    filtered_posts = [p for p in all_posts if not account_key or account_key == "all" or p.get("account_key") == account_key]

    counts = {
        "queue": sum(1 for p in filtered_posts if p.get("status") in QUEUE_STATUSES),
        "drafts": sum(1 for p in filtered_posts if p.get("status") in DRAFT_STATUSES),
        "approvals": sum(1 for p in filtered_posts if p.get("status") in APPROVAL_STATUSES),
        "sent": sum(1 for p in filtered_posts if p.get("status") in SENT_STATUSES),
        "failed": sum(1 for p in filtered_posts if p.get("status") in ("failed", "retry_waiting", "auth_required")),
        "total": len(filtered_posts),
    }

    return {
        "channels": channels,
        "counts": counts,
        "posts": filtered_posts,
        "timezone": "Asia/Kolkata",
    }


def update_scheduled_post(post_id: int, updates: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Safely update post fields or transition status."""
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scheduled_posts WHERE id = ?", (post_id,))
    post = cursor.fetchone()
    if not post:
        conn.close()
        return None, "Scheduled post not found"

    current_status = post["status"]
    new_status = updates.get("status")
    if new_status and new_status != current_status:
        allowed = SAFE_STATUS_TRANSITIONS.get(current_status, set())
        if new_status not in allowed:
            conn.close()
            return None, f"Unsafe status transition from '{current_status}' to '{new_status}' is not allowed."

    fields = []
    params: List[Any] = []
    for col in ("caption", "hashtags", "category", "scheduled_at", "status"):
        if col in updates and updates[col] is not None:
            fields.append(f"{col} = ?")
            params.append(updates[col])

    if not fields:
        conn.close()
        return dict(post), None

    fields.append("updated_at = CURRENT_TIMESTAMP")
    params.append(post_id)
    cursor.execute(f"UPDATE scheduled_posts SET {', '.join(fields)} WHERE id = ?", params)
    conn.commit()
    cursor.execute("SELECT * FROM scheduled_posts WHERE id = ?", (post_id,))
    updated = dict(cursor.fetchone())
    conn.close()
    return updated, None


def publish_post_now(post_id: int) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Publish a post immediately, respecting safe_test_mode."""
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scheduled_posts WHERE id = ?", (post_id,))
    post = cursor.fetchone()
    if not post:
        conn.close()
        return None, "Scheduled post not found"

    if post["status"] in SENT_STATUSES:
        conn.close()
        return None, f"Post is already '{post['status']}'"

    safe_mode = str(database.get_settings().get("safe_test_mode", "true")).lower() == "true"
    now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    if safe_mode:
        mock_id = f"safe_mock_{post['platform']}_{post_id}"
        cursor.execute(
            """
            UPDATE scheduled_posts
            SET status = 'published_safe_mode',
                published_at = ?,
                external_post_id = ?,
                error_message = NULL,
                error_category = NULL,
                next_retry_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (now_iso, mock_id, post_id),
        )
        conn.commit()
        cursor.execute("SELECT * FROM scheduled_posts WHERE id = ?", (post_id,))
        row = cursor.fetchone()
        updated = dict(row) if row else dict(post)
        conn.close()
        return updated, None

    if str(database.get_settings().get("global_kill_switch", "false")).lower() == "true":
        conn.close()
        return None, "Emergency Stop (global_kill_switch) is active."

    adapter = get_platform_adapter(post["platform"])
    res = adapter.publish(dict(post), safe_mode=False)
    if res.get("success"):
        cursor.execute(
            """
            UPDATE scheduled_posts
            SET status = 'published',
                published_at = ?,
                external_post_id = ?,
                permalink = ?,
                error_message = NULL,
                error_category = NULL,
                next_retry_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (now_iso, res.get("external_post_id"), res.get("permalink"), post_id),
        )
        conn.commit()
        cursor.execute("SELECT * FROM scheduled_posts WHERE id = ?", (post_id,))
        row = cursor.fetchone()
        updated = dict(row) if row else dict(post)
        conn.close()
        return updated, None

    err_msg = res.get("error") or "Publish failed"
    cursor.execute(
        """
        UPDATE scheduled_posts
        SET status = 'failed',
            error_message = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (err_msg, post_id),
    )
    conn.commit()
    conn.close()
    return None, err_msg


def create_publishing_post(data: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Create a new draft, approval, or scheduled post in scheduled_posts."""
    account_key = data.get("account_key") or "facebook:default"
    platform = data.get("platform") or account_key.split(":")[0]
    status = data.get("status") or "draft"
    if status not in ("draft", "pending_approval", "scheduled"):
        return None, f"Invalid initial status '{status}'"

    now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    scheduled_at = data.get("scheduled_at") or now_iso
    caption = data.get("caption") or ""
    hashtags = data.get("hashtags") or ""
    category = data.get("category") or "General Astrology"
    original_filename = data.get("original_filename") or "custom_post.mp4"
    media_path = data.get("media_path") or ""

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO scheduled_posts (
            account_key, platform, zodiac_index, zodiac_tamil, zodiac_english,
            category, original_filename, media_path, caption, hashtags,
            scheduled_at, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account_key,
            platform,
            int(data.get("zodiac_index") or 0),
            data.get("zodiac_tamil") or "",
            data.get("zodiac_english") or "Custom",
            category,
            original_filename,
            media_path,
            caption,
            hashtags,
            scheduled_at,
            status,
        ),
    )
    post_id = cursor.lastrowid
    conn.commit()
    cursor.execute("SELECT * FROM scheduled_posts WHERE id = ?", (post_id,))
    created = dict(cursor.fetchone())
    conn.close()
    return created, None
