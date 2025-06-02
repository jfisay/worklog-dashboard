from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import mysql.connector
from dotenv import load_dotenv
from passlib.hash import bcrypt
import os

load_dotenv()

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="your-super-secret-key")
templates = Jinja2Templates(directory="templates")

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )

# --- AUTH HELPERS ---
def get_user(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username, password_hash FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user

def create_user(username, password):
    hashed = bcrypt.hash(password)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", (username, hashed))
    conn.commit()
    cursor.close()
    conn.close()

def is_logged_in(request: Request):
    return request.session.get("logged_in") == True

def login_required(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=302)

# --- ROUTES ---
@app.get("/signup", response_class=HTMLResponse)
def signup_form(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.post("/signup")
def signup(request: Request, username: str = Form(...), password: str = Form(...)):
    if get_user(username):
        return templates.TemplateResponse("signup.html", {"request": request, "error": "User already exists."})
    create_user(username, password)
    request.session["logged_in"] = True
    return RedirectResponse(url="/", status_code=302)

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = get_user(username)
    if user and bcrypt.verify(password, user[1]):
        request.session["logged_in"] = True
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials."})

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    if not is_logged_in(request):
        return RedirectResponse("/login", status_code=302)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT log_date, entry FROM daily_logs ORDER BY log_date DESC")
    logs = cursor.fetchall()
    cursor.close()
    conn.close()
    return templates.TemplateResponse("index.html", {"request": request, "logs": logs})

@app.get("/summaries", response_class=HTMLResponse)
def summaries(request: Request):
    if not is_logged_in(request):
        return RedirectResponse("/login", status_code=302)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT week_start, week_end, summary FROM weekly_summaries ORDER BY week_start DESC")
    summaries = cursor.fetchall()
    cursor.close()
    conn.close()
    return templates.TemplateResponse("summary.html", {"request": request, "summaries": summaries})