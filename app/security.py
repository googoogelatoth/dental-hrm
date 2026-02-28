from .config import CIPHER_SUITE
import logging

logger = logging.getLogger("clinic_hrm")

def encrypt_data(data: str) -> str:
    """Encrypt sensitive data using Fernet symmetric encryption"""
    if not data:
        return ""
    
    # Validate input length (prevent DOS)
    if len(data) > 1000:
        raise ValueError("Data too long for encryption")
    
    try:
        return CIPHER_SUITE.encrypt(data.encode()).decode()
    except Exception as e:
        logger.error(f"Encryption failed: {type(e).__name__}")
        raise

def decrypt_data(data: str) -> str:
    """Decrypt sensitive data - returns empty string on failure"""
    if not data:
        return ""
    
    try:
        return CIPHER_SUITE.decrypt(data.encode()).decode()
    except Exception as e:
        # Log error without exposing details to user
        logger.error(f"Decryption failed: {type(e).__name__}")
        return ""  # Return empty instead of error message