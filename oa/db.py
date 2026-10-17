import sqlite3
from contextlib import closing
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "oa.db"


def connect():
    if not DB_PATH.is_file():
        raise RuntimeError("数据库不存在，请先执行 python -m oa.db")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS budgets (
                department TEXT NOT NULL,
                month TEXT NOT NULL,
                total_cents INTEGER NOT NULL CHECK (total_cents >= 0),
                used_cents INTEGER NOT NULL
                    CHECK (used_cents >= 0 AND used_cents <= total_cents),
                PRIMARY KEY (department, month)
            );

            CREATE TABLE IF NOT EXISTS suppliers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                status TEXT NOT NULL
                    CHECK (status IN ('active', 'inactive'))
            );
        """)

        conn.executemany("""
            INSERT INTO budgets
                (department, month, total_cents, used_cents)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (department, month) DO NOTHING
        """, [
            ("研发部", "2026-10", 10_000_000, 2_500_000),
            ("市场部", "2026-10", 5_000_000, 1_200_000),
            ("行政部", "2026-10", 3_000_000, 800_000),
        ])

        conn.executemany("""
            INSERT INTO suppliers (id, name, category, status)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (id) DO NOTHING
        """, [
            ("SUP001", "华信办公（模拟）", "办公设备", "active"),
            ("SUP002", "联达数码（模拟）", "电脑", "active"),
            ("SUP003", "旧城数码（模拟）", "电脑", "inactive"),
        ])

        conn.commit()

    print(f"数据库初始化完成：{DB_PATH}")


if __name__ == "__main__":
    initialize()