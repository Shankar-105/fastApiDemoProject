import pytest
import pytest_asyncio
import asyncio
import os, sys
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool
from httpx import AsyncClient, ASGITransport

# pytest doesnt see anything except the tests sub-folder so we need to add the
# project path to pythonpath so that now pytest can see all the project folders

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# after setting the PYTHONPATH then import any other folders in project dir
from app.main import app
import app.main as app_main
from app.models import Base
from app.db import getDb
from app import db as app_db
from app.config import settings

# Mock Redis with fakeredis (no real Redis server needed for tests)
import fakeredis
from app.services import redis_service
redis_service.redis_client = fakeredis.FakeAsyncRedis(decode_responses=True)

# Redis pubsub listener is not required for API-level tests and can add latency.
async def _skip_listener_startup() -> bool:
    return False

app_main.check_redis_connection = _skip_listener_startup

# Mock OTP generation + email sending for deterministic and fast tests.
from app.services import otp_service
from app.services import email_service
from app.my_utils import utils as password_utils

def _fixed_otp() -> str:
    return "123456"

async def _noop_send(*args, **kwargs):
    return None

otp_service.generateOtp = _fixed_otp
email_service.send_otp_email = _noop_send
email_service.send_verification_email = _noop_send

# Run Celery tasks eagerly in tests to avoid needing a running broker.
from app.celery_app import celery_app
celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True

# Replace actual Celery task objects with no-op tasks to avoid asyncio.run
# being executed inside the test event loop (which raises RuntimeError).
import app.tasks.email_tasks as _email_tasks

class _NoopCeleryTask:
    def delay(self, *args, **kwargs):
        return None
    def apply_async(self, *args, **kwargs):
        return None

_email_tasks.send_otp_email = _NoopCeleryTask()
_email_tasks.send_verification_email = _NoopCeleryTask()
# Also override any module-level imports that bound these task objects at import time
import app.routes.users as _routes_users
import app.routes.auth as _routes_auth
import app.routes.connect as _routes_connect
import app.tasks.notification_tasks as _notification_tasks
_routes_users.send_verification_email_task = _NoopCeleryTask()
_routes_auth.send_verification_email_task = _NoopCeleryTask()
_routes_connect.create_notification_task = _NoopCeleryTask()
_notification_tasks.create_notification_task = _NoopCeleryTask()

# Speed up auth-heavy tests by replacing bcrypt with deterministic test doubles.
async def _fast_hash_password(raw: str) -> str:
    return f"test-hash::{raw}"


async def _fast_verify_password(raw: str, hashed: str) -> bool:
    return hashed == f"test-hash::{raw}"


password_utils.hashPassword = _fast_hash_password
password_utils.verifyPassword = _fast_verify_password

# Disable rate limiting in tests.
# All test requests come from the same fake IP and the test session makes far
# more signup / post / comment calls than the production limits allow.
# We patch _check to a no-op so every dependency returns None immediately.
# The closures inside ip_rate_limit() and user_rate_limit() call `_check` by
# looking it up in rate_limiter's global namespace at call-time, so replacing
# the module attribute is all that's needed — same pattern as the fakeredis patch.
from app import rate_limiter as _rate_limiter
async def _noop_check(key: str, max_calls: int, window: int) -> None:
    pass
_rate_limiter._check = _noop_check

# make notification_service to use the test DB session factory !
# notification_service.create_notification() opens its own session (it can't
# use the request's session because BackgroundTasks run after it closes).
# so we redirect the tests to use the TestingAsyncSessionLocal so it writes to the test DB.
from app.services import notification_service

# SMART DATABASE HOST DETECTION FOR DOCKER vs LOCAL

def get_test_database_host():
    """
    Automatically detect if running in Docker container and return appropriate host.
    Detection methods (in order):
    1. Check for /.dockerenv file (exists in Docker containers)
    2. Check if DATABASE_HOST env var is explicitly set to 'db'
    3. Fall back to settings.database_host (localhost for local testing)
    
    Returns:
        str: 'db' if in Docker, 'localhost' (or custom) if local
    """
    # Method 1: Check for Docker environment file
    if os.path.exists('/.dockerenv'):
        return 'db'
    
    # Method 2: Check environment variable override
    env_host = os.getenv('DATABASE_HOST')
    if env_host and env_host == 'db':
        return 'db'
    
    # Method 3: Default to settings (localhost for local testing)
    return settings.database_host

# Use smart detection
TEST_DATABASE_HOST = get_test_database_host()

# PostgreSQL is case-insensitive by default and converts unquoted names to lowercase.
# We standardize on lowercase to prevent mismatches between creation and connection.
TEST_DB_NAME = f"{settings.database_name}_test".lower()

# Sync URL (psycopg2 — for creating/dropping the test DB and table management)
TEST_SYNC_URL = (
    f"postgresql://{settings.database_user}:{settings.database_password}"
    f"@{TEST_DATABASE_HOST}/{TEST_DB_NAME}"
)

# Async URL (asyncpg — for the test session override)
TEST_ASYNC_URL = (
    f"postgresql+asyncpg://{settings.database_user}:{settings.database_password}"
    f"@{TEST_DATABASE_HOST}/{TEST_DB_NAME}"
)

# Debug output to verify detection (helpful for troubleshooting)
print(f"[TEST] DB Host detected: {TEST_DATABASE_HOST}")
print(f"[TEST] DB URL: postgresql://***:***@{TEST_DATABASE_HOST}/{TEST_DB_NAME}")

# CREATE TEST DATABASE IF IT DOESN'T EXIST

def create_test_database_if_not_exists():
    """
    Create the test database if it doesn't exist.
    Connects to the default 'postgres' database to create our test database.
    Uses sync psycopg2 since this runs before the async event loop.
    """
    # Connect to default 'postgres' database to allow DB creation
    default_db_url = (
        f"postgresql://{settings.database_user}:{settings.database_password}"
        f"@{TEST_DATABASE_HOST}/postgres"
    )
    
    default_engine = create_engine(default_db_url, isolation_level="AUTOCOMMIT")
    
    try:
        with default_engine.connect() as conn:
            # Check if database exists (using the same lowercase name)
            result = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
                {"dbname": TEST_DB_NAME}
            )
            exists = result.scalar() is not None
            
            if not exists:
                print(f"[CREATE] Creating test database: {TEST_DB_NAME}")
                conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
                print(f"[SUCCESS] Test database created successfully!")
            else:
                print(f"[SUCCESS] Test database already exists: {TEST_DB_NAME}")
    except ProgrammingError as e:
        if "already exists" in str(e).lower():
            print(f"[SUCCESS] Test database already exists: {TEST_DB_NAME}")
        else:
            print(f"[ERROR] Programming Error: {e}")
            raise
    except Exception as e:
        print(f"[ERROR] Error checking/creating test database: {e}")
        raise
    finally:
        default_engine.dispose()

# Create test database before creating engines
create_test_database_if_not_exists()

# ── Sync engine (only for table creation/drop — psycopg2) ──
sync_test_engine = create_engine(TEST_SYNC_URL)

# ── Async engine + session factory (for test runtime — asyncpg) ──
# NullPool prevents connection reuse — each session gets a fresh connection.
# This avoids the "another operation is in progress" asyncpg error that occurs
# when a pooled connection is returned with a pending transaction.
async_test_engine = create_async_engine(TEST_ASYNC_URL, poolclass=NullPool)
TestingAsyncSessionLocal = async_sessionmaker(
    bind=async_test_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

# Redirect notification background tasks to the test DB
# notification_service.create_notification() opens its own session using
# _session_factory.  Without this change it would try to write to the
# production DB which doesn't have the test users, causing FK violations and other errors.
notification_service._session_factory = TestingAsyncSessionLocal

# pytest fixtures very helpful
@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    # Setup: Drop and recreate tables for a clean start (sync — runs before event loop)
    print("[SETUP] Dropping all existing tables...")
    Base.metadata.drop_all(bind=sync_test_engine)
    print("[SETUP] Creating all tables...")
    Base.metadata.create_all(bind=sync_test_engine)
    print("[SUCCESS] Test database setup complete!")
    yield
    # Teardown: Delete the test database after all tests are finished
    print(f"\n[TEARDOWN] Cleaning up test database: {TEST_DB_NAME}...")
    # First, dispose engines to close all active connections
    asyncio.run(async_test_engine.dispose())
    asyncio.run(app_db.async_engine.dispose())
    asyncio.run(redis_service.redis_client.aclose())
    sync_test_engine.dispose()
    # Connect to the default 'postgres' database to perform the drop
    cleanup_db_url = (
        f"postgresql://{settings.database_user}:{settings.database_password}"
        f"@{TEST_DATABASE_HOST}/postgres"
    )
    cleanup_engine = create_engine(cleanup_db_url, isolation_level="AUTOCOMMIT")
    try:
        with cleanup_engine.connect() as conn:
            # PostgreSQL 13+ supports WITH (FORCE) to drop DB with active connections
            try:
                conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
            except Exception:
                # Fallback for older PostgreSQL versions
                conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}"'))
            print(f"[SUCCESS] Test database '{TEST_DB_NAME}' deleted successfully!")
    except Exception as e:
        print(f"[ERROR] Error deleting test database: {e}")
    finally:
        cleanup_engine.dispose()

# ── Async DB dependency override ──
async def override_getDb():
    async with TestingAsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.close()

# override the actual dependency with async version
app.dependency_overrides[getDb] = override_getDb

# ── Async HTTP client using httpx (session-scoped) ──
@pytest_asyncio.fixture(scope="session")
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(scope="session")
def db_session_factory():
    return TestingAsyncSessionLocal

@pytest_asyncio.fixture(scope="session")
async def create_test_user(client):
    user_data = {
        "username": "testuser",
        "password": "testpassword",
        "nickname": "TestUser",
        "email": "testuser@example.com",
    }
    resp = await client.post("/user/signup", json=user_data)
    assert resp.status_code in (201, 409)  # 201=created, 409=already exists

    verify = await client.post(
        "/verify-email",
        json={"email": user_data["email"], "otp": "123456"},
    )
    assert verify.status_code in (200, 404)

    return user_data

# preserve the token!
@pytest_asyncio.fixture(scope="session")
async def get_token(client, create_test_user):
    data = {
        "username": create_test_user["username"],
        "password": create_test_user["password"]
    }
    resp = await client.post("/login", data=data)
    assert resp.status_code == 202
    token = resp.json()["accessToken"]
    return token
