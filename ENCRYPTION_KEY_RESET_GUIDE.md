# 🔐 คู่มือการตั้ง ENCRYPTION_KEY ใหม่

## สถานการณ์
- ระบบขึ้น error: `Decryption failed: InvalidToken`
- ไม่สามารถหา ENCRYPTION_KEY เดิมได้
- ต้องตั้ง key ใหม่และล้างข้อมูลเข้ารหัสเก่า

---

## ⚠️ ผลกระทบ
การตั้ง key ใหม่จะทำให้ **ข้อมูลที่เข้ารหัสเดิมอ่านไม่ได้** ต้องกรอกใหม่:
- เบอร์โทรศัพท์
- เลขบัตรประชาชน
- เลขบัญชีธนาคาร

**ข้อมูลอื่น ๆ ปลอดภัย** (ชื่อ, ตำแหน่ง, เงินเดือน, attendance, leave, payroll)

---

## 📋 ขั้นตอนทั้งหมด (5 ขั้นตอน)

### ขั้นที่ 1: สร้าง Key ใหม่
```powershell
python generate_new_key.py
```
- จะได้ key ใหม่แสดงบนหน้าจอ
- Key จะถูกบันทึกใน `NEW_ENCRYPTION_KEY.txt` ด้วย
- **คัดลอก key นี้ไว้** (จะใช้ในขั้นต่อไป)

---

### ขั้นที่ 2: Deploy Key ใหม่ไปยัง Cloud Run

#### วิธีที่ 1: ใช้ Script (แนะนำ)
1. เปิดไฟล์ `deploy_new_encryption_key.ps1`
2. แก้บรรทัดที่ 17: วาง key ใหม่แทน `YOUR_NEW_KEY_HERE`
3. รัน:
```powershell
.\deploy_new_encryption_key.ps1
```

#### วิธีที่ 2: ใช้คำสั่ง gcloud โดยตรง
```powershell
gcloud run services update mini-hrm `
  --region asia-southeast1 `
  --set-env-vars "ENCRYPTION_KEY=YOUR_NEW_KEY_HERE"
```
(แทน `YOUR_NEW_KEY_HERE` ด้วย key จริง)

#### วิธีที่ 3: ผ่าน GCP Console
1. เข้า: https://console.cloud.google.com/run
2. Click `mini-hrm`
3. Click **"Edit & Deploy New Revision"**
4. ไปที่แท็บ **"Variables & Secrets"**
5. หา `ENCRYPTION_KEY` → Click **Edit**
6. วาง key ใหม่
7. Click **"Deploy"**

⏱️ รอ 1-2 นาทีให้ deploy เสร็จ

---

### ขั้นที่ 3: ล้างข้อมูลเข้ารหัสเก่า

เชื่อมต่อ PostgreSQL แล้วรัน:
```bash
psql -h YOUR_DB_HOST -U YOUR_DB_USER -d YOUR_DB_NAME -f clear_encrypted_data.sql
```

หรือ copy SQL จาก `clear_encrypted_data.sql` ไป paste ใน Cloud SQL Console

**SQL จะ:**
- แสดงจำนวนแถวที่กระทบ
- ล้างฟิลด์ phone_number, id_card_number, bank_account_number
- ตรวจสอบผลลัพธ์

---

### ขั้นที่ 4: ทดสอบระบบ

1. เข้า: `https://mini-hrm-214923519480.asia-southeast1.run.app/my-profile`

2. เปิด Cloud Run Logs:
   - https://console.cloud.google.com/run/detail/asia-southeast1/mini-hrm/logs

3. ตรวจสอบว่า:
   - ✅ หน้า my-profile โหลดได้
   - ✅ **ไม่มี** error `Decryption failed: InvalidToken`
   - ✅ ฟิลด์ส่วนตัวว่างเปล่า (ถูกต้อง)

---

### ขั้นที่ 5: แจ้งให้ User กรอกข้อมูลใหม่

แจ้งพนักงาน/แอดมินว่า:
> "ระบบได้รับการอัปเดต กรุณาเข้าไปกรอกข้อมูลส่วนตัวใหม่ที่หน้า My Profile:
> - เบอร์โทรศัพท์
> - เลขบัตรประชาชน  
> - เลขบัญชีธนาคาร"

---

## 🧪 Troubleshooting

### ยังเห็น "InvalidToken" หลัง deploy
**สาเหตุ:** 
- Key ยังไม่อัปเดตจริง / revision เก่ายังรับ traffic
- SQL ยังไม่ได้รัน

**แก้:**
```powershell
# 1. ตรวจสอบ env ที่ deploy ไปจริง ๆ
gcloud run services describe mini-hrm --region asia-southeast1 --format="value(spec.template.spec.containers[0].env)"

# 2. บังคับ traffic ไป revision ใหม่ล่าสุด
gcloud run services update-traffic mini-hrm --region asia-southeast1 --to-latest

# 3. รัน SQL อีกรอบ
psql ... -f clear_encrypted_data.sql
```

---

### Key ที่สร้างไม่ valid
**อาการ:** Error `Invalid ENCRYPTION_KEY format`

**แก้:**
- ตรวจสอบว่า key มีความยาว ~44 ตัวอักษร
- ต้องจบด้วย `=`
- ไม่มี space หรือ newline
- ถ้าไม่แน่ใจ → สร้างใหม่ด้วย `python generate_new_key.py`

---

### กรอกข้อมูลใหม่แล้วยังอ่านไม่ได้
**สาเหตุ:** Key ไม่ตรงกับที่ใช้เข้ารหัส

**แก้:**
```sql
-- ตรวจสอบว่าข้อมูลถูกเข้ารหัสแล้วจริง ๆ
SELECT id, employee_code, 
       LEFT(phone_number, 10) as phone_prefix 
FROM employees 
WHERE phone_number IS NOT NULL 
LIMIT 5;

-- ควรเห็น gAAAAA... (Fernet prefix)
```

---

## 📞 Contact

หากมีปัญหาหรือข้อสงสัย:
1. เช็ค Cloud Run Logs ก่อน
2. ทดสอบ decrypt ด้วย Python console:
```python
from cryptography.fernet import Fernet
f = Fernet(b'YOUR_KEY_HERE')
f.decrypt(b'gAAAAA...')  # ลอง decrypt ข้อมูลจาก DB
```

---

**สร้างเมื่อ:** March 2, 2026  
**สถานะ:** Ready to use
