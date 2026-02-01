from pathlib import Path
from typing import Optional

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
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Main download page."""
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "user": user}
    )


@router.post("/fetch-formats", response_class=HTMLResponse)
async def fetch_formats(
    request: Request,
    urls: str = Form(...),
    user: User = Depends(get_current_user),
):
    """Fetch available formats for one or more URLs (HTMX endpoint)."""
    # Parse URLs - split by newlines, commas, or spaces
    url_list = []
    for line in urls.replace(',', '\n').split('\n'):
        url = line.strip()
        if url:
            url_list.append(url)

    if not url_list:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "error": "Please enter at least one URL"}
        )

    # Fetch info for all URLs
    results = fetch_multiple_video_info(url_list)

    return templates.TemplateResponse(
        "partials/format_options.html",
        {
            "request": request,
            "results": results,
            "single_mode": len(results) == 1,
        }
    )


@router.post("/download", response_class=HTMLResponse)
async def start_download(
    request: Request,
    urls: str = Form(...),  # Comma or newline separated URLs
    download_type: str = Form(...),  # "video" or "audio"
    quality: str = Form("best"),
    format_id: Optional[str] = Form(None),
    audio_format: str = Form("mp3"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start downloads for one or more URLs (HTMX endpoint)."""
    # Parse URLs
    url_list = [u.strip() for u in urls.replace(',', '\n').split('\n') if u.strip()]

    if not url_list:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "error": "No URLs provided"}
        )

    download_records = []
    errors = []

    for url in url_list:
        try:
            if download_type == "audio":
                result = extract_audio(
                    url=url,
                    user_id=user.id,
                    audio_format=audio_format,
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

            # Save to history
            download_record = Download(
                user_id=user.id,
                url=url,
                title=result.title,
                filename=result.filename,
                file_path=result.file_path,
                file_size=result.file_size,
                format_type=format_type,
                quality=quality_label,
            )
            db.add(download_record)
            db.commit()
            db.refresh(download_record)
            download_records.append(download_record)

        except Exception as e:
            errors.append({"url": url, "error": str(e)})

    return templates.TemplateResponse(
        "partials/download_complete.html",
        {
            "request": request,
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
