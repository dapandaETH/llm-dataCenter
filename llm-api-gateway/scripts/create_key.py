#!/usr/bin/env python3
import asyncio
import argparse
import hashlib
import secrets
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import init_db, DATABASE_PATH
import aiosqlite


async def create_key(owner: str, rate_limit: int = 100):
    await init_db()
    raw_key = f"sk-{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO api_keys (key_hash, owner, requests_per_minute) VALUES (?, ?, ?)",
            (key_hash, owner, rate_limit),
        )
        await db.commit()

    print(f"Created API key for '{owner}':")
    print(f"  Key: {raw_key}")
    print(f"  Hash: {key_hash}")
    print("Save this key now - it cannot be retrieved later.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a new API key")
    parser.add_argument("--owner", required=True, help="Owner/label for the key")
    parser.add_argument(
        "--rate-limit", type=int, default=100, help="Requests per minute"
    )
    args = parser.parse_args()
    asyncio.run(create_key(args.owner, args.rate_limit))
