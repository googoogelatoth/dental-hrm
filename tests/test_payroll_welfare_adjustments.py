from datetime import date, datetime

from app.main import calculate_dynamic_payroll_details
from app import models
from tests.security_test_utils import db_session  # noqa: F401


def test_calculate_dynamic_payroll_details_includes_welfare_and_adjustments(db_session):
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

    assert payroll["welfare_total"] == 500
    assert payroll["adjustment_income_total"] == 300
    assert payroll["adjustment_deduction_total"] == 200
    assert [item["label"] for item in payroll["welfare_items"]] == ["Dental Welfare Test"]
    assert [item["label"] for item in payroll["adjustment_income_items"]] == ["Monthly Incentive Test"]
    assert [item["label"] for item in payroll["adjustment_deduction_items"]] == ["Uniform Deduction Test"]
    assert payroll["gross_income"] == 31800
    assert payroll["total_deductions"] == 950
    assert payroll["net_salary"] == 30850