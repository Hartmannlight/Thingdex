import json
from pathlib import Path

from thingdex.main import app


def main() -> None:
    contract_path = Path("openapi.json")
    committed = json.loads(contract_path.read_text(encoding="utf-8"))
    generated = app.openapi()
    if committed != generated:
        raise SystemExit(
            "openapi.json is stale; run "
            "`poetry run python scripts/export_openapi.py openapi.json` and update the SDK contract"
        )
    print("OpenAPI contract is up to date")


if __name__ == "__main__":
    main()
