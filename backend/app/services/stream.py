"""
Progress event broadcast via RabbitMQ fanout exchange.

Instead of RabbitMQ Streams (which requires a binary native client), this module
uses a classic fanout exchange so every backend replica receives all progress events.

Topology:
  - Exchange: inference-progress (fanout, durable)
  - Worker publishes to the exchange
  - Each backend instance binds a private exclusive auto-delete queue on startup
"""
import asyncio
import json
import logging
import uuid
from typing import Callable

import aio_pika

logger = logging.getLogger(__name__)

PROGRESS_EXCHANGE = "inference-progress"


async def publish_progress(url: str, event: dict) -> None:
    """Publish one progress event to the fanout exchange (fire-and-forget connection)."""
    connection = await aio_pika.connect_robust(url)
    async with connection:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            PROGRESS_EXCHANGE, aio_pika.ExchangeType.FANOUT, durable=True
        )
        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(event).encode(),
                delivery_mode=aio_pika.DeliveryMode.NOT_PERSISTENT,
            ),
            routing_key="",
        )


async def subscribe_progress(
    url: str,
    callback: Callable,
) -> None:
    """
    Long-running coroutine that consumes all progress events and calls callback.
    Creates a private exclusive queue bound to the fanout exchange so this backend
    replica receives every message independently.
    """
    consumer_tag = f"backend-{uuid.uuid4().hex[:8]}"

    while True:
        connection = None
        try:
            connection = await aio_pika.connect_robust(url)
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=100)

            exchange = await channel.declare_exchange(
                PROGRESS_EXCHANGE, aio_pika.ExchangeType.FANOUT, durable=True
            )

            # Exclusive auto-delete queue: lives only for this process lifetime
            queue = await channel.declare_queue(
                f"progress-{consumer_tag}", exclusive=True, auto_delete=True
            )
            await queue.bind(exchange)

            logger.info(f"[Stream] Subscribed to {PROGRESS_EXCHANGE} as {consumer_tag}")

            async with queue.iterator() as messages:
                async for message in messages:
                    async with message.process():
                        try:
                            event = json.loads(message.body.decode())
                            project_id = event.get("project_id")
                            if project_id:
                                await callback(project_id, event)
                        except Exception as e:
                            logger.warning(f"[Stream] Failed to handle message: {e}")

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"[Stream] Consumer error, retrying in 5s: {e}")
            await asyncio.sleep(5)
        finally:
            if connection is not None:
                try:
                    await connection.close()
                except Exception:
                    pass
