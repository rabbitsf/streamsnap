import ipaddress
import logging
import re
import socket
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User, Download
from app.services.downloader import (
    fetch_video_info,
    fetch_multiple_video_info,
    download_video,
    extract_audio,
    get_user_base_dir,
    rename_download_file,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)

# Input allowlists
ALLOWED_AUDIO_FORMATS = {"mp3", "m4a", "wav"}
ALLOWED_AUDIO_QUALITIES = {"128", "192", "320"}
ALLOWED_QUALITIES = {"best", "2160p", "1440p", "1080p", "720p", "480p", "360p", "240p"}
ALLOWED_DOWNLOAD_TYPES = {"video", "audio"}
_FORMAT_ID_RE = re.compile(r'^[a-zA-Z0-9_\-+/]+$')

# Networks blocked to prevent SSRF
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _is_safe_url(url: str) -> bool:
    """Return False for non-HTTP(S) URLs and private/loopback IP targets."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        ip = ipaddress.ip_address(socket.gethostbyname(hostname))
        for network in _BLOCKED_NETWORKS:
            try:
                if ip in network:
                    return False
            except TypeError:
                pass
        return True
    except Exception:
        return False


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Main download page."""
    return templates.TemplateResponse(
        request, "index.html",
        {"user": user}
    )


@router.post("/fetch-formats", response_class=HTMLResponse)
async def fetch_formats(
    request: Request,
    urls: str = Form(...),
    user: User = Depends(get_current_user),
):
    """Fetch available formats for one or more URLs (HTMX endpoint)."""
    url_list = []
    for line in urls.replace(',', '\n').split('\n'):
        url = line.strip()
        if url:
            url_list.append(url)

    if not url_list:
        return templates.TemplateResponse(
            request, "partials/error.html",
            {"error": "Please enter at least one URL"}
        )

    # SSRF protection
    for url in url_list:
        if not _is_safe_url(url):
            return templates.TemplateResponse(
                request, "partials/error.html",
                {"error": "Invalid or disallowed URL"}
            )

    results = fetch_multiple_video_info(url_list)

    return templates.TemplateResponse(
        request, "partials/format_options.html",
        {
            "results": results,
            "single_mode": len(results) == 1,
        }
    )


@router.post("/download", response_class=HTMLResponse)
async def start_download(
    request: Request,
    urls: str = Form(...),
    download_type: str = Form(...),
    quality: str = Form("best"),
    format_id: Optional[str] = Form(None),
    audio_format: str = Form("mp3"),
    audio_quality: str = Form("192"),
    rename_mode: str = Form("original"),
    custom_names: Optional[list[str]] = Form(None),
    batch_prefix: str = Form(""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start downloads for one or more URLs (HTMX endpoint)."""
    # Validate enumerated inputs
    if download_type not in ALLOWED_DOWNLOAD_TYPES:
        return templates.TemplateResponse(
            request, "partials/error.html",
            {"error": "Invalid download type"}
        )
    if audio_format not in ALLOWED_AUDIO_FORMATS:
        return templates.TemplateResponse(
            request, "partials/error.html",
            {"error": "Invalid audio format"}
        )
    if audio_quality not in ALLOWED_AUDIO_QUALITIES:
        return templates.TemplateResponse(
            request, "partials/error.html",
            {"error": "Invalid audio quality"}
        )
    if quality not in ALLOWED_QUALITIES:
        return templates.TemplateResponse(
            request, "partials/error.html",
            {"error": "Invalid quality selection"}
        )
    if format_id and not _FORMAT_ID_RE.match(format_id):
        return templates.TemplateResponse(
            request, "partials/error.html",
            {"error": "Invalid format ID"}
        )

    # Parse URLs
    url_list = [u.strip() for u in urls.replace(',', '\n').split('\n') if u.strip()]

    if not url_list:
        return templates.TemplateResponse(
            request, "partials/error.html",
            {"error": "No URLs provided"}
        )

    # SSRF protection
    for url in url_list:
        if not _is_safe_url(url):
            return templates.TemplateResponse(
                request, "partials/error.html",
                {"error": "Invalid or disallowed URL"}
            )

    name_list = [n.strip() for n in (custom_names or []) if n.strip()]

    download_records = []
    errors = []

    for idx, url in enumerate(url_list):
        try:
            if download_type == "audio":
                result = extract_audio(
                    url=url,
                    user_id=user.id,
                    audio_format=audio_format,
                    audio_quality=audio_quality,
                )
                format_type = "audio"
                quality_label = audio_format.upper()
            else:
                result = download_video(
                    url=url,
                    user_id=user.id,
                    quality=quality,
                    format_id=format_id if format_id else None,
                )
                format_type = "video"
                quality_label = quality

            if not result.success:
                errors.append({"url": url, "error": result.error or "Download failed"})
                continue

            # Apply rename if requested
            final_path = result.file_path
            final_filename = result.filename
            final_title = result.title

            if rename_mode == "individual" and idx < len(name_list) and name_list[idx]:
                new_path = rename_download_file(result.file_path, name_list[idx], user.id)
                if new_path:
                    final_path = new_path
                    final_filename = Path(new_path).name
                    final_title = name_list[idx]
            elif rename_mode == "batch" and batch_prefix:
                new_name = f"{batch_prefix} {idx + 1:02d}"
                new_path = rename_download_file(result.file_path, new_name, user.id)
                if new_path:
                    final_path = new_path
                    final_filename = Path(new_path).name
                    final_title = new_name

            # Save to history
            download_record = Download(
                user_id=user.id,
                url=url,
                title=final_title,
                filename=final_filename,
                file_path=final_path,
                file_size=result.file_size,
                format_type=format_type,
                quality=quality_label,
            )
            db.add(download_record)
            db.commit()
            db.refresh(download_record)
            download_records.append(download_record)

        except Exception as e:
            logger.error("Unexpected error downloading %s for user %s: %s", url, user.id, e, exc_info=True)
            errors.append({"url": url, "error": "An unexpected error occurred. Please try again."})

    return templates.TemplateResponse(
        request, "partials/download_complete.html",
        {
            "downloads": download_records,
            "errors": errors,
            "single_mode": len(url_list) == 1,
        }
    )


@router.get("/file/{download_id}")
async def serve_file(
    download_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Serve a downloaded file to the user."""
    download = db.query(Download).filter(
        Download.id == download_id,
        Download.user_id == user.id,
    ).first()

    if not download:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = Path(download.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File no longer exists")

    # Verify file is in user's directory (security check)
    user_base_dir = get_user_base_dir(user.id)
    try:
        file_path.resolve().relative_to(user_base_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    return FileResponse(
        path=file_path,
        filename=download.filename,
        media_type="application/octet-stream",
    )
