import aiosqlite
import os
from pathlib import Path

DATABASE_PATH = os.getenv("DATABASE_PATH", "gateway.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_hash TEXT UNIQUE NOT NULL,
    owner TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    requests_per_minute INTEGER DEFAULT 100,
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS rate_buckets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_id INTEGER REFERENCES api_keys(id),
    window_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    request_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_id INTEGER REFERENCES api_keys(id),
    model TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    latency_ms INTEGER,
    tokens_used INTEGER
);
"""


async def init_db():
    async with aiosqlite.connect(DATABASE_PATH, timeout=30) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.executescript(SCHEMA)
        await db.commit()
