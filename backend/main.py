from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os

from backend.database import create_tables
from backend.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    os.makedirs(settings.upload_dir, exist_ok=True)
    yield


app = FastAPI(
    title="Campus Lost & Found",
    description="Find what you lost. Return what you found.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


@app.get("/health")
def health_check():
    return {"status": "ok", "app": "Campus Lost & Found"}
