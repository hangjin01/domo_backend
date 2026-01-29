from typing import Optional
from datetime import datetime, timedelta
from sqlmodel import SQLModel, Field
import uuid

class Invitation(SQLModel, table=True):
    __tablename__ = "invitations"

    id: Optional[int] = Field(default=None, primary_key=True)
    token: str = Field(index=True, unique=True)  # 초대 코드 (URL에 들어갈 값)
    workspace_id: int = Field(foreign_key="workspaces.id", ondelete="CASCADE")
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