from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from app.database import get_db
from app.routers.workspace import get_current_user_id  # 기존 인증 함수 재사용
from app.models.board import BoardColumn, Card, CardAssignee
from app.models.workspace import Project, WorkspaceMember
from app.schemas import BoardColumnCreate, BoardColumnResponse, CardCreate, CardResponse, CardUpdate
from datetime import datetime
from app.utils.logger import log_activity
from app.models.user import User
from app.models.workspace import Project
from app.models.file import FileMetadata
from app.models.board import CardFileLink
from app.schemas import FileResponse
from vectorwave import *


router = APIRouter(tags=["Board & Cards"])


# 1. 컬럼 생성
@router.post("/projects/{project_id}/columns", response_model=BoardColumnResponse)
@vectorize(search_description="Create board column", capture_return_value=True, replay=True) # 👈 추가
def create_column(project_id: int, col_data: BoardColumnCreate, user_id: int = Depends(get_current_user_id),
                  db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project: raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")

    # 워크스페이스 멤버 권한 확인 로직 생략(필요 시 추가)

    new_col = BoardColumn(**col_data.model_dump(), project_id=project_id)
    db.add(new_col)
    db.commit()
    db.refresh(new_col)

    user = db.get(User, user_id)
    # Project를 조회해서 workspace_id를 알아냄
    project = db.get(Project, project_id)

    log_activity(
        db=db,
        user_id=user_id,
        workspace_id=project.workspace_id,
        action_type="CREATE",
        content=f"📋 '{user.name}'님이 '{project.name}' 프로젝트에 '{new_col.title}' 컬럼을 생성했습니다."
    )

    return new_col


# 2. 카드 생성
@router.post("/columns/{column_id}/cards", response_model=CardResponse)
@vectorize(search_description="Create card", capture_return_value=True, replay=True) # 👈 추가
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

    user = db.get(User, user_id)
    # Column -> Project -> Workspace 역추적
    column = db.get(BoardColumn, column_id)
    project = db.get(Project, column.project_id)

    log_activity(
        db=db,
        user_id=user_id,
        workspace_id=project.workspace_id,
        action_type="CREATE",
        content=f"📝 '{user.name}'님이 '{project.name}'에 카드 '{new_card.title}'을(를) 생성했습니다."
    )

    return new_card


# 3. 특정 프로젝트의 모든 컬럼 및 카드 조회
@router.get("/projects/{project_id}/board")
@vectorize(search_description="Get project kanban board", capture_return_value=True, replay=True) # 👈 추가
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
@vectorize(search_description="Update card", capture_return_value=True, replay=True) # 👈 추가
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


@router.post("/cards/{card_id}/files/{file_id}", response_model=CardResponse)
@vectorize(search_description="Attach file to card", capture_return_value=True, replay=True) # 👈 추가
def attach_file_to_card(
        card_id: int,
        file_id: int,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 1. 존재 여부 확인
    card = db.get(Card, card_id)
    file = db.get(FileMetadata, file_id)

    if not card or not file:
        raise HTTPException(status_code=404, detail="카드 또는 파일을 찾을 수 없습니다.")

    # 2. 이미 연결되어 있는지 확인
    existing_link = db.get(CardFileLink, (card_id, file_id))
    if existing_link:
        return card  # 이미 있으면 그냥 반환

    # 3. 연결 생성
    link = CardFileLink(card_id=card_id, file_id=file_id)
    db.add(link)
    db.commit()
    db.refresh(card)  # card.files 관계 새로고침

    user = db.get(User, user_id)
    card = db.get(Card, card_id)
    file = db.get(FileMetadata, file_id)
    # 역추적
    column = db.get(BoardColumn, card.column_id)
    project = db.get(Project, column.project_id)

    log_activity(
        db=db,
        user_id=user_id,
        workspace_id=project.workspace_id,
        action_type="ATTACH",
        content=f"📎 '{user.name}'님이 카드 '{card.title}'에 파일 '{file.filename}'을(를) 첨부했습니다."
    )

    return card


# 5. [신규] 카드에서 파일 연결 해제
@router.delete("/cards/{card_id}/files/{file_id}")
@vectorize(search_description="Detach file from card", capture_return_value=True, replay=True) # 👈 추가
def detach_file_from_card(
        card_id: int,
        file_id: int,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    link = db.get(CardFileLink, (card_id, file_id))
    if not link:
        raise HTTPException(status_code=404, detail="해당 파일이 카드에 첨부되어 있지 않습니다.")

    db.delete(link)
    db.commit()

    user = db.get(User, user_id)
    card = db.get(Card, card_id)
    file = db.get(FileMetadata, file_id)
    # 역추적
    column = db.get(BoardColumn, card.column_id)
    project = db.get(Project, column.project_id)

    log_activity(
        db=db,
        user_id=user_id,
        workspace_id=project.workspace_id,
        action_type="DETACH",
        content=f"📎 '{user.name}'님이 카드 '{card.title}'에서 파일 '{file.filename}'을(를) 분리했습니다."
    )

    return {"message": "파일 연결이 해제되었습니다."}


@router.get("/cards/{card_id}", response_model=CardResponse)
@vectorize(search_description="Get card details", capture_return_value=True, replay=True) # 👈 추가
def get_card(
        card_id: int,
        db: Session = Depends(get_db)
):
    card = db.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="카드를 찾을 수 없습니다.")

    return card
