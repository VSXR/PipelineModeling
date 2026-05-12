from __future__ import annotations

import asyncio
import concurrent.futures
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wrapper.client import PipelineClient


def _run(coro):
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def _health(api_url: str) -> dict:
    async with PipelineClient(api_url) as client:
        return await client.health()


async def _infer(api_url: str, features: list[float], request_id: Optional[str]) -> object:
    async with PipelineClient(api_url) as client:
        return await client.infer(features, request_id)


async def _train(api_url: str, features: list[list[float]], labels: list[int]) -> object:
    async with PipelineClient(api_url) as client:
        return await client.train(features, labels)


async def _switch(api_url: str, git_ref: str) -> object:
    async with PipelineClient(api_url) as client:
        return await client.switch_version(git_ref)


async def _current_version(api_url: str) -> dict:
    async with PipelineClient(api_url) as client:
        return await client.current_version()


def fetch_health(api_url: str) -> dict:
    return _run(_health(api_url))


def fetch_inference(api_url: str, features: list[float], request_id: Optional[str]) -> object:
    return _run(_infer(api_url, features, request_id))


def fetch_training(api_url: str, features: list[list[float]], labels: list[int]) -> object:
    return _run(_train(api_url, features, labels))


def fetch_switch(api_url: str, git_ref: str) -> object:
    return _run(_switch(api_url, git_ref))


def fetch_current_version(api_url: str) -> dict:
    return _run(_current_version(api_url))
