# ใช้ Python 3.10 ตัวเล็กเพื่อให้ build เร็ว
FROM python:3.10-slim

# ตั้งค่า directory ทำงาน
WORKDIR /app

# copy ไฟล์ requirements เข้าไปติดตั้ง library
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy ไฟล์ทั้งหมดในโปรเจคเข้าไป
COPY . .

# สั่งรัน FastAPI (พอร์ต 8080 เป็นพอร์ตมาตรฐานของ Cloud Run)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]