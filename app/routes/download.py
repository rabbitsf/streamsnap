import ipaddress
import logging
import re
import socket
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request, Form
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.background import BackgroundTask
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User, Download
from app.services.downloader import (
    fetch_video_info,
    fetch_multiple_video_info,
    fetch_playlist_urls,
    download_video,
    extract_audio,
    create_job_dir,
    cleanup_job_dir,
    rename_download_file,
    resolve_output_name,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)

# Input allowlists
ALLOWED_AUDIO_FORMATS = {"mp3", "m4a", "wav"}
ALLOWED_AUDIO_QUALITIES = {"128", "192", "320"}
ALLOWED_QUALITIES = {"best", "2160p", "1440p", "1080p", "720p", "480p", "360p", "240p"}
ALLOWED_DOWNLOAD_TYPES = {"video", "audio"}
PLAYLIST_BATCH_SIZE = 15  # URLs per copy-able batch in the playlist lister
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
            logger.warning("Rejected URL %r: scheme %r not allowed", url, parsed.scheme)
            return False
        hostname = parsed.hostname
        if not hostname:
            logger.warning("Rejected URL %r: no hostname", url)
            return False
        try:
            ip = ipaddress.ip_address(socket.gethostbyname(hostname))
        except socket.gaierror as e:
            logger.warning("Rejected URL %r: DNS lookup for %s failed: %s", url, hostname, e)
            return False
        for network in _BLOCKED_NETWORKS:
            try:
                if ip in network:
                    logger.warning("Rejected URL %r: %s resolves to blocked address %s", url, hostname, ip)
                    return False
            except TypeError:
                pass
        return True
    except Exception as e:
        logger.warning("Rejected URL %r: %s", url, e, exc_info=True)
        return False


# Zero-width characters that clipboards can prepend to copied URLs (BOM, ZWSP, ZWNJ, ZWJ, word joiner)
_INVISIBLE_CHARS = "﻿​‌‍⁠"


def _parse_urls(raw: str) -> list[str]:
    """Split comma/newline-separated URL input, stripping whitespace and invisible characters."""
    urls = []
    for line in raw.replace(',', '\n').split('\n'):
        url = line.strip().strip(_INVISIBLE_CHARS).strip()
        if url:
            urls.append(url)
    return urls


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    url: Optional[str] = None,
    user: User = Depends(get_current_user),
):
    """Main download page. `?url=` prefills the URL box (History → "Again")."""
    return templates.TemplateResponse(
        request, "index.html",
        {"user": user, "prefill_url": url}
    )


@router.post("/fetch-formats", response_class=HTMLResponse)
async def fetch_formats(
    request: Request,
    urls: str = Form(...),
    user: User = Depends(get_current_user),
):
    """Fetch available formats for one or more URLs (HTMX endpoint)."""
    url_list = _parse_urls(urls)

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


@router.post("/playlist-urls", response_class=HTMLResponse)
async def playlist_urls(
    request: Request,
    playlist_url: str = Form(...),
    user: User = Depends(get_current_user),
):
    """List every video URL in a playlist so the user can paste them in batches (HTMX endpoint)."""
    url_list = _parse_urls(playlist_url)

    if len(url_list) != 1:
        return templates.TemplateResponse(
            request, "partials/error.html",
            {"error": "Please enter exactly one playlist URL"}
        )

    url = url_list[0]
    if not _is_safe_url(url):
        return templates.TemplateResponse(
            request, "partials/error.html",
            {"error": "Invalid or disallowed URL"}
        )

    try:
        playlist = fetch_playlist_urls(url)
    except Exception as e:
        logger.error("Failed to list playlist %s for user %s: %s", url, user.id, e, exc_info=True)
        return templates.TemplateResponse(
            request, "partials/error.html",
            {"error": "Could not read the playlist. Please check the URL."}
        )

    if not playlist.urls:
        return templates.TemplateResponse(
            request, "partials/error.html",
            {"error": "No videos found — is this a playlist link (with list=...)?"}
        )

    return templates.TemplateResponse(
        request, "partials/playlist_urls.html",
        {"playlist": playlist, "batch_size": PLAYLIST_BATCH_SIZE}
    )


def _json_error(message: str, status_code: int = 400) -> JSONResponse:
    """Error body for the fetch()-driven save endpoints (read by static/js/save.js)."""
    return JSONResponse({"error": message}, status_code=status_code)


def stream_and_cleanup(file_path: str, filename: str, job_dir: Path, user_id: int) -> FileResponse:
    """
    Canonical way to hand a finished file to the browser without keeping it:
    stream it as an attachment, then delete the request's job dir.
    Used by /download and /upload/extract.
    """
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream",
        background=BackgroundTask(cleanup_job_dir, job_dir, user_id),
    )


@router.post("/download")
async def start_download(
    urls: str = Form(...),
    item_index: int = Form(0),
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
    """
    Download ONE item of a batch and stream it to the browser (no copy kept on the server).

    The browser (static/js/save.js) calls this once per URL with `item_index`,
    sending the whole form each time so rename rules resolve server-side.
    """
    # Validate enumerated inputs
    if download_type not in ALLOWED_DOWNLOAD_TYPES:
        return _json_error("Invalid download type")
    if audio_format not in ALLOWED_AUDIO_FORMATS:
        return _json_error("Invalid audio format")
    if audio_quality not in ALLOWED_AUDIO_QUALITIES:
        return _json_error("Invalid audio quality")
    if quality not in ALLOWED_QUALITIES:
        return _json_error("Invalid quality selection")
    if format_id and not _FORMAT_ID_RE.match(format_id):
        return _json_error("Invalid format ID")

    url_list = _parse_urls(urls)
    if not url_list:
        return _json_error("No URLs provided")
    if not 0 <= item_index < len(url_list):
        return _json_error("Invalid item index")

    url = url_list[item_index]
    if not _is_safe_url(url):
        return _json_error("Invalid or disallowed URL")

    job_dir = create_job_dir(user.id)
    try:
        if download_type == "audio":
            result = await run_in_threadpool(
                extract_audio,
                url=url, user_id=user.id, job_dir=job_dir,
                audio_format=audio_format, audio_quality=audio_quality,
            )
            format_type = "audio"
            quality_label = audio_format.upper()
        else:
            result = await run_in_threadpool(
                download_video,
                url=url, user_id=user.id, job_dir=job_dir,
                quality=quality, format_id=format_id or None,
            )
            format_type = "video"
            quality_label = quality

        if not result.success or not result.file_path or not Path(result.file_path).exists():
            cleanup_job_dir(job_dir, user.id)
            return _json_error(result.error or "Download failed", status_code=502)

        final_path = result.file_path
        final_title = result.title
        new_name = resolve_output_name(rename_mode, custom_names, batch_prefix, item_index)
        if new_name:
            renamed = rename_download_file(result.file_path, new_name, user.id)
            if renamed:
                final_path = renamed
                final_title = new_name
        final_filename = Path(final_path).name

        # History is a log only — the file itself is not kept on the server
        db.add(Download(
            user_id=user.id,
            url=url,
            title=final_title,
            filename=final_filename,
            file_path="",
            file_size=result.file_size,
            format_type=format_type,
            quality=quality_label,
        ))
        db.commit()
    except Exception as e:
        cleanup_job_dir(job_dir, user.id)
        logger.error("Unexpected error downloading %s for user %s: %s", url, user.id, e, exc_info=True)
        return _json_error("An unexpected error occurred. Please try again.", status_code=500)

    return stream_and_cleanup(final_path, final_filename, job_dir, user.id)
