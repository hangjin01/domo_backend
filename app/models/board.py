# [파일 안내] backend/app/models/board.py
# 카드/그룹 및 담당자·파일·연결선·댓글 관계를 DB에 표현하는 SQLModel 테이블 정의입니다.
# Field는 실제 컬럼의 기본값/PK/FK/인덱스, Relationship은 ORM에서 객체를 탐색하는 관계입니다. Relationship 자체가 추가 DB 컬럼은 아닙니다.
# Optional[int] 기본 None인 PK는 저장 전 아직 번호가 없는 객체를 표현합니다. 실제 제약은 Field 선언을 확인해야 합니다.
# 관계의 cascade와 FK의 ondelete는 적용 계층이 다릅니다. 필드 변경 후 create_all만으로 기존 DB가 마이그레이션되지는 않습니다.

from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship
from app.models.user import User
from sqlalchemy import ForeignKey # 순환 참조용


# CardFileLink: card_files 테이블의 행과 관계를 표현합니다.
class CardFileLink(SQLModel, table=True):
    __tablename__ = "card_files"
    # DB 참조 대상: 'cards.id'. 연결된 행의 식별자를 저장합니다.
    card_id: int = Field(foreign_key="cards.id", primary_key=True)
    # DB 참조 대상: 'files.id'. 연결된 행의 식별자를 저장합니다.
    file_id: int = Field(foreign_key="files.id", primary_key=True)


# CardAssignee: card_assignees 테이블의 행과 관계를 표현합니다.
class CardAssignee(SQLModel, table=True):
    __tablename__ = "card_assignees"
    # DB 참조 대상: 'cards.id'. 연결된 행의 식별자를 저장합니다.
    card_id: int = Field(foreign_key="cards.id", primary_key=True)
    # DB 참조 대상: 'users.id'. 연결된 행의 식별자를 저장합니다.
    user_id: int = Field(foreign_key="users.id", primary_key=True)


# CardDependency: card_dependencies 테이블의 행과 관계를 표현합니다.
class CardDependency(SQLModel, table=True):
    __tablename__ = "card_dependencies"

    # 고유 ID 추가
    id: Optional[int] = Field(default=None, primary_key=True)

    # 연결 정보
    # DB 참조 대상: 'cards.id'. 연결된 행의 식별자를 저장합니다.
    from_card_id: int = Field(foreign_key="cards.id", ondelete="CASCADE")
    # DB 참조 대상: 'cards.id'. 연결된 행의 식별자를 저장합니다.
    to_card_id: int = Field(foreign_key="cards.id", ondelete="CASCADE")

    # 스타일 정보 (기본값 설정)
    style: str = Field(default="solid")   # solid, dashed, dotted
    shape: str = Field(default="bezier")  # bezier, straight, step

    source_handle: Optional[str] = Field(default=None)
    target_handle: Optional[str] = Field(default=None)


# 1. 보드 컬럼 (예: 할 일, 진행 중, 완료)
# BoardColumn: board_columns 테이블의 행과 관계를 표현합니다.
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
    # DB 참조 대상: 'board_columns.id'. 연결된 행의 식별자를 저장합니다.
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
    # DB 참조 대상: 'projects.id'. 연결된 행의 식별자를 저장합니다.
    project_id: int = Field(foreign_key="projects.id", index=True)
    created_at: datetime = Field(default_factory=datetime.now)

    # 관계 설정
    # ORM 역방향 속성 'columns'와 짝을 이루는 객체 관계입니다.
    project: Optional["Project"] = Relationship(back_populates="columns")

    # ORM 역방향 속성 'children'와 짝을 이루는 객체 관계입니다.
    parent: Optional["BoardColumn"] = Relationship(
        back_populates="children",
        sa_relationship_kwargs={
            "remote_side": "BoardColumn.id"  # 문자열로 지정하여 순환 참조 해결
        }
    )
    # ORM 역방향 속성 'parent'와 짝을 이루는 객체 관계입니다.
    children: List["BoardColumn"] = Relationship(back_populates="parent")

    # ORM 역방향 속성 'column'와 짝을 이루는 객체 관계입니다.
    cards: List["Card"] = Relationship(back_populates="column", sa_relationship_kwargs={"cascade": "all, delete"})


# Card: cards 테이블의 행과 관계를 표현합니다.
class Card(SQLModel, table=True):
    __tablename__ = "cards"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    content: Optional[str] = None
    order: int = Field(default=0)

    # 🚨 [핵심 변경] column_id를 Optional(선택)로 변경
    # DB 참조 대상: 'board_columns.id'. 연결된 행의 식별자를 저장합니다.
    column_id: Optional[int] = Field(default=None, foreign_key="board_columns.id", index=True)

    # ✅ [신규] 카드가 프로젝트에 직접 소속됨
    # DB 참조 대상: 'projects.id'. 연결된 행의 식별자를 저장합니다.
    project_id: int = Field(foreign_key="projects.id", index=True)

    # ... (assignees, files, x, y 등 기존 필드 유지) ...
    assignees: List[User] = Relationship(link_model=CardAssignee)
    # ORM 역방향 속성 'cards'와 짝을 이루는 객체 관계입니다.
    files: List["FileMetadata"] = Relationship(link_model=CardFileLink, back_populates="cards")
    card_type: str = Field(default="task")
    x: float = Field(default=0.0)
    y: float = Field(default=0.0)
    start_date: Optional[datetime] = Field(default=None)
    due_date: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # 관계 설정
    # ORM 역방향 속성 'cards'와 짝을 이루는 객체 관계입니다.
    column: Optional["BoardColumn"] = Relationship(back_populates="cards")
    # ORM 역방향 속성 'cards'와 짝을 이루는 객체 관계입니다.
    project: "Project" = Relationship(back_populates="cards") # 👈 프로젝트와 연결
    # ORM 역방향 속성 'card'와 짝을 이루는 객체 관계입니다.
    comments: List["CardComment"] = Relationship(back_populates="card", sa_relationship_kwargs={"cascade": "all, delete"})


# CardComment: card_comments 테이블의 행과 관계를 표현합니다.
class CardComment(SQLModel, table=True):
    __tablename__ = "card_comments"

    id: Optional[int] = Field(default=None, primary_key=True)
    # DB 참조 대상: 'cards.id'. 연결된 행의 식별자를 저장합니다.
    card_id: int = Field(foreign_key="cards.id")
    # DB 참조 대상: 'users.id'. 연결된 행의 식별자를 저장합니다.
    user_id: int = Field(foreign_key="users.id")

    content: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # 관계 설정
    # ORM 역방향 속성 'comments'와 짝을 이루는 객체 관계입니다.
    card: "Card" = Relationship(back_populates="comments")
    user: "User" = Relationship()  # 작성자 정보 접근용
