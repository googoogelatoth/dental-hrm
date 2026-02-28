import os
import base64
from cryptography.fernet import Fernet

# Load encryption key from environment; required for production.
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    raise RuntimeError("ENCRYPTION_KEY environment variable is not set. Set it to a valid Fernet key.")

# Validate Fernet key format (must be 32 bytes URL-safe base64)
try:
    decoded_key = base64.urlsafe_b64decode(ENCRYPTION_KEY)
    if len(decoded_key) != 32:
        raise ValueError("Key must be 32 bytes")
except Exception as e:
    raise RuntimeError(f"Invalid ENCRYPTION_KEY format: {e}. Generate with: Fernet.generate_key()")

# Create a single Fernet instance for the application
CIPHER_SUITE = Fernet(ENCRYPTION_KEY.encode())

# VAPID keys for Web Push
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")

# Cloudinary configuration is read directly where needed (main.py uses env vars)
