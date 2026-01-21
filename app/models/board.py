from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship
from app.models.user import User
from sqlalchemy import ForeignKey # 순환 참조용


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

    # 고유 ID 추가
    id: Optional[int] = Field(default=None, primary_key=True)

    # 연결 정보
    from_card_id: int = Field(foreign_key="cards.id")
    to_card_id: int = Field(foreign_key="cards.id")

    # 스타일 정보 (기본값 설정)
    style: str = Field(default="solid")   # solid, dashed, dotted
    shape: str = Field(default="bezier")  # bezier, straight, step


# 1. 보드 컬럼 (예: 할 일, 진행 중, 완료)
class BoardColumn(SQLModel, table=True):
    __tablename__ = "board_columns"

    # ========================================
    # 기본 식별자
    # ========================================
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str

    # ========================================
    # 상대 좌표 시스템 & 크기
    # ========================================
    local_x: float = Field(default=0.0)
    local_y: float = Field(default=0.0)
    width: float = Field(default=300.0)  # 기본 너비
    height: float = Field(default=500.0) # 기본 높이

    # ========================================
    # 계층 구조 (중첩 그룹 지원)
    # ========================================
    # 자기 자신을 참조 (Self-Referencing)
    parent_id: Optional[int] = Field(default=None, foreign_key="board_columns.id")
    depth: int = Field(default=0) # 0: 최상위, 1: 1단계...

    # ========================================
    # 변환 (Transform)
    # ========================================
    scale_x: float = Field(default=1.0)
    scale_y: float = Field(default=1.0)
    rotation: float = Field(default=0.0)

    # ========================================
    # UI 표시 속성
    # ========================================
    color: Optional[str] = Field(default="#ffffff") # 기본 흰색
    collapsed: bool = Field(default=False)
    order: int = Field(default=0)

    # ========================================
    # 연결 정보
    # ========================================
    project_id: int = Field(foreign_key="projects.id", index=True)
    created_at: datetime = Field(default_factory=datetime.now)

    # 관계 설정
    project: Optional["Project"] = Relationship(back_populates="columns")

    parent: Optional["BoardColumn"] = Relationship(
        back_populates="children",
        sa_relationship_kwargs={
            "remote_side": "BoardColumn.id"  # 문자열로 지정하여 순환 참조 해결
        }
    )
    children: List["BoardColumn"] = Relationship(back_populates="parent")

    cards: List["Card"] = Relationship(back_populates="column", sa_relationship_kwargs={"cascade": "all, delete"})


class Card(SQLModel, table=True):
    __tablename__ = "cards"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    content: Optional[str] = None
    order: int = Field(default=0)

    # 🚨 [핵심 변경] column_id를 Optional(선택)로 변경
    column_id: Optional[int] = Field(default=None, foreign_key="board_columns.id", index=True)

    # ✅ [신규] 카드가 프로젝트에 직접 소속됨
    project_id: int = Field(foreign_key="projects.id", index=True)

    # ... (assignees, files, x, y 등 기존 필드 유지) ...
    assignees: List[User] = Relationship(link_model=CardAssignee)
    files: List["FileMetadata"] = Relationship(link_model=CardFileLink, back_populates="cards")
    card_type: str = Field(default="task")
    x: float = Field(default=0.0)
    y: float = Field(default=0.0)
    start_date: Optional[datetime] = Field(default=None)
    due_date: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # 관계 설정
    column: Optional["BoardColumn"] = Relationship(back_populates="cards")
    project: "Project" = Relationship(back_populates="cards") # 👈 프로젝트와 연결
    comments: List["CardComment"] = Relationship(back_populates="card", sa_relationship_kwargs={"cascade": "all, delete"})


class CardComment(SQLModel, table=True):
    __tablename__ = "card_comments"

    id: Optional[int] = Field(default=None, primary_key=True)
    card_id: int = Field(foreign_key="cards.id")
    user_id: int = Field(foreign_key="users.id")

    content: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # 관계 설정
    card: "Card" = Relationship(back_populates="comments")
    user: "User" = Relationship()  # 작성자 정보 접근용
