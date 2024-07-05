"""
This module implements the remote agent communication with the server over
WebSockets.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

@router.websocket('/agent/connect')
async def agent_connect(websocket: WebSocket):
    """
    This function processes connections from remote agents to this server
    over WebSockets.
    """
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            print(f"Message received over websocket: {data}")
            await websocket.send_text(f"Message text as: {data}")
    except WebSocketDisconnect:
        print("Disconnected")
