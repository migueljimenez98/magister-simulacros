"""Seed the first admin user. Run after `alembic upgrade head`.

Usage:
    python -m scripts.seed_admin admin@magister.com 'StrongPassword123'
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.core.db import async_session
from app.core.models import User
from app.core.security import hash_password


async def main(email: str, password: str, name: str = "Admin") -> None:
    async with async_session() as s:
        existing = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if existing:
            print(f"User {email} already exists ({existing.id})")
            return
        user = User(email=email, password_hash=hash_password(password), name=name, role="admin")
        s.add(user)
        await s.commit()
        print(f"Created admin user {user.email} ({user.id})")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
