from datetime import date, time

import pytest

from app.models import Attendance, LeaveRequest, OTRequest, PayrollDetail
from tests.security_test_utils import (
    client,
    db_session,
    assert_api_error_contract,
    clear_employee_flow_records,
    create_inactive_user,
    create_user,
    set_authenticated_cookies,
)


def test_api_unauthenticated_returns_json_401_not_redirect(client):
    response = client.get("/api/manual-requests-count", follow_redirects=False)

    assert_api_error_contract(response, 401)


def test_pending_approvals_api_unauthenticated_returns_json_401_not_redirect(client):
    response = client.get("/api/pending-approvals-count", follow_redirects=False)

    assert_api_error_contract(response, 401)


@pytest.mark.parametrize("path,payload", [
    ("/api/accept-pdpa", {"accepted": True}),
    (
        "/api/save-subscription",
        {
            "endpoint": "https://example.push.service/sub/123",
            "keys": {"p256dh": "p256dh-key", "auth": "auth-key"},
        },
    ),
])
def test_api_endpoints_unauthenticated_return_json_401_contract(client, path: str, payload: dict):
    response = client.post(path, json=payload, follow_redirects=False)

    assert_api_error_contract(response, 401)


@pytest.mark.parametrize("path,payload", [
    ("/api/accept-pdpa", {"accepted": True}),
    (
        "/api/save-subscription",
        {
            "endpoint": "https://example.push.service/sub/403",
            "keys": {"p256dh": "p256dh-key", "auth": "auth-key"},
        },
    ),
])
def test_api_endpoints_inactive_user_return_json_403_contract(
    client,
    db_session,
    path: str,
    payload: dict,
):
    session_id = "inactive-api-session"
    inactive_user = create_inactive_user(db_session, f"sec_inactive_{path.split('/')[-1]}", "Employee", session_id=session_id)

    set_authenticated_cookies(client, user_id=inactive_user.id, session_id=session_id, role_cookie="Employee")
    client.cookies.set("csrf_token", "valid-token")

    response = client.post(
        path,
        json=payload,
        headers={"x-csrf-token": "valid-token"},
        follow_redirects=False,
    )

    assert_api_error_contract(response, 403)


def test_check_in_ignores_tampered_user_name_cookie(client, db_session):
    attacker = create_user(db_session, "sec_emp_checkin_attacker", "Employee", session_id="checkin-attacker-session")
    victim = create_user(db_session, "sec_emp_checkin_victim", "Employee", session_id="checkin-victim-session")
    clear_employee_flow_records(db_session, attacker.id)
    clear_employee_flow_records(db_session, victim.id)

    set_authenticated_cookies(client, user_id=attacker.id, session_id="checkin-attacker-session", role_cookie="Employee")
    client.cookies.set("user_name", victim.employee_code)
    client.cookies.set("csrf_token", "valid-token")

    response = client.post(
        "/attendance/check-in",
        data={"lat": "13.7563", "lon": "100.5018", "image_data": "", "csrf_token": "valid-token"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    attacker_record = db_session.query(Attendance).filter(Attendance.employee_id == attacker.id).first()
    victim_record = db_session.query(Attendance).filter(Attendance.employee_id == victim.id).first()
    assert attacker_record is not None
    assert victim_record is None


def test_my_leaves_ignores_tampered_user_name_cookie(client, db_session):
    attacker = create_user(db_session, "sec_emp_leave_attacker", "Employee", session_id="leave-attacker-session")
    victim = create_user(db_session, "sec_emp_leave_victim", "Employee", session_id="leave-victim-session")
    clear_employee_flow_records(db_session, attacker.id)
    clear_employee_flow_records(db_session, victim.id)

    db_session.add(
        LeaveRequest(
            employee_id=attacker.id,
            leave_type="ลากิจ",
            start_date=date(2031, 1, 10),
            end_date=date(2031, 1, 10),
            reason="attacker-leave-entry",
            status="Pending",
        )
    )
    db_session.add(
        LeaveRequest(
            employee_id=victim.id,
            leave_type="ลาป่วย",
            start_date=date(2031, 1, 11),
            end_date=date(2031, 1, 11),
            reason="victim-leave-entry",
            status="Pending",
        )
    )
    db_session.commit()

    set_authenticated_cookies(client, user_id=attacker.id, session_id="leave-attacker-session", role_cookie="Employee")
    client.cookies.set("user_name", victim.employee_code)

    response = client.get("/my-leaves", follow_redirects=False)

    assert response.status_code == 200
    assert "attacker-leave-entry" in response.text
    assert "victim-leave-entry" not in response.text


def test_my_ot_requests_ignores_tampered_id_cookie(client, db_session):
    attacker = create_user(db_session, "sec_emp_ot_attacker", "Employee", session_id="ot-attacker-session")
    victim = create_user(db_session, "sec_emp_ot_victim", "Employee", session_id="ot-victim-session")
    clear_employee_flow_records(db_session, attacker.id)
    clear_employee_flow_records(db_session, victim.id)

    db_session.add(
        OTRequest(
            employee_id=attacker.id,
            request_date=date(2031, 1, 1),
            start_time=time(18, 0),
            end_time=time(19, 17),
            total_minutes=77,
            ot_type="ot_1_5",
            reason="attacker-entry",
            status="pending",
        )
    )
    db_session.add(
        OTRequest(
            employee_id=victim.id,
            request_date=date(2031, 1, 2),
            start_time=time(20, 0),
            end_time=time(21, 0),
            total_minutes=60,
            ot_type="ot_1_5",
            reason="victim-entry",
            status="pending",
        )
    )
    db_session.commit()

    set_authenticated_cookies(client, user_id=attacker.id, session_id="ot-attacker-session", role_cookie="Employee")
    client.cookies.set("id", str(victim.id))

    response = client.get("/my-ot-requests", follow_redirects=False)

    assert response.status_code == 200
    assert "01/01/2031" in response.text
    assert "02/01/2031" not in response.text


def test_my_payslips_ignores_tampered_id_cookie(client, db_session):
    attacker = create_user(db_session, "sec_emp_payslip_attacker", "Employee", session_id="payslip-attacker-session")
    victim = create_user(db_session, "sec_emp_payslip_victim", "Employee", session_id="payslip-victim-session")
    clear_employee_flow_records(db_session, attacker.id)
    clear_employee_flow_records(db_session, victim.id)

    db_session.add(
        PayrollDetail(
            employee_id=attacker.id,
            month=3,
            year=2026,
            salary=11111,
            net_salary=11111,
            net_total=11111,
        )
    )
    db_session.add(
        PayrollDetail(
            employee_id=victim.id,
            month=3,
            year=2026,
            salary=99999,
            net_salary=99999,
            net_total=99999,
        )
    )
    db_session.commit()

    set_authenticated_cookies(client, user_id=attacker.id, session_id="payslip-attacker-session", role_cookie="Employee")
    client.cookies.set("id", str(victim.id))

    response = client.get("/my-payslips?month=3&year=2026", follow_redirects=False)

    assert response.status_code == 200
    assert attacker.employee_code in response.text
    assert victim.employee_code not in response.text
