from fastapi import FastAPI

app = FastAPI(title="模拟 OA 后端", version="0.1.0")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "oa",
    }