from typing import Any, Mapping
from datetime import datetime, timezone
from bson.errors import InvalidId
from pymongo import ReturnDocument
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.schemas.chat.message_schema import MessageCreate, MessageUpdate


class MessageRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.col = db["messages"]

    async def create(self, data: MessageCreate) -> dict:
        doc = {
            "chat_id": data.chat_id,
            "sender_id": data.sender_id,
            "text": data.text,
            "reply_to_message_id": data.reply_to_message_id,
            "forwarded_from": data.forwarded_from,
            "attachments": [a.model_dump() for a in data.attachments],
            "reactions": [],
            "mentions": data.mentions,
            "is_read": False,
            "views_count": 0,
            "edited": False,
            "deleted": False,
            "created_at": datetime.utcnow(),
            "edited_at": None,
        }
        result = await self.col.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        return doc

    async def get_by_id(self, message_id: str) -> Mapping[str, Any] | None:
        doc = await self.col.find_one({"_id": ObjectId(message_id), "deleted": False})
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc

    async def get_chat_messages(self, chat_id: int, limit: int = 50, before_id: str | None = None, ) -> list[
        Mapping[str, Any]]:
        query: dict = {"chat_id": chat_id, "deleted": False}

        if before_id:
            query["_id"] = {"$lt": ObjectId(before_id)}

        cursor = self.col.find(query).sort("_id", -1).limit(limit)
        messages = await cursor.to_list(length=limit)

        for m in messages:
            m["_id"] = str(m["_id"])

        return messages[::-1]

    async def update(self, message_id: str, sender_id: int, data: MessageUpdate) -> Mapping[str, Any] | None:
        try:
            oid = ObjectId(message_id)
        except InvalidId:
            return None

        doc = await self.col.find_one_and_update(
            {"_id": oid, "sender_id": int(sender_id), "deleted": False},
            {"$set": {
                "text": data.text,
                "edited": True,
                "edited_at": datetime.now(timezone.utc),
            }},
            return_document=ReturnDocument.AFTER,
        )
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc

    async def soft_delete(self, message_id: str, sender_id: int) -> bool:
        try:
            oid = ObjectId(message_id)
        except InvalidId:
            return False
        result = await self.col.update_one(
            {"_id": oid, "sender_id": int(sender_id)},
            {"$set": {"deleted": True}},
        )
        return result.modified_count > 0

    async def toggle_reaction(self, message_id: str, user_id: int, emoji: str) -> Mapping[str, Any] | None:
        doc = await self.col.find_one({"_id": ObjectId(message_id)})
        if not doc:
            return None

        reactions: list = doc.get("reactions", [])
        reaction = next((r for r in reactions if r["emoji"] == emoji), None)
        reaction_toggle = True
        if reaction:
            if user_id in reaction["user_ids"]:
                reaction["user_ids"].remove(user_id)
                reaction_toggle = False
            else:
                reaction["user_ids"].append(user_id)

            reactions = [r for r in reactions if r["user_ids"]]
        else:
            reactions.append({"emoji": emoji, "user_ids": [user_id]})

        updated = await self.col.find_one_and_update(
            {"_id": ObjectId(message_id)},
            {"$set": {"reactions": reactions}},
            return_document=True,
        )
        data = {
            "message_id": message_id,
            "emoji": emoji,
            "added": reaction_toggle,
            "sender_id": user_id
        }
        return data

    async def increment_views(self, message_id: str) -> None:
        await self.col.update_one(
            {"_id": ObjectId(message_id)},
            {"$inc": {"views_count": 1}},
        )

    async def mark_as_read(self, message_ids: list[str]) -> None:
        object_ids = [ObjectId(mid) for mid in message_ids]
        await self.col.update_many(
            {"_id": {"$in": object_ids}},
            {"$set": {"is_read": True}},
        )

    async def get_last_message(self, chat_id: int) -> dict | None:
        doc = await self.col.find_one(
            {"chat_id": chat_id, "deleted": False},
            sort=[("created_at", -1)],
        )
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc
