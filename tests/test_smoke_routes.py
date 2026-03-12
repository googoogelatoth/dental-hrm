from tests.security_test_utils import client, db_session, create_user, set_authenticated_cookies


def test_login_page_renders_html(client):
    response = client.get("/login", follow_redirects=False)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_dashboard_requires_authenticated_session(client):
    response = client.get("/dashboard", follow_redirects=False)

    assert response.status_code in (302, 303, 307)
    assert response.headers["location"].startswith("/login")


def test_dashboard_renders_for_authenticated_employee(client, db_session):
    session_id = "smoke-dashboard-employee-session"
    employee = create_user(db_session, "smoke_emp_dashboard_001", "Employee", session_id=session_id)

    set_authenticated_cookies(
        client,
        user_id=employee.id,
        session_id=session_id,
        role_cookie="Employee",
    )

    response = client.get("/dashboard", follow_redirects=False)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_admin_payroll_page_requires_admin_role(client, db_session):
    session_id = "smoke-payroll-employee-session"
    employee = create_user(db_session, "smoke_emp_payroll_001", "Employee", session_id=session_id)

    set_authenticated_cookies(
        client,
        user_id=employee.id,
        session_id=session_id,
        role_cookie="Employee",
    )

    response = client.get("/admin/calculate-payroll", follow_redirects=False)

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/json")


def test_admin_can_open_payroll_page(client, db_session):
    session_id = "smoke-payroll-admin-session"
    admin = create_user(db_session, "smoke_admin_payroll_001", "Admin", session_id=session_id)

    set_authenticated_cookies(
        client,
        user_id=admin.id,
        session_id=session_id,
        role_cookie="Admin",
    )

    response = client.get("/admin/calculate-payroll", follow_redirects=False)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
