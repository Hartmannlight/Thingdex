from __future__ import annotations

from pathlib import Path

import pytest

from scripts.container_smoke import POSTGRES_IMAGE, container_state, failure_categories
from scripts.release import context
from scripts.security_gate import findings


def test_container_smoke_uses_an_immutable_postgres_image() -> None:
    name, digest = POSTGRES_IMAGE.split("@sha256:", 1)
    assert name == "postgres:15"
    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")


def test_container_health_checks_bypass_environment_proxies() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    smoke = Path("scripts/container_smoke.py").read_text(encoding="utf-8")
    assert "http.client.HTTPConnection" in dockerfile
    assert "http.client.HTTPConnection" in smoke
    assert "urllib.request" not in dockerfile
    assert "urllib.request" not in smoke


def test_container_runtime_can_import_application_during_migrations() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    entrypoint = Path("scripts/docker-entrypoint.sh").read_text(encoding="utf-8")
    assert "PYTHONPATH=/app" in dockerfile
    assert "python -m alembic upgrade head" in entrypoint


def test_container_runtime_excludes_build_tooling() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    command = "python -m pip uninstall -y pip setuptools wheel jaraco.context"
    assert f"/app/.venv/bin/{command}" in dockerfile
    assert command in dockerfile


def test_container_diagnostics_expose_only_lifecycle_facts(monkeypatch) -> None:
    captured = []

    def fake_run(*args: str) -> str:
        captured.extend(args)
        return "status=exited exit=1 health=none"

    monkeypatch.setattr("scripts.container_smoke.run", fake_run)
    assert container_state("safe-id") == "status=exited exit=1 health=none"
    assert captured[-1] == "safe-id"
    assert "{{.Config.Env}}" not in captured
    assert "{{json .}}" not in captured


def test_container_log_diagnostics_emit_categories_not_log_text(monkeypatch) -> None:
    class Result:
        stdout = "sqlalchemy.exc.OperationalError: connection refused at secret-host"
        stderr = ""

    monkeypatch.setattr("scripts.container_smoke.subprocess.run", lambda *_a, **_k: Result())
    category = failure_categories("safe-id")
    assert category == "database-connection"
    assert "secret-host" not in category


def test_container_log_diagnostics_allowlist_missing_module_names(monkeypatch) -> None:
    class KnownResult:
        stdout = "ModuleNotFoundError: No module named 'uvicorn'"
        stderr = ""

    monkeypatch.setattr(
        "scripts.container_smoke.subprocess.run", lambda *_a, **_k: KnownResult()
    )
    assert failure_categories("safe-id") == "python-import:uvicorn"

    class UnknownResult:
        stdout = "ModuleNotFoundError: No module named 'customer_secret_module'"
        stderr = ""

    monkeypatch.setattr(
        "scripts.container_smoke.subprocess.run", lambda *_a, **_k: UnknownResult()
    )
    assert failure_categories("safe-id") == "python-import:unknown"


def test_release_context_rejects_feature_branches(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/feature")
    monkeypatch.setenv("GITHUB_RUN_ID", "1")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    with pytest.raises(RuntimeError, match="restricted"):
        context()


def test_security_gate_blocks_fixable_high_findings() -> None:
    report = {
        "Results": [
            {
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "CVE-TEST",
                        "PkgName": "fixture",
                        "Severity": "HIGH",
                        "FixedVersion": "2",
                    }
                ]
            }
        ]
    }
    assert findings(report)[0] == [("CVE-TEST", "fixture")]
