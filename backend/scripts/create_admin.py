"""Create the first admin account.

    uv run python -m scripts.create_admin --email you@ikrux.com --name "Your Name"

There is no password to set. Sign-in is a one-time code mailed to this address,
so the only thing that matters is that the mailbox is real and reachable.

Use --send-code to have a code mailed immediately, which doubles as an
end-to-end check that the Microsoft Graph credentials work.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from pymongo.errors import DuplicateKeyError

from app import db
from app.config import settings
from app.main import ensure_indexes
from app.services import auth_service, otp_service


async def run(email: str, name: str, role: str, reactivate: bool, send_code: bool) -> int:
    await db.connect()
    await ensure_indexes()
    try:
        address = email.strip().lower()
        existing = await db.users().find_one({"email": address})

        if existing:
            changes: dict = {}
            if existing.get("role") != role:
                changes["role"] = role
            if reactivate and not existing.get("active", True):
                changes["active"] = True
            if not changes:
                print(
                    f"{address} already exists (role={existing.get('role')}, "
                    f"active={existing.get('active', True)}). Nothing to do."
                )
            else:
                await db.users().update_one({"_id": existing["_id"]}, {"$set": changes})
                print(f"Updated {address}: {changes}")
        else:
            user = await auth_service.create_user(email=address, name=name, role=role)
            print(f"Created {address} (role={role}, id={user['_id']}).")

        if send_code:
            if not settings.graph_configured:
                print(
                    "\nCannot send: Microsoft Graph is not configured. Set GRAPH_TENANT_ID, "
                    "GRAPH_CLIENT_ID and GRAPH_CLIENT_SECRET in .env."
                )
                return 1
            try:
                await otp_service.request_code(email=address, ip="cli", user_agent="create_admin")
            except otp_service.OtpError as exc:
                print(f"\nCould not send the sign-in code: {exc.message}")
                return 1
            print(f"\nSign-in code sent to {address} from {settings.graph_sender}.")
            print(f"It expires in {settings.otp_ttl_minutes} minutes.")

        print("\nSign in at POST /api/auth/request-code, then POST /api/auth/verify-code.")
        return 0
    except DuplicateKeyError:
        print(f"User {email} already exists.")
        return 1
    finally:
        from app.services import mailer

        await mailer.close()
        await db.disconnect()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or update a Candidate Search user.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", default="admin", choices=["admin", "recruiter"])
    parser.add_argument("--reactivate", action="store_true", help="Re-enable a deactivated account")
    parser.add_argument(
        "--send-code",
        action="store_true",
        help="Mail a sign-in code now - also verifies the Graph credentials end to end",
    )
    args = parser.parse_args()
    return asyncio.run(run(args.email, args.name, args.role, args.reactivate, args.send_code))


if __name__ == "__main__":
    sys.exit(main())
