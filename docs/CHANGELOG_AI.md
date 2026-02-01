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

---

## 2026-02-01: Multi-Select Delete for History

### Changes
- Added checkboxes to history table for multi-select
- Added "Delete Selected" button with item count
- Added "Delete All" button to clear entire history
- New routes: `POST /history/delete-bulk`, `POST /history/delete-all`
- Both endpoints reuse canonical `delete_download()` from `app/services/downloader.py`

### Files Modified
- `app/routes/history.py` - added bulk delete endpoints
- `app/templates/history.html` - added checkboxes, toolbar, and JavaScript
