# AI Changelog

## 2026-02-01: StreamSnap Web Application

### Initial Implementation
- Created FastAPI web application for video/audio downloading
- User authentication with bcrypt password hashing and JWT sessions
- Integration with yt-dlp for 1000+ site support
- Download history with re-download and delete functionality
- Tailwind CSS + HTMX frontend (server-side rendering)

### Enhancements
- **Multiple URL support**: Users can paste multiple URLs (newline or comma-separated) for batch downloading
- **Separate storage folders**: Videos saved to `downloads/{user_id}/videos/`, audios to `downloads/{user_id}/audios/`
- **Shell aliases**: Added `streamstart` and `streamstop` aliases to `~/.zshrc`

### Canonical Implementations
| Behavior | File |
|----------|------|
| Video/audio downloading | `app/services/downloader.py` |
| Authentication | `app/auth.py` |
| Database models | `app/models.py` |
