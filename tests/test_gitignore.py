"""X3: source docs are tracked; generated pipeline output stays ignored."""
import subprocess

import pytest

from conftest import REPO_ROOT


def is_ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", path],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    if result.returncode not in (0, 1):
        pytest.fail(f"git check-ignore failed: {result.stderr!r}")
    return result.returncode == 0


@pytest.mark.parametrize(
    "path",
    [
        "README.md",
        "ROADMAP.md",
        "docs/CURRENT-HANDOFF.md",
        "docs/ROADMAP-PROGRESS.md",
        "tests/fixtures/golden/ti_context.txt",
        "ai_trading_crew/report/templates/report.html",
    ],
)
def test_source_files_are_tracked(path):
    assert not is_ignored(path), f"{path} should not be ignored"


@pytest.mark.parametrize(
    "path",
    [
        "output/agents_outputs/2026-01-01/AAPL/day_trading_recommendation.md",
        "output/agents_inputs/2026-01-01/AAPL_stock_news.txt",
        "output/aitc.sqlite",
        "finviz_response.html",
        "logs/run.log",
        ".env",
        ".claude/state/session.json",
    ],
)
def test_generated_and_secret_files_are_ignored(path):
    assert is_ignored(path), f"{path} should be ignored"
