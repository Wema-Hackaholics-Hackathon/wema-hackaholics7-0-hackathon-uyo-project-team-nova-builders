from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from core.config import settings
from typing import AsyncGenerator

DEV_DB = settings.DEV_DB
PROD_DB = settings.PROD_DB


engine = create_async_engine(
    DEV_DB,
    echo=True
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession
)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get an async database session"""

    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """Initialize the database by creating all tables"""

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)