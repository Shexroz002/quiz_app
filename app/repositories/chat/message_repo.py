from datetime import datetime, timezone
from typing import Any, Mapping

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

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
            "attachments": data.attachments,
            "reactions": [],
            "mentions": [m for m in data.mentions],
            "views_count": 0,
            "edited": False,
            "deleted": False,
            "created_at": datetime.utcnow(),
            "edited_at": None,
        }
        result = await self.col.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        return doc

    async def forward_message(self, original_message_id: str, target_chat_id: int, current_user_id: int,
                              sender_name: str):
        original = await self.col.find_one({
            "_id": ObjectId(original_message_id),
            "deleted": False,
        })

        if not original:
            return None

        new_message = {
            "chat_id": target_chat_id,
            "sender_id": current_user_id,
            "sender_name": sender_name,
            "text": original.get("text", ""),
            "attachments": original.get("attachments", []),

            "forwarded_from": {
                "message_id": str(original["_id"]),
                "chat_id": original["chat_id"],
                "sender_id": original["sender_id"],
                "sender_name": sender_name,
                "original_created_at": original["created_at"],
            },

            "reply_to_message_id": None,
            "reactions": [],
            "mentions": [],
            "is_read": False,
            "views_count": 0,
            "edited": False,
            "deleted": False,
            "created_at": datetime.utcnow(),
            "edited_at": None,
        }

        result = await self.col.insert_one(new_message)

        new_message["_id"] = result.inserted_id
        return new_message

    async def get_by_id(self, message_id: str) -> Mapping[str, Any] | None:
        doc = await self.col.find_one({"_id": ObjectId(message_id), "deleted": False})
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc

    async def get_chat_messages(
            self,
            chat_id: int,
            limit: int = 50,
            before_id: str | None = None,
    ) -> list[Mapping[str, Any]]:

        match_query: dict[str, Any] = {
            "chat_id": chat_id,
            "deleted": False,
        }

        if before_id:
            match_query["_id"] = {"$lt": ObjectId(before_id)}

        pipeline = [
            {"$match": match_query},
            {"$sort": {"_id": -1}},
            {"$limit": limit},

            {
                "$addFields": {
                    "reply_object_id": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$ne": ["$reply_to_message_id", None]},
                                    {"$ne": ["$reply_to_message_id", ""]},
                                ]
                            },
                            {"$toObjectId": "$reply_to_message_id"},
                            None,
                        ]
                    }
                }
            },
            {
                "$lookup": {
                    "from": "messages",
                    "localField": "reply_object_id",
                    "foreignField": "_id",
                    "as": "reply_message_data",
                }
            },
            {
                "$addFields": {
                    "reply_message": {
                        "$cond": [
                            {"$gt": [{"$size": "$reply_message_data"}, 0]},
                            {
                                "sender_id": {
                                    "$arrayElemAt": [
                                        "$reply_message_data.sender_id",
                                        0,
                                    ]
                                },
                                "text": {
                                    "$arrayElemAt": [
                                        "$reply_message_data.text",
                                        0,
                                    ]
                                },
                            },
                            None,
                        ]
                    }
                }
            },
            {
                "$project": {
                    "reply_object_id": 0,
                    "reply_message_data": 0,
                }
            },
            {"$sort": {"_id": 1}},
        ]

        cursor = self.col.aggregate(pipeline)
        messages = await cursor.to_list(length=limit)

        for m in messages:
            m["_id"] = str(m["_id"])

            if m.get("created_at"):
                m["created_at"] = m["created_at"].isoformat()

            if m.get("edited_at"):
                m["edited_at"] = m["edited_at"].isoformat()

            if m.get("forwarded_from"):
                original_created_at = m["forwarded_from"].get("original_created_at")
                if original_created_at and hasattr(original_created_at, "isoformat"):
                    m["forwarded_from"]["original_created_at"] = original_created_at.isoformat()

        return messages

    async def update(self, message_id: str, sender_id: int, data: MessageUpdate) -> Mapping[str, Any] | None:
        try:
            oid = ObjectId(message_id)
        except InvalidId:
            return None

        doc = await self.col.find_one_and_update(
            {"_id": oid, "sender_id": sender_id, "deleted": False},
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

    async def get_unread_counts(self, cursors: dict[int, str | None], current_user_id: int, ) -> dict[int, int]:
        if not cursors:
            return {}

        or_branches = []
        for chat_id, last_read_id in cursors.items():
            branch = {"chat_id": chat_id}
            if last_read_id:
                branch["_id"] = {"$gt": ObjectId(last_read_id)}
            or_branches.append(branch)

        pipeline = [
            {
                "$match": {
                    "$or": or_branches,
                    "deleted": False,
                    "sender_id": {"$ne": current_user_id},
                }
            },
            {
                "$group": {
                    "_id": "$chat_id",
                    "count": {"$sum": 1},
                }
            },
        ]
        result = {chat_id: 0 for chat_id in cursors}
        async for item in self.col.aggregate(pipeline):
            result[item["_id"]] = item["count"]
        return result
