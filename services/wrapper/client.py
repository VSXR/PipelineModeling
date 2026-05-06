from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import httpx


@dataclass(frozen=True)
class InferenceResult:
    prediction: int
    probability: List[float]
    model_version: str
    request_id: Optional[str]


@dataclass(frozen=True)
class TrainingResult:
    status: str
    samples_trained: int
    model_version: str


@dataclass(frozen=True)
class VersionSwitchResult:
    status: str
    previous_version: str
    current_version: str


class PipelineClient:
    """
    Async HTTP wrapper around the PipelineModeling API.
    Designed to be used as an async context manager.

    Usage:
        async with PipelineClient("http://localhost:8000") as client:
            result = await client.infer([0.1] * 10)
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 10.0,
        max_connections: int = 100,
        max_keepalive: int = 20,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(
                max_connections=max_connections,
                max_keepalive_connections=max_keepalive,
            ),
        )

    async def __aenter__(self) -> "PipelineClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._client.aclose()

    async def infer(
        self,
        features: List[float],
        request_id: Optional[str] = None,
    ) -> InferenceResult:
        response = await self._client.post(
            "/infer/",
            json={"features": features, "request_id": request_id},
        )
        response.raise_for_status()
        return InferenceResult(**response.json())

    async def train(
        self,
        features: List[List[float]],
        labels: List[int],
    ) -> TrainingResult:
        response = await self._client.post(
            "/train/",
            json={"features": features, "labels": labels},
        )
        response.raise_for_status()
        return TrainingResult(**response.json())

    async def switch_version(self, git_ref: str) -> VersionSwitchResult:
        response = await self._client.post(
            "/version/switch",
            json={"git_ref": git_ref},
            timeout=300.0,
        )
        response.raise_for_status()
        return VersionSwitchResult(**response.json())

    async def current_version(self) -> dict:
        response = await self._client.get("/version/current")
        response.raise_for_status()
        return response.json()

    async def health(self) -> dict:
        response = await self._client.get("/health")
        response.raise_for_status()
        return response.json()
