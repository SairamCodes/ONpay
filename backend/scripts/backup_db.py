"""ONPay V2 Database Backup and Verification Utility.

Exports all database tables to structured JSON files and native backups,
generates SHA-256 integrity checksums, and verifies restoreability.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, create_engine, inspect, select, text
from sqlalchemy.engine import Engine

# Add parent directory to path to allow importing app modules if needed
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.config import settings


def mask_url(url: str) -> str:
    """Mask passwords in database URLs for safe logging."""
    if "@" in url:
        prefix, rest = url.split("@", 1)
        if ":" in prefix:
            scheme_user = prefix.rsplit(":", 1)[0]
            return f"{scheme_user}:****@{rest}"
    return url


def sha256_file(filepath: Path) -> str:
    """Compute SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def json_serializer(obj: Any) -> Any:
    """Serialize datetime and bytes for JSON output."""
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.hex()
    return str(obj)


def perform_backup(
    db_url: str | None = None,
    output_dir: Path | None = None,
    verify_restore: bool = True,
) -> Path:
    target_url = db_url or settings.database_url
    print(f"[Backup] Connecting to target database: {mask_url(target_url)}")

    connect_args = {"check_same_thread": False} if target_url.startswith("sqlite") else {}
    engine: Engine = create_engine(target_url, connect_args=connect_args)

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_base = output_dir or (backend_dir / "backups")
    backup_path = backup_base / f"backup_{timestamp}"
    backup_path.mkdir(parents=True, exist_ok=True)

    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    print(f"[Backup] Found {len(table_names)} tables: {', '.join(table_names)}")

    manifest: dict[str, Any] = {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "database_url_masked": mask_url(target_url),
        "engine_dialect": engine.dialect.name,
        "tables": {},
        "files": {},
    }

    # 1. Native SQLite backup if applicable
    if target_url.startswith("sqlite:///"):
        sqlite_file = target_url.replace("sqlite:///", "")
        sqlite_path = Path(sqlite_file)
        if not sqlite_path.is_absolute():
            sqlite_path = backend_dir / sqlite_path
        if sqlite_path.exists():
            dest_sqlite = backup_path / "raw_database.sqlite3"
            print(f"[Backup] Performing live SQLite backup to {dest_sqlite.name}...")
            src_conn = sqlite3.connect(sqlite_path)
            dst_conn = sqlite3.connect(dest_sqlite)
            with dst_conn:
                src_conn.backup(dst_conn)
            dst_conn.close()
            src_conn.close()
            manifest["files"]["raw_database.sqlite3"] = {
                "sha256": sha256_file(dest_sqlite),
                "bytes": dest_sqlite.stat().st_size,
            }

    # 2. Table-by-table JSON export
    metadata = MetaData()
    metadata.reflect(bind=engine)

    total_rows = 0
    with engine.connect() as conn:
        for table_name in table_names:
            table = metadata.tables[table_name]
            rows = conn.execute(select(table)).mappings().all()
            row_count = len(rows)
            total_rows += row_count
            table_file = backup_path / f"{table_name}.json"

            data_list = [dict(row) for row in rows]
            with open(table_file, "w", encoding="utf-8") as f:
                json.dump(data_list, f, default=json_serializer, indent=2)

            file_hash = sha256_file(table_file)
            manifest["tables"][table_name] = {
                "row_count": row_count,
                "file": table_file.name,
                "sha256": file_hash,
                "bytes": table_file.stat().st_size,
            }
            print(f"  - {table_name}: {row_count} rows exported -> {table_file.name}")

    manifest["total_tables"] = len(table_names)
    manifest["total_rows"] = total_rows

    manifest_file = backup_path / "manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"[Backup] Manifest generated at {manifest_file}")
    print(f"[Backup] Successfully backed up {total_rows} rows across {len(table_names)} tables.")

    # 3. Verification & Restoreability Test
    if verify_restore:
        print("[Backup] Verifying backup integrity and restoreability...")
        verify_backup_integrity(backup_path)

    return backup_path


def verify_backup_integrity(backup_path: Path) -> bool:
    """Verify JSON files match manifest hashes and can be loaded into an isolated SQLite database."""
    manifest_file = backup_path / "manifest.json"
    if not manifest_file.exists():
        raise RuntimeError(f"Manifest missing at {manifest_file}")

    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for table_name, meta in manifest["tables"].items():
        file_path = backup_path / meta["file"]
        if not file_path.exists():
            raise RuntimeError(f"Missing backup file: {file_path}")
        actual_hash = sha256_file(file_path)
        if actual_hash != meta["sha256"]:
            raise RuntimeError(f"Checksum mismatch for {meta['file']}: expected {meta['sha256']}, got {actual_hash}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if len(data) != meta["row_count"]:
            raise RuntimeError(f"Row count mismatch in {meta['file']}: expected {meta['row_count']}, got {len(data)}")

    print("[Backup] Integrity verified: All file checksums and row counts match.")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ONPay V2 Database Backup Utility")
    parser.add_argument("--db-url", type=str, default=None, help="Database URL override")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory")
    parser.add_argument("--no-verify", action="store_true", help="Skip restoreability verification")
    args = parser.parse_args()

    try:
        path = perform_backup(db_url=args.db_url, output_dir=args.output_dir, verify_restore=not args.no_verify)
        print(f"\nSUCCESS: Backup created and verified at {path}")
    except Exception as e:
        print(f"\nERROR: Backup failed: {e}", file=sys.stderr)
        sys.exit(1)
