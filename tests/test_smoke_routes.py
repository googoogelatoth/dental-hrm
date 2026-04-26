from app.models import PayrollDetail
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

    assert response.status_code == 303
    assert "msg=insufficient_role" in response.headers["location"]


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


def test_admin_can_open_adjustments_page(client, db_session):
    session_id = "smoke-adjustments-admin-session"
    admin = create_user(db_session, "smoke_admin_adjust_001", "Admin", session_id=session_id)

    set_authenticated_cookies(
        client,
        user_id=admin.id,
        session_id=session_id,
        role_cookie="Admin",
    )

    response = client.get("/admin/payroll-adjustments", follow_redirects=False)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_admin_can_open_payslip_from_payroll_summary(client, db_session):
    session_id = "smoke-payslip-admin-session"
    admin = create_user(db_session, "smoke_admin_payslip_001", "Admin", session_id=session_id)
    employee = create_user(db_session, "smoke_emp_payslip_001", "Employee", session_id="smoke-payslip-employee-session")

    payroll = db_session.query(PayrollDetail).filter(
        PayrollDetail.employee_id == employee.id,
        PayrollDetail.month == 4,
        PayrollDetail.year == 2031,
    ).first()
    if payroll is None:
        payroll = PayrollDetail(
            employee_id=employee.id,
            month=4,
            year=2031,
            salary=12000,
            position_allowance=1000,
            ot_pay=0,
            other_allowances=0,
            extra_income=0,
            extra_deduction=0,
            absence_deduction=0,
            late_deduction=0,
            early_deduction=0,
            sso=0,
            tax=0,
            net_salary=13000,
            net_total=None,
            status="Finalized",
        )
        db_session.add(payroll)
        db_session.commit()
        db_session.refresh(payroll)

    set_authenticated_cookies(
        client,
        user_id=admin.id,
        session_id=session_id,
        role_cookie="Admin",
    )

    response = client.get(f"/admin/payslip/{payroll.id}", follow_redirects=False)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "13,000.00" in response.text
