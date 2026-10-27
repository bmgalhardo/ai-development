"""Run separately with: python -m tools.dashboard."""

import argparse
import os

import uvicorn

from tools.settings import load_env


def main():
    load_env()
    parser = argparse.ArgumentParser(description="Read-only issue board; leaves workers untouched")
    parser.add_argument("--host", default=os.environ.get("WORK_DASHBOARD_HOST", "127.0.0.1"),
                        help="bind address (default: WORK_DASHBOARD_HOST, else this host only)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("WORK_DASHBOARD_PORT", "8765")))
    args = parser.parse_args()
    uvicorn.run("tools.dashboard.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
