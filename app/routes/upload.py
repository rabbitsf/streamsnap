from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User, Download
from app.services.downloader import (
    get_user_upload_dir,
    extract_audio_from_file,
    sanitize_filename,
)

router = APIRouter(prefix="/upload")
templates = Jinja2Templates(directory="app/templates")

ALLOWED_VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv",
    ".m4v", ".mpg", ".mpeg", ".3gp", ".ts",
}
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB


@router.post("/extract", response_class=HTMLResponse)
async def upload_and_extract(
    request: Request,
    files: list[UploadFile] = File(...),
    audio_format: str = Form("mp3"),
    rename_mode: str = Form("original"),
    custom_names: Optional[list[str]] = Form(None),
    batch_prefix: str = Form(""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload video files, extract audio, clean up sources — single step."""
    upload_dir = get_user_upload_dir(user.id)
    names = custom_names or []
    download_records = []
    errors = []

    for i, file in enumerate(files):
        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_VIDEO_EXTENSIONS:
            errors.append({"url": "local upload", "error": f"{file.filename}: unsupported format ({ext})"})
            continue

        # Save to temp dir with collision-safe name
        safe_name = f"{uuid4().hex}_{sanitize_filename(Path(file.filename).name)}"
        dest = upload_dir / safe_name

        total_size = 0
        size_exceeded = False
        try:
            with open(dest, "wb") as f:
                while True:
                    chunk = await file.read(1024 * 1024)  # 1 MB chunks
                    if not chunk:
                        break
                    total_size += len(chunk)
                    if total_size > MAX_FILE_SIZE:
                        size_exceeded = True
                        break
                    f.write(chunk)
        except Exception as e:
            dest.unlink(missing_ok=True)
            errors.append({"url": "local upload", "error": f"{file.filename}: upload failed ({e})"})
            continue

        if size_exceeded:
            dest.unlink(missing_ok=True)
            errors.append({"url": "local upload", "error": f"{file.filename}: exceeds 2 GB limit"})
            continue

        # Determine output name based on rename_mode
        output_name = None
        if rename_mode == "individual" and i < len(names) and names[i].strip():
            output_name = names[i].strip()
        elif rename_mode == "batch" and batch_prefix:
            output_name = f"{batch_prefix} {i + 1:02d}"

        # Extract audio
        result = extract_audio_from_file(
            source_path=str(dest),
            user_id=user.id,
            audio_format=audio_format,
            output_filename=output_name,
        )

        # Always clean up source file
        dest.unlink(missing_ok=True)

        if not result.success:
            errors.append({"url": "local upload", "error": result.error or "Extraction failed"})
            continue

        # Create DB record
        record = Download(
            user_id=user.id,
            url="local upload",
            title=result.title,
            filename=result.filename,
            file_path=result.file_path,
            file_size=result.file_size,
            format_type="audio",
            quality=audio_format.upper(),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        download_records.append(record)

    return templates.TemplateResponse(
        request, "partials/download_complete.html",
        {
            "downloads": download_records,
            "errors": errors,
            "single_mode": len(files) == 1,
        },
    )
