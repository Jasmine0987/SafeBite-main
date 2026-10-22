import os
import tempfile

import pytest

# Point the app at a throwaway SQLite file for the whole test session,
# BEFORE app.main (and therefore app.core.database) gets imported —
# database.py reads this env var at import time. Without this, test runs
# would read/write the real dev database and leave junk scan rows behind.
_TEST_DB_DIR = tempfile.mkdtemp(prefix="safebite-test-db-")
os.environ.setdefault("SAFEBITE_DB_PATH", os.path.join(_TEST_DB_DIR, "test.db"))

from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    """
    A FastAPI test client — makes requests in-process, no real server needed.

    Uses TestClient as a context manager so the app's lifespan (startup)
    actually runs: that's what calls db.init_db() and
    db.seed_demo_scans_if_empty(), and without it the isolated test
    database would never get its tables created.
    """
    with TestClient(app) as c:
        yield c