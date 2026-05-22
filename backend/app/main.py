import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.api import api_router
from app.core.limiter import limiter
from app.services import sse, stream

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async def on_progress(project_id: str, event: dict):
        await sse.broadcast(project_id, event)

    task = asyncio.create_task(
        stream.subscribe_progress(
            url=settings.rabbitmq_url,
            callback=on_progress,
        )
    )
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title=settings.app_name,
    description="API for parking lot detection and editing",
    version=settings.app_version,
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": settings.app_version, "service": "backend"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Parking Lot Mapping Tool API",
        "docs": "/docs",
        "health": "/health",
    }
