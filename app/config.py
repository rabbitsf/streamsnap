import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

# Database
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/streamsnap.db")

# Downloads directory
DOWNLOADS_DIR = BASE_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

# Security — fail hard if SECRET_KEY is missing or still the dev default
_DEV_SECRET = "dev-secret-key-change-in-production"
SECRET_KEY = os.getenv("SECRET_KEY", _DEV_SECRET)
if not SECRET_KEY or SECRET_KEY == _DEV_SECRET:
    raise RuntimeError(
        "SECRET_KEY environment variable must be set to a secure random value. "
        "Generate one with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8  # 8 hours

# Session cookie name
SESSION_COOKIE_NAME = "streamsnap_session"

# Registration — set ALLOW_REGISTRATION=true in .env to enable new account creation
ALLOW_REGISTRATION = os.getenv("ALLOW_REGISTRATION", "false").lower() == "true"

# Set SECURE_COOKIES=true only when running behind HTTPS (e.g. production)
SECURE_COOKIES = os.getenv("SECURE_COOKIES", "false").lower() == "true"
