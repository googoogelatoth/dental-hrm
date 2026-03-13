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

## ⚙️ Environment Variables
ตั้งค่าตัวแปรเหล่านี้ก่อนรันระบบ (โดยเฉพาะบน production):

- `DATABASE_URL`: URL ของฐานข้อมูล PostgreSQL
- `ENCRYPTION_KEY`: คีย์เข้ารหัสข้อมูลสำคัญ
- `VAPID_PUBLIC_KEY`: Public key สำหรับ Web Push
- `VAPID_PRIVATE_KEY`: Private key สำหรับ Web Push
- `VAPID_CLAIMS_SUB`: อีเมลผู้ดูแลระบบรูปแบบ `mailto:you@example.com`

ตัวเลือกสำหรับควบคุม log:

- `ENVIRONMENT`: ใช้ `production` บนระบบจริง (default: `development`)
- `LOG_LEVEL`: ระดับ log ของแอป (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`)
- `PAYROLL_DEBUG`: เปิด debug log สำหรับ payroll โดยตรง (`true/false`)

คำแนะนำ production:

- ตั้ง `ENVIRONMENT=production`
- ตั้ง `LOG_LEVEL=INFO` (หรือ `WARNING` หากต้องการลด log เพิ่ม)
- ตั้ง `PAYROLL_DEBUG=false` (หรือไม่ต้องตั้งค่า เพื่อปิดโดย default บน production)

---
*Developed by HR Architech*