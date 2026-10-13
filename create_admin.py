"""
SMART CAMPUS 360 - SECURE INITIAL MAIN ADMIN PROVISIONING SCRIPT
Government Engineering College, Mosalehosahalli (Hassan)

Usage:
  Interactive Mode:
    python create_admin.py

  Automated / Headless Mode:
    python create_admin.py --name "Admin Name" --email "admin@gechassan.ac.in" --password "SecurePass123" --phone "+91 98450 11001"
"""

import sys
import argparse
import getpass
import re
from app import create_app
from app.database import db
from app.models import User, AuditLog

def validate_password_strength(password: str) -> bool:
    """Enforces minimum 8 characters, at least 1 digit, and at least 1 letter."""
    if len(password) < 8:
        print("[!] Password must be at least 8 characters long.")
        return False
    if not re.search(r"[A-Za-z]", password):
        print("[!] Password must contain at least one alphabetical character.")
        return False
    if not re.search(r"\d", password):
        print("[!] Password must contain at least one numeric digit.")
        return False
    return True

def provision_admin(name=None, email=None, password=None, department="System Administration", phone=None):
    app = create_app()
    with app.app_context():
        print("\n" + "=" * 65)
        print("  SMART CAMPUS 360 - SECURE MAIN ADMIN PROVISIONING")
        print("  Government Engineering College, Mosalehosahalli (Hassan)")
        print("=" * 65 + "\n")

        # Interactive prompts if arguments not supplied. Phase 10 fix: when all
        # required flags (--name/--email/--password) are supplied the script runs
        # fully headless; the OPTIONAL phone prompt no longer blocks CI/docker
        # runs, and missing required values without a terminal fail fast.
        automated = bool(name and email and password)
        interactive = sys.stdin.isatty()

        if not name:
            if not interactive:
                print("[!] Error: --name is required in non-interactive mode.")
                sys.exit(1)
            name = input("Enter Main Admin Full Name: ").strip()
            if not name:
                print("[!] Error: Admin name cannot be empty.")
                sys.exit(1)

        if not email:
            if not interactive:
                print("[!] Error: --email is required in non-interactive mode.")
                sys.exit(1)
            email = input("Enter Main Admin Email (e.g. admin@gechassan.ac.in): ").strip().lower()
            if not email or "@" not in email:
                print("[!] Error: A valid email address is required.")
                sys.exit(1)
        else:
            email = email.strip().lower()

        if not password:
            if not interactive:
                print("[!] Error: --password is required in non-interactive mode.")
                sys.exit(1)
            while True:
                password = getpass.getpass("Enter Secure Admin Password (min 8 chars): ")
                if not validate_password_strength(password):
                    continue
                confirm = getpass.getpass("Confirm Admin Password: ")
                if password != confirm:
                    print("[!] Passwords do not match. Please try again.")
                    continue
                break
        else:
            if not validate_password_strength(password):
                sys.exit(1)

        if not phone:
            if not automated:
                phone = input("Enter Contact Phone (optional): ").strip()

        # Check for existing user
        user = User.query.filter_by(email=email).first()
        if user:
            print(f"\n[*] User with email '{email}' already exists (Current Role: {user.role}).")
            if not sys.argv or "--password" not in sys.argv:
                confirm_upgrade = input("Update this account to Main Admin with the new password? (y/N): ").strip().lower()
                if confirm_upgrade != 'y':
                    print("Provisioning cancelled.")
                    sys.exit(0)

            user.full_name = name
            user.role = 'main_admin'
            user.department = department or user.department
            user.phone = phone or user.phone
            user.is_active = True
            user.is_verified = True
            user.set_password(password)
            action_desc = f"Existing user '{email}' upgraded to Main Admin."
        else:
            user = User(
                full_name=name,
                email=email,
                role='main_admin',
                department=department,
                phone=phone,
                is_active=True,
                is_verified=True
            )
            user.set_password(password)
            db.session.add(user)
            action_desc = f"New Main Admin account created for '{email}'."

        db.session.commit()

        # Write to security audit log
        AuditLog.log(
            action='MAIN_ADMIN_PROVISIONED',
            module='ADMIN',
            user_id=user.id,
            details=action_desc,
            ip_address="CLI_LOCAL_HOST"
        )

        print("\n" + "=" * 65)
        print(f"[OK] Main Admin account configured successfully!")
        print(f"     Name:       {user.full_name}")
        print(f"     Email:      {user.email}")
        print(f"     Role:       MAIN_ADMIN")
        print(f"     Verified:   TRUE")
        print(f"     Active:     TRUE")
        print("=" * 65 + "\n")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Provision Main Admin for Smart Campus 360")
    parser.add_argument("--name", help="Admin Full Name")
    parser.add_argument("--email", help="Admin Email")
    parser.add_argument("--password", help="Admin Password")
    parser.add_argument("--dept", default="System Administration", help="Department")
    parser.add_argument("--phone", help="Phone Number")

    args = parser.parse_args()

    provision_admin(
        name=args.name,
        email=args.email,
        password=args.password,
        department=args.dept,
        phone=args.phone
    )
