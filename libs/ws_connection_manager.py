import asyncio
from fastapi import WebSocket

from libs.logger import logger


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"New connection established for session_id: {session_id}")

    def disconnect(self, session_id: str):
        self.active_connections.pop(session_id, None)

    async def send_personal_message(self, message: dict[str, str], session_id: str):
        websocket = self.active_connections.get(session_id)
        if websocket:
            try:
                await asyncio.wait_for(websocket.send_json(message), timeout=5.0)
                logger.info(f"Sent message to {session_id}: {message}")
            except Exception as e:
                logger.error(f"Error sending message to {session_id}: {e}")
                self.disconnect(session_id)
        else:
            logger.warning(
                f"Attempted to send message to {session_id} but no active connection found."
            )


ws_manager = ConnectionManager()
