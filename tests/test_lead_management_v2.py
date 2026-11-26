"""Focused tests for GSP V2.0 Phase 2.0A: Smart Lead Management Foundation."""
import pytest
from fastapi.testclient import TestClient

import database
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_leads_tables():
    database.init_db()
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM lead_activity_history")
    c.execute("DELETE FROM leads")
    conn.commit()
    conn.close()


def _sample_lead(**overrides):
    payload = {
        "business_type": "Astrology",
        "platform": "facebook",
        "account_id": "fb_page_astro_1",
        "source_comment_id": "cmt_1001",
        "customer_name": "Arjun Nair",
        "customer_username": "arjun_nair",
        "customer_contact": None,
        "enquiry_category": "Astrology consultation",
        "original_message": "Namaste, I want to book a consultation.",
        "detected_language": "en",
        "lead_status": "New",
        "priority": "Medium",
    }
    payload.update(overrides)
    return payload


def test_lead_creation_and_retrieval():
    res = client.post("/api/leads", json=_sample_lead())
    assert res.status_code == 201
    created = res.json()
    assert created["id"] > 0
    assert created["business_type"] == "Astrology"
    assert created["lead_status"] == "New"

    get_res = client.get(f"/api/leads/{created['id']}")
    assert get_res.status_code == 200
    assert get_res.json()["source_comment_id"] == "cmt_1001"

    list_res = client.get("/api/leads")
    assert list_res.status_code == 200
    assert list_res.json()["count"] == 1

    summary_res = client.get("/api/leads/summary")
    assert summary_res.status_code == 200
    assert summary_res.json()["total"] == 1
    assert summary_res.json()["by_business"]["Astrology"] == 1


def test_lead_updates_and_history_persistence():
    created = client.post("/api/leads", json=_sample_lead()).json()
    lead_id = created["id"]

    upd_res = client.put(
        f"/api/leads/{lead_id}",
        json={
            "lead_status": "Contacted",
            "priority": "High",
            "internal_notes": "Called customer, prefers evening slot.",
            "customer_contact": "DM on Facebook",
            "next_follow_up_at": "2026-12-01T18:00:00",
            "follow_up_completed": True,
        },
    )
    assert upd_res.status_code == 200
    updated = upd_res.json()
    assert updated["lead_status"] == "Contacted"
    assert updated["priority"] == "High"
    assert updated["internal_notes"] == "Called customer, prefers evening slot."
    assert updated["last_contacted_at"] is not None

    hist_res = client.get(f"/api/leads/{lead_id}/history")
    assert hist_res.status_code == 200
    events = [item["event_type"] for item in hist_res.json()["history"]]
    for expected in (
        "lead_created",
        "status_changed",
        "priority_changed",
        "notes_added",
        "contact_updated",
        "follow_up_scheduled",
        "follow_up_completed",
    ):
        assert expected in events


def test_duplicate_prevention():
    res1 = client.post("/api/leads", json=_sample_lead())
    assert res1.status_code == 201

    res2 = client.post("/api/leads", json=_sample_lead())
    assert res2.status_code == 409


def test_business_separation():
    astro = client.post(
        "/api/leads",
        json=_sample_lead(business_type="Astrology", source_comment_id="cmt_a1"),
    ).json()
    vivaham = client.post(
        "/api/leads",
        json=_sample_lead(
            business_type="Vivaham",
            account_id="ig_vivaham_1",
            platform="instagram",
            source_comment_id="cmt_v1",
            enquiry_category="Marriage enquiry",
        ),
    ).json()

    astro_list = client.get("/api/leads?business_type=Astrology").json()
    assert astro_list["count"] == 1
    assert astro_list["leads"][0]["id"] == astro["id"]

    # Cross-business get/update/history must not expose or modify another business's lead
    assert client.get(f"/api/leads/{astro['id']}?business_type=Vivaham").status_code == 404
    assert client.put(
        f"/api/leads/{astro['id']}",
        json={"business_type": "Vivaham", "lead_status": "Converted"},
    ).status_code == 404
    assert client.get(f"/api/leads/{astro['id']}/history?business_type=Vivaham").status_code == 404
    assert vivaham["business_type"] == "Vivaham"


def test_platform_status_and_category_filtering():
    client.post(
        "/api/leads",
        json=_sample_lead(platform="facebook", lead_status="New", enquiry_category="Horoscope analysis", source_comment_id="c1"),
    )
    client.post(
        "/api/leads",
        json=_sample_lead(platform="instagram", lead_status="Interested", enquiry_category="Numerology", source_comment_id="c2"),
    )
    client.post(
        "/api/leads",
        json=_sample_lead(platform="youtube", lead_status="Converted", enquiry_category="General enquiry", source_comment_id="c3"),
    )

    assert client.get("/api/leads?platform=instagram").json()["count"] == 1
    assert client.get("/api/leads?lead_status=Interested").json()["count"] == 1
    assert client.get("/api/leads?enquiry_category=Numerology").json()["count"] == 1


def test_invalid_input_handling():
    assert client.post("/api/leads", json=_sample_lead(business_type="InvalidBiz")).status_code == 400
    assert client.post("/api/leads", json=_sample_lead(platform="tiktok")).status_code == 400
    assert client.post("/api/leads", json=_sample_lead(enquiry_category="UnknownCat")).status_code == 400


def test_followup_summary_counts():
    l1 = client.post("/api/leads", json=_sample_lead(source_comment_id="fu_1")).json()
    client.put(f"/api/leads/{l1['id']}", json={"next_follow_up_at": "2020-01-01T10:00:00"})

    l2 = client.post("/api/leads", json=_sample_lead(source_comment_id="fu_2")).json()
    client.put(f"/api/leads/{l2['id']}", json={"next_follow_up_at": "2099-01-01T10:00:00"})

    summary = client.get("/api/leads/summary").json()
    assert summary["pending_follow_ups"] == 2
    assert summary["overdue_follow_ups"] == 1
    assert client.post("/api/leads", json=_sample_lead(lead_status="Closed")).status_code == 400
    assert client.post("/api/leads", json=_sample_lead(priority="Urgent")).status_code == 400
    assert client.post("/api/leads", json=_sample_lead(original_message="   ")).status_code == 400


def test_database_restart_persistence():
    created = client.post("/api/leads", json=_sample_lead(source_comment_id="persist_1")).json()
    database.init_db()
    fetched = client.get(f"/api/leads/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["source_comment_id"] == "persist_1"


def test_oauth_secret_protection():
    conn = database.get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO accounts (platform, account_id, account_name, access_token, is_active) VALUES (?, ?, ?, ?, 1)",
        ("facebook", "fb_page_astro_1", "Astro Page", "SUPER_SECRET_OAUTH_TOKEN_12345"),
    )
    conn.commit()
    conn.close()

    res = client.post("/api/leads", json=_sample_lead(source_comment_id="sec_1"))
    assert res.status_code == 201
    body_text = res.text + client.get("/api/leads").text + client.get("/api/leads/summary").text
    assert "SUPER_SECRET_OAUTH_TOKEN_12345" not in body_text
    assert "access_token" not in res.json()
