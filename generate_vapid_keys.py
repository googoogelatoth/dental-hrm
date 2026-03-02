"""
Generate VAPID Keys for Web Push Notifications
Uses pywebpush library (part of requirements.txt)
"""
try:
    from pywebpush import Vapid
    from cryptography.hazmat.primitives import serialization
    import base64
    
    def generate_vapid_keys():
        """Generate VAPID key pair for Web Push"""
        vapid = Vapid()
        vapid.generate_keys()
        
        # Get keys in the correct format
        private_key = vapid.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        public_key = vapid.public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )
        
        # Convert to base64url format (URL-safe)
        private_key_b64 = base64.urlsafe_b64encode(
            vapid.private_key.private_numbers().private_value.to_bytes(32, 'big')
        ).decode('utf-8').rstrip('=')
        
        public_key_b64 = base64.urlsafe_b64encode(public_key).decode('utf-8').rstrip('=')
        
        print("=" * 70)
        print("🔔 VAPID KEYS GENERATED FOR WEB PUSH")
        print("=" * 70)
        print()
        print("Public Key:")
        print(public_key_b64)
        print()
        print("Private Key:")
        print(private_key_b64)
        print()
        print("=" * 70)
        print("⚠️  IMPORTANT: Copy these keys NOW!")
        print("=" * 70)
        print()
        
        # Save to file
        with open("NEW_VAPID_KEYS.txt", "w") as f:
            f.write(f"VAPID_PUBLIC_KEY={public_key_b64}\n")
            f.write(f"VAPID_PRIVATE_KEY={private_key_b64}\n")
            f.write(f"VAPID_CLAIMS_SUB=mailto:admin@clinic.com\n")
            f.write(f"\n# Generated at: {__import__('datetime').datetime.now()}\n")
        
        print("✅ Keys saved to: NEW_VAPID_KEYS.txt")
        print()
        print("Next Steps:")
        print("1. Copy the keys above")
        print("2. Update Cloud Run environment variables:")
        print(f"   VAPID_PUBLIC_KEY={public_key_b64}")
        print(f"   VAPID_PRIVATE_KEY={private_key_b64}")
        print()
        
        return public_key_b64, private_key_b64

except ImportError:
    # Fallback: use cryptography directly
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    import base64
    
    def generate_vapid_keys():
        """Generate VAPID key pair using cryptography"""
        # Generate EC key pair (NIST P-256 curve)
        private_key = ec.generate_private_key(ec.SECP256R1())
        public_key = private_key.public_key()
        
        # Get public key in uncompressed point format
        public_key_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )
        
        # Get private key as integer
        private_numbers = private_key.private_numbers()
        private_key_bytes = private_numbers.private_value.to_bytes(32, 'big')
        
        # Convert to base64url format (URL-safe, no padding)
        public_key_b64 = base64.urlsafe_b64encode(public_key_bytes).decode('utf-8').rstrip('=')
        private_key_b64 = base64.urlsafe_b64encode(private_key_bytes).decode('utf-8').rstrip('=')
        
        print("=" * 70)
        print("🔔 VAPID KEYS GENERATED FOR WEB PUSH")
        print("=" * 70)
        print()
        print("Public Key:")
        print(public_key_b64)
        print()
        print("Private Key:")
        print(private_key_b64)
        print()
        print("=" * 70)
        print("⚠️  IMPORTANT: Copy these keys NOW!")
        print("=" * 70)
        print()
        print(f"Public Key Length: {len(public_key_b64)} characters (should be ~86)")
        print(f"Private Key Length: {len(private_key_b64)} characters (should be ~43)")
        print()
        
        # Save to file
        with open("NEW_VAPID_KEYS.txt", "w") as f:
            f.write(f"VAPID_PUBLIC_KEY={public_key_b64}\n")
            f.write(f"VAPID_PRIVATE_KEY={private_key_b64}\n")
            f.write(f"VAPID_CLAIMS_SUB=mailto:admin@clinic.com\n")
            f.write(f"\n# Generated at: {__import__('datetime').datetime.now()}\n")
            f.write(f"\n# Key Details:\n")
            f.write(f"# Public Key Length: {len(public_key_b64)}\n")
            f.write(f"# Private Key Length: {len(private_key_b64)}\n")
        
        print("✅ Keys saved to: NEW_VAPID_KEYS.txt")
        print()
        print("Next Steps:")
        print("1. Copy the keys above")
        print("2. Update Cloud Run environment variables:")
        print(f"   VAPID_PUBLIC_KEY={public_key_b64}")
        print(f"   VAPID_PRIVATE_KEY={private_key_b64}")
        print(f"   VAPID_CLAIMS_SUB=mailto:admin@clinic.com")
        print()
        
        return public_key_b64, private_key_b64

if __name__ == "__main__":
    generate_vapid_keys()
