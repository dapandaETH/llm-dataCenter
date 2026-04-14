import pytest
import pytest_asyncio
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from httpx import AsyncClient, ASGITransport


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def client():
    from database import init_db, DATABASE_PATH

    if os.path.exists(DATABASE_PATH):
        os.remove(DATABASE_PATH)
    await init_db()

    import main

    main.router = main.load_router()

    from main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    if os.path.exists(DATABASE_PATH):
        os.remove(DATABASE_PATH)
