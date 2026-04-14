# LLM API Gateway
An OpenAI-compatible API gateway for self-hosted LLM inference backends (vLLM on vast.ai). Provides API key authentication, per-key and global rate limiting, multi-model routing, and streaming support.
## Table of Contents
- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Server](#running-the-server)
- [Managing API Keys](#managing-api-keys)
- [API Reference](#api-reference)
- [Docker Deployment](#docker-deployment)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
## Features
- **OpenAI-compatible API** — drop-in replacement for `https://api.openai.com/v1` endpoints
- **API key authentication** — SHA-256 hashed keys, Bearer token auth
- **Per-key rate limiting** — configurable requests-per-minute per API key
- **Global rate limiting** — protects backend from aggregate overload
- **Multi-model routing** — route requests to different backends based on model name
- **Streaming support** — Server-Sent Events (SSE) for streaming completions
- **Usage logging** — tracks model, latency, and key usage per request
- **Async architecture** — built on FastAPI + aiosqlite for non-blocking I/O
- **Docker-ready** — includes Dockerfile with health check
## Architecture
```
Client (OpenAI SDK / curl)
    │
    ▼
┌─────────────────────────────────────┐
│         LLM API Gateway            │
│                                     │
│  ┌───────────┐  ┌────────────────┐  │
│  │   Auth    │  │  Rate Limiter  │  │
│  │ (API key  │  │  (per-key +    │  │
│  │  verify)  │  │   global)      │  │
│  └─────┬─────┘  └───────┬────────┘  │
│        │                │           │
│        ▼                ▼           │
│  ┌─────────────────────────────┐    │
│  │       Model Router          │    │
│  │  (config.yaml → backend)    │    │
│  └─────────────┬───────────────┘    │
│                │                    │
│  ┌─────────────▼───────────────┐    │
│  │    HTTP Proxy (httpx)       │    │
│  │  (non-streaming/streaming)  │    │
│  └─────────────┬───────────────┘    │
│                │                    │
│  ┌─────────────▼───────────────┐    │
│  │     SQLite (gateway.db)     │    │
│  │  api_keys | rate_buckets    │    │
│  │  usage_log                  │    │
│  └─────────────────────────────┘    │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│     vLLM Backend (vast.ai GPU)     │
│     http://YOUR_VAST_AI_IP:8000    │
└─────────────────────────────────────┘
```
**Request flow:**
1. Client sends request with `Authorization: Bearer sk-...`
2. Gateway hashes the key and looks it up in SQLite
3. Per-key rate limit is checked (fixed 60-second window)
4. Global rate limit is checked (sum of all key counts)
5. Rate counter is incremented
6. Model name is resolved to a backend URL via `config.yaml`
7. Request is proxied to the vLLM backend
8. Response is returned to the client (JSON or SSE stream)
## Prerequisites
- Python 3.11+
- A running vLLM instance (e.g., on vast.ai) exposing an OpenAI-compatible API
## Installation
```bash
cd llm-api-gateway
pip install -r requirements.txt
```
**Dependencies:**
| Package | Purpose |
|---------|---------|
| fastapi >= 0.109.0 | Web framework |
| uvicorn[standard] >= 0.27.0 | ASGI server |
| httpx >= 0.26.0 | Async HTTP client for backend proxy |
| aiosqlite >= 0.19.0 | Async SQLite for auth/rate limiting |
| pydantic >= 2.0.0 | Request/response validation |
| pyyaml >= 6.0 | YAML config parsing |
| python-dotenv >= 1.0.0 | Environment variable loading |
| pytest >= 8.0.0 | Testing |
| pytest-asyncio >= 0.23.0 | Async test support |
## Configuration
Edit `config.yaml` to configure the gateway:
```yaml
app:
  host: "0.0.0.0"        # Bind address
  port: 8000              # Listen port
  debug: false            # Debug mode
rate_limits:
  global_requests_per_minute: 1000          # Total across all keys
  default_per_key_requests_per_minute: 100  # Default per API key
vllm:
  timeout_seconds: 120    # Backend request timeout
models:
  glm5:                                        # Model ID (used in requests)
    backend_url: "http://YOUR_VAST_AI_IP:8000" # vLLM backend URL
    display_name: "GLM-5 32B"                  # Display name for /v1/models
  # Add more models:
  # glm4:
  #   backend_url: "http://192.168.1.100:8000"
  #   display_name: "GLM-4"
```
**Environment variables** (override defaults):
| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_PATH` | `gateway.db` | SQLite database file path |
| `CONFIG_PATH` | `config.yaml` | Config file path |
## Running the Server
### Development
```bash
cd llm-api-gateway
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
### Production
```bash
cd llm-api-gateway
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```
The server will:
1. Initialize the SQLite database (creates `gateway.db` if it doesn't exist)
2. Load model routing config from `config.yaml`
3. Start listening on `http://0.0.0.0:8000`
Verify it's running:
```bash
curl http://localhost:8000/health
```
Expected response:
```json
{"status": "ok", "models": ["glm5"]}
```
## Managing API Keys
API keys are managed via the CLI script. Keys are hashed with SHA-256 before storage — only the hash is stored in the database.
### Create a key
```bash
python scripts/create_key.py --owner "my-app" --rate-limit 100
```
Output:
```
Created API key for 'my-app':
  Key: sk-R4nd0mT0k3nH3r3...
WARNING: This key will only be shown once. Do not share it. Treat it like a password.
```
| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--owner` | Yes | — | Label for the key (e.g., app name, user) |
| `--rate-limit` | No | 100 | Requests per minute for this key |
**Important:** The raw key is shown only once. Store it securely. If lost, create a new key.
### Key format
Keys follow the format `sk-<32-char-url-safe-token>` and are passed in the `Authorization` header as a Bearer token:
```
Authorization: Bearer sk-R4nd0mT0k3nH3r3...
```
## API Reference
### `GET /health`
Health check endpoint. No authentication required.
**Response:**
```json
{
  "status": "ok",
  "models": ["glm5"]
}
```
### `GET /v1/models`
Lists available models. Requires authentication.
**Request:**
```bash
curl http://localhost:8000/v1/models \
  -H "Authorization: Bearer sk-YOUR_KEY"
```
**Response:**
```json
{
  "object": "list",
  "data": [
    {
      "id": "glm5",
      "object": "model",
      "created": 1677610602,
      "owned_by": "local",
      "display_name": "GLM-5 32B"
    }
  ]
}
```
### `POST /v1/chat/completions`
Chat completions endpoint. OpenAI-compatible. Requires authentication.
**Request (non-streaming):**
```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer sk-YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "glm5",
    "messages": [
      {"role": "user", "content": "Hello, how are you?"}
    ],
    "temperature": 0.7,
    "max_tokens": 512
  }'
```
**Request (streaming):**
```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer sk-YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "glm5",
    "messages": [
      {"role": "user", "content": "Write a haiku about programming"}
    ],
    "stream": true
  }'
```
**Request body fields:**
| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `model` | string | Yes | — | Model ID (must match a key in `config.yaml`) |
| `messages` | array | Yes | — | Chat messages (`[{role, content}]`) |
| `temperature` | float | No | 0.7 | Sampling temperature (0.0 - 2.0) |
| `top_p` | float | No | 1.0 | Nucleus sampling parameter |
| `max_tokens` | int | No | null | Max tokens to generate |
| `stream` | bool | No | false | Enable SSE streaming |
| `stop` | string/array | No | null | Stop sequences |
| `frequency_penalty` | float | No | 0.0 | Frequency penalty |
| `presence_penalty` | float | No | 0.0 | Presence penalty |
**Response (non-streaming):**
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1677610602,
  "model": "glm5",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "I'm doing well, thank you!"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 12,
    "completion_tokens": 8,
    "total_tokens": 20
  }
}
```
**Response (streaming):**
Server-Sent Events format:
```
data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","choices":[{"delta":{"content":"Hello"}}]}
data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","choices":[{"delta":{"content":" world"}}]}
data: [DONE]
```
### Using with the OpenAI Python SDK
```python
from openai import OpenAI
client = OpenAI(
    api_key="sk-YOUR_KEY",
    base_url="http://your-gateway:8000/v1"
)
# Non-streaming
response = client.chat.completions.create(
    model="glm5",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)
# Streaming
stream = client.chat.completions.create(
    model="glm5",
    messages=[{"role": "user", "content": "Tell me a story"}],
    stream=True
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```
### Error Responses
| Status | Meaning | Cause |
|--------|---------|-------|
| 401 | Unauthorized | Missing or invalid API key |
| 401 | Inactive key | API key has been deactivated |
| 400 | Bad request | Unknown model name |
| 429 | Rate limited | Per-key or global rate limit exceeded |
| 502 | Bad gateway | Backend vLLM server unreachable or error |
Rate-limited responses include a `Retry-After` header:
```json
{
  "detail": "Rate limit exceeded"
}
```
## Docker Deployment
### Build
```bash
cd llm-api-gateway
docker build -t llm-api-gateway .
```
### Run
```bash
docker run -d \
  --name llm-api-gateway \
  -p 8000:8000 \
  -v $(pwd)/config.yaml:/app/config.yaml \
  -v $(pwd)/data:/app/data \
  -e DATABASE_PATH=/app/data/gateway.db \
  llm-api-gateway
```
### Docker Compose
```yaml
version: "3.8"
services:
  gateway:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./config.yaml:/app/config.yaml
      - gateway-data:/app/data
    environment:
      - DATABASE_PATH=/app/data/gateway.db
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 5s
      retries: 3
volumes:
  gateway-data:
```
**Creating API keys inside the container:**
```bash
docker exec llm-api-gateway python scripts/create_key.py --owner "my-app"
```
## Testing
```bash
cd llm-api-gateway
python -m pytest tests/ -v
```
**Test suite (19 tests):**
| Test file | Tests | Coverage |
|-----------|-------|----------|
| `test_auth.py` | 8 | API key validation, missing/invalid/inactive keys, malformed headers |
| `test_rate_limiter.py` | 2 | Per-key allow/block, increment behavior |
| `test_router.py` | 3 | Backend URL resolution, unknown model error, model listing |
| `test_endpoints.py` | 6 | Health check, auth enforcement, model listing, chat completions, rate limiting |
## Project Structure
```
llm-api-gateway/
├── main.py                    # FastAPI app, endpoints, HTTP proxy logic
├── database.py                # SQLite schema and async DB initialization
├── auth.py                    # API key verification (Bearer token)
├── rate_limiter.py            # Per-key and global rate limiting
├── router.py                  # Model name → backend URL routing
├── schemas.py                 # Pydantic request/response models
├── config.yaml                # Model routes and rate limit config
├── requirements.txt           # Python dependencies
├── Dockerfile                 # Container image definition
├── .gitignore
├── scripts/
│   └── create_key.py          # CLI tool to generate API keys
└── tests/
    ├── conftest.py            # Shared fixtures (test client, DB setup)
    ├── test_auth.py           # Auth module tests
    ├── test_rate_limiter.py   # Rate limiter tests
    ├── test_router.py         # Router tests
    └── test_endpoints.py      # Integration tests
```
## How It Works
### Authentication
1. Client sends `Authorization: Bearer sk-abc123...`
2. Gateway strips the `Bearer ` prefix using `str.removeprefix()`
3. Key is hashed with SHA-256
4. Hash is looked up in the `api_keys` SQLite table
5. If found and active, the key record (including `requests_per_minute`) is returned
6. If not found, 401 is returned
Keys are never stored in plaintext. The database only contains SHA-256 hashes.
### Rate Limiting
Two layers of rate limiting are applied sequentially:
**Per-key limit:**
- Each API key has a `requests_per_minute` value (set at key creation, default 100)
- Uses a fixed 60-second window tracked in the `rate_buckets` table
- On each request, expired windows (>60s old) are cleaned up
- If the count for the key's current window is at or above the limit, 429 is returned
- If allowed, the count is incremented after both checks pass
**Global limit:**
- Sums `request_count` across all active `rate_buckets` entries within the last 60 seconds
- If the total is at or above `global_requests_per_minute` (default 1000), 429 is returned
- Protects the backend from aggregate overload across all keys
Both checks must pass before the request is proxied. Rate-limited responses include a `Retry-After` header indicating seconds until the window resets.
### Model Routing
Model routing is configured in `config.yaml`. Each model entry maps a model ID to a backend URL:
```yaml
models:
  glm5:
    backend_url: "http://192.168.1.100:8000"
    display_name: "GLM-5 32B"
```
When a request specifies `"model": "glm5"`, the gateway looks up the corresponding `backend_url` and proxies the request to `http://192.168.1.100:8000/v1/chat/completions`. Unknown model names return a 400 error.
### Streaming
When `stream: true` is set in the request:
1. The gateway opens a streaming connection to the backend using `httpx.AsyncClient.stream()`
2. Backend response lines are relayed as Server-Sent Events (`data: {...}\n\n`)
3. A final `data: [DONE]\n\n` sentinel is sent to signal completion
4. The response uses `text/event-stream` content type with `no-cache` and `keep-alive` headers
5. Streaming timeout is 300 seconds (vs 120 for non-streaming)
### Database Schema
Three SQLite tables:
**`api_keys`** — stores API key hashes and metadata
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment ID |
| key_hash | TEXT UNIQUE | SHA-256 hash of the raw key |
| owner | TEXT | Key owner label |
| created_at | TIMESTAMP | Creation timestamp |
| requests_per_minute | INTEGER | Per-key rate limit (default 100) |
| active | INTEGER | 1 = active, 0 = disabled |
**`rate_buckets`** — tracks request counts per key per time window
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment ID |
| key_id | INTEGER FK | References api_keys(id) |
| window_start | TIMESTAMP | Window start time (epoch) |
| request_count | INTEGER | Requests in this window |
**`usage_log`** — records completed requests for analytics
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment ID |
| key_id | INTEGER FK | References api_keys(id) |
| model | TEXT | Model used |
| timestamp | TIMESTAMP | Request timestamp |
| latency_ms | INTEGER | Response latency in milliseconds |
| tokens_used | INTEGER | Tokens consumed (if reported by backend) |
