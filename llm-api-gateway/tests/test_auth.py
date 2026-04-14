import pytest
import pytest_asyncio
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth import get_api_key_record


@pytest_asyncio.fixture
async def db_with_key():
    from database import init_db, DATABASE_PATH

    await init_db()
    key_hash = hashlib.sha256(b"sk-testkey123").hexdigest()
    async with __import__("aiosqlite").connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO api_keys (key_hash, owner, requests_per_minute) VALUES (?, ?, ?)",
            (key_hash, "test", 100),
        )
        await db.commit()
    yield
    if os.path.exists(DATABASE_PATH):
        os.remove(DATABASE_PATH)


@pytest.mark.asyncio
async def test_valid_key_returns_record(db_with_key):
    record = await get_api_key_record("sk-testkey123")
    assert record is not None
    assert record["owner"] == "test"


@pytest_asyncio.fixture
async def db_empty():
    from database import init_db, DATABASE_PATH

    await init_db()
    yield
    if os.path.exists(DATABASE_PATH):
        os.remove(DATABASE_PATH)


@pytest.mark.asyncio
async def test_invalid_key_returns_none(db_empty):
    record = await get_api_key_record("sk-nonexistent")
    assert record is None
