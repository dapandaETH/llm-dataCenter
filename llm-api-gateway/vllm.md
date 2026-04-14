# Connecting vLLM on vast.ai to the API Gateway

## Architecture

```
Your Laptop / App
       │
       │  requests to: http://YOUR_VPS_IP:8000/v1/chat/completions
       ▼
┌──────────────────────┐
│   Gateway Server     │  ← Deploy this (cheap VPS, not GPU)
│   (this project)     │
│   port 8000          │
└────────┬─────────────┘
         │  forwards to:
         ▼
┌──────────────────────┐
│   vast.ai GPU Node   │  ← vLLM running here
│   port 8000 (vLLM)   │
└──────────────────────┘
```

The gateway is a proxy server you deploy somewhere accessible (e.g., Hetzner, DigitalOcean, or even the same vast.ai machine). Your vLLM runs on a GPU instance on vast.ai.

The gateway proxies your requests to the vLLM backend URL you configure.

---

## What Your vLLM Endpoint Looks Like

When you start vLLM on vast.ai, you get an OpenAI-compatible API. It exposes:

| Endpoint | URL | Auth |
|----------|-----|------|
| Health | `http://YOUR_VAST_AI_IP:8000/health` | None |
| List models | `http://YOUR_VAST_AI_IP:8000/v1/models` | None |
| Chat completions | `http://YOUR_VAST_AI_IP:8000/v1/chat/completions` | None |

### Starting vLLM

```bash
# On your vast.ai instance:
python -m vllm.entrypoints.openai.api_server \
  --model THUDM/glm-5-32b \
  --host 0.0.0.0 \
  --port 8000
```

### Request to vLLM directly (bypassing gateway):

```bash
curl http://YOUR_VAST_AI_IP:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "THUDM/glm-5-32b",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

### vLLM response:

```json
{
  "id": "chatcmpl-8a1b2c",
  "object": "chat.completion",
  "created": 1712000000,
  "model": "THUDM/glm-5-32b",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "Hello! How can I help you today?"
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 12,
    "total_tokens": 22
  }
}
```

---

## Two Connection Patterns

### Pattern 1: Direct to vLLM (no gateway)

Your app → `http://VAST_AI_IP:8000` (vLLM directly)

**Pros:** Simple, no extra server
**Cons:** No API key auth, no rate limiting, no multi-model routing, vLLM is exposed to the internet

### Pattern 2: Through Gateway (recommended)

Your app → `http://YOUR_VPS:8000` (gateway) → `http://VAST_AI_IP:8000` (vLLM)

**Pros:** API key auth, rate limiting, multi-model routing, vLLM stays private
**Cons:** Extra hop (added latency ~5-20ms)

---

## Plugging In Your vLLM — Step by Step

**Step 1:** On vast.ai, start your vLLM instance:

```bash
# SSH into vast.ai instance, then:
python -m vllm.entrypoints.openai.api_server \
  --model THUDM/glm-5-32b \
  --host 0.0.0.0 \
  --port 8000
```

Note the **public IP** of your vast.ai instance (e.g., `123.45.67.89`).

**Step 2:** Edit `config.yaml` on your gateway VPS:

```yaml
models:
  glm5:
    backend_url: "http://123.45.67.89:8000"   # ← your vast.ai IP
    display_name: "GLM-5 32B"
```

**Step 3:** Deploy gateway on a VPS:

```bash
# On your VPS:
git clone https://github.com/dapandaETH/llm-dataCenter.git
cd llm-dataCenter/llm-api-gateway
pip install -r requirements.txt
python scripts/create_key.py --owner "my-app"
# Copy the sk-... key shown
uvicorn main:app --host 0.0.0.0 --port 8000
```

**Step 4:** Use the gateway:

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-...",          # ← key from Step 3
    base_url="http://YOUR_VPS_IP:8000/v1"
)

response = client.chat.completions.create(
    model="glm5",              # ← must match config.yaml
    messages=[{"role": "user", "content": "Hello"}]
)
```

---

## Networking

Your vast.ai instance needs to be **reachable from your VPS**. Options:

1. **Public IP** — vast.ai instances often have public IPs (check your instance details)
2. **SSH tunnel** — forward port from vast.ai to your VPS
3. **Tailscale / WireGuard** — private VPN between the two

If vast.ai blocks inbound access to port 8000, you can use ngrok on the vast.ai instance to create a tunnel, or set up a WireGuard VPN.

---

## Full Request Flow (Gateway to vLLM)

```
Client
  │
  │  POST /v1/chat/completions
  │  Authorization: Bearer sk-...
  │
  ▼
┌─────────────────────────┐
│      FastAPI App        │
│                         │
│  1. LIFESPAN START     │
│     - init_db()         │
│     - load_router()     │
│     - parse config.yaml │
│                         │
│  2. AUTH MIDDLEWARE     │
│     verify_api_key()    │
│     ├─ strip "Bearer "  │
│     ├─ SHA-256 hash key │
│     ├─ lookup in DB     │
│     └─ check active?    │
│          │               │
│          ▼               │
│        401? ──────► END │
│          │               │
│          ▼               │
│  3. RATE LIMIT (key)   │
│     check_rate_limit()  │
│     ├─ cleanup old      │
│     │  buckets (>60s)  │
│     ├─ count requests   │
│     └─ limit exceeded?  │
│          │               │
│          ▼               │
│        429? ──────► END │
│          │               │
│          ▼               │
│  4. RATE LIMIT (global)│
│     check_global_limit()│
│     ├─ SUM all bucket   │
│     │  counts (<60s)    │
│     └─ global exceeded? │
│          │               │
│          ▼               │
│        429? ──────► END │
│          │               │
│          ▼               │
│  5. INCREMENT COUNT    │
│     increment_rate_count│
│     └─ UPDATE bucket    │
│          │               │
│          ▼               │
│  6. MODEL ROUTING      │
│     router.get_backend_ │
│     url(model)          │
│     ├─ lookup config    │
│     └─ resolve URL      │
│          │               │
│          ▼               │
│     Unknown model?      │
│          │               │
│          ▼               │
│        400? ──────► END │
│          │               │
│          ▼               │
│  7. PROXY TO BACKEND   │
│     httpx.AsyncClient   │
│          │               │
│          ▼               │
│    stream=true?         │
│     ├─ YES: stream_     │
│     │    completion()   │
│     │    └─ httpx.stream│
│     │       └─ yield    │
│     │          SSE lines │
│     └─ NO: non_streaming│
│          completion()    │
│          └─ POST to     │
│             backend      │
│          │               │
│          ▼               │
│    Backend error?       │
│     ├─ HTTPStatusError   │
│     │   └─ 502? ──► END │
│     └─ Exception        │
│         └─ 502? ──► END │
│          │               │
│          ▼               │
│  8. LOG USAGE          │
│     log_usage()         │
│     └─ INSERT into      │
│        usage_log        │
│          │               │
│          ▼               │
│  9. RETURN RESPONSE    │
│     (JSON or SSE)       │
│                         │
└─────────────────────────┘
  │
  ▼
Client receives response
```

**Key decision points:**

| Step | Check | Failure | Success |
|------|-------|---------|---------|
| Auth | API key valid & active | 401 Unauthorized | Continue |
| Rate (key) | Per-key RPM not exceeded | 429 + `Retry-After` | Continue |
| Rate (global) | Global RPM not exceeded | 429 + `Retry-After` | Continue |
| Routing | Model in `config.yaml` | 400 Bad Request | Continue |
| Backend | vLLM responds | 502 Bad Gateway | Response |
