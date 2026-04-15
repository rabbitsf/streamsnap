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
from app.config import ACCESS_TOKEN_EXPIRE_MINUTES, SESSION_COOKIE_NAME
from app.database import get_db
from app.models import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


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
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=access_token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
    )
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(
    request: Request,
    user: User = Depends(get_optional_user),
):
    """Display registration page."""
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
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=access_token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
    )
    return response


@router.get("/logout")
async def logout():
    """Log out the current user."""
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response
