from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from app.database import get_db
from app.routers.workspace import get_current_user_id # 기존 인증 함수 재사용
from app.models.board import BoardColumn, Card, CardAssignee
from app.models.workspace import Project, WorkspaceMember
from app.schemas import BoardColumnCreate, BoardColumnResponse, CardCreate, CardResponse, CardUpdate
from app.models.user import User
from datetime import datetime


router = APIRouter(tags=["Board & Cards"])

# 1. 컬럼 생성
@router.post("/projects/{project_id}/columns", response_model=BoardColumnResponse)
def create_column(project_id: int, col_data: BoardColumnCreate, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project: raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")

    # 워크스페이스 멤버 권한 확인 로직 생략(필요 시 추가)

    new_col = BoardColumn(**col_data.model_dump(), project_id=project_id)
    db.add(new_col)
    db.commit()
    db.refresh(new_col)
    return new_col

# 2. 카드 생성
@router.post("/columns/{column_id}/cards", response_model=CardResponse)
def create_card(
        column_id: int,
        card_data: CardCreate,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 컬럼 확인
    column = db.get(BoardColumn, column_id)
    if not column:
        raise HTTPException(status_code=404, detail="컬럼을 찾을 수 없습니다.")

    # 카드 생성
    new_card = Card(
        title=card_data.title,
        content=card_data.content,
        order=card_data.order,
        column_id=column_id,
        x=card_data.x,
        y=card_data.y
    )

    # 담당자 연결 (Many-to-Many)
    if card_data.assignee_ids:
        users = db.exec(select(User).where(User.id.in_(card_data.assignee_ids))).all()
        new_card.assignees = users

    db.add(new_card)
    db.commit()
    db.refresh(new_card)
    return new_card

# 3. 특정 프로젝트의 모든 컬럼 및 카드 조회
@router.get("/projects/{project_id}/board")
def get_board(project_id: int, db: Session = Depends(get_db)):
    columns = db.exec(select(BoardColumn).where(BoardColumn.project_id == project_id).order_by(BoardColumn.order)).all()
    result = []
    for col in columns:
        cards = db.exec(select(Card).where(Card.column_id == col.id).order_by(Card.order)).all()
        result.append({
            "column": col,
            "cards": cards
        })
    return result

@router.patch("/cards/{card_id}", response_model=CardResponse)
def update_card(
        card_id: int,
        card_data: CardUpdate,
        db: Session = Depends(get_db)
):
    card = db.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="카드를 찾을 수 없습니다.")

    # 기본 필드 업데이트
    card_data_dict = card_data.model_dump(exclude_unset=True)

    # assignee_ids는 별도 처리하므로 딕셔너리에서 제외
    if "assignee_ids" in card_data_dict:
        assignee_ids = card_data_dict.pop("assignee_ids")
        # 담당자 목록 교체 (기존 관계 지우고 새로 설정)
        users = db.exec(select(User).where(User.id.in_(assignee_ids))).all()
        card.assignees = users

    for key, value in card_data_dict.items():
        setattr(card, key, value)

    card.updated_at = datetime.now()
    db.add(card)
    db.commit()
    db.refresh(card)
    return card