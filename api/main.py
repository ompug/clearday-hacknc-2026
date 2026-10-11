"""ASGI entry point: FastAPI for HTTP, python-socketio mounted alongside on /socket.io.

Run with: uv run uvicorn api.main:app --port 8000
"""

import logging

import psycopg
import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import get_settings
from api.db import connect_async
from api.nessie.background import lifespan
from api.realtime import sio
from api.routes import assistant as assistant_routes
from api.routes import expenses, payments, reads, session
from api.routes import forecast as forecast_routes
from api.routes import insights as insights_routes
from api.routes import voice as voice_routes

log = logging.getLogger("clearday.api")

settings = get_settings()

fastapi_app = FastAPI(
    title="Clearday API", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan
)
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.web_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

fastapi_app.include_router(session.router)
fastapi_app.include_router(reads.router)
fastapi_app.include_router(payments.router)
fastapi_app.include_router(expenses.router)
fastapi_app.include_router(forecast_routes.router)
fastapi_app.include_router(assistant_routes.router)
fastapi_app.include_router(voice_routes.router)
fastapi_app.include_router(insights_routes.router)


@fastapi_app.get("/api/health")
async def health() -> JSONResponse:
    try:
        async with await connect_async() as conn:
            await conn.execute("SELECT 1")
    except (psycopg.Error, OSError) as exc:
        # Class name only: driver messages can include the host or user.
        log.warning("health: database unreachable (%s)", type(exc).__name__)
        return JSONResponse({"status": "degraded", "db": "unreachable"}, status_code=503)
    return JSONResponse({"status": "ok", "db": "ok"})


app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)
