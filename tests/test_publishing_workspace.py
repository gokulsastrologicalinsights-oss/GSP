from fastapi.testclient import TestClient
import main

client = TestClient(main.app)


def test_publishing_workspace_endpoint():
    res = client.get("/api/publishing/workspace")
    assert res.status_code == 200
    data = res.json()
    assert "channels" in data
    assert "counts" in data
    assert "posts" in data
    assert data["timezone"] == "Asia/Kolkata"
    assert len(data["channels"]) == 3


def test_create_edit_and_publish_now_safe_mode():
    # Create draft
    res = client.post(
        "/api/publishing/posts",
        json={
            "account_key": "facebook:default",
            "status": "draft",
            "caption": "Test Buffer Workspace Draft",
            "category": "General Astrology",
        },
    )
    assert res.status_code == 200
    post = res.json()["post"]
    pid = post["id"]
    assert post["status"] == "draft"

    # Edit caption & move to scheduled
    res2 = client.patch(
        f"/api/auto-post/posts/{pid}",
        json={"caption": "Updated Caption", "status": "scheduled"},
    )
    assert res2.status_code == 200
    assert res2.json()["post"]["status"] == "scheduled"
    assert res2.json()["post"]["caption"] == "Updated Caption"

    # Publish Now in safe_test_mode
    res3 = client.post(f"/api/auto-post/posts/{pid}/publish-now")
    assert res3.status_code == 200
    assert res3.json()["post"]["status"] == "published_safe_mode"

    # Unsafe transition from published_safe_mode back to draft must fail
    res4 = client.patch(f"/api/auto-post/posts/{pid}", json={"status": "draft"})
    assert res4.status_code == 400
