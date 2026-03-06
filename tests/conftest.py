from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--live-model-tests",
        action="store_true",
        default=False,
        help="Run tests that call real LLM APIs.",
    )


@pytest.fixture
def require_live_model_tests(request: pytest.FixtureRequest) -> None:
    if not request.config.getoption("--live-model-tests"):
        pytest.skip("Use --live-model-tests to run real LLM API tests.")
