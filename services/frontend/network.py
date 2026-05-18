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


async def _switch(api_url: str, model_ref: str) -> object:
    async with PipelineClient(api_url) as client:
        return await client.switch_version(model_ref)


async def _chaos_state(api_url: str) -> dict:
    async with PipelineClient(api_url) as client:
        return await client.chaos_state()


async def _set_chaos(api_url: str, rate: float) -> dict:
    async with PipelineClient(api_url) as client:
        return await client.set_chaos(rate)


async def _reset_chaos(api_url: str) -> dict:
    async with PipelineClient(api_url) as client:
        return await client.reset_chaos()


async def _current_version(api_url: str) -> dict:
    async with PipelineClient(api_url) as client:
        return await client.current_version()


async def _register_version(api_url: str) -> dict:
    async with PipelineClient(api_url) as client:
        return await client.register_version()


async def _list_versions(api_url: str) -> dict:
    async with PipelineClient(api_url) as client:
        return await client.list_versions()


def fetch_health(api_url: str) -> dict:
    return _run(_health(api_url))


def fetch_inference(api_url: str, features: list[float], request_id: Optional[str]) -> object:
    return _run(_infer(api_url, features, request_id))


def fetch_training(api_url: str, features: list[list[float]], labels: list[int]) -> object:
    return _run(_train(api_url, features, labels))


def fetch_switch(api_url: str, model_ref: str) -> object:
    return _run(_switch(api_url, model_ref))


def fetch_current_version(api_url: str) -> dict:
    return _run(_current_version(api_url))


def fetch_register_version(api_url: str) -> dict:
    return _run(_register_version(api_url))


def fetch_chaos_state(api_url: str) -> dict:
    return _run(_chaos_state(api_url))


def fetch_set_chaos(api_url: str, rate: float) -> dict:
    return _run(_set_chaos(api_url, rate))


def fetch_reset_chaos(api_url: str) -> dict:
    return _run(_reset_chaos(api_url))


def fetch_version_list(api_url: str) -> dict:
    return _run(_list_versions(api_url))
