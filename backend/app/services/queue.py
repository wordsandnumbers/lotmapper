"""AMQP classic queue helpers for job dispatch."""
import json
import aio_pika

JOBS_QUEUE = "inference_jobs"


async def publish_job(url: str, job_id: str, project_id: str, user_id: str) -> None:
    connection = await aio_pika.connect_robust(url)
    async with connection:
        channel = await connection.channel()
        await channel.declare_queue(JOBS_QUEUE, durable=True)
        payload = json.dumps({
            "job_id": job_id,
            "project_id": project_id,
            "user_id": user_id,
        }).encode()
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=payload,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=JOBS_QUEUE,
        )
