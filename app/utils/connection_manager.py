from typing import List, Dict, Optional
from fastapi import WebSocket
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    일반 WebSocket 연결 관리자
    프로젝트별 연결 관리
    """
    def __init__(self):
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
        if project_id in self.active_connections:
            for connection in self.active_connections[project_id]:
                if connection != sender_socket:
                    await connection.send_json(message)


class VoiceConnectionManager:
    """
    음성 채팅 전용 WebSocket 연결 관리자
    - 프로젝트별 연결 관리
    - 소켓-유저ID 매핑 관리
    - 디버깅 로그 포함
    """
    def __init__(self):
        # { project_id: [socket1, socket2, ...] }
        self.active_connections: Dict[int, List[WebSocket]] = {}
        # { project_id: { socket: user_id } }
        self.socket_user_map: Dict[int, Dict[WebSocket, int]] = {}

    async def connect(self, websocket: WebSocket, project_id: int):
        """새 WebSocket 연결 수락"""
        await websocket.accept()
        
        if project_id not in self.active_connections:
            self.active_connections[project_id] = []
            self.socket_user_map[project_id] = {}
            
        self.active_connections[project_id].append(websocket)
        logger.debug(f"[VoiceManager] Connected. Project {project_id} now has {len(self.active_connections[project_id])} connections")

    def register_user(self, websocket: WebSocket, project_id: int, user_id: int):
        """소켓에 userId 등록 (join 메시지 수신 시 호출)"""
        if project_id in self.socket_user_map:
            self.socket_user_map[project_id][websocket] = user_id
            logger.debug(f"[VoiceManager] Registered user {user_id} for socket in project {project_id}")

    def get_user_id(self, websocket: WebSocket, project_id: int) -> Optional[int]:
        """소켓의 userId 조회"""
        if project_id in self.socket_user_map:
            return self.socket_user_map[project_id].get(websocket)
        return None

    def disconnect(self, websocket: WebSocket, project_id: int):
        """WebSocket 연결 해제"""
        if project_id in self.active_connections:
            if websocket in self.active_connections[project_id]:
                self.active_connections[project_id].remove(websocket)
                
            # 소켓-유저 매핑에서도 제거
            if project_id in self.socket_user_map and websocket in self.socket_user_map[project_id]:
                del self.socket_user_map[project_id][websocket]
                
            # 빈 프로젝트 정리
            if not self.active_connections[project_id]:
                del self.active_connections[project_id]
                if project_id in self.socket_user_map:
                    del self.socket_user_map[project_id]
                    
        logger.debug(f"[VoiceManager] Disconnected from project {project_id}")

    def get_peer_count(self, project_id: int, exclude_socket: WebSocket = None) -> int:
        """프로젝트의 다른 참여자 수 반환"""
        if project_id not in self.active_connections:
            return 0
        
        count = len(self.active_connections[project_id])
        if exclude_socket and exclude_socket in self.active_connections[project_id]:
            count -= 1
        return count

    def get_other_user_sockets(self, project_id: int, exclude_socket: WebSocket) -> List[WebSocket]:
        """특정 소켓을 제외한 다른 연결 목록 반환"""
        if project_id not in self.active_connections:
            return []
        return [s for s in self.active_connections[project_id] if s != exclude_socket]

    async def broadcast(self, message: dict, project_id: int, sender_socket: WebSocket):
        """
        발신자를 제외한 같은 방의 모든 연결에 메시지 전송
        """
        if project_id not in self.active_connections:
            logger.warning(f"[VoiceManager] No connections for project {project_id}")
            return
            
        recipients = 0
        failed = 0
        
        for connection in self.active_connections[project_id]:
            if connection != sender_socket:
                try:
                    await connection.send_json(message)
                    recipients += 1
                except Exception as e:
                    logger.error(f"[VoiceManager] Failed to send to connection: {e}")
                    failed += 1
                    
        logger.debug(f"[VoiceManager] Broadcast complete: {recipients} success, {failed} failed")

    async def broadcast_all(self, message: dict, project_id: int):
        """
        같은 방의 모든 연결에 메시지 전송 (발신자 포함)
        주로 user_left 알림에 사용
        """
        if project_id not in self.active_connections:
            return
            
        for connection in self.active_connections[project_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"[VoiceManager] Failed to send to connection: {e}")

    async def send_to_user(self, message: dict, project_id: int, target_user_id: int):
        """
        특정 userId를 가진 소켓에만 메시지 전송
        """
        if project_id not in self.socket_user_map:
            return False
            
        for socket, user_id in self.socket_user_map[project_id].items():
            if user_id == target_user_id:
                try:
                    await socket.send_json(message)
                    return True
                except Exception as e:
                    logger.error(f"[VoiceManager] Failed to send to user {target_user_id}: {e}")
                    return False
        return False


class BoardEventManager:
    def __init__(self):
        # { project_id: [WebSocket, ...] }
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

    async def broadcast(self, project_id: int, message: dict):
        """해당 프로젝트에 접속한 모든 유저에게 이벤트 전송"""
        if project_id in self.active_connections:
            for connection in self.active_connections[project_id]:
                await connection.send_json(message)


class WorkspaceEventManager:
    """
    워크스페이스 레벨 WebSocket 연결 관리자
    - 워크스페이스별 연결 관리
    - 소켓-유저ID 매핑 (self-echo 방지용)
    - 이벤트: MEMBER_JOINED, MEMBER_LEFT, WORKSPACE_UPDATED, PROJECT_CREATED, PROJECT_DELETED
    """
    def __init__(self):
        # { workspace_id: [WebSocket, ...] }
        self.active_connections: Dict[int, List[WebSocket]] = {}
        # { workspace_id: { socket: user_id } }
        self.socket_user_map: Dict[int, Dict[WebSocket, int]] = {}

    async def connect(self, websocket: WebSocket, workspace_id: int, user_id: int):
        await websocket.accept()
        if workspace_id not in self.active_connections:
            self.active_connections[workspace_id] = []
            self.socket_user_map[workspace_id] = {}
        self.active_connections[workspace_id].append(websocket)
        self.socket_user_map[workspace_id][websocket] = user_id
        logger.debug(f"[WorkspaceManager] User {user_id} connected to workspace {workspace_id}. Total: {len(self.active_connections[workspace_id])}")

    def disconnect(self, websocket: WebSocket, workspace_id: int):
        if workspace_id in self.active_connections:
            if websocket in self.active_connections[workspace_id]:
                self.active_connections[workspace_id].remove(websocket)
            if workspace_id in self.socket_user_map and websocket in self.socket_user_map[workspace_id]:
                del self.socket_user_map[workspace_id][websocket]
            if not self.active_connections[workspace_id]:
                del self.active_connections[workspace_id]
                if workspace_id in self.socket_user_map:
                    del self.socket_user_map[workspace_id]
        logger.debug(f"[WorkspaceManager] Disconnected from workspace {workspace_id}")

    async def broadcast(self, workspace_id: int, message: dict):
        """해당 워크스페이스에 접속한 모든 유저에게 이벤트 전송"""
        if workspace_id not in self.active_connections:
            return
        dead_connections = []
        for connection in self.active_connections[workspace_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"[WorkspaceManager] Failed to send: {e}")
                dead_connections.append(connection)
        for dc in dead_connections:
            self.disconnect(dc, workspace_id)


class CommunityEventManager:
    """
    글로벌 커뮤니티 WebSocket 연결 관리자
    - 프로젝트/워크스페이스 구분 없이 전체 연결 관리
    - 이벤트: POST_CREATED, POST_DELETED, POST_UPDATED
    """
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.debug(f"[CommunityManager] Connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.debug(f"[CommunityManager] Disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """모든 연결된 클라이언트에게 이벤트 전송"""
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"[CommunityManager] Failed to send: {e}")
                dead_connections.append(connection)
        for dc in dead_connections:
            self.disconnect(dc)


# 싱글톤 인스턴스
manager = ConnectionManager()
voice_manager = VoiceConnectionManager()
board_event_manager = BoardEventManager()
chat_manager = ConnectionManager()
workspace_event_manager = WorkspaceEventManager()
community_event_manager = CommunityEventManager()
