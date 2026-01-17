from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship

# 1. 파일 메타데이터 (프로젝트 내의 '파일' 개념)
class FileMetadata(SQLModel, table=True):
    __tablename__ = "files"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", index=True)
    filename: str = Field(index=True) # 원본 파일명 (예: 기획서.pdf)
    owner_id: int = Field(foreign_key="users.id")

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

# 2. 파일 버전 (실제 물리적 파일 정보)
class FileVersion(SQLModel, table=True):
    __tablename__ = "file_versions"

    id: Optional[int] = Field(default=None, primary_key=True)
    file_id: int = Field(foreign_key="files.id", index=True)

    version: int = Field(default=1) # v1, v2, ...
    saved_path: str # 서버에 저장된 실제 경로 (UUID 등으로 변환됨)
    file_size: int  # 바이트 단위

    uploader_id: int = Field(foreign_key="users.id") # 버전을 올린 사람
    created_at: datetime = Field(default_factory=datetime.now)