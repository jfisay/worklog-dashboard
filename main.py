from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from starlette.middleware.sessions import SessionMiddleware
from weekly_summary import fetch_weekly_logs, summarize_logs, save_summary_to_db
import mysql.connector
from cryptography.fernet import Fernet
import base64
import os
import re  
from dotenv import load_dotenv
from admin import router as admin_router
from utils import get_db_connection, is_logged_in
from admin import router as admin_router
from itsdangerous import URLSafeTimedSerializer

load_dotenv()

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY").encode()
fernet = Fernet(ENCRYPTION_KEY)

serializer = URLSafeTimedSerializer(os.getenv("SECRET_KEY"))



app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET"))

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")



def get_user(username):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    if "username" not in request.session:
        return templates.TemplateResponse("home.html", {"request": request})

    username = request.session["username"]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT log_date, entry FROM daily_logs WHERE username = %s ORDER BY log_date DESC",
        (username,)
    )
    logs_encrypted = cursor.fetchall()
    cursor.close()
    conn.close()

    # Decrypt each log entry
    logs = []
    for log_date, encrypted_entry in logs_encrypted:
        try:
            decrypted_entry = fernet.decrypt(encrypted_entry.encode()).decode()
        except Exception:
            decrypted_entry = "[Error decrypting entry]"
        logs.append((log_date, decrypted_entry))

    return templates.TemplateResponse("index.html", {"request": request, "logs": logs})
@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = get_user(username)
    
    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "No user found with that username."
        })
    
    if not user["is_active"]:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "This account is inactive. Please contact an administrator."
        })

    if not pwd_context.verify(password, user["password"]):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Incorrect password."
        })

    # Success
    request.session["username"] = username
    return RedirectResponse("/", status_code=302)
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

def create_user(username, hashed_password, first_name, last_name, email, phone_number):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO users (username, password, first_name, last_name, email, phone_number)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (username, hashed_password, first_name, last_name, email, phone_number)
    )
    conn.commit()
    cursor.close()
    conn.close()
@app.post("/signup")
def signup(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    phone_number: str = Form(...),
    username: str = Form(...),
    password: str = Form(...)
):
    # Password validation...
    if (len(password) < 8 or
        not re.search(r"[A-Z]", password) or
        not re.search(r"[a-z]", password) or
        not re.search(r"\d", password) or
        not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password)):
        return templates.TemplateResponse("signup.html", {
            "request": request,
            "error": "Password must be at least 8 characters long and include an uppercase letter, lowercase letter, number, and special character."
        })

    # Check for existing user
    existing_user = get_user(username)
    if existing_user:
        return templates.TemplateResponse("home.html", {
            "request": request,
            "error": "Username already exists."
        })

    # Hash password and create user
    hashed_pw = pwd_context.hash(password)
    create_user(username, hashed_pw, first_name, last_name, email, phone_number)
    request.session["username"] = username
    return RedirectResponse("/", status_code=302)
@app.get("/signup")
def signup_form(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)

@app.get("/summaries", response_class=HTMLResponse)
def view_summaries(request: Request):
    if "username" not in request.session:
        return RedirectResponse("/login", status_code=302)

    username = request.session["username"]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT week_start, week_end, summary FROM weekly_summaries WHERE username = %s ORDER BY week_start DESC",
        (username,)
    )
    encrypted_summaries = cursor.fetchall()
    cursor.close()
    conn.close()

    summaries = []
    for start, end, encrypted_summary in encrypted_summaries:
        try:
            decrypted_summary = fernet.decrypt(encrypted_summary.encode()).decode()
        except Exception:
            decrypted_summary = "[Error decrypting summary]"
        summaries.append((start, end, decrypted_summary))

    return templates.TemplateResponse("summary.html", {
        "request": request,
        "summaries": summaries
    })
@app.post("/log")
def add_log(request: Request, log_date: str = Form(...), entry: str = Form(...)):
    if "username" not in request.session:
        return RedirectResponse("/login", status_code=302)

    username = request.session["username"]
    
    # Encrypt the entry
    encrypted_entry = fernet.encrypt(entry.encode()).decode()

    # Save to DB
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO daily_logs (log_date, entry, username) VALUES (%s, %s, %s)",
        (log_date, encrypted_entry, username)
    )
    conn.commit()
    cursor.close()
    conn.close()

    return RedirectResponse("/", status_code=302)
@app.post("/submit-summary")
def submit_summary(request: Request, week_start: str = Form(...), week_end: str = Form(...), summary: str = Form(...)):
    if "username" not in request.session:
        return RedirectResponse("/login", status_code=302)

    username = request.session["username"]
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO weekly_summaries (week_start, week_end, summary, username)
        VALUES (%s, %s, %s, %s)
    """, (week_start, week_end, summary, username))

    conn.commit()
    cursor.close()
    conn.close()

    return RedirectResponse("/summaries", status_code=302)


@app.post("/generate-summary")
def generate_summary(request: Request):
    # Check if user is logged in
    username = request.session.get("username")
    if not username:
        return RedirectResponse("/login", status_code=302)

    # Calculate current week's date range
    start_of_week = datetime.today() - timedelta(days=datetime.today().weekday())
    end_of_week = start_of_week + timedelta(days=6)

    # Fetch logs for the week
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT log_date, entry FROM daily_logs
        WHERE log_date BETWEEN %s AND %s AND username = %s
        ORDER BY log_date ASC
    """, (start_of_week.date(), end_of_week.date(), username))
    logs = cursor.fetchall()
    cursor.close()
    conn.close()

    if not logs:
        return RedirectResponse("/", status_code=302)

    # Decrypt logs and prepare text for summarization
    log_text = "\n".join([
        f"{log[0]}: {fernet.decrypt(log[1].encode()).decode(errors='ignore')}"
        for log in logs
    ])
    summary_text = summarize_logs(log_text)

    # Encrypt the summary and store it
    encrypted_summary = fernet.encrypt(summary_text.encode()).decode()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO weekly_summaries (week_start, week_end, summary, username)
        VALUES (%s, %s, %s, %s)
    """, (start_of_week.date(), end_of_week.date(), encrypted_summary, username))
    conn.commit()
    cursor.close()
    conn.close()

    return RedirectResponse("/summaries", status_code=302)

@app.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_form(request: Request):
    return templates.TemplateResponse("forgot_password.html", {"request": request})



@app.post("/forgot-password")
def send_reset_email(request: Request, identifier: str = Form(...)):
    user = get_user(identifier)
    if not user:
        return templates.TemplateResponse("forgot_password.html", {
            "request": request,
            "error": "User not found."
        })

    token = serializer.dumps(user["username"], salt="reset-password")
    reset_link = f"http://localhost:8000/reset-password/{token}" #This might chage when getting deployed
    # ⛔ Replace this with actual email-sending logic
    print("Send this reset link:", reset_link)

    return templates.TemplateResponse("forgot_password.html", {
        "request": request,
        "message": "Reset link sent. Check your email."
    })

@app.get("/reset-password/{token}", response_class=HTMLResponse)
def reset_form(request: Request, token: str):
    return templates.TemplateResponse("reset_password.html", {
        "request": request,
        "token": token
    })

@app.post("/reset-password")
def process_reset(request: Request, token: str = Form(...), new_password: str = Form(...)):
    try:
        username = serializer.loads(token, max_age=3600)
    except Exception:
        return templates.TemplateResponse("reset_password.html", {
            "request": request,
            "error": "Reset link expired or invalid.",
            "token": token
        })

    hashed = pwd_context.hash(new_password)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET password = %s WHERE username = %s", (hashed, username))
    conn.commit()
    cursor.close()
    conn.close()

    return RedirectResponse("/login", status_code=302)
# The Admin Router
#app.include_router(admin_router, prefix="/admin-home")
app.include_router(admin_router)