import os
import pytest
import httpx

# Representative sample from the Breast Cancer Wisconsin dataset (sample #0, malignant).
# 30 features: 10 mean values · 10 standard-error values · 10 worst values.
FEATURES_30 = [
    17.99, 10.38, 122.80, 1001.0, 0.1184, 0.2776, 0.3001, 0.1471, 0.2419, 0.0787,
     1.095,  0.905,   8.589,  153.4, 0.0064, 0.0490, 0.0537, 0.0159, 0.0300, 0.0062,
    25.38,  17.33,  184.60, 2019.0, 0.1622, 0.6656, 0.7119, 0.2654, 0.4601, 0.1189,
]


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
