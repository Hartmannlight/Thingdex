"""Smoke-test the exact Thingdex candidate with a real PostgreSQL service."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import uuid


POSTGRES_IMAGE = "postgres:15@sha256:9b1d34adbce1dd07ee6e94b4a2cf698884b89bd44a6c9c12f5da8f3acbfe4957"


def run(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


def main() -> None:
    image = sys.argv[1]
    suffix = uuid.uuid4().hex[:10]
    network = f"thingdex-smoke-{suffix}"
    database = f"thingdex-db-{suffix}"
    application = ""
    Path("artifacts").mkdir(exist_ok=True)
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
            "-e", "LABEL_PRINTING_ENABLED=false", "-p", "127.0.0.1::8000", image,
        )
        binding = run("docker", "port", application, "8000/tcp").splitlines()[0]
        deadline = time.monotonic() + 90
        while True:
            try:
                with urllib.request.urlopen(f"http://{binding}/health/ready", timeout=3) as response:
                    status = response.status
                    payload = json.load(response)
                if status == 200:
                    break
            except (OSError, ValueError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(1)
        if payload.get("status") != "ready":
            raise RuntimeError(f"Unexpected readiness payload: {payload}")
        uid = run("docker", "exec", application, "python", "-c", "import os; print(os.getuid())")
        if uid == "0":
            raise RuntimeError("Thingdex candidate runs as root")
    finally:
        for container in (application, database):
            if container:
                logs = subprocess.run(["docker", "logs", container], capture_output=True, text=True)
                Path(f"artifacts/{container[:12]}.log").write_text(logs.stdout + logs.stderr, encoding="utf-8")
                subprocess.run(["docker", "rm", "-f", container], check=False)
        subprocess.run(["docker", "network", "rm", network], check=False)


if __name__ == "__main__":
    main()
