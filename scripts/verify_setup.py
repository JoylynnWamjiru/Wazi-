"""Verify the Wazi development environment is correctly configured.

Run this after setting up Docker and installing dependencies:
    python scripts/verify_setup.py
"""

import sys
from pathlib import Path

from sqlalchemy import text

# Ensure the repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def check_imports() -> bool:
    """Verify all required packages import cleanly."""
    packages = [
        ("sqlalchemy", "SQLAlchemy ORM"),
        ("pgvector.sqlalchemy", "pgvector (SQLAlchemy extension)"),
        ("psycopg2", "psycopg2 (PostgreSQL driver)"),
        ("fastembed", "fastembed (ONNX embeddings)"),
        ("pymupdf", "PyMuPDF (PDF extraction)"),
        ("fastapi", "FastAPI"),
        ("uvicorn", "Uvicorn"),
    ]
    all_ok = True
    for module, name in packages:
        try:
            __import__(module)
            print(f"  ✓ {name}")
        except ImportError as e:
            print(f"  ✗ {name} — {e}")
            all_ok = False
    return all_ok


def check_models() -> bool:
    """Verify all SQLAlchemy models can be imported and inspected."""
    try:
        from src.shared.models import (
            Base, User, Session, Message, Dispute, Source, Chunk,
            GovernmentArm, ReportType, IngestionStatus, DisputeStatus,
        )
        tables = list(Base.metadata.tables.keys())
        print(f"  ✓ {len(tables)} tables defined: {', '.join(tables)}")
        print(f"  ✓ GovernmentArm values: {[a.value for a in GovernmentArm]}")
        print(f"  ✓ ReportType values: {[r.value for r in ReportType]}")
        print(f"  ✓ DisputeStatus values: {[s.value for s in DisputeStatus]}")
        return True
    except Exception as e:
        print(f"  ✗ Model import failed: {e}")
        return False


def check_database() -> bool:
    """Verify PostgreSQL connection and table creation."""
    try:
        from src.shared.database import init_db, get_session

        init_db()
        with get_session() as session:
            session.execute(text("SELECT 1"))
            print("  ✓ PostgreSQL connection successful")
            print("  ✓ All tables created (or already exist)")

        # Verify pgvector extension is enabled
        with get_session() as session:
            session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            session.commit()
        print("  ✓ pgvector extension enabled")
        return True
    except Exception as e:
        print(f"  ✗ Database connection failed: {e}")
        print("    Make sure Docker is running: docker compose up -d")
        print(f"    Connection string: check DATABASE_URL in your .env")
        return False


def main() -> None:
    print("=" * 56)
    print("Wazi — Environment Verification")
    print("=" * 56)

    print("\n[1] Checking installed packages...")
    imports_ok = check_imports()

    print("\n[2] Checking SQLAlchemy models...")
    models_ok = check_models()

    print("\n[3] Checking PostgreSQL connection...")
    db_ok = check_database()

    print("\n" + "=" * 56)
    if all([imports_ok, models_ok, db_ok]):
        print("✓ All checks passed! Wazi is ready for development.")
    else:
        print("✗ Some checks failed. See details above.")
    print("=" * 56)


if __name__ == "__main__":
    main()
