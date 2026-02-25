from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.user import User
from app.models.project import Project
from app.models.polygon import Polygon
from app.api.deps import get_current_active_user
from app.services.inference import run_inference_for_project

router = APIRouter()


@router.post("/run/{project_id}")
async def trigger_inference(
    project_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Trigger model inference for a project's bounding box."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    if project.status == "processing":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project is already being processed",
        )

    # Update status to processing
    project.status = "processing"
    db.commit()

    # Run inference in background
    background_tasks.add_task(
        run_inference_for_project,
        project_id=str(project_id),
        user_id=str(current_user.id),
    )

    return {
        "message": "Inference started",
        "project_id": str(project_id),
        "status": "processing",
    }


@router.get("/status/{project_id}")
async def get_inference_status(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get the inference status for a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    polygon_count = db.query(Polygon).filter(
        Polygon.project_id == project_id,
        Polygon.status != "deleted",
    ).count()

    return {
        "project_id": str(project_id),
        "status": project.status,
        "polygon_count": polygon_count,
    }
