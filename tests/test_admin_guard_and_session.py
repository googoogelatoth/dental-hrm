import pytest

from tests.security_test_utils import (
    client,
    db_session,
    create_user,
    create_inactive_user,
    set_authenticated_cookies,
)


def test_unauthenticated_admin_post_redirects_to_login(client):
    response = client.post("/admin/approve-all-requests", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_role_tampering_cookie_cannot_escalate_admin_post(client, db_session):
    session_id = "employee-real-session"
    employee = create_user(db_session, "sec_emp_001", "Employee", session_id=session_id)

    set_authenticated_cookies(
        client,
        user_id=employee.id,
        session_id=session_id,
        role_cookie="Admin",  # Tampered cookie must not grant admin access.
    )
    client.cookies.set("csrf_token", "valid-token")

    response = client.post(
        "/admin/approve-all-requests",
        data={"csrf_token": "valid-token"},
        follow_redirects=False,
    )

    assert response.status_code == 403


def test_missing_csrf_blocks_authenticated_state_change(client, db_session):
    session_id = "admin-real-session"
    admin = create_user(db_session, "sec_admin_001", "Admin", session_id=session_id)

    set_authenticated_cookies(
        client,
        user_id=admin.id,
        session_id=session_id,
        role_cookie="Admin",
    )

    # No csrf_token cookie and no csrf_token form field.
    response = client.post("/admin/approve-all-requests", data={}, follow_redirects=False)

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid CSRF token"


def test_non_admin_cannot_access_holidays_page(client, db_session):
    session_id = "holiday-employee-session"
    employee = create_user(db_session, "sec_emp_holiday_001", "Employee", session_id=session_id)

    set_authenticated_cookies(
        client,
        user_id=employee.id,
        session_id=session_id,
        role_cookie="Employee",
    )

    response = client.get("/holidays", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"


def test_non_admin_cannot_export_attendance(client, db_session):
    session_id = "export-employee-session"
    employee = create_user(db_session, "sec_emp_export_001", "Employee", session_id=session_id)

    set_authenticated_cookies(
        client,
        user_id=employee.id,
        session_id=session_id,
        role_cookie="Employee",
    )

    response = client.get("/export-attendance", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"


def test_logout_requires_post_method(client):
    response = client.get("/logout", follow_redirects=False)

    assert response.status_code == 405


def test_non_admin_cannot_access_manual_count_api(client, db_session):
    session_id = "manual-count-employee-session"
    employee = create_user(db_session, "sec_emp_manual_count_001", "Employee", session_id=session_id)

    set_authenticated_cookies(
        client,
        user_id=employee.id,
        session_id=session_id,
        role_cookie="Employee",
    )

    response = client.get("/api/manual-requests-count", follow_redirects=False)

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/json")
    assert response.json().get("detail") == "Forbidden"


@pytest.mark.parametrize("path", [
    "/admin/encryption-audit",
    "/admin/calculate-payroll",
    "/admin/approve-ot",
    "/debug/vapid-status",
])
def test_non_admin_blocked_by_centralized_admin_guard(client, db_session, path: str):
    session_id = f"non-admin-guard-{path.split('/')[-1]}"
    employee = create_user(db_session, f"sec_emp_guard_{path.split('/')[-1]}", "Employee", session_id=session_id)

    set_authenticated_cookies(
        client,
        user_id=employee.id,
        session_id=session_id,
        role_cookie="Employee",
    )

    response = client.get(path, follow_redirects=False)

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/json")
    assert response.json().get("detail") == "Forbidden"


@pytest.mark.parametrize("path", [
    "/admin/encryption-audit",
    "/admin/calculate-payroll",
    "/debug/vapid-status",
])
def test_inactive_admin_redirected_to_login_by_guard(client, db_session, path: str):
    session_id = f"inactive-admin-{path.split('/')[-1]}"
    inactive_admin = create_inactive_user(
        db_session,
        f"sec_inactive_admin_{path.split('/')[-1]}",
        "Admin",
        session_id=session_id,
    )

    set_authenticated_cookies(
        client,
        user_id=inactive_admin.id,
        session_id=session_id,
        role_cookie="Admin",
    )

    response = client.get(path, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_admin_can_access_encryption_audit_endpoint(client, db_session):
    session_id = "active-admin-audit"
    admin = create_user(db_session, "sec_admin_audit_001", "Admin", session_id=session_id)

    set_authenticated_cookies(
        client,
        user_id=admin.id,
        session_id=session_id,
        role_cookie="Admin",
    )

    response = client.get("/admin/encryption-audit", follow_redirects=False)

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, dict)
    assert "field_status_summary" in payload
    assert "scanned_employees" in payload
