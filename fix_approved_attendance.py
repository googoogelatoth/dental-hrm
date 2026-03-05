"""
🔧 Script แก้ไขข้อมูล Attendance ที่อนุมัติไปแล้ว
คำนวณค่า late_minutes และ early_minutes ใหม่สำหรับคำขอที่ Approved แล้ว
"""
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import engine, SessionLocal
from app import models

def recalculate_approved_attendance():
    db: Session = SessionLocal()
    
    try:
        # 1. หาคำขอทั้งหมดที่ Approved แล้ว
        approved_requests = db.query(models.ManualAttendanceRequest).filter(
            models.ManualAttendanceRequest.status == "Approved"
        ).all()
        
        print(f"🔍 พบคำขอที่ Approved แล้ว: {len(approved_requests)} รายการ")
        
        updated_count = 0
        
        for req in approved_requests:
            # 2. ดึง attendance record ที่เกี่ยวข้อง
            attendance = db.query(models.Attendance).filter(
                models.Attendance.employee_id == req.employee_id,
                models.Attendance.date == req.request_date
            ).first()
            
            if not attendance:
                print(f"⚠️  ไม่พบ attendance record สำหรับ employee_id={req.employee_id}, date={req.request_date}")
                continue
                
            # 3. ดึงข้อมูลพนักงานและตารางเวลา
            emp = db.query(models.Employee).get(req.employee_id)
            if not emp or not emp.schedule:
                print(f"⚠️  ไม่พบข้อมูลพนักงานหรือตารางเวลา สำหรับ employee_id={req.employee_id}")
                continue
            
            sched = emp.schedule
            
            # 4. รีเซ็ตค่า
            old_late = attendance.late_minutes
            old_early = attendance.early_minutes
            old_status = attendance.status
            
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
                    diff_in = datetime.combine(req.request_date, actual_in) - datetime.combine(req.request_date, target_in)
                    late_mins = int(diff_in.total_seconds() / 60)
                    if late_mins > (sched.grace_period_late or 0):
                        attendance.late_minutes = late_mins
                        attendance.status = "สาย"

            # --- กรณี: ออกก่อนเวลา (Early Out) ---
            if attendance.check_out and sched.work_end_time:
                target_out = datetime.strptime(sched.work_end_time[:5], "%H:%M").time()
                actual_out = attendance.check_out.time()
                if actual_out < target_out:
                    diff_out = datetime.combine(req.request_date, target_out) - datetime.combine(req.request_date, actual_out)
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
            
            # 6. แสดงผลการเปลี่ยนแปลง
            if old_late != attendance.late_minutes or old_early != attendance.early_minutes or old_status != attendance.status:
                print(f"✏️  Employee: {emp.employee_code}, Date: {req.request_date}")
                print(f"   เดิม: สาย={old_late}นาที, ออกก่อน={old_early}นาที, สถานะ={old_status}")
                print(f"   ใหม่: สาย={attendance.late_minutes}นาที, ออกก่อน={attendance.early_minutes}นาที, สถานะ={attendance.status}")
                updated_count += 1
        
        # 7. บันทึกการเปลี่ยนแปลง
        db.commit()
        print(f"\n✅ แก้ไขข้อมูลเรียบร้อย: อัพเดท {updated_count} รายการจากทั้งหมด {len(approved_requests)} รายการ")
        
    except Exception as e:
        db.rollback()
        print(f"❌ เกิดข้อผิดพลาด: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    print("=" * 60)
    print("🔧 เริ่มแก้ไขข้อมูล Attendance ที่อนุมัติไปแล้ว")
    print("=" * 60)
    
    confirm = input("\n⚠️  คุณต้องการดำเนินการต่อหรือไม่? (yes/no): ")
    
    if confirm.lower() in ['yes', 'y']:
        recalculate_approved_attendance()
    else:
        print("❌ ยกเลิกการดำเนินการ")
