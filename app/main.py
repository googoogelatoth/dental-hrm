import os
import logging
import builtins
from datetime import date, datetime, timedelta
import io
import json
import uuid
import calendar
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from typing import List
from urllib.parse import urlparse

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    Request,
    Form,
    File,
    UploadFile,
    Response,
    Query,
    BackgroundTasks,
)
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
    FileResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, extract
from .database import SessionLocal, engine
from . import models
from .security import encrypt_data, decrypt_data
from .languages import TRANSLATIONS

import pandas as pd
from pywebpush import webpush, WebPushException
import cloudinary
import cloudinary.uploader
from starlette.exceptions import HTTPException as StarletteHTTPException
from dateutil.relativedelta import relativedelta
import pytz

import starlette.status as status
from .config import VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY

app = FastAPI()

# Configure structured logging for the application
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("clinic_hrm")

# Redirect simple logger.info() calls to structured logging (INFO level)
# This helps catch stray prints without changing every call site immediately.
builtins.print = logger.info

# --- ส่วนบนสุดของ main.py ---

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

# บนสุดของไฟล์
TH_TZ = pytz.timezone('Asia/Bangkok')

def get_now_th():
    return datetime.now(TH_TZ).replace(tzinfo=None)

# สร้างตารางในฐานข้อมูล (ถ้ายังไม่มี)
models.Base.metadata.create_all(bind=engine)

# 1. ตั้งค่า Cloudinary (ดึงค่าจากชื่อตัวแปร Environment)
cloudinary.config(
    cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key = os.getenv('CLOUDINARY_API_KEY'),
    api_secret = os.getenv('CLOUDINARY_API_SECRET'),
    secure = True
)

# ตั้งค่าตำแหน่งของไฟล์ HTML
templates = Jinja2Templates(directory="app/templates")


# Serve service worker at site root for full-origin scope
@app.get("/service-worker.js", include_in_schema=False)
async def service_worker() -> FileResponse:
    sw_path = os.path.join(STATIC_DIR, "sw.js")
    return FileResponse(sw_path, media_type="application/javascript")

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
    except Exception:
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

def upload_base64_to_cloudinary(base64_data, employee_code, suffix):
    try:
        if not base64_data or len(base64_data) < 100:
            return None
            
        # 🚩 ขั้นตอนสำคัญ: ถ้ามีหัวข้อความติดมา ให้ตัดออกเหลือแต่ตัวรหัสรูป
        if "base64," in base64_data:
            base64_data = base64_data.split("base64,")[1]

        # อัปโหลดขึ้น Cloudinary โดยตรง
        upload_result = cloudinary.uploader.upload(
            f"data:image/png;base64,{base64_data}",
            folder="hrm_system/attendance",
            public_id=f"{employee_code}_{suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            transformation=[
                {"width": 640, "crop": "limit", "quality": "auto"}
            ]
        )
        return upload_result.get("secure_url") # คืนค่าเป็นลิงก์ https://...
    except Exception as e:
        logger.info(f"❌ Cloudinary Error: {e}")
        return None
    
def upload_file_to_cloudinary(file, folder_name):
    try:
        # อัปโหลดไฟล์ตรงๆ จากหน่วยความจำ
        upload_result = cloudinary.uploader.upload(
            file.file,
            folder=f"hrm_system/{folder_name}/",
            # ถ้าเป็น PDF หรือรูปภาพ Cloudinary จัดการให้ได้หมดครับ
            resource_type="auto" 
        )
        return upload_result.get("secure_url")
    except Exception as e:
        logger.info(f"❌ Cloudinary Upload Error: {e}")
        return None

# ตั้งค่าการเข้ารหัสรหัสผ่าน
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Encryption helpers are provided by `app/security.py` and the Fernet instance
# is created from the `ENCRYPTION_KEY` environment variable in `app/config.py`.

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
            logger.info("--- Created Initial Admin User (User: admin / Pass: admin1234) ---")
    finally:
        db.close()


@app.on_event("startup")
async def validate_required_env():
    """Fail fast on startup when required environment variables are missing."""
    missing = []
    required = ["ENCRYPTION_KEY", "VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "DATABASE_URL"]
    for name in required:
        if not os.getenv(name):
            missing.append(name)

    if missing:
        logger.error("Missing required environment variables on startup: %s", ",".join(missing))
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
        
# Consolidated: push notification moved to send_push_notification() function (see line ~2432)

# ในไฟล์ app/main.py ฟังก์ชัน log_activity
def log_activity(db, user, action, details, request):
    # ตรวจสอบว่า user มี attribute first_name ไหม ถ้าไม่มีให้ใช้ชื่อที่ส่งมาหรือ 'System'
    u_name = "Unknown"
    if hasattr(user, 'first_name') and hasattr(user, 'last_name'):
        u_name = f"{user.first_name} {user.last_name}"
    elif hasattr(user, 'full_name'): # เผื่อกรณีใช้ object หลอกตัวเดิม
        u_name = user.full_name
    elif hasattr(user, 'employee_code'):
        u_name = user.employee_code

    now_th = datetime.now(TH_TZ).replace(tzinfo=None)
    new_log = models.ActivityLog(
        user_id=user.id if hasattr(user, 'id') else 0,
        user_name=u_name, # ใช้ตัวแปรที่เราเช็คมาแล้ว
        action=action,
        details=details,
        ip_address=request.client.host,
        created_at=now_th,
        timestamp=now_th
    )
    db.add(new_log)

# แก้ไขจากของเดิม ให้เป็นแบบนี้ครับ
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    # 1. เช็คก่อนว่าล็อกอินค้างไว้ไหม
    is_logged_in = request.cookies.get("is_logged_in") == "true"
    
    if is_logged_in:
        # ถ้าล็อกอินแล้ว ให้เด้งไปหน้ากราฟ (Monitor) ทันที
        return RedirectResponse(url="/monitor", status_code=303)
    else:
        # ถ้ายังไม่ได้ล็อกอิน ให้ไปหน้า Login
        return RedirectResponse(url="/login", status_code=303)

@app.get("/manifest.json")
async def get_manifest(db: Session = Depends(get_db)):
    # ดึงข้อมูลบริษัทล่าสุดจาก DB
    company = db.query(models.CompanySetting).first()
    
    # ถ้ายังไม่ได้อัปโหลดโลโก้ ให้ใช้โลโก้ Default
    logo_url = "/static/img/mini-hrm-logo.png"
    if company and company.logo_path:
        # ถ้า logo_path เป็น https (Cloudinary) ก็ใช้ได้เลย
        logo_url = company.logo_path if company.logo_path.startswith('http') else f"/static/uploads/{company.logo_path}"

    manifest_data = {
        "name": "Mini HRM System",
        "short_name": "MiniHRM",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#007bff",
        "icons": [
            {
                "src": logo_url,
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any"
            },
            {
                "src": logo_url,
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any"
            }
        ]
    }
    
    return Response(content=json.dumps(manifest_data), media_type="application/json")

@app.get("/admin/audit-logs")
async def view_audit_logs(
    request: Request,
    db: Session = Depends(get_db),
    user: models.Employee = Depends(get_current_active_user),
    texts: dict = Depends(get_lang)
):
    # 1. ตรวจสอบสิทธิ์ Admin เท่านั้น
    if user.role != "Admin":
        return RedirectResponse(url="/dashboard?error=permission", status_code=303)

    # 2. ดึงข้อมูล Logs 200 รายการล่าสุด
    logs = db.query(models.ActivityLog).order_by(models.ActivityLog.timestamp.desc()).limit(200).all()

    return templates.TemplateResponse("admin_logs.html", {
        "request": request,
        "logs": logs,
        "texts": texts,
        "user": user
    })

@app.get("/monitor", response_class=HTMLResponse)
async def monitor_page(
    request: Request,
    user: models.Employee = Depends(get_current_active_user),
    texts: dict = Depends(get_lang),
    db: Session = Depends(get_db)
):
    # 1. ข้อมูลพื้นฐานและเวลาปัจจุบัน
    now_th = get_now_th()
    today = now_th.date()
    company = db.query(models.CompanySetting).first()

    # 2. คำนวณสถิติ "วันนี้" (ข้อมูลจริง)
    total_active_emp = db.query(models.Employee).filter(models.Employee.is_active).count()
    
    # - มาทำงาน (เช็คอินแล้ว)
    present_today = db.query(models.Attendance).filter(models.Attendance.date == today).count()
    
    # - ลางาน (เฉพาะที่อนุมัติแล้วและครอบคลุมวันนี้)
    on_leave_today = db.query(models.LeaveRequest).filter(
        models.LeaveRequest.status == "Approved",
        models.LeaveRequest.start_date <= today,
        models.LeaveRequest.end_date >= today
    ).count()

    # - สาย และ ออกก่อน (ดึงจากบันทึกเวลาวันนี้)
    stat_late_today = db.query(models.Attendance).filter(
        models.Attendance.date == today, 
        models.Attendance.late_minutes > 0
    ).count()
    
    stat_early_today = db.query(models.Attendance).filter(
        models.Attendance.date == today, 
        models.Attendance.early_minutes > 0
    ).count()

    # - ขาดงาน (พนักงานทั้งหมด - มาทำงาน - ลางาน)
    stat_absent_today = max(0, total_active_emp - present_today - on_leave_today)

    # 3. ข้อมูลสำหรับกราฟวงกลม (Pie Chart) - สถิติการลาทั้งหมด
    sick_leave = db.query(models.LeaveRequest).filter(models.LeaveRequest.leave_type == "ลาป่วย").count()
    personal_leave = db.query(models.LeaveRequest).filter(models.LeaveRequest.leave_type == "ลากิจ").count()
    vacation_leave = db.query(models.LeaveRequest).filter(models.LeaveRequest.leave_type == "ลาพักร้อน").count()
    leave_pie_data = [sick_leave, personal_leave, vacation_leave]

    # 4. ข้อมูลสำหรับกราฟแท่ง (Bar Chart) - สถิติลา 6 เดือนล่าสุด
    thai_months = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    leave_bar_labels = []
    leave_bar_data = []

    for i in range(5, -1, -1):
        target_date = now_th - relativedelta(months=i)
        m = target_date.month
        y = target_date.year
        
        # นับจำนวนการลาในเดือนนั้นๆ
        month_count = db.query(models.LeaveRequest).filter(
            extract('month', models.LeaveRequest.start_date) == m,
            extract('year', models.LeaveRequest.start_date) == y
        ).count()
        
        leave_bar_labels.append(thai_months[m])
        leave_bar_data.append(month_count)

    return templates.TemplateResponse("monitor.html", {
        "request": request,
        "texts": texts,
        "user": user,
        "stat_total": total_active_emp,
        "stat_present": present_today,
        "stat_onleave": on_leave_today,
        "stat_late_today": stat_late_today,
        "stat_early_today": stat_early_today,
        "stat_absent_today": stat_absent_today,
        "leave_bar_labels": leave_bar_labels,
        "leave_bar_data": leave_bar_data,
        "leave_pie_data": leave_pie_data,
        "company_name": company.company_name if company else "Mini HRM",
        "company_logo": company.logo_path if company else None,
    })

@app.post("/api/accept-pdpa")
async def accept_pdpa(
    data: dict, 
    request: Request,  # 🚩 เพิ่มตรงนี้เพื่อให้เรียกใช้ใน log_activity ได้
    db: Session = Depends(get_db),
    user: models.Employee = Depends(get_current_active_user)
):
    if data.get("accepted"):
        # 1. อัปเดตสถานะใน DB
        db_user = db.query(models.Employee).filter(models.Employee.id == user.id).first()
        if db_user:
            db_user.pdpa_accepted = True
            
            # 2. บันทึก Log (🚩 เปลี่ยน Action และ Details ให้ตรงกับงาน)
            log_activity(
                db, 
                user, 
                "PDPA Consent", 
                "กดยอมรับเงื่อนไขการคุ้มครองข้อมูลส่วนบุคคล (PDPA)", 
                request
            )
            
            # 3. ยืนยันการบันทึก
            db.commit()
            return {"status": "success"}
            
    return {"status": "error"}

@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    # กรณี 401: ไม่ได้ Login หรือ Session หมดอายุ
    # กรณี 403: ไม่มีสิทธิ์เข้าถึง (บางทีเกิดจาก Session เพี้ยน)
    if exc.status_code in [401, 403]:
        return RedirectResponse(url="/login?msg=session_expired")
    
    # สำหรับ Error อื่นๆ เช่น 404 (หาหน้าไม่เจอ) หรือ 500 (ระบบพัง)
    # ให้ส่งค่ากลับไปเป็นหน้าจอปกติที่ระบบควรจะเป็น (ไม่หน้าขาวแน่นอน)
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": str(exc.detail)},
    )

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: models.Employee = Depends(get_current_active_user),
    texts: dict = Depends(get_lang), 
    db: Session = Depends(get_db)
):
    # 1. เช็คพื้นฐานว่ามีการ Login ไหม
    user_id = request.cookies.get("user_id")
    company = db.query(models.CompanySetting).first()
    
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
    active_emps = db.query(models.Employee).filter(models.Employee.is_active).all()
    resigned_emps = db.query(models.Employee).filter(~models.Employee.is_active).all()
    
    # 4. ส่งข้อมูลไปที่หน้า HTML
    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "active_emps": active_emps,     # ✅ ส่งตัวแปรที่เพิ่ง Query มา
        "resigned_emps": resigned_emps,   # ✅ ส่งตัวแปรที่เพิ่ง Query มา
        "public_vapid_key": VAPID_PUBLIC_KEY,
        "user_role": user.role, 
        "user": user,
        "company_name": company.company_name if company else None,
        "company_logo": company.logo_path if company else None,
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

# --- 1. ส่วนเพิ่มพนักงาน (ป้องกัน Error 500 จากการซ้ำ) ---
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
    # --- 1. ตรวจสอบสิทธิ์ Admin ---
    if not hasattr(user, 'role') or user.role != "Admin":
        raise HTTPException(status_code=403, detail="คุณไม่มีสิทธิ์")

    # --- 2. เช็คข้อมูลซ้ำ (Employee Code & ID Card) ---
    if db.query(models.Employee).filter(models.Employee.employee_code == employee_code).first():
        return templates.TemplateResponse("add_employee.html", {"request": request, "error": f"รหัสพนักงาน {employee_code} มีในระบบแล้ว", "texts": get_lang()})

    if id_card_number:
        target_id = encrypt_data(id_card_number)
        if db.query(models.Employee).filter(models.Employee.id_card_number == target_id).first():
            return templates.TemplateResponse("add_employee.html", {"request": request, "error": "เลขบัตรนี้มีในระบบแล้ว", "texts": get_lang()})

    # --- 3. จัดการรูปโปรไฟล์ ---
    profile_url = "/static/img/default-avatar.png"
    if profile_picture and profile_picture.filename:
        try:
            upload_result = cloudinary.uploader.upload(profile_picture.file, folder="hrm/profiles", public_id=f"emp_{employee_code}", overwrite=True)
            profile_url = upload_result.get("secure_url")
        except Exception as e:
            logger.info(f"Cloudinary Error: {e}")

    # --- 4. สร้าง Object พนักงานใหม่ ---
    new_emp = models.Employee(
        employee_code=employee_code,
        first_name=first_name,
        last_name=last_name,
        nickname=nickname,
        phone_number=encrypt_data(phone_number) if phone_number else None,
        id_card_number=encrypt_data(id_card_number) if id_card_number else None,
        bank_account_number=encrypt_data(bank_account_number) if bank_account_number else None,
        address=address, position=position, role=role,
        base_salary=base_salary, position_allowance=position_allowance,
        profile_picture=profile_url,
        hashed_password=pwd_context.hash(password)
    )
    
    db.add(new_emp)
    db.commit()
    db.refresh(new_emp)
    
    # --- 5. จัดการไฟล์เอกสาร ---
    if documents:
        for doc in documents:
            if doc.filename:
                try:
                    doc_upload = cloudinary.uploader.upload(doc.file, folder=f"hrm/docs/{employee_code}", resource_type="raw", public_id=doc.filename)
                    new_doc = models.EmployeeDocument(file_path=doc_upload.get("secure_url"), file_name=doc.filename, employee_id=new_emp.id)
                    db.add(new_doc)
                except Exception as e: 
                    logger.info(f"Doc Error: {e}")
        db.commit()

    # --- 6. 🚩 บันทึก Log การเพิ่มพนักงาน ---
    log_activity(
        db, 
        user, 
        "เพิ่มพนักงาน", 
        f"เพิ่มพนักงานใหม่: {first_name} {last_name} (รหัส: {employee_code})", 
        request
    )

    return RedirectResponse(url="/dashboard?msg=success", status_code=303)


# --- 2. ส่วนอัปเดตตั้งค่าองค์กร (Cloudinary) ---
@app.post("/admin/settings/company/update")
async def update_company_settings(
    request: Request, # 🚩 เพิ่มเพื่อใช้ดึง IP ใน Log
    company_name: str = Form(...),
    address: str = Form(...),
    logo: UploadFile = File(None),
    db: Session = Depends(get_db),
    user: models.Employee = Depends(get_current_active_user) # 🚩 เพิ่มเพื่อเช็คคนทำ
):
    # --- 1. ตรวจสอบสิทธิ์ (ควรให้เฉพาะ Admin เปลี่ยนค่าบริษัทได้) ---
    if user.role != "Admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    # --- 2. ค้นหาหรือสร้างข้อมูลบริษัท ---
    company = db.query(models.CompanySetting).first()
    if not company:
        company = models.CompanySetting()
        db.add(company)

    # --- 3. อัปเดตข้อมูล ---
    company.company_name = company_name
    company.address = address

    # --- 4. จัดการโลโก้บริษัท ---
    if logo and logo.filename:
        try:
            upload_result = cloudinary.uploader.upload(
                logo.file, 
                folder="hrm/company", 
                public_id="company_logo", 
                overwrite=True
            )
            company.logo_path = upload_result.get("secure_url")
        except Exception as e: 
            logger.info(f"Logo Error: {e}")

    # --- 5. 🚩 บันทึก Log ก่อน Commit ---
    log_activity(
        db, 
        user, 
        "ตั้งค่าระบบ", 
        f"อัปเดตข้อมูลบริษัท: {company_name}", 
        request
    )

    db.commit()
    return RedirectResponse(url="/admin/settings?msg=success", status_code=303)

# # --- 1. แสดงหน้าฟอร์มแก้ไข ---
# @app.get("/edit-employee/{emp_id}", response_class=HTMLResponse)
# async def edit_employee_page(emp_id: int, request: Request,user: models.Employee = Depends(get_current_active_user),texts: dict = Depends(get_lang), db: Session = Depends(get_db)):
    
#     if request.cookies.get("user_role") != "Admin":
#         return RedirectResponse(url="/check-in-page", status_code=303)
    
#     employee = db.query(models.Employee).filter(models.Employee.id == emp_id).first()
#     return templates.TemplateResponse("edit_employee.html",{"request": request,"texts": texts, "employee": employee})

# # --- 2. รับข้อมูลจากฟอร์มแก้ไข (POST) ---
# @app.post("/edit-employee/{emp_id}")
# async def handle_edit_employee(
#     request: Request,
#     emp_id: int,
#     first_name: str = Form(...),
#     last_name: str = Form(...),
#     nickname: str = Form(None),
#     id_card_number: str = Form(None),
#     phone_number: str = Form(None),
#     address: str = Form(None),
#     bank_account_number: str = Form(None),
#     position: str = Form(...),
#     role: str = Form(...),
#     # ✅ เพิ่มการรับค่าเงินเดือนและโควตาการลา
#     base_salary: float = Form(0.0),
#     position_allowance: float = Form(0.0),
#     sick_quota: int = Form(30),
#     personal_quota: int = Form(6),
#     vacation_quota: int = Form(6),
#     profile_picture: UploadFile = File(None),
#     documents: List[UploadFile] = File(None),
#     user: models.Employee = Depends(get_current_active_user),
#     db: Session = Depends(get_db)
# ):
#     # --- 1. ตรวจสอบสิทธิ์ Admin ---
#     if user.role != "Admin":
#         raise HTTPException(status_code=403, detail="Forbidden")
    
#     employee = db.query(models.Employee).filter(models.Employee.id == emp_id).first()
#     if not employee:
#         return RedirectResponse(url="/employees", status_code=status.HTTP_303_SEE_OTHER)

#     # เก็บข้อมูลเดิมไว้ทำ Log
#     old_data = f"เดิม: {employee.first_name} {employee.last_name}, เงินเดือน: {employee.base_salary}"

#     # --- 2. UNIQUE Check สำหรับบัตรประชาชน ---
#     if id_card_number:
#         encrypted_id_input = encrypt_data(id_card_number)
#         existing_emp = db.query(models.Employee).filter(
#             models.Employee.id_card_number == encrypted_id_input,
#             models.Employee.id != emp_id
#         ).first()
#         if existing_emp:
#             return templates.TemplateResponse("edit_employee.html", {
#                 "request": request,
#                 "employee": employee,
#                 "error": "เลขบัตรประชาชนนี้มีในระบบแล้ว"
#             })

#     # --- 3. อัปเดตข้อมูลทั่วไปและเงินเดือน ✅ ---
#     employee.first_name = first_name
#     employee.last_name = last_name
#     employee.nickname = nickname if nickname and nickname != "None" else employee.nickname
#     employee.address = address
#     employee.position = position
#     employee.role = role
    
#     # อัปเดตเงินเดือนและค่าตอบแทน
#     employee.base_salary = base_salary
#     employee.position_allowance = position_allowance
    
#     # อัปเดตโควตาการลา
#     employee.sick_leave_quota = sick_quota
#     employee.personal_leave_quota = personal_quota
#     employee.vacation_leave_quota = vacation_quota
    
#     # อัปเดตข้อมูลที่ต้องเข้ารหัส
#     if id_card_number:
#         employee.id_card_number = encrypt_data(id_card_number)
#     if phone_number:
#         employee.phone_number = encrypt_data(phone_number)
#     if bank_account_number:
#         employee.bank_account_number = encrypt_data(bank_account_number)

#     # --- 4. จัดการรูปโปรไฟล์ (Cloudinary) ---
#     log_details_extra = ""
#     if profile_picture and profile_picture.filename:
#         try:
#             upload_result = cloudinary.uploader.upload(
#                 profile_picture.file,
#                 folder="hrm/profiles",
#                 public_id=f"emp_{employee.employee_code}",
#                 overwrite=True
#             )
#             employee.profile_picture = upload_result.get("secure_url")
#             log_details_extra += " [อัปเดตรูปโปรไฟล์]"
#         except Exception as e:
#             logger.info(f"Cloudinary Profile Upload Error: {e}")

#     # --- 5. จัดการเอกสาร PDF ---
#     if documents:
#         for doc in documents:
#             if doc.filename:
#                 try:
#                     doc_upload = cloudinary.uploader.upload(
#                         doc.file,
#                         folder=f"hrm/docs/{employee.employee_code}",
#                         resource_type="raw",
#                         public_id=doc.filename
#                     )
#                     new_doc = models.EmployeeDocument(
#                         file_path=doc_upload.get("secure_url"),
#                         file_name=doc.filename,
#                         employee_id=employee.id
#                     )
#                     db.add(new_doc)
#                     log_details_extra += f" [เพิ่มเอกสาร: {doc.filename}]"
#                 except Exception as e:
#                     logger.info(f"Cloudinary Document Upload Error: {e}")
    
#     # --- 6. บันทึก Log และ Commit ---
#     new_data = f"ใหม่: {first_name} {last_name}, เงินเดือน: {base_salary}"
#     log_msg = f"แก้ไขข้อมูลพนักงาน ID: {emp_id} | {old_data} -> {new_data}{log_details_extra}"
    
#     log_activity(db, user, "แก้ไขข้อมูลพนักงาน", log_msg, request)
#     db.commit()

#     return RedirectResponse(url="/dashboard?msg=updated", status_code=status.HTTP_303_SEE_OTHER)

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
    
    # 🚩 เพิ่มบรรทัดนี้ครับนาย!
    logger.info(f"--- DEBUG EMPLOYEE {emp_id} ---")
    logger.info(f"Decrypted Data: {display_data}")
    logger.info("-------------------------------")

    return templates.TemplateResponse("employee_detail_content.html", {
        "request": request,
        "texts": texts, 
        "employee": employee,
        "decrypted": display_data  # ส่งค่าที่ถอดรหัสแล้วแยกไป
    })

# --- 🚩 ฟังก์ชันแจ้งลาออก ---
@app.post("/admin/employee/resign/{emp_id}")
async def resign_employee(
    request: Request, # 🚩 เพิ่มเพื่อใช้ดึง IP ใน Log
    emp_id: int, 
    db: Session = Depends(get_db),
    user: models.Employee = Depends(get_current_active_user)
):
    # 1. เช็คสิทธิ์ก่อน (ต้องเป็น Admin เท่านั้น)
    if not user or user.role != "Admin":
        return RedirectResponse(url="/dashboard?error=permission", status_code=303)

    # 2. ค้นหาพนักงานที่ต้องการเปลี่ยนสถานะ
    target_user = db.query(models.Employee).filter(models.Employee.id == emp_id).first()
    
    if target_user:
        # เก็บชื่อพนักงานไว้ใส่ใน Log ก่อนจะเปลี่ยนสถานะ
        emp_name = f"{target_user.first_name} {target_user.last_name}"
        emp_code = target_user.employee_code

        # 3. 🔴 เปลี่ยนสถานะเป็นลาออก (Disable Account)
        target_user.is_active = False 
        
        # 4. 🚩 บันทึก Log การลาออก
        log_activity(
            db, 
            user, 
            "แจ้งพนักงานลาออก", 
            f"เปลี่ยนสถานะพนักงานเป็นลาออก: {emp_name} (รหัส: {emp_code})", 
            request
        )

        # 5. ยืนยันการเปลี่ยนแปลง
        db.commit()
    
    return RedirectResponse(url="/dashboard?msg=resigned", status_code=303)

# --- 🟢 ฟังก์ชันดึงกลับเป็นพนักงาน (เผื่อกดผิด) ---
@app.post("/admin/employee/restore/{emp_id}")
async def restore_employee(
    request: Request, # 🚩 เพิ่มเพื่อใช้ดึง IP ใน Log
    emp_id: int, 
    db: Session = Depends(get_db),
    user: models.Employee = Depends(get_current_active_user)
):
    # 1. เช็คสิทธิ์ Admin
    if not user or user.role != "Admin":
        return RedirectResponse(url="/dashboard?error=permission", status_code=303)

    # 2. ค้นหาพนักงานที่ต้องการดึงกลับมา
    target_user = db.query(models.Employee).filter(models.Employee.id == emp_id).first()
    
    if target_user:
        # เก็บชื่อพนักงานไว้ใส่ใน Log
        emp_name = f"{target_user.first_name} {target_user.last_name}"
        emp_code = target_user.employee_code

        # 3. 🟢 เปลี่ยนสถานะกลับมาเป็น Active (คืนสิทธิ์การใช้งาน)
        target_user.is_active = True 
        
        # 4. 🚩 บันทึก Log การคืนสถานะ
        log_activity(
            db, 
            user, 
            "คืนสถานะพนักงาน", 
            f"กู้คืนสถานะพนักงานให้กลับมาทำงานปกติ: {emp_name} (รหัส: {emp_code})", 
            request
        )

        # 5. ยืนยันการเปลี่ยนแปลง
        db.commit()
    
    # แก้ msg ใน URL ให้เป็น restored เพื่อให้นายเอาไปดึงแจ้งเตือนหน้าบ้านได้ถูกตัวครับ
    return RedirectResponse(url="/dashboard?msg=restored", status_code=303)

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
    request: Request,
    texts: dict = Depends(get_lang),
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # 1. ค้นหาพนักงาน
    user = db.query(models.Employee).filter(models.Employee.employee_code == username).first()
    
    # 2. ตรวจสอบรหัสผ่าน
    if user and pwd_context.verify(password.encode('utf-8')[:72], user.hashed_password):
        
        # --- [ส่วนที่เพิ่มใหม่: Single Device Login] ---
        new_session_id = str(uuid.uuid4())
        user.current_session_id = new_session_id
        
        # 🚩 บันทึก Log: Login สำเร็จ (ใช้ตัวแปร user จริงจาก DB)
        log_activity(
            db, 
            user, 
            "เข้าสู่ระบบ", 
            f"พนักงาน {user.first_name} เข้าสู่ระบบสำเร็จ (Session: {new_session_id[:8]}...)", 
            request
        )
        
        db.commit()
        # --------------------------------------------

        # กำหนดหน้าปลายทาง
        res = RedirectResponse(url="/monitor", status_code=status.HTTP_303_SEE_OTHER)
        
        # 3. ตั้งค่า Cookie
        max_age = 60 * 60 * 24 * 30  # 30 วัน
        res.set_cookie(key="session_id", value=new_session_id, max_age=max_age, httponly=True)
        res.set_cookie(key="is_logged_in", value="true", max_age=max_age)
        res.set_cookie(key="user_name", value=user.employee_code, max_age=max_age) 
        res.set_cookie(key="user_role", value=user.role, max_age=max_age)
        res.set_cookie(key="user_id", value=str(user.id), max_age=max_age) 
        
        return res
    
    # --- 🚩 บันทึก Log: Login ล้มเหลว (สร้าง Dummy Object ที่มี Attribute ตรงกับ log_activity) ---
    log_user_id = user.id if user else 0
    dummy_user = type('obj', (object,), {
        'id': log_user_id, 
        'first_name': 'Unknown', 
        'last_name': f'({username})',
        'employee_code': username
    })
    
    log_activity(
        db, 
        dummy_user, 
        "ล็อกอินล้มเหลว", 
        f"พยายามเข้าสู่ระบบด้วยรหัส: {username} แต่รหัสผ่านไม่ถูกต้อง", 
        request
    )
    db.commit()

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
    request: Request,
    user: models.Employee = Depends(get_current_active_user),
    texts: dict = Depends(get_lang),
    old_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    # 1. ตรวจสอบรหัสผ่านใหม่และยืนยันว่าตรงกันไหม
    if new_password != confirm_password:
        return templates.TemplateResponse("change_password.html", {
            "request": request, 
            "texts": texts,
            "error": "รหัสผ่านใหม่และยืนยันรหัสผ่านไม่ตรงกัน"
        })

    # 2. ค้นหา User (ใช้ object 'user' จาก Depends ได้เลยครับนาย ไม่ต้องดึงจาก cookie ซ้ำ)
    if user:
        # 3. ตรวจสอบรหัสผ่านเดิม
        if pwd_context.verify(old_password, user.hashed_password):
            
            # 4. เข้ารหัสผ่านใหม่ (Hash) และบันทึก
            user.hashed_password = pwd_context.hash(new_password)
            
            # 🚩 บันทึก Log: เปลี่ยนรหัสผ่านสำเร็จ
            log_activity(
                db, 
                user, 
                "เปลี่ยนรหัสผ่าน", 
                "ดำเนินการเปลี่ยนรหัสผ่านใหม่สำเร็จด้วยตนเอง", 
                request
            )
            
            db.commit()
            
            # 5. Redirect ไปหน้า dashboard
            return RedirectResponse(url="/dashboard?msg=pw_changed", status_code=status.HTTP_303_SEE_OTHER)
        
        # --- 🚩 บันทึก Log: เปลี่ยนรหัสผ่านล้มเหลว (รหัสเดิมผิด) ---
        log_activity(
            db, 
            user, 
            "เปลี่ยนรหัสผ่านล้มเหลว", 
            "พยายามเปลี่ยนรหัสผ่านแต่ระบุรหัสผ่านเดิมไม่ถูกต้อง", 
            request
        )
        db.commit() # ต้อง commit log ลงไปครับ

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
# def save_attendance_photo(base64_data, emp_code, type="in"):
#     if not base64_data:
#         return None
    
#     # ตรวจสอบและสร้างโฟลเดอร์ถ้ายังไม่มี
#     upload_dir = "uploads/attendance_photos"
#     if not os.path.exists(upload_dir):
#         os.makedirs(upload_dir)

#     # ตัดส่วน Header ของ Base64 ออก (data:image/jpeg;base64,...)
#     header, encoded = base64_data.split(",", 1)
#     data = base64.b64decode(encoded)
    
#     # ตั้งชื่อไฟล์: รหัสพนักงาน_ประเภท_วันเวลา_uuid.jpg
#     file_name = f"{emp_code}_{type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.jpg"
#     file_path = os.path.join(upload_dir, file_name)
    
#     with open(file_path, "wb") as f:
#         f.write(data)
    
#     return file_name

# 🚩 ฟังก์ชันจัดการการลงเวลา (รวม In และ Out ไว้ในจุดที่จัดการง่าย)
@app.post("/attendance/check-in")
async def handle_check_in(
    request: Request,
    user: models.Employee = Depends(get_current_active_user), 
    lat: float = Form(None), 
    lon: float = Form(None),
    image_data: str = Form(None), 
    db: Session = Depends(get_db)
):
    # 1. ดึงข้อมูลพนักงานจาก Cookie เพื่อความปลอดภัย
    emp_code = request.cookies.get("user_name")
    user = db.query(models.Employee).filter(models.Employee.employee_code == emp_code).first()
    
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    # 2. ตั้งค่าเวลาปัจจุบัน (ICT Timezone)
    now = get_now_th()
    today = now.date()
    current_time = now.time()
    schedule = user.schedule

    # 3. ค้นหา Record ของวันนี้ในฐานข้อมูล
    attendance = db.query(models.Attendance).filter(
        models.Attendance.employee_id == user.id,
        models.Attendance.date == today
    ).first()

    # -------------------------------------------------------
    # 📸 กรณีที่ 1: บันทึกเช็คอิน (First-In)
    # จะทำงานเฉพาะตอนที่ "ยังไม่มี" ข้อมูลของวันนี้เท่านั้น
    # -------------------------------------------------------
    if not attendance:
        # อัปโหลดรูปเข้างาน (ครั้งแรกของวัน)
        photo_url = upload_base64_to_cloudinary(image_data, user.employee_code, "in")
        
        late_min = 0
        status = "Normal"

        # คำนวณนาทีสาย
        if schedule and schedule.work_start_time:
            start_dt = datetime.strptime(schedule.work_start_time, "%H:%M")
            if current_time > start_dt.time():
                diff = datetime.combine(today, current_time) - datetime.combine(today, start_dt.time())
                total_late = int(diff.total_seconds() / 60)
                # หักลบช่วงเวลา Grace Period (ถ้ามี)
                late_min = max(0, total_late - (schedule.grace_period_late or 0))
                if late_min > 0:
                    status = "Late"

        # สร้าง Record ใหม่ (มีแค่ Check-in)
        new_attendance = models.Attendance(
            employee_id=user.id,
            date=today,
            check_in=now, # บันทึกเวลาเข้าครั้งแรก
            lat=lat,
            lon=lon,
            late_minutes=late_min,
            image_in=photo_url,
            status=status
        )
        db.add(new_attendance)
        msg = "success"
    
    # -------------------------------------------------------
    # 📸 กรณีที่ 2: บันทึกเช็คเอาท์ (Last-Out)
    # จะทำงานเมื่อมีข้อมูลเช็คอินอยู่แล้ว และจะ Update ทับทุกครั้งที่กดซ้ำ
    # -------------------------------------------------------
    else:
        # อัปโหลดรูปออกงาน (จะอัปเดตรูปใหม่ทุกครั้งที่กดออกซ้ำ)
        photo_url = upload_base64_to_cloudinary(image_data, user.employee_code, "out")
        
        early_min = 0
        # คำนวณนาทีออกก่อน (เทียบกับเวลาที่กดล่าสุด)
        if schedule and schedule.work_end_time:
            end_dt = datetime.strptime(schedule.work_end_time, "%H:%M")
            if current_time < end_dt.time():
                diff = datetime.combine(today, end_dt.time()) - datetime.combine(today, current_time)
                total_early = int(diff.total_seconds() / 60)
                early_min = max(0, total_early - (schedule.grace_period_early_out or 0))

        # อัปเดตข้อมูลทับลงในแถวเดิม (Update Existing Row)
        attendance.check_out = now  # เวลาจะเลื่อนไปตามการกดครั้งล่าสุด
        attendance.early_minutes = early_min
        attendance.image_out = photo_url 
        
        # ตรวจสอบสถานะรวม (ถ้าสายหรือออกก่อน ให้เป็น Abnormal)
        if (attendance.late_minutes or 0) > 0 or early_min > 0:
            attendance.status = "Abnormal"
        else:
            attendance.status = "Normal"
            
        # อัปเดตพิกัดล่าสุดตอนออก
        if lat:
            attendance.lat = lat
        if lon:
            attendance.lon = lon
        msg = "checkout_success"

    # 4. บันทึกทุกอย่างลง Database
    db.commit()
    
    # ส่งกลับไปยังหน้าเช็คอินพร้อมข้อความแจ้งเตือน
    return RedirectResponse(url=f"/check-in-page?msg={msg}", status_code=303)

# @app.post("/attendance/check-out")
# async def handle_check_out(
#     request: Request,
#     user: models.Employee = Depends(get_current_active_user), 
#     lat: float = Form(None), 
#     lon: float = Form(None),
#     image_data: str = Form(None), 
#     db: Session = Depends(get_db)
# ):
#     # 1. ตรวจสอบ User จาก Cookie
#     emp_code = request.cookies.get("user_name")
#     user = db.query(models.Employee).filter(models.Employee.employee_code == emp_code).first()
    
#     if not user:
#         return RedirectResponse(url="/login", status_code=303)

#     now = get_now_th() # ใช้เวลาไทยที่ตั้งค่าไว้
#     today = now.date()
#     current_time = now.time()
#     schedule = user.schedule

#     # 2. ค้นหา Record ของวันนี้ที่เคย Check-in ไว้
#     attendance = db.query(models.Attendance).filter(
#         models.Attendance.employee_id == user.id,
#         models.Attendance.date == today
#     ).first()
    
#     if attendance:
#         # --- 📸 1. บันทึกรูปภาพตอนออกงานขึ้น Cloudinary ---
#         # ใช้ฟังก์ชัน upload_base64_to_cloudinary ที่เราสร้างไว้
#         photo_url = upload_base64_to_cloudinary(image_data, emp_code, "out")
        
#         # เก็บ URL ที่ได้ลงในฐานข้อมูล (ถ้าอัปโหลดสำเร็จจะได้ https://...)
#         if photo_url:
#             attendance.image_out = photo_url 

#         # --- 2. คำนวณการออกก่อนเวลา (Early Out) ---
#         early_min = 0
#         if schedule and schedule.work_end_time:
#             try:
#                 end_dt = datetime.strptime(schedule.work_end_time, "%H:%M")
#                 end_time = end_dt.time()
                
#                 if current_time < end_time:
#                     # คำนวณส่วนต่างเวลา
#                     diff = datetime.combine(today, end_time) - datetime.combine(today, current_time)
#                     total_early = int(diff.total_seconds() / 60)
                    
#                     # หักลบช่วงเวลาอนุโลม (Grace Period)
#                     grace_period = schedule.grace_period_early_out or 0
#                     early_min = max(0, total_early - grace_period)
#             except Exception as e:
#                 logger.info(f"❌ Error calculating early out: {e}")

#         # --- 3. บันทึกค่าลง Database ---
#         attendance.check_out = now 
#         attendance.early_minutes = early_min
        
#         # ปรับสถานะ (ถ้ามาสายตอนเช้า หรือออกก่อนตอนเย็น ให้เป็น Abnormal)
#         is_late = attendance.late_minutes and attendance.late_minutes > 0
#         is_early = early_min > 0
        
#         if is_late or is_early:
#             attendance.status = "Abnormal"
#         else:
#             attendance.status = "Normal"
        
#         # อัปเดตพิกัดล่าสุดตอนออก
#         if lat: attendance.lat = lat 
#         if lon: attendance.lon = lon
        
#         db.commit()

#     return RedirectResponse(url="/check-in-page?msg=checkout_success", status_code=303)

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
    user: models.Employee = Depends(get_current_active_user),
    texts: dict = Depends(get_lang), 
    db: Session = Depends(get_db)
):
    # 🔓 เตรียมข้อมูลถอดรหัส
    display_data = {
        "phone_number": decrypt_data(user.phone_number) if user.phone_number else "",
        "id_card_number": decrypt_data(user.id_card_number) if user.id_card_number else "",
        "bank_account_number": decrypt_data(user.bank_account_number) if user.bank_account_number else ""
    }

    return templates.TemplateResponse("my_profile.html", {
        "request": request, 
        "employee": user,
        "public_vapid_key": VAPID_PUBLIC_KEY,
        "texts": texts, 
        "decrypted": display_data,  # ✅ นายต้องเพิ่มบรรทัดนี้ครับ! ปัญหาอยู่ตรงนี้เลย
        "is_staff_view": True 
    })
    
@app.post("/leave/apply")
async def handle_leave_apply(
    request: Request,
    user: models.Employee = Depends(get_current_active_user),
    leave_type: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    reason: str = Form(...),
    evidence: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    # 1. ตรวจสอบ Login
    emp_code = request.cookies.get("user_name")
    user = db.query(models.Employee).filter(models.Employee.employee_code == emp_code).first()
    
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    # ✅ 2. จัดการไฟล์แนบ (เปลี่ยนจากเซฟลงเครื่อง เป็นขึ้น Cloudinary)
    evidence_url = None
    if evidence and evidence.filename:
        # เรียกใช้ฟังก์ชันที่เราสร้างไว้
        evidence_url = upload_file_to_cloudinary(evidence, "leave_documents")

    # 3. บันทึกลง Database
    new_leave = models.LeaveRequest(
        employee_id=user.id,
        leave_type=leave_type,
        # แปลง string เป็น date object
        start_date=datetime.strptime(start_date, "%Y-%m-%d").date(),
        end_date=datetime.strptime(end_date, "%Y-%m-%d").date(),
        reason=reason,
        evidence_path=evidence_url, # 🚩 เก็บเป็น URL HTTPS แทน Path เดิม
        status="Pending"
    )
    db.add(new_leave)
    db.commit()

    # 🚩 ส่วนส่งแจ้งเตือนหา Admin
    try:
        admins = db.query(models.Employee).filter(
            (models.Employee.role.ilike("admin")) | 
            (models.Employee.employee_code == "admin")
        ).all()
        
        for admin in admins:
            sender_info = user.employee_code if user else "ไม่ระบุรหัส"
            send_push_notification(
                admin.id, 
                "📢 มีคำขอลาใหม่", 
                f"พนักงานรหัส {sender_info} ส่งคำขอรออนุมัติ ({leave_type})", 
                db
            )
    except Exception as e:
        logger.info(f"❌ Notification Error: {e}")

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
                except Exception:
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
            send_push_notification(
                leave.employee_id, 
                f"{icon} ผลการพิจารณาการลา", 
                f"คำขอลาของคุณ{status_text}", 
                db
            )
        except Exception as e:
            logger.info(f"Push Notification Error: {e}")
    
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
async def edit_employee_page(
    emp_id: int, 
    request: Request,
    user: models.Employee = Depends(get_current_active_user),
    texts: dict = Depends(get_lang), 
    db: Session = Depends(get_db)
):
    # ตรวจสอบสิทธิ์ Admin (ใช้ user object โดยตรงชัวร์กว่า cookie)
    if not user or user.role != "Admin":
        return RedirectResponse(url="/dashboard", status_code=303)
    
    employee = db.query(models.Employee).filter(models.Employee.id == emp_id).first()
    if not employee:
        return RedirectResponse(url="/dashboard", status_code=303)

    # ✅ เพิ่มการถอดรหัสข้อมูลก่อนส่งไปโชว์ที่หน้า Form
    decrypted_data = {
        "phone_number": decrypt_data(employee.phone_number),
        "id_card_number": decrypt_data(employee.id_card_number),
        "bank_account_number": decrypt_data(employee.bank_account_number)
    }
    
    return templates.TemplateResponse("edit_employee.html", {
        "request": request, 
        "texts": texts, 
        "employee": employee,
        "decrypted": decrypted_data # 🚩 ส่งค่าที่ถอดแล้วไปใช้ใน value ของ HTML
    })

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
    base_salary: float = Form(0.0),
    position_allowance: float = Form(0.0),
    sick_quota: int = Form(30),        # รวมโควตาลามาไว้ที่นี่เลย
    personal_quota: int = Form(6),
    vacation_quota: int = Form(6),
    profile_picture: UploadFile = File(None),
    documents: List[UploadFile] = File(None),
    user: models.Employee = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # 1. ตรวจสอบสิทธิ์ Admin
    if not user or user.role != "Admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    
    employee = db.query(models.Employee).filter(models.Employee.id == emp_id).first()
    if not employee:
        return RedirectResponse(url="/dashboard", status_code=303)

    # 2. เก็บข้อมูลเดิมไว้ทำ Log (ละเอียดขึ้น)
    old_data = (f"เดิม: {employee.first_name} {employee.last_name}, "
                f"เงินเดือน: {employee.base_salary}, "
                f"โควตา(ป่วย/กิจ/พัก): {employee.sick_leave_quota}/{employee.personal_leave_quota}/{employee.vacation_leave_quota}")

    # 3. UNIQUE Check สำหรับบัตรประชาชน (Encrypt ก่อนเทียบ)
    if id_card_number:
        encrypted_id_input = encrypt_data(id_card_number)
        existing_emp = db.query(models.Employee).filter(
            models.Employee.id_card_number == encrypted_id_input,
            models.Employee.id != emp_id
        ).first()
        if existing_emp:
            return templates.TemplateResponse("edit_employee.html", {
                "request": request, "employee": employee, "error": "เลขบัตรประชาชนนี้มีในระบบแล้ว", "texts": get_lang()
            })

    # 4. อัปเดตข้อมูลทั่วไป เงินเดือน และโควตาการลา
    employee.first_name = first_name
    employee.last_name = last_name
    employee.nickname = nickname if nickname and nickname != "None" else employee.nickname
    employee.address = address
    employee.position = position
    employee.role = role
    employee.base_salary = base_salary
    employee.position_allowance = position_allowance
    employee.sick_leave_quota = sick_quota
    employee.personal_leave_quota = personal_quota
    employee.vacation_leave_quota = vacation_quota
    
    # 5. ✅ เข้ารหัสข้อมูลลับก่อนบันทึก
    if id_card_number:
        employee.id_card_number = encrypt_data(id_card_number)
    if phone_number:
        employee.phone_number = encrypt_data(phone_number)
    if bank_account_number:
        employee.bank_account_number = encrypt_data(bank_account_number)

    # 6. จัดการรูปโปรไฟล์ (Cloudinary)
    log_extra = ""
    if profile_picture and profile_picture.filename:
        try:
            upload_result = cloudinary.uploader.upload(
                profile_picture.file,
                folder="hrm/profiles",
                public_id=f"emp_{employee.employee_code}",
                overwrite=True
            )
            employee.profile_picture = upload_result.get("secure_url")
            log_extra += " [อัปเดตรูป]"
        except Exception as e:
            logger.info(f"Cloudinary Error: {e}")

    # 7. บันทึก Log และ Commit
    new_data = f"ใหม่: {first_name} {last_name}, เงินเดือน: {base_salary}, โควตา: {sick_quota}/{personal_quota}/{vacation_quota}"
    log_activity(db, user, "แก้ไขข้อมูลพนักงาน", f"{old_data} -> {new_data}{log_extra}", request)
    
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
            if leave:
                status = f"ลา ({leave.leave_type})"
            elif is_holiday:
                status = f"วันหยุด ({is_holiday.holiday_name})"
            elif not is_work_day:
                status = "วันหยุดประจำสัปดาห์"

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
        logger.info(f"❌ Database Error: {e}")
        return RedirectResponse(url="/attendance-report?msg=error", status_code=303)

    # 🚩 3. ส่งแจ้งเตือนหา Admin (วางไว้ตรงนี้หลัง commit)
    try:
        # ใช้สูตรหา Admin ที่ชัวร์ที่สุด
        admins = db.query(models.Employee).filter(
            (models.Employee.role.ilike("admin")) | 
            (models.Employee.employee_code == "admin")
        ).all()
        
        for admin in admins:
            send_push_notification(
                admin.id, 
                "📢 คำขอลงเวลาย้อนหลัง", 
                f"มีคำขอจาก {user.first_name} ({user.nickname}) รอการอนุมัติ", 
                db
            )
        logger.info(f"🔔 Manual Attendance Notification sent to {len(admins)} admins")
    except Exception as e:
        logger.info(f"❌ Notification Error: {e}")
    
    return RedirectResponse(url="/attendance-report?msg=request_sent", status_code=303)

async def perform_approval_logic(request_id: int, status: str, admin_remark: str, db: Session):
    req = db.query(models.ManualAttendanceRequest).filter(models.ManualAttendanceRequest.id == request_id).first()
    if not req:
        return False

    if status == "Rejected":
        req.status = "Rejected"
        req.admin_remark = admin_remark
        db.commit()
        send_push_notification(req.employee_id, "❌ คำขอลงเวลาถูกปฏิเสธ", f"คำขอวันที่ {req.request_date} ไม่ได้รับอนุมัติ {admin_remark or ''}", db)
        return True

    # --- กรณี Admin กด "อนุมัติ" (Approved) ---
    # emp = db.query(models.Employee).get(req.employee_id)  # unused
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

    # ... (ก๊อป Logic การเช็ค Late/Early Out ของนายมาใส่ตรงนี้เหมือนเดิมเป๊ะ) ...
    is_abnormal = False
    # (โค้ดเช็คสายและออกก่อนเหมือนที่นายส่งมา)
    
    attendance.status = "ผิดปกติ" if is_abnormal else "ปกติ"
    req.status = "Approved"
    req.admin_remark = admin_remark
    db.commit()
    send_push_notification(req.employee_id, "✅ อนุมัติการแก้ไขเวลา", f"คำขอวันที่ {req.request_date} อนุมัติเรียบร้อย", db)
    return True

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
    
@app.post("/admin/approve-request/{request_id}")
async def approve_request(
    request_id: int, 
    user: models.Employee = Depends(get_current_active_user), 
    status: str = Form(...), 
    admin_remark: str = Form(None), 
    db: Session = Depends(get_db)
):
    # เรียกใช้ฟังก์ชันกลาง
    await perform_approval_logic(request_id, status, admin_remark, db)
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
async def import_attendance_upload(
    request: Request, 
    file: UploadFile = File(...), 
    db: Session = Depends(get_db),
    user: models.Employee = Depends(get_current_active_user) # 🚩 เพิ่มเพื่อเก็บ Log คนทำ
):
    # --- ตรวจสอบสิทธิ์ Admin ---
    if user.role != "Admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        contents = await file.read()
        # รองรับทั้ง Excel และ CSV
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
                    if pd.isna(t_val) or str(t_val).strip() in ('-', '', 'nan'):
                        return None
                    if hasattr(t_val, 'hour'):
                        return t_val
                    t_str = str(t_val).strip()
                    for fmt in ("%H:%M:%S", "%H:%M"):
                        try:
                            return datetime.strptime(t_str, fmt).time()
                        except Exception:
                            continue
                    return None

                # 3. ดึงเวลาเข้า-ออก
                in_time = parse_time_flexible(row.iloc[3])
                out_time = parse_time_flexible(row.iloc[5])

                # 🚀 บันทึกใน ManualAttendanceRequest (คำร้องขอลงเวลา)
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
                        reason=f"Imported from {file.filename}", # ระบุชื่อไฟล์ที่มา
                        status="Pending"
                    )
                    db.add(new_req)
                    count_success += 1
        
        # 🚩 บันทึก Log: การ Import ข้อมูล
        log_activity(
            db, 
            user, 
            "Import ข้อมูลเข้างาน", 
            f"นำเข้าไฟล์: {file.filename} สำเร็จ {count_success} รายการ (รอ Admin อนุมัติ)", 
            request
        )

        db.commit()
        return RedirectResponse(url="/admin/attendance-requests?msg=import_success", status_code=303)
        
    except Exception as e:
        logger.info(f"🚩 Import Error: {e}")
        # บันทึก Log กรณีล้มเหลวด้วยเพื่อตรวจสอบปัญหา
        log_activity(db, user, "Import ล้มเหลว", f"เกิดข้อผิดพลาดขณะนำเข้าไฟล์ {file.filename}: {str(e)}", request)
        db.commit()
        return {"error": f"เกิดข้อผิดพลาดในการนำเข้า: {str(e)}"}

# 🚀 เพิ่มฟังก์ชันนี้เพื่อให้ปุ่มในหน้า Report ทำงานได้
@app.get("/manual-attendance-form-admin", response_class=HTMLResponse)
async def import_attendance_page(request: Request):
    # หน้าจอนี้สำหรับ Admin เข้าไปเพื่อ Upload ไฟล์ Excel
    return templates.TemplateResponse("import_attendance.html", {"request": request})

# VAPID configuration is loaded from `app.config` via environment variables.
VAPID_CLAIMS = {
    "sub": os.getenv("VAPID_CLAIMS_SUB", "mailto:your-email@example.com")
}

@app.post("/api/save-subscription")
async def save_subscription(request: Request, db: Session = Depends(get_db)):
    subscription_data = await request.json()
    # ดึงข้อมูลผู้ใช้จาก Cookie
    user_code = request.cookies.get("employee_code") or request.cookies.get("user_name")
    
    user = db.query(models.Employee).filter(models.Employee.employee_code == user_code).first()
    
    if not user:
        return {"status": "error", "message": "User not found"}

    # ค้นหาว่าเครื่องนี้/Browser นี้เคยลงทะเบียนหรือยัง
    existing = db.query(models.PushSubscription).filter(
        models.PushSubscription.endpoint == subscription_data['endpoint']
    ).first()
    
    now_th = get_now_th() # ใช้เวลาไทยที่นายทำไว้
    action_type = ""
    log_detail = ""

    if existing:
        # 🚩 อัปเดตข้อมูลให้เป็นปัจจุบัน
        existing.p256dh = subscription_data['keys']['p256dh']
        existing.auth = subscription_data['keys']['auth']
        existing.employee_id = user.id 
        
        action_type = "UPDATE NOTIFICATION"
        log_detail = "อัปเดตข้อมูลการแจ้งเตือน (Device/Browser เดิม)"
    else:
        # ✅ บันทึกอันใหม่ (เปิดครั้งแรก)
        new_sub = models.PushSubscription(
            employee_id=user.id,
            endpoint=subscription_data['endpoint'],
            p256dh=subscription_data['keys']['p256dh'],
            auth=subscription_data['keys']['auth']
        )
        db.add(new_sub)
        
        action_type = "ENABLE NOTIFICATION"
        log_detail = f"เปิดการแจ้งเตือนครั้งแรก (Device: {subscription_data['endpoint'][:40]}...)"

    # ✅ เพิ่มการบันทึก Activity Log ลงใน Database
    new_log = models.ActivityLog(
        user_id=user.id,
        user_name=f"{user.first_name} {user.last_name}",
        action=action_type,
        details=log_detail,
        ip_address=request.client.host if request.client else "Unknown",
        timestamp=now_th
    )
    db.add(new_log)
    
    db.commit()
    return {"status": "success"}

# def send_push_notification(employee_id: int, title: str, message: str, db: Session):
#     # ดึง Subscription ทั้งหมดของพนักงานคนนี้ (เขาอาจจะมีหลายเครื่อง)
#     subs = db.query(models.PushSubscription).filter(
#         models.PushSubscription.employee_id == employee_id
#     ).all()
    
#     for sub in subs:
#         try:
#             webpush(
#                 subscription_info={
#                     "endpoint": sub.endpoint,
#                     "keys": {"p256dh": sub.p256dh, "auth": sub.auth}
#                 },
#                 data=json.dumps({"title": title, "body": message}),
#                 vapid_private_key=VAPID_PRIVATE_KEY,
#                 vapid_claims=VAPID_CLAIMS
#             )
#         except WebPushException as ex:
#             logger.info(f"Push failed: {ex}")
#             # ถ้า Token หมดอายุ (410 Gone) ให้ลบออกจาก DB
#             if ex.response and ex.response.status_code == 410:
#                 db.delete(sub)
#                 db.commit()

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
            logger.info(f"Push failed: {ex}")
            if ex.response and ex.response.status_code == 410:
                db.delete(sub)
                db.commit()

def calculate_ot_pay(emp_id: int, month: int, year: int, db: Session):
    # 1. ดึงข้อมูลพนักงานเพื่อเอาฐานเงินเดือนมาคำนวณ Rate ต่อชั่วโมง
    user = db.query(models.Employee).filter(models.Employee.id == emp_id).first()
    if not user or not user.base_salary:
        return 0.0
    
    # สูตรคำนวณรายชั่วโมง (เงินเดือน / 30 วัน / 8 ชั่วโมง)
    # หมายเหตุ: ตรงนี้คูณ 1.5 เป็นค่าเฉลี่ย ถ้านายมีหลาย Rate (1.5, 2, 3) 
    # อาจต้องทำ Logic แยกตามประเภท ot_type ในอนาคตครับ
    hourly_rate = (user.base_salary / 30 / 8)
    
    # 2. รวมนาที OT จากตาราง ot_requests (คอลัมน์ total_minutes ตาม Model ของนาย)
    total_mins = db.query(func.sum(models.OTRequest.total_minutes)).filter(
        models.OTRequest.employee_id == emp_id,
        models.OTRequest.status == "approved",  # ดึงเฉพาะที่ Admin อนุมัติแล้ว
        extract('month', models.OTRequest.request_date) == month, # ใช้ request_date ตาม Model
        extract('year', models.OTRequest.request_date) == year
    ).scalar() or 0.0
    
    # 3. แปลงนาทีเป็นชั่วโมง (หาร 60) แล้วคูณด้วย Rate (สมมติมาตรฐานที่ 1.5 เท่า)
    ot_pay_total = (total_mins / 60) * hourly_rate * 1.5
    
    return round(ot_pay_total, 2)

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
    request: Request, 
    user: models.Employee = Depends(get_current_active_user), 
    texts: dict = Depends(get_lang),
    start_date: str = None,
    end_date: str = None,
    reset: str = Query(None),
    db: Session = Depends(get_db)
):
    # 1. จัดการวันที่ Default ของเดือน
    now_th = get_now_th()
    if not start_date or not end_date:
        start_date = now_th.replace(day=1).strftime('%Y-%m-%d')
        last_day = calendar.monthrange(now_th.year, now_th.month)[1]
        end_date = now_th.replace(day=last_day).strftime('%Y-%m-%d')

    s_dt_global = datetime.strptime(start_date, '%Y-%m-%d').date()
    e_dt_global = datetime.strptime(end_date, '%Y-%m-%d').date()

    # 2. ระบบ Reset Draft
    if reset == "true":
        db.query(models.PayrollDetail).filter(
            models.PayrollDetail.month == e_dt_global.month,
            models.PayrollDetail.year == e_dt_global.year,
            models.PayrollDetail.status == "Draft"
        ).delete()
        db.commit()
        return RedirectResponse(url=f"/admin/calculate-payroll?start_date={start_date}&end_date={end_date}", status_code=303)

    settings = get_payroll_settings(db)
    employees = db.query(models.Employee).filter(models.Employee.is_active).all()

    # ดึงวันหยุดนักขัตฤกษ์ในช่วงเวลาที่เลือก
    holidays = db.query(models.Holiday).filter(
        models.Holiday.holiday_date >= s_dt_global,
        models.Holiday.holiday_date <= e_dt_global
    ).all()
    holiday_dates = {h.holiday_date for h in holidays}

    for emp in employees:
        # --- 🚩 [แก้ไขส่วนการเลือกวันที่] ---
        # 1. เช็คข้อมูล Draft ใน DB ก่อน
        draft = db.query(models.PayrollDetail).filter(
            models.PayrollDetail.employee_id == emp.id,
            models.PayrollDetail.month == e_dt_global.month,
            models.PayrollDetail.year == e_dt_global.year
        ).first()

        # 2. รับค่าจาก Query Params (ลำดับความสำคัญสูงสุด)
        ind_start_query = request.query_params.get(f'start_{emp.id}')
        ind_end_query = request.query_params.get(f'end_{emp.id}')
        
        # 3. ตัดสินใจเลือกวันที่ที่จะใช้
        if ind_start_query and ind_end_query:
            # ใช้จาก URL (เมื่อมีการเลือกใหม่หน้าเว็บ)
            s_dt = datetime.strptime(ind_start_query, '%Y-%m-%d').date()
            e_dt = datetime.strptime(ind_end_query, '%Y-%m-%d').date()
        elif draft and draft.calc_start_date and draft.calc_end_date:
            # 🚩 ใช้จากที่เคยบันทึกไว้ในฐานข้อมูล (ระบบจะจำค่าได้)
            s_dt = draft.calc_start_date
            e_dt = draft.calc_end_date
        else:
            # ใช้ค่ามาตรฐานของเดือน
            s_dt = s_dt_global
            e_dt = e_dt_global

        # --- [A] คำนวณสถิติรายบุคคล (ใช้ s_dt และ e_dt ที่เลือกมาแล้ว) ---
        paid_days = 0 
        total_late_mins = 0
        total_early_mins = 0
        curr = s_dt
        
        while curr <= e_dt:
            day_name = curr.strftime('%a')
            is_holiday = curr in holiday_dates
            
            att = db.query(models.Attendance).filter(
                models.Attendance.employee_id == emp.id,
                models.Attendance.date == curr
            ).first()
            
            is_weekly_off = emp.weekly_off and day_name not in emp.weekly_off
            
            leave = db.query(models.LeaveRequest).filter(
                models.LeaveRequest.employee_id == emp.id,
                models.LeaveRequest.status == "Approved",
                models.LeaveRequest.start_date <= curr,
                models.LeaveRequest.end_date >= curr
            ).first()

            if att or is_holiday or is_weekly_off or leave:
                paid_days += 1
                if att:
                    total_late_mins += (att.late_minutes or 0)
                    total_early_mins += (att.early_minutes or 0)
            
            curr += timedelta(days=1)

        emp.calc_start_date = s_dt
        emp.calc_end_date = e_dt
        emp.paid_days = paid_days
        emp.late_minutes = total_late_mins
        emp.early_minutes = total_early_mins

        # --- [B] คำนวณตัวเลขเงิน ---
        base_salary_val = (emp.base_salary or 0)
        position_allowance_val = (emp.position_allowance or 0)
        base_calc = base_salary_val + position_allowance_val
        
        daily_rate = base_calc / 30
        real_income_total = round(daily_rate * paid_days, 2)

        # คำนวณ OT (ใช้เดือน/ปี ตามงวด)
        emp.approved_ot_pay = calculate_ot_pay(emp.id, e_dt_global.month, e_dt_global.year, db)

        # คำนวณเงินหัก สาย/ออกก่อน
        late_conf = settings.get('late')
        l_days = late_conf.divider_days if late_conf else 30
        l_hours = late_conf.divider_hours if late_conf else 8
        rate_min = base_calc / l_days / l_hours / 60 if l_days * l_hours > 0 else 0
        
        emp.calculated_late_deduction = round(rate_min * total_late_mins, 2)
        emp.calculated_early_deduction = round(rate_min * total_early_mins, 2)
        emp.calculated_absent_deduction = 0 
        emp.display_income = real_income_total 

        # --- [C] จัดการข้อมูลร่าง (Draft) ดึงค่าเงินที่เคยกรอกไว้ ---
        if draft:
            emp.draft_extra_income = draft.extra_income
            emp.draft_extra_deduction = draft.extra_deduction
            emp.draft_tax = draft.tax
            emp.draft_sso = draft.sso
            # ถ้าใน DB มีค่าหักสาย/ขาดงานที่เคยแก้ด้วยมือ ก็ดึงมาโชว์ (Optional)
            emp.calculated_late_deduction = draft.late_deduction
            emp.calculated_early_deduction = draft.early_deduction
            emp.calculated_absent_deduction = draft.absence_deduction
        else:
            emp.draft_extra_income = 0
            emp.draft_extra_deduction = 0
            emp.draft_tax = 0
            emp.draft_sso = min(base_salary_val * 0.05, 750)

    return templates.TemplateResponse("admin_payroll.html", {
        "request": request,
        "employees": employees,
        "start_date": start_date,
        "end_date": end_date,
        "texts": texts
    })
    
def get_payroll_settings(db: Session):
    """ดึงค่าการตั้งค่าทั้งหมดมาเป็น Dictionary เพื่อใช้งานง่าย"""
    settings = db.query(models.PayrollSetting).all()
    return {s.type_name: s for s in settings}

@app.post("/admin/process-payroll")
async def process_payroll(
    request: Request,
    action: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.Employee = Depends(get_current_active_user)
):
    if current_user.role != "Admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    form_data = await request.form()
    emp_ids = form_data.getlist("emp_ids")
    dt_end_global = datetime.strptime(end_date, '%Y-%m-%d').date()

    def parse_to_float_field(field_name, default_form=form_data):
        val = default_form.get(field_name, "0")
        if val and str(val).strip() != "":
            return float(str(val).replace(',', ''))
        return 0.0

    # If specific employees selected, process those (preserve per-employee date ranges)
    if emp_ids:
        for eid in emp_ids:
            ind_start = form_data.get(f"start_{eid}") or start_date
            ind_end = form_data.get(f"end_{eid}") or end_date
            dt_start = datetime.strptime(ind_start, '%Y-%m-%d').date()
            dt_end = datetime.strptime(ind_end, '%Y-%m-%d').date()

            user = db.query(models.Employee).filter(models.Employee.id == int(eid)).first()
            if not user:
                continue

            # remove old draft for this employee
            db.query(models.PayrollDetail).filter(
                models.PayrollDetail.employee_id == user.id,
                models.PayrollDetail.month == dt_end_global.month,
                models.PayrollDetail.year == dt_end_global.year
            ).delete()

            new_payroll = models.PayrollDetail(
                employee_id=user.id,
                month=dt_end_global.month,
                year=dt_end_global.year,
                calc_start_date=dt_start,
                calc_end_date=dt_end,
                salary=user.base_salary,
                position_allowance=user.position_allowance,
                ot_pay=parse_to_float_field(f"ot_{eid}"),
                sso=parse_to_float_field(f"sso_{eid}"),
                tax=parse_to_float_field(f"tax_{eid}"),
                late_deduction=parse_to_float_field(f"late_deduct_{eid}"),
                early_deduction=parse_to_float_field(f"early_deduct_{eid}"),
                absence_deduction=parse_to_float_field(f"absent_deduct_{eid}"),
                extra_income=parse_to_float_field(f"extra_income_{eid}"),
                extra_deduction=parse_to_float_field(f"extra_deduction_{eid}"),
                net_total=parse_to_float_field(f"net_{eid}"),
                status="Draft" if action == "save_draft" else "Finalized"
            )
            db.add(new_payroll)

            log_activity(
                db, current_user, "บันทึกเงินเดือน",
                f"คำนวณงวด {dt_end_global.month}/{dt_end_global.year} ของ {user.first_name} (ช่วง {ind_start} ถึง {ind_end})",
                request
            )

    else:
        # No specific selection: process all employees using per-employee fields from the form
        employees = db.query(models.Employee).all()
        dt_end = datetime.strptime(end_date, '%Y-%m-%d')

        for emp in employees:
            e_income = parse_to_float_field(f"extra_income_{emp.id}")
            e_deduction = parse_to_float_field(f"extra_deduction_{emp.id}")
            sso_val = parse_to_float_field(f"sso_{emp.id}")
            tax_val = parse_to_float_field(f"tax_{emp.id}")
            ot_pay_val = parse_to_float_field(f"ot_{emp.id}")
            late_val = parse_to_float_field(f"late_deduct_{emp.id}")
            early_val = parse_to_float_field(f"early_deduct_{emp.id}")
            absent_val = parse_to_float_field(f"absent_deduct_{emp.id}")
            net_val = parse_to_float_field(f"net_{emp.id}")

            # remove old draft
            db.query(models.PayrollDetail).filter(
                models.PayrollDetail.employee_id == emp.id,
                models.PayrollDetail.month == dt_end.month,
                models.PayrollDetail.year == dt_end.year
            ).delete()

            new_record = models.PayrollDetail(
                employee_id=emp.id,
                month=dt_end.month,
                year=dt_end.year,
                salary=emp.base_salary,
                position_allowance=emp.position_allowance,
                ot_pay=ot_pay_val,
                sso=sso_val,
                tax=tax_val,
                late_deduction=late_val,
                early_deduction=early_val,
                absence_deduction=absent_val,
                extra_income=e_income,
                extra_deduction=e_deduction,
                net_total=net_val,
                status="Draft" if action == "save_draft" else "Finalized"
            )
            db.add(new_record)

        # single log for full-run
        log_name = "บันทึกร่างเงินเดือน" if action == "save_draft" else "ยืนยันเงินเดือน"
        log_activity(db, current_user, log_name, f"งวด {dt_end.month}/{dt_end.year}", request)

    db.commit()

    if action == "save_draft":
        return RedirectResponse(url=f"/admin/calculate-payroll?start_date={start_date}&end_date={end_date}&msg=draft_saved", status_code=303)

    return RedirectResponse(url=f"/admin/payroll-summary?month={dt_end_global.month}&year={dt_end_global.year}", status_code=303)

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
    if month is None:
        month = now.month
    if year is None:
        year = now.year

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
                send_push_notification(admin.id, "📢 มีคำขอ OT ใหม่", f"พนักงาน {user.first_name if user else user_id} ยื่นขอ OT", db)
        except Exception as e:
            logger.info(f"❌ Notification Error: {e}")

        return RedirectResponse(url="/my-ot-requests?msg=success", status_code=303)

    except Exception as e:
        db.rollback()
        logger.info(f"🚩 Error: {e}")
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
            send_push_notification(
                ot_req.employee_id, 
                f"{icon} ผลการอนุมัติ OT", 
                f"คำขอ OT ของคุณ{msg_text}", 
                db
            )
        except Exception as e:
            logger.info(f"Push Notification Error: {e}")
            
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

@app.post("/admin/approve-all-requests")
async def approve_all_requests(db: Session = Depends(get_db)):
    pending_list = db.query(models.ManualAttendanceRequest).filter(
        models.ManualAttendanceRequest.status == "Pending"
    ).all()
    
    for req in pending_list:
        try:
            # ส่งค่า db เข้าไปตรงๆ ได้เลย ไม่ต้องผ่าน Depends อีกรอบ
            await perform_approval_logic(req.id, "Approved", "อนุมัติอัตโนมัติทั้งหมด", db)
        except Exception as e:
            logger.info(f"🚩 Error: {e}")
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
    if not month:
        month = now.month
    if not year:
        year = now.year

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