"""
E2E tests for the Streamlit frontend using pytest-playwright.

Requirements:
  - Full Docker stack running (python manage.py start)
  - Playwright browsers installed: playwright install chromium
  - Run: python manage.py test --frontend
    or directly: pytest tests/test_frontend.py -v

Environment:
  FRONTEND_URL  Base URL of the Streamlit app (default: http://localhost:8501)
"""
from __future__ import annotations

import os

import pytest

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8501")
_TIMEOUT = 15_000  # ms



@pytest.fixture(scope="session", autouse=True)
def require_frontend():
    import urllib.request

    try:
        with urllib.request.urlopen(f"{FRONTEND_URL}/_stcore/health", timeout=5) as r:
            if r.status != 200:
                pytest.skip(f"Frontend not healthy at {FRONTEND_URL}")
    except Exception as exc:
        pytest.skip(f"Frontend not available at {FRONTEND_URL} — {exc}")



def _goto(page, path: str = "") -> None:
    page.goto(f"{FRONTEND_URL}{path}")
    page.wait_for_load_state("networkidle", timeout=_TIMEOUT)



def test_fe01_page_title(page):
    """Page title contains the project name."""
    _goto(page)
    assert "PipelineModeling" in page.title()



def test_fe02_tabs_count(page):
    """Exactly 4 navigation tabs are visible: Inference, Training, Versioning, Chaos/Debug."""
    _goto(page)
    tabs = page.locator('[data-baseweb="tab"]')
    tabs.first.wait_for(timeout=_TIMEOUT)
    count = tabs.count()
    assert count == 4, f"Expected 4 tabs, found {count}"



def test_fe03_sidebar_api_status(page):
    """Header renders an API status indicator (Online or Offline) without crashing."""
    _goto(page)
    # Sidebar was replaced with a compact header; status pill is rendered via
    # st.success/st.error which produce stAlert / stNotificationContentSuccess elements.
    status = page.locator('[data-testid="stAlert"]').first
    status.wait_for(timeout=_TIMEOUT)
    status_text = status.inner_text()
    assert "Online" in status_text or "Offline" in status_text, (
        f"Header does not contain API status. Content: {status_text[:200]}"
    )



@pytest.mark.fragile
def test_fe04_inference_form_inputs(page):
    """
    Inference tab Form mode contains at least 30 numeric inputs.

    Marked fragile: depends on Streamlit internal DOM structure which may change
    between minor Streamlit versions.
    """
    _goto(page)
    # Ensure Inference tab is active (first tab)
    inference_tab = page.locator('[data-baseweb="tab"]').first
    inference_tab.click()
    page.wait_for_load_state("networkidle", timeout=_TIMEOUT)

    # Number inputs rendered by st.number_input — each has type="number"
    inputs = page.locator('input[type="number"]')
    inputs.first.wait_for(timeout=_TIMEOUT)
    count = inputs.count()
    assert count >= 30, f"Expected at least 30 number inputs, found {count}"



def test_fe05_versioning_tab_renders(page):
    """Versioning tab loads and shows at least a Refresh list button."""
    _goto(page)
    ver_tab = page.get_by_role("tab", name="Versioning")
    ver_tab.wait_for(timeout=_TIMEOUT)
    ver_tab.click()
    page.wait_for_load_state("networkidle", timeout=_TIMEOUT)

    # Either Refresh list button (dynamic picker) or Switch version button
    refresh_btn = page.get_by_role("button", name="Refresh list")
    switch_btn = page.get_by_role("button", name="Switch version")
    assert refresh_btn.is_visible() or switch_btn.is_visible(), (
        "Versioning tab must show at least one version control button"
    )



def test_fe06_no_traceback_on_load(page):
    """Page loads without an unhandled Python traceback being displayed."""
    _goto(page)
    body_text = page.locator("body").inner_text()
    # Streamlit renders uncaught exceptions inside a red error box with traceback
    assert "Traceback (most recent call last)" not in body_text, (
        "Unhandled exception traceback found in rendered page"
    )



@pytest.mark.fragile
def test_fe07_inference_submit_returns_result(page):
    """
    Submitting a complete inference form (all features at 0) returns a
    result metric visible in the page.

    Marked fragile: depends on Streamlit widget key names and DOM structure.
    """
    _goto(page)
    inference_tab = page.locator('[data-baseweb="tab"]').first
    inference_tab.click()
    page.wait_for_load_state("networkidle", timeout=_TIMEOUT)

    run_btn = page.get_by_role("button", name="Run inference")
    run_btn.wait_for(timeout=_TIMEOUT)
    run_btn.click()
    # Wait for Streamlit to rerender after submit
    page.wait_for_load_state("networkidle", timeout=_TIMEOUT)

    # Result section must contain a metric with "Prediction" label
    page_text = page.locator("body").inner_text()
    assert "Prediction" in page_text or "prediction" in page_text, (
        "No prediction result found after submitting inference form"
    )
