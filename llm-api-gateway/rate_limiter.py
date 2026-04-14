import time
import aiosqlite
from dataclasses import dataclass
from database import DATABASE_PATH


@dataclass
class Config:
    global_rpm: int = 1000
    default_per_key_rpm: int = 100


config = Config()


async def check_rate_limit(
    key_id: int, limit: int | None = None
) -> tuple[bool, int, int | None]:
    limit = limit or config.default_per_key_rpm
    window_duration = 60

    async with aiosqlite.connect(DATABASE_PATH) as db:
        now = time.time()
        window_start = now - window_duration

        await db.execute(
            "DELETE FROM rate_buckets WHERE key_id = ? AND window_start < ?",
            (key_id, window_start),
        )

        cursor = await db.execute(
            "SELECT request_count FROM rate_buckets WHERE key_id = ?", (key_id,)
        )
        row = await cursor.fetchone()

        if row is None:
            await db.execute(
                "INSERT INTO rate_buckets (key_id, window_start, request_count) VALUES (?, ?, ?)",
                (key_id, now, 0),
            )
            await db.commit()
            return True, limit, None

        current_count = row[0]

        if current_count >= limit:
            retry_after = window_duration - int(now % window_duration)
            return False, 0, retry_after

        await db.commit()
        return True, limit - current_count - 1, None


async def increment_rate_count(key_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE rate_buckets SET request_count = request_count + 1 WHERE key_id = ?",
            (key_id,),
        )
        await db.commit()


async def check_global_limit() -> tuple[bool, int | None]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        now = time.time()
        window_start = now - 60
        cursor = await db.execute(
            "SELECT SUM(request_count) FROM rate_buckets WHERE window_start > ?",
            (window_start,),
        )
        row = await cursor.fetchone()
        total = row[0] or 0

        if total >= config.global_rpm:
            return False, 60 - int(now % 60)
        return True, None
