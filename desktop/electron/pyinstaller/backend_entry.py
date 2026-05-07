import argparse
import os
from pathlib import Path

import uvicorn


def parse_args():
    parser = argparse.ArgumentParser(description="CyclopsCmd packaged backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--data-dir", default=None)
    return parser.parse_args()


def main():
    args = parse_args()
    data_dir = Path(args.data_dir or os.getcwd()).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(data_dir)

    from app import app as fastapi_app

    uvicorn.run(fastapi_app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
