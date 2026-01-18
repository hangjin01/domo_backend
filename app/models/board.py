from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship
from app.models.user import User


class CardFileLink(SQLModel, table=True):
    __tablename__ = "card_files"
    card_id: int = Field(foreign_key="cards.id", primary_key=True)
    file_id: int = Field(foreign_key="files.id", primary_key=True)


class CardAssignee(SQLModel, table=True):
    __tablename__ = "card_assignees"
    card_id: int = Field(foreign_key="cards.id", primary_key=True)
    user_id: int = Field(foreign_key="users.id", primary_key=True)


class CardDependency(SQLModel, table=True):
    __tablename__ = "card_dependencies"

    # 선의 시작점 (From)
    from_card_id: int = Field(foreign_key="cards.id", primary_key=True)
    # 선의 도착점 (To)
    to_card_id: int = Field(foreign_key="cards.id", primary_key=True)


# 1. 보드 컬럼 (예: 할 일, 진행 중, 완료)
class BoardColumn(SQLModel, table=True):
    __tablename__ = "board_columns"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    order: int = Field(default=0)  # 컬럼 순서
    project_id: int = Field(foreign_key="projects.id", index=True)
    created_at: datetime = Field(default_factory=datetime.now)


# 2. 카드 (실제 할 일 / 포스트잇)
class Card(SQLModel, table=True):
    __tablename__ = "cards"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    content: Optional[str] = None
    order: int = Field(default=0)  # 컬럼 내에서의 카드 순서

    column_id: int = Field(foreign_key="board_columns.id", index=True)
    assignees: List[User] = Relationship(link_model=CardAssignee)
    files: List["FileMetadata"] = Relationship(link_model=CardFileLink, back_populates="cards")

    x: float = Field(default=0.0)
    y: float = Field(default=0.0)

    start_date: Optional[datetime] = Field(default=None)
    due_date: Optional[datetime] = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
