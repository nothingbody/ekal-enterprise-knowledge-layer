"""Pytest configuration for backend tests."""
import sys
import os

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(BACKEND_ROOT, ".."))

# Ensure the backend root and shared package are on sys.path
sys.path.insert(0, BACKEND_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "shared"))

import pytest


@pytest.fixture(autouse=True)
def token_blacklist_memory_fallback():
    from app.config import settings
    from rag_platform_common.token_blacklist import reset_state

    original = settings.TOKEN_BLACKLIST_STRICT
    settings.TOKEN_BLACKLIST_STRICT = False
    reset_state()
    try:
        yield
    finally:
        settings.TOKEN_BLACKLIST_STRICT = original
        reset_state()
