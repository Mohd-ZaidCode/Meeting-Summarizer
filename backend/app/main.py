from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers.meetings import router as meetings_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Minute — Meeting Summarizer",
    description="Upload meeting audio, transcribe with Whisper, and generate action-oriented minutes.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meetings_router)


@app.get("/")
def root():
    return {
        "name": "Minute",
        "docs": "/docs",
        "health": "/api/health",
    }
