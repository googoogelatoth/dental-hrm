from datetime import date, time

from app.models import ManualAttendanceRequest, PayrollDetail, PayrollSetting
from tests.security_test_utils import client, db_session, create_user, set_authenticated_cookies


def test_admin_can_import_attendance_csv_happy_path(client, db_session):
    session_id = "admin-import-attendance"
    admin = create_user(db_session, "sec_admin_import_001", "Admin", session_id=session_id)
    employee = create_user(db_session, "sec_emp_import_001", "Employee", session_id="emp-import-session")

    db_session.query(ManualAttendanceRequest).filter(
        ManualAttendanceRequest.employee_id == employee.id
    ).delete()
    db_session.commit()

    set_authenticated_cookies(
        client,
        user_id=admin.id,
        session_id=session_id,
        role_cookie="Admin",
    )
    client.cookies.set("csrf_token", "valid-token")

    csv_content = (
        "work_date,employee_code,col2,check_in,col4,check_out\n"
        "2031-04-15,sec_emp_import_001,x,08:30,x,17:45\n"
    )

    response = client.post(
        "/import-attendance-upload",
        data={"csrf_token": "valid-token"},
        files={"file": ("attendance_import.csv", csv_content, "text/csv")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/admin/attendance-requests?msg=import_success")

    imported = db_session.query(ManualAttendanceRequest).filter(
        ManualAttendanceRequest.employee_id == employee.id,
        ManualAttendanceRequest.request_date == date(2031, 4, 15),
        ManualAttendanceRequest.status == "Pending",
    ).first()

    assert imported is not None
    assert imported.reason == "Imported from attendance_import.csv"
    assert imported.check_in_time == time(8, 30)
    assert imported.check_out_time == time(17, 45)


def test_import_attendance_invalid_date_returns_error_and_no_insert(client, db_session):
    session_id = "admin-import-invalid-date"
    admin = create_user(db_session, "sec_admin_import_invalid_001", "Admin", session_id=session_id)
    employee = create_user(db_session, "sec_emp_import_invalid_001", "Employee", session_id="emp-import-invalid")

    db_session.query(ManualAttendanceRequest).filter(
        ManualAttendanceRequest.employee_id == employee.id
    ).delete()
    db_session.commit()

    set_authenticated_cookies(
        client,
        user_id=admin.id,
        session_id=session_id,
        role_cookie="Admin",
    )
    client.cookies.set("csrf_token", "valid-token")

    csv_content = (
        "work_date,employee_code,col2,check_in,col4,check_out\n"
        "not-a-date,sec_emp_import_invalid_001,x,08:30,x,17:45\n"
    )

    response = client.post(
        "/import-attendance-upload",
        data={"csrf_token": "valid-token"},
        files={"file": ("attendance_invalid.csv", csv_content, "text/csv")},
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.json()
    assert "error" in payload
    assert "เกิดข้อผิดพลาดในการนำเข้า" in payload["error"]

    imported = db_session.query(ManualAttendanceRequest).filter(
        ManualAttendanceRequest.employee_id == employee.id
    ).all()
    assert imported == []


def test_import_attendance_unknown_employee_skips_row_and_still_redirects_success(client, db_session):
    session_id = "admin-import-unknown-employee"
    admin = create_user(db_session, "sec_admin_import_unknown_001", "Admin", session_id=session_id)

    set_authenticated_cookies(
        client,
        user_id=admin.id,
        session_id=session_id,
        role_cookie="Admin",
    )
    client.cookies.set("csrf_token", "valid-token")

    csv_content = (
        "work_date,employee_code,col2,check_in,col4,check_out\n"
        "2031-04-16,unknown_emp_code,x,08:30,x,17:45\n"
    )

    response = client.post(
        "/import-attendance-upload",
        data={"csrf_token": "valid-token"},
        files={"file": ("attendance_unknown_employee.csv", csv_content, "text/csv")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/admin/attendance-requests?msg=import_success")

    inserted = db_session.query(ManualAttendanceRequest).filter(
        ManualAttendanceRequest.reason == "Imported from attendance_unknown_employee.csv"
    ).all()
    assert inserted == []


def test_admin_can_save_payroll_settings_happy_path(client, db_session):
    session_id = "admin-save-payroll-settings"
    admin = create_user(db_session, "sec_admin_payroll_001", "Admin", session_id=session_id)

    set_authenticated_cookies(
        client,
        user_id=admin.id,
        session_id=session_id,
        role_cookie="Admin",
    )
    client.cookies.set("csrf_token", "valid-token")

    response = client.post(
        "/admin/save-payroll-settings",
        data={
            "csrf_token": "valid-token",
            "late_days": "30",
            "late_hours": "8",
            "absent_days": "30",
            "ot_1_5_days": "30",
            "ot_1_5_hours": "8",
            "ot_1_5_mult": "1.5",
            "ot_1_mult": "1.0",
            "ot_2_mult": "2.0",
            "ot_3_mult": "3.0",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/payroll-settings?msg=success"

    settings = {
        row.type_name: row
        for row in db_session.query(PayrollSetting).filter(
            PayrollSetting.type_name.in_(["late", "absent", "ot_1_5", "ot_1_0", "ot_2_0", "ot_3_0"])
        ).all()
    }

    assert len(settings) == 6
    assert settings["late"].multiplier == 1.0
    assert settings["absent"].divider_hours == 0
    assert settings["ot_1_5"].multiplier == 1.5
    assert settings["ot_1_0"].multiplier == 1.0
    assert settings["ot_2_0"].multiplier == 2.0
    assert settings["ot_3_0"].multiplier == 3.0


def test_save_payroll_settings_missing_required_field_returns_422(client, db_session):
    session_id = "admin-save-payroll-settings-422"
    admin = create_user(db_session, "sec_admin_payroll_422_001", "Admin", session_id=session_id)

    set_authenticated_cookies(
        client,
        user_id=admin.id,
        session_id=session_id,
        role_cookie="Admin",
    )
    client.cookies.set("csrf_token", "valid-token")

    response = client.post(
        "/admin/save-payroll-settings",
        data={
            "csrf_token": "valid-token",
            "late_days": "30",
            "late_hours": "8",
            "absent_days": "30",
            "ot_1_5_days": "30",
            "ot_1_5_hours": "8",
            # Intentionally missing required ot_1_5_mult
            "ot_1_mult": "1.0",
            "ot_2_mult": "2.0",
            "ot_3_mult": "3.0",
        },
        follow_redirects=False,
    )

    assert response.status_code == 422


def test_admin_can_process_payroll_save_draft_happy_path(client, db_session):
    session_id = "admin-process-payroll"
    admin = create_user(db_session, "sec_admin_process_payroll_001", "Admin", session_id=session_id)
    employee = create_user(db_session, "sec_emp_process_payroll_001", "Employee", session_id="emp-process-payroll")

    employee.base_salary = 15000
    employee.position_allowance = 1500
    employee.weekly_off = "Mon,Tue,Wed,Thu,Fri"
    db_session.commit()

    db_session.query(PayrollDetail).filter(PayrollDetail.employee_id == employee.id).delete()
    db_session.commit()

    set_authenticated_cookies(
        client,
        user_id=admin.id,
        session_id=session_id,
        role_cookie="Admin",
    )
    client.cookies.set("csrf_token", "valid-token")

    start_date = "2031-05-01"
    end_date = "2031-05-31"
    response = client.post(
        "/admin/process-payroll",
        data={
            "csrf_token": "valid-token",
            "action": "save_draft",
            "start_date": start_date,
            "end_date": end_date,
            "emp_ids": str(employee.id),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith(
        f"/admin/calculate-payroll?start_date={start_date}&end_date={end_date}&msg=draft_saved"
    )

    payroll_row = db_session.query(PayrollDetail).filter(
        PayrollDetail.employee_id == employee.id,
        PayrollDetail.month == 5,
        PayrollDetail.year == 2031,
    ).first()

    assert payroll_row is not None
    assert payroll_row.status == "Draft"
    assert payroll_row.calc_start_date == date(2031, 5, 1)
    assert payroll_row.calc_end_date == date(2031, 5, 31)


def test_process_payroll_missing_action_returns_422_and_no_row(client, db_session):
    session_id = "admin-process-payroll-missing-action"
    admin = create_user(db_session, "sec_admin_process_missing_001", "Admin", session_id=session_id)
    employee = create_user(db_session, "sec_emp_process_missing_001", "Employee", session_id="emp-process-missing")

    db_session.query(PayrollDetail).filter(PayrollDetail.employee_id == employee.id).delete()
    db_session.commit()

    set_authenticated_cookies(
        client,
        user_id=admin.id,
        session_id=session_id,
        role_cookie="Admin",
    )
    client.cookies.set("csrf_token", "valid-token")

    response = client.post(
        "/admin/process-payroll",
        data={
            "csrf_token": "valid-token",
            "start_date": "2031-05-01",
            "end_date": "2031-05-31",
            "emp_ids": str(employee.id),
        },
        follow_redirects=False,
    )

    assert response.status_code == 422

    payroll_rows = db_session.query(PayrollDetail).filter(
        PayrollDetail.employee_id == employee.id,
        PayrollDetail.month == 5,
        PayrollDetail.year == 2031,
    ).all()
    assert payroll_rows == []
