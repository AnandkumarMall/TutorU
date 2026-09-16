import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from dotenv import load_dotenv

load_dotenv()

# Ensure the instance directory exists
os.makedirs('instance', exist_ok=True)

# Convert a plain sqlite:// URL to the async sqlite+aiosqlite:// driver.
# This lets DATABASE_URL be set as a plain sqlite:// in the environment without
# requiring the caller to know about the aiosqlite driver suffix.
_raw_url = os.environ.get('DATABASE_URL', 'sqlite:///instance/courses.db')
if _raw_url.startswith('sqlite://') and '+aiosqlite' not in _raw_url:
    SQLALCHEMY_DATABASE_URL = _raw_url.replace('sqlite://', 'sqlite+aiosqlite://', 1)
else:
    SQLALCHEMY_DATABASE_URL = _raw_url

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=False,
    # aiosqlite manages thread-safety internally; check_same_thread is not applicable
    # For PostgreSQL async, remove the connect_args kwarg entirely.
)

# expire_on_commit=False prevents SQLAlchemy from expiring loaded attributes after commit,
# which would require a second DB round-trip to access them again in async context.
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()


async def get_db():
    """FastAPI dependency that yields an AsyncSession and guarantees cleanup."""
    async with AsyncSessionLocal() as session:
        yield session
