import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_no_secrets_committed():
    sys.path.insert(0, str(ROOT / "scripts"))
    from check_secrets import scan

    assert scan() == []


def test_module_layer_contracts_hold():
    # The venv's Scripts/bin folder is not on PATH unless the venv is activated (check.cmd does not activate it).
    exe = shutil.which("lint-imports", path=str(pathlib.Path(sys.executable).parent)) or "lint-imports"
    result = subprocess.run([exe], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
