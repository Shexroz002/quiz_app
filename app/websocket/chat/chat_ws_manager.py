from fastapi.websockets import WebSocket


class ConnectionManager:
    def __init__(self):
        # user_id -> set of WebSocket connections (multi-device)
        self.connections: dict[str, set[WebSocket]] = {}

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.connections.setdefault(user_id, set()).add(ws)

    def disconnect(self, user_id: str, ws: WebSocket):
        if user_id in self.connections:
            self.connections[user_id].discard(ws)
            if not self.connections[user_id]:
                del self.connections[user_id]

    async def send_to_user(self, user_id: str, message: dict):

        for ws in self.connections.get(user_id, set()).copy():
            try:
                await ws.send_json(message)
            except Exception:

                self.connections[user_id].discard(ws)

    def is_online(self, user_id: str) -> bool:
        return user_id in self.connections and len(self.connections[user_id]) > 0

chat_manager = ConnectionManager()