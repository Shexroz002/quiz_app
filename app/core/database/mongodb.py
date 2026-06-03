from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import AsyncGenerator, Annotated
from fastapi import Depends
from app.core.config import settings


client = AsyncIOMotorClient(settings.MONGODB_URL)

async def get_mongo_db() -> AsyncGenerator[AsyncIOMotorDatabase, None]:
    yield client[settings.MONGODB_DB_NAME]

def get_mongo_db_to_method() -> AsyncIOMotorDatabase:
    return client[settings.MONGODB_DB_NAME]

MongoDep = Annotated[AsyncIOMotorDatabase, Depends(get_mongo_db)]