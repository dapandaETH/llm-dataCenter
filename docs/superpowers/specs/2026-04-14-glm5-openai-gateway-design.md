# GLM5 OpenAI-Style API Gateway — Design Spec

## Overview

Build a FastAPI-based proxy gateway that accepts OpenAI-format requests, validates API keys, enforces rate limits, and routes to GLM5 (and other models) running on vLLM instances via vast.ai. The gateway exposes standard OpenAI-compatible endpoints so any OpenAI SDK client can use it.

## Architecture

```
Client (OpenAI SDK) → FastAPI Gateway (VPS) → vLLM Backend (vast.ai)
                         │
                    SQLite DB (API keys, rate limits, usage)
```

### Deployment

- **Gateway**: Separate VPS (e.g., DigitalOcean, Hetzner, $5-10/month)
- **Backend**: GLM5 + vLLM running on vast.ai GPU instance(s)
- **Database**: SQLite (co-located with gateway)

## Data Model

### Database: `gateway.db`

**Table: `api_keys`**
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-increment ID |
| key_hash | TEXT UNIQUE NOT NULL | SHA-256 hash of the API key |
| owner | TEXT NOT NULL | Owner/label for the key |
| created_at | TIMESTAMP | Creation timestamp |
| requests_per_minute | INTEGER DEFAULT 100 | Per-key rate limit |
| active | BOOLEAN DEFAULT 1 | Whether key is active |

**Table: `rate_buckets`**
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-increment ID |
| key_id | INTEGER REFERENCES api_keys(id) | Associated API key |
| window_start | TIMESTAMP | Start of current rate window |
| request_count | INTEGER DEFAULT 0 | Requests in current window |

**Table: `usage_log`**
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-increment ID |
| key_id | INTEGER REFERENCES api_keys(id) | API key used |
| model | TEXT | Model requested |
| timestamp | TIMESTAMP | Request timestamp |
| latency_ms | INTEGER | Request latency |
| tokens_used | INTEGER | Estimated tokens |

## API Endpoints

### `/v1/chat/completions`
- **Method**: POST
- **Auth**: `Authorization: Bearer <api_key>` header
- **Body**: OpenAI Chat Completions format
  ```json
  {
    "model": "glm5",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": false,
    "temperature": 0.7,
    "max_tokens": 1000
  }
  ```
- **Response**: OpenAI Chat Completions response (streaming or non-streaming)

### `/v1/models`
- **Method**: GET
- **Auth**: `Authorization: Bearer <api_key>` header
- **Response**: List of available models

### `/health`
- **Method**: GET
- **Auth**: None
- **Response**: `{"status": "ok", "models": ["glm5", ...]}`

## Functionality

### 1. API Key Management
- Keys stored as SHA-256 hashes in SQLite
- New keys generated via CLI script (`python scripts/create_key.py --owner "user1"`)
- Keys returned once on creation; hashed for storage
- Keys can be revoked by setting `active=0`

### 2. Rate Limiting
- **Per-key**: Configurable limit per API key (default: 100 req/min)
- **Global**: Total limit across all keys (configurable, default: 1000 req/min)
- Uses sliding window algorithm
- Returns `429 Too Many Requests` with `Retry-After` header when exceeded

### 3. Model Routing
- Model → backend URL mapping in `config.yaml`:
  ```yaml
  models:
    glm5:
      backend_url: "http://<vast-ai-ip>:8000"
      display_name: "GLM-5 32B"
    llama3:
      backend_url: "http://<other-ip>:8000"
      display_name: "Llama 3 70B"
  ```
- Requests forwarded to appropriate backend preserving all parameters
- Streaming/non-streaming mode passed through as-is

### 4. Streaming Support
- When `stream: true`, response uses `text/event-stream` (SSE)
- Chunks forwarded from vLLM directly to client
- Proper SSE framing with `data: ` prefix
- `data: [DONE]` sent at end

### 5. Request Forwarding
- Uses `httpx.AsyncClient` for async HTTP
- Timeout: 120 seconds for non-streaming, no timeout for streaming
- Preserves all request headers except hop-by-hop headers
- Returns vLLM errors with appropriate HTTP status codes

## Project Structure

```
llm-api-gateway/
├── main.py                 # FastAPI app entry point, routes, middleware
├── config.yaml             # Model routes, rate limits, global settings
├── database.py             # SQLite setup, queries, migrations
├── auth.py                 # API key validation (dependency)
├── rate_limiter.py         # Rate limiting logic
├── router.py               # Model routing and request forwarding
├── schemas.py              # Pydantic request/response models
├── requirements.txt        # Dependencies
├── scripts/
│   └── create_key.py       # CLI to generate new API keys
├── tests/
│   ├── test_auth.py        # API key validation tests
│   ├── test_rate_limiter.py
│   ├── test_router.py
│   └── test_integration.py
└── Dockerfile              # Optional containerization
```

## Configuration (config.yaml)

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
  llama3:
    backend_url: "http://YOUR_OTHER_IP:8000"
    display_name: "Llama 3 70B"
```

## Security

- API keys hashed with SHA-256 before storage
- Backend URLs never exposed to clients
- Input validation via Pydantic on all request bodies
- Backend request timeout prevents resource exhaustion
- CORS configured for allowed origins (configurable)

## Dependencies

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

## Implementation Order

1. Project scaffold, dependencies, config
2. Database setup and migrations
3. API key management scripts
4. Auth dependency (key validation)
5. Rate limiter
6. Model router
7. Chat completions endpoint
8. Models listing endpoint
9. Health endpoint
10. Streaming support
11. Tests
12. Dockerfile (optional)
