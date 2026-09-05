from __future__ import annotations

from pathlib import Path

import pytest

from scripts.container_smoke import POSTGRES_IMAGE
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
