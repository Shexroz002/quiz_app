from typing import Type, TypeVar, Generic, Optional, Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

ModelType = TypeVar("ModelType")


class BaseRepository(Generic[ModelType]):

    def __init__(self, model: Type[ModelType], db: AsyncSession):
        self.model = model
        self.db = db

    async def get(self, obj_id: int) -> Optional[ModelType]:
        stmt = select(self.model).where(self.model.id == obj_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list(self) -> Sequence[ModelType]:
        result = await self.db.execute(select(self.model))
        return result.scalars().all()

    async def create(self, obj_data: dict,commit:bool=True) -> ModelType:
        obj = self.model(**obj_data)
        self.db.add(obj)
        await self.db.flush()
        if commit:
            await self.db.commit()
            await self.db.refresh(obj)
        return obj

    async def delete(self, obj: ModelType):
        await self.db.delete(obj)

    async def update(
            self,
            obj: ModelType,
            update_data: dict,
            *,
            commit: bool = True,
    ) -> ModelType:

        for field, value in update_data.items():
            if hasattr(obj, field):
                setattr(obj, field, value)

        self.db.add(obj)
        if commit:
            await self.db.commit()
            await self.db.refresh(obj)
        return obj
