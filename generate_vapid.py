#!/usr/bin/env python3
"""
Generate VAPID keys for Web Push Notifications.
Run: python generate_vapid.py
"""

import sys
import os

# Add venv to path if needed
venv_scripts = os.path.join(os.path.dirname(__file__), 'venv', 'Lib', 'site-packages')
if os.path.exists(venv_scripts):
    sys.path.insert(0, venv_scripts)

try:
    # Try py_vapid first
    try:
        from py_vapid import Vapid01
        
        # Generate new VAPID key pair
        vapid = Vapid01.generate()
        
        public_key_str = vapid.public_key.urlsafe_b64encode().decode('ascii')
        private_key_str = vapid.private_key.urlsafe_b64encode().decode('ascii')
        
        print("\n" + "="*70)
        print("🔑 NEW VAPID KEYS GENERATED")
        print("="*70)
        print(f"\nVAPID_PUBLIC_KEY={public_key_str}")
        print(f"Public Key Length: {len(public_key_str)} characters (expected ~87)")
        print(f"\nVAPID_PRIVATE_KEY={private_key_str}")
        print(f"Private Key Length: {len(private_key_str)} characters (expected ~43)")
        print("\n" + "="*70)
        print("📝 UPDATE YOUR .env FILE:")
        print("="*70)
        print(f"\nVAPID_PUBLIC_KEY={public_key_str}")
        print(f"VAPID_PRIVATE_KEY={private_key_str}")
        print("\n" + "="*70)
        print("✅ Then restart your application!")
        print("="*70 + "\n")
        
    except ImportError:
        # Fallback to pywebpush
        from pywebpush import generate_vapid_keys
        
        public_key, private_key = generate_vapid_keys()
        
        print("\n" + "="*70)
        print("🔑 NEW VAPID KEYS GENERATED (via pywebpush)")
        print("="*70)
        print(f"\nVAPID_PUBLIC_KEY={public_key}")
        print(f"Public Key Length: {len(public_key)} characters")
        print(f"\nVAPID_PRIVATE_KEY={private_key}")
        print(f"Private Key Length: {len(private_key)} characters")
        print("\n" + "="*70)
        print("📝 UPDATE YOUR .env FILE:")
        print("="*70)
        print(f"\nVAPID_PUBLIC_KEY={public_key}")
        print(f"VAPID_PRIVATE_KEY={private_key}")
        print("\n" + "="*70)
        print("✅ Then restart your application!")
        print("="*70 + "\n")
        
except ImportError as e:
    print(f"❌ Error: Required packages not installed or not in PATH")
    print(f"   Error: {e}")
    print(f"\n   Install with: pip install py-vapid")
    print(f"   Or use online generator: https://web-push-codelab.glitch.me/")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error generating VAPID keys: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
