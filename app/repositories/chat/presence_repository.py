from redis.asyncio import Redis


class PresenceRepository:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def is_online(self, user_id: int) -> bool:
        """User online'mi tekshiradi."""
        key = f"presence:{user_id}"
        exists = await self.redis.exists(key)
        return bool(exists)

    async def is_online_bulk(self, user_ids: list[int]) -> dict[int, bool]:
        """
        Bir nechta user uchun online statusni bitta Redis call bilan oladi.
        N ta MGET dan ko'ra MGET tezroq, lekin EXISTS multiple key ham yaxshi.
        """
        if not user_ids:
            return {}

        keys = [f"presence:{uid}" for uid in user_ids]
        # MGET - bitta network round-trip
        values = await self.redis.mget(keys)

        return {
            uid: value is not None
            for uid, value in zip(user_ids, values)
        }

    async def get_last_seen(self, user_id: int) -> str | None:
        """Last seen vaqtini ISO format'da qaytaradi."""
        return await self.redis.get(f"last_seen:{user_id}")

    async def get_last_seen_bulk(
            self, user_ids: list[int]
    ) -> dict[int, str | None]:
        if not user_ids:
            return {}

        keys = [f"last_seen:{uid}" for uid in user_ids]
        values = await self.redis.mget(keys)
        return dict(zip(user_ids, values))