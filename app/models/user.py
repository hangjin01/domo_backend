# [파일 안내] backend/app/models/user.py
# 학교 이메일 계정·인증·프로필를 DB에 표현하는 SQLModel 테이블 정의입니다.
# Field는 실제 컬럼의 기본값/PK/FK/인덱스, Relationship은 ORM에서 객체를 탐색하는 관계입니다. Relationship 자체가 추가 DB 컬럼은 아닙니다.
# Optional[int] 기본 None인 PK는 저장 전 아직 번호가 없는 객체를 표현합니다. 실제 제약은 Field 선언을 확인해야 합니다.
# 관계의 cascade와 FK의 ondelete는 적용 계층이 다릅니다. 필드 변경 후 create_all만으로 기존 DB가 마이그레이션되지는 않습니다.

from typing import Optional,List
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship



# User: users 테이블의 행과 관계를 표현합니다.
class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    name: str
    nickname: Optional[str] = Field(default=None)
    profile_image: Optional[str] = None

    is_student_verified: bool = Field(default=False)

    is_active: bool = Field(default=True) # 탈퇴 시 False로 변경
    deleted_at: Optional[datetime] = Field(default=None) # 언제 탈퇴했는지 기록

    last_active_at: datetime = Field(default_factory=datetime.now)
    created_at: datetime = Field(default_factory=datetime.now)
    # ORM 역방향 속성 'user'와 짝을 이루는 객체 관계입니다.
    workspaces: List["WorkspaceMember"] = Relationship(back_populates="user", sa_relationship_kwargs={"cascade": "all, delete"})
