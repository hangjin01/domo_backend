# app/routers/board.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from app.database import get_db
from app.routers.workspace import get_current_user_id
from app.models.board import BoardColumn, Card, CardAssignee
from app.models.workspace import Project, WorkspaceMember
from app.schemas import (
    BoardColumnCreate, BoardColumnResponse, CardCreate, CardResponse, CardUpdate,
    CardCommentCreate, CardCommentResponse, BoardColumnUpdate, FileResponse,
    CardConnectionCreate, CardConnectionResponse, TransformSchema # 👈 CardConnectionCreate 확인
)
from datetime import datetime
from app.utils.logger import log_activity
from app.models.user import User
from app.models.file import FileMetadata
from app.models.board import CardFileLink, CardComment, CardDependency
from vectorwave import *

router = APIRouter(tags=["Board & Cards"])

# =================================================================
# 1. 컬럼(Group) 관련 API
# =================================================================

@router.post("/projects/{project_id}/columns", response_model=BoardColumnResponse)
@vectorize(search_description="Create board column (Group)", capture_return_value=True, replay=True)
def create_column(
        project_id: int,
        col_data: BoardColumnCreate,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    project = db.get(Project, project_id)
    if not project: raise HTTPException(status_code=404, detail="Project not found")

    if col_data.parent_id == 0: col_data.parent_id = None

    new_col = BoardColumn(**col_data.model_dump(by_alias=False), project_id=project_id)
    if new_col.parent_id == 0: new_col.parent_id = None

    db.add(new_col)
    db.commit()
    db.refresh(new_col)

    return BoardColumnResponse(
        id=new_col.id,
        title=new_col.title,
        local_x=new_col.local_x,
        local_y=new_col.local_y,
        width=new_col.width,
        height=new_col.height,
        parent_id=new_col.parent_id,
        depth=new_col.depth,
        color=new_col.color,
        collapsed=new_col.collapsed,
        order=new_col.order,
        project_id=new_col.project_id,
        transform=TransformSchema(
            scaleX=new_col.scale_x,
            scaleY=new_col.scale_y,
            rotation=new_col.rotation
        )
    )

@router.patch("/columns/{column_id}", response_model=BoardColumnResponse)
@vectorize(search_description="Update board column (Group)", capture_return_value=True)
def update_column(
        column_id: int,
        col_data: BoardColumnUpdate,
        db: Session = Depends(get_db)
):
    col = db.get(BoardColumn, column_id)
    if not col: raise HTTPException(status_code=404, detail="Column not found")

    update_dict = col_data.model_dump(exclude_unset=True, by_alias=False, exclude={"transform"})
    for key, value in update_dict.items():
        setattr(col, key, value)

    if col_data.transform:
        if col_data.transform.scaleX is not None: col.scale_x = col_data.transform.scaleX
        if col_data.transform.scaleY is not None: col.scale_y = col_data.transform.scaleY
        if col_data.transform.rotation is not None: col.rotation = col_data.transform.rotation

    if col.parent_id == 0: col.parent_id = None

    db.add(col)
    db.commit()
    db.refresh(col)

    return BoardColumnResponse(
        id=col.id,
        title=col.title,
        local_x=col.local_x,
        local_y=col.local_y,
        width=col.width,
        height=col.height,
        parent_id=col.parent_id,
        depth=col.depth,
        color=col.color,
        collapsed=col.collapsed,
        order=col.order,
        project_id=col.project_id,
        transform=TransformSchema(
            scaleX=col.scale_x,
            scaleY=col.scale_y,
            rotation=col.rotation
        )
    )

@router.delete("/columns/{column_id}")
@vectorize(search_description="Delete board column (Preserve cards)", capture_return_value=True)
def delete_column(
        column_id: int,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    column = db.get(BoardColumn, column_id)
    if not column: raise HTTPException(status_code=404, detail="Column not found")

    project = db.get(Project, column.project_id)
    col_title = column.title
    card_count = len(column.cards)

    # 카드 대피 (column_id = None)
    for card in column.cards:
        card.column_id = None
        db.add(card)
    db.commit() # 대피 내용 저장

    # 컬럼 삭제
    db.refresh(column)
    db.delete(column)
    db.commit()

    if project:
        user = db.get(User, user_id)
        log_activity(
            db=db, user_id=user_id, workspace_id=project.workspace_id, action_type="DELETE",
            content=f"🗑️ '{user.name}'님이 그룹 '{col_title}'을(를) 삭제했습니다. (카드 {card_count}개는 보관됨)"
        )

    return {"message": "그룹이 삭제되었으며, 포함된 카드들은 보관함으로 이동되었습니다."}


@router.get("/projects/{project_id}/columns", response_model=List[BoardColumnResponse])
def get_project_columns(project_id: int, db: Session = Depends(get_db)):
    columns = db.exec(select(BoardColumn).where(BoardColumn.project_id == project_id).order_by(BoardColumn.order)).all()
    return columns


# =================================================================
# 2. 카드 연결(Connections) API
# 🚨 [중요] /cards/{card_id} 보다 상위에 위치해야 함 (라우팅 순서 문제 해결)
# =================================================================

@router.get("/projects/{project_id}/connections", response_model=List[CardConnectionResponse])
@vectorize(search_description="Get project card connections", capture_return_value=True)
def get_project_connections(project_id: int, db: Session = Depends(get_db)):
    statement = (
        select(CardDependency)
        .join(Card, CardDependency.from_card_id == Card.id)
        .where(Card.project_id == project_id) # ✅ 컬럼 조인 없이 카드에서 바로 프로젝트 확인
    )
    connections = db.exec(statement).all()

    results = []
    for conn in connections:
        results.append(CardConnectionResponse(
            id=conn.id,
            from_card_id=conn.from_card_id,
            to_card_id=conn.to_card_id,
            board_id=project_id,
            style=conn.style if hasattr(conn, 'style') else "solid",
            shape=conn.shape if hasattr(conn, 'shape') else "bezier"
        ))
    return results

@router.post("/cards/connections", response_model=CardConnectionResponse) # 👈 반환 모델 변경
@vectorize(search_description="Create dependency between cards", capture_return_value=True)
def create_card_connection(
        connection_data: CardConnectionCreate,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    from_card = db.get(Card, connection_data.from_card_id)
    to_card = db.get(Card, connection_data.to_card_id)

    if not from_card or not to_card:
        raise HTTPException(status_code=404, detail="카드를 찾을 수 없습니다.")

    # 컬럼 거치지 않고 카드.project_id 직접 비교 (백로그 카드 지원)
    if from_card.project_id != to_card.project_id:
        raise HTTPException(status_code=400, detail="다른 프로젝트의 카드끼리는 연결할 수 없습니다.")

    # 연결 생성
    new_dependency = CardDependency(
        from_card_id=from_card.id,
        to_card_id=to_card.id,
        dependency_type="finish_to_start", # 기본값
        style="solid",   # 기본값 (필요시 connection_data에서 받아오도록 수정 가능)
        shape="bezier"   # 기본값
    )

    # 만약 프론트에서 style/shape를 보내준다면 여기서 덮어쓰기
    if hasattr(connection_data, "style") and connection_data.style:
        new_dependency.style = connection_data.style
    if hasattr(connection_data, "shape") and connection_data.shape:
        new_dependency.shape = connection_data.shape

    db.add(new_dependency)
    db.commit()
    db.refresh(new_dependency)

    # 로그 기록
    project = db.get(Project, from_card.project_id)
    user = db.get(User, user_id)

    log_activity(
        db=db, user_id=user_id, workspace_id=project.workspace_id, action_type="UPDATE",
        content=f"🔗 '{user.name}'님이 카드 '{from_card.title}'와(과) '{to_card.title}'을(를) 연결했습니다."
    )

    # ✅ [수정] 프론트엔드가 원하는 객체 반환
    return CardConnectionResponse(
        id=new_dependency.id,
        from_card_id=new_dependency.from_card_id,
        to_card_id=new_dependency.to_card_id,
        board_id=from_card.project_id,
        style=new_dependency.style,
        shape=new_dependency.shape
    )

@router.delete("/cards/connections/{connection_id}")
@vectorize(search_description="Delete card connection", capture_return_value=True)
def delete_card_connection(
        connection_id: int, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)
):
    connection = db.get(CardDependency, connection_id)
    if not connection: raise HTTPException(status_code=404, detail="Connection not found")
    db.delete(connection)
    db.commit()
    return {"message": "연결이 삭제되었습니다."}


# 🚨 [중요] /cards/comments/... 도 /cards/{card_id}보다 위에 있어야 안전함
@router.delete("/cards/comments/{comment_id}")
def delete_comment(
        comment_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    comment = db.get(CardComment, comment_id)
    if not comment: raise HTTPException(status_code=404, detail="Comment not found")
    if comment.user_id != user_id: raise HTTPException(status_code=403, detail="작성자만 삭제할 수 있습니다.")

    db.delete(comment)
    db.commit()
    return {"message": "댓글이 삭제되었습니다."}


# =================================================================
# 3. 카드(Card) API
# =================================================================

@router.post("/projects/{project_id}/cards", response_model=CardResponse)
@vectorize(search_description="Create card in project", capture_return_value=True, replay=True)
def create_card(
        project_id: int,
        card_data: CardCreate,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    project = db.get(Project, project_id)
    if not project: raise HTTPException(status_code=404, detail="Project not found")

    final_column_id = card_data.column_id if card_data.column_id else None

    if final_column_id:
        column = db.get(BoardColumn, final_column_id)
        if not column: raise HTTPException(status_code=404, detail="지정된 컬럼을 찾을 수 없습니다.")
        if column.project_id != project_id: raise HTTPException(status_code=400, detail="해당 컬럼은 이 프로젝트에 속하지 않습니다.")

    new_card = Card(
        title=card_data.title,
        content=card_data.content,
        project_id=project_id,
        column_id=final_column_id,
        order=card_data.order,
        x=card_data.x, y=card_data.y,
        card_type=card_data.card_type,
        start_date=card_data.start_date, due_date=card_data.due_date
    )

    if card_data.assignee_ids:
        users = db.exec(select(User).where(User.id.in_(card_data.assignee_ids))).all()
        new_card.assignees = users

    db.add(new_card)
    db.commit()
    db.refresh(new_card)

    user = db.get(User, user_id)
    location = f"'{project.name}' 프로젝트"
    if final_column_id:
        col = db.get(BoardColumn, final_column_id)
        if col: location += f"의 '{col.title}' 컬럼"

    log_activity(
        db=db, user_id=user_id, workspace_id=project.workspace_id, action_type="CREATE",
        content=f"📝 '{user.name}'님이 {location}에 카드 '{new_card.title}'을(를) 생성했습니다."
    )
    return new_card

@router.get("/projects/{project_id}/board")
@vectorize(search_description="Get project kanban board", capture_return_value=True, replay=True)
def get_board(project_id: int, db: Session = Depends(get_db)):
    columns = db.exec(select(BoardColumn).where(BoardColumn.project_id == project_id).order_by(BoardColumn.order)).all()
    result = []
    for col in columns:
        cards = db.exec(select(Card).where(Card.column_id == col.id).order_by(Card.order)).all()
        result.append({"column": col, "cards": cards})
    return result

@router.get("/projects/{project_id}/cards", response_model=List[CardResponse])
@vectorize(search_description="Get all cards in project", capture_return_value=True, replay=True)
def get_project_cards(project_id: int, db: Session = Depends(get_db)):
    cards = db.exec(select(Card).where(Card.project_id == project_id).order_by(Card.id)).all()
    return cards

# -----------------------------------------------------------------
# 여기서부터 /cards/{card_id} 패턴 사용 (connections보다 아래에 있어야 함!)
# -----------------------------------------------------------------

@router.patch("/cards/{card_id}", response_model=CardResponse)
@vectorize(search_description="Update card", capture_return_value=True, replay=True)
def update_card(card_id: int, card_data: CardUpdate, db: Session = Depends(get_db)):
    card = db.get(Card, card_id)
    if not card: raise HTTPException(status_code=404, detail="카드를 찾을 수 없습니다.")

    card_data_dict = card_data.model_dump(exclude_unset=True)
    if "assignee_ids" in card_data_dict:
        assignee_ids = card_data_dict.pop("assignee_ids")
        users = db.exec(select(User).where(User.id.in_(assignee_ids))).all()
        card.assignees = users

    for key, value in card_data_dict.items():
        setattr(card, key, value)

    card.updated_at = datetime.now()
    db.add(card)
    db.commit()
    db.refresh(card)
    return card

@router.delete("/cards/{card_id}")
@vectorize(search_description="Delete card", capture_return_value=True)
def delete_card(card_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    card = db.get(Card, card_id)
    if not card: raise HTTPException(status_code=404, detail="카드를 찾을 수 없습니다.")

    column = db.get(BoardColumn, card.column_id) if card.column_id else None
    project = db.get(Project, card.project_id) if card.project_id else (db.get(Project, column.project_id) if column else None)

    db.delete(card)
    db.commit()

    if project:
        user = db.get(User, user_id)
        log_activity(
            db=db, user_id=user_id, workspace_id=project.workspace_id, action_type="DELETE",
            content=f"🗑️ '{user.name}'님이 카드 '{card.title}'을(를) 삭제했습니다."
        )
    return {"message": "카드가 삭제되었습니다."}

@router.post("/cards/{card_id}/files/{file_id}", response_model=CardResponse)
@vectorize(search_description="Attach file to card", capture_return_value=True, replay=True)
def attach_file_to_card(card_id: int, file_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    card = db.get(Card, card_id)
    file = db.get(FileMetadata, file_id)
    if not card or not file: raise HTTPException(status_code=404, detail="카드 또는 파일을 찾을 수 없습니다.")

    existing_link = db.get(CardFileLink, (card_id, file_id))
    if existing_link: return card

    link = CardFileLink(card_id=card_id, file_id=file_id)
    db.add(link)
    db.commit()
    db.refresh(card)

    user = db.get(User, user_id)
    project = db.get(Project, card.project_id)
    log_activity(
        db=db, user_id=user_id, workspace_id=project.workspace_id, action_type="ATTACH",
        content=f"📎 '{user.name}'님이 카드 '{card.title}'에 파일 '{file.filename}'을(를) 첨부했습니다."
    )
    return card

@router.delete("/cards/{card_id}/files/{file_id}")
@vectorize(search_description="Detach file from card", capture_return_value=True, replay=True)
def detach_file_from_card(card_id: int, file_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    link = db.get(CardFileLink, (card_id, file_id))
    if not link: raise HTTPException(status_code=404, detail="해당 파일이 카드에 첨부되어 있지 않습니다.")

    db.delete(link)
    db.commit()

    user = db.get(User, user_id)
    card = db.get(Card, card_id)
    file = db.get(FileMetadata, file_id)
    project = db.get(Project, card.project_id)

    log_activity(
        db=db, user_id=user_id, workspace_id=project.workspace_id, action_type="DETACH",
        content=f"📎 '{user.name}'님이 카드 '{card.title}'에서 파일 '{file.filename}'을(를) 분리했습니다."
    )
    return {"message": "파일 연결이 해제되었습니다."}

@router.get("/cards/{card_id}", response_model=CardResponse)
@vectorize(search_description="Get card details", capture_return_value=True, replay=True)
def get_card(card_id: int, db: Session = Depends(get_db)):
    card = db.get(Card, card_id)
    if not card: raise HTTPException(status_code=404, detail="카드를 찾을 수 없습니다.")
    return card

@router.post("/cards/{card_id}/comments", response_model=CardCommentResponse)
@vectorize(search_description="Add comment to card", capture_return_value=True)
def create_comment(card_id: int, comment_data: CardCommentCreate, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    card = db.get(Card, card_id)
    if not card: raise HTTPException(status_code=404, detail="Card not found")

    new_comment = CardComment(card_id=card_id, user_id=user_id, content=comment_data.content)
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)
    return new_comment

@router.get("/cards/{card_id}/comments", response_model=List[CardCommentResponse])
def get_card_comments(card_id: int, db: Session = Depends(get_db)):
    comments = db.exec(select(CardComment).where(CardComment.card_id == card_id).order_by(CardComment.created_at.asc())).all()
    return comments