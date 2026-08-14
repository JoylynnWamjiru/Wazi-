"""Database migration — apply schema changes that ``create_all`` can't.

``Base.metadata.create_all()`` only creates tables that don't exist.  It
never alters existing tables, so new columns and constraints added to the
ORM models after the initial deploy need a real migration.  This script is
that migration.

Applies (idempotently):
  1. ``sources.content_hash`` column (SHA-256 of the downloaded PDF).
  2. ``uq_source_url`` UNIQUE constraint on ``sources.url`` — with a
     dedupe pre-check because a UNIQUE constraint fails if duplicates
     already exist.
  3. ``uq_dispute_one_per_user`` UNIQUE constraint on
     ``disputes(message_id, reported_by_user_id)``.

Usage:
    python scripts/migrate.py            # apply
    python scripts/migrate.py --dry-run  # report what WOULD change

Run on the VPS:
    cd /opt/wazi && /opt/wazi/venv/bin/python scripts/migrate.py
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text

from src.shared.database import get_session, init_db


def column_exists(session, table: str, column: str) -> bool:
    row = session.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}).first()
    return row is not None


def constraint_exists(session, name: str) -> bool:
    row = session.execute(text(
        "SELECT 1 FROM pg_constraint WHERE conname = :n"
    ), {"n": name}).first()
    return row is not None


def duplicate_urls(session) -> list[tuple[str, int]]:
    """Return (url, count) for URLs appearing more than once."""
    return session.execute(text(
        "SELECT url, COUNT(*) AS c FROM sources GROUP BY url HAVING COUNT(*) > 1"
    )).fetchall()


def migrate(dry_run: bool = False) -> dict:
    init_db()
    report = {"actions": [], "dry_run": dry_run}

    with get_session() as session:
        # 1. Add content_hash column.
        if not column_exists(session, "sources", "content_hash"):
            report["actions"].append("ADD COLUMN sources.content_hash VARCHAR(64)")
            if not dry_run:
                session.execute(text(
                    "ALTER TABLE sources ADD COLUMN content_hash VARCHAR(64)"
                ))

        # 2. Dedupe sources.url before adding the UNIQUE constraint.
        if not constraint_exists(session, "uq_source_url"):
            dups = duplicate_urls(session)
            if dups:
                report["actions"].append(
                    f"DELETE duplicate sources (keeping MIN(id) per URL): {len(dups)} urls"
                )
                if not dry_run:
                    session.execute(text(
                        "DELETE FROM sources WHERE id NOT IN "
                        "(SELECT MIN(id) FROM sources GROUP BY url)"
                    ))
            report["actions"].append("ADD CONSTRAINT uq_source_url UNIQUE (url)")
            if not dry_run:
                session.execute(text(
                    "ALTER TABLE sources ADD CONSTRAINT uq_source_url UNIQUE (url)"
                ))

        # 3. Add dispute dedup constraint.
        if not constraint_exists(session, "uq_dispute_one_per_user"):
            report["actions"].append(
                "ADD CONSTRAINT uq_dispute_one_per_user UNIQUE (message_id, reported_by_user_id)"
            )
            if not dry_run:
                session.execute(text(
                    "ALTER TABLE disputes ADD CONSTRAINT uq_dispute_one_per_user "
                    "UNIQUE (message_id, reported_by_user_id)"
                ))

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Wazi DB migration.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what WOULD change without applying.")
    args = parser.parse_args()

    report = migrate(dry_run=args.dry_run)

    verb = "Would apply" if report["dry_run"] else "Applied"
    if not report["actions"]:
        print("Schema already up to date — nothing to migrate.")
    else:
        print(f"{verb}:")
        for action in report["actions"]:
            print(f"  - {action}")


if __name__ == "__main__":
    main()
