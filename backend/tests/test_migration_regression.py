import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-more-than-32-characters")
os.environ.setdefault("DATABASE_URL", "sqlite://")

from app.database import Base
from app.models import User, now_utc


class MigrationRegressionTests(unittest.TestCase):
    def test_upgrade_adds_missing_delivery_status_without_losing_existing_rows(self):
        backend_dir = Path(__file__).resolve().parents[1]
        descriptor, temp_database = tempfile.mkstemp(
            prefix=".onpay-migration-regression-", suffix=".sqlite", dir=backend_dir,
        )
        os.close(descriptor)
        database_path = Path(temp_database).resolve()
        if database_path.parent != backend_dir.resolve():
            raise RuntimeError("Migration test database must stay inside the backend workspace")
        try:
            database_url = f"sqlite:///{database_path.as_posix()}"
            engine = create_engine(database_url)
            legacy_tables = [table for table in Base.metadata.sorted_tables if table.name != "otp_challenges"]
            Base.metadata.create_all(bind=engine, tables=legacy_tables)

            with Session(engine) as session:
                session.add(User(
                    id="migration-user", full_name="Migration Test", email="migration@example.invalid",
                    phone=None, college=None, verified_email=False, verified_phone=False, plan="free",
                ))
                session.commit()

            # Create the pre-delivery-status table shape without SQLite DROP COLUMN,
            # so the regression works with older SQLite versions too.
            with engine.begin() as connection:
                connection.execute(text("""
                    CREATE TABLE otp_challenges (
                        id VARCHAR(36) NOT NULL PRIMARY KEY,
                        contact VARCHAR(254) NOT NULL,
                        channel VARCHAR(12) NOT NULL,
                        intent VARCHAR(12) NOT NULL,
                        full_name VARCHAR(100),
                        college VARCHAR(140),
                        code_hash VARCHAR(128),
                        provider_ref VARCHAR(120),
                        expires_at DATETIME NOT NULL,
                        last_sent_at DATETIME NOT NULL,
                        attempts INTEGER NOT NULL,
                        consumed_at DATETIME
                    )
                """))
                connection.execute(text("""
                    INSERT INTO otp_challenges
                        (id, contact, channel, intent, full_name, college, code_hash, provider_ref,
                         expires_at, last_sent_at, attempts, consumed_at)
                    VALUES
                        ('migration-challenge', 'migration@example.invalid', 'email', 'signup',
                         'Migration Test', NULL, NULL, NULL, :expires_at, :last_sent_at, 0, NULL)
                """), {
                    "expires_at": (now_utc() + timedelta(minutes=5)).isoformat(),
                    "last_sent_at": now_utc().isoformat(),
                })
            engine.dispose()

            child_env = os.environ.copy()
            child_env.update({
                "APP_ENV": "development",
                "DATABASE_URL": database_url,
                "SECRET_KEY": "test-only-secret-key-with-more-than-32-characters",
            })
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=backend_dir, env=child_env, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            connection = sqlite3.connect(database_path)
            try:
                columns = {row[1]: row for row in connection.execute('PRAGMA table_info("otp_challenges")')}
                self.assertIn("delivery_status", columns)
                delivery_status = columns["delivery_status"]
                self.assertEqual(delivery_status[2].upper(), "VARCHAR(16)")
                self.assertEqual(delivery_status[3], 1)  # NOT NULL
                self.assertEqual(delivery_status[4], "'pending'")
                self.assertEqual(connection.execute("SELECT count(*) FROM users").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT count(*) FROM otp_challenges").fetchone()[0], 1)
                self.assertEqual(
                    connection.execute(
                        "SELECT delivery_status FROM otp_challenges WHERE id = ?", ("migration-challenge",),
                    ).fetchone()[0],
                    "pending",
                )
                self.assertEqual(
                    connection.execute("SELECT version_num FROM alembic_version").fetchone()[0],
                    "0002_location_otp_plans",
                )
            finally:
                connection.close()
                engine.dispose()
        finally:
            if database_path.exists():
                database_path.unlink()


if __name__ == "__main__":
    unittest.main()
