"""Restore a backup into a new, separate file and verify its tables; never replace live OA."""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3
from uuid import uuid4


def restore_check(source_path):
    source_path = Path(source_path).resolve(strict=True)
    restored = source_path.with_name(source_path.stem + "-restore-" + uuid4().hex[:8] + ".db")
    # Reserve the exact new file; refuse any accidental overwrite.
    with restored.open("xb"):
        pass
    restored.chmod(0o600)
    with closing(sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True)) as source, \
         closing(sqlite3.connect(restored)) as destination:
        source.backup(destination)
        if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Restored database failed integrity check")
        counts = {table: destination.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in ("budgets", "suppliers")}
    return restored, counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("backup")
    args = parser.parse_args()
    path, counts = restore_check(args.backup)
    print(f"Restored into isolated file: {path}; rows: {counts}. Live OA unchanged.")
