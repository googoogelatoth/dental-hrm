import os
import shutil
from fastapi import Depends, HTTPException
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from .database import SessionLocal, engine
from . import models
from fastapi import FastAPI, Request, Form, File, UploadFile
from typing import List
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.cors import CORSMiddleware
import starlette.status as status
from fastapi import Response
from passlib.context import CryptContext
from fastapi import Request
from urllib.parse import quote
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from fastapi import Query 
from fastapi.responses import FileResponse
from fastapi import BackgroundTasks 
import pandas as pd
import base64
import uuid
import io
from pywebpush import webpush, WebPushException
import json
from fastapi.staticfiles import StaticFiles
from urllib.parse import urlparse
from sqlalchemy import func, extract
import calendar
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import joinedload
from .security import encrypt_data
from .security import decrypt_data
from .languages import TRANSLATIONS
from fastapi import status
import cloudinary
import cloudinary.uploader

app = FastAPI()

# --- ส่วนบนสุดของ main.py ---
VAPID_PUBLIC_KEY = "BOgA23yQvhkjWnKvHE9PFcfV_Pf7UCLLR3s63u_PQUtEA8J06l310gkZF2m_MxBAiUkH43ziGd8P93XxLp-m5q4"
VAPID_PRIVATE_KEY = "2200Y9KHaV65qsAhS9gdFbmINvTymrFcFJ10ROvXI6Y"

UPLOAD_DIR = "uploads/leave_documents"
# เช็คว่าถ้าไม่มีโฟลเดอร์ uploads ให้สร้างขึ้นมาใหม่
# 🚩 1. หาตำแหน่งของไฟล์ main.py (ซึ่งอยู่ในโฟลเดอร์ app)
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) 

# 🚩 2. ตั้งค่าระบบ Static (สำหรับโลโก้วงแดง และ CSS)
# ชี้ไปที่ app/static
STATIC_DIR = os.path.join(BASE_DIR, "static")
LOGO_UPLOAD_DIR = os.path.join(STATIC_DIR, "uploads") # ที่เก็บโลโก้

# สร้างโฟลเดอร์เก็บโลโก้ถ้ายังไม่มี
os.makedirs(LOGO_UPLOAD_DIR, exist_ok=True)

# 🚩 3. ตั้งค่าระบบ Uploads (สำหรับใบลาและเอกสารพนักงาน - อยู่นอก app)
# ถอยกลับไป 1 ระดับจาก app/ เพื่อไปที่ root โปรเจกต์
ROOT_DIR = os.path.dirname(BASE_DIR)
DOCS_UPLOAD_DIR = os.path.join(ROOT_DIR, "uploads")
LEAVE_DIR = os.path.join(DOCS_UPLOAD_DIR, "leave_documents")

# สร้างโฟลเดอร์เอกสารทั้งหมด
os.makedirs(os.path.join(DOCS_UPLOAD_DIR, "profile_pics"), exist_ok=True)
os.makedirs(os.path.join(DOCS_UPLOAD_DIR, "documents"), exist_ok=True)
os.makedirs(LEAVE_DIR, exist_ok=True)

# 🚩 4. Mount ประตูเข้าออกไฟล์ (ห้ามประกาศซ้ำ)
# เข้าถึงโลโก้ผ่าน: /static/uploads/company_logo.png
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# เข้าถึงใบลาผ่าน: /uploads/leave_documents/file.pdf
app.mount("/uploads", StaticFiles(directory=DOCS_UPLOAD_DIR), name="uploads")

# สร้างตารางในฐานข้อมูล (ถ้ายังไม่มี)
models.Base.metadata.create_all(bind=engine)

# 1. ตั้งค่า Cloudinary (ดึงค่าจากชื่อตัวแปร Environment)
cloudinary.config(
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key = os.getenv("CLOUDINARY_API_KEY"),
    api_secret = os.getenv("CLOUDINARY_API_SECRET")
)

# ตั้งค่าตำแหน่งของไฟล์ HTML
templates = Jinja2Templates(directory="app/templates")

# ฟังก์ชันสำหรับดึง Database Session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 3. วาง "ฟังก์ชันเช็ค Session" ไว้ตรงนี้ (ก่อนพวก @app.get)
# ---------------------------------------------------------
async def get_current_active_user(request: Request, db: Session = Depends(get_db)):
    user_id = request.cookies.get("user_id")
    cookie_session = request.cookies.get("session_id")
    
    # 1. ถ้าไม่มีคุกกี้พื้นฐาน (ไม่ได้ Login)
    if not user_id or not cookie_session:
        # แทนที่จะ return None ให้เด้งไปหน้า Login เลย
        raise HTTPException(status_code=401, detail="กรุณาเข้าสู่ระบบ")

    # 2. ดึงข้อมูล User จาก DB
    try:
        user = db.query(models.Employee).filter(models.Employee.id == int(user_id)).first()
    except:
        raise HTTPException(status_code=401, detail="ข้อมูลผู้ใช้ไม่ถูกต้อง")
    
    # 3. 🛡️ เช็คว่ามีตัวตน และ สถานะพนักงาน
    if not user or not user.is_active:
        # เด้ง Error แทนการ return string
        raise HTTPException(status_code=403, detail="บัญชีนี้ถูกระงับการใช้งาน")

    # 4. 🔒 ตรวจสอบ Single Device Login
    if user.current_session_id != cookie_session:
        # เด้ง Error เพื่อให้ Middleware หรือหน้าเว็บจัดการส่งไป Login ใหม่
        raise HTTPException(status_code=401, detail="เซสชั่นหมดอายุหรือมีการเข้าสู่ระบบจากที่อื่น")
        
    return user # คืนค่าเป็นก้อน Object จริงๆ เท่านั้น

async def get_lang(request: Request):
    # ดึงค่า lang จากคุกกี้ ถ้าไม่มีให้ใช้ 'th' เป็น Default
    lang = request.cookies.get("lang", "th")
    return TRANSLATIONS.get(lang, TRANSLATIONS["th"])

# ตั้งค่าการเข้ารหัสรหัสผ่าน
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@app.on_event("startup")
async def create_first_admin():
    db = SessionLocal()
    try:
        # เช็คก่อนว่ามีพนักงานในระบบหรือยัง
        admin_exists = db.query(models.Employee).filter(models.Employee.employee_code == "admin").first()
        
        if not admin_exists:
            # สร้าง User Admin คนแรก
            hashed_pw = pwd_context.hash("admin1234") # ตั้งรหัสผ่านเริ่มต้นที่นี่
            first_admin = models.Employee(
                employee_code="admin",
                first_name="System",
                last_name="Admin",
                position="Admin",
                role="Admin",
                hashed_password=hashed_pw,
                # ใส่ฟิลด์บังคับอื่นๆ ให้ครบ (ถ้ามี)
            )
            db.add(first_admin)
            db.commit()
            print("--- Created Initial Admin User (User: admin / Pass: admin1234) ---")
    finally:
        db.close()
        
def send_push_to_user(employee_id: int, title: str, body: str, db: Session):
    subscriptions = db.query(models.PushSubscription).filter(
        models.PushSubscription.employee_id == employee_id
    ).all()
    
    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth}
                },
                data=json.dumps({"title": title, "body": body}),
                vapid_private_key=VAPID_PRIVATE_KEY, # มั่นใจว่ามีตัวแปรนี้ใน config
                vapid_claims={"sub": "mailto:admin@clinic.com"}
            )
        except WebPushException as ex:
            print(f"Push failed: {ex}")

# แก้ไขจากของเดิม ให้เป็นแบบนี้ครับ
@app.get("/", response_class=HTMLResponse)
async def read_root(response: Response):
    # สร้าง Redirect และสั่งล้าง Cookie เก่าที่อาจจะค้างจนทำให้หน้าจอเทา
    res = RedirectResponse(url="/login", status_code=303)
    # การล้าง Cookie จะช่วยให้ Browser Reset สถานะใหม่
    return res

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: models.Employee = Depends(get_current_active_user),
    texts: dict = Depends(get_lang), 
    db: Session = Depends(get_db)
):
    # 1. เช็คพื้นฐานว่ามีการ Login ไหม
    user_id = request.cookies.get("user_id")
    cookie_session = request.cookies.get("session_id")
    
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)
    
    # 🛡️ ตรวจสอบสถานะ User (get_current_active_user จะส่งสถานะมาให้)
    if user == "inactive":
        res = RedirectResponse(url="/login?msg=account_inactive", status_code=303)
        res.delete_cookie("user_id")
        return res
    if user == "expired":
        res = RedirectResponse(url="/login?msg=session_expired", status_code=303)
        return res

    # 3. 🎯 ดึงข้อมูลพนักงานแยกกลุ่ม (🚩 แก้ไขตรงนี้)
    # เราต้องดึงมาทั้ง 2 กลุ่มเพื่อเอาไปโชว์ใน Tabs ของนายครับ
    active_emps = db.query(models.Employee).filter(models.Employee.is_active == True).all()
    resigned_emps = db.query(models.Employee).filter(models.Employee.is_active == False).all()
    
    # 4. ส่งข้อมูลไปที่หน้า HTML
    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "active_emps": active_emps,     # ✅ ส่งตัวแปรที่เพิ่ง Query มา
        "resigned_emps": resigned_emps,   # ✅ ส่งตัวแปรที่เพิ่ง Query มา
        "public_vapid_key": VAPID_PUBLIC_KEY,
        "user_role": user.role, 
        "user": user,
        "texts": texts
    })

@app.get("/add-employee", response_class=HTMLResponse)
async def add_employee_page(
    request: Request,
    texts: dict = Depends(get_lang),
    user: models.Employee = Depends(get_current_active_user),
    db: Session = Depends(get_db) # เพิ่ม db เข้ามาเผื่อใช้ตรวจสอบข้อมูล
):
    # ตรวจสอบว่า user ที่ได้มามีตัวตนและมี attribute role จริงไหม
    if not hasattr(user, 'role') or user.role != "Admin":
        return RedirectResponse(url="/dashboard?error=permission", status_code=303)
    
    return templates.TemplateResponse("add_employee.html", {
        "request": request,
        "texts": texts,
        "user": user # ส่ง user ไปให้หน้า HTML ด้วย เผื่อต้องโชว์ชื่อคนทำรายการ
    })

@app.post("/add-employee")
async def handle_add_employee(
    request: Request,
    user: models.Employee = Depends(get_current_active_user),
    employee_code: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    nickname: str = Form(None),
    phone_number: str = Form(None),
    id_card_number: str = Form(None),
    address: str = Form(None),
    bank_account_number: str = Form(None),
    position: str = Form(...),
    role: str = Form(...),
    password: str = Form(...),
    base_salary: float = Form(0.0),
    position_allowance: float = Form(0.0),
    profile_picture: UploadFile = File(None),
    documents: List[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    # 1. เช็คสิทธิ์ Admin
    if not hasattr(user, 'role') or user.role != "Admin":
        raise HTTPException(status_code=403, detail="คุณไม่มีสิทธิ์")

    # 2. เช็คเลขบัตรซ้ำ (เข้ารหัสก่อนเช็ค)
    if id_card_number:
        target_id = encrypt_data(id_card_number)
        if db.query(models.Employee).filter(models.Employee.id_card_number == target_id).first():
            return templates.TemplateResponse("add_employee.html", {"request": request, "error": "เลขบัตรนี้มีในระบบแล้ว", "texts": get_lang()})

    # 3. 📸 จัดการรูปโปรไฟล์ (ส่งไป Cloudinary)
    profile_url = "/static/img/default-avatar.png"
    if profile_picture and profile_picture.filename:
        try:
            upload_result = cloudinary.uploader.upload(
                profile_picture.file,
                folder="hrm/profiles",
                public_id=f"emp_{employee_code}",
                overwrite=True
            )
            profile_url = upload_result.get("secure_url")
        except Exception as e:
            print(f"Cloudinary Profile Error: {e}")

    # 4. เข้ารหัสข้อมูลและ Hash Password
    new_emp = models.Employee(
        employee_code=employee_code,
        first_name=first_name,
        last_name=last_name,
        nickname=nickname,
        phone_number=encrypt_data(phone_number),
        id_card_number=encrypt_data(id_card_number),
        bank_account_number=encrypt_data(bank_account_number),
        address=address,
        position=position,
        role=role,
        base_salary=base_salary,
        position_allowance=position_allowance,
        profile_picture=profile_url, # ✅ ลิงก์ Cloudinary (ไม่หายแน่นอน)
        hashed_password=pwd_context.hash(password)
    )
    
    db.add(new_emp)
    db.commit()
    db.refresh(new_emp)

    # 5. 📄 จัดการไฟล์เอกสาร PDF (ส่งไป Cloudinary)
    if documents:
        for doc in documents:
            if doc.filename:
                try:
                    doc_upload = cloudinary.uploader.upload(
                        doc.file,
                        folder=f"hrm/docs/{employee_code}",
                        resource_type="raw", # สำคัญสำหรับ PDF
                        public_id=doc.filename
                    )
                    new_doc = models.EmployeeDocument(
                        file_path=doc_upload.get("secure_url"), # ✅ ลิงก์ Cloudinary
                        file_name=doc.filename,
                        employee_id=new_emp.id
                    )
                    db.add(new_doc)
                except Exception as e:
                    print(f"Cloudinary Doc Error: {e}")
        db.commit()

    return RedirectResponse(url="/dashboard?msg=success", status_code=303)

# --- 1. แสดงหน้าฟอร์มแก้ไข ---
@app.get("/edit-employee/{emp_id}", response_class=HTMLResponse)
async def edit_employee_page(emp_id: int, request: Request,user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang), db: Session = Depends(get_db)):
    
    if request.cookies.get("user_role") != "Admin":
        return RedirectResponse(url="/check-in-page", status_code=303)
    
    employee = db.query(models.Employee).filter(models.Employee.id == emp_id).first()
    return templates.TemplateResponse("edit_employee.html",{"request": request,"texts": texts, "employee": employee})

# --- 2. รับข้อมูลจากฟอร์มแก้ไข (POST) ---
@app.post("/edit-employee/{emp_id}")
async def handle_edit_employee(
    request: Request,
    emp_id: int,
    first_name: str = Form(...),
    last_name: str = Form(...),
    nickname: str = Form(None),
    id_card_number: str = Form(None),
    phone_number: str = Form(None),
    address: str = Form(None),
    bank_account_number: str = Form(None),
    position: str = Form(...),
    role: str = Form(...),
    profile_picture: UploadFile = File(None),
    documents: List[UploadFile] = File(None),
    user: models.Employee = Depends(get_current_active_user), # 🛡️ เช็ค Session ในตัว
    db: Session = Depends(get_db)
):
    # --- 1. ตรวจสอบสิทธิ์ Admin ---
    if user.role != "Admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    
    employee = db.query(models.Employee).filter(models.Employee.id == emp_id).first()
    if not employee:
        return RedirectResponse(url="/employees", status_code=status.HTTP_303_SEE_OTHER)

    # --- 2. UNIQUE Check (Encryption Version) ---
    if id_card_number:
        # ต้อง Encrypt ค่าใหม่ก่อนไปค้นหาใน DB
        encrypted_id_input = encrypt_data(id_card_number)
        existing_emp = db.query(models.Employee).filter(
            models.Employee.id_card_number == encrypted_id_input,
            models.Employee.id != emp_id
        ).first()
        if existing_emp:
            # นายอาจจะเปลี่ยนเป็นดึงข้อมูลเดิมมาโชว์แล้วส่ง Error กลับไปหน้า HTML
            return templates.TemplateResponse("edit_employee.html", {
                "request": request,
                "employee": employee,
                "error": "เลขบัตรประชาชนนี้มีในระบบแล้ว"
            })

    # --- 3. อัปเดตข้อมูลพร้อมเข้ารหัส (Encryption) ---
    employee.first_name = first_name
    employee.last_name = last_name
    employee.nickname = nickname if nickname and nickname != "None" else employee.nickname
    employee.address = address
    employee.position = position
    employee.role = role
    
    # เข้ารหัสข้อมูลสำคัญก่อนบันทึก
    employee.id_card_number = encrypt_data(id_card_number) if id_card_number else employee.id_card_number
    employee.phone_number = encrypt_data(phone_number) if phone_number else employee.phone_number
    employee.bank_account_number = encrypt_data(bank_account_number) if bank_account_number else employee.bank_account_number

    # --- 4. จัดการรูปโปรไฟล์ ---
    if profile_picture and profile_picture.filename:
        os.makedirs("uploads/profile_pics", exist_ok=True)
        file_ext = profile_picture.filename.split(".")[-1]
        profile_path = f"uploads/profile_pics/{employee.employee_code}.{file_ext}"
        with open(profile_path, "wb") as buffer:
            shutil.copyfileobj(profile_picture.file, buffer)
        employee.profile_picture = profile_path

    # --- 5. จัดการเอกสาร PDF ---
    if documents:
        os.makedirs("uploads/documents", exist_ok=True)
        for doc in documents:
            if doc.filename:
                doc_path = f"uploads/documents/{employee.employee_code}_{doc.filename}"
                with open(doc_path, "wb") as buffer:
                    shutil.copyfileobj(doc.file, buffer)
                
                new_doc = models.EmployeeDocument(
                    file_path=doc_path,
                    file_name=doc.filename,
                    employee_id=employee.id
                )
                db.add(new_doc)
    
    db.commit()
    return RedirectResponse(url="/dashboard?msg=updated", status_code=status.HTTP_303_SEE_OTHER)

# --- 3. ฟังก์ชันลบข้อมูล ---
@app.get("/delete-employee/{emp_id}")
async def delete_employee(emp_id: int, db: Session = Depends(get_db)):
    employee = db.query(models.Employee).filter(models.Employee.id == emp_id).first()
    if employee:
        db.delete(employee)
        db.commit()
    return RedirectResponse(url="/dashboard?msg=deleted", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/employee/{emp_id}", response_class=HTMLResponse)
async def employee_detail(
    emp_id: int, 
    request: Request,
    user: models.Employee = Depends(get_current_active_user),
    texts: dict = Depends(get_lang), 
    db: Session = Depends(get_db)
):
    # ดึงข้อมูลพนักงาน
    employee = db.query(models.Employee).filter(models.Employee.id == emp_id).first()
    
    if not employee:
        return HTMLResponse(content="<p class='text-danger'>ไม่พบข้อมูลพนักงานท่านนี้ในระบบ</p>", status_code=404)

    # --- ✨ ส่วนที่เพิ่ม: ถอดรหัสข้อมูลก่อนแสดงผล ---
    # เราจะสร้าง Dict ใหม่เพื่อไม่ให้กระทบข้อมูลใน Database
    display_data = {
        "phone_number": decrypt_data(employee.phone_number) if employee.phone_number else "",
        "id_card_number": decrypt_data(employee.id_card_number) if employee.id_card_number else "",
        "bank_account_number": decrypt_data(employee.bank_account_number) if employee.bank_account_number else ""
    }

    return templates.TemplateResponse("employee_detail.html", {
        "request": request,
        "texts": texts, 
        "employee": employee,
        "decrypted": display_data  # ส่งค่าที่ถอดรหัสแล้วแยกไป
    })

# --- 🚩 ฟังก์ชันแจ้งลาออก ---
@app.post("/admin/employee/resign/{emp_id}")
async def resign_employee(
    emp_id: int, 
    db: Session = Depends(get_db),
    user: models.Employee = Depends(get_current_active_user)
):
    # เช็คสิทธิ์ก่อน (ต้องเป็น Admin เท่านั้น)
    if not user or user.role != "Admin":
        return RedirectResponse(url="/dashboard?error=permission", status_code=303)

    target_user = db.query(models.Employee).filter(models.Employee.id == emp_id).first()
    if target_user:
        target_user.is_active = False  # 🔴 เปลี่ยนสถานะเป็นลาออก
        db.commit()
    
    return RedirectResponse(url="/dashboard?msg=resigned", status_code=303)

# --- 🟢 ฟังก์ชันดึงกลับเป็นพนักงาน (เผื่อกดผิด) ---
@app.post("/admin/employee/restore/{emp_id}")
async def restore_employee(
    emp_id: int, 
    db: Session = Depends(get_db),
    user: models.Employee = Depends(get_current_active_user)
):
    if not user or user.role != "Admin":
        return RedirectResponse(url="/dashboard?error=permission", status_code=303)

    target_user = db.query(models.Employee).filter(models.Employee.id == emp_id).first()
    if target_user:
        target_user.is_active = True  # 🟢 ดึงกลับมาทำงานปกติ
        db.commit()
    
    return RedirectResponse(url="/dashboard?msg=resigned", status_code=303)

# 1. หน้าแสดงฟอร์ม Login
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    # สร้างการตอบกลับหน้า Login
    res = templates.TemplateResponse("login.html", {"request": request})
    
    # --- ท่าไม้ตาย: สั่งลบ Cookie ทันทีที่เข้าหน้านี้ ---
    res.delete_cookie("is_logged_in")
    res.delete_cookie("user_role")
    res.delete_cookie("user_name")
    
    return res

@app.post("/login")
async def handle_login(
    request: Request,texts: dict = Depends(get_lang),
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # 1. ค้นหาพนักงาน
    user = db.query(models.Employee).filter(models.Employee.employee_code == username).first()
    
    # 2. ตรวจสอบรหัสผ่าน
    if user and pwd_context.verify(password.encode('utf-8')[:72], user.hashed_password):
        
        # --- [ส่วนที่เพิ่มใหม่: Single Device Login] ---
        # เจน Session ID ใหม่ (ใคร Login ล่าสุด คนนั้นได้เลขนี้ไป)
        new_session_id = str(uuid.uuid4())
        
        # อัปเดตลง Database
        user.current_session_id = new_session_id
        db.commit()
        # --------------------------------------------

        # กำหนดหน้าปลายทาง
        res = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        
        # 3. ตั้งค่า Cookie สำคัญ
        max_age = 60 * 60 * 24 * 30  # 30 วัน

        # ฝังเลข Session ล่าสุดลงในเครื่องนี้
        res.set_cookie(key="session_id", value=new_session_id, max_age=max_age, httponly=True)
        
        # Cookie อื่นๆ ของเดิม
        res.set_cookie(key="is_logged_in", value="true", max_age=max_age)
        res.set_cookie(key="user_name", value=user.employee_code, max_age=max_age) 
        res.set_cookie(key="user_role", value=user.role, max_age=max_age)
        res.set_cookie(key="user_id", value=str(user.id), max_age=max_age) 
        
        return res
    
    # กรณี Login ไม่สำเร็จ
    return templates.TemplateResponse("login.html", {
        "request": request,
        "texts": texts, 
        "error": "รหัสพนักงานหรือรหัสผ่านไม่ถูกต้อง"
    })

# 3. ฟังก์ชันออกจากระบบ
@app.get("/logout")
async def logout():
    res = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    # ลบ Cookie ทั้งหมดที่เกี่ยวกับ Session
    res.delete_cookie("is_logged_in")
    res.delete_cookie("user_name")
    return res

# --- หน้าแสดงฟอร์มเปลี่ยนรหัสผ่าน ---
@app.get("/change-password", response_class=HTMLResponse)
async def change_password_page(request: Request,user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang)):
    if request.cookies.get("is_logged_in") != "true":
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("change_password.html", {"texts": texts,"request": request})

# --- จัดการการเปลี่ยนรหัสผ่านใน Database ---
@app.post("/change-password")
async def handle_change_password(
    request: Request,user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang),
    old_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    # 1. ตรวจสอบรหัสผ่านใหม่และยืนยันว่าตรงกันไหม
    if new_password != confirm_password:
        return templates.TemplateResponse("change_password.html", {
            "request": request, 
            "error": "รหัสผ่านใหม่และยืนยันรหัสผ่านไม่ตรงกัน"
        })

    # 2. ค้นหา User จากรหัสพนักงานที่เก็บไว้ใน Cookie
    emp_code = request.cookies.get("user_name")
    user = db.query(models.Employee).filter(models.Employee.employee_code == emp_code).first()

    if user:
        # 3. แก้ไข: ตรวจสอบรหัสผ่านเดิมด้วย pwd_context.verify (แทนการ Hard-code "1234")
        if pwd_context.verify(old_password, user.hashed_password):
            
            # 4. แก้ไข: เข้ารหัสผ่านใหม่ (Hash) ก่อนบันทึกลง Database
            user.hashed_password = pwd_context.hash(new_password)
            db.commit()
            
            # 5. ปรับ URL ให้ Redirect ไปที่หน้า dashboard หรือหน้าที่ต้องการ
            return RedirectResponse(url="/dashboard?msg=pw_changed", status_code=status.HTTP_303_SEE_OTHER)
    
    # กรณีรหัสผ่านเดิมไม่ถูกต้อง
    return templates.TemplateResponse("change_password.html", {
        "request": request,
        "texts": texts, 
        "error": "รหัสผ่านเดิมไม่ถูกต้อง"
    })
    
@app.get("/check-in-page", response_class=HTMLResponse)
async def check_in_page(request: Request,user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang), db: Session = Depends(get_db)):
    emp_code = request.cookies.get("user_name")
    user = db.query(models.Employee).filter(models.Employee.employee_code == emp_code).first()
    
    # ถ้าหา user ไม่เจอ (เช่น ยังไม่ได้ login หรือ cookie หมดอายุ) ให้เตะไปหน้า Login
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    # ตรวจสอบว่าวันนี้ลงเวลาไปหรือยัง
    attendance = db.query(models.Attendance).filter(
        models.Attendance.employee_id == user.id,
        models.Attendance.date == date.today()
    ).first()
    
    return templates.TemplateResponse("check_in_page.html", {"texts": texts,"request": request, "attendance": attendance})

# ฟังก์ชันช่วยแปลง Base64 เป็นไฟล์ภาพ
def save_attendance_photo(base64_data, emp_code, type="in"):
    if not base64_data:
        return None
    
    # ตรวจสอบและสร้างโฟลเดอร์ถ้ายังไม่มี
    upload_dir = "uploads/attendance_photos"
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)

    # ตัดส่วน Header ของ Base64 ออก (data:image/jpeg;base64,...)
    header, encoded = base64_data.split(",", 1)
    data = base64.b64decode(encoded)
    
    # ตั้งชื่อไฟล์: รหัสพนักงาน_ประเภท_วันเวลา_uuid.jpg
    file_name = f"{emp_code}_{type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.jpg"
    file_path = os.path.join(upload_dir, file_name)
    
    with open(file_path, "wb") as f:
        f.write(data)
    
    return file_name

@app.post("/attendance/check-in")
async def handle_check_in(
    request: Request,user: models.Employee = Depends(get_current_active_user), 
    lat: float = Form(None), 
    lon: float = Form(None),
    image_data: str = Form(None), 
    db: Session = Depends(get_db)
):
    emp_code = request.cookies.get("user_name")
    user = db.query(models.Employee).filter(models.Employee.employee_code == emp_code).first()
    
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    now = datetime.now()
    today = now.date()
    current_time = now.time()
    schedule = user.schedule

    # ค้นหา Record ของวันนี้
    attendance = db.query(models.Attendance).filter(
        models.Attendance.employee_id == user.id,
        models.Attendance.date == today
    ).first()

    if not attendance:
        # --- 📸 ส่วนที่ 1: บันทึกรูปภาพตอนเข้า (Check-in) ---
        photo_name = save_attendance_photo(image_data, user.employee_code, "in")
        
        late_min = 0
        status = "Normal"

        if schedule and schedule.work_start_time:
            start_dt = datetime.strptime(schedule.work_start_time, "%H:%M")
            start_time = start_dt.time()
            
            if current_time > start_time:
                diff = datetime.combine(today, current_time) - datetime.combine(today, start_time)
                total_late = int(diff.total_seconds() / 60)
                late_min = max(0, total_late - (schedule.grace_period_late or 0))
                if late_min > 0:
                    status = "Late"

        new_attendance = models.Attendance(
            employee_id=user.id,
            date=today,
            check_in=now, # ส่งเป็น datetime object สำหรับ SQLite
            lat=lat,
            lon=lon,
            late_minutes=late_min,
            image_in=photo_name, # บันทึกชื่อไฟล์รูปเข้า
            status=status
        )
        db.add(new_attendance)
    
    else:
        # --- 📸 ส่วนที่ 2: บันทึกรูปภาพตอนออก (Check-out) ---
        photo_name = save_attendance_photo(image_data, user.employee_code, "out")
        
        early_min = 0
        if schedule and schedule.work_end_time:
            end_dt = datetime.strptime(schedule.work_end_time, "%H:%M")
            end_time = end_dt.time()
            
            if current_time < end_time:
                diff = datetime.combine(today, end_time) - datetime.combine(today, current_time)
                total_early = int(diff.total_seconds() / 60)
                early_min = max(0, total_early - (schedule.grace_period_early or 0))

        attendance.check_out = now # ส่งเป็น datetime object เพื่อแก้ SQLite Error
        attendance.early_minutes = early_min
        attendance.image_out = photo_name # บันทึกชื่อไฟล์รูปออก
        
        if attendance.late_minutes > 0 or early_min > 0:
            attendance.status = "Abnormal"

    db.commit()
    return RedirectResponse(url="/check-in-page?msg=success", status_code=303)

@app.post("/attendance/check-out")
async def handle_check_out(
    request: Request,user: models.Employee = Depends(get_current_active_user), 
    lat: float = Form(None), 
    lon: float = Form(None),
    image_data: str = Form(None), 
    db: Session = Depends(get_db)
):
    emp_code = request.cookies.get("user_name")
    user = db.query(models.Employee).filter(models.Employee.employee_code == emp_code).first()
    
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    now = datetime.now()
    today = now.date()
    current_time = now.time()
    schedule = user.schedule

    # ค้นหา Record ของวันนี้ที่เคย Check-in ไว้ (ใช้ตัวแปรเดียวให้ชัดเจน)
    attendance = db.query(models.Attendance).filter(
        models.Attendance.employee_id == user.id,
        models.Attendance.date == today
    ).first()
    
    if attendance:
        # --- 📸 1. บันทึกรูปภาพตอนออกงาน ---
        photo_name = save_attendance_photo(image_data, emp_code, "out")
        attendance.image_out = photo_name 

        # --- 2. คำนวณการออกก่อนเวลา (Early Out) ---
        early_min = 0
        if schedule and schedule.work_end_time:
            end_dt = datetime.strptime(schedule.work_end_time, "%H:%M")
            end_time = end_dt.time()
            
            if current_time < end_time:
                diff = datetime.combine(today, end_time) - datetime.combine(today, current_time)
                total_early = int(diff.total_seconds() / 60)
                # ใช้ชื่อฟิลด์ตามตารางของคุณ (grace_period_early_out)
                early_min = max(0, total_early - (schedule.grace_period_early_out or 0))

        # --- 3. บันทึกค่าลง Database ---
        attendance.check_out = now # ใช้ datetime วัตถุเพื่อเลี่ยง Error ใน SQLite
        attendance.early_minutes = early_min
        
        # ปรับสถานะ (ถ้าสายหรือออกก่อนให้เป็น Abnormal)
        if (attendance.late_minutes and attendance.late_minutes > 0) or early_min > 0:
            attendance.status = "Abnormal"
        else:
            attendance.status = "Normal"
        
        # อัปเดตพิกัดล่าสุดตอนออก
        attendance.lat = lat 
        attendance.lon = lon
        
        db.commit()

    return RedirectResponse(url="/check-in-page?msg=checkout_success", status_code=303)

@app.post("/save-schedules")
async def save_schedules(request: Request,user: models.Employee = Depends(get_current_active_user), db: Session = Depends(get_db)):
    # 1. ตรวจสอบการ Login
    if request.cookies.get("is_logged_in") != "true":
        return RedirectResponse(url="/login", status_code=303)

    # 2. เพิ่มการตรวจสอบสิทธิ Admin (สำคัญมาก!)
    if request.cookies.get("user_role") != "Admin":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="คุณไม่มีสิทธิแก้ไขตารางเวลา")

    form_data = await request.form()
    employees = db.query(models.Employee).all()

    for emp in employees:
        
        # ดึงค่า checkbox ของพนักงานแต่ละคน (จะได้ออกมาเป็น list เช่น ['Sat', 'Sun'])
        selected_days = form_data.getlist(f"weekly_off_{emp.id}")
        
        # 2. รับค่าวันทำงาน (Checkbox) ที่เราส่งมาเป็น days_{{ emp.id }}
        # ในระบบของคุณ ติ๊กถูก = วันทำงาน ดังนั้นวันที่ไม่ถูกติ๊ก = วันหยุด
        work_days_list = form_data.getlist(f"days_{emp.id}")
        
        # บันทึกรายชื่อ "วันทำงาน" ลงในฟิลด์ weekly_off ของ Employee
        # (แนะนำให้เปลี่ยนชื่อฟิลด์เป็น work_days ในอนาคตเพื่อให้ไม่งงครับ)
        emp.weekly_off = ",".join(work_days_list)
        
        start = form_data.get(f"start_{emp.id}")
        late = form_data.get(f"late_{emp.id}")
        end = form_data.get(f"end_{emp.id}")
        early = form_data.get(f"early_{emp.id}")

        schedule = db.query(models.WorkSchedule).filter(models.WorkSchedule.employee_id == emp.id).first()
        
        if not schedule:
            schedule = models.WorkSchedule(employee_id=emp.id)
            db.add(schedule)
        
        schedule.work_start_time = start
        schedule.grace_period_late = int(late) if late else 0
        schedule.work_end_time = end
        schedule.grace_period_early_out = int(early) if early else 0

    db.commit()
    return RedirectResponse(url="/schedules?msg=success", status_code=303)

@app.get("/schedules", response_class=HTMLResponse)
async def schedule_management_page(request: Request,user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang), db: Session = Depends(get_db)):
    # 1. ตรวจสอบการ Login
    if request.cookies.get("is_logged_in") != "true":
        return RedirectResponse(url="/login", status_code=303)
    
    # --- เพิ่มตรงนี้: ตรวจสอบสิทธิ Admin ---
    if request.cookies.get("user_role") != "Admin":
        # ถ้าไม่ใช่ Admin ให้เตะไปหน้าลงเวลา (หรือหน้า Dashboard ที่จำกัดข้อมูล)
        return RedirectResponse(url="/check-in-page", status_code=303)
    
    # 2. ดึงรายชื่อพนักงานทุกคนมาแสดงเพื่อตั้งค่า
    employees = db.query(models.Employee).all()
    
    return templates.TemplateResponse("schedules.html", {
        "request": request,
        "texts": texts, 
        "employees": employees
    })

@app.get("/attendance-report", response_class=HTMLResponse)
async def attendance_report(
    request: Request, user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang),
    start_date: str = Query(None), 
    end_date: str = Query(None), 
    search_query: str = Query(None), 
    db: Session = Depends(get_db)
):
    user_role = request.cookies.get("user_role")
    user_name = request.cookies.get("user_name")
    
    # 1. จัดการช่วงวันที่ให้เป็น Date Object
    try:
        s_date = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else date.today()
        e_date = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else s_date
    except ValueError:
        s_date = e_date = date.today()
    
    # 2. กรองรายชื่อพนักงาน
    query = db.query(models.Employee)
    if user_role == "Admin":
        if search_query and search_query.strip():
            pattern = f"%{search_query.strip()}%"
            query = query.filter(
                (models.Employee.employee_code.like(pattern)) |
                (models.Employee.first_name.like(pattern)) |
                (models.Employee.last_name.like(pattern))
            )
        employees_to_check = query.all()
    else:
        employees_to_check = db.query(models.Employee).filter(models.Employee.employee_code == user_name).all()
    
    report_data = []
    
    # 3. วนลูปตามช่วงวันที่
    current_day = s_date
    while current_day <= e_date:
        today_name = current_day.strftime('%a') 
        is_holiday = db.query(models.Holiday).filter(models.Holiday.holiday_date == current_day).first()
        
        # ภายในลูป while current_day <= e_date:
        for emp in employees_to_check:
            record = db.query(models.Attendance).filter(
                models.Attendance.employee_id == emp.id,
                func.date(models.Attendance.date) == current_day
            ).first()
    
            if record:
                # 1. ตั้งค่าพื้นฐาน
                record.late_minutes = 0
                record.early_minutes = 0
                record.status = "ปกติ" # ค่าเริ่มต้น
                
                sched = emp.schedule
                if sched:
                    # --- 🚩 กรณี: ไม่ลงเวลาเข้า ---
                    if not record.check_in and record.check_out:
                        record.status = "ไม่ลงเวลาเข้า"
                    
                    # --- 🚩 กรณี: สาย (Late) ---
                    elif record.check_in and sched.work_start_time:
                        target_in = datetime.strptime(sched.work_start_time[:5], "%H:%M").time()
                        actual_in = record.check_in.time()
                        if actual_in > target_in:
                            diff_in = datetime.combine(current_day, actual_in) - datetime.combine(current_day, target_in)
                            late_mins = int(diff_in.total_seconds() / 60)
                            if late_mins > (sched.grace_period_late or 0):
                                record.late_minutes = late_mins
                                record.status = "สาย"

                    # --- 🚩 กรณี: ออกก่อนเวลา (Early Out) ---
                    # เช็คต่อจาก "สาย" หากสายด้วยและออกก่อนด้วย จะโชว์ว่าออกก่อน (หรือคุณจะรวมคำก็ได้)
                    if record.check_out and sched.work_end_time:
                        target_out = datetime.strptime(sched.work_end_time[:5], "%H:%M").time()
                        actual_out = record.check_out.time()
                        if actual_out < target_out:
                            diff_out = datetime.combine(current_day, target_out) - datetime.combine(current_day, actual_out)
                            early_mins = int(diff_out.total_seconds() / 60)
                            if early_mins > (sched.grace_period_early_out or 0):
                                record.early_minutes = early_mins
                                # ถ้าเดิมสถานะคือ "สาย" อยู่แล้ว อาจจะเปลี่ยนเป็น "สาย/ออกก่อน"
                                if record.status == "สาย":
                                    record.status = "สาย/ออกก่อน"
                                else:
                                    record.status = "ออกก่อนเวลา"

                # กรณีลืมลงเวลาออก (แต่มีเวลาเข้า)
                if record.check_in and not record.check_out:
                    record.status = "ยังไม่ลงเวลาออก"

                report_data.append(record)
        
            else:
                # ❌ กรณีไม่มีบันทึก (เช็ค ลา / วันหยุด / ขาดงาน)
                leave = db.query(models.LeaveRequest).filter(
                    models.LeaveRequest.employee_id == emp.id,
                    models.LeaveRequest.status == "Approved",
                    models.LeaveRequest.start_date <= current_day,
                    models.LeaveRequest.end_date >= current_day
                ).first()
                
                is_work_day = emp.weekly_off and today_name in emp.weekly_off
                
                if leave:
                    status = f"ลา ({leave.leave_type})" 
                elif is_holiday:
                    status = f"วันหยุด ({is_holiday.holiday_name})"
                elif emp.weekly_off and not is_work_day:
                    status = "วันหยุดประจำสัปดาห์"
                else:
                    status = "ขาดงาน"
                    # นับยอดสะสมวันขาดงานไว้ในตัวแปรเพื่อส่งไปหน้า Payroll
                    emp.total_absent_days = getattr(emp, 'total_absent_days', 0) + 1
                
                report_data.append({
                    "date": current_day,
                    "employee": emp,
                    "check_in": None,
                    "check_out": None,
                    "late_minutes": 0,
                    "early_minutes": 0,
                    "status": status,
                    "location_in": "-"
                })
        
        current_day += timedelta(days=1)
    
    # 4. ส่งข้อมูลกลับหน้าจอ
    return templates.TemplateResponse("attendance_report.html", {
        "request": request, 
        "records": report_data,
        "start_date": s_date,
        "end_date": e_date,
        "texts": texts,
        "search_query": search_query
    })

@app.get("/my-profile", response_class=HTMLResponse)
async def my_profile_page(
    request: Request,
    user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang), # 🛡️ ตัวนี้เช็ค Login/Session ให้จบในตัวเดียวแล้ว
    db: Session = Depends(get_db)
):
    # ไม่ต้องเช็คคุกกี้ซ้ำแล้วครับ เพราะถ้าไม่ Login ตัว Depends จะดีดออกไปหน้า Login ให้เอง
    
    # 🔓 ถอดรหัสข้อมูลก่อนส่งไปโชว์ที่หน้า HTML
    # เราใช้วิธี Copy ข้อมูลออกมาถอดรหัส เพื่อไม่ให้ไปกระทบค่าใน Database จริงๆ
    display_employee = user
    display_employee.phone_number = decrypt_data(user.phone_number)
    display_employee.id_card_number = decrypt_data(user.id_card_number)
    display_employee.bank_account_number = decrypt_data(user.bank_account_number)

    return templates.TemplateResponse("employee_detail.html", {
        "request": request, 
        "employee": display_employee,
        "public_vapid_key": VAPID_PUBLIC_KEY,
        "texts": texts, 
        "is_staff_view": True # เพื่อซ่อนปุ่ม Edit/Delete สำหรับพนักงานทั่วไป
    })
    
@app.post("/leave/apply")
async def handle_leave_apply(
    request: Request,user: models.Employee = Depends(get_current_active_user),
    leave_type: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    reason: str = Form(...),
    evidence: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    # 1. ตรวจสอบ Login (ใช้ employee_code จาก user_name cookie)
    emp_code = request.cookies.get("user_name")
    user = db.query(models.Employee).filter(models.Employee.employee_code == emp_code).first()
    
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    # 2. จัดการไฟล์แนบ
    evidence_path = None
    if evidence and evidence.filename:
        file_ext = evidence.filename.split(".")[-1]
        file_name = f"{user.employee_code}_{datetime.now().strftime('%Y%m%d%H%M')}.{file_ext}"
        
        # วาง Path ให้ถูกต้องสำหรับ Windows/Linux
        evidence_path = os.path.join("static", "uploads", "leave_documents", file_name)
        full_path = os.path.join(os.getcwd(), "app", evidence_path)
        
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "wb") as buffer:
            shutil.copyfileobj(evidence.file, buffer)

    # 3. บันทึกลง Database
    new_leave = models.LeaveRequest(
        employee_id=user.id,
        leave_type=leave_type,
        start_date=datetime.strptime(start_date, "%Y-%m-%d").date(),
        end_date=datetime.strptime(end_date, "%Y-%m-%d").date(),
        reason=reason,
        evidence_path=evidence_path,
        status="Pending"
    )
    db.add(new_leave)
    db.commit() # ✅ บันทึกให้สำเร็จก่อนแจ้งเตือน

    # 🚩 ส่วนส่งแจ้งเตือนหา Admin (เวอร์ชันแก้ Error user_id)
    try:
        # 1. ดึง Admin ทั้งหมด
        admins = db.query(models.Employee).filter(
            (models.Employee.role.ilike("admin")) | 
            (models.Employee.employee_code == "admin")
        ).all()
        
        print(f"🔔 DEBUG: พบ Admin ทั้งหมด {len(admins)} คน")

        # 2. วนลูปส่งแจ้งเตือน
        for admin in admins:
            print(f"🚀 DEBUG: กำลังส่ง Push หา Admin ID: {admin.id}")
            
            # ดึงรหัสพนักงานจากตัวแปร user (ที่มีอยู่ในฟังก์ชัน handle_leave_apply)
            sender_info = user.employee_code if user else "ไม่ระบุรหัส"
            
            send_push_to_user(
                admin.id, 
                "📢 มีคำขอลาใหม่", 
                f"พนักงานรหัส {sender_info} ส่งคำขอรออนุมัติ", 
                db
            )
    except Exception as e:
        print(f"❌ Notification Error ในจุดส่งหา Admin: {e}")

    return RedirectResponse(url="/check-in-page?msg=leave_sent", status_code=303)

@app.get("/admin/leaves", response_class=HTMLResponse)
async def admin_leave_management(request: Request,user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang), db: Session = Depends(get_db)):
    # กั้นสิทธิ Admin
    if request.cookies.get("user_role") != "Admin":
        return RedirectResponse(url="/check-in-page", status_code=303)
    
    # ดึงรายการลาที่รอการอนุมัติ (หรือทั้งหมด)
    pending_leaves = db.query(models.LeaveRequest).order_by(models.LeaveRequest.created_at.desc()).all()
    
    return templates.TemplateResponse("admin_leaves.html", {
        "request": request,
        "texts": texts,
        "leaves": pending_leaves
    })
    
@app.post("/admin/leave/approve/{leave_id}")
async def approve_leave(leave_id: int, status: str = Form(...),admin_remark: str = Form(None),user: models.Employee = Depends(get_current_active_user), db: Session = Depends(get_db)):
    # 1. ค้นหาใบลา
    leave = db.query(models.LeaveRequest).filter(models.LeaveRequest.id == leave_id).first()
    
    if leave:
        # --- [ส่วนคำนวณวันลา] ---
        # ถ้าเป็นการอนุมัติ (Approved) และเป็นใบลาที่ระบุเวลา (เช่น ลาป่วย/ลากิจ รายวัน)
        if status.lower() == "approved":
            # ตรวจสอบว่าเป็นการลาภายในวันเดียวหรือไม่ (ถ้าลาหลายวันอาจต้องใช้สูตรคำนวณวันที่เพิ่ม)
            if leave.start_date == leave.end_date:
                # คำนวณชั่วโมงลา (สมมติว่าใน Model มีคอลัมน์ start_time และ end_time)
                # ถ้า Model ของคุณใช้ชื่อคอลัมน์อื่น ให้เปลี่ยนชื่อตามจริงนะครับ
                try:
                    # แปลงเวลาเป็นนาทีเพื่อหาผลต่าง
                    start_minutes = leave.start_time.hour * 60 + leave.start_time.minute
                    end_minutes = leave.end_time.hour * 60 + leave.end_time.minute
                    duration_hours = (end_minutes - start_minutes) / 60
                    
                    # ตรรกะ: มากกว่า 4 ชั่วโมง = 1 วัน, ถ้าน้อยกว่าหรือเท่ากับ = 0.5 วัน
                    days_to_deduct = 1.0 if duration_hours > 4 else 0.5
                except:
                    # กรณีไม่มีเวลา หรือเกิด Error ในการคำนวณ ให้ Default เป็น 1 วัน
                    days_to_deduct = 1.0
            else:
                # กรณีลาหลายวัน (เช่น ลาพักร้อน) คำนวณตามจำนวนวันจริง
                days_to_deduct = (leave.end_date - leave.start_date).days + 1

            # หักโควตาจากพนักงาน (ตรวจสอบชื่อคอลัมน์โควตาในฐานข้อมูลของคุณด้วยนะครับ)
            employee = db.query(models.Employee).filter(models.Employee.id == leave.employee_id).first()
            if employee:
                # หักโควตาตามประเภทการลา (ตัวอย่าง: sick_leave, personal_leave)
                # ต้องมั่นใจว่าใน DB คอลัมน์เหล่านี้เป็นประเภท Float
                if leave.leave_type == "ลาป่วย":
                    employee.sick_leave_quota -= days_to_deduct
                elif leave.leave_type == "ลากิจ":
                    employee.personal_leave_quota -= days_to_deduct
                elif leave.leave_type == "ลาพักร้อน":
                    employee.vacation_leave_quota -= days_to_deduct

        # --- [อัปเดตสถานะและแจ้งเตือน] ---
        leave.status = status 
        leave.admin_remark = admin_remark # ✅ บันทึกลง DB
        db.commit() # บันทึกทั้งสถานะและยอดโควตาที่ถูกหัก
        
        # 2. เตรียมข้อความแจ้งเตือนตามสถานะจริง
        # ปรับข้อความแจ้งเตือนให้เห็นเหตุผล
        remark_text = f" (เหตุผล: {admin_remark})" if admin_remark else ""
        status_text = "ได้รับการอนุมัติแล้ว" if status.lower() == "approved" else f"ไม่ได้รับการอนุมัติ{remark_text}"
        icon = "✅" if status.lower() == "approved" else "❌"

        # 🚩 3. ส่งแจ้งเตือน
        try:
            send_push_to_user(
                leave.employee_id, 
                f"{icon} ผลการพิจารณาการลา", 
                f"คำขอลาของคุณ{status_text}", 
                db
            )
        except Exception as e:
            print(f"Push Notification Error: {e}")
    
    # 🚩 4. บรรทัด return ต้องอยู่ล่างสุดเสมอ
    return RedirectResponse(url="/admin/leaves?msg=updated", status_code=303)

@app.get("/leave-apply", response_class=HTMLResponse)
async def leave_apply_page(request: Request,user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang)):
    # ตรวจสอบการ Login
    if request.cookies.get("is_logged_in") != "true":
        return RedirectResponse(url="/login", status_code=303)
        
    return templates.TemplateResponse("leave_apply.html", {"texts": texts,"request": request})

@app.get("/my-leaves", response_class=HTMLResponse)
async def my_leaves_page(request: Request,user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang), db: Session = Depends(get_db)):
    emp_code = request.cookies.get("user_name")
    user = db.query(models.Employee).filter(models.Employee.employee_code == emp_code).first()
    
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    approved_leaves = db.query(models.LeaveRequest).filter(
        models.LeaveRequest.employee_id == user.id,
        models.LeaveRequest.status == "Approved"
    ).all()

    used_days = {"ลาป่วย": 0, "ลากิจ": 0, "ลาพักร้อน": 0}
    
    for leave in approved_leaves:
        # --- Logic ใหม่: คำนวณตามเวลา ---
        # 1. คำนวณจำนวนวันจากวันที่ก่อน
        num_days = 1 # เบื้องต้นถือว่าลา 1 วัน (เนื่องจากตอนนี้โมเดลเราเก็บ date เดียวแต่มี start/end time)
        
        # 2. ถ้ามีการระบุเวลา ให้คำนวณสัดส่วน (สมมติเวลาทำงานปกติคือ 9 ชั่วโมงรวมพัก)
        if leave.start_date and leave.end_date:
            from datetime import datetime
            fmt = '%H:%M'
            t1 = leave.start_date
            t2 = leave.end_date
            
            # คำนวณชั่วโมงที่ลา
            diff_hours = (t2 - t1).seconds / 3600
            
            # ถ้าลาน้อยกว่าหรือเท่ากับ 4 ชั่วโมง ให้ถือเป็น 0.5 วัน (ลาครึ่งวัน)
            # ถ้าลามากกว่านั้นให้ถือเป็น 1 วัน หรือตามสัดส่วนชั่วโมงทำงานจริง
            if diff_hours <= 4:
                num_days = 0.5
            else:
                num_days = 1.0

        if leave.leave_type in used_days:
            used_days[leave.leave_type] += num_days

    return templates.TemplateResponse("my_leaves.html", {
        "request": request,"texts": texts,
        "leaves": db.query(models.LeaveRequest).filter(models.LeaveRequest.employee_id == user.id).all(),
        "quotas": {
            "sick": user.sick_leave_quota,
            "personal": user.personal_leave_quota,
            "vacation": user.vacation_leave_quota
        },
        "used": used_days
    })
    
@app.get("/admin/edit-employee/{emp_id}", response_class=HTMLResponse)
async def edit_employee_page(emp_id: int, request: Request,user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang), db: Session = Depends(get_db)):
    # เช็คสิทธิ Admin
    if request.cookies.get("user_role") != "Admin":
        return RedirectResponse(url="/dashboard", status_code=303)
    
    employee = db.query(models.Employee).filter(models.Employee.id == emp_id).first()
    return templates.TemplateResponse("edit_employee.html", {"texts": texts,"request": request, "employee": employee})

@app.post("/admin/edit-employee/{emp_id}")
async def handle_edit_employee(
    emp_id: int,user: models.Employee = Depends(get_current_active_user),
    sick_quota: int = Form(...),
    personal_quota: int = Form(...),
    vacation_quota: int = Form(...),
    db: Session = Depends(get_db)
):
    employee = db.query(models.Employee).filter(models.Employee.id == emp_id).first()
    if employee:
        employee.sick_leave_quota = sick_quota
        employee.personal_leave_quota = personal_quota
        employee.vacation_leave_quota = vacation_quota
        db.commit()
    
    return RedirectResponse(url="/dashboard?msg=updated", status_code=303)

@app.get("/my-attendance", response_class=HTMLResponse)
async def my_attendance(request: Request,user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang), db: Session = Depends(get_db)):
    user_name = request.cookies.get("user_name")
    emp = db.query(models.Employee).filter(models.Employee.employee_code == user_name).first()
    
    if not emp:
        return RedirectResponse(url="/login")

    s_date = date.today() - timedelta(days=30)
    e_date = date.today()
    
    report_data = []
    current_day = s_date
    
    while current_day <= e_date:
        today_name = current_day.strftime('%a')
        is_holiday = db.query(models.Holiday).filter(models.Holiday.holiday_date == current_day).first()
        record = db.query(models.Attendance).filter(
            models.Attendance.employee_id == emp.id,
            models.Attendance.date == current_day
        ).first()
        
        if record:
            sched = emp.schedule
            if sched:
                # 🚀 แก้ไขจุดที่ Error: แปลง String เป็น Time Object ก่อนคำนวณ
                def get_time_obj(t_val):
                    if isinstance(t_val, str):
                        try:
                            return datetime.strptime(t_val, "%H:%M:%S").time()
                        except ValueError:
                            return datetime.strptime(t_val, "%H:%M").time()
                    return t_val

                # คำนวณนาทีสาย
                if record.check_in and sched.work_start_time:
                    actual_in = record.check_in.hour * 60 + record.check_in.minute
                    st_time = get_time_obj(sched.work_start_time)
                    target_in = st_time.hour * 60 + st_time.minute
                    
                    grace_late = sched.grace_period_late or 0
                    if actual_in > (target_in + grace_late):
                        record.late_minutes = actual_in - target_in
                    else:
                        record.late_minutes = 0
                
                # คำนวณนาทีออกก่อน
                if record.check_out and sched.work_end_time:
                    actual_out = record.check_out.hour * 60 + record.check_out.minute
                    en_time = get_time_obj(sched.work_end_time)
                    target_out = en_time.hour * 60 + en_time.minute
                    
                    grace_early = sched.grace_period_early_out or 0
                    if actual_out < (target_out - grace_early):
                        record.early_minutes = target_out - actual_out
                    else:
                        record.early_minutes = 0

            # กำหนดสถานะ
            if (record.late_minutes and record.late_minutes > 0) or (record.early_minutes and record.early_minutes > 0):
                record.status = "ผิดปกติ"
            else:
                record.status = "ปกติ"
            report_data.append(record)
        else:
            # --- กรณีไม่มีบันทึก (เช็ค ลางาน/วันหยุด) ---
            leave = db.query(models.LeaveRequest).filter(
                models.LeaveRequest.employee_id == emp.id,
                models.LeaveRequest.status == "Approved",
                models.LeaveRequest.start_date <= current_day,
                models.LeaveRequest.end_date >= current_day
            ).first()

            is_work_day = emp.weekly_off and today_name in emp.weekly_off
            status = "ขาดงาน"
            if leave: status = f"ลา ({leave.leave_type})"
            elif is_holiday: status = f"วันหยุด ({is_holiday.holiday_name})"
            elif not is_work_day: status = "วันหยุดประจำสัปดาห์"

            report_data.append({
                "date": current_day,
                "status": status,
                "check_in": None,
                "check_out": None,
                "late_minutes": 0,
                "early_minutes": 0,
                "location_in": "ไม่มีพิกัด"
            })
            
        current_day += timedelta(days=1)

    return templates.TemplateResponse("my_attendance.html", {"texts": texts,"request": request, "records": report_data})

@app.post("/update-schedules")
async def update_schedules(request: Request,user: models.Employee = Depends(get_current_active_user), db: Session = Depends(get_db)):
    form_data = await request.form()
    employees = db.query(models.Employee).all()

    for emp in employees:
        # ดึงค่าจาก Form ตาม ID พนักงาน
        start_time = form_data.get(f"start_{emp.id}")
        end_time = form_data.get(f"end_{emp.id}")
        late_grace = form_data.get(f"late_{emp.id}", 0)
        early_grace = form_data.get(f"early_{emp.id}", 0)
        
        # ดึงค่า Checkbox วันทำงาน (เลือกหลายวัน)
        selected_days = form_data.getlist(f"days_{emp.id}")
        work_days_str = ",".join(selected_days) # แปลง List เป็น "Mon,Tue,Wed"

        # ตรวจสอบว่ามี Schedule เดิมไหม ถ้าไม่มีให้สร้างใหม่
        schedule = db.query(models.WorkSchedule).filter(models.WorkSchedule.employee_id == emp.id).first()
        
        if not schedule:
            schedule = models.WorkSchedule(employee_id=emp.id)
            db.add(schedule)

        # อัปเดตข้อมูล
        schedule.work_start_time = start_time
        schedule.work_end_time = end_time
        schedule.grace_period_late = int(late_grace)
        schedule.grace_period_early_out = int(early_grace)
        schedule.work_days = work_days_str

    db.commit()
    return RedirectResponse(url="/schedules", status_code=303)

@app.get("/holidays", response_class=HTMLResponse)
async def holiday_page(request: Request,user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang), db: Session = Depends(get_db)):
    holidays = db.query(models.Holiday).order_by(models.Holiday.holiday_date).all()
    return templates.TemplateResponse("holidays.html", {"texts": texts,"request": request, "holidays": holidays})

@app.post("/add-holiday")
async def add_holiday(holiday_date: date = Form(...), holiday_name: str = Form(...),user: models.Employee = Depends(get_current_active_user), db: Session = Depends(get_db)):
    new_holiday = models.Holiday(holiday_date=holiday_date, holiday_name=holiday_name)
    db.add(new_holiday)
    db.commit()
    return RedirectResponse(url="/holidays", status_code=303)

@app.get("/delete-holiday/{holiday_id}")
async def delete_holiday(holiday_id: int, db: Session = Depends(get_db)):
    holiday = db.query(models.Holiday).filter(models.Holiday.id == holiday_id).first()
    if holiday:
        db.delete(holiday)
        db.commit()
    return RedirectResponse(url="/holidays", status_code=303)

@app.get("/export-attendance")
async def export_attendance(
    background_tasks: BackgroundTasks, # เพิ่มสำหรับจัดการลบไฟล์หลังดาวน์โหลด
    start_date: str = Query(None), 
    end_date: str = Query(None), 
    search_query: str = Query(None), 
    db: Session = Depends(get_db)
):
    # 1. จัดการช่วงวันที่ (Logic เดียวกับหน้า Report)
    try:
        s_date = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else date.today()
        e_date = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else s_date
    except ValueError:
        s_date = e_date = date.today()

    # 2. กรองรายชื่อพนักงานตามเงื่อนไข
    query = db.query(models.Employee)
    if search_query and search_query.strip():
        pattern = f"%{search_query.strip()}%"
        query = query.filter(
            (models.Employee.employee_code.like(pattern)) |
            (models.Employee.first_name.like(pattern)) |
            (models.Employee.last_name.like(pattern))
        )
    employees_to_check = query.all()

    data_for_excel = []
    
    # 3. วนลูปตามช่วงวันที่เพื่อดึงข้อมูลทีละวัน
    current_day = s_date
    while current_day <= e_date:
        today_name = current_day.strftime('%a')
        is_holiday = db.query(models.Holiday).filter(models.Holiday.holiday_date == current_day).first()
        
        for emp in employees_to_check:
            record = db.query(models.Attendance).filter(
                models.Attendance.employee_id == emp.id,
                models.Attendance.date == current_day
            ).first()
            
            # กำหนดสถานะพื้นฐานกรณีไม่มี Record
            status = "ขาดงาน"
            if is_holiday:
                status = f"วันหยุด ({is_holiday.holiday_name})"
            elif emp.weekly_off and today_name in emp.weekly_off:
                status = "วันหยุดประจำสัปดาห์"

            # จัดรูปแบบแถวข้อมูลสำหรับ Excel
            data_for_excel.append({
                "วันที่": current_day,
                "รหัสพนักงาน": emp.employee_code,
                "ชื่อ-นามสกุล": f"{emp.first_name} {emp.last_name}",
                "เวลาเข้า": record.check_in.strftime('%H:%M:%S') if (record and record.check_in) else "-",
                "สาย (นาที)": record.late_minutes if (record and record.late_minutes) else 0,
                "เวลาออก": record.check_out.strftime('%H:%M:%S') if (record and record.check_out) else "-",
                "ออกก่อน (นาที)": record.early_minutes if (record and record.early_minutes) else 0,
                "สถานะ": record.status if (record and hasattr(record, 'status')) else status
            })
        current_day += timedelta(days=1)

    # 4. สร้างไฟล์ Excel
    df = pd.DataFrame(data_for_excel)
    file_name = f"attendance_{s_date}_to_{e_date}.xlsx"
    file_path = os.path.join("uploads", file_name) # แนะนำให้เก็บในโฟลเดอร์ชั่วคราว
    
    # ตรวจสอบว่ามีโฟลเดอร์ uploads หรือยัง
    if not os.path.exists("uploads"):
        os.makedirs("uploads")
        
    df.to_excel(file_path, index=False)

    # สั่งให้ลบไฟล์ทิ้งหลังจากส่งไฟล์ให้ User เรียบร้อยแล้ว
    background_tasks.add_task(os.remove, file_path)

    return FileResponse(
        path=file_path, 
        filename=file_name, 
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.post("/submit-attendance-request")
async def submit_attendance_request(
    request: Request,
    request_date: date = Form(...),
    check_in: str = Form(None),
    check_out: str = Form(None),
    reason: str = Form(...),
    lat: float = Form(None),
    lon: float = Form(None),
    db: Session = Depends(get_db)
):
    # 1. ตรวจสอบ User ก่อน
    user_name = request.cookies.get("user_name")
    user = db.query(models.Employee).filter(models.Employee.employee_code == user_name).first()
    
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    # 2. บันทึกลง Database ให้สำเร็จก่อน
    try:
        in_time = datetime.strptime(check_in, "%H:%M").time() if check_in else None
        out_time = datetime.strptime(check_out, "%H:%M").time() if check_out else None

        new_request = models.ManualAttendanceRequest(
            employee_id=user.id,
            request_date=request_date,
            check_in_time=in_time,
            check_out_time=out_time,
            reason=reason,
            request_lat=lat,
            request_lon=lon,
            status="Pending"
        )
        
        db.add(new_request)
        db.commit() # ✅ ยืนยันข้อมูลเข้า DB
    except Exception as e:
        print(f"❌ Database Error: {e}")
        return RedirectResponse(url="/attendance-report?msg=error", status_code=303)

    # 🚩 3. ส่งแจ้งเตือนหา Admin (วางไว้ตรงนี้หลัง commit)
    try:
        # ใช้สูตรหา Admin ที่ชัวร์ที่สุด
        admins = db.query(models.Employee).filter(
            (models.Employee.role.ilike("admin")) | 
            (models.Employee.employee_code == "admin")
        ).all()
        
        for admin in admins:
            send_push_to_user(
                admin.id, 
                "📢 คำขอลงเวลาย้อนหลัง", 
                f"มีคำขอจาก {user.first_name} ({user.nickname}) รอการอนุมัติ", 
                db
            )
        print(f"🔔 Manual Attendance Notification sent to {len(admins)} admins")
    except Exception as e:
        print(f"❌ Notification Error: {e}")
    
    return RedirectResponse(url="/attendance-report?msg=request_sent", status_code=303)

@app.get("/admin/attendance-requests", response_class=HTMLResponse)
async def view_attendance_requests(request: Request,user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang), db: Session = Depends(get_db)):
    # ดึงคำร้องที่ยังค้างอยู่ (Pending) มาแสดงผล
    requests = db.query(models.ManualAttendanceRequest).filter(
        models.ManualAttendanceRequest.status == "Pending"
    ).all()
    return templates.TemplateResponse("admin_requests.html", {
        "request": request,
        "texts": texts, 
        "pending_requests": requests
    })
    
@app.post("/admin/approve-request/{request_id}") # ✅ เปลี่ยนเป็น POST
async def approve_request(
    request_id: int,user: models.Employee = Depends(get_current_active_user), 
    status: str = Form(...),           # ✅ รับค่า Approved หรือ Rejected
    admin_remark: str = Form(None),    # ✅ รับเหตุผล (ไม่บังคับ)
    db: Session = Depends(get_db)
):
    req = db.query(models.ManualAttendanceRequest).filter(models.ManualAttendanceRequest.id == request_id).first()
    
    if req:
        # --- กรณี Admin กด "ปฏิเสธ" (Rejected) ---
        if status == "Rejected":
            req.status = "Rejected"
            req.admin_remark = admin_remark
            db.commit()
            
            # ส่งแจ้งเตือนบอกพนักงานว่าโดนปฏิเสธเพราะอะไร
            remark_msg = f" เหตุผล: {admin_remark}" if admin_remark else ""
            send_push_to_user(req.employee_id, "❌ คำขอลงเวลาถูกปฏิเสธ", f"คำขอวันที่ {req.request_date} ไม่ได้รับอนุมัติ{remark_msg}", db)
            return RedirectResponse(url="/admin/attendance-requests?msg=rejected", status_code=303)

        # --- กรณี Admin กด "อนุมัติ" (Approved) - (ตรรกะเดิมของนาย) ---
        emp = db.query(models.Employee).get(req.employee_id)
        sched = emp.schedule
        
        # ค้นหา/สร้าง Record การเข้างานจริง
        attendance = db.query(models.Attendance).filter(
            models.Attendance.employee_id == req.employee_id,
            func.date(models.Attendance.date) == req.request_date
        ).first()

        if not attendance:
            attendance = models.Attendance(employee_id=req.employee_id, date=req.request_date)
            db.add(attendance)

        if req.check_in_time: 
            attendance.check_in = datetime.combine(req.request_date, req.check_in_time)
        if req.check_out_time: 
            attendance.check_out = datetime.combine(req.request_date, req.check_out_time)

        is_abnormal = False
        if sched:
            # เช็คสาย (Late)
            if req.check_in_time and sched.work_start_time:
                target_in = datetime.strptime(sched.work_start_time[:5], "%H:%M").time()
                if req.check_in_time > target_in:
                    diff = datetime.combine(req.request_date, req.check_in_time) - datetime.combine(req.request_date, target_in)
                    late_mins = int(diff.total_seconds() / 60)
                    if late_mins > (sched.grace_period_late or 0):
                        attendance.late_minutes = late_mins
                        is_abnormal = True

            # เช็คออกก่อน (Early Out)
            if req.check_out_time and sched.work_end_time:
                target_out = datetime.strptime(sched.work_end_time[:5], "%H:%M").time()
                if req.check_out_time < target_out:
                    diff_out = datetime.combine(req.request_date, target_out) - datetime.combine(req.request_date, req.check_out_time)
                    early_mins = int(diff_out.total_seconds() / 60)
                    if early_mins > (sched.grace_period_early_out or 0):
                        attendance.early_minutes = early_mins
                        is_abnormal = True

        # อัปเดตสถานะและบันทึก
        attendance.status = "ผิดปกติ" if is_abnormal else "ปกติ"
        req.status = "Approved"
        req.admin_remark = admin_remark # บันทึกเหตุผล (ถ้ามี)
        db.commit()

        # 🔔 ส่งแจ้งเตือนแจ้งพนักงาน
        send_push_to_user(req.employee_id, "✅ อนุมัติการแก้ไขเวลา", f"คำขอวันที่ {req.request_date} อนุมัติเรียบร้อย", db)
        
    return RedirectResponse(url="/admin/attendance-requests?msg=updated", status_code=303)

@app.get("/admin/reject-request/{request_id}")
async def reject_request(request_id: int, db: Session = Depends(get_db)):
    req = db.query(models.ManualAttendanceRequest).filter(models.ManualAttendanceRequest.id == request_id).first()
    if req:
        req.status = "Rejected" # เปลี่ยนสถานะเฉยๆ ไม่ต้องไปยุ่งกับตาราง Attendance
        db.commit()
    return RedirectResponse(url="/admin/attendance-requests", status_code=303)

# 🚀 1. ฟังก์ชันแสดงหน้าฟอร์มยื่นคำขอสำหรับพนักงาน
@app.get("/manual-attendance-form")
async def manual_attendance_form(
    request: Request, 
    texts: dict = Depends(get_lang) # 1. เพิ่ม Dependency ตัวเดิมเข้าไป
):
    return templates.TemplateResponse("manual_attendance_form.html", {
        "request": request,
        "texts": texts # 2. ส่งก้อนคำแปลไปด้วย
    })

# 🚀 2. ฟังก์ชันดึงจำนวนคำขอที่ค้างอยู่ (สำหรับโชว์ Badge แดงๆ ใน Navbar)
@app.get("/api/manual-requests-count")
async def get_manual_count(db: Session = Depends(get_db)):
    count = db.query(models.ManualAttendanceRequest).filter(
        models.ManualAttendanceRequest.status == "Pending"
    ).count()
    return {"count": count}

@app.post("/import-attendance-upload")
async def import_attendance_upload(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        contents = await file.read()
        # รองรับทั้ง Excel และ CSV ตามที่คุณเคยเขียนไว้
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
        
        count_success = 0
        for index, row in df.iterrows():
            # 1. ดึงรหัสพนักงาน (ตำแหน่งที่ 2)
            raw_code = str(row.iloc[1]).split('.')[0].strip()
            emp = db.query(models.Employee).filter_by(employee_code=raw_code).first()
            
            if emp:
                # 2. จัดการวันที่ (ตำแหน่งที่ 1)
                target_date = pd.to_datetime(row.iloc[0]).date()
                
                # ฟังก์ชันช่วยแกะเวลา
                def parse_time_flexible(t_val):
                    if pd.isna(t_val) or str(t_val).strip() in ('-', '', 'nan'): return None
                    if hasattr(t_val, 'hour'): return t_val
                    t_str = str(t_val).strip()
                    for fmt in ("%H:%M:%S", "%H:%M"):
                        try: return datetime.strptime(t_str, fmt).time()
                        except: continue
                    return None

                # 3. ดึงเวลาเข้า-ออก (ตำแหน่งที่ 3 และ 5)
                in_time = parse_time_flexible(row.iloc[3])
                out_time = parse_time_flexible(row.iloc[5])

                # 🚀 เปลี่ยนมาบันทึกใน ManualAttendanceRequest (คำร้องขอลงเวลา)
                # เช็คก่อนว่ามีคำร้องที่ "รอดำเนินการ" ในวันเดียวกันนี้อยู่แล้วหรือไม่ เพื่อไม่ให้ข้อมูลซ้ำ
                existing_req = db.query(models.ManualAttendanceRequest).filter_by(
                    employee_id=emp.id,
                    request_date=target_date,
                    status="Pending"
                ).first()

                if not existing_req:
                    new_req = models.ManualAttendanceRequest(
                        employee_id=emp.id,
                        request_date=target_date,
                        check_in_time=in_time,
                        check_out_time=out_time,
                        reason="Imported from Excel", # ระบุที่มาเพื่อให้ HR ตรวจสอบได้
                        status="Pending"
                    )
                    db.add(new_req)
                    count_success += 1
        
        db.commit()
        # ส่งกลับไปหน้า "จัดการคำร้อง" เพื่อให้คุณกดอนุมัติทีเดียว
        return RedirectResponse(url="/admin/attendance-requests?msg=import_success", status_code=303)
        
    except Exception as e:
        print(f"🚩 Import Error: {e}")
        return {"error": f"เกิดข้อผิดพลาดในการนำเข้า: {str(e)}"}

# 🚀 เพิ่มฟังก์ชันนี้เพื่อให้ปุ่มในหน้า Report ทำงานได้
@app.get("/manual-attendance-form-admin", response_class=HTMLResponse)
async def import_attendance_page(request: Request):
    # หน้าจอนี้สำหรับ Admin เข้าไปเพื่อ Upload ไฟล์ Excel
    return templates.TemplateResponse("import_attendance.html", {"request": request})

# กุญแจ VAPID ที่คุณเจนเนอเรตไว้ (เก็บเป็นความลับ)
VAPID_PRIVATE_KEY = "2200Y9KHaV65qsAhS9gdFbmINvTymrFcFJ10ROvXI6Y"
VAPID_CLAIMS = {
    "sub": "mailto:your-email@example.com" # ใส่ Email ของคุณเพื่อระบุตัวตนกับผู้ให้บริการ Push
}

@app.post("/api/save-subscription")
async def save_subscription(request: Request, db: Session = Depends(get_db)):
    subscription_data = await request.json()
    # แนะนำให้ใช้รหัสพนักงานหรือ ID ที่แน่นอนจาก Cookie
    user_code = request.cookies.get("employee_code") or request.cookies.get("user_name")
    
    user = db.query(models.Employee).filter(models.Employee.employee_code == user_code).first()
    
    if not user:
        return {"status": "error", "message": "User not found"}

    # ค้นหาว่าเครื่องนี้/Browser นี้เคยลงทะเบียนหรือยัง
    existing = db.query(models.PushSubscription).filter(
        models.PushSubscription.endpoint == subscription_data['endpoint']
    ).first()
    
    if existing:
        # 🚩 อัปเดตข้อมูลให้เป็นปัจจุบันเสมอ เผื่อ Browser เปลี่ยน Keys
        existing.p256dh = subscription_data['keys']['p256dh']
        existing.auth = subscription_data['keys']['auth']
        existing.employee_id = user.id # เผื่อมีการเปลี่ยน User ในเครื่องเดิม
    else:
        # บันทึกอันใหม่
        new_sub = models.PushSubscription(
            employee_id=user.id,
            endpoint=subscription_data['endpoint'],
            p256dh=subscription_data['keys']['p256dh'],
            auth=subscription_data['keys']['auth']
        )
        db.add(new_sub)
    
    db.commit()
    return {"status": "success"}

def send_push_notification(employee_id: int, title: str, message: str, db: Session):
    # ดึง Subscription ทั้งหมดของพนักงานคนนี้ (เขาอาจจะมีหลายเครื่อง)
    subs = db.query(models.PushSubscription).filter(
        models.PushSubscription.employee_id == employee_id
    ).all()
    
    for sub in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth}
                },
                data=json.dumps({"title": title, "body": message}),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims=VAPID_CLAIMS
            )
        except WebPushException as ex:
            print(f"Push failed: {ex}")
            # ถ้า Token หมดอายุ (410 Gone) ให้ลบออกจาก DB
            if ex.response and ex.response.status_code == 410:
                db.delete(sub)
                db.commit()

# @app.post("/admin/send-broadcast")
# async def send_broadcast(title: str = Form(...), message: str = Form(...), db: Session = Depends(get_db)):
#     # 💡 ปรับปรุง: ดึงเฉพาะพนักงานที่มี Subscription เท่านั้น (Join Table)
#     subscriptions = db.query(models.PushSubscription).all()
    
#     for sub in subscriptions:
#         # ดึงข้อมูลการส่งแจ้งเตือนรายเครื่อง
#         send_push_notification(sub.employee_id, title, message, db)
        
#     return {"status": "success", "detail": f"ส่งประกาศหาพนักงานทั้งหมด {len(subscriptions)} รายการเรียบร้อยแล้ว"}

@app.get("/admin/broadcast", response_class=HTMLResponse)
async def broadcast_page(request: Request,user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang)):
    return templates.TemplateResponse("admin_broadcast.html", {"texts": texts,"request": request})

@app.post("/admin/send-broadcast")
async def send_broadcast(
    title: str = Form(...), 
    message: str = Form(...), 
    db: Session = Depends(get_db)
):
    # 1. วนลูปส่งประกาศหาพนักงานตามปกติ
    all_employees = db.query(models.Employee).all()
    for emp in all_employees:
        send_push_notification(emp.id, title, message, db)
        
    # 2. แก้ไขส่วนสุดท้าย: แทนที่ "return {"status": "success", ...}" ด้วยบรรทัดนี้ครับ:
    # ระบบจะพาส่งกลับไปที่หน้า Dashboard ทันทีหลังจากส่งครบทุกคน
    return RedirectResponse(url="/dashboard", status_code=303)

# หาตำแหน่งโฟลเดอร์ app
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@app.get("/service-worker.js")
async def get_service_worker():
    # แก้ Path ให้ชี้ไปที่ app/static/sw.js ตามภาพ
    sw_path = os.path.join(BASE_DIR, "static", "sw.js")
    
    if not os.path.exists(sw_path):
        return {"error": f"ไม่พบไฟล์ที่: {sw_path}"}
        
    return FileResponse(sw_path, media_type="application/javascript")

@app.get("/manifest.json")
async def get_manifest():
    # ชี้ไปที่ Path จริงของ manifest.json
    return FileResponse("app/static/manifest.json", media_type="application/json")

def send_push_notification(employee_id: int, title: str, message: str, db: Session):
    subs = db.query(models.PushSubscription).filter(
        models.PushSubscription.employee_id == employee_id
    ).all()
    
    for sub in subs:
        try:
            # ดึงเฉพาะส่วน Domain จาก endpoint (เช่น https://fcm.googleapis.com)
            parsed_url = urlparse(sub.endpoint)
            audience = f"{parsed_url.scheme}://{parsed_url.netloc}"
            
            # เพิ่ม audience เข้าไปใน VAPID Claims
            claims = VAPID_CLAIMS.copy()
            claims["aud"] = audience # <--- จุดที่ต้องเพิ่มครับ

            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth}
                },
                data=json.dumps({"title": title, "body": message}),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims=claims # ใช้ claims ที่ใส่ aud แล้ว
            )
        except WebPushException as ex:
            print(f"Push failed: {ex}")
            if ex.response and ex.response.status_code == 410:
                db.delete(sub)
                db.commit()

def calculate_ot_pay(emp_id: int, month: int, year: int, db: Session):
    # 1. ดึงฐานเงินเดือนพนักงานมาคำนวณ Rate ต่อชั่วโมง
    user = db.query(models.Employee).filter(models.Employee.id == emp_id).first()
    if not user or not user.base_salary:
        return 0.0
    
    # สูตร: (เงินเดือน / 30 / 8) * 1.5 (หรือตามนโยบายคลินิกคุณ)
    hourly_rate = (user.base_salary / 30 / 8) * 1.5
    
    # 2. รวมชั่วโมง OT ที่ได้รับการอนุมัติแล้วในเดือนนั้น
    total_hours = db.query(func.sum(models.OTRequest.hours)).filter(
        models.OTRequest.employee_id == emp_id,
        models.OTRequest.status == "approved",
        extract('month', models.OTRequest.date) == month,
        extract('year', models.OTRequest.date) == year
    ).scalar() or 0.0
    
    return total_hours * hourly_rate

def count_absent_days(emp_id: int, month: int, year: int, db: Session):
    # 1. หาวันที่ทั้งหมดในเดือนและปีที่ระบุ
    import calendar
    _, num_days = calendar.monthrange(year, month)
    
    # 2. ดึงวันที่ที่มีการลงเวลา (Check-in) ของพนักงานคนนี้
    recorded_days = db.query(extract('day', models.Attendance.date)).filter(
        models.Attendance.employee_id == emp_id,
        extract('month', models.Attendance.date) == month,
        extract('year', models.Attendance.date) == year
    ).all()
    
    # แปลงผลลัพธ์เป็น List ของตัวเลขวันที่
    recorded_days_list = [d[0] for d in recorded_days]
    
    # 3. คำนวณวันขาด (เบื้องต้น: วันทั้งหมด - วันที่มี Log)
    # หมายเหตุ: ในอนาคตคุณสามารถหักลบวันเสาร์-อาทิตย์ หรือวันหยุดนักขัตฤกษ์ออกได้ครับ
    absent_count = 0
    for day in range(1, num_days + 1):
        if day not in recorded_days_list:
            absent_count += 1
            
    return absent_count

def calculate_absence_deduction(emp_id: int, month: int, year: int, db: Session):
    # ดึงฐานเงินเดือนมาหา Rate ต่อวัน (เงินเดือน / 30)
    user = db.query(models.Employee).filter(models.Employee.id == emp_id).first()
    if not user or not user.base_salary:
        return 0.0
    
    daily_rate = user.base_salary / 30
    
    # นับจำนวนวันที่พนักงาน "ขาดงาน" (ไม่มี Log ในตาราง Attendance)
    # หมายเหตุ: ควรหักเฉพาะวันทำงานปกติ ไม่นับวันหยุด
    absent_count = count_absent_days(emp_id, month, year, db) 
    
    return absent_count * daily_rate

def get_salary_and_approved_ot(emp_id: int, month: int, year: int, db: Session):
    # 1. ดึงข้อมูลพนักงานเพื่อเอาเงินเดือนและค่าตำแหน่ง
    user = db.query(models.Employee).filter(models.Employee.id == emp_id).first()
    base_salary = user.base_salary if user and hasattr(user, 'base_salary') else 0.0
    pos_allowance = user.position_allowance if user and hasattr(user, 'position_allowance') else 0.0

    # 2. รวมยอด OT จากคำขอที่ได้รับอนุมัติแล้ว (Approved) ในเดือน/ปี นั้นๆ
    total_ot_pay = calculate_ot_pay(emp_id, month, year, db) 

    # 3. ส่งค่ากลับเป็น Object เพื่อให้นำไปใช้งานต่อได้ง่าย
    class SalaryInfo:
        base = base_salary
        allowance = pos_allowance
        ot = total_ot_pay
        total_income = base_salary + pos_allowance + total_ot_pay

    return SalaryInfo()

@app.get("/admin/calculate-payroll")
async def calculate_payroll_page(
    request: Request,user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang),
    start_date: str = None,
    end_date: str = None,
    db: Session = Depends(get_db)
):
    # 1. จัดการวันที่ Default
    if not start_date or not end_date:
        today = datetime.now()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        last_day = calendar.monthrange(today.year, today.month)[1]
        end_date = today.replace(day=last_day).strftime('%Y-%m-%d')

    s_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
    e_dt = datetime.strptime(end_date, '%Y-%m-%d').date()

    # 2. ดึงการตั้งค่า และ พนักงาน
    settings = get_payroll_settings(db)
    default_set = {"days": 30, "hours": 8}
    employees = db.query(models.Employee).all()

    # ดึงรายชื่อวันหยุดนักขัตฤกษ์
    holidays = db.query(models.Holiday).filter(
        models.Holiday.holiday_date >= s_dt,
        models.Holiday.holiday_date <= e_dt
    ).all()
    holiday_dates = {h.holiday_date: h.holiday_name for h in holidays}

    for emp in employees:
        absent_count = 0
        total_late_mins = 0
        total_early_mins = 0
        curr = s_dt
        
        # --- 🚩 3. วนลูปเช็คสถิติการมาทำงาน ---
        while curr <= e_dt:
            day_name = curr.strftime('%a')
            is_holiday = curr in holiday_dates
            is_weekly_off = emp.weekly_off and day_name not in emp.weekly_off
            
            att = db.query(models.Attendance).filter(
                models.Attendance.employee_id == emp.id,
                func.date(models.Attendance.date) == curr
            ).first()
            
            leave = db.query(models.LeaveRequest).filter(
                models.LeaveRequest.employee_id == emp.id,
                models.LeaveRequest.status == "Approved",
                models.LeaveRequest.start_date <= curr,
                models.LeaveRequest.end_date >= curr
            ).first()

            if not (is_holiday or is_weekly_off or leave):
                if att:
                    total_late_mins += (att.late_minutes or 0)
                    total_early_mins += (att.early_minutes or 0)
                else:
                    absent_count += 1
            curr += timedelta(days=1)

        emp.absent_days = absent_count
        emp.late_minutes = total_late_mins
        emp.early_minutes = total_early_mins

        # --- 🚩 4. คำนวณยอดเงินตามสถิติ ---
        base_calc = (emp.base_salary or 0) + (emp.position_allowance or 0)
        
        # หักสาย/ออกก่อน
        late_conf = settings.get('late')
        l_days = late_conf.divider_days if late_conf else default_set["days"]
        l_hours = late_conf.divider_hours if late_conf else default_set["hours"]
        rate_min = base_calc / l_days / l_hours / 60 if l_days * l_hours > 0 else 0

        emp.calculated_late_deduction = round(rate_min * emp.late_minutes, 2)
        emp.calculated_early_deduction = round(rate_min * emp.early_minutes, 2)

        # หักขาดงาน
        abs_conf = settings.get('absent')
        a_days = abs_conf.divider_days if abs_conf else default_set["days"]
        rate_day = base_calc / a_days if a_days > 0 else 0
        emp.calculated_absent_deduction = round(rate_day * emp.absent_days, 2)

        # คำนวณ OT
        ot_data = db.query(
            models.OTRequest.ot_type,
            func.sum(models.OTRequest.total_minutes).label("mins")
        ).filter(
            models.OTRequest.employee_id == emp.id,
            models.OTRequest.status == "approved",
            models.OTRequest.request_date >= s_dt,
            models.OTRequest.request_date <= e_dt
        ).group_by(models.OTRequest.ot_type).all()

        total_ot_pay = 0
        for ot in ot_data:
            conf = settings.get(ot.ot_type)
            o_mult = conf.multiplier if conf else (1.0 if "1_0" in ot.ot_type else 1.5)
            ot_rate_min = base_calc / (conf.divider_days if conf else 30) / (conf.divider_hours if conf else 8) / 60
            total_ot_pay += (ot_rate_min * ot.mins * o_mult)
        emp.approved_ot_pay = round(total_ot_pay, 2)

        # --- 🚩 5. ส่วนที่เพิ่มใหม่: ดึงข้อมูลที่เคยบันทึกร่างไว้ (Draft Data) ---
        # ค้นหาข้อมูลในตาราง PayrollDetail ของเดือนที่เลือก
        payroll_draft = db.query(models.PayrollDetail).filter(
            models.PayrollDetail.employee_id == emp.id,
            models.PayrollDetail.month == e_dt.month,
            models.PayrollDetail.year == e_dt.year
        ).first()

        # ถ้ามีข้อมูลร่าง ให้ส่งค่าเหล่านั้นไปที่หน้าจอ ถ้าไม่มีให้เป็น 0
        emp.draft_extra_income = payroll_draft.extra_income if payroll_draft else 0
        emp.draft_extra_deduction = payroll_draft.extra_deduction if payroll_draft else 0
        # พ่วงค่า SSO และ Tax เผื่อกรณีมีการแก้ไขมือด้วย
        emp.draft_sso = payroll_draft.sso if payroll_draft else None
        emp.draft_tax = payroll_draft.tax if payroll_draft else 0

    return templates.TemplateResponse("admin_payroll.html", {
        "request": request,
        "employees": employees,
        "start_date": start_date,
        "texts": texts,
        "end_date": end_date
    })
    
def get_payroll_settings(db: Session):
    """ดึงค่าการตั้งค่าทั้งหมดมาเป็น Dictionary เพื่อใช้งานง่าย"""
    settings = db.query(models.PayrollSetting).all()
    return {s.type_name: s for s in settings}

@app.post("/admin/calculate-payroll")
async def process_payroll(
    emp_id: int = Form(...), # รับค่าจากฟอร์มในหน้าคำนวณ
    month: int = Form(...),
    year: int = Form(...),
    sso_custom: float = Form(None), 
    tax_custom: float = Form(None), 
    db: Session = Depends(get_db)
):
    # 1. ดึงข้อมูลพนักงานเพื่อเอาฐานเงินเดือนที่ตั้งไว้ในหน้าจัดการพนักงาน
    user = db.query(models.Employee).filter(models.Employee.id == emp_id).first()
    if not user:
        return {"error": "Employee not found"}

    # ดึงค่าฐานเงินเดือนและค่าตำแหน่งอัตโนมัติ
    salary = user.base_salary if hasattr(user, 'base_salary') else 0.0
    position_allowance = user.position_allowance if hasattr(user, 'position_allowance') else 0.0
    
    # 2. ดึงค่า OT จากคำขอที่ได้รับการอนุมัติแล้ว
    ot = calculate_ot_pay(emp_id, month, year, db) 
    
    # 3. คำนวณรายได้รวม
    total_earnings = salary + position_allowance + ot

    # 4. จัดการค่า SSO และ Tax ตามที่คุณต้องการให้กรอกทับได้
    final_sso = sso_custom if sso_custom is not None else min(salary * 0.05, 750)
    final_tax = tax_custom if tax_custom is not None else 0.0
    
    # หักเงินขาดงานอัตโนมัติจากหน้าลงเวลา
    other_deductions = calculate_absence_deduction(emp_id, month, year, db)

    # 5. คำนวณยอดสุทธิ
    net_salary = total_earnings - (final_sso + final_tax + other_deductions)

    # 6. บันทึกลงฐานข้อมูล PayrollDetail เพื่อออกสลิปและรายงานสรุป
    new_payroll = models.PayrollDetail(
        employee_id=emp_id,
        month=month,
        year=year,
        salary=salary,
        position_allowance=position_allowance,
        ot_pay=ot,
        sso=final_sso,
        tax=final_tax,
        absence_deduction=other_deductions,
        net_total=net_salary
    )
    
    db.add(new_payroll)
    db.commit() # บันทึกข้อมูลถาวร

    # 7. Redirect กลับไปหน้ารายงานสรุปเพื่อดูผลลัพธ์
    return RedirectResponse(url=f"/admin/payroll-summary?month={month}&year={year}", status_code=303)

@app.post("/admin/save-payroll-settings")
async def save_payroll_settings(
    request: Request,
    late_days: int = Form(...),
    late_hours: int = Form(...),
    absent_days: int = Form(...),
    ot_1_5_days: int = Form(...),
    ot_1_5_hours: int = Form(...),
    ot_1_5_mult: float = Form(...),
    ot_1_mult: float = Form(1.0), 
    ot_2_mult: float = Form(2.0),
    ot_3_mult: float = Form(3.0),
    db: Session = Depends(get_db)
):
    # ตรวจสอบสิทธิ์ Admin ก่อนบันทึก
    if request.cookies.get("user_role") != "Admin":
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์")

    # อัปเดตหรือสร้างค่าใหม่ (Upsert Logic)
    settings_to_update = [
        {"type_name": "late", "label": "หักมาสาย", "divider_days": late_days, "divider_hours": late_hours, "multiplier": 1.0},
        {"type_name": "absent", "divider_days": absent_days, "divider_hours": 0, "multiplier": 1.0},
        {"type_name": "ot_1_5", "divider_days": ot_1_5_days, "divider_hours": ot_1_5_hours, "multiplier": 1.5},
        {"type_name": "ot_1_0", "divider_days": ot_1_5_days, "divider_hours": ot_1_5_hours, "multiplier": ot_1_mult},
        {"type_name": "ot_2_0", "divider_days": ot_1_5_days, "divider_hours": ot_1_5_hours, "multiplier": ot_2_mult},
        {"type_name": "ot_3_0", "divider_days": ot_1_5_days, "divider_hours": ot_1_5_hours, "multiplier": ot_3_mult},
    ]

    for item in settings_to_update:
        setting = db.query(models.PayrollSetting).filter_by(type_name=item["type_name"]).first()
        if setting:
            setting.divider_days = item["divider_days"]
            setting.divider_hours = item["divider_hours"]
            setting.multiplier = item["multiplier"]
        else:
            new_set = models.PayrollSetting(**item)
            db.add(new_set)
    
    db.commit()
    return RedirectResponse(url="/admin/payroll-settings?msg=success", status_code=303)

@app.post("/admin/process-payroll")
async def process_payroll(
    request: Request,
    action: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    db: Session = Depends(get_db)
):
    form_data = await request.form()
    # ดึงพนักงานทุกคนมาวนลูปบันทึกตาม ID ที่ส่งมาจากหน้าจอ
    employees = db.query(models.Employee).all()
    dt_end = datetime.strptime(end_date, '%Y-%m-%d')

    for emp in employees:
        # ฟังก์ชันช่วยดึงค่าเพื่อป้องกัน Error จากค่าว่างหรือตัวอักษรแปลกปลอม
        def parse_to_float(field_name):
            val = form_data.get(field_name, "0")
            # ลบคอมม่าออกและจัดการช่องว่าง
            if val and str(val).strip() != "":
                return float(str(val).replace(',', ''))
            return 0.0
        
        # 🚩 ดึงค่าเงินเพิ่ม/ลดพิเศษ (ใช้ emp.id ให้ตรงกับ HTML)
        e_income = parse_to_float(f"extra_income_{emp.id}")
        e_deduction = parse_to_float(f"extra_deduction_{emp.id}")
        
        # ดึงค่าคำนวณอื่นๆ
        sso_val = parse_to_float(f"sso_{emp.id}")
        tax_val = parse_to_float(f"tax_{emp.id}")
        ot_pay_val = parse_to_float(f"ot_{emp.id}")
        net_val = parse_to_float(f"net_{emp.id}")
        
        # รายการหัก
        absent_deduct = parse_to_float(f"absent_deduct_{emp.id}")
        late_deduct = parse_to_float(f"late_deduct_{emp.id}")
        early_deduct = parse_to_float(f"early_deduct_{emp.id}")

        # 🛡️ 1. ลบข้อมูลเก่าของเดือน/ปีนี้ออกก่อน (ไม่ว่าจะ Draft หรือ Finalize)
        # เพื่อป้องกันปัญหา "พนักงานเกิน" ในหน้ารายงานสรุป
        db.query(models.PayrollDetail).filter(
            models.PayrollDetail.employee_id == emp.id,
            models.PayrollDetail.month == dt_end.month,
            models.PayrollDetail.year == dt_end.year
        ).delete()

        # 🛡️ 2. สร้าง Record ใหม่บันทึกลงฐานข้อมูล (ค่า extra_income/extra_deduction จะถูกเซฟที่นี่)
        new_record = models.PayrollDetail(
            employee_id=emp.id,
            month=dt_end.month,
            year=dt_end.year,
            salary=emp.base_salary,
            position_allowance=emp.position_allowance,
            ot_pay=ot_pay_val,
            sso=sso_val,
            tax=tax_val,
            absence_deduction=absent_deduct,
            # late_deduction=late_deduct,   # เปิดใช้ถ้าใน Model มี Column นี้
            # early_deduction=early_deduct, # เปิดใช้ถ้าใน Model มี Column นี้
            extra_income=e_income,
            extra_deduction=e_deduction,
            net_total=net_val,
        )
        db.add(new_record)
            
    db.commit()

    # 🚩 3. จัดการการเปลี่ยนหน้าหลังกดปุ่ม
    if action == "save_draft":
        # ถ้าบันทึกร่าง ให้กลับไปหน้าคำนวณเหมือนเดิม พร้อมส่งค่าวันที่กลับไปด้วย
        return RedirectResponse(
            url=f"/admin/calculate-payroll?start_date={start_date}&end_date={end_date}&msg=draft_saved", 
            status_code=303
        )
    
    # ถ้าประมวลผลเสร็จสิ้น ให้ไปหน้าสรุปรายงาน (Payroll Summary)
    return RedirectResponse(
        url=f"/admin/payroll-summary?month={dt_end.month}&year={dt_end.year}&msg=finalize", 
        status_code=303
    )

@app.post("/admin/save-payroll")
async def save_payroll(
    emp_id: int,
    month: int,
    year: int,
    sso_amount: float = Form(...), # รับค่าประกันสังคมที่คุณกรอก
    tax_amount: float = Form(...), # รับค่าภาษีที่คุณกรอก
    db: Session = Depends(get_db)
):
    # ดึงรายได้ที่คำนวณไว้แล้ว (Salary + OT)
    salary_info = get_salary_and_approved_ot(emp_id, month, year, db) 
    
    # บันทึกลงตาราง PayrollDetail เพื่อเป็นประวัติ
    new_payroll = models.PayrollDetail(
        employee_id=emp_id,
        month=month,
        year=year,
        salary=salary_info.base,
        ot_pay=salary_info.ot,
        sso=sso_amount, # ใช้ยอดที่คุณ Override มา
        tax=tax_amount, # ใช้ยอดที่คุณ Override มา
        net_total= (salary_info.total_income - sso_amount - tax_amount)
    )
    db.add(new_payroll)
    db.commit()
    
    return {"status": "success", "message": "บันทึกข้อมูลเงินเดือนเรียบร้อย"}

# ตัวอย่างการเรียกใช้แจ้งเตือนหลังบันทึก Payroll
@app.post("/admin/confirm-payroll")
async def confirm_payroll(emp_id: int, month: int, db: Session = Depends(get_db)):
    # ... โค้ดบันทึกข้อมูล ...
    
    # ส่งแจ้งเตือนหาพนักงานรายบุคคล
    title = "สลิปเงินเดือนพร้อมแล้ว"
    message = f"สลิปเงินเดือนประจำเดือน {month} พร้อมให้ตรวจสอบแล้วในแอป"
    send_push_notification(emp_id, title, message, db)
    
    return {"status": "success"}

@app.get("/admin/payroll-summary", response_class=HTMLResponse)
async def payroll_summary(
    request: Request,user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang), 
    month: int = None, 
    year: int = None, 
    db: Session = Depends(get_db)
):
    # 1. กำหนดค่าเริ่มต้น (ถ้าไม่เลือก ให้เอาเดือนปัจจุบัน)
    now = datetime.now()
    if month is None: month = now.month
    if year is None: year = now.year

    # 2. ดึงข้อมูลพนักงานตามเดือน/ปี ที่เลือก
    raw_data = db.query(models.PayrollDetail).options(
        joinedload(models.PayrollDetail.employee)
    ).filter(
        models.PayrollDetail.month == month,
        models.PayrollDetail.year == year
    ).all()

    # 3. ป้องกัน "พนักงานเกิน" (ใช้ Dictionary กรอง ID ซ้ำ)
    unique_payroll = {}
    for p in raw_data:
        unique_payroll[p.employee_id] = p
    
    payroll_data = list(unique_payroll.values())

    # 4. คำนวณยอดรวม (Grand Total) รวมเงินเพิ่ม/ลดพิเศษด้วย
    summary = {
        "total_salary": sum((p.salary or 0) + (p.position_allowance or 0) for p in payroll_data),
        "total_ot": sum(p.ot_pay or 0 for p in payroll_data),
        "total_extra_income": sum(p.extra_income or 0 for p in payroll_data), # เพิ่มใหม่
        "total_sso": sum(p.sso or 0 for p in payroll_data),
        "total_tax": sum(p.tax or 0 for p in payroll_data),
        "total_extra_deduction": sum(p.extra_deduction or 0 for p in payroll_data), # เพิ่มใหม่
        "total_net": sum(p.net_total or 0 for p in payroll_data),
        "count": len(payroll_data)
    }

    # 5. ส่งค่ากลับไปที่ Template พร้อมข้อมูลสำหรับตัวเลือก Filter
    return templates.TemplateResponse("admin_payroll_summary.html", {
        "request": request,
        "payroll_data": payroll_data,
        "summary": summary,
        "current_month": month,
        "current_year": year,
        "months_range": range(1, 13),
        "texts": texts,
        "years_range": range(now.year - 1, now.year + 2) # เลือกย้อนหลังได้ 1 ปี
    })

@app.get("/admin/payroll-settings")
async def payroll_settings_page(request: Request,user: models.Employee = Depends(get_current_active_user), db: Session = Depends(get_db),texts: dict = Depends(get_lang)):
    # ตรวจสอบสิทธิ์ Admin
    if request.cookies.get("user_role") != "Admin":
        return RedirectResponse(url="/dashboard", status_code=303)

    # ดึงค่าปัจจุบันจาก DB ไปโชว์ในฟอร์ม (ถ้ามี)
    late_set = db.query(models.PayrollSetting).filter_by(type_name='late').first()
    ot_set = db.query(models.PayrollSetting).filter_by(type_name='ot_1_5').first()

    return templates.TemplateResponse("payroll_settings.html", {
        "request": request,
        "late_set": late_set,
        "texts": texts,
        "ot_set": ot_set
    })

# --- 1. หน้าเปิดฟอร์มยื่น OT (GET) ---
@app.get("/request-ot")
async def request_ot_page(
    request: Request, 
    texts: dict = Depends(get_lang)  # <--- เพิ่มอันนี้
):
    return templates.TemplateResponse("request_ot.html", {
        "request": request,
        "texts": texts  # <--- ส่งก้อนนี้ไปด้วย
    })

# --- 2. ฟังก์ชันรับข้อมูลยื่น OT (POST) - รวมแจ้งเตือนและคำนวณเวลา ---
@app.post("/request-ot")
async def handle_request_ot(
    request: Request,user: models.Employee = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # 1. ดึงข้อมูลจาก Form แบบแมนนวลเพื่อกัน Error 422
    form_data = await request.form()
    
    ot_date = form_data.get("request_date")
    start_time = form_data.get("start_time")
    end_time = form_data.get("end_time")
    ot_type = form_data.get("ot_type", "ot_1_5") # ถ้าไม่มีให้เป็นค่าเริ่มต้น
    reason = form_data.get("reason", "") # ถ้าไม่ใส่เหตุผล ให้เป็นค่าว่าง ไม่พังแน่นอน
    
    # เช็คข้อมูลที่จำเป็น (วันที่และเวลา)
    if not all([ot_date, start_time, end_time]):
        return RedirectResponse(url="/request-ot?msg=missing_fields", status_code=303)

    # ตรวจสอบ ID พนักงานจาก Cookie
    user_id_raw = request.cookies.get("id") or request.cookies.get("user_id")
    if not user_id_raw:
        return RedirectResponse(url="/login", status_code=303)
    
    user_id = int(user_id_raw)
    user = db.query(models.Employee).filter(models.Employee.id == user_id).first()

    # 2. คำนวณเวลาและบันทึก
    fmt = '%H:%M'
    try:
        t1 = datetime.strptime(start_time, fmt)
        t2 = datetime.strptime(end_time, fmt)
        tdelta = t2 - t1
        total_minutes = int(tdelta.total_seconds() / 60)
        
        if total_minutes <= 0:
            return RedirectResponse(url="/request-ot?msg=invalid_time", status_code=303)

        new_ot = models.OTRequest(
            employee_id=user_id,
            request_date=datetime.strptime(ot_date, '%Y-%m-%d').date(),
            start_time=t1.time(),
            end_time=t2.time(),
            total_minutes=total_minutes,
            ot_type=ot_type,
            reason=reason if reason else "-", # ใส่ขีดไว้ถ้าว่าง
            status="pending"
        )
        
        db.add(new_ot)
        db.commit()

        # 🚩 3. ส่งแจ้งเตือนหา Admin
        try:
            admins = db.query(models.Employee).filter(
                (models.Employee.role.ilike("admin")) | 
                (models.Employee.employee_code == "admin")
            ).all()
            for admin in admins:
                send_push_to_user(admin.id, "📢 มีคำขอ OT ใหม่", f"พนักงาน {user.first_name if user else user_id} ยื่นขอ OT", db)
        except Exception as e:
            print(f"❌ Notification Error: {e}")

        return RedirectResponse(url="/my-ot-requests?msg=success", status_code=303)

    except Exception as e:
        db.rollback()
        print(f"🚩 Error: {e}")
        return RedirectResponse(url="/request-ot?msg=error", status_code=303)

@app.get("/admin/approve-ot")
async def approve_ot_page(request: Request,user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang), db: Session = Depends(get_db)):
    # 1. สั่งให้โปรแกรมไป "ค้นหา" ในตาราง OTRequest
    # โดยเลือกเฉพาะรายการที่สถานะเป็น "pending" (รออนุมัติ)
    data = db.query(models.OTRequest).filter(models.OTRequest.status == "pending").all()
    
    # 2. ส่งข้อมูลที่ค้นหาได้ (ตัวแปร data) ไปที่หน้า HTML
    # โดยตั้งชื่อในหน้า HTML ว่า "pending_ot"
    return templates.TemplateResponse("admin_approve_ot.html", {
        "request": request,
        "texts": texts, 
        "pending_ot": data  # 🚩 ข้อมูลจะถูกส่งไปชื่อนี้เพื่อให้ HTML วนลูปแสดงผล
    })

@app.post("/admin/process-ot/{ot_id}")
async def process_ot(
    ot_id: int, 
    action: str = Form(...), 
    admin_remark: str = Form(None), # ✅ 1. เพิ่มให้รับค่าเหตุผล (None = ไม่บังคับ)
    db: Session = Depends(get_db)
):
    ot_req = db.query(models.OTRequest).filter(models.OTRequest.id == ot_id).first()
    
    if ot_req:
        if action == "approve":
            ot_req.status = "approved"
            msg_text = "ได้รับการอนุมัติแล้ว"
            icon = "✅"
        else:
            ot_req.status = "rejected"
            # ✅ 2. ถ้ามีการใส่เหตุผล ให้พ่วงไปในข้อความแจ้งเตือนด้วย
            remark_suffix = f" เนื่องจาก: {admin_remark}" if admin_remark else ""
            msg_text = f"ไม่ได้รับการอนุมัติ{remark_suffix}"
            icon = "❌"
            
        # ✅ 3. บันทึกเหตุผลลงในฐานข้อมูล
        ot_req.admin_remark = admin_remark
        db.commit() 
        
        # 🚩 ส่งแจ้งเตือนหาพนักงาน
        try:
            send_push_to_user(
                ot_req.employee_id, 
                f"{icon} ผลการอนุมัติ OT", 
                f"คำขอ OT ของคุณ{msg_text}", 
                db
            )
        except Exception as e:
            print(f"Push Notification Error: {e}")
            
    return RedirectResponse(url="/admin/approve-ot?msg=updated", status_code=303)

@app.get("/my-ot-requests")
async def my_ot_requests_page(request: Request,user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang), db: Session = Depends(get_db)):
    # 1. ตรวจสอบชื่อคุกกี้ (ถ้าหน้าอื่นเข้าได้ ให้ใช้ชื่อตามหน้านั้น เช่น "id")
    user_id_raw = request.cookies.get("user_id") or request.cookies.get("id")
    
    if not user_id_raw:
        return RedirectResponse(url="/login", status_code=303)
    
    try:
        # 2. แปลงเป็น Integer เพื่อให้ตรงกับประเภทข้อมูลใน Database
        user_id = int(user_id_raw)
        
        # 3. ดึงข้อมูลโดยใช้ IDที่เป็น Integer
        my_ots = db.query(models.OTRequest).filter(
            models.OTRequest.employee_id == user_id
        ).order_by(models.OTRequest.request_date.desc()).all()
        
        return templates.TemplateResponse("my_ot_requests.html", {
            "request": request,
            "ots": my_ots,
            "texts": texts
        })
    except ValueError:
        # กรณีคุกกี้ไม่ใช่ตัวเลข ให้ส่งไป Login ใหม่
        return RedirectResponse(url="/login", status_code=303)
    
@app.get("/admin/ot-summary-report")
async def ot_summary_report(request: Request,user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang), db: Session = Depends(get_db)):
    if request.cookies.get("user_role") != "Admin":
        return RedirectResponse(url="/dashboard", status_code=303)

    # ดึง OT ที่อนุมัติแล้วทั้งหมดมาสรุปยอด
    all_approved_ots = db.query(models.OTRequest).filter(
        models.OTRequest.status == "approved"
    ).all()
    
    # คำนวณยอดรวมนาทีแยกตามประเภทเพื่อทำ Dashboard เล็กๆ
    summary = {
        "ot_1_0": sum(ot.total_minutes for ot in all_approved_ots if ot.ot_type == "ot_1_0"),
        "ot_1_5": sum(ot.total_minutes for ot in all_approved_ots if ot.ot_type == "ot_1_5"),
        "ot_2_0": sum(ot.total_minutes for ot in all_approved_ots if ot.ot_type == "ot_2_0"),
        "ot_3_0": sum(ot.total_minutes for ot in all_approved_ots if ot.ot_type == "ot_3_0"),
    }

    return templates.TemplateResponse("admin_ot_report.html", {
        "request": request,
        "ots": all_approved_ots,
        "texts": texts,
        "summary": summary
    })

@app.get("/admin/download-attendance-template")
async def download_attendance_template():
    # สร้างโครงสร้างคอลัมน์ให้ตรงกับที่ระบบ Index (0, 1, 2, 3, 4, 5) คาดหวัง
    data = {
        'วันที่ (YYYY-MM-DD)': ['2026-02-01'],
        'รหัสพนักงาน': ['20220201'],
        'ชื่อ-นามสกุล (ไม่บังคับ)': ['สมชาย สายเสมอ'],
        'เวลาเข้า (HH:mm)': ['08:00'],
        'สาย (นาที) - ระบบคำนวณเอง': [''],
        'เวลาออก (HH:mm)': ['17:00'],
        'สถานะ (ไม่บังคับ)': ['']
    }
    
    df = pd.DataFrame(data)
    
    # สร้างไฟล์ Excel ใน Memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Template')
        
    output.seek(0)
    
    headers = {
        'Content-Disposition': 'attachment; filename="attendance_template.xlsx"'
    }
    return StreamingResponse(output, headers=headers, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.get("/admin/approve-all-requests")
async def approve_all_requests(db: Session = Depends(get_db)):
    # 1. ดึงรายการที่ยังเป็น Pending ทั้งหมดออกมา
    pending_list = db.query(models.ManualAttendanceRequest).filter(
        models.ManualAttendanceRequest.status == "Pending"
    ).all()
    
    if not pending_list:
        return RedirectResponse(url="/admin/attendance-requests?msg=no_pending", status_code=303)

    # 2. วนลูปอนุมัติทีละรายการโดยใช้ Logic การอนุมัติหลัก
    for req in pending_list:
        try:
            # เรียกใช้ฟังก์ชันอนุมัติที่คุณมีอยู่แล้วเพื่อให้คำนวณสาย/ออกก่อนให้ด้วย
            # หมายเหตุ: ถ้า approve_request ของคุณเป็น async อย่าลืมใส่ await
            await approve_request(req.id, db) 
        except Exception as e:
            print(f"🚩 Error approving request {req.id}: {e}")
            continue
            
    return RedirectResponse(url="/admin/attendance-requests?msg=all_approved_success", status_code=303)

# --- A. พิมพ์สลิปเงินเดือน (รายคน) ---
@app.get("/admin/payslip/{payroll_id}", response_class=HTMLResponse)
async def view_payslip(request: Request, payroll_id: int,user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang), db: Session = Depends(get_db)):
    payroll = db.query(models.PayrollDetail).filter(models.PayrollDetail.id == payroll_id).first()
    
    # 🚩 ดึงข้อมูลบริษัทล่าสุดออกมา
    company = db.query(models.CompanySetting).first()
    
    if not payroll:
        return "ไม่พบข้อมูลสลิปเงินเดือน"
    
    return templates.TemplateResponse("payslip_print.html", {
        "request": request, # บรรทัดนี้จะไม่ Error แล้ว
        "p": payroll,
        "texts": texts,
        "company": company # ส่งค่าไปที่ Template
    })

# --- B & C. สรุปยอด SSO และ ภาษี (รายเดือน) ---
@app.get("/admin/payroll-tax-sso-report")
async def payroll_tax_sso_report(
    request: Request,user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang), 
    month: int = None, # 🚩 เปลี่ยนจากบังคับรับค่า เป็น None เพื่อให้เข้าหน้าแรกได้
    year: int = None,  # 🚩 เปลี่ยนเป็น None
    db: Session = Depends(get_db)
):
    # กำหนดค่าปัจจุบันหากไม่ได้เลือกเดือน/ปีมา
    now = datetime.now()
    if not month: month = now.month
    if not year: year = now.year

    data = db.query(models.PayrollDetail).filter(
        models.PayrollDetail.month == month,
        models.PayrollDetail.year == year
    ).all()
    
    total_sso = sum(p.sso or 0 for p in data)
    total_tax = sum(p.tax or 0 for p in data)
    
    return templates.TemplateResponse("sso_tax_report.html", {
        "request": request,
        "data": data,
        "total_sso": total_sso,
        "total_tax": total_tax,
        "current_month": month,
        "current_year": year,
        "months_range": range(1, 13),
        "texts": texts,
        "years_range": range(now.year - 1, now.year + 2)
    })
    
@app.post("/admin/settings/company/update")
async def update_company_settings(
    company_name: str = Form(...),
    address: str = Form(...),
    logo: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    company = db.query(models.CompanySetting).first()
    if not company:
        company = models.CompanySetting()
        db.add(company)

    company.company_name = company_name
    company.address = address

    if logo and logo.filename:
        file_extension = os.path.splitext(logo.filename)[1]
        new_filename = f"company_logo{file_extension}"
        
        # 🚩 แก้ตรงนี้: เปลี่ยนจาก UPLOAD_DIR เป็น LOGO_UPLOAD_DIR
        # เพื่อให้รูปไปลงที่ app/static/uploads/ ตามที่เราเปิดประตู (Mount) ไว้
        file_path = os.path.join(LOGO_UPLOAD_DIR, new_filename)

        # บันทึกไฟล์ลง Disk
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(logo.file, buffer)
        
        company.logo_path = new_filename

    db.commit()
    return RedirectResponse(url="/admin/settings?msg=success", status_code=303)

@app.get("/admin/settings")
async def settings_page(request: Request,user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang), db: Session = Depends(get_db)):
    # 1. ดึงข้อมูลบริษัท
    company = db.query(models.CompanySetting).first()
    
    # 2. ดึงข้อมูล User ปัจจุบันจาก Cookie (เพื่อให้แสดงชื่อใน Tab ข้อมูลส่วนตัวได้)
    user_id = request.cookies.get("user_id")
    current_user = None
    if user_id:
        current_user = db.query(models.Employee).filter(models.Employee.id == user_id).first()
    
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "company": company,
        "texts": texts,
        "user": current_user  # 🚩 เพิ่มบรรทัดนี้เพื่อส่งข้อมูล User ไปให้ HTML
    })

# --- ในไฟล์ app/main.py ---

@app.get("/my-payslips", response_class=HTMLResponse)
async def my_payslips(
    request: Request,user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang), 
    month: int = None, 
    year: int = None, 
    db: Session = Depends(get_db)
):
    # ... โค้ดเช็ค Login เดิม ...
    user_id = request.cookies.get("user_id")
    
    now = datetime.now()
    target_month = month or now.month
    target_year = year or now.year

    # 🚩 แก้บรรทัดที่มีปัญหา: เปลี่ยน models.Payslip เป็น models.PayrollDetail
    payslips = db.query(models.PayrollDetail).filter(
        models.PayrollDetail.employee_id == int(user_id),
        models.PayrollDetail.month == target_month,
        models.PayrollDetail.year == target_year
    ).all()

    # ดึงข้อมูลบริษัทและพนักงานเพื่อไปแสดงในสลิป
    company = db.query(models.CompanySetting).first()
    employee = db.query(models.Employee).filter(models.Employee.id == int(user_id)).first()

    return templates.TemplateResponse("my_payslips.html", {
        "request": request,
        "payslips": payslips,
        "employee": employee,
        "company": company,
        "current_month": target_month,
        "texts": texts,
        "current_year": target_year
    })

@app.get("/admin/leave-summary")
async def admin_leave_summary(request: Request,user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang), db: Session = Depends(get_db)):
    # ดึงพนักงานทุกคนมาเพื่อแสดงยอดคงเหลือ
    employees = db.query(models.Employee).all()
    
    # ดึงการลาที่ Approved แล้วมานับยอด
    # (หรือจะดึงจากคอลัมน์ quota ในตาราง Employee ตรงๆ ก็ได้ถ้าเราเขียนระบบหักยอดไว้เป๊ะแล้ว)
    return templates.TemplateResponse("admin_leave_summary.html", {
        "request": request,
        "texts": texts,
        "employees": employees
    })