import base64
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

# 1. สร้าง Private Key ชุดใหม่
private_key = ec.generate_private_key(ec.SECP256R1())

# 2. แปลง Private Key เป็น Base64 (URL Safe)
priv_num = private_key.private_numbers().private_value
priv_bytes = priv_num.to_bytes(32, 'big')
private_base64 = base64.urlsafe_b64encode(priv_bytes).decode().strip('=')

# 3. แปลง Public Key เป็น Byte ตามมาตรฐาน X9.62 (Uncompressed)
# นี่คือวิธีที่ปลอดภัยที่สุดในการดึงค่า Point สำหรับ VAPID
pub_bytes = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.X962,
    format=serialization.PublicFormat.UncompressedPoint
)
public_base64 = base64.urlsafe_b64encode(pub_bytes).decode().strip('=')

print("\n--- กุญแจชุดใหม่สำหรับ HR Architech ---")
print(f"Public Key (สำหรับ Frontend):  {public_base64}")
print(f"Private Key (สำหรับ Backend): {private_base64}")
print("--------------------------------------\n")