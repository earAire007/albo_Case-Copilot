"""stdio entrypoint: one server process per case, bound to that case's customer.

Usage: python -m mcp_server --customer-id cus_001
"""

import argparse
from pathlib import Path

from backend.mock_core.repository import DEFAULT_DATA_DIR, JsonCoreRepository
from mcp_server.server import create_server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--customer-id", required=True)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args()
    create_server(JsonCoreRepository(args.data_dir), args.customer_id).run(transport="stdio")


if __name__ == "__main__":
    main()
