# Data Retention Policy — Wazi

> Effective: 2026-08-11 · Owner: Backend/AI (Joyline)

Wazi's guiding principle is **data minimisation**: hold the least data, for
the shortest time, needed to answer citizens and keep answers accountable.
This document is the single source of truth for *what* we keep, *how long*,
and *why* — enforced automatically by `scripts/retention.py`.

## What we never store

- **No phone numbers.** A citizen's WhatsApp id is HMAC-SHA256 hashed with a
  secret salt on receipt and discarded; only the 64-char hash is persisted.
  See `src/api/middleware/identity.py`.
- **No identity ↔ dispute join.** Disputes record the reporter's hashed user
  id for anti-bot diversity checks but carry no path back to the disputed
  question's author. The system cannot produce "who reported what".

## Retention windows

| Data | Table | Retained for | Rationale |
|------|-------|--------------|-----------|
| Chat messages (Q&A) | `messages` | **90 days** | Long enough to debug answers and let a citizen continue a conversation; short enough to minimise exposure. |
| Dispute reports | `disputes` | **365 days** | Moderation and escalation (e.g. to EACC) can take months; keeping a year supports audit of how a disputed answer was handled. |
| Source registry | `sources` | **Indefinite** | Public-document metadata, no personal data. |
| Corpus chunks | `chunks` | **Indefinite** | Derived from public PDFs, no personal data. |
| Hashed users | `users` | Tied to messages | A user row with no messages inside the window carries no useful signal; pruned once its last message ages out (future extension). |

## The 90-day / 365-day interaction (important)

A dispute (`disputes.message_id`) points at the answer it contests. Because
disputes are kept **longer** than messages, naïvely deleting a 90-day-old
message could orphan a still-live dispute and break referential integrity.

The retention job therefore runs in a fixed order:

1. **Delete expired disputes first** — `disputes.created_at` older than 365 days.
2. **Delete expired messages that are no longer referenced** — `messages.created_at`
   older than 90 days **and not referenced by any surviving dispute**. A message
   under active/recent dispute is preserved until that dispute itself expires,
   at which point a later run removes both.

This guarantees no orphaned disputes and no FK violations, and it means a
disputed answer is never silently deleted while its complaint is still open.

## How it runs

Manual / dry-run:

```bash
python scripts/retention.py --dry-run   # report what WOULD be deleted
python scripts/retention.py             # actually delete
```

Scheduled on the VPS (daily at 03:15) via cron:

```cron
15 3 * * * cd /opt/wazi && /opt/wazi/venv/bin/python scripts/retention.py >> /var/log/wazi-retention.log 2>&1
```

Or as a systemd timer (`wazi-retention.timer` + `.service`) — see the VPS
runbook. Either way the job is **idempotent**: running it twice in a row
deletes nothing the second time.

## Responsible-computing alignment

This policy operationalises Wazi's privacy-by-design posture and supports
compliance with Kenya's Data Protection Act (2019) principle of storage
limitation. It is the concrete, automated backing for the retention claims
made in `docs/problem-statement.md` (§ Responsible Computing Considerations)
and the strategic plan's § Responsible Computing.
