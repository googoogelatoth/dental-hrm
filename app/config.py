import os
import base64
from cryptography.fernet import Fernet

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except Exception:
    pass

# Load encryption key from environment; required for production.
ENCRYPTION_KEY = (os.getenv("ENCRYPTION_KEY") or "").strip().strip('"').strip("'")
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
# Strip aggressively to handle quotes and whitespace in environment variables
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "").strip().strip('"').strip("'").strip()
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "").strip().strip('"').strip("'").strip()

# VAPID Claims Subject (must be a valid mailto: link or admin email)
VAPID_CLAIMS_SUB = os.getenv("VAPID_CLAIMS_SUB", "").strip().strip('"').strip("'")
if not VAPID_CLAIMS_SUB or VAPID_CLAIMS_SUB == "mailto:your-email@example.com":
    # Use fallback admin email if VAPID_CLAIMS_SUB is not configured
    VAPID_CLAIMS_SUB = os.getenv("ADMIN_EMAIL", "mailto:admin@example.com").strip()

# Ensure VAPID_CLAIMS_SUB is always in mailto: format (required by pywebpush)
if VAPID_CLAIMS_SUB and not VAPID_CLAIMS_SUB.startswith("mailto:"):
    VAPID_CLAIMS_SUB = f"mailto:{VAPID_CLAIMS_SUB}"

# Validate VAPID keys (optional in dev, but warn if missing)
if not VAPID_PUBLIC_KEY or not VAPID_PRIVATE_KEY:
    import sys
    print("⚠️  WARNING: VAPID keys are not configured!")
    print("   Push notifications will not work.")
    print("   Set VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY environment variables.")
    print("   Generate keys with: npx web-push generate-vapid-keys")
    print(f"   VAPID_PUBLIC_KEY length: {len(VAPID_PUBLIC_KEY)}")
    print(f"   VAPID_PRIVATE_KEY length: {len(VAPID_PRIVATE_KEY)}")
else:
    # Summary check for key format (base64url, no padding)
    if len(VAPID_PUBLIC_KEY) < 85:
        print(f"⚠️  WARNING: VAPID_PUBLIC_KEY may be too short ({len(VAPID_PUBLIC_KEY)} chars, expected ~87)")
    else:
        print(f"✅ VAPID_PUBLIC_KEY loaded: {len(VAPID_PUBLIC_KEY)} characters")
    if len(VAPID_PRIVATE_KEY) < 42:
        print(f"⚠️  WARNING: VAPID_PRIVATE_KEY may be too short ({len(VAPID_PRIVATE_KEY)} chars, expected ~43)")
    else:
        print(f"✅ VAPID_PRIVATE_KEY loaded: {len(VAPID_PRIVATE_KEY)} characters")
    print(f"✅ VAPID_CLAIMS_SUB loaded: {VAPID_CLAIMS_SUB}")

# Cloudinary configuration is read directly where needed (main.py uses env vars)
