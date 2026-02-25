from typing import Generic, TypeVar
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

ModelType = TypeVar("ModelType")


class BaseService(Generic[ModelType]):

    def __init__(self, repository):
        self.repo = repository

    async def get(self, obj_id: int):
        obj = await self.repo.get(obj_id)

        if not obj:
            raise HTTPException(404, "Object not found")

        return obj

    async def list(self):
        return await self.repo.list()

    async def create(self, data: dict):
        return await self.repo.create(data)

    async def delete(self, obj_id: int):
        obj = await self.get(obj_id)
        await self.repo.delete(obj)
