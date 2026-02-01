"""
Canonical implementation for all video/audio downloading operations.

All routes that need to download content MUST use this service.
This is the single source of truth for yt-dlp operations.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yt_dlp

from app.config import DOWNLOADS_DIR


@dataclass
class FormatInfo:
    """Information about an available format."""
    format_id: str
    ext: str
    resolution: Optional[str]
    filesize: Optional[int]
    vcodec: Optional[str]
    acodec: Optional[str]
    quality_label: str
    is_audio_only: bool


@dataclass
class VideoInfo:
    """Information about a video."""
    url: str
    title: str
    duration: Optional[int]
    thumbnail: Optional[str]
    uploader: Optional[str]
    formats: list[FormatInfo]


@dataclass
class DownloadResult:
    """Result of a download operation."""
    success: bool
    file_path: Optional[str]
    filename: Optional[str]
    title: Optional[str]
    file_size: Optional[int]
    error: Optional[str]


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename for safe storage."""
    # Remove or replace problematic characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filename = filename.strip('. ')
    # Limit length
    if len(filename) > 200:
        filename = filename[:200]
    return filename or "download"


def get_user_download_dir(user_id: int, media_type: str = None) -> Path:
    """
    Get or create the download directory for a user.

    Args:
        user_id: The user's ID
        media_type: "video" or "audio" for separate folders, None for base dir
    """
    user_dir = DOWNLOADS_DIR / str(user_id)
    if media_type == "video":
        user_dir = user_dir / "videos"
    elif media_type == "audio":
        user_dir = user_dir / "audios"
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def get_user_base_dir(user_id: int) -> Path:
    """Get the base download directory for a user (for security checks)."""
    return DOWNLOADS_DIR / str(user_id)


def fetch_video_info(url: str) -> VideoInfo:
    """
    Fetch available formats and info for a URL.

    This is the canonical method to get video information.
    All format selection UI must use this.
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    formats = []
    seen_qualities = set()

    # Process video formats
    for f in info.get('formats', []):
        format_id = f.get('format_id', '')
        ext = f.get('ext', '')
        height = f.get('height')
        vcodec = f.get('vcodec', 'none')
        acodec = f.get('acodec', 'none')
        filesize = f.get('filesize') or f.get('filesize_approx')

        is_audio_only = vcodec == 'none' and acodec != 'none'

        if is_audio_only:
            # Audio format
            abr = f.get('abr', 0)
            quality_label = f"{int(abr)}kbps {ext}" if abr else f"audio {ext}"
            resolution = None
        elif height:
            # Video format
            resolution = f"{height}p"
            quality_label = resolution
        else:
            continue

        # Skip duplicates
        key = (quality_label, ext, is_audio_only)
        if key in seen_qualities:
            continue
        seen_qualities.add(key)

        formats.append(FormatInfo(
            format_id=format_id,
            ext=ext,
            resolution=resolution,
            filesize=filesize,
            vcodec=vcodec if vcodec != 'none' else None,
            acodec=acodec if acodec != 'none' else None,
            quality_label=quality_label,
            is_audio_only=is_audio_only,
        ))

    # Sort: video by resolution (desc), then audio
    def sort_key(f: FormatInfo):
        if f.is_audio_only:
            return (1, 0)
        if f.resolution:
            try:
                return (0, -int(f.resolution.replace('p', '')))
            except ValueError:
                return (0, 0)
        return (0, 0)

    formats.sort(key=sort_key)

    return VideoInfo(
        url=url,
        title=info.get('title', 'Unknown'),
        duration=info.get('duration'),
        thumbnail=info.get('thumbnail'),
        uploader=info.get('uploader'),
        formats=formats,
    )


def download_video(
    url: str,
    user_id: int,
    quality: str = "best",
    format_id: Optional[str] = None,
) -> DownloadResult:
    """
    Download a video with specified quality.

    This is the canonical method for video downloads.
    All download triggers must call this.

    Args:
        url: The video URL
        user_id: The user's ID (for directory isolation)
        quality: Quality preference ("best", "1080p", "720p", etc.)
        format_id: Specific format ID to download
    """
    user_dir = get_user_download_dir(user_id, media_type="video")

    # Build format selector
    if format_id:
        format_selector = format_id + "+bestaudio/best"
    elif quality == "best":
        format_selector = "bestvideo+bestaudio/best"
    else:
        # Try to match quality like "1080p" or "720p"
        height = quality.replace('p', '')
        format_selector = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"

    ydl_opts = {
        'format': format_selector,
        'outtmpl': str(user_dir / '%(title)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4',
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

            # Get the actual filename
            if info.get('requested_downloads'):
                filepath = info['requested_downloads'][0]['filepath']
            else:
                # Fallback
                title = sanitize_filename(info.get('title', 'video'))
                ext = info.get('ext', 'mp4')
                filepath = str(user_dir / f"{title}.{ext}")

            file_path = Path(filepath)
            file_size = file_path.stat().st_size if file_path.exists() else None

            return DownloadResult(
                success=True,
                file_path=str(file_path),
                filename=file_path.name,
                title=info.get('title'),
                file_size=file_size,
                error=None,
            )
    except Exception as e:
        return DownloadResult(
            success=False,
            file_path=None,
            filename=None,
            title=None,
            file_size=None,
            error=str(e),
        )


def extract_audio(
    url: str,
    user_id: int,
    audio_format: str = "mp3",
    audio_quality: str = "192",
) -> DownloadResult:
    """
    Extract audio from a video URL.

    This is the canonical method for audio extraction.
    All audio download triggers must call this.

    Args:
        url: The video URL
        user_id: The user's ID (for directory isolation)
        audio_format: Output format ("mp3", "m4a", "wav", etc.)
        audio_quality: Bitrate in kbps ("128", "192", "320")
    """
    user_dir = get_user_download_dir(user_id, media_type="audio")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': str(user_dir / '%(title)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': audio_format,
            'preferredquality': audio_quality,
        }],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

            # The filename will have the audio extension after post-processing
            title = sanitize_filename(info.get('title', 'audio'))
            filepath = user_dir / f"{title}.{audio_format}"

            # yt-dlp might sanitize the title differently
            if not filepath.exists():
                # Try to find the file
                for f in user_dir.iterdir():
                    if f.suffix == f".{audio_format}" and f.stem.startswith(title[:20]):
                        filepath = f
                        break

            file_size = filepath.stat().st_size if filepath.exists() else None

            return DownloadResult(
                success=True,
                file_path=str(filepath),
                filename=filepath.name,
                title=info.get('title'),
                file_size=file_size,
                error=None,
            )
    except Exception as e:
        return DownloadResult(
            success=False,
            file_path=None,
            filename=None,
            title=None,
            file_size=None,
            error=str(e),
        )


def delete_download(file_path: str, user_id: int) -> bool:
    """
    Delete a downloaded file.

    Args:
        file_path: Path to the file
        user_id: The user's ID (for security check)

    Returns:
        True if deleted, False otherwise
    """
    path = Path(file_path)
    user_base_dir = get_user_base_dir(user_id)

    # Security: ensure file is in user's directory (including subdirs)
    try:
        path.resolve().relative_to(user_base_dir.resolve())
    except ValueError:
        return False

    if path.exists():
        os.remove(path)
        return True
    return False


def fetch_multiple_video_info(urls: list[str]) -> list[dict]:
    """
    Fetch info for multiple URLs.

    Returns a list of dicts with either 'info' (VideoInfo) or 'error' (str).
    """
    results = []
    for url in urls:
        url = url.strip()
        if not url:
            continue
        try:
            info = fetch_video_info(url)
            results.append({"url": url, "info": info, "error": None})
        except Exception as e:
            results.append({"url": url, "info": None, "error": str(e)})
    return results
