import pytest
import pytest_asyncio
import hashlib


@pytest_asyncio.fixture
async def auth_headers():
    from database import DATABASE_PATH, init_db
    import aiosqlite

    await init_db()
    raw_key = "sk-test-integration-key"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO api_keys (key_hash, owner, requests_per_minute, active) VALUES (?, ?, ?, ?)",
            (key_hash, "integration-test", 1000, 1),
        )
        await db.commit()
    return {"Authorization": f"Bearer {raw_key}"}


@pytest.mark.asyncio
async def test_health_no_auth(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_list_models_requires_auth(client):
    resp = await client.get("/v1/models")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_models_with_auth(client, auth_headers):
    resp = await client.get("/v1/models", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    assert len(data["data"]) >= 1


@pytest.mark.asyncio
async def test_chat_completions_requires_auth(client):
    resp = await client.post(
        "/v1/chat/completions",
        json={"model": "glm5", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_chat_completions_unknown_model(client, auth_headers):
    resp = await client.post(
        "/v1/chat/completions",
        json={"model": "nonexistent", "messages": [{"role": "user", "content": "hi"}]},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "Unknown model" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_rate_limit_returns_429(client):
    from database import DATABASE_PATH
    from unittest.mock import patch, AsyncMock, MagicMock
    import aiosqlite

    raw_key = "sk-rate-limit-test"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO api_keys (key_hash, owner, requests_per_minute, active) VALUES (?, ?, ?, ?)",
            (key_hash, "rate-limit-test", 2, 1),
        )
        await db.commit()

    headers = {"Authorization": f"Bearer {raw_key}"}

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "id": "test",
        "object": "chat.completion",
        "model": "glm5",
        "choices": [{"message": {"role": "assistant", "content": "hi"}}],
    }
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    mock_client_instance = AsyncMock()
    mock_client_instance.post = AsyncMock(return_value=mock_response)

    with patch("main.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = mock_client_instance
        for _ in range(2):
            resp = await client.post(
                "/v1/chat/completions",
                json={"model": "glm5", "messages": [{"role": "user", "content": "hi"}]},
                headers=headers,
            )
            assert resp.status_code == 200

        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "glm5", "messages": [{"role": "user", "content": "hi"}]},
            headers=headers,
        )
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
