"""ONPay V2 Secure Database Reset Utility.

Safely resets all student operational data while strictly preserving schemas,
Alembic migration history, admin accounts, and system configuration.
Mandates a verified backup prior to execution.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import MetaData, create_engine, inspect, select, text
from sqlalchemy.engine import Engine

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.config import settings
from scripts.backup_db import mask_url, perform_backup

# Tables to preserve
PRESERVED_TABLES = {
    "alembic_version",
    "admin_users",
    "admin_sessions",
    "admin_audit_logs",
    "admin_qr_codes",
}

# Tables to truncate/delete in strict leaf-to-root foreign key order
OPERATIONAL_TABLES = [
    "user_login_events",
    "messages",
    "conversations",
    "friend_requests",
    "friendships",
    "status_events",
    "payment_attempts",
    "points_ledger",
    "reports",
    "blocks",
    "notifications",
    "subscription_requests",
    "subscriptions",
    "match_requests",
    "exchanges",
    "listings",
    "login_sessions",
    "otp_challenges",
    "users",
]


def safe_reset(
    db_url: str | None = None,
    confirm_flag: bool = False,
    skip_backup: bool = False,
) -> None:
    if not confirm_flag:
        print(
            "ERROR: Destructive database reset requires explicit confirmation flag:\n"
            "  --confirm-reset-i-understand-data-loss\n"
            "Aborting without making changes.",
            file=sys.stderr,
        )
        sys.exit(1)

    target_url = db_url or settings.database_url
    print(f"\n=======================================================")
    print(f"  TARGET DATABASE: {mask_url(target_url)}")
    print(f"=======================================================\n")

    # Step 1: Pre-reset backup
    if not skip_backup:
        print("[Reset Safety] Creating mandatory pre-reset backup...")
        backup_path = perform_backup(db_url=target_url, verify_restore=True)
        print(f"[Reset Safety] Verified backup confirmed at: {backup_path}\n")

    connect_args = {"check_same_thread": False} if target_url.startswith("sqlite") else {}
    engine: Engine = create_engine(target_url, connect_args=connect_args)

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    # Step 2: Record before counts
    before_counts: dict[str, int] = {}
    with engine.connect() as conn:
        for tbl in existing_tables:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar() or 0
            before_counts[tbl] = count

    print("[Reset] Current table record counts:")
    for tbl, cnt in before_counts.items():
        preserved = "(PRESERVED)" if tbl in PRESERVED_TABLES else "(OPERATIONAL - WILL RESET)"
        print(f"  - {tbl}: {cnt} rows {preserved}")

    # Step 3: Perform reset
    print("\n[Reset] Deleting operational student data...")
    with engine.begin() as conn:
        if target_url.startswith("sqlite"):
            conn.execute(text("PRAGMA foreign_keys = OFF;"))
            for tbl in OPERATIONAL_TABLES:
                if tbl in existing_tables:
                    conn.execute(text(f"DELETE FROM {tbl};"))
            conn.execute(text("PRAGMA foreign_keys = ON;"))
        else:
            # PostgreSQL / NeonDB
            tables_to_truncate = [tbl for tbl in OPERATIONAL_TABLES if tbl in existing_tables]
            if tables_to_truncate:
                stmt = f"TRUNCATE TABLE {', '.join(tables_to_truncate)} CASCADE;"
                conn.execute(text(stmt))

    # Step 4: Verify post-reset row counts
    print("\n[Reset] Verifying post-reset row counts...")
    failed = False
    with engine.connect() as conn:
        for tbl in OPERATIONAL_TABLES:
            if tbl in existing_tables:
                remaining = conn.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar() or 0
                if remaining != 0:
                    print(f"  FAILED: {tbl} still has {remaining} rows!", file=sys.stderr)
                    failed = True
                else:
                    print(f"  OK: {tbl} is clean (0 rows)")

        # Verify preserved tables are untouched
        for tbl in PRESERVED_TABLES:
            if tbl in existing_tables:
                after_cnt = conn.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar() or 0
                if after_cnt != before_counts[tbl]:
                    print(f"  WARNING: Preserved table {tbl} count changed: {before_counts[tbl]} -> {after_cnt}")
                else:
                    print(f"  PRESERVED: {tbl} untouched ({after_cnt} rows)")

    if failed:
        raise RuntimeError("Database reset verification failed: non-zero rows detected in operational tables!")

    print("\nSUCCESS: Database operational data cleanly reset. Schemas and admin configurations preserved.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ONPay V2 Safe Database Reset Utility")
    parser.add_argument("--db-url", type=str, default=None, help="Database URL override")
    parser.add_argument(
        "--confirm-reset-i-understand-data-loss",
        action="store_true",
        help="Explicit confirmation required to proceed with data reset",
    )
    parser.add_argument("--skip-backup", action="store_true", help="Skip pre-reset backup (strongly discouraged)")
    args = parser.parse_args()

    safe_reset(
        db_url=args.db_url,
        confirm_flag=args.confirm_reset_i_understand_data_loss,
        skip_backup=args.skip_backup,
    )
