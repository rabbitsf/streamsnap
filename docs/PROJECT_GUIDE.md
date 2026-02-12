# StreamSnap - AI-Optimized System Map

> Living documentation for the StreamSnap project.
> Last updated: 2026-02-12 (local file upload + audio extraction + rename feature)

## 1. Project Overview

### What this project does
This project contains two components:

#### A. StreamSnap Web Application (NEW)
- Self-hosted web app for downloading videos from 1000+ sites
- User authentication with session-based login
- Video quality selection and audio extraction
- Local file upload with drag-and-drop for audio extraction via FFmpeg
- Rename support (individual + batch sequential) for downloads and uploads
- Download history with re-download capability

#### B. Claude Code Skills (existing)
- **video-downloader**: Downloads videos/audio from URLs using yt-dlp
- **audio-extractor**: Extracts audio tracks from local video files using FFmpeg
- Skills are packaged as `.skill` files for Claude Code

### What this project does NOT do
- Does not host or stream media files
- Does not transcode beyond what yt-dlp/FFmpeg provides

## 2. High-Level Architecture

### Web Application Architecture
```
Browser (User)
    │ HTTP
    ▼
FastAPI Backend (app/)
    ├── Jinja2 templates (SSR)
    ├── Session-based auth (JWT cookies)
    └── REST endpoints
         │
    ┌────┴────┐
    │         │
    ▼         ▼
 SQLite    yt-dlp
 (users,   (download
 history)  engine)
              │
              ▼
         /downloads
         (file storage)
```

### Canonical source layer (where permanent changes must be made)
- `app/services/downloader.py` - ALL video/audio download logic + local file extraction + rename (web app)
- `app/auth.py` - ALL authentication logic (web app)
- `~/.claude/skills/video-downloader/SKILL.md` - Video downloader skill
- `~/.claude/skills/audio-extractor/SKILL.md` - Audio extractor skill

### Artifact / output layer (generated files)
- `streamsnap.db` - SQLite database (auto-generated)
- `downloads/` - Downloaded media files (user-generated)
- `*.skill` files - Packaged skill archives

## 3. End-to-End Workflows

### Web Application Workflows

#### Workflow A: User Registration/Login
1. User visits `/register` or `/login`
2. Form validated, password hashed with bcrypt
3. JWT token stored in HTTP-only cookie
4. User redirected to main page

#### Workflow B: Video Download (supports multiple URLs + rename)
1. User pastes one or more URLs (newline or comma-separated)
2. HTMX POST to `/fetch-formats` → `downloader.fetch_multiple_video_info()`
3. All video previews rendered; user selects quality/format + rename option
4. HTMX POST to `/download` → batch calls to `download_video()` or `extract_audio()`
5. If rename requested, `rename_download_file()` applied after download
6. Videos saved to `downloads/{user_id}/videos/`
7. Audios saved to `downloads/{user_id}/audios/`
8. Download records saved to database
9. Success partial rendered with individual download links

#### Workflow B2: Local File Upload + Audio Extraction
1. User switches to "Extract from Files" tab on landing page
2. User drags-and-drops or browses for local video files
3. HTMX POST to `/upload/files` → files saved to `downloads/{user_id}/uploads/`
4. Upload options partial rendered with audio format + rename choices
5. HTMX POST to `/upload/extract` → `extract_audio_from_file()` via FFmpeg
6. Audios saved to `downloads/{user_id}/audios/`
7. Source files deleted from uploads dir after extraction
8. Download records saved to database (url="local upload")
9. Success partial rendered with download links

#### Workflow C: History Management
1. User visits `/history`
2. All downloads queried, file existence checked
3. User can re-download or delete entries (single, bulk, or all)
4. DELETE/POST request removes file(s) and database record(s)

### Skill Workflows (unchanged)

#### Workflow D: Video/Audio Download via Skill
1. User provides URL to Claude
2. Claude invokes `video-downloader` skill
3. Skill guides Claude to use yt-dlp
4. Media file downloaded to specified path

## 4. Canonical Implementations (Single Source of Truth)

### 4.1 Web App: Video/Audio Downloading & Local File Extraction
- **User-facing behavior**: Download videos/audio via web interface; extract audio from local uploads
- **Canonical implementation**: `app/services/downloader.py`
- **All routes must use**: `fetch_video_info()`, `download_video()`, `extract_audio()`, `extract_audio_from_file()`, `rename_download_file()`
- **Never duplicate**: yt-dlp calls, FFmpeg calls, format parsing, file path logic, rename logic

### 4.2 Web App: Authentication
- **User-facing behavior**: Login, register, logout
- **Canonical implementation**: `app/auth.py`
- **All routes must use**: `get_current_user`, `authenticate_user`, `create_user`
- **Never duplicate**: Password hashing, JWT creation/validation

### 4.3 Web App: Database Models
- **Canonical implementation**: `app/models.py`
- **Tables**: `users`, `downloads`

### 4.4 Skill: Video Downloading
- **Canonical implementation**: `~/.claude/skills/video-downloader/SKILL.md`
- **Generated artifact**: `video-downloader.skill`

### 4.5 Skill: Audio Extraction
- **Canonical implementation**: `~/.claude/skills/audio-extractor/SKILL.md`
- **Generated artifact**: `audio-extractor.skill`

## 5. Web Application Directory Structure

```
streamsnap/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Settings (DB, secrets, paths)
│   ├── database.py          # SQLAlchemy setup
│   ├── models.py            # User, Download models
│   ├── auth.py              # Authentication (CANONICAL)
│   ├── routes/
│   │   ├── auth.py          # /login, /register, /logout
│   │   ├── download.py      # /, /fetch-formats, /download, /file/{id}
│   │   ├── upload.py         # /upload/files, /upload/extract, /upload/cancel
│   │   └── history.py       # /history, bulk delete, delete-all
│   ├── services/
│   │   └── downloader.py    # yt-dlp wrapper (CANONICAL)
│   ├── templates/
│   │   ├── base.html        # Layout with Tailwind
│   │   ├── login.html
│   │   ├── register.html
│   │   ├── index.html       # Main download page
│   │   ├── history.html
│   │   └── partials/        # HTMX fragments
│   │       ├── format_options.html    # URL download options + rename UI
│   │       ├── upload_options.html    # File upload options + rename UI
│   │       ├── download_complete.html
│   │       └── error.html
│   └── static/css/
├── downloads/               # User files organized by type:
│   └── {user_id}/
│       ├── videos/          # Downloaded videos (.mp4)
│       ├── audios/          # Extracted audio (.mp3, .m4a, .wav)
│       └── uploads/         # Temporary uploaded files (cleaned up after extraction)
├── requirements.txt         # Python dependencies
├── package.json             # Tailwind CLI
└── tailwind.config.js
```

## 6. Routes Reference

| Route | Method | Auth | Purpose |
|-------|--------|------|---------|
| `/` | GET | Yes | Main download page |
| `/login` | GET/POST | No | Login form |
| `/register` | GET/POST | No | Registration form |
| `/logout` | GET | No | Clear session |
| `/fetch-formats` | POST | Yes | Get formats for multiple URLs (HTMX) |
| `/download` | POST | Yes | Batch download multiple URLs (HTMX) |
| `/file/{id}` | GET | Yes | Serve file to browser |
| `/history` | GET | Yes | Download history page |
| `/history/{id}` | DELETE | Yes | Remove single download (HTMX) |
| `/history/delete-bulk` | POST | Yes | Remove multiple selected downloads (HTMX) |
| `/history/delete-all` | POST | Yes | Remove all user downloads (HTMX) |
| `/upload/files` | POST | Yes | Upload local video files (HTMX, multipart) |
| `/upload/extract` | POST | Yes | Extract audio from uploaded files (HTMX) |
| `/upload/cancel` | POST | Yes | Clean up temp uploaded files (HTMX) |

## 7. Database Schema

### users
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER | Primary key |
| username | VARCHAR(50) | Unique, indexed |
| hashed_password | VARCHAR(255) | bcrypt hash |
| created_at | DATETIME | Auto-set |

### downloads
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER | Primary key |
| user_id | INTEGER | FK → users |
| url | VARCHAR(2048) | Source URL |
| title | VARCHAR(500) | Video title |
| filename | VARCHAR(255) | Stored name |
| file_path | VARCHAR(1024) | Full path |
| file_size | BIGINT | Bytes |
| format_type | VARCHAR(50) | "video"/"audio" |
| quality | VARCHAR(50) | e.g., "1080p" |
| created_at | DATETIME | Auto-set |

## 8. Running the Application

```bash
# Install dependencies
pip install -r requirements.txt
npm install

# Start server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Access at http://localhost:8000
```

### Shell Aliases (added to ~/.zshrc)
```bash
streamstart  # Start the server (Ctrl+C to stop)
streamstop   # Stop the server if running in background
```

## 9. Duplication Hotspots (AI Warnings)

- **Download logic**: Never call yt-dlp directly from routes. Always use `app/services/downloader.py`.
- **Local extraction**: Never call FFmpeg directly from routes. Always use `extract_audio_from_file()` from downloader.py.
- **Rename logic**: Never rename files from routes. Always use `rename_download_file()` from downloader.py.
- **Auth checks**: Never validate passwords or tokens outside `app/auth.py`.
- **File paths**: Always use `get_user_download_dir(user_id, media_type)` or `get_user_upload_dir(user_id)` from downloader.py.
- **Playlist suppression**: All yt-dlp option dicts in `downloader.py` MUST include `'noplaylist': True`. Without this, URLs containing playlist parameters (e.g., `&list=...&index=...`) cause yt-dlp to process the entire playlist, hanging the app.
- **Skill vs Web App**: The web app and skills are separate. Skills call yt-dlp via CLI; web app uses Python library.

## 10. Safe Change Playbook

### Modifying download behavior
1. Edit `app/services/downloader.py` only
2. Ensure all three yt-dlp option dicts (`fetch_video_info`, `download_video`, `extract_audio`) stay consistent -- every shared option (e.g., `noplaylist`, `quiet`, `no_warnings`) must appear in all three
3. Update affected templates if output format changes
4. Test via web interface

### Adding new user features
1. Add fields to `app/models.py`
2. Delete `streamsnap.db` or create migration
3. Update routes and templates

### Modifying skills
1. Edit `~/.claude/skills/<skill-name>/SKILL.md`
2. Test via Claude Code
3. Repackage `.skill` file
