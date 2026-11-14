"""Shared pytest setup.

Tests must never reach a real LLM or market-data API. The fixtures here strip
provider credentials from the environment so an accidental live call fails
fast instead of spending money.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

CREDENTIAL_VARS = (
    "OPENROUTER_API_KEY",
    "OPENROUTER_BASE_URL",
    "OPENROUTER_DEEPSEEK_R1",
    "TWELVE_API_KEY",
    "RAPID_API_KEY",
    "TIMEGPT_API_KEY",
)


def clean_env() -> dict:
    """Return a copy of os.environ without any provider credentials."""
    return {k: v for k, v in os.environ.items() if k not in CREDENTIAL_VARS}


@pytest.fixture
def no_credentials(monkeypatch):
    for var in CREDENTIAL_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def run_python(tmp_path):
    """Run a Python snippet in a fresh interpreter with no credentials.

    The working directory is a temp folder so import-time side effects
    (output/ and logs/ folders, .env loading) never touch the repository.
    """

    def _run(code: str) -> subprocess.CompletedProcess:
        env = clean_env()
        env["PYTHONPATH"] = str(REPO_ROOT)
        return subprocess.run(
            [sys.executable, "-c", code],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )

    return _run
