
import json
from redis.asyncio import Redis
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Contact
from app.models.chat.chat_members import ChatMember

ONLINE_TTL_SECONDS = 60

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

async def set_user_online(redis: Redis, user_id: int, online: bool):
    """User'ni online/offline deb belgilash va do'stlarga xabar berish."""
    if online:
        await redis.setex(f"online:{user_id}", ONLINE_TTL_SECONDS, "1")
        status = "online"
    else:
        await redis.delete(f"online:{user_id}")
        await redis.set(f"last_seen:{user_id}", now_iso())
        status = "offline"

    payload = json.dumps({
        "user_id": user_id,
        "status": status,
        "last_seen_at": now_iso() if status == "offline" else None,
    })
    await redis.publish(f"presence:{user_id}", payload)


async def touch_user_presence(redis: Redis, user_id: str):
    """Heartbeat - faqat TTL ni yangilash, event yubormaslik."""
    await redis.setex(f"online:{user_id}", ONLINE_TTL_SECONDS, "1")


async def get_user_presence(redis: Redis, user_id: str) -> dict:
    is_online = await redis.exists(f"online:{user_id}")
    if is_online:
        return {"status": "online", "last_seen_at": None}
    last_seen = await redis.get(f"last_seen:{user_id}")
    return {"status": "offline", "last_seen_at": last_seen}


async def get_user_chat_ids(session: AsyncSession, user_id: int) -> list[int]:
    """Foydalanuvchi a'zo bo'lgan barcha chatlarning ID lari."""
    stmt = select(ChatMember.chat_id).where(ChatMember.user_id == user_id)
    result = await session.execute(stmt)
    return [row[0] for row in result.all()]


async def get_user_friend_ids(session: AsyncSession, user_id: int) -> list[int]:
    """Foydalanuvchining qabul qilingan do'stlarining ID lari."""
    stmt = (
        select(Contact.friend_id)
        .where(
            Contact.user_id == user_id,
        )
    )
    result = await session.execute(stmt)
    return [row[0] for row in result.all()]