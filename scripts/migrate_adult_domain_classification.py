#!/usr/bin/env python3
"""
Add cached adult-classification columns to domains and create the
domain_adult_overrides table.
Safe for SQLite and Postgres; skips columns/tables that already exist.
"""

from pathlib import Path
import sys

from sqlalchemy import inspect, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import engine
from backend.models import DomainAdultOverride


MIGRATIONS = [
    ("domains", "domain_niche", "VARCHAR(20)"),
    ("domains", "adult_method", "VARCHAR(50)"),
    ("domains", "adult_confidence", "FLOAT"),
    ("domains", "adult_detail", "TEXT"),
    ("domains", "adult_classified_at", "DATETIME"),
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

    table = DomainAdultOverride.__tablename__
    if inspect(engine).has_table(table):
        print(f"[skip] table {table} already exists")
    else:
        DomainAdultOverride.__table__.create(bind=engine)
        print(f"[ok] created table {table}")


if __name__ == "__main__":
    main()
