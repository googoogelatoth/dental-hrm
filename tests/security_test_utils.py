import os
from datetime import date, time

import pytest
from fastapi.testclient import TestClient

# Configure env before importing the application module.
os.environ.setdefault("ENCRYPTION_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
os.environ.setdefault("DATABASE_URL", "sqlite:///./security_regression_test.db")
os.environ.setdefault("VAPID_PUBLIC_KEY", "A" * 87)
os.environ.setdefault("VAPID_PRIVATE_KEY", "B" * 43)

from app.database import SessionLocal
from app.main import app
from app.models import Employee, Attendance, LeaveRequest, OTRequest, PayrollDetail

# Avoid running unrelated startup bootstrap in tests.
app.router.on_startup = [
    fn for fn in app.router.on_startup if getattr(fn, "__name__", "") != "create_first_admin"
]


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_user(db_session, employee_code: str, role: str, session_id: str = "test-session") -> Employee:
    existing = db_session.query(Employee).filter(Employee.employee_code == employee_code).first()
    if existing:
        db_session.delete(existing)
        db_session.commit()

    user = Employee(
        employee_code=employee_code,
        first_name="Sec",
        last_name="Test",
        role=role,
        position=role,
        hashed_password="$2b$12$X0B42GIuM2kJ6jMQjA72Q.7F.8c3m3vQ/rD06xP9rz4wcbP5sJh4W",
        is_active=True,
        current_session_id=session_id,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def create_inactive_user(db_session, employee_code: str, role: str, session_id: str = "inactive-session") -> Employee:
    user = create_user(db_session, employee_code, role, session_id=session_id)
    user.is_active = False
    db_session.commit()
    db_session.refresh(user)
    return user


def set_authenticated_cookies(client: TestClient, user_id: int, session_id: str, role_cookie: str = "Employee"):
    client.cookies.set("is_logged_in", "true")
    client.cookies.set("user_id", str(user_id))
    client.cookies.set("session_id", session_id)
    client.cookies.set("user_role", role_cookie)


def assert_api_error_contract(response, expected_status_code: int):
    assert response.status_code == expected_status_code
    assert response.headers["content-type"].startswith("application/json")
    assert "location" not in response.headers
    payload = response.json()
    assert isinstance(payload, dict)
    assert "detail" in payload
    assert isinstance(payload["detail"], str)
    assert payload["detail"].strip()


def clear_employee_flow_records(db_session, employee_id: int):
    db_session.query(Attendance).filter(Attendance.employee_id == employee_id).delete()
    db_session.query(LeaveRequest).filter(LeaveRequest.employee_id == employee_id).delete()
    db_session.query(OTRequest).filter(OTRequest.employee_id == employee_id).delete()
    db_session.query(PayrollDetail).filter(PayrollDetail.employee_id == employee_id).delete()
    db_session.commit()
