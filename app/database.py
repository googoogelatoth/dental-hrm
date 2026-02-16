import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 🚩 เช็คว่าอยู่บน Cloud หรือเครื่องเรา
# ถ้าอยู่บน Cloud จะมี DATABASE_URL มาให้ ถ้าไม่มีให้ใช้ SQLite เดิม
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./database.db")

# แก้ไขปัญหา PostgreSQL ของ Render ที่มักจะขึ้นต้นด้วย postgres:// ให้เป็น postgresql://
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

# ตั้งค่า Engine
if "sqlite" in SQLALCHEMY_DATABASE_URL:
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# เพิ่มต่อท้ายไฟล์ database.py ได้เลยครับ
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()