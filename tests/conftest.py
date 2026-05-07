import os
import pytest
import httpx

FEATURES_10 = [0.1, -0.2, 0.5, 1.0, -0.3, 0.8, 0.0, -1.2, 0.4, 0.7]


@pytest.fixture(scope="session")
def api_url() -> str:
    return os.getenv("API_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def client(api_url: str) -> httpx.Client:
    with httpx.Client(base_url=api_url, timeout=15.0) as c:
        try:
            c.get("/health").raise_for_status()
        except Exception as exc:
            pytest.skip(f"API not available at {api_url} — {exc}")
        yield c
