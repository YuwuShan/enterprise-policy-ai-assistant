"""Start one role; use exec so Uvicorn receives stop signals."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("oa", "assistant"):
        raise SystemExit("usage: python deploy/container_start.py oa|assistant")
    role = sys.argv[1]
    if role == "oa":
        from oa.db import initialize
        initialize()
    port = "8001" if role == "oa" else "8000"
    command = [sys.executable, "-m", "uvicorn", f"{role}.main:app", "--host", "0.0.0.0", "--port", port]
    if role == "assistant":
        # Only trusted containers can reach this unpublished application port.
        command += ["--proxy-headers", "--forwarded-allow-ips", "*"]
    os.execv(sys.executable, command)


if __name__ == "__main__":
    main()
