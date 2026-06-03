"""
This module save message to db (mongo,Postgre) and return message_id to websocket consumer.
"""
from app.core.database.session import AsyncSessionLocal

async def save_message_to_db(data:dict) -> str:
    pass