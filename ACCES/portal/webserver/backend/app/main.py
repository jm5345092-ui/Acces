from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    ai,
    analysis,
    assistant,
    builds,
    devices,
    generator,
    jobs,
    modifications,
    projects,
    settings as settings_api,
    uploads,
)
from app.core.db import init_db
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    init_db()
    yield


app = FastAPI(title="APK-Lab Server API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(ai.router)
app.include_router(analysis.router)
app.include_router(assistant.router)
app.include_router(builds.router)
app.include_router(devices.router)
app.include_router(generator.router)
app.include_router(jobs.router)
app.include_router(modifications.router)
app.include_router(settings_api.router)
app.include_router(uploads.router)


@app.get("/health")
def health():
    return {"status": "ok"}
