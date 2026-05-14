"""
Progress event streaming via the native RabbitMQ Stream protocol (port 5552).

Uses the rstream client for best performance. Each backend replica subscribes
independently with OffsetType.NEXT so it receives only messages published after
it connects. subscribe_progress reconnects with exponential backoff (5s → 60s).

Topology:
  - Stream: inference-progress (durable, created idempotently by both sides)
  - Worker publishes via Producer.send()
  - Each backend instance consumes with a unique subscriber_name at NEXT offset
"""
import asyncio
import json
import logging
import uuid
from typing import Callable
from urllib.parse import urlparse

from rstream import (
    Consumer,
    ConsumerOffsetSpecification,
    MessageContext,
    OffsetType,
    Producer,
)

logger = logging.getLogger(__name__)

PROGRESS_STREAM = "inference-progress"
STREAM_PORT = 5552


def _parse_amqp_url(url: str) -> tuple[str, str, str]:
    """Extract (host, username, password) from an amqp:// URL."""
    p = urlparse(url)
    return p.hostname, p.username, p.password


async def publish_progress(url: str, event: dict) -> None:
    """Publish one progress event (creates a short-lived producer connection)."""
    host, username, password = _parse_amqp_url(url)
    async with Producer(host=host, port=STREAM_PORT, username=username, password=password) as producer:
        await producer.create_stream(PROGRESS_STREAM, exists_ok=True)
        await producer.send(stream=PROGRESS_STREAM, message=json.dumps(event).encode())


async def subscribe_progress(url: str, callback: Callable) -> None:
    """
    Long-running coroutine that consumes all progress events and calls callback.
    Starts from OffsetType.NEXT so only messages arriving after startup are
    delivered. Reconnects with exponential backoff if RabbitMQ is unavailable.
    """
    consumer_tag = f"backend-{uuid.uuid4().hex[:8]}"
    host, username, password = _parse_amqp_url(url)
    delay = 5

    while True:
        consumer = None
        try:
            consumer = Consumer(
                host=host,
                port=STREAM_PORT,
                username=username,
                password=password,
                connection_name=consumer_tag,
            )
            await consumer.start()
            await consumer.create_stream(PROGRESS_STREAM, exists_ok=True)

            async def on_message(data: bytes, _: MessageContext) -> None:
                try:
                    event = json.loads(data)
                    project_id = event.get("project_id")
                    if project_id:
                        await callback(project_id, event)
                except Exception as e:
                    logger.warning(f"[Stream] Failed to handle message: {e}")

            await consumer.subscribe(
                stream=PROGRESS_STREAM,
                callback=on_message,
                offset_specification=ConsumerOffsetSpecification(OffsetType.NEXT, None),
                subscriber_name=consumer_tag,
                decoder=lambda data: data,
            )

            logger.info(f"[Stream] Subscribed to {PROGRESS_STREAM} as {consumer_tag}")
            delay = 5
            await consumer.run()
            logger.warning("[Stream] Consumer disconnected, reconnecting...")

        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.warning(f"[Stream] Connection failed: {e}. Retrying in {delay}s...")
            delay = min(delay * 2, 60)
            await asyncio.sleep(delay)
        finally:
            if consumer is not None:
                try:
                    await consumer.close()
                except Exception:
                    pass
