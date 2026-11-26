"""Focused tests for Priority 2A: Hybrid Reply Approval Queue Backend."""
import pytest
from fastapi.testclient import TestClient

import database
from main import app
from facebook_service import FacebookService
from instagram_service import InstagramService
from youtube_service import YouTubeService


client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_approval_queue():
    """Isolate approval_queue and safe_test_mode state for each test."""
    database.init_db()
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM approval_queue")
    c.execute("DELETE FROM activities")
    conn.commit()
    conn.close()
    database.set_setting("safe_test_mode", "true")
    yield


def test_queue_record_creation_from_classification():
    """Questions, complaints, abuse/spam, and uncertain comments enter approval_queue."""
    res = FacebookService.process_and_reply_comment(
        {
            "id": "fb_q_1",
            "post_id": "post_1",
            "message": "What is the consultation fee?",
            "from": {"id": "user_1", "name": "Arun"},
        },
        page_id="page_1",
        access_token=None,
    )
    assert res["status"] == "review_required"

    items = database.get_approval_queue(status="pending", platform="facebook")
    assert len(items) == 1
    item = items[0]
    assert item["platform"] == "facebook"
    assert item["account_id"] == "page_1"
    assert item["comment_id"] == "fb_q_1"
    assert item["commenter_name"] == "Arun"
    assert item["comment_text"] == "What is the consultation fee?"
    assert item["detected_intent"] == "fee_enquiry"
    assert item["status"] == "pending"
    assert item["review_reason"] == "consultation_fee_enquiry"


def test_duplicate_queue_prevention():
    """Duplicate (platform, comment_id) must not create duplicate queue records."""
    q1 = database.enqueue_approval_item(
        platform="instagram",
        account_id="ig_1",
        comment_id="dup_c_1",
        commenter_name="Priya",
        comment_text="How much?",
        detected_language="en",
        detected_intent="fee_enquiry",
        suggested_reply=None,
        review_reason="consultation_fee_enquiry",
    )
    q2 = database.enqueue_approval_item(
        platform="instagram",
        account_id="ig_1",
        comment_id="dup_c_1",
        commenter_name="Priya",
        comment_text="How much?",
        detected_language="en",
        detected_intent="fee_enquiry",
        suggested_reply=None,
        review_reason="consultation_fee_enquiry",
    )
    assert q1 is not None
    assert q2 is None
    items = database.get_approval_queue(status="pending", platform="instagram")
    assert len(items) == 1


def test_pending_queue_retrieval_and_detail_api():
    """GET /api/approval-queue and GET /api/approval-queue/{id} return pending items."""
    qid = database.enqueue_approval_item(
        platform="youtube",
        account_id="yt_1",
        comment_id="yt_c_1",
        commenter_name="Karthik",
        comment_text="Is this available?",
        detected_language="en",
        detected_intent="question",
        suggested_reply=None,
        review_reason="question_requires_review",
    )
    resp = client.get("/api/approval-queue")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["items"][0]["id"] == qid

    detail = client.get(f"/api/approval-queue/{qid}")
    assert detail.status_code == 200
    assert detail.json()["item"]["comment_id"] == "yt_c_1"

    missing = client.get("/api/approval-queue/999999")
    assert missing.status_code == 404


def test_reply_editing():
    """PUT /api/approval-queue/{id}/edit updates edited_reply."""
    qid = database.enqueue_approval_item(
        platform="facebook",
        account_id="page_1",
        comment_id="fb_edit_1",
        commenter_name="Meena",
        comment_text="Timing please?",
        detected_language="en",
        detected_intent="question",
        suggested_reply=None,
        review_reason="question_requires_review",
    )
    resp = client.put(
        f"/api/approval-queue/{qid}/edit",
        json={"edited_reply": "Please DM us for timings."},
    )
    assert resp.status_code == 200
    assert resp.json()["item"]["edited_reply"] == "Please DM us for timings."


def test_approve_and_reject_actions_and_history():
    """Approve and reject move items out of pending into history."""
    q_app = database.enqueue_approval_item(
        platform="facebook",
        account_id="page_1",
        comment_id="fb_app_1",
        commenter_name="Siva",
        comment_text="Fee?",
        detected_language="en",
        detected_intent="fee_enquiry",
        suggested_reply=None,
        review_reason="consultation_fee_enquiry",
    )
    q_rej = database.enqueue_approval_item(
        platform="facebook",
        account_id="page_1",
        comment_id="fb_rej_1",
        commenter_name="Spammer",
        comment_text="Buy followers http://spam.example",
        detected_language="en",
        detected_intent="spam",
        suggested_reply=None,
        review_reason="spam_detected",
    )

    app_resp = client.post(
        f"/api/approval-queue/{q_app}/approve",
        json={"edited_reply": "Thank you, we will DM you."},
    )
    assert app_resp.status_code == 200
    assert app_resp.json()["item"]["status"] == "approved"
    assert app_resp.json()["item"]["approved_at"] is not None
    assert app_resp.json()["published"] is False

    rej_resp = client.post(
        f"/api/approval-queue/{q_rej}/reject",
        json={"reason": "spam_ignored"},
    )
    assert rej_resp.status_code == 200
    assert rej_resp.json()["item"]["status"] == "rejected"

    pending = client.get("/api/approval-queue").json()
    assert pending["count"] == 0

    history = client.get("/api/approval-queue/history").json()
    assert history["count"] == 2


def test_invalid_status_transitions():
    """Rejected or already-approved/replied records cannot be re-approved or edited after reject."""
    qid = database.enqueue_approval_item(
        platform="instagram",
        account_id="ig_1",
        comment_id="ig_inv_1",
        commenter_name="Ravi",
        comment_text="Bad service",
        detected_language="en",
        detected_intent="complaint_or_abuse",
        suggested_reply=None,
        review_reason="complaint_or_abuse",
    )
    assert client.post(f"/api/approval-queue/{qid}/reject").status_code == 200
    # Cannot approve a rejected item
    assert client.post(f"/api/approval-queue/{qid}/approve").status_code == 400
    # Cannot edit a rejected item
    assert (
        client.put(
            f"/api/approval-queue/{qid}/edit",
            json={"edited_reply": "Sorry"},
        ).status_code
        == 400
    )
    # Cannot reject again
    assert client.post(f"/api/approval-queue/{qid}/reject").status_code == 400


def test_queue_persistence_after_restart():
    """Queue records persist across init_db() / fresh DB connections."""
    qid = database.enqueue_approval_item(
        platform="youtube",
        account_id="yt_1",
        comment_id="yt_persist_1",
        commenter_name="Anitha",
        comment_text="Where is your office?",
        detected_language="en",
        detected_intent="question",
        suggested_reply=None,
        review_reason="question_requires_review",
    )
    database.init_db()
    item = database.get_approval_queue_item(qid)
    assert item is not None
    assert item["comment_id"] == "yt_persist_1"
    assert item["status"] == "pending"


def test_activity_log_consistency():
    """Processing a review_required comment logs to both activities and approval_queue."""
    InstagramService.process_and_reply_comment(
        {
            "id": "ig_act_1",
            "post_id": "ig_post_1",
            "text": "Worst experience ever!",
            "username": "angry_user",
        },
        ig_user_id="ig_1",
        access_token=None,
    )
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("SELECT status, reason FROM activities WHERE comment_id = 'ig_act_1'")
    act = c.fetchone()
    c.execute("SELECT status, review_reason FROM approval_queue WHERE comment_id = 'ig_act_1'")
    q = c.fetchone()
    conn.close()

    assert act is not None and act["status"] == "review_required"
    assert q is not None and q["status"] == "pending"
    assert act["reason"] == q["review_reason"]


def test_safe_testing_mode_prevents_publication(monkeypatch):
    """Approving a queue item while Safe Testing Mode is ON never calls platform send_reply."""
    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        return {"id": "should_not_happen"}

    monkeypatch.setattr(FacebookService, "send_reply", fail_if_called)
    monkeypatch.setattr(InstagramService, "send_reply", fail_if_called)
    monkeypatch.setattr(YouTubeService, "send_reply", fail_if_called)

    qid = database.enqueue_approval_item(
        platform="facebook",
        account_id="page_1",
        comment_id="fb_safe_1",
        commenter_name="Bala",
        comment_text="Price?",
        detected_language="en",
        detected_intent="fee_enquiry",
        suggested_reply=None,
        review_reason="consultation_fee_enquiry",
    )
    resp = client.post(f"/api/approval-queue/{qid}/approve")
    assert resp.status_code == 200
    body = resp.json()
    assert body["safe_test_mode"] is True
    assert body["published"] is False
    assert body["item"]["status"] == "approved"
    assert body["item"]["published_at"] is None
    assert called is False


def test_platform_queue_separation():
    """Facebook, Instagram, and YouTube queue items are cleanly separated by platform."""
    database.enqueue_approval_item("facebook", "fb_1", "c_fb", "U1", "Q?", "en", "question", None, "question_requires_review")
    database.enqueue_approval_item("instagram", "ig_1", "c_ig", "U2", "Q?", "en", "question", None, "question_requires_review")
    database.enqueue_approval_item("youtube", "yt_1", "c_yt", "U3", "Q?", "en", "question", None, "question_requires_review")

    fb = client.get("/api/approval-queue?platform=facebook").json()
    ig = client.get("/api/approval-queue?platform=instagram").json()
    yt = client.get("/api/approval-queue?platform=youtube").json()

    assert fb["count"] == 1 and fb["items"][0]["platform"] == "facebook"
    assert ig["count"] == 1 and ig["items"][0]["platform"] == "instagram"
    assert yt["count"] == 1 and yt["items"][0]["platform"] == "youtube"


def test_credential_security_in_queue_responses():
    """Queue API responses never expose OAuth tokens or secrets."""
    conn = database.get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO accounts (platform, account_id, account_name, access_token, is_active) VALUES (?, ?, ?, ?, 1)",
        ("facebook", "fb_sec_1", "Sec Page", "SUPER_SECRET_OAUTH_TOKEN_12345"),
    )
    conn.commit()
    conn.close()

    qid = database.enqueue_approval_item(
        "facebook", "fb_sec_1", "c_sec_1", "User", "Hello?", "en", "question", None, "question_requires_review"
    )
    list_resp = client.get("/api/approval-queue").text
    detail_resp = client.get(f"/api/approval-queue/{qid}").text
    assert "SUPER_SECRET_OAUTH_TOKEN_12345" not in list_resp
    assert "SUPER_SECRET_OAUTH_TOKEN_12345" not in detail_resp
    assert "access_token" not in list_resp
    assert "access_token" not in detail_resp
