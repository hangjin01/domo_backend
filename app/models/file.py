# [파일 안내] backend/app/models/file.py
# 논리 파일과 실제 업로드 버전를 DB에 표현하는 SQLModel 테이블 정의입니다.
# Field는 실제 컬럼의 기본값/PK/FK/인덱스, Relationship은 ORM에서 객체를 탐색하는 관계입니다. Relationship 자체가 추가 DB 컬럼은 아닙니다.
# Optional[int] 기본 None인 PK는 저장 전 아직 번호가 없는 객체를 표현합니다. 실제 제약은 Field 선언을 확인해야 합니다.
# 관계의 cascade와 FK의 ondelete는 적용 계층이 다릅니다. 필드 변경 후 create_all만으로 기존 DB가 마이그레이션되지는 않습니다.

from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship
from app.models.board import Card, CardFileLink


# 1. 파일 메타데이터 (프로젝트 내의 '파일' 개념)
# FileMetadata: files 테이블의 행과 관계를 표현합니다.
class FileMetadata(SQLModel, table=True):
    __tablename__ = "files"

    id: Optional[int] = Field(default=None, primary_key=True)
    # DB 참조 대상: 'projects.id'. 연결된 행의 식별자를 저장합니다.
    project_id: int = Field(foreign_key="projects.id", index=True)
    filename: str = Field(index=True)  # 원본 파일명 (예: 기획서.pdf)
    # DB 참조 대상: 'users.id'. 연결된 행의 식별자를 저장합니다.
    owner_id: int = Field(foreign_key="users.id")

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # ORM 역방향 속성 'files'와 짝을 이루는 객체 관계입니다.
    cards: List[Card] = Relationship(link_model=CardFileLink, back_populates="files")

    # ORM 역방향 속성 'file_metadata'와 짝을 이루는 객체 관계입니다.
    versions: List["FileVersion"] = Relationship(back_populates="file_metadata")
    # ORM 역방향 속성 'files'와 짝을 이루는 객체 관계입니다.
    project: Optional["Project"] = Relationship(back_populates="files")

    # ✅ [추가 2] "최신 버전"을 자동으로 계산하는 프로퍼티
    # 스키마(FileResponse)가 'latest_version'이라는 이름을 찾을 때 이 함수가 실행됩니다.
    @property
    def latest_version(self):
        if not self.versions:
            return None
        # 버전 숫자(version)를 기준으로 내림차순 정렬 후 첫 번째 것 반환
        return sorted(self.versions, key=lambda v: v.version, reverse=True)[0]


# 2. 파일 버전 (실제 물리적 파일 정보)
# FileVersion: file_versions 테이블의 행과 관계를 표현합니다.
class FileVersion(SQLModel, table=True):
    __tablename__ = "file_versions"

    id: Optional[int] = Field(default=None, primary_key=True)
    # DB 참조 대상: 'files.id'. 연결된 행의 식별자를 저장합니다.
    file_id: int = Field(foreign_key="files.id", index=True)

    version: int = Field(default=1)  # v1, v2, ...
    saved_path: str  # 서버에 저장된 실제 경로 (UUID 등으로 변환됨)
    file_size: int  # 바이트 단위

    # DB 참조 대상: 'users.id'. 연결된 행의 식별자를 저장합니다.
    uploader_id: int = Field(foreign_key="users.id")  # 버전을 올린 사람
    created_at: datetime = Field(default_factory=datetime.now)

    # ORM 역방향 속성 'versions'와 짝을 이루는 객체 관계입니다.
    file_metadata: Optional[FileMetadata] = Relationship(back_populates="versions")
