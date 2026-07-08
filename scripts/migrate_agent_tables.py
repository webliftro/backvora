#!/usr/bin/env python3
"""Create operational agent tables for existing SQLite installs."""

from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import settings  # noqa: E402


def db_path() -> Path:
    if not settings.database_url.startswith("sqlite:///"):
        raise RuntimeError("This migration script only supports SQLite DATABASE_URL values")
    path = settings.database_url.replace("sqlite:///", "", 1)
    return Path(path) if Path(path).is_absolute() else ROOT / path


def main() -> None:
    path = db_path()
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS agent_sessions (
                id VARCHAR(36) PRIMARY KEY,
                user_id VARCHAR(36) NOT NULL,
                title VARCHAR(255),
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                deleted_at DATETIME,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS ix_agent_sessions_user_id ON agent_sessions(user_id);

            CREATE TABLE IF NOT EXISTS agent_messages (
                id VARCHAR(36) PRIMARY KEY,
                session_id VARCHAR(36) NOT NULL,
                user_id VARCHAR(36) NOT NULL,
                role VARCHAR(20) NOT NULL,
                content TEXT NOT NULL,
                meta JSON,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                deleted_at DATETIME,
                FOREIGN KEY(session_id) REFERENCES agent_sessions(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS ix_agent_messages_session_id ON agent_messages(session_id);
            CREATE INDEX IF NOT EXISTS ix_agent_messages_user_id ON agent_messages(user_id);

            CREATE TABLE IF NOT EXISTS agent_action_audits (
                id VARCHAR(36) PRIMARY KEY,
                session_id VARCHAR(36) NOT NULL,
                user_id VARCHAR(36) NOT NULL,
                action_name VARCHAR(100) NOT NULL,
                permission VARCHAR(20) NOT NULL,
                requires_confirmation BOOLEAN NOT NULL DEFAULT 0,
                confirmed_at DATETIME,
                status VARCHAR(30) NOT NULL DEFAULT 'pending',
                input_json JSON,
                result_json JSON,
                error TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                deleted_at DATETIME,
                FOREIGN KEY(session_id) REFERENCES agent_sessions(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS ix_agent_action_audits_session_id ON agent_action_audits(session_id);
            CREATE INDEX IF NOT EXISTS ix_agent_action_audits_user_id ON agent_action_audits(user_id);
            CREATE INDEX IF NOT EXISTS ix_agent_action_audits_action_name ON agent_action_audits(action_name);
            """
        )
        conn.commit()
    finally:
        conn.close()
    print(f"Agent tables ready in {path}")


if __name__ == "__main__":
    main()
