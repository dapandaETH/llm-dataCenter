import pytest
import pytest_asyncio
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth import get_api_key_record, verify_api_key


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


@pytest_asyncio.fixture
async def db_with_active_key():
    from database import init_db, DATABASE_PATH

    await init_db()
    key_hash = hashlib.sha256(b"sk-activekey").hexdigest()
    async with __import__("aiosqlite").connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO api_keys (key_hash, owner, requests_per_minute, active) VALUES (?, ?, ?, ?)",
            (key_hash, "active_user", 100, 1),
        )
        await db.commit()
    yield
    if os.path.exists(DATABASE_PATH):
        os.remove(DATABASE_PATH)


@pytest_asyncio.fixture
async def db_with_inactive_key():
    from database import init_db, DATABASE_PATH

    await init_db()
    key_hash = hashlib.sha256(b"sk-inactivekey").hexdigest()
    async with __import__("aiosqlite").connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO api_keys (key_hash, owner, requests_per_minute, active) VALUES (?, ?, ?, ?)",
            (key_hash, "inactive_user", 100, 0),
        )
        await db.commit()
    yield
    if os.path.exists(DATABASE_PATH):
        os.remove(DATABASE_PATH)


@pytest.mark.asyncio
async def test_verify_api_key_missing_header(db_empty):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await verify_api_key(bearer=None)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_api_key_invalid_key(db_with_key):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await verify_api_key(bearer="Bearer sk-wrongkey")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_api_key_empty_key(db_empty):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await verify_api_key(bearer="Bearer ")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_api_key_valid(db_with_active_key):
    record = await verify_api_key(bearer="Bearer sk-activekey")
    assert record["owner"] == "active_user"


@pytest.mark.asyncio
async def test_verify_api_key_inactive(db_with_inactive_key):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await verify_api_key(bearer="Bearer sk-inactivekey")
    assert exc_info.value.status_code == 401
