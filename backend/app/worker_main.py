"""Worker process: consumes inference jobs from RabbitMQ and runs the inference pipeline."""
import asyncio
import json
import logging
from datetime import datetime

import aio_pika

from app.config import get_settings
from app.database import SessionLocal
from app.models.inference_job import InferenceJob
from app.services.inference import run_inference_for_project
from app.services.queue import JOBS_QUEUE
from app.services.stream import PROGRESS_EXCHANGE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    settings = get_settings()

    logger.info("[Worker] Connecting to RabbitMQ...")
    amqp_connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await amqp_connection.channel()
    await channel.set_qos(prefetch_count=1)

    jobs_queue = await channel.declare_queue(JOBS_QUEUE, durable=True)
    progress_exchange = await channel.declare_exchange(
        PROGRESS_EXCHANGE, aio_pika.ExchangeType.FANOUT, durable=True
    )

    async def _send_progress(event: dict) -> None:
        await progress_exchange.publish(
            aio_pika.Message(
                body=json.dumps(event).encode(),
                delivery_mode=aio_pika.DeliveryMode.NOT_PERSISTENT,
            ),
            routing_key="",
        )

    async def on_message(message: aio_pika.IncomingMessage):
        async with message.process():
            payload = json.loads(message.body)
            job_id = payload["job_id"]
            project_id = payload["project_id"]
            user_id = payload["user_id"]

            logger.info(f"[Worker] Processing job {job_id} for project {project_id}")

            db = SessionLocal()
            try:
                job = db.query(InferenceJob).filter(InferenceJob.id == job_id).first()
                if not job:
                    logger.error(f"[Worker] Job {job_id} not found in DB")
                    return

                job.status = "running"
                job.started_at = datetime.utcnow()
                db.commit()

                await _send_progress({
                    "project_id": project_id,
                    "status": "running",
                    "progress": 0,
                    "message": "Starting inference...",
                })

                async def progress_cb(step: int, total: int, progress: int, msg: str):
                    event = {
                        "project_id": project_id,
                        "status": "running",
                        "step": f"{step}/{total}",
                        "progress": progress,
                        "message": msg,
                    }
                    await _send_progress(event)
                    db.query(InferenceJob).filter(InferenceJob.id == job_id).update({
                        "progress": progress,
                        "step": f"{step}/{total}",
                        "message": msg,
                    })
                    db.commit()

                await run_inference_for_project(
                    project_id=project_id,
                    user_id=user_id,
                    progress_callback=progress_cb,
                )

                job = db.query(InferenceJob).filter(InferenceJob.id == job_id).first()
                job.status = "completed"
                job.progress = 100
                job.completed_at = datetime.utcnow()
                db.commit()

                await _send_progress({
                    "project_id": project_id,
                    "status": "completed",
                    "progress": 100,
                    "message": "Inference complete",
                })
                logger.info(f"[Worker] Job {job_id} completed")

            except Exception as e:
                logger.error(f"[Worker] Job {job_id} failed: {e}")
                try:
                    job = db.query(InferenceJob).filter(InferenceJob.id == job_id).first()
                    if job:
                        job.status = "failed"
                        job.error = str(e)
                        db.commit()
                except Exception:
                    pass
                await _send_progress({
                    "project_id": project_id,
                    "status": "failed",
                    "progress": 0,
                    "message": f"Failed: {e}",
                })
            finally:
                db.close()

    await jobs_queue.consume(on_message)
    logger.info("[Worker] Ready, waiting for jobs...")
    await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
