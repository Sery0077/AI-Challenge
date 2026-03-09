from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _python_with_mcp() -> str | None:
    candidates = [sys.executable, str(ROOT / ".venv" / "bin" / "python")]
    for candidate in candidates:
        if not Path(candidate).exists():
            continue
        result = subprocess.run(
            [candidate, "-c", "import mcp"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return candidate
    return None


def test_list_tools_script_outputs_available_tools() -> None:
    python_bin = _python_with_mcp()
    if python_bin is None:
        pytest.skip("Python interpreter with installed mcp package is not available.")

    result = subprocess.run(
        [python_bin, str(ROOT / "src" / "mcp" / "list_tools.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "MCP connection established." in result.stdout
    assert "Available tools:" in result.stdout
    assert "- ping" in result.stdout
    assert "- add" in result.stdout
