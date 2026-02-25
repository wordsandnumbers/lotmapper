#!/usr/bin/env python3
"""Create an admin user for first-time setup."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.user import User
from app.core.security import get_password_hash


def create_admin(email: str, password: str):
    db = SessionLocal()
    try:
        # Check if user exists
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            print(f"User {email} already exists")
            if existing.role != "admin":
                existing.role = "admin"
                existing.is_active = True
                db.commit()
                print(f"Updated {email} to admin role")
            return

        # Create admin user
        user = User(
            email=email,
            password_hash=get_password_hash(password),
            role="admin",
            is_active=True,
        )
        db.add(user)
        db.commit()
        print(f"Created admin user: {email}")

    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python create_admin.py <email> <password>")
        sys.exit(1)

    create_admin(sys.argv[1], sys.argv[2])
