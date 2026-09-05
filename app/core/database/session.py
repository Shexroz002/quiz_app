from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"server_settings": {"timezone": settings.DATABASE_TIME_ZONE}},
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
