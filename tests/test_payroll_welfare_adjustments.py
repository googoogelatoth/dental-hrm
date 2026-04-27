from datetime import date, datetime, timedelta

from app.main import calculate_dynamic_payroll_details, _get_approved_leave_dates
from app import models
from tests.security_test_utils import db_session  # noqa: F401


def test_calculate_dynamic_payroll_details_excludes_welfare_and_keeps_adjustments(db_session):
    employee = models.Employee(
        employee_code="payroll_items_emp_001",
        first_name="Payroll",
        last_name="Items",
        role="Staff",
        position="Staff",
        hashed_password="x",
        is_active=True,
        current_session_id="payroll-items-session",
        base_salary=30000,
        position_allowance=1000,
        weekly_off="Sun",
    )
    db_session.add(employee)
    db_session.flush()

    benefit = models.Benefit(
        name="Dental Welfare Test",
        amount=500,
        budget_amount=500,
        is_active=True,
    )
    db_session.add(benefit)
    db_session.flush()

    employee_benefit = models.EmployeeBenefit(
        employee_id=employee.id,
        benefit_id=benefit.id,
        is_active=True,
        initial_amount=500,
        remaining_amount=0,
    )
    db_session.add(employee_benefit)
    db_session.flush()

    db_session.add(models.BenefitTransaction(
        employee_benefit_id=employee_benefit.id,
        amount=500,
        used_at=datetime(2026, 3, 22, 9, 0, 0),
        status="Approved",
    ))

    income_type = models.PayrollAdjustmentType(
        name="Monthly Incentive Test",
        adjustment_kind="income",
        default_amount=300,
        is_active=True,
    )
    deduction_type = models.PayrollAdjustmentType(
        name="Uniform Deduction Test",
        adjustment_kind="deduction",
        default_amount=200,
        is_active=True,
    )
    db_session.add_all([income_type, deduction_type])
    db_session.flush()

    db_session.add_all([
        models.EmployeePayrollAdjustment(
            employee_id=employee.id,
            adjustment_type_id=income_type.id,
            amount=300,
            is_active=True,
        ),
        models.EmployeePayrollAdjustment(
            employee_id=employee.id,
            adjustment_type_id=deduction_type.id,
            amount=200,
            is_active=True,
        ),
    ])
    db_session.commit()

    payroll = calculate_dynamic_payroll_details(
        employee,
        start_date=date(2026, 3, 22),
        end_date=date(2026, 3, 22),
        db=db_session,
        holiday_dates={date(2026, 3, 22)},
        settings={},
        draft=None,
    )

    assert payroll["welfare_total"] == 0
    assert payroll["adjustment_income_total"] == 300
    assert payroll["adjustment_deduction_total"] == 200
    assert payroll["welfare_items"] == []
    assert [item["label"] for item in payroll["adjustment_income_items"]] == ["Monthly Incentive Test"]
    assert [item["label"] for item in payroll["adjustment_deduction_items"]] == ["Uniform Deduction Test"]
    assert payroll["gross_income"] == 31300
    assert payroll["total_deductions"] == 950
    assert payroll["net_salary"] == 30350


def test_get_approved_leave_dates_expands_every_day_in_range(db_session):
    employee = models.Employee(
        employee_code="leave_dates_emp_001",
        first_name="Leave",
        last_name="Dates",
        role="Staff",
        position="Staff",
        hashed_password="x",
        is_active=True,
        current_session_id="leave-dates-session",
    )
    db_session.add(employee)
    db_session.flush()

    db_session.add(models.LeaveRequest(
        employee_id=employee.id,
        leave_type="ลากิจ",
        start_date=date(2026, 4, 10),
        end_date=date(2026, 4, 12),
        reason="approved-leave-window",
        status="Approved",
    ))
    db_session.commit()

    leave_dates = _get_approved_leave_dates(
        db=db_session,
        employee_id=employee.id,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
    )

    assert leave_dates == {
        date(2026, 4, 10),
        date(2026, 4, 11),
        date(2026, 4, 12),
    }


def test_calculate_dynamic_payroll_details_skips_approved_leave_overlap(db_session):
    employee = models.Employee(
        employee_code="leave_overlap_emp_001",
        first_name="Leave",
        last_name="Overlap",
        role="Staff",
        position="Staff",
        hashed_password="x",
        is_active=True,
        current_session_id="leave-overlap-session",
        base_salary=30000,
        position_allowance=0,
        weekly_off="Mon,Tue,Wed,Thu,Fri",
    )
    db_session.add(employee)
    db_session.flush()

    period_start = date(2026, 4, 6)
    period_end = date(2026, 4, 10)

    for idx in range(5):
        day = period_start + timedelta(days=idx)
        db_session.add(models.Attendance(
            employee_id=employee.id,
            date=day,
            late_minutes=60,
            early_minutes=30,
            status="สาย/ออกก่อน",
        ))

    db_session.add(models.LeaveRequest(
        employee_id=employee.id,
        leave_type="ลาป่วย",
        start_date=date(2026, 4, 8),
        end_date=date(2026, 4, 9),
        reason="approved-leave-overlap",
        status="Approved",
    ))
    db_session.commit()

    payroll = calculate_dynamic_payroll_details(
        employee,
        start_date=period_start,
        end_date=period_end,
        db=db_session,
        holiday_dates=set(),
        settings={},
        draft=None,
    )

    assert payroll["paid_days"] == 3
    assert payroll["late_minutes"] == 180
    assert payroll["early_minutes"] == 90
    assert payroll["absent_days"] == 0
    assert payroll["calculated_absent_deduction"] == 0