from __future__ import annotations

from fastapi import FastAPI

from api.create_bot import router as recall_router
from settings import get_settings


settings = get_settings()

app = FastAPI(title="CallMeRocki", version="0.1.0")
app.include_router(recall_router)


@app.get("/health")
async def health() -> dict[str, str]:
	return {"status": "ok"}


def create_app() -> FastAPI:
	return app
