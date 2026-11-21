"""Architecture tests: run import-linter for real, plus negative tests per contract."""

import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]

_RUNNER = (
    "import sys; from importlinter.cli import lint_imports; "
    "sys.exit(lint_imports(config_filename=sys.argv[1], no_cache=True, no_logo=True))"
)

SUBPACKAGES = ("domain", "ports", "services", "adapters", "api", "core")

# Full contract names (as in pyproject.toml); import-linter prints "<name> BROKEN".
DOMAIN = "domain is pure"
PORTS = "ports only depend on domain"
SERVICES = "services only depend on domain and ports"
CORE = "core does not depend on application layers"
ADAPTERS = "adapters do not depend on api or services"
MAIN = "main only wires api, composition and core"
CLI = "cli only reaches adapters through composition"
API = "api does not import adapters (except deps) nor sqlalchemy"


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


def _broken_contracts(output: str) -> set[str]:
    """Contracts reported as BROKEN (format: '<contract name> BROKEN[ (n ignored imports)]')."""
    return {m.group(1) for m in re.finditer(r"^(.+?) BROKEN\b", output, flags=re.MULTILINE)}


def _make_package(
    root: Path, module: str, source: str, *, keep_deps_exception: bool = True
) -> None:
    """Build a minimal `app` package whose only content is one module with `source`.

    `api/deps.py` always imports the composition (its only allowed exception), so the contract's
    `ignore_imports` entry is matched and `unmatched_ignore_imports_alerting = "error"` does not
    fire; when the case is `api.deps` itself, `source` is appended to that import.
    """
    shutil.copy(BACKEND_DIR / "pyproject.toml", root / "pyproject.toml")
    app = root / "app"
    app.mkdir()
    (app / "__init__.py").write_text("")
    (app / "main.py").write_text("")
    (app / "composition.py").write_text("import app.adapters\n")
    (app / "cli.py").write_text("")
    for sub in SUBPACKAGES:
        (app / sub).mkdir()
        (app / sub / "__init__.py").write_text("")
    (app / "api" / "deps.py").write_text("import app.composition\n")
    if module == "api.deps" and keep_deps_exception:
        source = "import app.composition\n" + source
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


def _case(contract: str, module: str, *imports: str) -> list[tuple[str, str, str]]:
    return [(contract, module, f"import {name}\n") for name in imports]


VIOLATIONS: list[tuple[str, str, str]] = [
    # (full contract name, module, source). Each case must break ONLY that contract.
    *_case(
        DOMAIN,
        "domain.bad",
        *("app.services", "app.core", "app.ports", "app.adapters", "app.api", "app.main"),
        *("app.composition", "fastapi", "sqlalchemy", "pydantic", "pydantic_settings"),
        *("starlette", "httpx", "jwt", "argon2", "alembic"),
    ),
    *_case(
        PORTS,
        "ports.bad",
        *("app.services", "app.adapters", "app.core", "app.api", "app.main", "app.composition"),
        *("fastapi", "starlette", "sqlalchemy", "pydantic", "pydantic_settings"),
        *("jwt", "argon2", "alembic"),
    ),
    *_case(
        SERVICES,
        "services.bad",
        *("app.adapters", "app.api", "app.core", "app.main", "app.composition"),
        *("fastapi", "starlette", "sqlalchemy", "pydantic", "pydantic_settings"),
        *("jwt", "argon2", "alembic"),
    ),
    *_case(CORE, "core.bad", "app.api", "app.services", "app.adapters", "app.main"),
    *_case(
        ADAPTERS,
        "adapters.bad",
        *("app.api", "app.services", "app.main", "app.composition", "fastapi", "starlette"),
    ),
    *_case(
        MAIN,
        "main",
        *("app.adapters", "app.services", "app.ports", "app.domain"),
        *("sqlalchemy", "alembic", "argon2", "jwt"),
    ),
    *_case(CLI, "cli", "app.adapters", "sqlalchemy"),
    *_case(
        API,
        "api.bad",
        *("app.adapters", "app.composition", "sqlalchemy", "jwt", "argon2", "alembic"),
    ),
    # Modules added with the catalog/scan routes follow the same rules as their layer.
    *_case(API, "api.items", "app.composition"),
    *_case(API, "api.library", "app.adapters"),
    *_case(SERVICES, "services.scan_runner", "app.core"),
    *_case(SERVICES, "services.catalog", "app.adapters"),
    # The metadata feature: the use case and its ports stay free of the network and the adapters.
    *_case(SERVICES, "services.metadata_service", "app.adapters", "app.core", "pydantic"),
    *_case(SERVICES, "services.enrich_runner", "app.adapters"),
    *_case(PORTS, "ports.http_gateway", "app.adapters", "app.services"),
    *_case(PORTS, "ports.metadata_provider", "app.adapters", "pydantic"),
    *_case(PORTS, "ports.cover_store", "app.adapters", "app.core"),
    *_case(PORTS, "ports.translator", "app.adapters", "app.services", "pydantic"),
    *_case(DOMAIN, "domain.metadata", "app.ports", "app.adapters", "httpx"),
    *_case(ADAPTERS, "adapters.metadata_bad", "app.services", "app.api", "fastapi"),
    *_case(API, "api.series", "app.adapters"),
    # api.deps is allowed ONLY to import the composition: anything else is still forbidden.
    *_case(API, "api.deps", "app.adapters", "sqlalchemy", "jwt", "argon2", "alembic"),
]


@pytest.mark.parametrize(("contract", "module", "source"), VIOLATIONS)
def test_contract_is_enforced(tmp_path: Path, contract: str, module: str, source: str) -> None:
    _make_package(tmp_path, module, source)
    result = _lint(tmp_path)
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert f"{contract} BROKEN" in output, output
    assert _broken_contracts(output) == {contract}, output  # and nothing else


def _forbidden_by_contract() -> dict[str, list[str]]:
    config = tomllib.loads((BACKEND_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    return {
        c["name"]: c["forbidden_modules"]
        for c in config["tool"]["importlinter"]["contracts"]
        if c["type"] == "forbidden"
    }


def test_every_forbidden_module_has_a_violation_case() -> None:
    """tests/AGENTS.md: each item of `forbidden_modules` needs a case in VIOLATIONS."""
    covered = {(contract, source.split()[1].strip()) for contract, _, source in VIOLATIONS}
    missing = [
        (name, module)
        for name, modules in _forbidden_by_contract().items()
        for module in modules
        if (name, module) not in covered
    ]
    assert missing == []
    assert set(_forbidden_by_contract()) == {
        DOMAIN,
        PORTS,
        SERVICES,
        CORE,
        ADAPTERS,
        MAIN,
        CLI,
        API,
    }


def test_api_deps_may_import_the_composition(tmp_path: Path) -> None:
    _make_package(tmp_path, "api.deps", "import app.composition\n")
    result = _lint(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_api_deps_may_not_import_adapter_submodules(tmp_path: Path) -> None:
    _make_package(tmp_path, "api.deps", "import app.adapters.persistence.x\n")
    persistence = tmp_path / "app" / "adapters" / "persistence"
    persistence.mkdir()
    (persistence / "__init__.py").write_text("")
    (persistence / "x.py").write_text("")
    result = _lint(tmp_path)
    assert result.returncode != 0, result.stdout + result.stderr
    assert _broken_contracts(result.stdout + result.stderr) == {API}


def test_stale_ignore_import_is_reported(tmp_path: Path) -> None:
    """`unmatched_ignore_imports_alerting = "error"`: an exception that matches nothing fails."""
    _make_package(tmp_path, "api.deps", "", keep_deps_exception=False)
    result = _lint(tmp_path)
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "app.api.deps" in output, output


def test_main_may_import_api_composition_and_core(tmp_path: Path) -> None:
    _make_package(
        tmp_path,
        "main",
        "import app.api\nimport app.composition\nimport app.core\nimport fastapi\n",
    )
    result = _lint(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_composition_and_cli_via_composition_are_allowed(tmp_path: Path) -> None:
    _make_package(tmp_path, "composition", "import app.adapters\nimport app.core\n")
    (tmp_path / "app" / "cli.py").write_text("import app.composition\n")
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
    assert _broken_contracts(result.stdout + result.stderr) == {API}


def test_api_routers_may_use_services_and_domain(tmp_path: Path) -> None:
    _make_package(tmp_path, "api.items", "import app.services\nimport app.domain\n")
    result = _lint(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_api_may_use_fastapi_starlette_and_pydantic(tmp_path: Path) -> None:
    _make_package(tmp_path, "api.ok", "import fastapi\nimport starlette\nimport pydantic\n")
    result = _lint(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_services_may_use_threading_for_the_scan_runner(tmp_path: Path) -> None:
    _make_package(tmp_path, "services.scan_runner", "import threading\nimport app.ports\n")
    result = _lint(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_adapters_may_use_pyjwt_argon2_and_alembic(tmp_path: Path) -> None:
    _make_package(tmp_path, "adapters.ok", "import jwt\nimport argon2\nimport alembic\n")
    result = _lint(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_core_keys_may_be_used_by_composition_and_api(tmp_path: Path) -> None:
    _make_package(tmp_path, "composition", "import app.adapters\nimport app.core\n")
    (tmp_path / "app" / "api" / "csrf.py").write_text("import app.core\n")
    result = _lint(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
