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
- `APP_STORAGE_ROOT`: โฟลเดอร์หลักสำหรับเก็บไฟล์อัปโหลดบนเครื่อง host (เช่น `/home/zhost/mini_hrm_storage` หรือ `D:/zh_storage/mini_hrm`)

ตัวเลือกสำหรับควบคุม log:

- `ENVIRONMENT`: ใช้ `production` บนระบบจริง (default: `development`)
- `LOG_LEVEL`: ระดับ log ของแอป (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`)
- `PAYROLL_DEBUG`: เปิด debug log สำหรับ payroll โดยตรง (`true/false`)
- `SLOW_REQUEST_MS`: เกณฑ์เวลา (มิลลิวินาที) สำหรับ log request ที่ช้า (default: `800`)

คำแนะนำ production:

- ตั้ง `ENVIRONMENT=production`
- ตั้ง `LOG_LEVEL=INFO` (หรือ `WARNING` หากต้องการลด log เพิ่ม)
- ตั้ง `PAYROLL_DEBUG=false` (หรือไม่ต้องตั้งค่า เพื่อปิดโดย default บน production)

## 📦 Restore ฐานข้อมูลจาก `dental_hrm.sql` (สำหรับ ZHost)
เมื่อต้องย้ายจาก backup เดิมมา ZHosting ให้ทำตามลำดับนี้:

1. สร้างฐานข้อมูลปลายทาง (PostgreSQL)
2. restore dump:
   `psql -h <host> -U <user> -d <db_name> -f dental_hrm.sql`
3. ตั้ง env ของระบบให้ชี้ DB ใหม่ (`DATABASE_URL`) และ storage ใหม่ (`APP_STORAGE_ROOT`)
4. รัน migration ล่าสุดเพื่อเติม schema ที่ backup เดิมยังไม่มี:
   `alembic upgrade head`
5. รีสตาร์ทแอปและตรวจหน้า `/monitor`, `/dashboard`, `/my-profile`

มีสคริปต์ช่วยรันครบขั้นตอน:
`$cred = Get-Credential`
`./restore_dental_hrm_to_zhost.ps1 -SqlFilePath "C:/path/dental_hrm.sql" -DbHost "<host>" -DbPort 5432 -DbName "<db>" -DbCredential $cred`

หมายเหตุ:
- dump เดิมอาจยังไม่มีตารางใหม่ของ welfare/payroll adjustments จึงต้องรัน `alembic upgrade head` ทุกครั้งหลัง restore
- ตรวจสิทธิ์เขียนไฟล์ของโฟลเดอร์ `APP_STORAGE_ROOT` ให้พร้อมก่อนเปิดใช้งานจริง

## 🔎 Cloud Logging Queries (Google Cloud)
ตัวอย่าง Query ที่แนะนำสำหรับ troubleshooting:

baseline กลาง (ไม่ผูก provider): `OBSERVABILITY_BASELINE.md`

baseline สำหรับ Google Cloud โดยเฉพาะ: `CLOUD_LOGGING_BASELINE.md`

```text
# 1) หา request ตาม request_id เดียว (trace ทั้งเส้น)
textPayload:"request_id=req-123"

# 2) ดูเฉพาะคำขอที่ช้า/ผิดพลาดจาก middleware summary
textPayload:"http.request" AND (textPayload:"status=4" OR textPayload:"status=5" OR textPayload:"duration_ms=")

# 3) Flow payroll
textPayload:("payroll.calculate" OR "payroll.process" OR "payroll.recalculate")

# 4) Flow attendance import / requests
textPayload:("attendance.import" OR "attendance.requests.view" OR "attendance.request.process" OR "attendance.approve_all")

# 5) Flow OT approve/process
textPayload:("ot.approval.view" OR "ot.process" OR "ot.request")

# 6) Security/Auth denials
textPayload:("security.guard denied" OR "security.csrf denied" OR "auth.login failed")
```

---
*Developed by HR Architech*