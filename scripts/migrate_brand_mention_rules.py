#!/usr/bin/env python3
"""
Add brand mention rule columns to publisher_rules and orders tables.
Safe for SQLite and Postgres; skips columns that already exist.
"""

from pathlib import Path
import sys

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import engine


MIGRATIONS = [
    ("publisher_rules", "brand_mentions_scope", "VARCHAR(20)"),
    ("publisher_rules", "brand_mentions_brands", "TEXT"),
    ("publisher_rules", "brand_mentions_in_title", "BOOLEAN"),
    ("publisher_rules", "brand_mentions_body_count", "INTEGER"),
    ("orders", "brand_mentions_scope", "VARCHAR(20)"),
    ("orders", "brand_mentions_brands", "TEXT"),
    ("orders", "brand_mentions_in_title", "BOOLEAN"),
    ("orders", "brand_mentions_body_count", "INTEGER"),
]


def _has_column(conn, table_name: str, column_name: str) -> bool:
    inspector = conn.dialect.get_columns(conn, table_name)
    return any(col.get("name") == column_name for col in inspector)


def main() -> None:
    with engine.begin() as conn:
        for table_name, column_name, column_type in MIGRATIONS:
            if _has_column(conn, table_name, column_name):
                print(f"[skip] {table_name}.{column_name} already exists")
                continue
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
            print(f"[ok] added {table_name}.{column_name}")


if __name__ == "__main__":
    main()
