import asyncio
import json
from uuid import UUID, uuid4
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.models.project import Project
from app.models.polygon import Polygon
from app.models.inference_job import InferenceJob
from app.api.deps import get_current_active_user
from app.core.security import decode_token
from app.services import sse, queue

router = APIRouter()
settings = get_settings()


def _get_user_from_token(token: str, db: Session) -> User:
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


@router.post("/run/{project_id}")
async def trigger_inference(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Queue model inference for a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if project.created_by != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    if project.status == "processing":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project is already being processed")

    job_id = uuid4()

    job = InferenceJob(
        id=job_id,
        project_id=project_id,
        status="queued",
        queued_at=datetime.utcnow(),
    )
    db.add(job)
    project.status = "processing"
    db.commit()

    await queue.publish_job(settings.rabbitmq_url, str(job_id), str(project_id), str(current_user.id))

    queued_count = db.query(InferenceJob).filter(InferenceJob.status == "queued").count()

    return {
        "job_id": str(job_id),
        "project_id": str(project_id),
        "queue_position": queued_count,
    }


@router.get("/stream/{project_id}")
async def stream_inference_progress(
    project_id: UUID,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """SSE stream for inference progress. Accepts JWT as query param (EventSource limitation)."""
    current_user = _get_user_from_token(token, db)

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if project.created_by != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    q = sse.subscribe(str(project_id))

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("status") in ("completed", "failed"):
                        break
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            sse.unsubscribe(str(project_id), q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/status/{project_id}")
async def get_inference_status(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get the inference status for a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    polygon_count = db.query(Polygon).filter(
        Polygon.project_id == project_id,
        Polygon.status != "deleted",
    ).count()

    return {
        "project_id": str(project_id),
        "status": project.status,
        "polygon_count": polygon_count,
    }
