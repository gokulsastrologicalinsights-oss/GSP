"""Pytest configuration to isolate test database from production database."""
import os
import pytest

TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "test_gsp.db")
os.environ["GSP_DB_PATH"] = TEST_DB_PATH

import database
database.init_db()

@pytest.fixture(autouse=True)
def clean_test_db():
    database.init_db()
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM activities")
    c.execute("DELETE FROM accounts")
    c.execute("DELETE FROM oauth_sessions")
    c.execute("DELETE FROM scheduled_posts")
    c.execute("DELETE FROM posting_slots")
    c.execute("DELETE FROM posting_schedule_settings")
    c.execute("DELETE FROM approval_queue")
    c.execute("DELETE FROM approval_activity_log")
    c.execute("DELETE FROM publishing_attempts")
    c.execute("DELETE FROM notifications")
    c.execute("DELETE FROM leads")
    c.execute("DELETE FROM lead_activity_history")
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('safe_test_mode', 'true')")
    conn.commit()
    conn.close()
