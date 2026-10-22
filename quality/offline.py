"""One offline entry point. No .env reading, model calls or OA network calls."""
import os
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def blocked(*args, **kwargs):
    raise AssertionError("Offline test attempted a network connection")


def main():
    # These patches last only for this Python process and do not edit .env.
    with patch.dict(os.environ, {"DASHSCOPE_API_KEY":"offline-placeholder",
                               "DASHSCOPE_BASE_URL":"https://example.invalid/v1",
                               "CHAT_MODEL":"offline", "EMBEDDING_MODEL":"offline"}), \
         patch("dotenv.load_dotenv", return_value=False), \
         patch("socket.socket.connect", side_effect=blocked), \
         patch("socket.socket.connect_ex", side_effect=blocked), \
         patch("socket.create_connection", side_effect=blocked):
        with patch.object(sys, "argv", ["check_day3.py", "--expected-docs","50","--expected-chunks","150"]):
            runpy.run_path(str(ROOT / "check_day3.py"), run_name="__main__")
        suite = unittest.defaultTestLoader.loadTestsFromNames(["check_day4","check_day5","check_day8"])
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
