"""
Script สำหรับสร้าง Encryption Key และ VAPID Keys สำหรับระบบ HRM

การใช้งาน:
    python generate_security_keys.py
"""

from cryptography.fernet import Fernet
import secrets

def generate_fernet_key():
    """สร้าง Fernet encryption key (32 bytes URL-safe base64)"""
    key = Fernet.generate_key()
    return key.decode()

def generate_session_secret():
    """สร้าง secret key สำหรับ session (256-bit)"""
    return secrets.token_urlsafe(32)

def validate_fernet_key(key: str) -> bool:
    """ตรวจสอบว่า Fernet key ถูกต้องหรือไม่"""
    try:
        import base64
        decoded = base64.urlsafe_b64decode(key)
        return len(decoded) == 32
    except:
        return False

def main():
    print("=" * 60)
    print("🔐 Security Keys Generator for Mini-HRM System")
    print("=" * 60)
    print()
    
    # 1. Generate Fernet Key
    fernet_key = generate_fernet_key()
    print("1. ENCRYPTION_KEY (Fernet):")
    print(f"   {fernet_key}")
    print(f"   ✅ Valid: {validate_fernet_key(fernet_key)}")
    print()
    
    # 2. Generate Session Secret
    session_secret = generate_session_secret()
    print("2. SESSION_SECRET (256-bit):")
    print(f"   {session_secret}")
    print()
    
    # 3. Generate JWT Secret (example)
    jwt_secret = secrets.token_hex(32)
    print("3. JWT_SECRET (optional, ถ้ามีใช้ JWT):")
    print(f"   {jwt_secret}")
    print()
    
    print("-" * 60)
    print("📝 คัดลอกค่าเหล่านี้ใส่ในไฟล์ .env ของคุณ")
    print("-" * 60)
    print()
    print("ตัวอย่าง .env:")  
    print(f"ENCRYPTION_KEY={fernet_key}")
    print(f"SESSION_SECRET={session_secret}")
    print(f"# JWT_SECRET={jwt_secret}")
    print()
    
    print("=" * 60)
    print("⚠️  คำเตือนความปลอดภัย:")
    print("=" * 60)
    print("1. อย่าแชร์ keys เหล่านี้ใน Git หรือที่สาธารณะ")
    print("2. เก็บไฟล์ .env ไว้ใน .gitignore")
    print("3. ใช้ keys ที่แตกต่างกันระหว่าง dev และ production")
    print("4. เปลี่ยน keys ทุก 90-180 วัน (key rotation)")
    print("5. ใช้ Environment Variables ใน production")
    print()
    
    # Generate for VAPID (Web Push)
    print("-" * 60)
    print("🔔 สำหรับ Web Push Notifications (VAPID Keys):")
    print("-" * 60)
    print("ติดตั้ง: npm install -g web-push")
    print("สร้าง keys: npx web-push generate-vapid-keys")
    print()

if __name__ == "__main__":
    main()
