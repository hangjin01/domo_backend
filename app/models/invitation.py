# [파일 안내] backend/app/models/invitation.py
# 팀 초대 토큰·유효 기간·참여 역할를 DB에 표현하는 SQLModel 테이블 정의입니다.
# Field는 실제 컬럼의 기본값/PK/FK/인덱스, Relationship은 ORM에서 객체를 탐색하는 관계입니다. Relationship 자체가 추가 DB 컬럼은 아닙니다.
# Optional[int] 기본 None인 PK는 저장 전 아직 번호가 없는 객체를 표현합니다. 실제 제약은 Field 선언을 확인해야 합니다.
# 관계의 cascade와 FK의 ondelete는 적용 계층이 다릅니다. 필드 변경 후 create_all만으로 기존 DB가 마이그레이션되지는 않습니다.

from typing import Optional
from datetime import datetime, timedelta
from sqlmodel import SQLModel, Field
import uuid

# Invitation: invitations 테이블의 행과 관계를 표현합니다.
class Invitation(SQLModel, table=True):
    __tablename__ = "invitations"

    id: Optional[int] = Field(default=None, primary_key=True)
    token: str = Field(index=True, unique=True)  # 초대 코드 (URL에 들어갈 값)
    # DB 참조 대상: 'workspaces.id'. 연결된 행의 식별자를 저장합니다.
    workspace_id: int = Field(foreign_key="workspaces.id", ondelete="CASCADE")
    # DB 참조 대상: 'users.id'. 연결된 행의 식별자를 저장합니다.
    inviter_id: int = Field(foreign_key="users.id") # 초대한 사람

    role: str = Field(default="member") # 초대받은 사람이 가질 권한

    # 특정 이메일 전용 초대일 경우 사용 (없으면 누구나 사용 가능)
    target_email: Optional[str] = None

    expires_at: datetime
    created_at: datetime = Field(default_factory=datetime.now)

    # 이미 사용된 초대인지 체크 (1회용일 경우)
    is_used: bool = Field(default=False)

    @staticmethod
    def generate_token():
        return str(uuid.uuid4()) # 랜덤하고 긴 문자열 생성
