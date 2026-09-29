import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import get_settings
from app.database import engine, Base, SessionLocal
from app.models import User
from app.security import hash_password
from app.services.cleanup_service import periodic_cleanup_task
from app.routers import auth_router, unlock_router, admin_router

settings = get_settings()


def init_default_users():
    """Seed initial default admin and staff users if DB is fresh."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        # Check admin
        admin = db.query(User).filter(User.username == settings.DEFAULT_ADMIN_USERNAME).first()
        if not admin:
            admin = User(
                username=settings.DEFAULT_ADMIN_USERNAME,
                hashed_password=hash_password(settings.DEFAULT_ADMIN_PASSWORD),
                role="admin",
                is_active=True
            )
            db.add(admin)

        # Check staff
        staff = db.query(User).filter(User.username == settings.DEFAULT_STAFF_USERNAME).first()
        if not staff:
            staff = User(
                username=settings.DEFAULT_STAFF_USERNAME,
                hashed_password=hash_password(settings.DEFAULT_STAFF_PASSWORD),
                role="staff",
                is_active=True
            )
            db.add(staff)

        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    os.makedirs(settings.TEMP_DIR, exist_ok=True)
    init_default_users()

    # Launch periodic background cleanup task
    cleanup_task = asyncio.create_task(periodic_cleanup_task(interval_seconds=300))

    yield

    # Shutdown
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Internal Enterprise PDF Decryption and Unlocking System",
    lifespan=lifespan
)

# SlowAPI Rate Limiting Middleware
app.state.limiter = auth_router.limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please slow down and try again shortly."}
    )


# Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.tailwindcss.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: blob:; "
        "connect-src 'self';"
    )
    return response


# Include Routers
app.include_router(auth_router.router)
app.include_router(unlock_router.router)
app.include_router(admin_router.router)

# Mount Static Files & Templates
base_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(base_dir, "static")
templates_dir = os.path.join(base_dir, "templates")

os.makedirs(static_dir, exist_ok=True)
os.makedirs(templates_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)


@app.get("/api/health")
async def health_check():
    """Health check endpoint for container orchestrators and monitoring."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": "1.0.0",
        "workers": settings.WORKER_COUNT,
        "environment": settings.APP_ENV
    }


@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    """Serve the single page application."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "app_name": settings.APP_NAME,
            "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
            "max_files": settings.MAX_FILES_PER_JOB
        }
    )
