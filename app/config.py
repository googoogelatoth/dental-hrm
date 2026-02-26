import os
from cryptography.fernet import Fernet

# Load encryption key from environment; required for production.
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    raise RuntimeError("ENCRYPTION_KEY environment variable is not set. Set it to a valid Fernet key.")

# Create a single Fernet instance for the application
CIPHER_SUITE = Fernet(ENCRYPTION_KEY.encode())

# VAPID keys for Web Push
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")

# Cloudinary configuration is read directly where needed (main.py uses env vars)
