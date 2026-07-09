#!/usr/bin/env python3
"""Create campaign-domain exclusion table for existing installs."""

from pathlib import Path
import sys

from sqlalchemy import inspect

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import engine
from backend.models import CampaignDomainExclusion


def main() -> None:
    table = CampaignDomainExclusion.__tablename__
    if inspect(engine).has_table(table):
        print(f"[skip] table {table} already exists")
        return
    CampaignDomainExclusion.__table__.create(bind=engine)
    print(f"[ok] created table {table}")


if __name__ == "__main__":
    main()
