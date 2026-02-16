from cryptography.fernet import Fernet

# รันโค้ดนี้ครั้งเดียวใน Terminal เพื่อเจนคีย์: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# แล้วเอาคีย์ที่ได้มาวางในตัวแปรนี้ หรือเก็บใน .env
SECRET_KEY = b'HW6LlUWtMTProQn_42zV_LdPXV7c8nSxjZCaL853lbE=' 
cipher_suite = Fernet(SECRET_KEY)

def encrypt_data(data: str) -> str:
    if not data: return ""
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt_data(data: str) -> str:
    if not data: return ""
    try:
        return cipher_suite.decrypt(data.encode()).decode()
    except:
        return "Decryption Error"