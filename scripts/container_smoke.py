"""Smoke-test the exact Thingdex candidate with a real PostgreSQL service."""

from __future__ import annotations

import subprocess
import sys
import time
import uuid


POSTGRES_IMAGE = "postgres:15@sha256:9b1d34adbce1dd07ee6e94b4a2cf698884b89bd44a6c9c12f5da8f3acbfe4957"


def run(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


def container_state(container: str) -> str:
    """Return non-sensitive lifecycle facts suitable for public CI output."""
    return run(
        "docker",
        "inspect",
        "--format",
        (
            "status={{.State.Status}} exit={{.State.ExitCode}} "
            "health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}"
        ),
        container,
    )


def failure_categories(container: str) -> str:
    """Classify startup logs without emitting their potentially sensitive text."""
    result = subprocess.run(
        ["docker", "logs", container],
        capture_output=True,
        text=True,
    )
    content = (result.stdout + result.stderr).lower()
    markers = {
        "entrypoint-format": ("exec format error", "bad interpreter"),
        "missing-runtime-command": ("not found",),
        "database-connection": (
            "operationalerror",
            "connection refused",
            "could not translate host name",
            "password authentication failed",
        ),
        "migration": ("alembic.util.exc", "failed:"),
        "permission": ("permission denied",),
        "application-startup": ("application startup failed",),
    }
    matches = [
        category
        for category, needles in markers.items()
        if any(needle in content for needle in needles)
    ]
    if "modulenotfounderror" in content or "importerror" in content:
        allowed_modules = (
            "alembic",
            "fastapi",
            "httpx",
            "pydantic",
            "psycopg",
            "psycopg_binary",
            "sqlalchemy",
            "starlette",
            "thingdex",
            "uvicorn",
        )
        module = next(
            (
                candidate
                for candidate in allowed_modules
                if f"no module named '{candidate}" in content
                or f'no module named "{candidate}' in content
            ),
            "unknown",
        )
        matches.append(f"python-import:{module}")
    return ",".join(matches) or "unclassified"


def main() -> None:
    image = sys.argv[1]
    suffix = uuid.uuid4().hex[:10]
    network = f"thingdex-smoke-{suffix}"
    database = f"thingdex-db-{suffix}"
    application = ""
    run("docker", "network", "create", network)
    try:
        run(
            "docker", "run", "-d", "--name", database, "--network", network,
            "-e", "POSTGRES_USER=thingdex", "-e", "POSTGRES_PASSWORD=thingdex",
            "-e", "POSTGRES_DB=thingdex", POSTGRES_IMAGE,
        )
        deadline = time.monotonic() + 60
        while True:
            ready = subprocess.run(
                ["docker", "exec", database, "pg_isready", "-U", "thingdex", "-d", "thingdex"],
                capture_output=True,
            )
            if ready.returncode == 0:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("PostgreSQL did not become ready")
            time.sleep(1)
        application = run(
            "docker", "run", "-d", "--network", network,
            "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
            "-e", f"DATABASE_URL=postgresql+psycopg://thingdex:thingdex@{database}:5432/thingdex",
            "-e", "LABEL_PRINTING_ENABLED=false", image,
        )
        deadline = time.monotonic() + 90
        while True:
            ready = subprocess.run(
                [
                    "docker", "exec", application, "python", "-c",
                    (
                        "import http.client,json; "
                        "connection=http.client.HTTPConnection("
                        "'127.0.0.1',8000,timeout=3); "
                        "connection.request('GET','/health/ready'); "
                        "response=connection.getresponse(); "
                        "assert response.status == 200; "
                        "assert json.loads(response.read()).get('status') == 'ok'"
                    ),
                ],
                capture_output=True,
                text=True,
            )
            if ready.returncode == 0:
                break
            state = container_state(application)
            if not state.startswith("status=running "):
                category = failure_categories(application)
                raise RuntimeError(
                    "Thingdex candidate stopped before readiness "
                    f"({state} category={category})"
                )
            if time.monotonic() >= deadline:
                tcp = subprocess.run(
                    [
                        "docker", "exec", application, "python", "-c",
                        (
                            "import socket; connection=socket.create_connection("
                            "('127.0.0.1',8000),timeout=3); connection.close()"
                        ),
                    ],
                    capture_output=True,
                    text=True,
                )
                raise RuntimeError(
                    "Thingdex candidate did not become ready "
                    f"({state} tcp_probe_exit={tcp.returncode})"
                )
            time.sleep(1)
        uid = run("docker", "exec", application, "python", "-c", "import os; print(os.getuid())")
        if uid == "0":
            raise RuntimeError("Thingdex candidate runs as root")
    finally:
        for container in (application, database):
            if container:
                subprocess.run(["docker", "rm", "-f", container], check=False)
        subprocess.run(["docker", "network", "rm", network], check=False)


if __name__ == "__main__":
    main()
