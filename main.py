"""FastAPI backend application for Gokul Social Publisher."""
import os
import json
import uuid
import asyncio
import logging
import urllib.parse
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

import database
from facebook_service import FacebookService
from instagram_service import InstagramService
from youtube_service import YouTubeService

logger = logging.getLogger(__name__)


async def _instagram_background_sync_loop():
    """Periodically syncs Instagram comments when Instagram Auto Reply is enabled."""
    while True:
        await asyncio.sleep(60)
        try:
            settings = database.get_settings()
            if settings.get("ig_auto_reply_enabled") == "true":
                InstagramService.sync_instagram_comments()
        except Exception as e:
            logger.error(f"Background Instagram sync error: {e}")


async def _youtube_background_sync_loop():
    """Periodically syncs YouTube comments when YouTube Auto Reply is enabled."""
    while True:
        await asyncio.sleep(60)
        try:
            settings = database.get_settings()
            if settings.get("yt_auto_reply_enabled") == "true":
                YouTubeService.sync_youtube_comments()
        except Exception as e:
            logger.error(f"Background YouTube sync error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task_ig = asyncio.create_task(_instagram_background_sync_loop())
    task_yt = asyncio.create_task(_youtube_background_sync_loop())
    try:
        yield
    finally:
        task_ig.cancel()
        task_yt.cancel()


app = FastAPI(title="Gokul Social Publisher", version="1.0.0", lifespan=lifespan)

# Initialize database
database.init_db()

# Mount static folder
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir, exist_ok=True)

class SettingUpdate(BaseModel):
    key: str
    value: str

class FacebookConnectManual(BaseModel):
    page_id: str
    page_name: str
    access_token: str

class FacebookConfigUpdate(BaseModel):
    app_id: str
    app_secret: str
    redirect_uri: str = "http://localhost:8088/api/facebook/callback"

class SelectPageRequest(BaseModel):
    session_id: str
    page_id: str

class FacebookOAuthExchange(BaseModel):
    app_id: str
    app_secret: str
    redirect_uri: str
    code: str

class SimulateCommentRequest(BaseModel):
    comment_id: str
    author_name: str
    author_id: str
    message: str
    post_id: str = "post_1001"

class InstagramConnectManual(BaseModel):
    account_id: str
    account_name: str = ""
    access_token: str

class SelectIgAccountRequest(BaseModel):
    session_id: str
    account_id: str

class YouTubeConnectManual(BaseModel):
    channel_id: str
    channel_name: str = ""
    access_token: str
    refresh_token: str = ""

class YouTubeConfigUpdate(BaseModel):
    client_id: str
    client_secret: str
    redirect_uri: str = "http://localhost:8088/api/youtube/callback"

class SelectYouTubeChannelRequest(BaseModel):
    session_id: str
    channel_id: str

@app.get("/api/status")
def get_status():
    settings = database.get_settings()
    conn = database.get_connection()
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) as count FROM accounts WHERE is_active = 1")
    accounts_count = c.fetchone()["count"]
    
    c.execute("SELECT COUNT(*) as count FROM activities")
    total_processed = c.fetchone()["count"]
    
    c.execute("SELECT COUNT(*) as count FROM activities WHERE status = 'replied'")
    total_replied = c.fetchone()["count"]
    
    c.execute("SELECT COUNT(*) as count FROM activities WHERE status = 'review_required'")
    pending_review = c.fetchone()["count"]
    
    conn.close()
    
    return {
        "status": "online",
        "auto_reply_enabled": settings.get("auto_reply_enabled") == "true",
        "ig_auto_reply_enabled": settings.get("ig_auto_reply_enabled", "false") == "true",
        "yt_auto_reply_enabled": settings.get("yt_auto_reply_enabled", "false") == "true",
        "safe_test_mode": settings.get("safe_test_mode") == "true",
        "stats": {
            "connected_accounts": accounts_count,
            "comments_processed": total_processed,
            "auto_replies_sent": total_replied,
            "pending_review": pending_review
        }
    }

@app.post("/api/settings")
def update_setting(update: SettingUpdate):
    if update.key not in ["auto_reply_enabled", "ig_auto_reply_enabled", "yt_auto_reply_enabled", "safe_test_mode", "global_kill_switch"]:
        raise HTTPException(status_code=400, detail="Invalid setting key")
    database.set_setting(update.key, update.value)
    return {"success": True, "key": update.key, "value": update.value}

@app.get("/api/accounts")
def get_accounts():
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("SELECT id, platform, account_id, account_name, is_active, connected_at FROM accounts ORDER BY id DESC")
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return {"accounts": rows}

@app.get("/api/activities")
def get_activities(limit: int = 50):
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM activities ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return {"activities": rows}

# --- Facebook Endpoints ---

@app.get("/api/facebook/config")
def get_facebook_config():
    """Returns Meta App ID and configuration status. App Secret is NEVER exposed."""
    creds = FacebookService.get_credentials()
    app_id = creds.get("app_id") or ""
    has_secret = bool(creds.get("app_secret"))
    # Mask App ID if present
    masked_id = (app_id[:4] + "..." + app_id[-4:]) if len(app_id) > 8 else app_id
    return {
        "configured": bool(app_id and has_secret),
        "app_id_configured": bool(app_id),
        "app_secret_configured": has_secret,
        "app_id_preview": masked_id,
        "redirect_uri": creds.get("redirect_uri")
    }

@app.post("/api/facebook/config")
def set_facebook_config(config: FacebookConfigUpdate):
    """Saves Meta App ID, Secret, and Redirect URI securely."""
    if not config.app_id.strip() or not config.app_secret.strip():
        raise HTTPException(status_code=400, detail="App ID and App Secret cannot be empty")
    FacebookService.save_credentials(config.app_id, config.app_secret, config.redirect_uri)
    return {"success": True, "message": "Meta App credentials stored securely."}

@app.get("/api/facebook/login")
def facebook_oauth_login(request: Request):
    """Initiates official Meta OAuth login dialog."""
    try:
        # Determine redirect URI dynamically if needed
        base_url = str(request.base_url).rstrip("/")
        # If running on localhost or 127.0.0.1
        creds = FacebookService.get_credentials()
        r_uri = creds.get("redirect_uri") or f"{base_url}/api/facebook/callback"
        auth_url = FacebookService.get_oauth_dialog_url(redirect_uri=r_uri)
        return RedirectResponse(auth_url)
    except ValueError as e:
        # Redirect to UI with error
        return RedirectResponse(f"/?fb_error={urllib.parse.quote(str(e))}")

@app.get("/api/facebook/callback")
def facebook_oauth_callback(
    code: str = None,
    state: str = None,
    error: str = None,
    error_reason: str = None,
    error_description: str = None
):
    """Handles official Meta OAuth redirect callback."""
    # 1. Error handling for cancelled login or denied permissions
    if error or error_reason or error_description:
        err_msg = error_description or error_reason or error or "Facebook login was cancelled or denied."
        return RedirectResponse(f"/?view=accounts&fb_error={urllib.parse.quote(err_msg)}")

    if not code:
        return RedirectResponse("/?view=accounts&fb_error=Missing+authorization+code+from+Meta")

    # 2. Exchange authorization code for token
    token_res = FacebookService.exchange_code_for_token(code)
    if "error" in token_res:
        err_text = token_res["error"].get("message", "Token exchange failed.")
        return RedirectResponse(f"/?view=accounts&fb_error={urllib.parse.quote(err_text)}")

    user_token = token_res.get("access_token")
    if not user_token:
        return RedirectResponse("/?view=accounts&fb_error=Did+not+receive+access+token+from+Meta")

    # 3. Retrieve user's Facebook Pages
    pages = FacebookService.get_user_pages(user_token)
    if not pages:
        return RedirectResponse(
            "/?view=accounts&fb_error=No+Facebook+Pages+found+under+this+account.+Please+ensure+you+are+a+Page+admin+and+granted+page+permissions."
        )

    # 4. Store authorized pages in temporary OAuth session
    session_id = str(uuid.uuid4())
    database.save_oauth_session(session_id, json.dumps(pages))

    # 5. Redirect user back to UI with session_id to select page
    return RedirectResponse(f"/?view=accounts&fb_session={session_id}")

@app.get("/api/facebook/session-pages")
def get_session_pages(session_id: str):
    """Returns list of authorized pages for the user to select from (tokens are NEVER exposed)."""
    session_data = database.get_oauth_session(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="OAuth session expired or not found")
    
    pages = json.loads(session_data)
    # Sanitize: return only id, name, category. Strip tokens completely.
    sanitized = [
        {"id": p.get("id"), "name": p.get("name"), "category": p.get("category", "")}
        for p in pages
    ]
    return {"pages": sanitized}

@app.post("/api/facebook/select-page")
def select_facebook_page(payload: SelectPageRequest):
    """Connects the user-selected page using the token stored in the OAuth session."""
    session_data = database.get_oauth_session(payload.session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="OAuth session expired or invalid")
    
    pages = json.loads(session_data)
    target_page = next((p for p in pages if p.get("id") == payload.page_id), None)
    if not target_page:
        raise HTTPException(status_code=404, detail="Selected page not found in OAuth session")
    
    page_id = target_page.get("id")
    page_name = target_page.get("name")
    page_token = target_page.get("access_token")
    
    if not page_id or not page_token:
        raise HTTPException(status_code=400, detail="Incomplete page data or missing Page Access Token")
    
    # Securely save to database
    FacebookService.connect_page(page_id, page_name, page_token)
    
    # Delete temporary session
    database.delete_oauth_session(payload.session_id)
    
    return {"success": True, "connected_page": {"id": page_id, "name": page_name}}

@app.get("/api/facebook/status")
def get_facebook_status():
    page = FacebookService.get_connected_page()
    if page:
        return {"connected": True, "page": page}
    
    # Check if there is an active pending OAuth session waiting for page selection
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("SELECT session_id, pages_data FROM oauth_sessions ORDER BY created_at DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    
    if row:
        session_id = row["session_id"]
        try:
            pages = json.loads(row["pages_data"])
            sanitized = [
                {"id": p.get("id"), "name": p.get("name"), "category": p.get("category", "")}
                for p in pages
            ]
            return {
                "connected": False,
                "pending_selection": True,
                "session_id": session_id,
                "pages": sanitized
            }
        except Exception:
            pass

    return {"connected": False, "page": None, "pending_selection": False}

@app.post("/api/facebook/connect")
def connect_facebook_page(payload: FacebookConnectManual):
    if not payload.page_id or not payload.access_token:
        raise HTTPException(status_code=400, detail="Page ID and Access Token are required")
    name = payload.page_name if payload.page_name else f"Page {payload.page_id}"
    res = FacebookService.connect_page(payload.page_id, name, payload.access_token)
    return res

@app.post("/api/facebook/oauth-exchange")
def oauth_exchange_facebook(payload: FacebookOAuthExchange):
    token_res = FacebookService.exchange_code_for_token(
        payload.app_id, payload.app_secret, payload.redirect_uri, payload.code
    )
    if "error" in token_res:
        raise HTTPException(status_code=400, detail=token_res["error"].get("message", "OAuth error"))
    user_token = token_res.get("access_token")
    pages = FacebookService.get_user_pages(user_token)
    return {"success": True, "pages": pages}

@app.post("/api/facebook/disconnect")
def disconnect_facebook():
    page = FacebookService.get_connected_page()
    if page:
        FacebookService.disconnect_page(page["account_id"])
    return {"success": True}

@app.post("/api/facebook/sync")
def sync_facebook():
    res = FacebookService.sync_facebook_comments()
    return res

@app.post("/api/facebook/simulate-comment")
def simulate_facebook_comment(sim: SimulateCommentRequest):
    """Processes a test comment locally through the exact deterministic pipeline without live API posting."""
    page = FacebookService.get_connected_page()
    page_id = page["account_id"] if page else "test_page_100"
    
    comment_data = {
        "id": sim.comment_id,
        "post_id": sim.post_id,
        "message": sim.message,
        "from": {
            "id": sim.author_id,
            "name": sim.author_name
        }
    }
    
    # Process comment
    result = FacebookService.process_and_reply_comment(comment_data, page_id=page_id, access_token=None)
    return {"success": True, "result": result}

# --- Instagram Endpoints ---

@app.get("/api/instagram/config")
def get_instagram_config():
    """Returns Meta App configuration status for Instagram OAuth. App Secret is NEVER exposed."""
    creds = InstagramService.get_credentials()
    app_id = creds.get("app_id") or ""
    has_secret = bool(creds.get("app_secret"))
    masked_id = (app_id[:4] + "..." + app_id[-4:]) if len(app_id) > 8 else app_id
    return {
        "configured": bool(app_id and has_secret),
        "app_id_configured": bool(app_id),
        "app_secret_configured": has_secret,
        "app_id_preview": masked_id,
        "redirect_uri": creds.get("redirect_uri"),
    }

@app.get("/api/instagram/login")
def instagram_oauth_login(request: Request):
    """Initiates official Meta OAuth login dialog with Instagram permissions."""
    try:
        creds = InstagramService.get_credentials()
        base_url = str(request.base_url).rstrip("/")
        r_uri = creds.get("redirect_uri") or f"{base_url}/api/instagram/callback"
        auth_url = InstagramService.get_oauth_dialog_url(redirect_uri=r_uri)
        return RedirectResponse(auth_url)
    except ValueError as e:
        return RedirectResponse(f"/?view=accounts&ig_error={urllib.parse.quote(str(e))}")

@app.get("/api/instagram/callback")
def instagram_oauth_callback(
    code: str = None,
    state: str = None,
    error: str = None,
    error_reason: str = None,
    error_description: str = None,
):
    """Handles official Meta OAuth redirect callback for Instagram Professional accounts."""
    if error or error_reason or error_description:
        err_msg = error_description or error_reason or error or "Instagram login was cancelled or denied."
        return RedirectResponse(f"/?view=accounts&ig_error={urllib.parse.quote(err_msg)}")

    if not code:
        return RedirectResponse("/?view=accounts&ig_error=Missing+authorization+code+from+Meta")

    token_res = InstagramService.exchange_code_for_token(code)
    if "error" in token_res:
        err_text = token_res["error"].get("message", "Token exchange failed.")
        return RedirectResponse(f"/?view=accounts&ig_error={urllib.parse.quote(err_text)}")

    user_token = token_res.get("access_token")
    if not user_token:
        return RedirectResponse("/?view=accounts&ig_error=Did+not+receive+access+token+from+Meta")

    ig_res = InstagramService.get_instagram_accounts(user_token)
    if ig_res.get("error"):
        return RedirectResponse(f"/?view=accounts&ig_error={urllib.parse.quote(ig_res['error'])}")

    accounts = ig_res.get("accounts", [])
    if not accounts:
        return RedirectResponse(
            "/?view=accounts&ig_error=No+Instagram+Professional+account+found.+Ensure+your+Instagram+Business+or+Creator+account+is+linked+to+a+Facebook+Page+and+permissions+were+granted."
        )

    session_id = f"ig_{uuid.uuid4()}"
    database.save_oauth_session(session_id, json.dumps(accounts))
    return RedirectResponse(f"/?view=accounts&ig_session={session_id}")

@app.get("/api/instagram/session-accounts")
def get_ig_session_accounts(session_id: str):
    """Returns authorized Instagram Professional accounts for selection (tokens are NEVER exposed)."""
    session_data = database.get_oauth_session(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Instagram OAuth session expired or not found")

    accounts = json.loads(session_data)
    sanitized = [
        {
            "id": a.get("id"),
            "name": a.get("name"),
            "username": a.get("username", ""),
            "page_name": a.get("page_name", ""),
        }
        for a in accounts
    ]
    return {"accounts": sanitized}

@app.post("/api/instagram/select-account")
def select_instagram_account(payload: SelectIgAccountRequest):
    """Connects the selected Instagram Professional account using the token stored in the OAuth session."""
    session_data = database.get_oauth_session(payload.session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Instagram OAuth session expired or invalid")

    accounts = json.loads(session_data)
    target = next((a for a in accounts if a.get("id") == payload.account_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Selected Instagram account not found in OAuth session")

    account_id = target.get("id")
    account_name = target.get("name")
    access_token = target.get("access_token")
    if not account_id or not access_token:
        raise HTTPException(status_code=400, detail="Incomplete Instagram account data or missing Access Token")

    InstagramService.connect_account(account_id, account_name, access_token)
    database.delete_oauth_session(payload.session_id)
    return {"success": True, "connected_account": {"id": account_id, "name": account_name}}

@app.get("/api/instagram/status")
def get_instagram_status():
    account = InstagramService.get_connected_account()
    if account:
        return {"connected": True, "account": account}

    conn = database.get_connection()
    c = conn.cursor()
    c.execute("SELECT session_id, pages_data FROM oauth_sessions WHERE session_id LIKE 'ig_%' ORDER BY created_at DESC LIMIT 1")
    row = c.fetchone()
    conn.close()

    if row:
        try:
            accounts = json.loads(row["pages_data"])
            sanitized = [
                {"id": a.get("id"), "name": a.get("name"), "username": a.get("username", "")}
                for a in accounts
            ]
            return {
                "connected": False,
                "pending_selection": True,
                "session_id": row["session_id"],
                "accounts": sanitized,
            }
        except Exception:
            pass

    return {"connected": False, "account": None, "pending_selection": False}

@app.post("/api/instagram/connect")
def connect_instagram_manual(payload: InstagramConnectManual):
    if not payload.account_id.strip() or not payload.access_token.strip():
        raise HTTPException(status_code=400, detail="Instagram Account ID and Access Token are required")
    name = payload.account_name.strip() or f"IG {payload.account_id.strip()}"
    return InstagramService.connect_account(payload.account_id.strip(), name, payload.access_token.strip())

@app.post("/api/instagram/disconnect")
def disconnect_instagram():
    account = InstagramService.get_connected_account()
    if account:
        InstagramService.disconnect_account(account["account_id"])
    return {"success": True}

@app.post("/api/instagram/sync")
def sync_instagram():
    return InstagramService.sync_instagram_comments()

@app.post("/api/instagram/simulate-comment")
def simulate_instagram_comment(sim: SimulateCommentRequest):
    """Processes a test Instagram comment locally without live API posting."""
    account = InstagramService.get_connected_account()
    ig_user_id = account["account_id"] if account else "test_ig_100"
    ig_username = InstagramService._extract_username(account["account_name"]) if account else None

    comment_data = {
        "id": sim.comment_id,
        "post_id": sim.post_id,
        "text": sim.message,
        "username": sim.author_name,
        "from": {
            "id": sim.author_id,
            "username": sim.author_name,
        },
    }
    result = InstagramService.process_and_reply_comment(
        comment_data,
        ig_user_id=ig_user_id,
        ig_username=ig_username,
        access_token=None,
    )
    return {"success": True, "result": result}

# --- YouTube Endpoints ---

@app.get("/api/youtube/config")
def get_youtube_config():
    """Returns Google OAuth Client configuration status. Client Secret is NEVER exposed."""
    creds = YouTubeService.get_credentials()
    client_id = creds.get("client_id") or ""
    has_secret = bool(creds.get("client_secret"))
    masked_id = (client_id[:4] + "..." + client_id[-4:]) if len(client_id) > 8 else client_id
    return {
        "configured": bool(client_id and has_secret),
        "client_id_configured": bool(client_id),
        "client_secret_configured": has_secret,
        "client_id_preview": masked_id,
        "redirect_uri": creds.get("redirect_uri"),
    }

@app.post("/api/youtube/config")
def set_youtube_config(config: YouTubeConfigUpdate):
    """Saves Google OAuth Client ID, Secret, and Redirect URI securely."""
    if not config.client_id.strip() or not config.client_secret.strip():
        raise HTTPException(status_code=400, detail="Client ID and Client Secret cannot be empty")
    YouTubeService.save_credentials(config.client_id, config.client_secret, config.redirect_uri)
    return {"success": True, "message": "Google Client credentials stored securely."}

@app.get("/api/youtube/login")
def youtube_oauth_login(request: Request):
    """Initiates official Google OAuth 2.0 authorization dialog."""
    try:
        creds = YouTubeService.get_credentials()
        base_url = str(request.base_url).rstrip("/")
        r_uri = creds.get("redirect_uri") or f"{base_url}/api/youtube/callback"
        auth_url = YouTubeService.get_oauth_dialog_url(redirect_uri=r_uri)
        return RedirectResponse(auth_url)
    except ValueError as e:
        return RedirectResponse(f"/?view=accounts&yt_error={urllib.parse.quote(str(e))}")

@app.get("/api/youtube/callback")
def youtube_oauth_callback(
    code: str = None,
    state: str = None,
    error: str = None,
    error_description: str = None,
):
    """Handles official Google OAuth 2.0 redirect callback for YouTube channels."""
    if error or error_description:
        err_msg = error_description or error or "Google OAuth login was cancelled or denied."
        return RedirectResponse(f"/?view=accounts&yt_error={urllib.parse.quote(err_msg)}")

    if not code:
        return RedirectResponse("/?view=accounts&yt_error=Missing+authorization+code+from+Google")

    token_res = YouTubeService.exchange_code_for_token(code)
    if "error" in token_res:
        err_text = token_res["error"].get("message", "Token exchange failed.")
        return RedirectResponse(f"/?view=accounts&yt_error={urllib.parse.quote(err_text)}")

    access_token = token_res.get("access_token")
    refresh_token = token_res.get("refresh_token", "")
    if not access_token:
        return RedirectResponse("/?view=accounts&yt_error=Did+not+receive+access+token+from+Google")

    ch_res = YouTubeService.get_channel_details(access_token)
    if ch_res.get("error"):
        return RedirectResponse(f"/?view=accounts&yt_error={urllib.parse.quote(ch_res['error'])}")

    channels = ch_res.get("channels", [])
    if not channels:
        return RedirectResponse(
            "/?view=accounts&yt_error=No+YouTube+channel+found+for+this+Google+account.+Please+ensure+you+have+created+a+YouTube+channel."
        )

    # Attach token information to channels data for session storage
    session_channels = []
    for ch in channels:
        session_channels.append({
            "id": ch["id"],
            "title": ch["title"],
            "custom_url": ch.get("custom_url", ""),
            "uploads_playlist_id": ch.get("uploads_playlist_id", ""),
            "access_token": access_token,
            "refresh_token": refresh_token,
        })

    session_id = f"yt_{uuid.uuid4()}"
    database.save_oauth_session(session_id, json.dumps(session_channels))
    return RedirectResponse(f"/?view=accounts&yt_session={session_id}")

@app.get("/api/youtube/session-channels")
def get_yt_session_channels(session_id: str):
    """Returns authorized YouTube channels for selection (tokens are NEVER exposed)."""
    session_data = database.get_oauth_session(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="YouTube OAuth session expired or not found")

    channels = json.loads(session_data)
    sanitized = [
        {
            "id": c.get("id"),
            "title": c.get("title"),
            "custom_url": c.get("custom_url", ""),
        }
        for c in channels
    ]
    return {"channels": sanitized}

@app.post("/api/youtube/select-channel")
def select_youtube_channel(payload: SelectYouTubeChannelRequest):
    """Connects the selected YouTube channel using credentials stored in the OAuth session."""
    session_data = database.get_oauth_session(payload.session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="YouTube OAuth session expired or invalid")

    channels = json.loads(session_data)
    target = next((c for c in channels if c.get("id") == payload.channel_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Selected YouTube channel not found in OAuth session")

    channel_id = target.get("id")
    channel_title = target.get("title")
    access_token = target.get("access_token")
    refresh_token = target.get("refresh_token", "")
    uploads_playlist_id = target.get("uploads_playlist_id", "")
    if not channel_id or not access_token:
        raise HTTPException(status_code=400, detail="Incomplete YouTube channel data or missing Access Token")

    YouTubeService.connect_account(
        account_id=channel_id,
        account_name=channel_title,
        access_token=access_token,
        refresh_token=refresh_token,
        uploads_playlist_id=uploads_playlist_id,
    )
    database.delete_oauth_session(payload.session_id)
    return {"success": True, "connected_channel": {"id": channel_id, "title": channel_title}}

@app.get("/api/youtube/status")
def get_youtube_status():
    """Returns status of connected YouTube channel. Access tokens are NEVER exposed."""
    account = YouTubeService.get_connected_account()
    if account:
        return {"connected": True, "account": account}

    conn = database.get_connection()
    c = conn.cursor()
    c.execute("SELECT session_id, pages_data FROM oauth_sessions WHERE session_id LIKE 'yt_%' ORDER BY created_at DESC LIMIT 1")
    row = c.fetchone()
    conn.close()

    if row:
        try:
            channels = json.loads(row["pages_data"])
            sanitized = [
                {"id": ch.get("id"), "title": ch.get("title"), "custom_url": ch.get("custom_url", "")}
                for ch in channels
            ]
            return {
                "connected": False,
                "pending_selection": True,
                "session_id": row["session_id"],
                "channels": sanitized,
            }
        except Exception:
            pass

    return {"connected": False, "account": None, "pending_selection": False}

@app.post("/api/youtube/connect")
def connect_youtube_manual(payload: YouTubeConnectManual):
    """Manually connects a YouTube channel with given credentials."""
    if not payload.channel_id.strip() or not payload.access_token.strip():
        raise HTTPException(status_code=400, detail="Channel ID and Access Token are required")
    name = payload.channel_name.strip() or f"Channel {payload.channel_id.strip()}"
    return YouTubeService.connect_account(
        account_id=payload.channel_id.strip(),
        account_name=name,
        access_token=payload.access_token.strip(),
        refresh_token=payload.refresh_token.strip() or None,
    )

@app.post("/api/youtube/disconnect")
def disconnect_youtube():
    """Disconnects the active YouTube channel."""
    account = YouTubeService.get_connected_account()
    if account:
        YouTubeService.disconnect_account(account["account_id"])
    return {"success": True}

@app.post("/api/youtube/sync")
def sync_youtube():
    """Triggers immediate comment synchronization and automatic reply processing for YouTube."""
    return YouTubeService.sync_youtube_comments()

@app.post("/api/youtube/simulate-comment")
def simulate_youtube_comment(sim: SimulateCommentRequest):
    """Processes a test YouTube comment locally without live API posting."""
    account = YouTubeService.get_connected_account()
    channel_id = account["account_id"] if account else "test_yt_channel_100"
    channel_title = account["account_name"] if account else "My YouTube Channel"

    comment_data = {
        "id": sim.comment_id,
        "post_id": sim.post_id,
        "text": sim.message,
        "author_name": sim.author_name,
        "author_channel_id": sim.author_id,
    }
    result = YouTubeService.process_and_reply_comment(
        comment_data,
        channel_id=channel_id,
        channel_title=channel_title,
        access_token=None,
    )
    return {"success": True, "result": result}


# --- Approval Queue API (Priority 2A) ---

class ApprovalEditRequest(BaseModel):
    edited_reply: str


class ApprovalApproveRequest(BaseModel):
    edited_reply: Optional[str] = None


class ApprovalRejectRequest(BaseModel):
    reason: Optional[str] = None


@app.get("/api/approval-queue")
def list_approval_queue(
    status: Optional[str] = "pending",
    platform: Optional[str] = None,
    limit: int = 100,
):
    """Retrieve pending (or filtered) approval queue items."""
    items = database.get_approval_queue(status=status, platform=platform, limit=limit)
    return {"items": items, "count": len(items)}


@app.get("/api/approval-queue/history")
def list_approval_queue_history(
    platform: Optional[str] = None,
    limit: int = 100,
):
    """Retrieve non-pending approval queue history."""
    items = database.get_approval_queue_history(platform=platform, limit=limit)
    return {"items": items, "count": len(items)}


@app.get("/api/approval-queue/{queue_id}")
def get_approval_queue_detail(queue_id: int):
    """Retrieve details for a single approval queue item."""
    item = database.get_approval_queue_item(queue_id)
    if not item:
        raise HTTPException(status_code=404, detail="Approval queue item not found")
    return {"item": item}


@app.put("/api/approval-queue/{queue_id}/edit")
def edit_approval_queue_reply(queue_id: int, payload: ApprovalEditRequest):
    """Edit the suggested reply for a pending or approved queue item."""
    if not payload.edited_reply or not payload.edited_reply.strip():
        raise HTTPException(status_code=400, detail="edited_reply cannot be empty")
    ok, err, item = database.update_approval_reply(queue_id, payload.edited_reply.strip())
    if err == "not_found":
        raise HTTPException(status_code=404, detail="Approval queue item not found")
    if not ok:
        raise HTTPException(status_code=400, detail=err)
    return {"success": True, "item": item}


@app.post("/api/approval-queue/{queue_id}/validate-publish")
def validate_approval_queue_publish(queue_id: int):
    """Validate whether an approved queue item is eligible for future publishing.

    Does NOT publish publicly in Priority 2C.
    """
    result = database.validate_approved_item_for_publishing(queue_id)
    if result.get("reason") == "not_found":
        raise HTTPException(status_code=404, detail="Approval queue item not found")
    return result


@app.get("/api/approval-queue/activity-log/entries")
def list_approval_activity_log(
    approval_queue_id: Optional[int] = None,
    platform: Optional[str] = None,
    limit: int = 100,
):
    """Retrieve approval workflow activity log entries."""
    entries = database.get_approval_activity_log(
        approval_queue_id=approval_queue_id, platform=platform, limit=limit
    )
    return {"entries": entries, "count": len(entries)}


@app.post("/api/approval-queue/{queue_id}/approve")
def approve_approval_queue_item(
    queue_id: int, payload: Optional[ApprovalApproveRequest] = None
):
    """Approve a pending queue item. Does not publish while Safe Testing Mode is ON."""
    edited_reply = payload.edited_reply.strip() if payload and payload.edited_reply else None
    ok, err, item = database.approve_approval_item(queue_id, edited_reply=edited_reply)
    if err == "not_found":
        raise HTTPException(status_code=404, detail="Approval queue item not found")
    if not ok:
        raise HTTPException(status_code=400, detail=err)
    settings = database.get_settings()
    safe_test_mode = settings.get("safe_test_mode", "true") == "true"
    return {
        "success": True,
        "item": item,
        "published": False,
        "safe_test_mode": safe_test_mode,
    }


@app.post("/api/approval-queue/{queue_id}/reject")
def reject_approval_queue_item(
    queue_id: int, payload: Optional[ApprovalRejectRequest] = None
):
    """Reject a pending or approved queue item."""
    reason = payload.reason.strip() if payload and payload.reason else None
    ok, err, item = database.reject_approval_item(queue_id, reason=reason)
    if err == "not_found":
        raise HTTPException(status_code=404, detail="Approval queue item not found")
    if not ok:
        raise HTTPException(status_code=400, detail=err)
    return {"success": True, "item": item}


@app.post("/api/approval-queue/{queue_id}/prepare-publish")
def prepare_approval_queue_publish(queue_id: int):
    """Prepare safe publishing for one approved queue item (Priority 2D, no external dispatch)."""
    result = database.prepare_publishing_for_item(queue_id)
    if result.get("reason") == "not_found":
        raise HTTPException(status_code=404, detail="Approval queue item not found")
    return result


@app.get("/api/publishing-attempts")
def list_publishing_attempts(
    approval_queue_id: Optional[int] = None,
    platform: Optional[str] = None,
    limit: int = 100,
):
    """Retrieve publishing attempt history."""
    attempts = database.get_publishing_attempts(
        approval_queue_id=approval_queue_id, platform=platform, limit=limit
    )
    return {"attempts": attempts, "count": len(attempts)}


@app.get("/api/approval-queue/{queue_id}/publishing-status")
def get_approval_queue_publishing_status(queue_id: int):
    """Retrieve the latest publishing status for a queue item."""
    item = database.get_approval_queue_item(queue_id)
    if not item:
        raise HTTPException(status_code=404, detail="Approval queue item not found")
    latest = database.get_latest_publishing_status(queue_id)
    return {"queue_id": queue_id, "latest_attempt": latest}


class PlatformHybridSettingsUpdate(BaseModel):
    auto_reply_enabled: Optional[bool] = None
    praise_enabled: Optional[bool] = None
    emoji_enabled: Optional[bool] = None
    manual_queue_enabled: Optional[bool] = None
    enabled_templates: Optional[list[str]] = None


@app.get("/api/platform-settings")
def get_platform_settings():
    """Retrieve independent hybrid auto-reply settings and connection status for all platforms."""
    all_cfg = database.get_all_platform_hybrid_settings()
    conn = database.get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT platform, account_id, account_name FROM accounts WHERE is_active = 1")
        active_by_platform = {}
        for r in c.fetchall():
            active_by_platform.setdefault(r["platform"], []).append(
                {"account_id": r["account_id"], "account_name": r["account_name"]}
            )
    finally:
        conn.close()
    for p, cfg in all_cfg.items():
        accts = active_by_platform.get(p, [])
        cfg["connected"] = len(accts) > 0
        cfg["accounts"] = accts
    return {"platforms": all_cfg}


@app.put("/api/platform-settings/{platform}")
def update_platform_settings(platform: str, payload: PlatformHybridSettingsUpdate):
    """Update hybrid auto-reply settings for one platform without affecting others."""
    if platform not in ("facebook", "instagram", "youtube"):
        raise HTTPException(status_code=404, detail="Unsupported platform")
    try:
        updated = database.update_platform_hybrid_settings(
            platform,
            auto_reply_enabled=payload.auto_reply_enabled,
            praise_enabled=payload.praise_enabled,
            emoji_enabled=payload.emoji_enabled,
            manual_queue_enabled=payload.manual_queue_enabled,
            enabled_templates=payload.enabled_templates,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"success": True, "platform": platform, "settings": updated}


# --- Priority 2F: Unified Activity, Notifications & Dashboard Summary ---

@app.get("/api/activity/timeline")
def get_activity_timeline(
    platform: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
):
    """Retrieve unified activity timeline across Facebook, Instagram, and YouTube."""
    entries = database.get_unified_activity_timeline(
        platform=platform, status_filter=status, search=search, limit=limit
    )
    return {"entries": entries, "count": len(entries)}


@app.get("/api/notifications")
def list_notifications(unread_only: bool = False, limit: int = 50):
    """Retrieve persistent in-app notifications and unread count."""
    return database.get_notifications(unread_only=unread_only, limit=limit)


@app.post("/api/notifications/{notification_id}/read")
def mark_notification_as_read(notification_id: int):
    """Mark a single notification as read."""
    ok = database.mark_notification_read(notification_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"success": True, "notification_id": notification_id}


@app.post("/api/notifications/read-all")
def mark_all_notifications_as_read():
    """Mark all unread notifications as read."""
    updated = database.mark_all_notifications_read()
    return {"success": True, "updated": updated}


@app.get("/api/dashboard/summary")
def get_dashboard_summary_endpoint():
    """Retrieve live operational summary counts for the Dashboard."""
    return database.get_dashboard_summary()


# Serve frontend
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def serve_home():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Gokul Social Publisher API is running. UI loading..."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8088, reload=False)
