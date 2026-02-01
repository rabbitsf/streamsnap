from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User, Download
from app.services.downloader import delete_download

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/history", response_class=HTMLResponse)
async def history_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Display user's download history."""
    downloads = db.query(Download).filter(
        Download.user_id == user.id
    ).order_by(Download.created_at.desc()).all()

    # Check which files still exist
    for download in downloads:
        download.file_exists = Path(download.file_path).exists()

    return templates.TemplateResponse(
        "history.html",
        {
            "request": request,
            "user": user,
            "downloads": downloads,
        }
    )


@router.delete("/history/{download_id}", response_class=HTMLResponse)
async def delete_history_item(
    download_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a download from history (HTMX endpoint)."""
    download = db.query(Download).filter(
        Download.id == download_id,
        Download.user_id == user.id,
    ).first()

    if not download:
        raise HTTPException(status_code=404, detail="Download not found")

    # Delete the file
    delete_download(download.file_path, user.id)

    # Delete the database record
    db.delete(download)
    db.commit()

    # Return empty response to remove the row
    return ""


@router.post("/history/delete-bulk", response_class=HTMLResponse)
async def delete_bulk_history(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    ids: List[int] = Form(default=[]),
):
    """Delete multiple downloads from history (HTMX endpoint)."""
    if not ids:
        return ""

    downloads = db.query(Download).filter(
        Download.id.in_(ids),
        Download.user_id == user.id,
    ).all()

    for download in downloads:
        delete_download(download.file_path, user.id)
        db.delete(download)

    db.commit()

    # Return HX-Refresh header to reload the page
    return HTMLResponse(content="", headers={"HX-Refresh": "true"})


@router.post("/history/delete-all", response_class=HTMLResponse)
async def delete_all_history(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete all downloads from history (HTMX endpoint)."""
    downloads = db.query(Download).filter(
        Download.user_id == user.id,
    ).all()

    for download in downloads:
        delete_download(download.file_path, user.id)
        db.delete(download)

    db.commit()

    # Return HX-Refresh header to reload the page
    return HTMLResponse(content="", headers={"HX-Refresh": "true"})
