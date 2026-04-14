# GLM5 OpenAI Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI proxy gateway that accepts OpenAI-format requests, validates API keys, enforces rate limits, and routes to GLM5 (and other models) running on vLLM via vast.ai.

**Architecture:** FastAPI server on a VPS proxies requests to vLLM backends. API keys stored as SHA-256 hashes in SQLite. Rate limiting uses sliding window algorithm with per-key and global limits. Streaming responses use SSE forwarded directly from vLLM.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, httpx, aiosqlite, Pydantic, pytest

---

## File Map

```
llm-api-gateway/
├── main.py                 # FastAPI app, routes, middleware
├── config.yaml             # Model routes, rate limits, global settings
├── database.py             # SQLite setup, queries, migrations
├── auth.py                 # API key validation (FastAPI dependency)
├── rate_limiter.py         # Rate limiting logic
├── router.py               # Model routing and request forwarding
├── schemas.py              # Pydantic request/response models
├── requirements.txt        # Dependencies
├── scripts/
│   └── create_key.py       # CLI to generate new API keys
├── tests/
│   ├── conftest.py         # Shared pytest fixtures
│   ├── test_auth.py        # API key validation tests
│   ├── test_rate_limiter.py
│   └── test_endpoints.py
└── Dockerfile
```

---

## Task 1: Project Scaffold

**Files:**
- Create: `llm-api-gateway/requirements.txt`
- Create: `llm-api-gateway/config.yaml`
- Create: `llm-api-gateway/main.py` (minimal FastAPI shell)

- [ ] **Step 1: Create requirements.txt**

```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
httpx>=0.26.0
aiosqlite>=0.19.0
pydantic>=2.0.0
pyyaml>=6.0
python-dotenv>=1.0.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

- [ ] **Step 2: Create config.yaml**

```yaml
app:
  host: "0.0.0.0"
  port: 8000
  debug: false

rate_limits:
  global_requests_per_minute: 1000
  default_per_key_requests_per_minute: 100

vllm:
  timeout_seconds: 120

models:
  glm5:
    backend_url: "http://YOUR_VAST_AI_IP:8000"
    display_name: "GLM-5 32B"
```

- [ ] **Step 3: Create minimal main.py**

```python
import fastapi

app = fastapi.FastAPI()

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 4: Run app to verify it starts**

Run: `cd llm-api-gateway && pip install -r requirements.txt && uvicorn main:app --port 8000`
Expected: Server starts on port 8000

- [ ] **Step 5: Commit**

```bash
git add llm-api-gateway/requirements.txt llm-api-gateway/config.yaml llm-api-gateway/main.py
git commit -m "feat: scaffold project with FastAPI, requirements, and config"
```

---

## Task 2: Database Setup

**Files:**
- Create: `llm-api-gateway/database.py`

- [ ] **Step 1: Write the database module**

```python
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

async def get_db():
    db = await aiosqlite.connect(DATABASE_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()

async def init_db():
    Path(DATABASE_PATH).touch()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()
```

- [ ] **Step 2: Test database init**

Run: `cd llm-api-gateway && python -c "import asyncio; from database import init_db; asyncio.run(init_db())" && ls -la gateway.db`
Expected: `gateway.db` file created

- [ ] **Step 3: Commit**

```bash
git add llm-api-gateway/database.py
git commit -m "feat: add SQLite database with schema"
```

---

## Task 3: API Key Management Script

**Files:**
- Create: `llm-api-gateway/scripts/create_key.py`

- [ ] **Step 1: Write the key creation script**

```python
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
            (key_hash, owner, rate_limit)
        )
        await db.commit()
    
    print(f"Created API key for '{owner}':")
    print(f"  Key: {raw_key}")
    print(f"  Hash: {key_hash}")
    print("Save this key now — it cannot be retrieved later.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a new API key")
    parser.add_argument("--owner", required=True, help="Owner/label for the key")
    parser.add_argument("--rate-limit", type=int, default=100, help="Requests per minute")
    args = parser.parse_args()
    asyncio.run(create_key(args.owner, args.rate_limit))
```

- [ ] **Step 2: Test key creation**

Run: `cd llm-api-gateway && python scripts/create_key.py --owner "test-user" --rate-limit 50`
Expected: Outputs a new API key with hash

- [ ] **Step 3: Verify key in database**

Run: `cd llm-api-gateway && sqlite3 gateway.db "SELECT owner, requests_per_minute, active FROM api_keys;"`
Expected: Shows the test key

- [ ] **Step 4: Commit**

```bash
git add llm-api-gateway/scripts/create_key.py
git commit -m "feat: add API key creation script"
```

---

## Task 4: Auth Dependency

**Files:**
- Create: `llm-api-gateway/auth.py`
- Create: `llm-api-gateway/tests/test_auth.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
import hashlib
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth import get_api_key_record

@pytest.fixture
async def db_with_key():
    from database import init_db, DATABASE_PATH
    await init_db()
    key_hash = hashlib.sha256(b"sk-testkey123").hexdigest()
    async with __import__('aiosqlite').connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO api_keys (key_hash, owner, requests_per_minute) VALUES (?, ?, ?)",
            (key_hash, "test", 100)
        )
        await db.commit()
    yield
    os.remove(DATABASE_PATH)

@pytest.mark.asyncio
async def test_valid_key_returns_record(db_with_key):
    record = await get_api_key_record("sk-testkey123")
    assert record is not None
    assert record["owner"] == "test"

@pytest.mark.asyncio
async def test_invalid_key_returns_none():
    record = await get_api_key_record("sk-nonexistent")
    assert record is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd llm-api-gateway && pytest tests/test_auth.py -v`
Expected: FAIL with "auth module not found"

- [ ] **Step 3: Write minimal auth module**

```python
import hashlib
import aiosqlite
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
from database import DATABASE_PATH

bearer_scheme = APIKeyHeader(name="Authorization", auto_error=False)

async def get_api_key_record(raw_key: str) -> dict | None:
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, key_hash, owner, requests_per_minute, active FROM api_keys WHERE key_hash = ?",
            (key_hash,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

async def verify_api_key(bearer: str = Security(bearer_scheme)) -> dict:
    if not bearer:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    
    raw_key = bearer.replace("Bearer ", "", 1)
    record = await get_api_key_record(raw_key)
    
    if not record:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not record["active"]:
        raise HTTPException(status_code=401, detail="API key is inactive")
    
    return record
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd llm-api-gateway && pytest tests/test_auth.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add llm-api-gateway/auth.py llm-api-gateway/tests/test_auth.py
git commit -m "feat: add API key authentication dependency"
```

---

## Task 5: Rate Limiter

**Files:**
- Create: `llm-api-gateway/rate_limiter.py`
- Create: `llm-api-gateway/tests/test_rate_limiter.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rate_limiter import check_rate_limit, Config

@pytest.fixture
async def fresh_db():
    from database import init_db, DATABASE_PATH
    await init_db()
    yield
    os.remove(DATABASE_PATH)

@pytest.mark.asyncio
async def test_per_key_rate_limit_allows_requests_under_limit(fresh_db):
    allowed, remaining, retry_after = await check_rate_limit(key_id=1, limit=100)
    assert allowed is True
    assert remaining == 99

@pytest.mark.asyncio
async def test_per_key_rate_limit_blocks_over_limit(fresh_db):
    from database import init_db, DATABASE_PATH
    await init_db()
    async with __import__('aiosqlite').connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO api_keys (key_hash, owner, requests_per_minute, active) VALUES (?, ?, ?, ?)",
            ("hash1", "test", 5, 1)
        )
        await db.commit()
        key_id = await (await db.execute("SELECT last_insert_rowid()")).fetchone()
    
    for _ in range(5):
        allowed, _, _ = await check_rate_limit(key_id=key_id[0], limit=5)
        assert allowed is True
    
    allowed, remaining, retry_after = await check_rate_limit(key_id=key_id[0], limit=5)
    assert allowed is False
    assert retry_after is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd llm-api-gateway && pytest tests/test_rate_limiter.py -v`
Expected: FAIL with "rate_limiter module not found"

- [ ] **Step 3: Write the rate limiter module**

```python
import time
import aiosqlite
from dataclasses import dataclass
from database import DATABASE_PATH

@dataclass
class Config:
    global_rpm: int = 1000
    default_per_key_rpm: int = 100

config = Config()

async def check_rate_limit(key_id: int, limit: int | None = None) -> tuple[bool, int, int | None]:
    limit = limit or config.default_per_key_rpm
    window_duration = 60
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        now = time.time()
        window_start = now - window_duration
        
        await db.execute(
            "DELETE FROM rate_buckets WHERE key_id = ? AND window_start < ?",
            (key_id, window_start)
        )
        
        cursor = await db.execute(
            "SELECT request_count FROM rate_buckets WHERE key_id = ?",
            (key_id,)
        )
        row = await cursor.fetchone()
        
        if row is None:
            await db.execute(
                "INSERT INTO rate_buckets (key_id, window_start, request_count) VALUES (?, ?, ?)",
                (key_id, now, 1)
            )
            await db.commit()
            return True, limit - 1, None
        
        current_count = row[0]
        
        if current_count >= limit:
            retry_after = window_duration - int(now % window_duration)
            return False, 0, retry_after
        
        await db.execute(
            "UPDATE rate_buckets SET request_count = request_count + 1 WHERE key_id = ?",
            (key_id,)
        )
        await db.commit()
        return True, limit - current_count - 1, None

async def check_global_limit() -> tuple[bool, int | None]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        now = time.time()
        window_start = now - 60
        cursor = await db.execute(
            "SELECT SUM(request_count) FROM rate_buckets WHERE window_start > ?",
            (window_start,)
        )
        row = await cursor.fetchone()
        total = row[0] or 0
        
        if total >= config.global_rpm:
            return False, 60 - int(now % 60)
        return True, None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd llm-api-gateway && pytest tests/test_rate_limiter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add llm-api-gateway/rate_limiter.py llm-api-gateway/tests/test_rate_limiter.py
git commit -m "feat: add sliding window rate limiter"
```

---

## Task 6: Model Router

**Files:**
- Create: `llm-api-gateway/router.py`
- Create: `llm-api-gateway/tests/test_router.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from router import ModelRouter, RouterConfig

@pytest.fixture
def config():
    return RouterConfig(
        models={
            "glm5": {"backend_url": "http://localhost:8000", "display_name": "GLM-5"},
            "llama3": {"backend_url": "http://localhost:8001", "display_name": "Llama 3"},
        }
    )

def test_get_backend_url(config):
    r = ModelRouter(config)
    assert r.get_backend_url("glm5") == "http://localhost:8000"
    assert r.get_backend_url("llama3") == "http://localhost:8001"

def test_get_backend_url_unknown_model(config):
    r = ModelRouter(config)
    with pytest.raises(ValueError, match="Unknown model"):
        r.get_backend_url("unknown")

def test_list_models(config):
    r = ModelRouter(config)
    models = r.list_models()
    assert len(models) == 2
    assert models[0]["id"] == "glm5"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd llm-api-gateway && pytest tests/test_router.py -v`
Expected: FAIL with "router module not found"

- [ ] **Step 3: Write the router module**

```python
import yaml
import os
from dataclasses import dataclass, field
from typing import Any

@dataclass
class ModelConfig:
    backend_url: str
    display_name: str

@dataclass
class RouterConfig:
    models: dict[str, ModelConfig] = field(default_factory=dict)

class ModelRouter:
    def __init__(self, config: RouterConfig):
        self.config = config

    def get_backend_url(self, model: str) -> str:
        model_cfg = self.config.models.get(model)
        if not model_cfg:
            raise ValueError(f"Unknown model: {model}")
        return model_cfg.backend_url

    def list_models(self) -> list[dict[str, Any]]:
        return [
            {
                "id": model_id,
                "object": "model",
                "created": 1677610602,
                "owned_by": "local",
                "display_name": cfg.display_name,
            }
            for model_id, cfg in self.config.models.items()
        ]

    @classmethod
    def from_yaml(cls, path: str) -> "ModelRouter":
        with open(path) as f:
            data = yaml.safe_load(f)
        models = {}
        for model_id, cfg in data.get("models", {}).items():
            models[model_id] = ModelConfig(
                backend_url=cfg["backend_url"],
                display_name=cfg.get("display_name", model_id),
            )
        return cls(RouterConfig(models=models))

def load_router() -> ModelRouter:
    config_path = os.getenv("CONFIG_PATH", "config.yaml")
    return ModelRouter.from_yaml(config_path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd llm-api-gateway && pytest tests/test_router.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add llm-api-gateway/router.py llm-api-gateway/tests/test_router.py
git commit -m "feat: add model router with YAML config support"
```

---

## Task 7: Pydantic Schemas

**Files:**
- Create: `llm-api-gateway/schemas.py`

- [ ] **Step 1: Write the schemas module**

```python
from pydantic import BaseModel

class Message(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[Message]
    temperature: float | None = 0.7
    top_p: float | None = 1.0
    max_tokens: int | None = None
    stream: bool = False
    stop: str | list[str] | None = None
    frequency_penalty: float | None = 0.0
    presence_penalty: float | None = 0.0

class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

class ChatMessage(BaseModel):
    role: str
    content: str

class Choice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str | None = "stop"

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Usage

class ModelList(BaseModel):
    object: str = "list"
    data: list[dict]
```

- [ ] **Step 2: Commit**

```bash
git add llm-api-gateway/schemas.py
git commit -m "feat: add Pydantic request/response schemas"
```

---

## Task 8: Main API — Chat Completions + Models + Health

**Files:**
- Modify: `llm-api-gateway/main.py`

- [ ] **Step 1: Write the complete main.py**

```python
import time
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from auth import verify_api_key
from rate_limiter import check_rate_limit, check_global_limit
from router import load_router
from schemas import ChatCompletionRequest, ModelList

router = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    global router
    router = load_router()
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok", "models": list(router.config.models.keys())}

@app.get("/v1/models")
async def list_models(key_record: dict = Depends(verify_api_key)):
    return ModelList(data=router.list_models())

@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    key_record: dict = Depends(verify_api_key),
):
    allowed, remaining, retry_after = await check_rate_limit(
        key_id=key_record["id"],
        limit=key_record["requests_per_minute"],
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    global_ok, global_retry = await check_global_limit()
    if not global_ok:
        raise HTTPException(
            status_code=429,
            detail="Global rate limit exceeded",
            headers={"Retry-After": str(global_retry)},
        )

    try:
        backend_url = router.get_backend_url(request.model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    start = time.time()
    
    if request.stream:
        return await streaming_completion(backend_url, request, key_record, start)

    return await non_streaming_completion(backend_url, request, key_record, start)

async def non_streaming_completion(backend_url, request, key_record, start):
    timeout = httpx.Timeout(120.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(
                f"{backend_url}/v1/chat/completions",
                json=request.model_dump(mode="json"),
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            result = resp.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Backend error: {e}")

    latency = int((time.time() - start) * 1000)
    await log_usage(key_record["id"], request.model, latency)

    return result

async def streaming_completion(backend_url, request, key_record, start):
    timeout = httpx.Timeout(300.0, connect=30.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        try:
            async with client.stream(
                "POST",
                f"{backend_url}/v1/chat/completions",
                json=request.model_dump(mode="json"),
                headers={"Content-Type": "application/json"},
            ) as resp:
                if resp.status_code != 200:
                    text = await resp.aread()
                    raise HTTPException(status_code=resp.status_code, detail=text)
                
                async def generate():
                    async for line in resp.aiter_lines():
                        if line:
                            yield f"data: {line}\n\n"
                    yield "data: [DONE]\n\n"

                return Response(
                    content=generate(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                    },
                )
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Backend error: {e}")

async def log_usage(key_id: int, model: str, latency_ms: int):
    import aiosqlite
    from database import DATABASE_PATH
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute(
                "INSERT INTO usage_log (key_id, model, latency_ms) VALUES (?, ?, ?)",
                (key_id, model, latency_ms)
            )
            await db.commit()
    except Exception:
        pass
```

- [ ] **Step 2: Run and test**

Run: `cd llm-api-gateway && uvicorn main:app --port 8000 --reload &` then `sleep 2 && curl http://localhost:8000/health`
Expected: `{"status":"ok","models":["glm5"]}`

- [ ] **Step 3: Commit**

```bash
git add llm-api-gateway/main.py
git commit -m "feat: add main API with chat completions, models, and health endpoints"
```

---

## Task 9: Integration Tests

**Files:**
- Create: `llm-api-gateway/tests/conftest.py`
- Create: `llm-api-gateway/tests/test_endpoints.py`

- [ ] **Step 1: Write conftest.py**

```python
import pytest
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

@pytest.fixture
async def client():
    from database import init_db, DATABASE_PATH
    if os.path.exists(DATABASE_PATH):
        os.remove(DATABASE_PATH)
    await init_db()
    
    from main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    
    if os.path.exists(DATABASE_PATH):
        os.remove(DATABASE_PATH)
```

- [ ] **Step 2: Write integration tests**

```python
import pytest
import hashlib

@pytest.fixture
async def auth_headers():
    from database import DATABASE_PATH, init_db
    import aiosqlite
    await init_db()
    raw_key = "sk-test-integration-key"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO api_keys (key_hash, owner, requests_per_minute, active) VALUES (?, ?, ?, ?)",
            (key_hash, "integration-test", 1000, 1)
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
        json={"model": "glm5", "messages": [{"role": "user", "content": "hi"}]}
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
```

- [ ] **Step 3: Run integration tests**

Run: `cd llm-api-gateway && pytest tests/test_endpoints.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add llm-api-gateway/tests/conftest.py llm-api-gateway/tests/test_endpoints.py
git commit -m "test: add integration tests for API endpoints"
```

---

## Task 10: Dockerfile

**Files:**
- Create: `llm-api-gateway/Dockerfile`

- [ ] **Step 1: Write Dockerfile**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Test the container builds**

Run: `cd llm-api-gateway && docker build -t llm-gateway . && docker run --rm -p 8001:8000 llm-gateway &` then `sleep 2 && curl http://localhost:8001/health`
Expected: Health check returns ok

- [ ] **Step 3: Commit**

```bash
git add llm-api-gateway/Dockerfile
git commit -m "chore: add Dockerfile for containerized deployment"
```

---

## Self-Review Checklist

1. **Spec coverage:** All spec sections implemented — scaffold, database, key management, auth, rate limiter, router, schemas, endpoints, streaming, tests, Dockerfile.
2. **Placeholder scan:** No TBD, TODO, or vague requirements. All code is complete.
3. **Type consistency:** Pydantic schemas define exact types used in main.py. Database column names match query parameters.

---

**Plan complete.** Saved to `docs/superpowers/plans/2026-04-14-glm5-openai-gateway-plan.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
