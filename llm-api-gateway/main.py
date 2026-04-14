import time
import httpx
import aiosqlite
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from database import init_db, DATABASE_PATH
from auth import verify_api_key
from rate_limiter import check_rate_limit, check_global_limit, increment_rate_count
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

    await increment_rate_count(key_id=key_record["id"])

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
            raise HTTPException(
                status_code=e.response.status_code, detail=e.response.text
            )
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
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute(
                "INSERT INTO usage_log (key_id, model, latency_ms) VALUES (?, ?, ?)",
                (key_id, model, latency_ms),
            )
            await db.commit()
    except Exception:
        pass
