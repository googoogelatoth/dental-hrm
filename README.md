# Mini-HRM (Clinic Edition) 🏥
ระบบจัดการทรัพยากรบุคคลและคำนวณเงินเดือนสำหรับคลินิก พัฒนาด้วย FastAPI

## ✨ ฟีเจอร์หลัก
- **Employee Management:** แยกกลุ่มพนักงานปัจจุบันและพนักงานที่ลาออก
- **Payroll System:** คำนวณเงินเดือนอัตโนมัติ (รองรับ OT, ประกันสังคม, ภาษี)
- **Multi-language:** รองรับ 2 ภาษา (ไทย/อังกฤษ)
- **Security:** ระบบ Single Device Login และการจัดการสิทธิ์ Admin/User
- **PWA Ready:** รองรับการติดตั้งเป็น App และระบบแจ้งเตือน (Web Push)

## 🚀 วิธีการติดตั้ง (Installation)
1. สร้าง Virtual Environment:
   `python -m venv venv`
2. ติดตั้ง Library:
   `pip install -r requirements.txt`
3. รันโปรแกรม:
   `uvicorn app.main:app --reload`

---
*Developed by HR Architech*