"""FastAPI backend application for Gokul Social Publisher."""
import os
import json
import uuid
import asyncio
import logging
import urllib.parse
from contextlib import asynccontextmanager
from typing import List, Optional
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

import database
import media_server
import scheduler_service
import sync_service
from facebook_service import FacebookService
from instagram_service import InstagramService
from youtube_service import YouTubeService

logger = logging.getLogger(__name__)


def _run_fb_sync_if_enabled():
    settings = database.get_settings()
    if settings.get("auto_reply_enabled") == "true":
        FacebookService.sync_facebook_comments()


def _run_ig_sync_if_enabled():
    settings = database.get_settings()
    if settings.get("ig_auto_reply_enabled") == "true":
        InstagramService.sync_instagram_comments()


def _run_yt_sync_if_enabled():
    settings = database.get_settings()
    if settings.get("yt_auto_reply_enabled") == "true":
        YouTubeService.sync_youtube_comments()


async def _facebook_background_sync_loop():
    """Periodically syncs Facebook comments when Facebook Auto Reply is enabled."""
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(_run_fb_sync_if_enabled)
        except Exception as e:
            logger.error(f"Background Facebook sync error: {e}")


async def _instagram_background_sync_loop():
    """Periodically syncs Instagram comments when Instagram Auto Reply is enabled."""
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(_run_ig_sync_if_enabled)
        except Exception as e:
            logger.error(f"Background Instagram sync error: {e}")


async def _youtube_background_sync_loop():
    """Periodically syncs YouTube comments when YouTube Auto Reply is enabled."""
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(_run_yt_sync_if_enabled)
        except Exception as e:
            logger.error(f"Background YouTube sync error: {e}")


async def _auto_post_scheduler_loop():
    """Periodically checks and executes due scheduled posts."""
    while True:
        await asyncio.sleep(30)
        try:
            await asyncio.to_thread(scheduler_service.run_pending_scheduled_posts)
        except Exception as e:
            logger.error(f"Auto Post Scheduler loop error: {e}")


async def _comment_sync_worker_loop():
    """Single background worker checking due 30-minute account comment syncs."""
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(sync_service.run_due_syncs)
        except Exception as e:
            logger.error(f"Comment sync worker error: {e}")


async def _queued_reply_worker_loop():
    """Periodically dispatches queued manual replies respecting the 120s anti-spam interval."""
    while True:
        await asyncio.sleep(15)
        try:
            await asyncio.to_thread(database.process_queued_manual_replies)
        except Exception as e:
            logger.error(f"Queued reply worker error: {e}")


_startup_recovery_lock = asyncio.Lock()


def run_startup_recovery():
    """Run startup recovery safely after DB initialization, before scheduler loop starts."""
    try:
        result = scheduler_service.recover_interrupted_jobs()
        sync_service.run_startup_sync_recovery()
        logger.info(
            "Startup recovery completed: recovered=%s exhausted=%s checked_at=%s",
            result.get("recovered", 0),
            result.get("exhausted", 0),
            result.get("checked_at"),
        )
        return result
    except Exception as e:
        logger.exception("Startup recovery failed; continuing application startup: %s", e)
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    async with _startup_recovery_lock:
        run_startup_recovery()
    task_fb = asyncio.create_task(_facebook_background_sync_loop())
    task_ig = asyncio.create_task(_instagram_background_sync_loop())
    task_yt = asyncio.create_task(_youtube_background_sync_loop())
    task_autopost = asyncio.create_task(_auto_post_scheduler_loop())
    task_sync = asyncio.create_task(_comment_sync_worker_loop())
    task_qreply = asyncio.create_task(_queued_reply_worker_loop())
    try:
        yield
    finally:
        task_fb.cancel()
        task_ig.cancel()
        task_yt.cancel()
        task_autopost.cancel()
        task_sync.cancel()
        task_qreply.cancel()


app = FastAPI(title="Gokul Social Publisher", version="1.0.0", lifespan=lifespan)

# Initialize database
database.init_db()

# Mount static folder
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir, exist_ok=True)


@app.api_route("/api/media/temp/{token}", methods=["GET", "HEAD"])
def serve_temp_media_endpoint(token: str, request: Request):
    """Serve temporary Instagram Reels media directly from the main app."""
    return media_server.serve_temp_media(token, request)

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
    
    c.execute("SELECT COUNT(*) as count FROM approval_queue WHERE status = 'pending'")
    pending_review = c.fetchone()["count"]
    
    conn.close()
    
    return {
        "status": "online",
        "auto_reply_enabled": settings.get("auto_reply_enabled") == "true",
        "ig_auto_reply_enabled": settings.get("ig_auto_reply_enabled", "false") == "true",
        "yt_auto_reply_enabled": settings.get("yt_auto_reply_enabled", "false") == "true",
        "safe_test_mode": settings.get("safe_test_mode") == "true",
        "global_kill_switch": settings.get("global_kill_switch", "false") == "true",
        "ui_theme": settings.get("ui_theme", "dark"),
        "stats": {
            "connected_accounts": accounts_count,
            "comments_processed": total_processed,
            "auto_replies_sent": total_replied,
            "pending_review": pending_review
        }
    }

@app.post("/api/settings")
def update_setting(update: SettingUpdate):
    if update.key not in ["auto_reply_enabled", "ig_auto_reply_enabled", "yt_auto_reply_enabled", "safe_test_mode", "global_kill_switch", "ui_theme"]:
        raise HTTPException(status_code=400, detail="Invalid setting key")
    if update.key == "ui_theme" and update.value not in ("light", "dark"):
        raise HTTPException(status_code=400, detail="ui_theme must be 'light' or 'dark'")
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

    expected_state = database.get_settings().get("yt_oauth_csrf_state")
    if expected_state and state is not None and state != expected_state:
        return RedirectResponse("/?view=accounts&yt_error=Invalid+OAuth+state+parameter")

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


@app.post("/api/approval-queue/{queue_id}/ignore")
def ignore_approval_queue_item(queue_id: int):
    """Ignore a pending or manual_followup queue item."""
    ok, err, item = database.ignore_approval_item(queue_id)
    if err == "not_found":
        raise HTTPException(status_code=404, detail="Approval queue item not found")
    if not ok:
        raise HTTPException(status_code=400, detail=err)
    return {"success": True, "item": item}


@app.post("/api/approval-queue/{queue_id}/manual-followup")
def manual_followup_approval_queue_item(queue_id: int):
    """Mark a pending queue item for manual follow-up."""
    ok, err, item = database.mark_manual_followup_item(queue_id)
    if err == "not_found":
        raise HTTPException(status_code=404, detail="Approval queue item not found")
    if not ok:
        raise HTTPException(status_code=400, detail=err)
    return {"success": True, "item": item}


@app.post("/api/approval-queue/{queue_id}/regenerate")
def regenerate_approval_queue_item(queue_id: int):
    """Regenerate a personalized reply suggestion for a pending/manual_followup item."""
    ok, err, item = database.regenerate_approval_item(queue_id)
    if err == "not_found":
        raise HTTPException(status_code=404, detail="Approval queue item not found")
    if not ok:
        raise HTTPException(status_code=400, detail=err)
    return {"success": True, "item": item}


@app.post("/api/approval-queue/sync")
def sync_approval_queue_from_activities():
    """Idempotently backfill eligible review_required activities into approval_queue."""
    result = database.sync_review_required_to_approval_queue()
    return {"success": True, **result}


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


# ==============================================================================
# Smart Lead Management Endpoints (GSP V2.0 - Phase 2.0A)
# ==============================================================================

class LeadCreateRequest(BaseModel):
    business_type: str
    platform: str
    account_id: str
    source_comment_id: str
    customer_name: Optional[str] = None
    customer_username: Optional[str] = None
    customer_contact: Optional[str] = None
    enquiry_category: str
    original_message: str
    detected_language: Optional[str] = None
    lead_status: str = "New"
    priority: str = "Medium"
    internal_notes: Optional[str] = None
    next_follow_up_at: Optional[str] = None


class LeadUpdateRequest(BaseModel):
    business_type: Optional[str] = None
    lead_status: Optional[str] = None
    priority: Optional[str] = None
    internal_notes: Optional[str] = None
    customer_contact: Optional[str] = None
    next_follow_up_at: Optional[str] = None
    last_contacted_at: Optional[str] = None
    converted_at: Optional[str] = None
    enquiry_category: Optional[str] = None
    follow_up_completed: Optional[bool] = None


def _validate_lead_create(req: LeadCreateRequest) -> None:
    if req.business_type not in database.VALID_BUSINESS_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid business_type. Must be one of: {database.VALID_BUSINESS_TYPES}")
    if req.platform.lower() not in database.VALID_LEAD_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Invalid platform. Must be one of: {database.VALID_LEAD_PLATFORMS}")
    if not req.account_id or not req.account_id.strip():
        raise HTTPException(status_code=400, detail="account_id is required")
    if not req.source_comment_id or not req.source_comment_id.strip():
        raise HTTPException(status_code=400, detail="source_comment_id is required")
    if not req.original_message or not req.original_message.strip():
        raise HTTPException(status_code=400, detail="original_message is required")
    if req.enquiry_category not in database.VALID_ENQUIRY_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid enquiry_category. Must be one of: {database.VALID_ENQUIRY_CATEGORIES}")
    if req.lead_status not in database.VALID_LEAD_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid lead_status. Must be one of: {database.VALID_LEAD_STATUSES}")
    if req.priority not in database.VALID_LEAD_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"Invalid priority. Must be one of: {database.VALID_LEAD_PRIORITIES}")


@app.get("/api/leads/summary")
def get_leads_summary_endpoint(business_type: Optional[str] = None):
    """Retrieve lead count summary, optionally filtered by business_type."""
    if business_type and business_type not in database.VALID_BUSINESS_TYPES:
        raise HTTPException(status_code=400, detail="Invalid business_type")
    return database.get_leads_summary(business_type=business_type)


@app.get("/api/leads")
def list_leads_endpoint(
    business_type: Optional[str] = None,
    platform: Optional[str] = None,
    lead_status: Optional[str] = None,
    enquiry_category: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """List leads with optional business, platform, status, and category filters."""
    if business_type and business_type not in database.VALID_BUSINESS_TYPES:
        raise HTTPException(status_code=400, detail="Invalid business_type")
    if platform and platform.lower() not in database.VALID_LEAD_PLATFORMS:
        raise HTTPException(status_code=400, detail="Invalid platform")
    if lead_status and lead_status not in database.VALID_LEAD_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid lead_status")
    if enquiry_category and enquiry_category not in database.VALID_ENQUIRY_CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid enquiry_category")
    leads = database.get_leads(
        business_type=business_type,
        platform=platform,
        lead_status=lead_status,
        enquiry_category=enquiry_category,
        limit=limit,
        offset=offset,
    )
    return {"leads": leads, "count": len(leads)}


@app.get("/api/leads/{lead_id}")
def get_lead_endpoint(lead_id: int, business_type: Optional[str] = None):
    """Retrieve a single lead by ID, enforcing business_type isolation when provided."""
    if business_type and business_type not in database.VALID_BUSINESS_TYPES:
        raise HTTPException(status_code=400, detail="Invalid business_type")
    lead = database.get_lead_by_id(lead_id, business_type=business_type)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@app.post("/api/leads", status_code=201)
def create_lead_endpoint(req: LeadCreateRequest):
    """Create a new lead with validation and duplicate prevention."""
    _validate_lead_create(req)
    lead, err = database.create_lead(req.model_dump())
    if err == "duplicate":
        raise HTTPException(status_code=409, detail="Duplicate lead for this platform, account_id, and source_comment_id")
    if not lead:
        raise HTTPException(status_code=500, detail="Failed to create lead")
    return lead


@app.put("/api/leads/{lead_id}")
def update_lead_endpoint(lead_id: int, req: LeadUpdateRequest):
    """Update lead status, priority, notes, contact, or follow-up details."""
    if req.business_type and req.business_type not in database.VALID_BUSINESS_TYPES:
        raise HTTPException(status_code=400, detail="Invalid business_type")
    if req.lead_status and req.lead_status not in database.VALID_LEAD_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid lead_status")
    if req.priority and req.priority not in database.VALID_LEAD_PRIORITIES:
        raise HTTPException(status_code=400, detail="Invalid priority")
    if req.enquiry_category and req.enquiry_category not in database.VALID_ENQUIRY_CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid enquiry_category")

    updates = {k: v for k, v in req.model_dump().items() if k != "business_type" and v is not None}
    updated = database.update_lead(lead_id, updates, business_type=req.business_type)
    if not updated:
        raise HTTPException(status_code=404, detail="Lead not found")
    return updated


@app.get("/api/leads/{lead_id}/history")
def get_lead_history_endpoint(lead_id: int, business_type: Optional[str] = None):
    """Retrieve immutable activity history for a lead."""
    if business_type and business_type not in database.VALID_BUSINESS_TYPES:
        raise HTTPException(status_code=400, detail="Invalid business_type")
    history = database.get_lead_history(lead_id, business_type=business_type)
    if history is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {"lead_id": lead_id, "history": history}


# ==========================================
# Auto Post Scheduler V2 (Phase 3.0A)
# ==========================================

MEDIA_STORAGE_DIR = os.path.join(os.path.dirname(__file__), "media_storage", "auto_post")


class PostingSlotItem(BaseModel):
    day_of_week: int = -1
    slot_time: str


class PostingSlotsUpdateRequest(BaseModel):
    account_key: str
    slots: List[PostingSlotItem]


class BatchScheduleItem(BaseModel):
    original_filename: str
    media_path: str
    file_size_bytes: int = 0
    duration_seconds: Optional[float] = None
    zodiac_index: int
    caption: Optional[str] = None
    hashtags: Optional[str] = None
    thumbnail_path: Optional[str] = None


class ChannelSelection(BaseModel):
    account_key: str
    platform: str


class ScheduleMultiChannelRequest(BaseModel):
    accounts: List[ChannelSelection]
    category: str
    batch_id: Optional[str] = None
    items: List[BatchScheduleItem]


class ScheduleBatchRequest(BaseModel):
    account_key: str
    platform: str
    category: str
    batch_id: Optional[str] = None
    items: List[BatchScheduleItem]


class ReschedulePostRequest(BaseModel):
    scheduled_at: str


@app.post("/api/auto-post/upload-batch")
async def upload_auto_post_batch(
    files: List[UploadFile] = File(...),
    category: str = "Weekly Rasi Palan",
):
    if category not in scheduler_service.BATCH_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Unsupported category: {category}")
    batch_id = str(uuid.uuid4())[:8]
    batch_dir = os.path.join(MEDIA_STORAGE_DIR, batch_id)
    os.makedirs(batch_dir, exist_ok=True)

    items = []
    for f in files:
        safe_name = os.path.basename(f.filename or f"video_{len(items)+1}.mp4")
        dest_path = os.path.join(batch_dir, safe_name)
        content = await f.read()
        with open(dest_path, "wb") as out_f:
            out_f.write(content)

        detected = scheduler_service.detect_zodiac_from_filename(safe_name)
        z_idx = detected["index"] if detected else None
        if z_idx:
            gen = scheduler_service.generate_caption_and_hashtags(z_idx, category)
            needs_review = False
            review_reason = None
        else:
            gen = {"caption": "", "hashtags": "", "platform_descriptions": {}}
            needs_review = True
            review_reason = "Could not detect Rasi from filename; manual caption required."
        items.append(
            {
                "original_filename": safe_name,
                "media_path": dest_path,
                "media_url": f"/api/auto-post/media/{batch_id}/{urllib.parse.quote(safe_name)}",
                "file_size_bytes": len(content),
                "zodiac_index": z_idx,
                "zodiac_tamil": detected["tamil"] if detected else None,
                "zodiac_english": detected["english"] if detected else None,
                "caption": gen["caption"],
                "hashtags": gen["hashtags"],
                "platform_descriptions": gen.get("platform_descriptions", {}),
                "needs_review": needs_review,
                "review_reason": review_reason,
            }
        )

    analysis = scheduler_service.analyze_batch_items(items)
    analysis["batch_id"] = batch_id
    analysis["category"] = category
    return analysis


@app.get("/api/auto-post/media/{batch_id}/{filename}")
def serve_auto_post_media(batch_id: str, filename: str):
    safe_batch = os.path.basename(batch_id)
    safe_file = os.path.basename(filename)
    file_path = os.path.join(MEDIA_STORAGE_DIR, safe_batch, safe_file)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Media file not found")
    return FileResponse(file_path)


@app.get("/api/auto-post/slots")
def list_posting_slots(account_key: Optional[str] = None):
    return {"slots": scheduler_service.get_posting_slots(account_key=account_key)}


@app.post("/api/auto-post/slots")
def save_posting_slots_endpoint(req: PostingSlotsUpdateRequest):
    slots = scheduler_service.save_posting_slots(
        req.account_key, [s.model_dump() for s in req.slots]
    )
    return {"account_key": req.account_key, "slots": slots}


class AddPostingSlotRequest(BaseModel):
    account_key: str = "facebook:default"
    day_of_week: int = -1
    slot_time: str


@app.post("/api/auto-post/slots/add")
def add_posting_slot_endpoint(req: AddPostingSlotRequest):
    slots = scheduler_service.add_posting_slot(req.account_key, req.day_of_week, req.slot_time)
    return {"account_key": req.account_key, "slots": slots}


class GeneratePostingSlotsRequest(BaseModel):
    account_key: str = "facebook:default"
    mode: str
    days: Optional[List[int]] = None


@app.post("/api/auto-post/slots/generate")
def generate_posting_slots_endpoint(req: GeneratePostingSlotsRequest):
    try:
        slots = scheduler_service.generate_posting_slots(req.account_key, req.mode, req.days)
        return {"account_key": req.account_key, "slots": slots}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/auto-post/schedule-settings")
def get_schedule_settings_endpoint(account_key: str = "facebook:default"):
    return scheduler_service.get_posting_schedule_settings(account_key)


class ScheduleSettingsUpdateRequest(BaseModel):
    account_key: str = "facebook:default"
    timezone: Optional[str] = None
    weekly_goal: Optional[int] = None
    enabled_days: Optional[List[int]] = None


@app.post("/api/auto-post/schedule-settings")
def save_schedule_settings_endpoint(req: ScheduleSettingsUpdateRequest):
    try:
        return scheduler_service.save_posting_schedule_settings(
            account_key=req.account_key,
            timezone=req.timezone,
            weekly_goal=req.weekly_goal,
            enabled_days=req.enabled_days,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/auto-post/slots/{slot_id}")
def delete_posting_slot_endpoint(slot_id: int):
    deleted = scheduler_service.delete_posting_slot(slot_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Posting slot not found")
    return {"deleted": True, "slot_id": slot_id}


@app.post("/api/auto-post/schedule-multichannel")
def schedule_multichannel_endpoint(req: ScheduleMultiChannelRequest):
    try:
        result = scheduler_service.schedule_multichannel_batch(
            accounts=[a.model_dump() for a in req.accounts],
            category=req.category,
            items=[i.model_dump() for i in req.items],
            batch_id=req.batch_id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.put("/api/auto-post/videos/{video_id}/reschedule")
def reschedule_video_endpoint(video_id: str, req: ReschedulePostRequest):
    updated, err = scheduler_service.reschedule_video(video_id, req.scheduled_at)
    if err:
        code = 404 if "not found" in err.lower() else 409
        raise HTTPException(status_code=code, detail=err)
    return {"posts": updated}


@app.post("/api/auto-post/schedule-batch")
def schedule_batch_endpoint(req: ScheduleBatchRequest):
    try:
        result = scheduler_service.schedule_batch(
            account_key=req.account_key,
            platform=req.platform,
            category=req.category,
            items=[i.model_dump() for i in req.items],
            batch_id=req.batch_id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/api/auto-post/posts")
def list_scheduled_posts_endpoint(
    account_key: Optional[str] = None,
    status: Optional[str] = None,
):
    return {"posts": scheduler_service.get_scheduled_posts(account_key=account_key, status=status)}


@app.put("/api/auto-post/posts/{post_id}/reschedule")
def reschedule_post_endpoint(post_id: int, req: ReschedulePostRequest):
    updated, err = scheduler_service.reschedule_post(post_id, req.scheduled_at)
    if err:
        code = 404 if "not found" in err.lower() else 409
        raise HTTPException(status_code=code, detail=err)
    return {"post": updated}


@app.post("/api/auto-post/posts/{post_id}/retry")
def retry_scheduled_post_endpoint(post_id: int):
    updated, err = scheduler_service.retry_scheduled_post(post_id)
    if err:
        code = 404 if "not found" in err.lower() else 400
        raise HTTPException(status_code=code, detail=err)
    return {"post": updated}


@app.post("/api/auto-post/posts/{post_id}/cancel")
def cancel_scheduled_post_endpoint(post_id: int):
    updated, err = scheduler_service.cancel_scheduled_post(post_id)
    if err:
        code = 404 if "not found" in err.lower() else 400
        raise HTTPException(status_code=code, detail=err)
    return {"post": updated}


class UpdatePostRequest(BaseModel):
    caption: Optional[str] = None
    hashtags: Optional[str] = None
    category: Optional[str] = None
    scheduled_at: Optional[str] = None
    status: Optional[str] = None


class CreatePublishingPostRequest(BaseModel):
    account_key: str = "facebook:default"
    platform: Optional[str] = None
    status: str = "draft"
    caption: str = ""
    hashtags: str = ""
    category: str = "General Astrology"
    scheduled_at: Optional[str] = None
    original_filename: str = "custom_post.mp4"
    media_path: str = ""


@app.get("/api/publishing/workspace")
def get_publishing_workspace_endpoint(account_key: Optional[str] = None):
    return scheduler_service.get_publishing_workspace(account_key=account_key)


@app.patch("/api/auto-post/posts/{post_id}")
def update_scheduled_post_endpoint(post_id: int, req: UpdatePostRequest):
    updated, err = scheduler_service.update_scheduled_post(post_id, req.model_dump(exclude_unset=True))
    if err:
        code = 404 if "not found" in err.lower() else 400
        raise HTTPException(status_code=code, detail=err)
    return {"post": updated}


@app.post("/api/auto-post/posts/{post_id}/publish-now")
def publish_post_now_endpoint(post_id: int):
    updated, err = scheduler_service.publish_post_now(post_id)
    if err:
        code = 404 if "not found" in err.lower() else 400
        raise HTTPException(status_code=code, detail=err)
    return {"post": updated}


@app.post("/api/publishing/posts")
def create_publishing_post_endpoint(req: CreatePublishingPostRequest):
    created, err = scheduler_service.create_publishing_post(req.model_dump())
    if err:
        raise HTTPException(status_code=400, detail=err)
    return {"post": created}


def _check_platform_health(platform: str) -> dict:
    """Safely verify OAuth and publishing readiness for a platform without publishing or exposing tokens."""
    from datetime import datetime, timedelta
    import requests

    now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT account_id, account_name, access_token, refresh_token, token_expires_at, is_active FROM accounts WHERE platform = ? AND is_active = 1 LIMIT 1",
            (platform,),
        ).fetchone()
    except Exception:
        row = conn.execute(
            "SELECT account_id, account_name, access_token, is_active FROM accounts WHERE platform = ? AND is_active = 1 LIMIT 1",
            (platform,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return {
            "platform": platform,
            "account_connection": "Disconnected",
            "authorization": "Unknown",
            "publishing_readiness": "Blocked",
            "account_id": None,
            "account_name": None,
            "can_refresh": False,
            "last_checked": now_iso,
            "detail": "No active account connected.",
        }

    row_dict = dict(row)
    account_id = row_dict.get("account_id")
    account_name = row_dict.get("account_name")
    access_token = row_dict.get("access_token") or ""
    refresh_token = row_dict.get("refresh_token") or ""
    if platform == "youtube" and account_id:
        yt_tokens = YouTubeService.get_account_token_data(account_id) or {}
        access_token = yt_tokens.get("access_token") or access_token
        refresh_token = yt_tokens.get("refresh_token") or refresh_token
    expires_at = row_dict.get("token_expires_at")
    can_refresh = platform == "youtube" and bool(refresh_token)

    if not access_token:
        return {
            "platform": platform,
            "account_connection": "Connected",
            "authorization": "Refresh Required" if can_refresh else "Expired",
            "publishing_readiness": "Blocked",
            "account_id": account_id,
            "account_name": account_name,
            "can_refresh": can_refresh,
            "last_checked": now_iso,
            "detail": "Access token missing.",
        }

    expiring_soon = False
    if expires_at:
        try:
            exp_dt = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00").replace("+00:00", ""))
            if exp_dt <= datetime.now():
                return {
                    "platform": platform,
                    "account_connection": "Connected",
                    "authorization": "Refresh Required" if can_refresh else "Expired",
                    "publishing_readiness": "Blocked",
                    "account_id": account_id,
                    "account_name": account_name,
                    "can_refresh": can_refresh,
                    "last_checked": now_iso,
                    "detail": "Access token expired.",
                }
            if exp_dt <= datetime.now() + timedelta(minutes=10):
                expiring_soon = True
        except Exception:
            pass

    try:
        if platform == "facebook":
            resp = requests.get(
                "https://graph.facebook.com/v19.0/me",
                params={"fields": "id,name", "access_token": access_token},
                timeout=5,
            )
        elif platform == "instagram":
            resp = requests.get(
                f"https://graph.facebook.com/v19.0/{account_id}",
                params={"fields": "id,username", "access_token": access_token},
                timeout=5,
            )
        elif platform == "youtube":
            resp = requests.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params={"part": "id,snippet", "mine": "true"},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=5,
            )
        else:
            raise ValueError(f"Unsupported platform: {platform}")

        if resp.status_code == 200:
            auth_status = "Expiring Soon" if expiring_soon else "Valid"
            return {
                "platform": platform,
                "account_connection": "Connected",
                "authorization": auth_status,
                "publishing_readiness": "Ready",
                "account_id": account_id,
                "account_name": account_name,
                "can_refresh": can_refresh,
                "last_checked": now_iso,
                "detail": "Official API verification succeeded.",
            }
        if resp.status_code in (401, 403):
            return {
                "platform": platform,
                "account_connection": "Connected",
                "authorization": "Refresh Required" if can_refresh else "Expired",
                "publishing_readiness": "Blocked",
                "account_id": account_id,
                "account_name": account_name,
                "can_refresh": can_refresh,
                "last_checked": now_iso,
                "detail": f"Authorization rejected (HTTP {resp.status_code}).",
            }
        return {
            "platform": platform,
            "account_connection": "Connected",
            "authorization": "Authorization Check Failed",
            "publishing_readiness": "Not Verified",
            "account_id": account_id,
            "account_name": account_name,
            "can_refresh": can_refresh,
            "last_checked": now_iso,
            "detail": f"Verification returned HTTP {resp.status_code}.",
        }
    except Exception as exc:
        logger.warning("Health check failed for %s: %s", platform, type(exc).__name__)
        return {
            "platform": platform,
            "account_connection": "Connected",
            "authorization": "Authorization Check Failed",
            "publishing_readiness": "Not Verified",
            "account_id": account_id,
            "account_name": account_name,
            "can_refresh": can_refresh,
            "last_checked": now_iso,
            "detail": "Verification request failed.",
        }


@app.get("/api/accounts/health")
def get_accounts_health(platform: Optional[str] = None):
    """Consolidated OAuth and publishing readiness health check for Facebook, Instagram, and YouTube."""
    targets = [platform] if platform in ("facebook", "instagram", "youtube") else ["facebook", "instagram", "youtube"]
    results = {p: _check_platform_health(p) for p in targets}
    return {"accounts": results}


@app.post("/api/accounts/health/refresh")
def refresh_account_authorization(platform: str):
    """Safely refresh OAuth authorization where supported (YouTube with refresh token)."""
    if platform != "youtube":
        raise HTTPException(status_code=400, detail="Token refresh is only supported for YouTube.")
    acc = YouTubeService.get_connected_account()
    if not acc or not acc.get("account_id"):
        raise HTTPException(status_code=404, detail="No connected YouTube account found.")
    try:
        YouTubeService.refresh_access_token(acc["account_id"])
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Token refresh failed: {type(exc).__name__}")
    return {"account": _check_platform_health("youtube")}


# =============================================================================
# Community Inbox API (Post-Centric Comment Management)
# =============================================================================

class InboxReplyRequest(BaseModel):
    reply_text: str
    selected_level: Optional[str] = "custom"


@app.get("/api/inbox/posts")
def get_inbox_posts_endpoint(
    platform: Optional[str] = None,
    status: str = "all",
    date: str = "all",
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """Retrieve posts with comments for the Buffer-style Community Inbox."""
    result = database.get_inbox_posts(
        platform=platform,
        status_filter=status,
        date_filter=date,
        search=search,
        limit=limit,
        offset=offset,
    )
    settings = database.get_settings()
    result["safe_test_mode"] = settings.get("safe_test_mode", "true") == "true"
    return result


@app.get("/api/inbox/posts/{platform}/{post_id:path}/comments")
def get_inbox_post_comments_endpoint(
    platform: str,
    post_id: str,
    limit: int = 20,
    offset: int = 0,
    status: str = "all",
):
    """Retrieve selected post details and paginated comments with 3-level suggestions."""
    decoded_post_id = urllib.parse.unquote(post_id)
    result = database.get_inbox_post_comments(
        platform=platform,
        post_id=decoded_post_id,
        limit=limit,
        offset=offset,
        status_filter=status,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Post not found")
    settings = database.get_settings()
    result["safe_test_mode"] = settings.get("safe_test_mode", "true") == "true"
    return result


@app.post("/api/inbox/comments/{platform}/{comment_id:path}/regenerate")
def regenerate_inbox_suggestions_endpoint(platform: str, comment_id: str):
    """Regenerate 3-level personalized suggestions for a single comment."""
    decoded_id = urllib.parse.unquote(comment_id)
    sugg = database.regenerate_inbox_comment_suggestions(platform, decoded_id)
    if not sugg:
        raise HTTPException(status_code=404, detail="Comment not found")
    return {"success": True, "suggestions": sugg}


@app.post("/api/inbox/comments/{platform}/{comment_id:path}/reply")
def send_inbox_reply_endpoint(platform: str, comment_id: str, payload: InboxReplyRequest):
    """Explicitly send (or Safe-Test-record) a reply to a specific comment."""
    decoded_id = urllib.parse.unquote(comment_id)
    res = database.send_inbox_reply(
        platform=platform,
        comment_id=decoded_id,
        reply_text=payload.reply_text,
        selected_level=payload.selected_level or "custom",
    )
    if not res.get("success"):
        reason = res.get("reason")
        if reason == "comment_not_found":
            raise HTTPException(status_code=404, detail=res.get("error", "Comment not found"))
        if res.get("duplicate_blocked"):
            raise HTTPException(status_code=409, detail=res.get("error", "Already replied"))
        if reason in ("empty_reply_text", "invalid_comment_id", "unsupported_platform"):
            raise HTTPException(status_code=400, detail=res.get("error", "Invalid request"))
    return res


@app.get("/api/inbox/analytics")
def get_inbox_analytics_endpoint(platform: Optional[str] = None, period: str = "day"):
    """Return day/week/month comment analytics filtered by platform."""
    return database.get_comment_analytics(platform=platform, period=period)


@app.post("/api/inbox/sync")
def sync_inbox_comments_endpoint(platform: Optional[str] = None):
    """Sync comments from connected platforms into the Community Inbox."""
    targets = [platform.lower()] if platform and platform.lower() in ("facebook", "instagram", "youtube") else ["facebook", "instagram", "youtube"]
    results = {}
    for p in targets:
        if p == "facebook":
            results["facebook"] = FacebookService.sync_facebook_comments()
        elif p == "instagram":
            results["instagram"] = InstagramService.sync_instagram_comments()
        elif p == "youtube":
            results["youtube"] = YouTubeService.sync_youtube_comments()
    return {"success": True, "results": results}


# Serve frontend
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/api/sync/accounts")
def get_sync_accounts():
    return {"accounts": sync_service.ensure_account_sync_states()}


@app.post("/api/sync/accounts/{platform}/{account_id}/settings")
def update_sync_account_settings(platform: str, account_id: str, payload: dict):
    try:
        updated = sync_service.update_account_sync_settings(
            platform=platform,
            account_id=account_id,
            auto_sync_enabled=payload.get("auto_sync_enabled"),
            reply_mode=payload.get("reply_mode"),
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Account sync state not found")
        return {"account": updated}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/sync/accounts/{platform}/{account_id}/now")
def trigger_manual_account_sync(platform: str, account_id: str):
    return sync_service.sync_account(platform, account_id, sync_type="manual")


@app.get("/api/sync/history")
def get_sync_history_endpoint(limit: int = 50):
    return {"history": sync_service.get_sync_history(limit=limit)}


@app.get("/")
def serve_home():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Gokul Social Publisher API is running. UI loading..."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8088, reload=False)
