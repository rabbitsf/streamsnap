# StreamSnap - AI-Optimized System Map

> Living documentation for the StreamSnap project.
> Last updated: 2026-02-01

## 1. Project Overview

### What this project does
This project contains two components:

#### A. StreamSnap Web Application (NEW)
- Self-hosted web app for downloading videos from 1000+ sites
- User authentication with session-based login
- Video quality selection and audio extraction
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
- `app/services/downloader.py` - ALL video/audio download logic (web app)
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

#### Workflow B: Video Download (supports multiple URLs)
1. User pastes one or more URLs (newline or comma-separated)
2. HTMX POST to `/fetch-formats` → `downloader.fetch_multiple_video_info()`
3. All video previews rendered; user selects quality/format
4. HTMX POST to `/download` → batch calls to `download_video()` or `extract_audio()`
5. Videos saved to `downloads/{user_id}/videos/`
6. Audios saved to `downloads/{user_id}/audios/`
7. Download records saved to database
8. Success partial rendered with individual download links

#### Workflow C: History Management
1. User visits `/history`
2. All downloads queried, file existence checked
3. User can re-download or delete entries
4. DELETE request removes file and database record

### Skill Workflows (unchanged)

#### Workflow D: Video/Audio Download via Skill
1. User provides URL to Claude
2. Claude invokes `video-downloader` skill
3. Skill guides Claude to use yt-dlp
4. Media file downloaded to specified path

## 4. Canonical Implementations (Single Source of Truth)

### 4.1 Web App: Video/Audio Downloading
- **User-facing behavior**: Download videos/audio via web interface
- **Canonical implementation**: `app/services/downloader.py`
- **All routes must use**: `fetch_video_info()`, `download_video()`, `extract_audio()`
- **Never duplicate**: yt-dlp calls, format parsing, file path logic

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
│   │   └── history.py       # /history, DELETE /history/{id}
│   ├── services/
│   │   └── downloader.py    # yt-dlp wrapper (CANONICAL)
│   ├── templates/
│   │   ├── base.html        # Layout with Tailwind
│   │   ├── login.html
│   │   ├── register.html
│   │   ├── index.html       # Main download page
│   │   ├── history.html
│   │   └── partials/        # HTMX fragments
│   │       ├── format_options.html
│   │       ├── download_complete.html
│   │       └── error.html
│   └── static/css/
├── downloads/               # User files organized by type:
│   └── {user_id}/
│       ├── videos/          # Downloaded videos (.mp4)
│       └── audios/          # Extracted audio (.mp3, .m4a)
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
| `/history/{id}` | DELETE | Yes | Remove download (HTMX) |

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
- **Auth checks**: Never validate passwords or tokens outside `app/auth.py`.
- **File paths**: Always use `get_user_download_dir(user_id, media_type)` from downloader.py. Pass `media_type="video"` or `media_type="audio"` to route files to the correct subfolder.
- **Skill vs Web App**: The web app and skills are separate. Skills call yt-dlp via CLI; web app uses Python library.

## 10. Safe Change Playbook

### Modifying download behavior
1. Edit `app/services/downloader.py` only
2. Update affected templates if output format changes
3. Test via web interface

### Adding new user features
1. Add fields to `app/models.py`
2. Delete `streamsnap.db` or create migration
3. Update routes and templates

### Modifying skills
1. Edit `~/.claude/skills/<skill-name>/SKILL.md`
2. Test via Claude Code
3. Repackage `.skill` file
