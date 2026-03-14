from datetime import date, time

from app.models import OTRequest
from tests.security_test_utils import (
    client,
    db_session,
    clear_employee_flow_records,
    create_user,
    set_authenticated_cookies,
)


def _post_ot_request(client, request_date: str, start_time: str, end_time: str):
    return client.post(
        "/request-ot",
        data={
            "request_date": request_date,
            "start_time": start_time,
            "end_time": end_time,
            "ot_type": "ot_1_5",
            "reason": "test-overlap",
            "csrf_token": "valid-token",
        },
        follow_redirects=False,
    )


def test_request_ot_blocks_duplicate_time_slot(client, db_session):
    user = create_user(db_session, "sec_emp_ot_overlap_01", "Employee", session_id="ot-overlap-session-01")
    clear_employee_flow_records(db_session, user.id)

    set_authenticated_cookies(client, user_id=user.id, session_id="ot-overlap-session-01", role_cookie="Employee")
    client.cookies.set("csrf_token", "valid-token")

    first = _post_ot_request(client, "2031-01-03", "19:00", "20:00")
    second = _post_ot_request(client, "2031-01-03", "19:00", "20:00")

    assert first.status_code == 303
    assert first.headers.get("location") == "/my-ot-requests?msg=success"
    assert second.status_code == 303
    assert second.headers.get("location") == "/request-ot?msg=overlap_time"

    rows = (
        db_session.query(OTRequest)
        .filter(
            OTRequest.employee_id == user.id,
            OTRequest.request_date == date(2031, 1, 3),
        )
        .all()
    )
    assert len(rows) == 1


def test_request_ot_blocks_partial_overlap_with_existing_pending_or_approved(client, db_session):
    user = create_user(db_session, "sec_emp_ot_overlap_02", "Employee", session_id="ot-overlap-session-02")
    clear_employee_flow_records(db_session, user.id)

    db_session.add(
        OTRequest(
            employee_id=user.id,
            request_date=date(2031, 1, 4),
            start_time=time(19, 0),
            end_time=time(20, 0),
            total_minutes=60,
            ot_type="ot_1_5",
            reason="existing-approved",
            status="approved",
        )
    )
    db_session.commit()

    set_authenticated_cookies(client, user_id=user.id, session_id="ot-overlap-session-02", role_cookie="Employee")
    client.cookies.set("csrf_token", "valid-token")

    response = _post_ot_request(client, "2031-01-04", "19:30", "20:30")

    assert response.status_code == 303
    assert response.headers.get("location") == "/request-ot?msg=overlap_time"

    rows = (
        db_session.query(OTRequest)
        .filter(
            OTRequest.employee_id == user.id,
            OTRequest.request_date == date(2031, 1, 4),
        )
        .all()
    )
    assert len(rows) == 1


def test_request_ot_allows_adjacent_non_overlapping_slot(client, db_session):
    user = create_user(db_session, "sec_emp_ot_overlap_03", "Employee", session_id="ot-overlap-session-03")
    clear_employee_flow_records(db_session, user.id)

    db_session.add(
        OTRequest(
            employee_id=user.id,
            request_date=date(2031, 1, 5),
            start_time=time(19, 0),
            end_time=time(20, 0),
            total_minutes=60,
            ot_type="ot_1_5",
            reason="existing-pending",
            status="pending",
        )
    )
    db_session.commit()

    set_authenticated_cookies(client, user_id=user.id, session_id="ot-overlap-session-03", role_cookie="Employee")
    client.cookies.set("csrf_token", "valid-token")

    response = _post_ot_request(client, "2031-01-05", "20:00", "21:00")

    assert response.status_code == 303
    assert response.headers.get("location") == "/my-ot-requests?msg=success"

    rows = (
        db_session.query(OTRequest)
        .filter(
            OTRequest.employee_id == user.id,
            OTRequest.request_date == date(2031, 1, 5),
        )
        .all()
    )
    assert len(rows) == 2
