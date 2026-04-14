import fastapi

app = fastapi.FastAPI()


@app.get("/health")
async def health():
    return {"status": "ok"}
