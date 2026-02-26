from .config import CIPHER_SUITE

def encrypt_data(data: str) -> str:
    if not data:
        return ""
    return CIPHER_SUITE.encrypt(data.encode()).decode()

def decrypt_data(data: str) -> str:
    if not data:
        return ""
    try:
        return CIPHER_SUITE.decrypt(data.encode()).decode()
    except Exception:
        return "Decryption Error"