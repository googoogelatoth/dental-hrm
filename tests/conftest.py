import os

import pytest

# Use isolated test database/config defaults for all test modules.
os.environ.setdefault("ENCRYPTION_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
# Force tests to use an isolated sqlite database to avoid touching non-test DBs.
os.environ["DATABASE_URL"] = "sqlite:///./security_regression_test.db"
os.environ.setdefault("VAPID_PUBLIC_KEY", "A" * 87)
os.environ.setdefault("VAPID_PRIVATE_KEY", "B" * 43)

from app.database import Base, engine


def _assert_safe_test_database_url() -> None:
    db_url = str(engine.url)
    if not db_url.startswith("sqlite"):
        raise RuntimeError(f"Unsafe test database URL (expected sqlite): {db_url}")
    if "security_regression_test.db" not in db_url:
        raise RuntimeError(f"Unsafe test database URL (expected test DB file): {db_url}")


@pytest.fixture(scope="session", autouse=True)
def reset_test_db_schema():
    _assert_safe_test_database_url()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
