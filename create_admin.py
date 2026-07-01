#!/usr/bin/env python3
"""Create an admin user from command line."""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from backend.database import SessionLocal, init_db
from backend.models import User
from backend.auth import hash_password


def main():
    parser = argparse.ArgumentParser(description="Create admin user")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--name", default="Admin")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == args.email).first():
            print(f"User {args.email} already exists")
            sys.exit(1)
        user = User(email=args.email, password_hash=hash_password(args.password), name=args.name)
        db.add(user)
        db.commit()
        print(f"Created user: {args.email} (id: {user.id})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
