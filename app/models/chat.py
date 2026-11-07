# [파일 안내] backend/app/models/chat.py
# 프로젝트에 속한 채팅 메시지를 DB에 표현하는 SQLModel 테이블 정의입니다.
# Field는 실제 컬럼의 기본값/PK/FK/인덱스, Relationship은 ORM에서 객체를 탐색하는 관계입니다. Relationship 자체가 추가 DB 컬럼은 아닙니다.
# Optional[int] 기본 None인 PK는 저장 전 아직 번호가 없는 객체를 표현합니다. 실제 제약은 Field 선언을 확인해야 합니다.
# 관계의 cascade와 FK의 ondelete는 적용 계층이 다릅니다. 필드 변경 후 create_all만으로 기존 DB가 마이그레이션되지는 않습니다.

from typing import Optional
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime
from app.models.user import User

# ChatMessage: chat_messages 테이블의 행과 관계를 표현합니다.
class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    # DB 참조 대상: 'projects.id'. 연결된 행의 식별자를 저장합니다.
    project_id: int = Field(foreign_key="projects.id", index=True)
    # DB 참조 대상: 'users.id'. 연결된 행의 식별자를 저장합니다.
    user_id: int = Field(foreign_key="users.id")

    content: str
    created_at: datetime = Field(default_factory=datetime.now)

    user: Optional[User] = Relationship()
    # ORM 역방향 속성 'chats'와 짝을 이루는 객체 관계입니다.
    project: Optional["Project"] = Relationship(back_populates="chats")
