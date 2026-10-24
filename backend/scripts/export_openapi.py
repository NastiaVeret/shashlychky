"""Print the OpenAPI schema as JSON. Used by `make types` to generate frontend TypeScript types.

Runs without a database or an API key: importing the app does not connect anywhere.
"""

import json
import sys

from app.main import app


def main() -> None:
    json.dump(app.openapi(), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
