"""
Continuous data seeder.

Three concurrent coroutines share one httpx.AsyncClient:
  - inference_loop  : streams synthetic inference requests at a fixed RPS.
  - training_loop   : drains the shared buffer and sends partial_fit batches.
  - drift_controller: activates a statistical shift after DRIFT_ONSET_AFTER_S.

Backpressure is enforced by:
  1. asyncio.Semaphore capping concurrent in-flight requests.
  2. collections.deque with maxlen preventing unbounded buffer growth.
"""

import asyncio
import logging
import os
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import AsyncGenerator, Deque, List, Tuple

import httpx
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("seeder")

API_URL = os.getenv("API_URL", "http://api:8000")
RPS = float(os.getenv("REQUESTS_PER_SECOND", "20"))
CONCURRENCY = int(os.getenv("INFERENCE_CONCURRENCY", "10"))
TRAIN_INTERVAL = float(os.getenv("TRAINING_INTERVAL_S", "30"))
BATCH_SIZE = int(os.getenv("TRAINING_BATCH_SIZE", "50"))
DRIFT_ONSET = float(os.getenv("DRIFT_ONSET_AFTER_S", "120"))
DRIFT_MAG = float(os.getenv("DRIFT_MAGNITUDE", "2.0"))
N_FEATURES = 10
BUFFER_MAX = 2_000
API_STARTUP_GRACE = 5.0


@dataclass
class DriftState:
    active: bool = False
    magnitude: float = 0.0
    onset_time: float = field(default_factory=lambda: 0.0)


def _generate_sample(drift: DriftState) -> Tuple[List[float], int]:
    base = np.random.randn(N_FEATURES)
    if drift.active:
        shift = np.ones(N_FEATURES) * drift.magnitude * np.random.uniform(0.8, 1.2)
        base += shift
    label = int(np.dot(base[:3], [1.0, 0.5, 0.25]) > 0.5)
    return base.tolist(), label


async def _sample_stream(
    drift: DriftState,
) -> AsyncGenerator[Tuple[List[float], int], None]:
    while True:
        yield _generate_sample(drift)
        await asyncio.sleep(0)


async def _send_inference(
    client: httpx.AsyncClient,
    features: List[float],
    sem: asyncio.Semaphore,
) -> None:
    async with sem:
        try:
            r = await client.post(
                "/infer/",
                json={"features": features, "request_id": str(uuid.uuid4())},
                timeout=5.0,
            )
            r.raise_for_status()
        except httpx.HTTPStatusError as exc:
            log.warning("Inference HTTP %s", exc.response.status_code)
        except httpx.TimeoutException:
            log.debug("Inference request timed out")
        except Exception as exc:  # noqa: BLE001
            log.debug("Inference error: %s", exc)


async def inference_loop(
    client: httpx.AsyncClient,
    drift: DriftState,
    buffer: Deque[Tuple[List[float], int]],
) -> None:
    sem = asyncio.Semaphore(CONCURRENCY)
    interval = 1.0 / RPS
    async for features, label in _sample_stream(drift):
        buffer.append((features, label))
        asyncio.create_task(_send_inference(client, features, sem))
        await asyncio.sleep(interval)


async def training_loop(
    client: httpx.AsyncClient,
    buffer: Deque[Tuple[List[float], int]],
) -> None:
    while True:
        await asyncio.sleep(TRAIN_INTERVAL)

        if len(buffer) < BATCH_SIZE:
            log.debug("Buffer too small for training (%d/%d)", len(buffer), BATCH_SIZE)
            continue

        batch = [buffer.popleft() for _ in range(min(BATCH_SIZE, len(buffer)))]
        features = [f for f, _ in batch]
        labels = [lbl for _, lbl in batch]

        try:
            r = await client.post(
                "/train/",
                json={"features": features, "labels": labels},
                timeout=30.0,
            )
            r.raise_for_status()
            data = r.json()
            log.info(
                "Training OK — %d samples, version=%s",
                data["samples_trained"],
                data["model_version"],
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Training request failed: %s — batch returned to buffer", exc)
            buffer.extendleft(reversed(batch))


async def drift_controller(drift: DriftState) -> None:
    await asyncio.sleep(DRIFT_ONSET)
    drift.active = True
    drift.magnitude = DRIFT_MAG
    log.warning(
        "DATA DRIFT ACTIVATED — magnitude=%.2f, features shifted by N(%.2f, 0.2)",
        DRIFT_MAG,
        DRIFT_MAG,
    )


async def _wait_for_api(client: httpx.AsyncClient) -> None:
    log.info("Waiting for API readiness…")
    for attempt in range(30):
        try:
            r = await client.get("/health", timeout=3.0)
            if r.status_code == 200 and r.json().get("model_loaded"):
                log.info("API ready after %d attempts", attempt + 1)
                return
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(API_STARTUP_GRACE)
    log.warning("API did not become ready in time — proceeding anyway")


async def main() -> None:
    drift = DriftState()
    buffer: Deque[Tuple[List[float], int]] = deque(maxlen=BUFFER_MAX)

    async with httpx.AsyncClient(base_url=API_URL) as client:
        await _wait_for_api(client)
        log.info("Seeder running — %.0f req/s, drift onset in %.0fs", RPS, DRIFT_ONSET)

        await asyncio.gather(
            inference_loop(client, drift, buffer),
            training_loop(client, buffer),
            drift_controller(drift),
        )


if __name__ == "__main__":
    asyncio.run(main())
