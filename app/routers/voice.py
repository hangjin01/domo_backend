# app/routers/voice.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List, Optional
import json

router = APIRouter(tags=["Voice Chat"])

class ConnectionManager:
    def __init__(self):
        # project_id -> { user_id: WebSocket }
        self.active_connections: Dict[str, Dict[int, WebSocket]] = {}

    async def connect(self, websocket: WebSocket, project_id: str, user_id: int):
        await websocket.accept()
        if project_id not in self.active_connections:
            self.active_connections[project_id] = {}

        # 이미 접속 중이라면 기존 연결 끊기 (중복 접속 방지)
        if user_id in self.active_connections[project_id]:
            try:
                await self.active_connections[project_id][user_id].close()
            except:
                pass

        self.active_connections[project_id][user_id] = websocket

    def disconnect(self, project_id: str, user_id: int):
        if project_id in self.active_connections:
            if user_id in self.active_connections[project_id]:
                del self.active_connections[project_id][user_id]
            if not self.active_connections[project_id]:
                del self.active_connections[project_id]

    async def broadcast(self, message: dict, project_id: str, exclude_user: int = None):
        """방에 있는 모든 사람에게 메시지 전송 (나 제외)"""
        if project_id in self.active_connections:
            # 딕셔너리 변경 에러 방지를 위해 리스트로 복사 후 순회
            for uid, connection in list(self.active_connections[project_id].items()):
                if uid != exclude_user:
                    try:
                        await connection.send_text(json.dumps(message))
                    except Exception:
                        # 연결이 끊긴 소켓 정리
                        self.disconnect(project_id, uid)

    async def send_personal_message(self, message: dict, project_id: str, to_user: int):
        """특정 사용자에게만 귓속말 전송 (1:1 시그널링)"""
        if project_id in self.active_connections:
            if to_user in self.active_connections[project_id]:
                try:
                    target_ws = self.active_connections[project_id][to_user]
                    await target_ws.send_text(json.dumps(message))
                except Exception:
                    self.disconnect(project_id, to_user)

manager = ConnectionManager()

@router.websocket("/ws/projects/{project_id}/voice")
async def voice_chat_endpoint(websocket: WebSocket, project_id: str):
    # 1. 쿼리 파라미터나 헤더 등에서 user_id를 가져오는 로직이 필요하지만,
    #    현재 구조상 클라이언트가 첫 메시지로 join을 보낸다고 가정하고 임시 처리
    #    (실제로는 토큰에서 user_id를 꺼내는 것이 안전함)

    current_user_id = None

    try:
        # 일단 연결 수락 (나중에 user_id 받으면 등록)
        await websocket.accept()

        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            msg_type = message.get("type")

            # [1] 입장 처리 (Join)
            if msg_type == "join":
                current_user_id = message.get("senderId") or message.get("userId")
                if current_user_id is None:
                    continue

                # 매니저에 정식 등록
                # (connect 메서드를 직접 호출하지 않고 여기서 수동 처리)
                if project_id not in manager.active_connections:
                    manager.active_connections[project_id] = {}
                manager.active_connections[project_id][current_user_id] = websocket

                # 기존 멤버들에게 "나 왔어!" 알림 (Broadcast)
                await manager.broadcast(
                    {"type": "user_joined", "userId": current_user_id},
                    project_id,
                    exclude_user=current_user_id
                )

                # 나에게 "현재 방에 있는 사람들" 목록 보내주기 (Mesh 연결 시작용)
                existing_users = [
                    uid for uid in manager.active_connections[project_id].keys()
                    if uid != current_user_id
                ]
                await websocket.send_text(json.dumps({
                    "type": "existing_users",
                    "users": existing_users
                }))

            # [2] 시그널링 메시지 (Offer, Answer, ICE) -> 귓속말 처리!
            elif msg_type in ["offer", "answer", "ice", "candidate"]:
                to_user = message.get("to") # 클라이언트가 반드시 'to'를 보내줘야 함
                if to_user is not None:
                    # 특정인에게만 전송
                    await manager.send_personal_message(message, project_id, to_user)
                else:
                    # to가 없으면 예전처럼 방송 (하위 호환)
                    await manager.broadcast(message, project_id, exclude_user=current_user_id)

            # [3] 기타 메시지
            else:
                await manager.broadcast(message, project_id, exclude_user=current_user_id)

    except WebSocketDisconnect:
        if current_user_id is not None:
            manager.disconnect(project_id, current_user_id)
            # 퇴장 알림
            await manager.broadcast(
                {"type": "user_left", "userId": current_user_id},
                project_id
            )