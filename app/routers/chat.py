# app/routers/chat.py

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlmodel import Session, select
from typing import List
from datetime import datetime
from app.database import get_db, engine
from app.models.chat import ChatMessage
from app.models.user import User
from app.schemas import ChatMessageResponse
from app.routers.workspace import get_current_user_id
from app.utils.connection_manager import chat_manager
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Project Chat"])


# 1. 채팅 메시지 목록 조회 (입장 시 이전 메시지 로드용)
@router.get("/projects/{project_id}/chat", response_model=List[ChatMessageResponse])
def get_chat_messages(
        project_id: int,
        limit: int = 50,
        after_id: int = 0,
        db: Session = Depends(get_db),
        user_id: int = Depends(get_current_user_id)
):
    query = select(ChatMessage).where(ChatMessage.project_id == project_id)

    if after_id > 0:
        query = query.where(ChatMessage.id > after_id)

    messages = db.exec(query.order_by(ChatMessage.created_at.desc()).limit(limit)).all()

    return list(reversed(messages))


# 2. WebSocket 실시간 채팅
@router.websocket("/ws/projects/{project_id}/chat")
async def chat_websocket(websocket: WebSocket, project_id: int):
    await chat_manager.connect(websocket, project_id)
    logger.info(f"[Chat] WebSocket connected: project {project_id}")

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "MESSAGE_SENT":
                content = data.get("content", "").strip()
                user_id = data.get("user_id")

                if not content or not user_id:
                    continue

                # DB 세션 생성 (WebSocket 내에서는 Depends 사용 불가)
                with Session(engine) as db:
                    user = db.get(User, user_id)
                    if not user:
                        continue

                    new_msg = ChatMessage(
                        project_id=project_id,
                        user_id=user_id,
                        content=content
                    )
                    db.add(new_msg)
                    db.commit()
                    db.refresh(new_msg)

                    # 응답 데이터 구성
                    response = {
                        "type": "MESSAGE_SENT",
                        "data": {
                            "id": new_msg.id,
                            "project_id": new_msg.project_id,
                            "user_id": new_msg.user_id,
                            "content": new_msg.content,
                            "created_at": new_msg.created_at.isoformat(),
                            "user": {
                                "id": user.id,
                                "name": user.name,
                                "nickname": user.nickname,
                                "email": user.email,
                                "profile_image": getattr(user, 'profile_image', None),
                            }
                        }
                    }

                    # 발신자에게도 전송 (ID 확인용)
                    await websocket.send_json(response)
                    # 다른 사용자들에게 브로드캐스트
                    await chat_manager.broadcast(response, project_id, websocket)

            elif msg_type == "PING":
                await websocket.send_json({"type": "PONG"})

    except WebSocketDisconnect:
        chat_manager.disconnect(websocket, project_id)
        logger.info(f"[Chat] WebSocket disconnected: project {project_id}")
    except Exception as e:
        logger.error(f"[Chat] WebSocket error: {e}")
        chat_manager.disconnect(websocket, project_id)
