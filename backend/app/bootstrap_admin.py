"""ONPay V2 Admin Bootstrap CLI.

Creates or updates a superadmin user with secure password hashing.
Usage:
  python -m app.bootstrap_admin --email admin@onpay.com --password <secret> --name "Admin"
Or via environment variables:
  ADMIN_BOOTSTRAP_EMAIL, ADMIN_BOOTSTRAP_PASSWORD, ADMIN_BOOTSTRAP_NAME
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.admin_security import hash_password
from app.database import SessionLocal
from app.models import AdminUser, now_utc


def bootstrap_admin(
    email: str,
    password: str,
    name: str = "System Admin",
    role: str = "superadmin",
) -> None:
    if len(password) < 8:
        raise ValueError("Password must have at least 8 characters")

    db = SessionLocal()
    try:
        existing = db.query(AdminUser).filter_by(email=email.strip().lower()).first()
        hashed = hash_password(password)

        if existing:
            existing.full_name = name
            existing.hashed_password = hashed
            existing.role = role
            existing.is_active = True
            db.commit()
            print(f"[Admin Bootstrap] Updated existing admin: {existing.email} (Role: {existing.role})")
        else:
            admin = AdminUser(
                id=str(uuid.uuid4()),
                email=email.strip().lower(),
                hashed_password=hashed,
                full_name=name,
                role=role,
                is_active=True,
                created_at=now_utc(),
            )
            db.add(admin)
            db.commit()
            print(f"[Admin Bootstrap] Successfully created new admin: {admin.email} (Role: {admin.role})")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bootstrap ONPay Admin Account")
    parser.add_argument("--email", default=os.getenv("ADMIN_BOOTSTRAP_EMAIL"))
    parser.add_argument("--password", default=os.getenv("ADMIN_BOOTSTRAP_PASSWORD"))
    parser.add_argument("--name", default=os.getenv("ADMIN_BOOTSTRAP_NAME", "System Admin"))
    parser.add_argument("--role", default="superadmin")
    args = parser.parse_args()

    if not args.email or not args.password:
        print("ERROR: --email and --password are required (or set ADMIN_BOOTSTRAP_EMAIL / ADMIN_BOOTSTRAP_PASSWORD)", file=sys.stderr)
        sys.exit(1)

    try:
        bootstrap_admin(email=args.email, password=args.password, name=args.name, role=args.role)
    except Exception as e:
        print(f"ERROR: Admin bootstrap failed: {e}", file=sys.stderr)
        sys.exit(1)
