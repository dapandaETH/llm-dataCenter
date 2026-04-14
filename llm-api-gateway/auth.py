import hashlib
import aiosqlite
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
from database import DATABASE_PATH

bearer_scheme = APIKeyHeader(name="Authorization", auto_error=False)


async def get_api_key_record(raw_key: str) -> dict | None:
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id, key_hash, owner, requests_per_minute, active FROM api_keys WHERE key_hash = ?",
                (key_hash,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None
    except aiosqlite.Error:
        raise HTTPException(status_code=500, detail="Database error")


async def verify_api_key(bearer: str = Security(bearer_scheme)) -> dict:
    if not bearer:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    raw_key = bearer.replace("Bearer ", "", 1)
    if not raw_key.strip():
        raise HTTPException(status_code=401, detail="Invalid API key")

    record = await get_api_key_record(raw_key)

    if not record:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not record["active"]:
        raise HTTPException(status_code=401, detail="API key is inactive")

    return record
