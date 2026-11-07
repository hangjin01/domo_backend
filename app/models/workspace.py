# [파일 안내] backend/app/models/workspace.py
# 워크스페이스·팀원 역할·프로젝트를 DB에 표현하는 SQLModel 테이블 정의입니다.
# Field는 실제 컬럼의 기본값/PK/FK/인덱스, Relationship은 ORM에서 객체를 탐색하는 관계입니다. Relationship 자체가 추가 DB 컬럼은 아닙니다.
# Optional[int] 기본 None인 PK는 저장 전 아직 번호가 없는 객체를 표현합니다. 실제 제약은 Field 선언을 확인해야 합니다.
# 관계의 cascade와 FK의 ondelete는 적용 계층이 다릅니다. 필드 변경 후 create_all만으로 기존 DB가 마이그레이션되지는 않습니다.

from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship


# 1. 워크스페이스 멤버 (N:M 관계 테이블)
# WorkspaceMember: workspace_members 테이블의 행과 관계를 표현합니다.
class WorkspaceMember(SQLModel, table=True):
    __tablename__ = "workspace_members"

    # DB 참조 대상: 'workspaces.id'. 연결된 행의 식별자를 저장합니다.
    workspace_id: int = Field(primary_key=True, foreign_key="workspaces.id")
    # DB 참조 대상: 'users.id'. 연결된 행의 식별자를 저장합니다.
    user_id: int = Field(primary_key=True, foreign_key="users.id")
    role: str = Field(default="member")  # admin, member 등
    joined_at: datetime = Field(default_factory=datetime.now)

    # 관계 설정
    # ORM 역방향 속성 'members'와 짝을 이루는 객체 관계입니다.
    workspace: "Workspace" = Relationship(back_populates="members")
    # ORM 역방향 속성 'workspaces'와 짝을 이루는 객체 관계입니다.
    user: "User" = Relationship(back_populates="workspaces")


# 2. 워크스페이스 (팀 단위)
# Workspace: workspaces 테이블의 행과 관계를 표현합니다.
class Workspace(SQLModel, table=True):
    __tablename__ = "workspaces"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None
    owner_id: int = Field(index=True)  # 생성자(팀장)
    created_at: datetime = Field(default_factory=datetime.now)

    # ORM 역방향 속성 'workspace'와 짝을 이루는 객체 관계입니다.
    projects: List["Project"] = Relationship(back_populates="workspace",
                                             sa_relationship_kwargs={"cascade": "all, delete"})
    # ORM 역방향 속성 'workspace'와 짝을 이루는 객체 관계입니다.
    members: List["WorkspaceMember"] = Relationship(back_populates="workspace",
                                                    sa_relationship_kwargs={"cascade": "all, delete"})
    # ORM 역방향 속성 'workspace'와 짝을 이루는 객체 관계입니다.
    activity_logs: List["ActivityLog"] = Relationship(back_populates="workspace",
                                                      sa_relationship_kwargs={"cascade": "all, delete"})
    invitations: List["Invitation"] = Relationship(
        sa_relationship_kwargs={"cascade": "all, delete"}
    )


# 3. 프로젝트 (워크스페이스 하위 작업 단위)
# Project: projects 테이블의 행과 관계를 표현합니다.
class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None
    # DB 참조 대상: 'workspaces.id'. 연결된 행의 식별자를 저장합니다.
    workspace_id: int = Field(foreign_key="workspaces.id")
    created_at: datetime = Field(default_factory=datetime.now)

    # 부모 관계
    # ORM 역방향 속성 'projects'와 짝을 이루는 객체 관계입니다.
    workspace: Optional[Workspace] = Relationship(back_populates="projects")

    # 👇 자식 관계들 (삭제 시 같이 삭제되도록 cascade 설정)
    # ORM 역방향 속성 'project'와 짝을 이루는 객체 관계입니다.
    columns: List["BoardColumn"] = Relationship(back_populates="project",
                                                sa_relationship_kwargs={"cascade": "all, delete"})
    # ORM 역방향 속성 'project'와 짝을 이루는 객체 관계입니다.
    posts: List["Post"] = Relationship(back_populates="project", sa_relationship_kwargs={"cascade": "all, delete"})
    # ORM 역방향 속성 'project'와 짝을 이루는 객체 관계입니다.
    chats: List["ChatMessage"] = Relationship(back_populates="project",
                                              sa_relationship_kwargs={"cascade": "all, delete"})
    # ORM 역방향 속성 'project'와 짝을 이루는 객체 관계입니다.
    events: List["ProjectEvent"] = Relationship(back_populates="project",
                                                sa_relationship_kwargs={"cascade": "all, delete"})
    # ORM 역방향 속성 'project'와 짝을 이루는 객체 관계입니다.
    files: List["FileMetadata"] = Relationship(back_populates="project",
                                               sa_relationship_kwargs={"cascade": "all, delete"})
    # ORM 역방향 속성 'project'와 짝을 이루는 객체 관계입니다.
    cards: List["Card"] = Relationship(back_populates="project", sa_relationship_kwargs={"cascade": "all, delete"})
