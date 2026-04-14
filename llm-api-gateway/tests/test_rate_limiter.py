import pytest
import pytest_asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rate_limiter import check_rate_limit, Config


@pytest_asyncio.fixture
async def fresh_db():
    from database import init_db, DATABASE_PATH

    await init_db()
    yield
    if os.path.exists(DATABASE_PATH):
        os.remove(DATABASE_PATH)


@pytest.mark.asyncio
async def test_per_key_rate_limit_allows_requests_under_limit(fresh_db):
    allowed, remaining, retry_after = await check_rate_limit(key_id=1, limit=100)
    assert allowed is True
    assert remaining == 99


@pytest.mark.asyncio
async def test_per_key_rate_limit_blocks_over_limit(fresh_db):
    from database import init_db, DATABASE_PATH
    import aiosqlite

    await init_db()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO api_keys (key_hash, owner, requests_per_minute, active) VALUES (?, ?, ?, ?)",
            ("hash1", "test", 5, 1),
        )
        await db.commit()
        key_id = (await (await db.execute("SELECT last_insert_rowid()")).fetchone())[0]

    for _ in range(5):
        allowed, _, _ = await check_rate_limit(key_id=key_id, limit=5)
        assert allowed is True

    allowed, remaining, retry_after = await check_rate_limit(key_id=key_id, limit=5)
    assert allowed is False
    assert retry_after is not None
