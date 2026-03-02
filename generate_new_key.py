"""
Generate New Encryption Key for Mini-HRM System
"""
from cryptography.fernet import Fernet

def generate_new_key():
    """Generate a new Fernet encryption key"""
    new_key = Fernet.generate_key().decode()
    
    print("=" * 70)
    print("🔐 NEW ENCRYPTION_KEY GENERATED")
    print("=" * 70)
    print()
    print(new_key)
    print()
    print("=" * 70)
    print("⚠️  IMPORTANT: Copy this key NOW!")
    print("=" * 70)
    print()
    print("Next Steps:")
    print("1. Copy the key above")
    print("2. Update Cloud Run environment variable:")
    print(f"   ENCRYPTION_KEY={new_key}")
    print()
    print("3. Run SQL to clear old encrypted data (see clear_encrypted_data.sql)")
    print()
    
    # Save to file for reference
    with open("NEW_ENCRYPTION_KEY.txt", "w") as f:
        f.write(f"ENCRYPTION_KEY={new_key}\n")
        f.write(f"\nGenerated at: {__import__('datetime').datetime.now()}\n")
    
    print("✅ Key also saved to: NEW_ENCRYPTION_KEY.txt")
    print()
    
    return new_key

if __name__ == "__main__":
    generate_new_key()
