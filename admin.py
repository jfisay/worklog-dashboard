from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
import os
from dotenv import load_dotenv
from utils import get_db_connection, get_user
from cryptography.fernet import Fernet


load_dotenv()
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY").encode()
fernet = Fernet(ENCRYPTION_KEY)


router = APIRouter()
templates = Jinja2Templates(directory="templates")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    if not request.session.get("is_admin"):
        return RedirectResponse("/admin-login", status_code=302)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT username, first_name, last_name, email, phone_number, is_active,
        (SELECT COUNT(*) FROM daily_logs WHERE daily_logs.username = users.username) AS log_count
        FROM users
    """)
    users = cursor.fetchall()
    cursor.close()
    conn.close()

    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request,
        "users": users
    })

@router.get("/admin-signup", response_class=HTMLResponse)
def admin_signup_form(request: Request):
    return templates.TemplateResponse("admin_signup.html", {"request": request})

@router.post("/admin-signup")
def admin_signup(request: Request,
                 first_name: str = Form(...),
                 last_name: str = Form(...),
                 email: str = Form(...),
                 phone_number: str = Form(...),
                 username: str = Form(...),
                 password: str = Form(...)):

    existing_user = get_user(username)
    if existing_user:
        return templates.TemplateResponse("admin_signup.html", {
            "request": request,
            "error": "Username already exists."
        })

    hashed_pw = pwd_context.hash(password)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (first_name, last_name, email, phone_number, username, password, is_admin)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (first_name, last_name, email, phone_number, username, hashed_pw, True))
    conn.commit()
    cursor.close()
    conn.close()

    request.session["username"] = username
    request.session["is_admin"] = True
    return RedirectResponse("/admin", status_code=302)

@router.get("/admin-login", response_class=HTMLResponse)
def admin_login_form(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request})


@router.post("/admin-login")
def admin_login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = get_user(username)
    if user and user["is_admin"]:
        if pwd_context.verify(password, user["password"]):  # ✅ verify hashed password
            request.session["username"] = username
            request.session["is_admin"] = True
            return RedirectResponse("/admin", status_code=302)
        else:
            print("DEBUG: Incorrect password")
    else:
        print("DEBUG: Admin user not found or not an admin")

    return templates.TemplateResponse("admin_login.html", {
        "request": request,
        "error": "Invalid admin credentials"
    })
    

@router.post("/admin-logout")
def admin_logout(request: Request):
    request.session.pop("is_admin", None)
    return RedirectResponse("/admin-login", status_code=302)

@router.get("/admin-home", response_class=HTMLResponse)
def admin_home(request: Request):
    return templates.TemplateResponse("admin_home.html", {"request": request})

@router.get("/admin/user-logs/{username}", response_class=HTMLResponse)
def view_user_logs(username: str, request: Request):
    if not request.session.get("is_admin"):
        return RedirectResponse("/admin-login", status_code=302)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT log_date, entry FROM daily_logs WHERE username = %s ORDER BY log_date DESC", (username,))
    logs_raw = cursor.fetchall()
    cursor.close()
    conn.close()

    logs = []
    for log in logs_raw:
        try:
            decrypted = fernet.decrypt(log['entry'].encode()).decode()
        except Exception:
            decrypted = "[Error decrypting log]"
        logs.append({
            "log_date": log["log_date"],
            "entry": decrypted
        })  

    return templates.TemplateResponse("admin_user_logs.html", {
        "request": request,
        "logs": logs,
        "username": username,
        "error":"user not found"
    })

@router.post("/admin/deactivate/{username}")
def deactivate_user(username: str, request: Request):
    if not request.session.get("is_admin"):
        return RedirectResponse("/admin-login", status_code=302)

    admin = request.session.get("username")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_active = FALSE WHERE username = %s", (username,))
    cursor.execute("INSERT INTO admin_logs (admin_username, action, target_user) VALUES (%s, %s, %s)",
                   (admin, "deactivated user", username))

    conn.commit()
    cursor.close()
    conn.close()

    return RedirectResponse("/admin", status_code=302)

@router.post("/admin/reactivate/{username}")
def reactivate_user(username: str, request: Request):
    if not request.session.get("is_admin"):
        return RedirectResponse("/admin-login", status_code=302)

    admin = request.session["username"]

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("UPDATE users SET is_active = TRUE WHERE username = %s", (username,))
    cursor.execute("INSERT INTO admin_logs (admin_username, action, target_user) VALUES (%s, %s, %s)",
                   (admin, "reactivated user", username))

    conn.commit()
    cursor.close()
    conn.close()

    return RedirectResponse("/admin", status_code=302)

@router.get("/admin/audit-logs", response_class=HTMLResponse)
def audit_logs(request: Request):
    if not request.session.get("is_admin"):
        return RedirectResponse("/admin-login", status_code=302)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT admin_username, action, target_user, timestamp 
        FROM admin_logs 
        ORDER BY timestamp DESC
    """)
    logs = cursor.fetchall()
    cursor.close()
    conn.close()

    return templates.TemplateResponse("admin_audit_logs.html", {
        "request": request,
        "logs": logs
    })