from typing import List, Dict
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # 프로젝트 ID별로 연결된 소켓 리스트 저장 { project_id: [socket1, socket2] }
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, project_id: int):
        await websocket.accept()
        if project_id not in self.active_connections:
            self.active_connections[project_id] = []
        self.active_connections[project_id].append(websocket)

    def disconnect(self, websocket: WebSocket, project_id: int):
        if project_id in self.active_connections:
            if websocket in self.active_connections[project_id]:
                self.active_connections[project_id].remove(websocket)
                if not self.active_connections[project_id]:
                    del self.active_connections[project_id]

    async def broadcast(self, message: dict, project_id: int, sender_socket: WebSocket):
        # 나를 제외한 같은 방 사람들에게 메시지 전송
        if project_id in self.active_connections:
            for connection in self.active_connections[project_id]:
                if connection != sender_socket:
                    await connection.send_json(message)


manager = ConnectionManager()
