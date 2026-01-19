from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.utils.connection_manager import manager

router = APIRouter(tags=["Voice Chat"])

@router.websocket("/ws/projects/{project_id}/voice")
async def voice_chat_endpoint(websocket: WebSocket, project_id: int):
    await manager.connect(websocket, project_id)
    try:
        while True:
            # 클라이언트의 WebRTC 시그널(Offer, Answer, ICE)을 받아서
            data = await websocket.receive_json()
            # 같은 방의 다른 사람들에게 그대로 전달 (Signaling)
            await manager.broadcast(data, project_id, websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket, project_id)
        # 퇴장 알림 (필요시)
        await manager.broadcast({"type": "user_left"}, project_id, websocket)