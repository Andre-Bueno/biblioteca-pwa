"""Architecture tests: run import-linter for real, plus negative tests per contract."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]

_RUNNER = (
    "import sys; from importlinter.cli import lint_imports; "
    "sys.exit(lint_imports(config_filename=sys.argv[1], no_cache=True, no_logo=True))"
)

SUBPACKAGES = ("domain", "ports", "services", "adapters", "api", "core")


def _lint(cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", _RUNNER, "pyproject.toml"],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
    )


def _make_package(root: Path, module: str, source: str) -> None:
    """Build a minimal `app` package whose only content is one module with `source`."""
    shutil.copy(BACKEND_DIR / "pyproject.toml", root / "pyproject.toml")
    app = root / "app"
    app.mkdir()
    (app / "__init__.py").write_text("")
    (app / "main.py").write_text("")
    for sub in SUBPACKAGES:
        (app / sub).mkdir()
        (app / sub / "__init__.py").write_text("")
    target = app.joinpath(*module.split("."))
    target.with_suffix(".py").write_text(source)


def test_import_linter_contracts_hold() -> None:
    result = _lint(BACKEND_DIR)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "KEPT" in output, output  # proves contracts were actually evaluated


def test_runner_passes_on_clean_minimal_package(tmp_path: Path) -> None:
    _make_package(tmp_path, "services.ok", "import app.domain\nimport app.ports\n")
    result = _lint(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


VIOLATIONS = [
    # (contract name fragment, module, source)
    ("domain is pure", "domain.bad", "import app.services\n"),
    ("domain is pure", "domain.bad", "import app.core\n"),
    ("domain is pure", "domain.bad", "import app.ports\n"),
    ("domain is pure", "domain.bad", "import app.adapters\n"),
    ("domain is pure", "domain.bad", "import app.api\n"),
    ("domain is pure", "domain.bad", "import app.main\n"),
    ("domain is pure", "domain.bad", "import fastapi\n"),
    ("domain is pure", "domain.bad", "import sqlalchemy\n"),
    ("domain is pure", "domain.bad", "import pydantic\n"),
    ("domain is pure", "domain.bad", "import starlette\n"),
    ("domain is pure", "domain.bad", "import httpx\n"),
    ("ports only depend on domain", "ports.bad", "import app.services\n"),
    ("ports only depend on domain", "ports.bad", "import app.adapters\n"),
    ("ports only depend on domain", "ports.bad", "import app.core\n"),
    ("ports only depend on domain", "ports.bad", "import app.api\n"),
    ("ports only depend on domain", "ports.bad", "import app.main\n"),
    ("ports only depend on domain", "ports.bad", "import fastapi\n"),
    ("ports only depend on domain", "ports.bad", "import sqlalchemy\n"),
    ("services only depend on domain and ports", "services.bad", "import app.adapters\n"),
    ("services only depend on domain and ports", "services.bad", "import app.api\n"),
    ("services only depend on domain and ports", "services.bad", "import app.core\n"),
    ("services only depend on domain and ports", "services.bad", "import app.main\n"),
    ("services only depend on domain and ports", "services.bad", "import fastapi\n"),
    ("services only depend on domain and ports", "services.bad", "import sqlalchemy\n"),
    ("core does not depend on application layers", "core.bad", "import app.api\n"),
    ("core does not depend on application layers", "core.bad", "import app.services\n"),
    ("core does not depend on application layers", "core.bad", "import app.adapters\n"),
    ("core does not depend on application layers", "core.bad", "import app.main\n"),
    ("adapters do not depend on api or services", "adapters.bad", "import app.api\n"),
    ("adapters do not depend on api or services", "adapters.bad", "import app.services\n"),
    ("adapters do not depend on api or services", "adapters.bad", "import app.main\n"),
    ("api does not import adapters", "api.bad", "import app.adapters\n"),
    ("api does not import adapters", "api.bad", "import sqlalchemy\n"),
]


@pytest.mark.parametrize(("contract", "module", "source"), VIOLATIONS)
def test_contract_is_enforced(tmp_path: Path, contract: str, module: str, source: str) -> None:
    _make_package(tmp_path, module, source)
    result = _lint(tmp_path)
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert f"{contract}" in output
    assert "BROKEN" in output


def test_api_deps_is_the_only_api_module_allowed_to_import_adapters(tmp_path: Path) -> None:
    _make_package(tmp_path, "api.deps", "import app.adapters\n")
    result = _lint(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_api_deps_may_import_adapter_submodules(tmp_path: Path) -> None:
    _make_package(tmp_path, "api.deps", "import app.adapters.persistence.x\n")
    persistence = tmp_path / "app" / "adapters" / "persistence"
    persistence.mkdir()
    (persistence / "__init__.py").write_text("")
    (persistence / "x.py").write_text("")
    result = _lint(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_other_api_modules_cannot_import_adapter_submodules(tmp_path: Path) -> None:
    _make_package(tmp_path, "api.bad", "import app.adapters.persistence.x\n")
    persistence = tmp_path / "app" / "adapters" / "persistence"
    persistence.mkdir()
    (persistence / "__init__.py").write_text("")
    (persistence / "x.py").write_text("")
    result = _lint(tmp_path)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "BROKEN" in result.stdout + result.stderr
