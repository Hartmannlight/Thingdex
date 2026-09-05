from __future__ import annotations

import os
import signal
import time

from thingdex.db import SessionLocal
from thingdex.print_intents import PrintHubConnector, deliver_one


def main() -> None:
    interval = max(0.1, float(os.getenv("THINGDEX_PRINT_WORKER_INTERVAL_SECONDS", "1")))
    max_attempts = max(1, int(os.getenv("THINGDEX_PRINT_MAX_ATTEMPTS", "10")))
    stopping = False

    def stop(_signum, _frame) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    connector = PrintHubConnector()
    while not stopping:
        worked = deliver_one(SessionLocal, connector, max_attempts=max_attempts)
        if not worked:
            time.sleep(interval)


if __name__ == "__main__":
    main()
