"""
main.py
FastAPI application entrypoint for QuantForge Trading Research Platform.
"""

import os
import sys

# Ensure project root is on sys.path so `backend.modules` imports resolve
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

import config
from api.routes import router

app = FastAPI(
    title="QuantForge API",
    description="Mini end-to-end trading research platform",
    version="1.0.0",
)

# CORS — allow React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        config.FRONTEND_URL,
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def root():
    return {"message": "QuantForge API is running", "docs": "/docs"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=True,
        log_level="info",
    )
