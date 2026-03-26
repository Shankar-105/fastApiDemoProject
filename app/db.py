from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings as cg

# Detect cloud DB and add SSL if needed
_is_cloud = "azure.com" in cg.database_host
_async_ssl = {"ssl": True} if _is_cloud else {}
_sync_ssl = {"sslmode": "require"} if _is_cloud else {}

# ── Async engine + session (used at runtime by all routes/services) ──
ASYNC_SQL_ALCHEMY_URL = (
    f"postgresql+asyncpg://{cg.database_user}:{cg.database_password}"
    f"@{cg.database_host}/{cg.database_name}"
)

async_engine = create_async_engine(ASYNC_SQL_ALCHEMY_URL, connect_args=_async_ssl)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

# ── Sync engine (used ONLY by Alembic migrations + initial create_all) ──
SYNC_SQL_ALCHEMY_URL = (
    f"postgresql://{cg.database_user}:{cg.database_password}"
    f"@{cg.database_host}/{cg.database_name}"
)

sync_engine = create_engine(SYNC_SQL_ALCHEMY_URL, connect_args=_sync_ssl)

# ── Declarative base (shared by both sync and async) ──
Base = declarative_base()

# ── Async dependency for FastAPI routes ──
async def getDb():
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.close()
