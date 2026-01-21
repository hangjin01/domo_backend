from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship


# 1. 워크스페이스 멤버 (N:M 관계 테이블)
class WorkspaceMember(SQLModel, table=True):
    __tablename__ = "workspace_members"

    workspace_id: int = Field(primary_key=True, foreign_key="workspaces.id")
    user_id: int = Field(primary_key=True, foreign_key="users.id")
    role: str = Field(default="member")  # admin, member 등
    joined_at: datetime = Field(default_factory=datetime.now)

    # 관계 설정
    workspace: "Workspace" = Relationship(back_populates="members")
    user: "User" = Relationship(back_populates="workspaces")


# 2. 워크스페이스 (팀 단위)
class Workspace(SQLModel, table=True):
    __tablename__ = "workspaces"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None
    owner_id: int = Field(index=True)  # 생성자(팀장)
    created_at: datetime = Field(default_factory=datetime.now)

    projects: List["Project"] = Relationship(back_populates="workspace",
                                             sa_relationship_kwargs={"cascade": "all, delete"})
    members: List["WorkspaceMember"] = Relationship(back_populates="workspace",
                                                    sa_relationship_kwargs={"cascade": "all, delete"})
    activity_logs: List["ActivityLog"] = Relationship(back_populates="workspace",
                                                      sa_relationship_kwargs={"cascade": "all, delete"})


# 3. 프로젝트 (워크스페이스 하위 작업 단위)
class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None
    workspace_id: int = Field(foreign_key="workspaces.id")
    created_at: datetime = Field(default_factory=datetime.now)

    # 부모 관계
    workspace: Optional[Workspace] = Relationship(back_populates="projects")

    # 👇 자식 관계들 (삭제 시 같이 삭제되도록 cascade 설정)
    columns: List["BoardColumn"] = Relationship(back_populates="project",
                                                sa_relationship_kwargs={"cascade": "all, delete"})
    posts: List["Post"] = Relationship(back_populates="project", sa_relationship_kwargs={"cascade": "all, delete"})
    chats: List["ChatMessage"] = Relationship(back_populates="project",
                                              sa_relationship_kwargs={"cascade": "all, delete"})
    events: List["ProjectEvent"] = Relationship(back_populates="project",
                                                sa_relationship_kwargs={"cascade": "all, delete"})
    files: List["FileMetadata"] = Relationship(back_populates="project",
                                               sa_relationship_kwargs={"cascade": "all, delete"})
    cards: List["Card"] = Relationship(back_populates="project", sa_relationship_kwargs={"cascade": "all, delete"})
