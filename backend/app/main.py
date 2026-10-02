from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle using the modern lifespan pattern."""
    logger.info("Initializing database tables...")
    await init_db()

    # P0-3: Clean up any executions stuck in 'running' across server restarts
    try:
        from app.agent.execution_runner import execution_runner
        await execution_runner.cleanup_orphaned_executions()
    except Exception as e:
        logger.warning(f"Startup execution cleanup failed: {e}")

    # Re-register tools from active MCP servers on startup
    try:
        from app.core.database import async_session_maker
        from app.models.entities import Connection
        from app.connections.resolver import ConnectionResolver
        from app.tools.adapters.mcp_adapter import discover_and_register_mcp_tools
        from sqlalchemy import select
        async with async_session_maker() as db:
            mcp_conns = (await db.execute(select(Connection).where(Connection.app_id == "mcp", Connection.status == "connected"))).scalars().all()
            resolver = ConnectionResolver()
            for mc in mcp_conns:
                if mc.encrypted_credentials:
                    try:
                        creds = await resolver.resolve(mc.app_id, mc.user_id, db, allow_reconnection=True)
                        tools = await discover_and_register_mcp_tools(mc.id, mc.name, creds)
                        mc.discovered_tools = tools
                        await db.commit()
                        logger.info(f"Loaded {len(tools)} tools from MCP server '{mc.name}'")
                    except Exception as e:
                        logger.warning(f"Could not connect to MCP server '{mc.name}' on startup: {e}")
    except Exception as e:
        logger.warning(f"MCP startup tool registration error: {e}")

    logger.info(f"Relay API online. LLM Provider: {settings.LLM_PROVIDER}, Model: {settings.OLLAMA_MODEL}")
    yield
    logger.info("Relay API shutting down.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Relay - Autonomous Work Agent Backend",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
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
