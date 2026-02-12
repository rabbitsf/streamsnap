# StreamSnap

A self-hosted web application for downloading videos and extracting audio from 1000+ websites. Built with FastAPI, HTMX, and Tailwind CSS.

## Features

- **Video Downloads** — Download videos from YouTube, Twitter/X, TikTok, Instagram, Vimeo, Twitch, Reddit, and 1000+ other sites via [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- **Audio Extraction from URLs** — Extract audio as MP3 or M4A directly from video URLs
- **Local File Upload** — Drag-and-drop local video files to extract audio (MP3, M4A, WAV) using FFmpeg
- **Batch Processing** — Paste multiple URLs or upload multiple files at once
- **Rename Support** — Rename output files individually or with sequential numbering (e.g., "Episode 01", "Episode 02")
- **Quality Selection** — Choose video quality (Best, 1080p, 720p, 480p) before downloading
- **Download History** — Browse, re-download, and manage past downloads with single/bulk/select-all delete
- **User Accounts** — Session-based authentication with per-user file isolation
- **Server-Side Rendering** — Fast, lightweight UI with HTMX partial updates (no JavaScript framework)

## Screenshots

The interface has two tabs:

- **Download from URL** — Paste one or more video URLs, fetch available formats, choose video/audio + rename options, and download
- **Extract from Files** — Drag-and-drop local video files, pick audio format and rename options, and extract in one step

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | [FastAPI](https://fastapi.tiangolo.com/) (Python) |
| Templates | [Jinja2](https://jinja.palletsprojects.com/) SSR |
| Frontend | [HTMX](https://htmx.org/) + [Tailwind CSS](https://tailwindcss.com/) |
| Database | SQLite via [SQLAlchemy](https://www.sqlalchemy.org/) |
| Download Engine | [yt-dlp](https://github.com/yt-dlp/yt-dlp) |
| Audio Extraction | [FFmpeg](https://ffmpeg.org/) |
| Auth | JWT cookies + bcrypt password hashing |

## Prerequisites

- Python 3.10+
- [FFmpeg](https://ffmpeg.org/download.html) installed and on PATH
- Node.js (for Tailwind CSS CLI, optional for development)

## Setup

```bash
# Clone the repository
git clone git@github.com:rabbitsf/streamsnap.git
cd streamsnap

# Create virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt
npm install              # for Tailwind (optional)

# Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000](http://localhost:8000) in your browser. Register an account to get started.

## Project Structure

```
streamsnap/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Settings (DB, secrets, paths)
│   ├── database.py          # SQLAlchemy setup
│   ├── models.py            # User, Download models
│   ├── auth.py              # Authentication (JWT + bcrypt)
│   ├── routes/
│   │   ├── auth.py          # /login, /register, /logout
│   │   ├── download.py      # /, /fetch-formats, /download, /file/{id}
│   │   ├── upload.py        # /upload/extract (local file upload + extract)
│   │   └── history.py       # /history, bulk delete
│   ├── services/
│   │   └── downloader.py    # yt-dlp + FFmpeg wrapper (canonical)
│   ├── templates/           # Jinja2 templates
│   └── static/css/          # Tailwind styles
├── downloads/               # User files (gitignored)
│   └── {user_id}/
│       ├── videos/
│       ├── audios/
│       └── uploads/         # Temp files (cleaned after extraction)
├── requirements.txt
└── package.json
```

## API Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/` | GET | Main page (URL download + file upload tabs) |
| `/login` | GET/POST | Login |
| `/register` | GET/POST | Registration |
| `/logout` | GET | Logout |
| `/fetch-formats` | POST | Fetch video info for URLs (HTMX) |
| `/download` | POST | Download videos/audio from URLs (HTMX) |
| `/upload/extract` | POST | Upload local files + extract audio (HTMX) |
| `/file/{id}` | GET | Serve downloaded file |
| `/history` | GET | Download history page |
| `/history/{id}` | DELETE | Delete single download |
| `/history/delete-bulk` | POST | Delete selected downloads |
| `/history/delete-all` | POST | Delete all downloads |

## License

MIT
