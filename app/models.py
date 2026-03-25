from sqlalchemy import Column, Integer, String, Text, ForeignKey, Date, DateTime, Float, Time, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime
import enum


# กำหนดสิทธิการใช้งาน
class UserRole(str, enum.Enum):
    ADMIN = "Admin"
    DOCTOR = "Doctor"
    STAFF = "Staff"

class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    employee_code = Column(String, unique=True, index=True) # รหัสพนักงาน
    first_name = Column(String)
    last_name = Column(String)
    nickname = Column(String)
    phone_number = Column(String)
    id_card_number = Column(String, unique=True) # เลขบัตรประชาชน
    address = Column(Text)
    bank_account_number = Column(String)
    
    department = Column(String) # แผนก
    position = Column(String)   # ตำแหน่ง
    role = Column(String, default=UserRole.STAFF) # สิทธิการใช้งาน
    is_active = Column(Boolean, default=True)
    
    hashed_password = Column(String) # สำหรับ Login (เก็บแบบเข้ารหัส)
    profile_picture = Column(String, nullable=True) # เก็บ Path ของรูปถ่าย
    
    # ความสัมพันธ์กับไฟล์เอกสาร (หนึ่งคนมีได้หลายไฟล์)
    documents = relationship("EmployeeDocument", back_populates="owner")
    schedule = relationship("WorkSchedule", back_populates="employee", uselist=False)
    leaves = relationship("LeaveRequest", back_populates="owner")
    
    # เพิ่มส่วนโควตาวันลา (จำนวนวันต่อปี)
    sick_leave_quota = Column(Integer, default=30)      # ลาป่วย (ตามกฎหมาย 30 วัน)
    personal_leave_quota = Column(Integer, default=3)   # ลากิจ
    vacation_leave_quota = Column(Integer, default=6)   # ลาพักร้อน
    working_days = Column(String)  # เก็บเป็น "Mon,Tue,Wed,Thu,Fri"
    weekly_off = Column(String, nullable=True, default="Sun")
    
    base_salary = Column(Float, default=0.0) 
    position_allowance = Column(Float, default=0.0)
    
    attendance = relationship("Attendance", back_populates="employee")
    ot_requests = relationship("OTRequest", back_populates="employee")
    payroll_details = relationship("PayrollDetail", back_populates="employee")
    payroll_adjustments = relationship("EmployeePayrollAdjustment", back_populates="employee", cascade="all, delete-orphan")
    employee_benefits = relationship("EmployeeBenefit", back_populates="employee", cascade="all, delete-orphan")
    current_session_id = Column(String, nullable=True)
    pdpa_accepted = Column(Boolean, default=False)
    subscriptions = relationship("PushSubscription", back_populates="employee", cascade="all, delete")

    # การตั้งค่าการมีส่วนร่วมในระบบ
    enable_schedule = Column(Boolean, default=True)  # มีตารางเวลา/บันทึกการเข้างาน
    enable_payroll = Column(Boolean, default=True)   # คำนวณเงินเดือนและแสดงในรายงาน

class Benefit(Base):
    __tablename__ = "benefits"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    amount = Column(Float, default=0.0)
    description = Column(Text, nullable=True)
    budget_amount = Column(Float, default=0.0)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    is_employee_specific = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    employee_links = relationship("EmployeeBenefit", back_populates="benefit", cascade="all, delete-orphan")


class EmployeeBenefit(Base):
    __tablename__ = "employee_benefits"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    benefit_id = Column(Integer, ForeignKey("benefits.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    # ระบุช่วงเวลาที่สวัสดิการนี้มีผล
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    # จำนวนเงินที่พนักงานได้รับสำหรับสวัสดิการนี้ (ค่าเริ่มต้นมาจาก Benefit.amount แต่เก็บแยกในระดับพนักงานได้)
    initial_amount = Column(Float, default=0.0)
    # จำนวนคงเหลือที่ยังสามารถใช้ได้ (จะถูกลดเมื่อมีการใช้)
    remaining_amount = Column(Float, default=0.0)

    __table_args__ = (
        UniqueConstraint("employee_id", "benefit_id", name="uq_employee_benefit"),
    )

    employee = relationship("Employee", back_populates="employee_benefits")
    benefit = relationship("Benefit", back_populates="employee_links")
    transactions = relationship("BenefitTransaction", back_populates="employee_benefit", cascade="all, delete-orphan")

class EmployeeDocument(Base):
    __tablename__ = "employee_documents"

    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String) # ที่อยู่ไฟล์ PDF ใน Server
    file_name = Column(String) # ชื่อไฟล์ที่แสดง
    employee_id = Column(Integer, ForeignKey("employees.id"))
    
    owner = relationship("Employee", back_populates="documents")

# เพิ่ม Model นี้ใน app/models.py
class Attendance(Base):
    __tablename__ = "attendance"
    
    lat = Column(Float, nullable=True)  # ละติจูด
    lon = Column(Float, nullable=True)  # ลองจิจูด

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    date = Column(Date)                 # วันที่ (YYYY-MM-DD)
    check_in = Column(DateTime)          # เวลาเข้างานจริง
    check_out = Column(DateTime, nullable=True) # เวลาออกงานจริง
    # is_absent = Column(Boolean, default=False)
    status = Column(String)             # เช่น 'Normal', 'Late', 'Early Out'
    late_minutes = Column(Integer, default=0)
    early_minutes = Column(Integer, default=0)
    image_in = Column(String, nullable=True)  # เก็บชื่อไฟล์ภาพตอนเข้างาน
    image_out = Column(String, nullable=True) # เก็บชื่อไฟล์ภาพตอนออกงาน

    employee = relationship("Employee", back_populates="attendance")

class WorkSchedule(Base):
    __tablename__ = "work_schedules"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), unique=True) # 1 คนมี 1 ตารางหลัก
    work_start_time = Column(String, default="09:00")
    work_end_time = Column(String, default="18:00")
    grace_period_late = Column(Integer, default=0)
    grace_period_early_out = Column(Integer, default=0)

    employee = relationship("Employee", back_populates="schedule")
    work_days = Column(String, default="Mon,Tue,Wed,Thu,Fri")

#------------------- Class Leave --------------------------------#
class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    leave_type = Column(String)  # ลาป่วย, ลากิจ, ลาพักร้อน
    start_date = Column(Date)
    end_date = Column(Date)
    reason = Column(Text)
    status = Column(String, default="Pending")  # Pending (รอ), Approved (อนุมัติ), Rejected (ไม่อนุมัติ)
    evidence_path = Column(String, nullable=True)  # เก็บพาธไฟล์ใบรับรองแพทย์ (ถ้ามี)
    created_at = Column(DateTime, default=datetime.now)
    admin_remark = Column(String, nullable=True) # เก็บเหตุผลการปฏิเสธ (null ได้เพราะไม่บังคับ)

    # เชื่อมความสัมพันธ์กลับไปที่ Employee
    owner = relationship("Employee", back_populates="leaves")

class Holiday(Base):
    __tablename__ = "holidays"
    id = Column(Integer, primary_key=True, index=True)
    holiday_date = Column(Date, unique=True, nullable=False) # วันที่หยุด
    holiday_name = Column(String, nullable=False)           # ชื่อวันหยุด เช่น "วันสงกรานต์"
    description = Column(String, nullable=True)             # รายละเอียดเพิ่มเติม

# app/models.py

class ManualAttendanceRequest(Base):
    __tablename__ = "manual_attendance_requests"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    
    # วันที่และเวลาที่ขอแก้ไข
    request_date = Column(Date, nullable=False)  # วันที่ลืมลงเวลา
    check_in_time = Column(Time, nullable=True)  # เวลาเข้าที่ขอ
    check_out_time = Column(Time, nullable=True) # เวลาออกที่ขอ
    
    reason = Column(String)                      # เหตุผลที่ลืม
    status = Column(String, default="Pending")   # Pending, Approved, Rejected
    
    # หลักฐานความโปร่งใส (พิกัดตอนกดยื่นคำขอ)
    request_lat = Column(Float, nullable=True)
    request_lon = Column(Float, nullable=True)
    
    created_at = Column(DateTime, default=datetime.now)
    admin_remark = Column(String, nullable=True) # เก็บเหตุผลการปฏิเสธ (null ได้เพราะไม่บังคับ)

    # เชื่อมโยงกับพนักงาน
    employee = relationship("Employee")

class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    
    # ข้อมูล Endpoint และ Keys ที่ได้จาก Browser
    endpoint = Column(String, unique=True, nullable=False)
    p256dh = Column(String, nullable=False)
    auth = Column(String, nullable=False)
    
    # เก็บข้อมูลอุปกรณ์เบื้องต้น (เผื่อไว้ตรวจสอบ)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    employee = relationship("Employee")


class BenefitTransaction(Base):
    __tablename__ = "benefit_transactions"

    id = Column(Integer, primary_key=True, index=True)
    employee_benefit_id = Column(Integer, ForeignKey("employee_benefits.id"))
    amount = Column(Float, default=0.0)
    trans_date = Column(DateTime, default=datetime.now)
    used_at = Column(DateTime, nullable=True)
    requested_at = Column(DateTime, default=datetime.now)
    status = Column(String, default="Recorded")
    reason = Column(String, nullable=True)
    admin_remark = Column(String, nullable=True)
    approved_by_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)

    employee_benefit = relationship("EmployeeBenefit", back_populates="transactions")
    approved_by = relationship("Employee", foreign_keys=[approved_by_id])


class PayrollAdjustmentType(Base):
    __tablename__ = "payroll_adjustment_types"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    adjustment_kind = Column(String, nullable=False)  # income | deduction
    description = Column(Text, nullable=True)
    default_amount = Column(Float, default=0.0)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True)

    employee_assignments = relationship("EmployeePayrollAdjustment", back_populates="adjustment_type", cascade="all, delete-orphan")


class EmployeePayrollAdjustment(Base):
    __tablename__ = "employee_payroll_adjustments"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    adjustment_type_id = Column(Integer, ForeignKey("payroll_adjustment_types.id"), nullable=False)
    amount = Column(Float, default=0.0)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    note = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)

    employee = relationship("Employee", back_populates="payroll_adjustments")
    adjustment_type = relationship("PayrollAdjustmentType", back_populates="employee_assignments")
    payroll_line_items = relationship("PayrollLineItem", back_populates="employee_adjustment")

# ตัวอย่าง Model สำหรับเก็บข้อมูลการจ่ายเงินรายเดือน
class PayrollDetail(Base):
    __tablename__ = "payroll_details"
    
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    month = Column(Integer)
    year = Column(Integer)
    
    # รายได้ (Earnings)
    salary = Column(Float) # ฐานเงินเดือน
    position_allowance = Column(Float, default=0) # ค่าตำแหน่ง
    overtime_pay = Column(Float, default=0) # ค่า OT
    other_allowances = Column(Float, default=0) # ค่าเบี้ยเลี้ยง/อื่นๆ
    
    # รายการหัก (Deductions) - ปรับให้เป็นช่องกรอกตามที่คุณต้องการ
    sso = Column(Float, default=0.0)
    sso_amount = Column(Float) # ประกันสังคม (กรอกเองหรือแก้ไขได้)
    tax = Column(Float, default=0.0)
    income_tax = Column(Float) # ภาษีหัก ณ ที่จ่าย (กรอกเองหรือแก้ไขได้)
    absence_deduction = Column(Float, default=0) # หักขาดงาน
    extra_income = Column(Float, default=0.0)    # สำหรับรายได้อื่นๆ
    extra_deduction = Column(Float, default=0.0) # สำหรับรายจ่ายอื่นๆ
    late_deduction = Column(Float, default=0.0)  # เพิ่มตัวนี้
    early_deduction = Column(Float, default=0.0) # เพิ่มตัวนี้
    status = Column(String, default="Draft")     # เพิ่มตัวนี้
    
    net_salary = Column(Float) # เงินเดือนสุทธิ
    net_total = Column(Float)
    ot_pay = Column(Float, default=0.0)
    calc_start_date = Column(Date, nullable=True) # 🚩 เพิ่มเพื่อเก็บวันที่เริ่มคำนวณรายคน
    calc_end_date = Column(Date, nullable=True)   # 🚩 เพิ่มเพื่อเก็บวันที่จบคำนวณรายคน
    
    employee = relationship("Employee", back_populates="payroll_details")
    line_items = relationship("PayrollLineItem", back_populates="payroll_detail", cascade="all, delete-orphan")


class PayrollLineItem(Base):
    __tablename__ = "payroll_line_items"

    id = Column(Integer, primary_key=True, index=True)
    payroll_detail_id = Column(Integer, ForeignKey("payroll_details.id"), nullable=False)
    item_type = Column(String, nullable=False)  # earning | deduction
    source_type = Column(String, nullable=False)  # salary | overtime | welfare | adjustment | manual | statutory | attendance
    code = Column(String, nullable=True)
    label = Column(String, nullable=False)
    amount = Column(Float, default=0.0)
    sort_order = Column(Integer, default=0)
    benefit_transaction_id = Column(Integer, ForeignKey("benefit_transactions.id"), nullable=True)
    employee_adjustment_id = Column(Integer, ForeignKey("employee_payroll_adjustments.id"), nullable=True)

    payroll_detail = relationship("PayrollDetail", back_populates="line_items")
    employee_adjustment = relationship("EmployeePayrollAdjustment", back_populates="payroll_line_items")
    
class OTRequest(Base):
    __tablename__ = "ot_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    employee = relationship("Employee", back_populates="ot_requests")
    request_date = Column(Date) # วันที่ทำ OT
    start_time = Column(Time)
    end_time = Column(Time)
    total_minutes = Column(Integer) # ระบบคำนวณจากเวลาให้เอง
    ot_type = Column(String) # เช่น 'ot_1_5', 'ot_2_0', 'ot_3_0'
    reason = Column(String)
    status = Column(String, default="pending") # pending, approved, rejected
    admin_remark = Column(String, nullable=True) # เก็บเหตุผลการปฏิเสธ (null ได้เพราะไม่บังคับ)

# Overtime class removed - duplicate of OTRequest functionality

class PayrollSetting(Base):
    __tablename__ = "payroll_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    type_name = Column(String, unique=True)  # เช่น 'late', 'absent', 'ot_1_5', 'ot_3'
    label = Column(String)                  # ชื่อแสดงผล เช่น "หักสาย", "OT 1.5 เท่า"
    base_on_salary = Column(Boolean, default=True) # ใช้เงินเดือนพื้นฐานคำนวณไหม
    divider_days = Column(Integer, default=30)     # ตัวหารวัน
    divider_hours = Column(Integer, default=8)    # ตัวหารชั่วโมง
    multiplier = Column(Float, default=1.0)        # ตัวคูณ (1.5, 3.0, หรือ 1.0 สำหรับหักเงิน)

class CompanySetting(Base):
    __tablename__ = "company_settings"
    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String)
    address = Column(Text)
    logo_path = Column(String)  # เก็บชื่อไฟล์โลโก้

# UserSubscription class removed - duplicate of PushSubscription
    
class ActivityLog(Base):
    __tablename__ = "activity_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer)
    user_name = Column(String)
    action = Column(String)
    details = Column(String)
    ip_address = Column(String)
    # ✅ ลบ default=datetime.now ออก เพื่อให้รับค่าที่เราส่งไปจาก Python ตรงๆ
    timestamp = Column(DateTime) 
    # หรือถ้าอยากมี created_at อีกตัวก็ทำเหมือนกันครับ
    created_at = Column(DateTime)