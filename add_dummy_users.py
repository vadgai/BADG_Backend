"""
Seed a handful of demo users into the auth_users collection so the admin
dashboard has data to show (Users / Payments / Report Usage pages).

Usage (from the Backend directory, with your .env configured):
    python add_dummy_users.py

Idempotent — running it again skips users that already exist. All demo users
share the password "Test@1234" (override with DUMMY_USER_PASSWORD in the env).

Requires MONGO_URI to be set so the users persist. Without a database the users
are created only in the in-memory store of this short-lived process and will not
be visible to the running server — in that case set SEED_DUMMY_USERS=true and
restart the server instead.
"""

import asyncio
import logging

logging.basicConfig(level=logging.INFO)

from database.connection import connect_to_mongodb, close_mongodb_connection, is_database_available
from auth.seed import seed_dummy_users, DUMMY_PASSWORD


async def main() -> None:
    connected = await connect_to_mongodb()
    if not connected or not is_database_available():
        print(
            "⚠️  MongoDB is not available. Users would only be created in this "
            "process's memory and would NOT be visible to the server.\n"
            "    Set MONGO_URI in your .env, or start the server with "
            "SEED_DUMMY_USERS=true instead."
        )
    created = await seed_dummy_users()
    print(f"✅ Done. Created {created} new demo user(s). Password: {DUMMY_PASSWORD}")
    await close_mongodb_connection()


if __name__ == "__main__":
    asyncio.run(main())
