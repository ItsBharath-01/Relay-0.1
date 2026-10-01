from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.core.config import settings
from app.core.database import init_db
from app.api.health import router as health_router
from app.api.auth import router as auth_router
from app.api.goals import router as goals_router
from app.api.plans import router as plans_router
from app.api.executions import router as executions_router
from app.api.approvals import router as approvals_router
from app.api.connections import router as connections_router
from app.api.history import router as history_router
from app.api.voice import router as voice_router
from app.api.catalog import router as catalog_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("relay")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Relay - Autonomous Work Agent Backend",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all API Routers under /api and /api/v1
routers = [
    health_router,
    auth_router,
    goals_router,
    plans_router,
    executions_router,
    approvals_router,
    connections_router,
    history_router,
    voice_router,
    catalog_router,
]

for r in routers:
    app.include_router(r, prefix="/api")
    app.include_router(r, prefix="/api/v1")

@app.get("/")
async def root():
    return {
        "name": "Relay Autonomous Work Agent API",
        "version": "0.2.0",
        "status": "online",
        "docs": "/docs",
        "llm_provider": settings.LLM_PROVIDER,
        "ollama_model": settings.OLLAMA_MODEL,
    }

@app.on_event("startup")
async def startup_event():
    logger.info("Initializing database tables...")
    await init_db()
    logger.info(f"Relay API online. LLM Provider: {settings.LLM_PROVIDER}, Model: {settings.OLLAMA_MODEL}")
