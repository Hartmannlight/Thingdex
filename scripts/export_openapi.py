import json
from pathlib import Path

from thingdex.main import app


def main() -> None:
    openapi = app.openapi()
    output_path = Path("openapi.json")
    output_path.write_text(json.dumps(openapi, indent=2), encoding="utf-8")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
