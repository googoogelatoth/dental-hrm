from .config import CIPHER_SUITE, FALLBACK_CIPHER_SUITES
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


def decrypt_data_with_status(data: str):
    """Return tuple(status, value) where status is one of:
    empty, current_key, old_key, plaintext, unreadable.
    """
    if not data:
        return "empty", ""

    token = data.strip()
    try:
        return "current_key", CIPHER_SUITE.decrypt(token.encode()).decode()
    except Exception as current_exc:
        for fallback_cipher in FALLBACK_CIPHER_SUITES:
            try:
                return "old_key", fallback_cipher.decrypt(token.encode()).decode()
            except Exception:
                continue

        if token.startswith("gAAAA"):
            logger.error(f"Decryption failed: {type(current_exc).__name__}")
            return "unreadable", ""

        logger.warning("Sensitive data appears to be stored as plaintext; returning raw value")
        return "plaintext", data

def decrypt_data(data: str) -> str:
    """Decrypt sensitive data with fallback support for key rotation and legacy plaintext."""
    _, value = decrypt_data_with_status(data)
    return value