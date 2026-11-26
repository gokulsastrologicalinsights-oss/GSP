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
    conn.commit()
    conn.close()
