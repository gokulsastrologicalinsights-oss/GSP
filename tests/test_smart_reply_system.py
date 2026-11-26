from fastapi.testclient import TestClient

import database
import main
import reply_suggester


def test_classification_tamil_tanglish_english():
    assert reply_suggester.classify_comment("அருமை! மிக்க நன்றி 🙏")["intent"] == "positive"
    assert reply_suggester.classify_comment("Semma super video bro!")["intent"] == "positive"
    assert reply_suggester.classify_comment("Vanakkam")["intent"] == "greeting"
    assert reply_suggester.classify_comment("What is the consultation fee for jathagam?")["intent"] == "general_inquiry"
    assert reply_suggester.classify_comment("Okay noted")["intent"] == "neutral"
    assert reply_suggester.classify_comment("This video is boring and waste")["intent"] == "negative"
    assert reply_suggester.classify_comment("I paid but got no response, need refund")["intent"] == "complaint"
    assert reply_suggester.classify_comment("You are a scammer and idiot")["intent"] == "abusive"
    assert reply_suggester.classify_comment("Click here https://spam.example.com to earn money")["intent"] == "spam"
    assert reply_suggester.classify_comment("I will sue you and expose you in court")["intent"] == "threatening"


def test_personalized_reply_generation_and_safety():
    pos = reply_suggester.generate_reply_suggestion(
        "Thank you, very helpful!", commenter_name="Priya", account_name="Gokul's Astrological Insights"
    )
    neg = reply_suggester.generate_reply_suggestion(
        "Not useful at all", commenter_name="Ravi", account_name="Gokul Vivaham"
    )
    abuse = reply_suggester.generate_reply_suggestion(
        "You are a fraud and idiot", commenter_name="Anon", account_name="Gokul's Astrological Insights"
    )
    spam = reply_suggester.generate_reply_suggestion("Visit https://spam.test now")
    threat = reply_suggester.generate_reply_suggestion("I will hurt you")

    assert pos["generation_method"] == "local_contextual"
    assert "Priya" in pos["suggested_reply"]
    assert pos["suggested_reply"] != neg["suggested_reply"]
    assert "Gokul Vivaham" in neg["suggested_reply"]
    assert "WhatsApp" in abuse["suggested_reply"]
    assert "idiot" not in abuse["suggested_reply"].lower()
    assert spam["suggested_reply"] == ""
    assert threat["suggested_reply"] == ""


def test_approval_queue_actions_and_sync_idempotency():
    client = TestClient(main.app)
    sync1 = client.post("/api/approval-queue/sync")
    assert sync1.status_code == 200
    assert sync1.json()["success"] is True

    sync2 = client.post("/api/approval-queue/sync")
    assert sync2.status_code == 200
    assert sync2.json()["inserted"] == 0
