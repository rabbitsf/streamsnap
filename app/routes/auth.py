import time
from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import (
    authenticate_user,
    create_user,
    create_access_token,
    get_optional_user,
)
from app.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    SESSION_COOKIE_NAME,
    ALLOW_REGISTRATION,
    SECURE_COOKIES,
)
from app.database import get_db
from app.models import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Simple in-memory rate limiter for login attempts
_login_attempts: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 60   # seconds
_RATE_LIMIT_MAX = 10      # attempts per window per IP


def _is_rate_limited(ip: str) -> bool:
    """Return True if this IP has exceeded the login rate limit."""
    now = time.time()
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < _RATE_LIMIT_WINDOW]
    if len(_login_attempts[ip]) >= _RATE_LIMIT_MAX:
        return True
    _login_attempts[ip].append(now)
    return False


def _set_session_cookie(response, token: str):
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=SECURE_COOKIES,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    user: User = Depends(get_optional_user),
):
    """Display login page."""
    if user:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request, "login.html",
        {"error": None}
    )


@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """Handle login form submission."""
    ip = request.client.host if request.client else "unknown"
    if _is_rate_limited(ip):
        return templates.TemplateResponse(
            request, "login.html",
            {"error": "Too many login attempts. Please wait a minute."},
            status_code=429,
        )

    user = authenticate_user(db, username, password)
    if not user:
        return templates.TemplateResponse(
            request, "login.html",
            {"error": "Invalid username or password"},
            status_code=400,
        )

    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    response = RedirectResponse(url="/", status_code=303)
    _set_session_cookie(response, access_token)
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(
    request: Request,
    user: User = Depends(get_optional_user),
):
    """Display registration page."""
    if not ALLOW_REGISTRATION:
        return RedirectResponse(url="/login", status_code=303)
    if user:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request, "register.html",
        {"error": None}
    )


@router.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    """Handle registration form submission."""
    if not ALLOW_REGISTRATION:
        return RedirectResponse(url="/login", status_code=303)

    # Validate input
    if len(username) < 3:
        return templates.TemplateResponse(
            request, "register.html",
            {"error": "Username must be at least 3 characters"},
            status_code=400,
        )
    if len(password) < 6:
        return templates.TemplateResponse(
            request, "register.html",
            {"error": "Password must be at least 6 characters"},
            status_code=400,
        )
    if password != confirm_password:
        return templates.TemplateResponse(
            request, "register.html",
            {"error": "Passwords do not match"},
            status_code=400,
        )

    # Check if username exists
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        return templates.TemplateResponse(
            request, "register.html",
            {"error": "Username already taken"},
            status_code=400,
        )

    # Create user
    user = create_user(db, username, password)

    # Log them in
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    response = RedirectResponse(url="/", status_code=303)
    _set_session_cookie(response, access_token)
    return response


@router.get("/logout")
async def logout():
    """Log out the current user."""
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response
