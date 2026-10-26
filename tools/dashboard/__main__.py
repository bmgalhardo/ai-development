"""Run separately with: python -m tools.dashboard."""

import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Read-only issue board; leaves workers untouched")
    parser.add_argument("--host", default="0.0.0.0", help="bind address (default: all interfaces)")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    uvicorn.run("tools.dashboard.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
