"""Enforce Wazi's data-retention policy (see docs/DATA_RETENTION.md).

Deletes, in a fixed order that preserves referential integrity:
  1. disputes older than DISPUTE_RETENTION_DAYS (default 365)
  2. messages older than MESSAGE_RETENTION_DAYS (default 90) that are NOT
     referenced by any surviving dispute

Idempotent: a second run immediately after deletes nothing. Safe to schedule
daily via cron/systemd on the VPS.

Usage:
    python scripts/retention.py            # delete
    python scripts/retention.py --dry-run  # report only, delete nothing
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import func

from src.shared.database import get_session
from src.shared.models import Dispute, Message

MESSAGE_RETENTION_DAYS = 90
DISPUTE_RETENTION_DAYS = 365


def purge(
    now: datetime | None = None,
    message_days: int = MESSAGE_RETENTION_DAYS,
    dispute_days: int = DISPUTE_RETENTION_DAYS,
    dry_run: bool = False,
) -> dict:
    """Apply the retention policy. Returns counts of (would-be) deletions.

    ``now`` is injectable so tests can control the clock.
    """
    now = now or datetime.now(timezone.utc)
    message_cutoff = now - timedelta(days=message_days)
    dispute_cutoff = now - timedelta(days=dispute_days)

    with get_session() as session:
        # 1. Expired disputes first, so step 2 sees the final reference set.
        expired_disputes = session.query(Dispute).filter(
            Dispute.created_at < dispute_cutoff
        )
        disputes_deleted = expired_disputes.count()

        # 2. Expired messages NOT referenced by any surviving dispute.
        #    Recompute the surviving-dispute set AFTER the step-1 deletion so a
        #    message whose only dispute just expired becomes eligible.
        if dry_run:
            surviving_dispute_msg_ids = session.query(Dispute.message_id).filter(
                Dispute.created_at >= dispute_cutoff
            )
        else:
            expired_disputes.delete(synchronize_session=False)
            surviving_dispute_msg_ids = session.query(Dispute.message_id)

        expired_messages = session.query(Message).filter(
            Message.created_at < message_cutoff,
            Message.id.notin_(surviving_dispute_msg_ids),
        )
        messages_deleted = expired_messages.count()

        if not dry_run:
            expired_messages.delete(synchronize_session=False)

    return {
        "dry_run": dry_run,
        "now": now.isoformat(),
        "message_cutoff": message_cutoff.isoformat(),
        "dispute_cutoff": dispute_cutoff.isoformat(),
        "disputes_deleted": disputes_deleted,
        "messages_deleted": messages_deleted,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Enforce Wazi data-retention policy.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be deleted without deleting anything.",
    )
    args = parser.parse_args()

    result = purge(dry_run=args.dry_run)

    verb = "Would delete" if result["dry_run"] else "Deleted"
    print(f"[retention] cutoff messages<{result['message_cutoff']} "
          f"disputes<{result['dispute_cutoff']}")
    print(f"[retention] {verb}: "
          f"{result['disputes_deleted']} disputes, "
          f"{result['messages_deleted']} messages")


if __name__ == "__main__":
    main()
