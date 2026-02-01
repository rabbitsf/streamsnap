from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import HTTPException

from app.database import init_db
from app.routes import auth, download, history

app = FastAPI(
    title="StreamSnap",
    description="Download videos from 1000+ sites",
    version="1.0.0",
)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include routers
app.include_router(auth.router)
app.include_router(download.router)
app.include_router(history.router)


@app.on_event("startup")
async def startup():
    """Initialize database on startup."""
    init_db()


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with redirects for auth errors."""
    if exc.status_code == 401:
        return RedirectResponse(url="/login", status_code=303)
    raise exc


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
