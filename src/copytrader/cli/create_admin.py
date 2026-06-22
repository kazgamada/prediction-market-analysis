"""初期管理者ユーザー作成スクリプト。

Usage:
    python -m copytrader.cli.create_admin email password
"""
from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) != 3:  # noqa: PLR2004
        print("Usage: python -m copytrader.cli.create_admin <email> <password>")
        sys.exit(1)

    email = sys.argv[1]
    password = sys.argv[2]

    if len(password) < 8:  # noqa: PLR2004
        print("Error: password must be at least 8 characters")
        sys.exit(1)

    import bcrypt
    from sqlalchemy import select

    from copytrader.db.engine import get_session, run_migrations
    from copytrader.db.models import User

    print("Running migrations...")
    run_migrations()

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    with get_session() as s:
        existing = s.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if existing:
            existing.role = "admin"
            existing.pw_hash = pw_hash
            existing.is_active = True
            print(f"Updated existing user {email} to admin role")
        else:
            s.add(User(email=email, pw_hash=pw_hash, role="admin"))
            print(f"Created admin user: {email}")


if __name__ == "__main__":
    main()
