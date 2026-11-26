"""Focused tests for Phase 2: Facebook Automatic Comment Reply."""
import pytest
from starlette.testclient import TestClient
from main import app
import database
from nlp_detector import detect_language, analyze_comment
from facebook_service import FacebookService

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    database.init_db()
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM activities")
    c.execute("DELETE FROM accounts")
    conn.commit()
    conn.close()

def test_language_detection():
    # Tamil script
    assert detect_language("வணக்கம் உங்கள் பதிவு அருமை") == "ta"
    assert detect_language("மிகவும் நன்றி தலைவா") == "ta"
    
    # Tanglish (Tamil in Latin alphabet)
    assert detect_language("Super bro vera level") == "tanglish"
    assert detect_language("Vanakkam nalla irukku nanri") == "tanglish"
    assert detect_language("Romba nalla timing") == "tanglish"
    
    # English
    assert detect_language("Great post, love your content!") == "en"
    assert detect_language("Hello team, wonderful presentation") == "en"

def test_intent_detection_and_templates():
    # 1. Praise in Tamil
    lang, intent, reply, status = analyze_comment("சூப்பர் அருமையான பதிவு வாழ்த்துகள்")
    assert lang == "ta"
    assert intent == "praise"
    assert status == "reply_ready"
    assert reply is not None

    # 2. Tanglish praise
    lang, intent, reply, status = analyze_comment("Semma mass bro super")
    assert lang == "tanglish"
    assert intent == "praise"
    assert status == "reply_ready"
    assert reply is not None

    # 3. English greeting (non-praise -> manual review per Priority 1)
    lang, intent, reply, status = analyze_comment("Hello! Good morning everyone")
    assert lang == "en"
    assert status == "review_required"
    assert reply is None

    # 4. Abuse / Complaint filter -> Must require manual review, NO auto-reply
    lang, intent, reply, status = analyze_comment("This is fake and scam! Waste money fraud")
    assert intent == "complaint_or_abuse"
    assert status == "review_required"
    assert reply is None

    # Tanglish complaint filter
    lang, intent, reply, status = analyze_comment("Romba mosam fraud panreenga cheat")
    assert intent == "complaint_or_abuse"
    assert status == "review_required"
    assert reply is None

    # Tamil abuse filter
    lang, intent, reply, status = analyze_comment("இது போலி ஏமாற்று குப்பை")
    assert intent == "complaint_or_abuse"
    assert status == "review_required"
    assert reply is None

def test_english_praise_and_safety_cases():
    for text in ["Very useful video", "Very useful", "Good"]:
        lang, intent, reply, status = analyze_comment(text)
        assert lang == "en"
        assert intent == "praise"
        assert status == "reply_ready"
        assert reply is not None

    for unsafe_text in ["Not good", "Not useful", "Check this random link"]:
        lang, intent, reply, status = analyze_comment(unsafe_text)
        assert lang == "en"
        assert status == "review_required"
        assert reply is None

def test_facebook_pipeline_self_comment_exclusion():
    page_id = "page_9999"
    comment = {
        "id": "c_self_1",
        "post_id": "post_1",
        "message": "Super post!",
        "from": {"id": "page_9999", "name": "My Page"}  # Same as page_id
    }
    result = FacebookService.process_and_reply_comment(comment, page_id=page_id)
    assert result["status"] == "skipped"
    assert result["reason"] == "self_comment"

def test_facebook_pipeline_duplicate_prevention_and_safe_test_mode():
    database.set_setting("auto_reply_enabled", "true")
    database.set_setting("safe_test_mode", "true")
    page_id = "page_1234"
    comment = {
        "id": "c_unique_101",
        "post_id": "post_1",
        "message": "Awesome work bro, congrats!",
        "from": {"id": "user_789", "name": "Fan User"}
    }
    
    # First run -> safe testing mode prepares reply without calling live API
    res1 = FacebookService.process_and_reply_comment(comment, page_id=page_id)
    assert res1["status"] == "test_prepared"
    assert res1["intent"] == "praise"
    assert res1["reply_text"] is not None

    # Second run -> duplicate prevention must skip
    res2 = FacebookService.process_and_reply_comment(comment, page_id=page_id)
    assert res2["status"] == "skipped"
    assert res2["reason"] == "already_processed"

def test_token_security():
    # Connect Facebook page
    FacebookService.connect_page("sec_page_1", "Secret FB Page", "EAAB_SECRET_PAGE_ACCESS_TOKEN_XYZ")
    
    # Public accounts API must never expose access_token
    res = client.get("/api/accounts")
    assert res.status_code == 200
    for acc in res.json()["accounts"]:
        assert "access_token" not in acc

    # Facebook status API must never expose access_token
    fb_status = client.get("/api/facebook/status")
    assert fb_status.status_code == 200
    if fb_status.json()["connected"]:
        assert "access_token" not in fb_status.json()["page"]

def test_simulate_comment_endpoint():
    database.set_setting("auto_reply_enabled", "true")
    database.set_setting("safe_test_mode", "true")
    payload = {
        "comment_id": "sim_pytest_1",
        "author_name": "Test Tester",
        "author_id": "u1",
        "message": "வணக்கம் வாழ்த்துகள்"
    }
    res = client.post("/api/facebook/simulate-comment", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["result"]["language"] == "ta"
