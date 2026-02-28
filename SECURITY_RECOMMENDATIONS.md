# 🔐 รายงานการตรวจสอบ Security (Encryption/Decryption)

## ✅ สิ่งที่ทำได้ดีแล้ว

1. **Password Hashing** - ใช้ bcrypt อย่างถูกต้อง (ไม่ควร encrypt รหัสผ่าน)
2. **Sensitive Data Encryption** - เข้ารหัส: เบอร์โทร, เลขบัตรประชาชน, เลขบัญชี
3. **Fernet (AES-128)** - ใช้ symmetric encryption ที่ปลอดภัย
4. **Environment Variables** - ENCRYPTION_KEY ไม่ hardcode ในโค้ด
5. **HttpOnly Cookies** - ป้องกัน JavaScript access (XSS)
6. **Single Device Login** - มีการตรวจสอบ session

---

## ❗ ปัญหาสำคัญที่ต้องแก้ทันที

### 1. **Cookie Security ไม่สมบูรณ์**
```python
# ❌ ปัจจุบัน
res.set_cookie(key="session_id", value=new_session_id, max_age=max_age, httponly=True)

# ✅ ควรเป็น
res.set_cookie(
    key="session_id", 
    value=new_session_id, 
    max_age=max_age, 
    httponly=True,
    secure=True,        # บังคับ HTTPS (production)
    samesite="Lax"      # ป้องกัน CSRF
)
```

### 2. **Session ID ไม่ปลอดภัยพอ**
```python
# ❌ ปัจจุบัน - UUID ธรรมดา
new_session_id = str(uuid.uuid4())

# ✅ ควรเป็น - Cryptographically secure
import secrets
new_session_id = secrets.token_urlsafe(32)  # 256-bit random
```

### 3. **Decryption Error แสดงข้อความไม่ปลอดภัย**
```python
# ❌ ปัจจุบัน - เปิดเผยว่ามี encryption error
def decrypt_data(data: str) -> str:
    if not data:
        return ""
    try:
        return CIPHER_SUITE.decrypt(data.encode()).decode()
    except Exception:
        return "Decryption Error"  # ❌ อาจถูกใช้ attack

# ✅ ควรเป็น - ไม่เปิดเผยข้อมูล
def decrypt_data(data: str) -> str:
    if not data:
        return ""
    try:
        return CIPHER_SUITE.decrypt(data.encode()).decode()
    except Exception as e:
        # Log แต่ไม่ให้ user เห็น
        logger.error(f"Decryption failed: {type(e).__name__}")
        return ""  # หรือ raise exception ขึ้นไปจัดการ
```

### 4. **ไม่มี CSRF Protection**
FastAPI ไม่มี built-in CSRF ควรเพิ่ม:
```bash
pip install fastapi-csrf-protect
```

### 5. **ไม่มี Rate Limiting สำหรับ Login**
```python
# ติดตั้ง
pip install slowapi

# เพิ่มใน main.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/login")
@limiter.limit("5/minute")  # จำกัด 5 ครั้งต่อนาที
async def handle_login(...):
    ...
```

---

## ⚠️ ข้อเสนอแนะเพิ่มเติม

### 1. **ข้อมูลที่ควร Encrypt เพิ่ม**
- ✅ ที่อยู่บ้าน (address) - ข้อมูลส่วนตัว
- ⚖️ เงินเดือน (base_salary) - พิจารณาตามนโยบาย
- ✅ Emergency contact

### 2. **Validation ก่อน Encrypt**
```python
def encrypt_data(data: str) -> str:
    if not data:
        return ""
    # Validate ว่าเป็นข้อมูลที่คาดหวัง
    if len(data) > 1000:  # ป้องกัน DOS
        raise ValueError("Data too long")
    return CIPHER_SUITE.encrypt(data.encode()).decode()
```

### 3. **Key Rotation Strategy**
```python
# เพิ่มใน config.py
OLD_ENCRYPTION_KEY = os.getenv("OLD_ENCRYPTION_KEY")  # สำหรับ migrate

def migrate_encryption_key(old_key, new_key, db_session):
    """Re-encrypt ข้อมูลเก่าด้วย key ใหม่"""
    employees = db_session.query(Employee).all()
    old_cipher = Fernet(old_key.encode())
    new_cipher = Fernet(new_key.encode())
    
    for emp in employees:
        if emp.phone_number:
            decrypted = old_cipher.decrypt(emp.phone_number.encode()).decode()
            emp.phone_number = new_cipher.encrypt(decrypted.encode()).decode()
    
    db_session.commit()
```

### 4. **ENCRYPTION_KEY Validation**
```python
# เพิ่มใน config.py
import base64

def validate_fernet_key(key: str) -> bool:
    try:
        decoded = base64.urlsafe_b64decode(key)
        return len(decoded) == 32  # ต้องเป็น 32 bytes
    except:
        return False

if not validate_fernet_key(ENCRYPTION_KEY):
    raise RuntimeError("Invalid ENCRYPTION_KEY format. Generate with: Fernet.generate_key()")
```

### 5. **Password Policy**
```python
def validate_password_strength(password: str) -> tuple[bool, str]:
    """ตรวจสอบความแข็งแกร่งของรหัสผ่าน"""
    if len(password) < 8:
        return False, "รหัสผ่านต้องมีอย่างน้อย 8 ตัวอักษร"
    if not any(c.isupper() for c in password):
        return False, "ต้องมีตัวพิมพ์ใหญ่อย่างน้อย 1 ตัว"
    if not any(c.isdigit() for c in password):
        return False, "ต้องมีตัวเลขอย่างน้อย 1 ตัว"
    return True, "OK"
```

### 6. **Audit Log - ไม่ควร Log ข้อมูล Sensitive**
```python
# ✅ ดีแล้ว - ไม่ log เบอร์โทร/บัตรประชาชน
log_activity(db, user, "แก้ไขพนักงาน", f"แก้ไขข้อมูล {emp.first_name}", request)

# ❌ อย่าทำ
log_activity(db, user, "แก้ไข", f"เปลี่ยนเบอร์เป็น {phone_number}", request)
```

---

## 📋 Checklist การปรับปรุง (เรียงตามลำดับความสำคัญ)

### High Priority (ควรทำทันที)
- [ ] เพิ่ม `secure=True` และ `samesite="Lax"` ใน cookies
- [ ] เปลี่ยน session ID เป็น `secrets.token_urlsafe(32)`
- [ ] ปรับ decryption error handling ไม่เปิดเผยรายละเอียด
- [ ] เพิ่ม rate limiting สำหรับ login endpoint
- [ ] Validate ENCRYPTION_KEY format

### Medium Priority (ควรทำใน sprint ถัดไป)
- [ ] เพิ่ม CSRF protection
- [ ] Encrypt ที่อยู่บ้าน (address)
- [ ] เพิ่ม password strength validation
- [ ] เพิ่ม input validation ก่อน encrypt
- [ ] ตั้งค่า HTTP Security Headers (HSTS, X-Frame-Options, etc.)

### Low Priority (พิจารณาในอนาคต)
- [ ] Key rotation mechanism
- [ ] Encrypt เงินเดือน (ถ้านโยบายต้องการ)
- [ ] 2FA (Two-Factor Authentication)
- [ ] Session timeout ที่เข้มงวดกว่า
- [ ] Audit log encryption (สำหรับ compliance)

---

## 🔧 วิธีสร้าง ENCRYPTION_KEY ที่ปลอดภัย

```python
from cryptography.fernet import Fernet

# Generate key
key = Fernet.generate_key()
print(key.decode())  # เก็บค่านี้ใน .env

# ตัวอย่าง: gAAAAABhPxxx... (44 characters, URL-safe base64)
```

**ตั้งค่าใน .env:**
```bash
ENCRYPTION_KEY=gAAAAABhPxxx_your_actual_key_here_xxx
```

---

## 📚 อ้างอิง

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Fernet Specification](https://github.com/fernet/spec/)
- [FastAPI Security Best Practices](https://fastapi.tiangolo.com/tutorial/security/)
- [PDPA Thailand](https://www.pdpc.or.th/) - Personal Data Protection Act

---

**สรุป:** ระบบมีพื้นฐานความปลอดภัยที่ดี แต่ควรปรับปรุงรายละเอียดเพื่อให้สมบูรณ์ตาม best practices โดยเฉพาะเรื่อง cookie security, session management และ rate limiting
