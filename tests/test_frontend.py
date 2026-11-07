import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="Node is optional and only needed for frontend unit tests")
@pytest.mark.parametrize("test_file", [
    "test_progress.mjs", "test_evaluation_help.mjs", "test_evaluation_review.mjs",
])
def test_frontend_behaviour(test_file: str) -> None:
    version = subprocess.check_output([NODE, "--version"], text=True, timeout=10)
    if int(version.strip().lstrip("v").split(".", 1)[0]) < 22:
        pytest.skip("Node 22+ is optional and only needed for frontend unit tests")
    result = subprocess.run([NODE, "--test",
                             f"tests/web/{test_file}"], cwd=ROOT, capture_output=True,
                            text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
