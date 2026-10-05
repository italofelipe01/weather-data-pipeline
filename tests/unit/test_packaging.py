import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"


@pytest.mark.parametrize("module", ["planner.handler", "collector.handler", "publisher.handler"])
def test_light_functions_do_not_import_pyarrow(module: str) -> None:
    """Only the Curator gets the pyarrow layer; the other Lambdas must stay small and fast to cold start."""
    code = f"import sys, {module}; sys.exit(1 if 'pyarrow' in sys.modules else 0)"
    completed = subprocess.run([sys.executable, "-c", code], cwd=SRC, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr or f"{module} imports pyarrow"
