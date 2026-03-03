from fastapi import APIRouter
from app.api import auth, projects, polygons, inference, maps

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(polygons.router, prefix="/polygons", tags=["polygons"])
api_router.include_router(inference.router, prefix="/inference", tags=["inference"])
api_router.include_router(maps.router, prefix="/maps", tags=["maps"])
