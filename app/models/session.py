# [파일 안내] backend/app/models/session.py
# 사용자 로그인 세션과 만료 시각를 DB에 표현하는 SQLModel 테이블 정의입니다.
# Field는 실제 컬럼의 기본값/PK/FK/인덱스, Relationship은 ORM에서 객체를 탐색하는 관계입니다. Relationship 자체가 추가 DB 컬럼은 아닙니다.
# Optional[int] 기본 None인 PK는 저장 전 아직 번호가 없는 객체를 표현합니다. 실제 제약은 Field 선언을 확인해야 합니다.
# 관계의 cascade와 FK의 ondelete는 적용 계층이 다릅니다. 필드 변경 후 create_all만으로 기존 DB가 마이그레이션되지는 않습니다.

import uuid
from datetime import datetime
from sqlmodel import SQLModel, Field


# UserSession: user_sessions 테이블의 행과 관계를 표현합니다.
class UserSession(SQLModel, table=True):
    __tablename__ = "user_sessions"

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: int = Field(index=True)

    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: datetime
    ip_address: str | None = None
