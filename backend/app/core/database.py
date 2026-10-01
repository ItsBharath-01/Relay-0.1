from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

from app.core.config import settings

# Setup async database engine
# SQLite requires check_same_thread=False
connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args=connect_args,
    future=True,
)

async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an async database session."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db():
    """Initializes tables in database and applies lightweight column migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Migration: ensure executions table has outcome, evidence_level, and outcome_summary
        def migrate_schema(connection):
            from sqlalchemy import inspect, text
            inspector = inspect(connection)
            
            # Executions migrations
            exec_cols = {col["name"] for col in inspector.get_columns("executions")}
            if "outcome" not in exec_cols:
                connection.execute(text("ALTER TABLE executions ADD COLUMN outcome VARCHAR(50)"))
            if "evidence_level" not in exec_cols:
                connection.execute(text("ALTER TABLE executions ADD COLUMN evidence_level VARCHAR(50)"))
            if "outcome_summary" not in exec_cols:
                connection.execute(text("ALTER TABLE executions ADD COLUMN outcome_summary TEXT"))

            # Connections migrations
            conn_cols = {col["name"] for col in inspector.get_columns("connections")}
            if "discovered_tools" not in conn_cols:
                connection.execute(text("ALTER TABLE connections ADD COLUMN discovered_tools JSON"))

        await conn.run_sync(migrate_schema)
