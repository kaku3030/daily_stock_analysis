"""Launch the Stock Razor realtime-monitor MCP server over stdio."""

import os
import runpy
from pathlib import Path


def main():
    server_path = Path(__file__).with_name("server.py")
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    runpy.run_path(str(server_path), run_name="__main__")


if __name__ == "__main__":
    main()
