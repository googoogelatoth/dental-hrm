"""
🔧 Script รีคำนวณ late_minutes และ early_minutes ทั้งหมด
สำหรับข้อมูล Attendance ในช่วงเวลาที่กำหนด
"""
from datetime import datetime, date
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app import models

def recalculate_attendance_period(start_date: date, end_date: date):
    db: Session = SessionLocal()
    
    try:
        # 1. ดึงข้อมูล Attendance ในช่วงเวลาที่กำหนด
        attendances = db.query(models.Attendance).filter(
            models.Attendance.date >= start_date,
            models.Attendance.date <= end_date
        ).all()
        
        print(f"🔍 พบข้อมูล Attendance: {len(attendances)} รายการ")
        print(f"📅 ช่วงเวลา: {start_date} ถึง {end_date}")
        print("=" * 80)
        
        updated_count = 0
        
        for attendance in attendances:
            # 2. ดึงข้อมูลพนักงานและตารางเวลา
            emp = db.query(models.Employee).get(attendance.employee_id)
            if not emp or not emp.schedule:
                continue
            
            sched = emp.schedule
            current_day = attendance.date
            
            # 3. เก็บค่าเก่าไว้เทียบ
            old_late = attendance.late_minutes
            old_early = attendance.early_minutes
            old_status = attendance.status
            
            # 4. รีเซ็ตค่า
            attendance.late_minutes = 0
            attendance.early_minutes = 0
            attendance.status = "ปกติ"
            
            # 5. คำนวณใหม่
            # --- กรณี: ไม่ลงเวลาเข้า ---
            if not attendance.check_in and attendance.check_out:
                attendance.status = "ไม่ลงเวลาเข้า"
            
            # --- กรณี: สาย (Late) ---
            elif attendance.check_in and sched.work_start_time:
                target_in = datetime.strptime(sched.work_start_time[:5], "%H:%M").time()
                actual_in = attendance.check_in.time()
                if actual_in > target_in:
                    diff_in = datetime.combine(current_day, actual_in) - datetime.combine(current_day, target_in)
                    late_mins = int(diff_in.total_seconds() / 60)
                    if late_mins > (sched.grace_period_late or 0):
                        attendance.late_minutes = late_mins
                        attendance.status = "สาย"

            # --- กรณี: ออกก่อนเวลา (Early Out) ---
            if attendance.check_out and sched.work_end_time:
                target_out = datetime.strptime(sched.work_end_time[:5], "%H:%M").time()
                actual_out = attendance.check_out.time()
                if actual_out < target_out:
                    diff_out = datetime.combine(current_day, target_out) - datetime.combine(current_day, actual_out)
                    early_mins = int(diff_out.total_seconds() / 60)
                    if early_mins > (sched.grace_period_early_out or 0):
                        attendance.early_minutes = early_mins
                        if attendance.status == "สาย":
                            attendance.status = "สาย/ออกก่อน"
                        else:
                            attendance.status = "ออกก่อนเวลา"

            # กรณีลืมลงเวลาออก
            if attendance.check_in and not attendance.check_out:
                attendance.status = "ยังไม่ลงเวลาออก"
            
            # 6. แสดงผลเฉพาะที่มีการเปลี่ยนแปลง
            if old_late != attendance.late_minutes or old_early != attendance.early_minutes or old_status != attendance.status:
                print(f"✏️  Employee: {emp.employee_code}, Date: {attendance.date}")
                print(f"   เดิม: สาย={old_late}นาที, ออกก่อน={old_early}นาที, สถานะ={old_status}")
                print(f"   ใหม่: สาย={attendance.late_minutes}นาที, ออกก่อน={attendance.early_minutes}นาที, สถานะ={attendance.status}")
                updated_count += 1
        
        # 7. บันทึกการเปลี่ยนแปลง
        db.commit()
        print("=" * 80)
        print(f"✅ รีคำนวณเรียบร้อย: อัพเดท {updated_count} รายการจากทั้งหมด {len(attendances)} รายการ")
        
    except Exception as e:
        db.rollback()
        print(f"❌ เกิดข้อผิดพลาด: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    print("=" * 80)
    print("🔧 รีคำนวณ late_minutes และ early_minutes ทั้งหมด")
    print("=" * 80)
    
    # กำหนดช่วงเวลา payroll (26/02/2026 - 05/03/2026)
    start = date(2026, 2, 26)
    end = date(2026, 3, 5)
    
    print(f"\n📅 ช่วงเวลา: {start} ถึง {end}")
    confirm = input("⚠️  ต้องการดำเนินการต่อหรือไม่? (yes/no): ")
    
    if confirm.lower() in ['yes', 'y']:
        recalculate_attendance_period(start, end)
    else:
        print("❌ ยกเลิกการดำเนินการ")
