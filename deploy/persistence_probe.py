"""Create/read a separate probe table; never change budget or supplier rows."""
import argparse
from contextlib import closing
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from oa.db import connect


def run(action):
    with closing(connect()) as connection:
        if action == "write":
            connection.execute("CREATE TABLE IF NOT EXISTS deployment_probe (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
            value = uuid4().hex
            connection.execute("INSERT INTO deployment_probe(id, value) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET value = excluded.value", (value,))
            connection.commit()
        else:
            row = connection.execute("SELECT value FROM deployment_probe WHERE id = 1").fetchone()
            if row is None:
                raise RuntimeError("Run the write probe first")
            value = row[0]
        print(value)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("write", "read"))
    run(parser.parse_args().action)
