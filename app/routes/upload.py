from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, UploadFile, File
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User, Download
from app.routes.download import _json_error, stream_and_cleanup
from app.services.downloader import (
    create_job_dir,
    cleanup_job_dir,
    extract_audio_from_file,
    resolve_output_name,
    sanitize_filename,
)

router = APIRouter(prefix="/upload")

ALLOWED_VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv",
    ".m4v", ".mpg", ".mpeg", ".3gp", ".ts",
}
ALLOWED_AUDIO_FORMATS = {"mp3", "m4a", "wav"}
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB


@router.post("/extract")
async def upload_and_extract(
    file: UploadFile = File(...),
    item_index: int = Form(0),
    audio_format: str = Form("mp3"),
    rename_mode: str = Form("original"),
    custom_names: Optional[list[str]] = Form(None),
    batch_prefix: str = Form(""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload ONE video file, extract its audio and stream the audio back (nothing kept on the server).

    The browser (static/js/save.js) calls this once per selected file with `item_index`,
    sending the rename fields each time so names resolve server-side.
    """
    if audio_format not in ALLOWED_AUDIO_FORMATS:
        return _json_error("Invalid audio format")

    original_name = file.filename or "upload"
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        return _json_error(f"{original_name}: unsupported format ({ext})")

    job_dir = create_job_dir(user.id)
    try:
        source = job_dir / sanitize_filename(Path(original_name).name)

        total_size = 0
        with open(source, "wb") as f:
            while chunk := await file.read(1024 * 1024):  # 1 MB chunks
                total_size += len(chunk)
                if total_size > MAX_FILE_SIZE:
                    cleanup_job_dir(job_dir, user.id)
                    return _json_error(f"{original_name}: exceeds 2 GB limit", status_code=413)
                f.write(chunk)

        output_name = resolve_output_name(rename_mode, custom_names, batch_prefix, item_index)
        result = await run_in_threadpool(
            extract_audio_from_file,
            source_path=str(source),
            user_id=user.id,
            job_dir=job_dir,
            audio_format=audio_format,
            output_filename=output_name,
        )
        source.unlink(missing_ok=True)

        if not result.success or not result.file_path:
            cleanup_job_dir(job_dir, user.id)
            return _json_error(result.error or "Extraction failed", status_code=502)

        # History is a log only — the file itself is not kept on the server
        db.add(Download(
            user_id=user.id,
            url="local upload",
            title=result.title,
            filename=result.filename,
            file_path="",
            file_size=result.file_size,
            format_type="audio",
            quality=audio_format.upper(),
        ))
        db.commit()
    except Exception:
        cleanup_job_dir(job_dir, user.id)
        raise

    return stream_and_cleanup(result.file_path, result.filename, job_dir, user.id)
