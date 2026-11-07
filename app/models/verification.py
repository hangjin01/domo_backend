# [파일 안내] backend/app/models/verification.py
# 이메일 인증 코드와 만료를 DB에 표현하는 SQLModel 테이블 정의입니다.
# Field는 실제 컬럼의 기본값/PK/FK/인덱스, Relationship은 ORM에서 객체를 탐색하는 관계입니다. Relationship 자체가 추가 DB 컬럼은 아닙니다.
# Optional[int] 기본 None인 PK는 저장 전 아직 번호가 없는 객체를 표현합니다. 실제 제약은 Field 선언을 확인해야 합니다.
# 관계의 cascade와 FK의 ondelete는 적용 계층이 다릅니다. 필드 변경 후 create_all만으로 기존 DB가 마이그레이션되지는 않습니다.

from datetime import datetime
from sqlmodel import SQLModel, Field

# EmailVerification: email_verifications 테이블의 행과 관계를 표현합니다.
class EmailVerification(SQLModel, table=True):
    __tablename__ = "email_verifications"

    email: str = Field(primary_key=True) # 이메일 하나당 하나의 인증코드만 유지
    code: str
    created_at: datetime = Field(default_factory=datetime.now)
