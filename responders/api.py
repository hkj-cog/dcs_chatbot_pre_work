from fastapi import APIRouter, WebSocket

router = APIRouter()


@router.websocket("/ws")
async def chat_socket(websocket: WebSocket):
    await websocket.accept()
    # Your Redis logic here
