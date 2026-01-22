from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from app.database import get_db
from app.routers.workspace import get_current_user_id  # 기존 인증 함수 재사용
from app.models.board import BoardColumn, Card, CardAssignee
from app.models.workspace import Project, WorkspaceMember
from app.schemas import BoardColumnCreate, BoardColumnResponse, CardCreate, CardResponse, CardUpdate, CardCommentCreate, \
    CardCommentResponse, BoardColumnUpdate
from datetime import datetime
from app.utils.logger import log_activity
from app.models.user import User
from app.models.workspace import Project
from app.models.file import FileMetadata
from app.models.board import CardFileLink, CardComment, CardDependency
from app.schemas import FileResponse
from vectorwave import *
from app.schemas import CardConnectionCreate, CardConnectionResponse, TransformSchema

router = APIRouter(tags=["Board & Cards"])


# 1. 컬럼 생성
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

    if col_data.parent_id == 0:
        col_data.parent_id = None

    # DB 모델 생성 (col_data의 alias들이 자동으로 매핑됨)
    # by_alias=False로 해야 파이썬 변수명(local_x)으로 덤프됨
    new_col = BoardColumn(
        **col_data.model_dump(by_alias=False),
        project_id=project_id
    )

    if new_col.parent_id == 0:
        new_col.parent_id = None

    db.add(new_col)
    db.commit()
    db.refresh(new_col)

    # 응답 객체 수동 구성 (transform 조립)
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
    if not col:
        raise HTTPException(status_code=404, detail="Column not found")

    # 1. 일반 필드 업데이트 (transform 제외)
    # exclude_unset=True: 프론트에서 보내지 않은 필드는 건드리지 않음 (핵심!)
    update_dict = col_data.model_dump(exclude_unset=True, by_alias=False, exclude={"transform"})

    for key, value in update_dict.items():
        setattr(col, key, value)

    # 2. Transform 객체 별도 처리 (들어왔을 경우에만)
    if col_data.transform:
        if col_data.transform.scaleX is not None: col.scale_x = col_data.transform.scaleX
        if col_data.transform.scaleY is not None: col.scale_y = col_data.transform.scaleY
        if col_data.transform.rotation is not None: col.rotation = col_data.transform.rotation

    # 3. parent_id가 0으로 들어오면 None으로 보정 (최상위 이동 시)
    if col.parent_id == 0:
        col.parent_id = None

    db.add(col)
    db.commit()
    db.refresh(col)

    # 응답 조립
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


@router.post("/projects/{project_id}/cards", response_model=CardResponse)
@vectorize(search_description="Create card in project", capture_return_value=True, replay=True)
def create_card(
        project_id: int,
        card_data: CardCreate,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 1. 프로젝트 확인
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")

    # ✅ [수정 포인트 1] 0이나 빈 값이 들어오면 None으로 변환 (이게 핵심!)
    # (Python에서 0은 False로 취급되므로, 이 조건문 하나로 0과 None을 모두 처리할 수 있습니다.)
    final_column_id = card_data.column_id if card_data.column_id else None

    # 2. 컬럼 ID가 유효한 값(1 이상)일 때만 DB 조회 및 검사
    if final_column_id:
        column = db.get(BoardColumn, final_column_id)
        if not column:
            raise HTTPException(status_code=404, detail="지정된 컬럼을 찾을 수 없습니다.")
        if column.project_id != project_id:
            raise HTTPException(status_code=400, detail="해당 컬럼은 이 프로젝트에 속하지 않습니다.")

    # 3. 카드 생성
    new_card = Card(
        title=card_data.title,
        content=card_data.content,
        project_id=project_id,
        column_id=final_column_id,  # ✅ [수정 포인트 2] 변환된 값(None) 사용
        order=card_data.order,
        x=card_data.x,
        y=card_data.y,
        card_type=card_data.card_type,
        start_date=card_data.start_date,
        due_date=card_data.due_date
    )

    # 담당자 연결
    if card_data.assignee_ids:
        users = db.exec(select(User).where(User.id.in_(card_data.assignee_ids))).all()
        new_card.assignees = users

    db.add(new_card)
    db.commit()
    db.refresh(new_card)

    # 로그 기록
    user = db.get(User, user_id)
    location = f"'{project.name}' 프로젝트"
    if final_column_id: # column_id 대신 final_column_id 체크
        # column 변수가 위 if문 스코프 안에 있으므로 다시 조회하거나 로직 조정 필요
        # 간단하게 다시 조회
        col = db.get(BoardColumn, final_column_id)
        if col:
            location += f"의 '{col.title}' 컬럼"

    log_activity(
        db=db,
        user_id=user_id,
        workspace_id=project.workspace_id,
        action_type="CREATE",
        content=f"📝 '{user.name}'님이 {location}에 카드 '{new_card.title}'을(를) 생성했습니다."
    )

    return new_card

@router.delete("/columns/{column_id}")
@vectorize(search_description="Delete board column (Preserve cards)", capture_return_value=True)
def delete_column(
        column_id: int,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    컬럼(그룹)을 삭제합니다.
    ✅ 변경점: 컬럼 안에 있던 카드들은 삭제되지 않고 '백로그(Unassigned)' 상태로 변경됩니다.
    """
    # 1. 컬럼 조회
    column = db.get(BoardColumn, column_id)
    if not column:
        raise HTTPException(status_code=404, detail="Column not found")

    project = db.get(Project, column.project_id)
    col_title = column.title
    card_count = len(column.cards)

    # 2. [핵심] 카드 대피시키기 (column_id = None)
    # 모델에 cascade="all, delete"가 걸려 있어도,
    # 관계를 먼저 끊고(None) 커밋하면 삭제되지 않습니다.
    for card in column.cards:
        card.column_id = None
        db.add(card)

    # 카드를 먼저 대피시킨 내용을 저장 (필수!)
    db.commit()

    # 3. 이제 빈 껍데기가 된 컬럼 삭제
    db.refresh(column) # 관계 갱신
    db.delete(column)
    db.commit()

    # 4. 활동 로그 기록
    if project:
        user = db.get(User, user_id)
        log_activity(
            db=db,
            user_id=user_id,
            workspace_id=project.workspace_id,
            action_type="DELETE",
            # 로그 메시지도 상황에 맞게 조금 더 상세하게 적어주면 좋습니다.
            content=f"🗑️ '{user.name}'님이 그룹 '{col_title}'을(를) 삭제했습니다. (카드 {card_count}개는 보관됨)"
        )

    return {"message": "그룹이 삭제되었으며, 포함된 카드들은 보관함으로 이동되었습니다."}


# 3. 특정 프로젝트의 모든 컬럼 및 카드 조회
@router.get("/projects/{project_id}/board")
@vectorize(search_description="Get project kanban board", capture_return_value=True, replay=True)  # 👈 추가
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

@router.get("/projects/{project_id}/cards", response_model=List[CardResponse])
@vectorize(search_description="Get all cards in project", capture_return_value=True, replay=True)
def get_project_cards(
        project_id: int,
        db: Session = Depends(get_db)
):
    """
    특정 프로젝트에 속한 '모든 카드'를 조회합니다.
    (칸반 컬럼에 있는 카드 + 컬럼 없는 백로그/화이트보드 카드 모두 포함)
    """
    cards = db.exec(
        select(Card)
        .where(Card.project_id == project_id)
        .order_by(Card.id) # 또는 order_by(Card.order)
    ).all()

    return cards


@router.get("/projects/{project_id}/columns", response_model=List[BoardColumnResponse])
def get_project_columns(
        project_id: int,
        db: Session = Depends(get_db)
):
    columns = db.exec(
        select(BoardColumn)
        .where(BoardColumn.project_id == project_id)
        .order_by(BoardColumn.order)
    ).all()
    return columns


@router.patch("/cards/{card_id}", response_model=CardResponse)
@vectorize(search_description="Update card", capture_return_value=True, replay=True)  # 👈 추가
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

@router.delete("/cards/{card_id}")
@vectorize(search_description="Delete card", capture_return_value=True)
def delete_card(
        card_id: int,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 1. 카드 조회
    card = db.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="카드를 찾을 수 없습니다.")

    # 2. 삭제 전 로그를 위한 정보 수집 (삭제하면 정보가 사라지므로 미리 조회)
    column = db.get(BoardColumn, card.column_id)
    project = db.get(Project, column.project_id) if column else None

    # 3. 삭제 수행
    # (Card 모델에 cascade 옵션이 잘 설정되어 있다면 댓글 등도 자동 삭제됩니다.)
    db.delete(card)
    db.commit()

    # 4. 활동 로그 기록
    if project:
        user = db.get(User, user_id)
        log_activity(
            db=db,
            user_id=user_id,
            workspace_id=project.workspace_id,
            action_type="DELETE",
            content=f"🗑️ '{user.name}'님이 카드 '{card.title}'을(를) 삭제했습니다."
        )

    return {"message": "카드가 삭제되었습니다."}


@router.post("/cards/{card_id}/files/{file_id}", response_model=CardResponse)
@vectorize(search_description="Attach file to card", capture_return_value=True, replay=True)  # 👈 추가
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
@vectorize(search_description="Detach file from card", capture_return_value=True, replay=True)  # 👈 추가
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
@vectorize(search_description="Get card details", capture_return_value=True, replay=True)  # 👈 추가
def get_card(
        card_id: int,
        db: Session = Depends(get_db)
):
    card = db.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="카드를 찾을 수 없습니다.")

    return card


@router.post("/cards/{card_id}/comments", response_model=CardCommentResponse)
@vectorize(search_description="Add comment to card", capture_return_value=True)
def create_comment(
        card_id: int,
        comment_data: CardCommentCreate,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    card = db.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    new_comment = CardComment(
        card_id=card_id,
        user_id=user_id,
        content=comment_data.content
    )
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)

    # 활동 로그 (선택)
    user = db.get(User, user_id)
    # log_activity(...) # 필요하다면 추가

    return new_comment


@router.get("/cards/{card_id}/comments", response_model=List[CardCommentResponse])
def get_card_comments(
        card_id: int,
        db: Session = Depends(get_db)
):
    comments = db.exec(
        select(CardComment)
        .where(CardComment.card_id == card_id)
        .order_by(CardComment.created_at.asc())  # 오래된 순 정렬
    ).all()
    return comments


@router.delete("/cards/comments/{comment_id}")
def delete_comment(
        comment_id: int,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    comment = db.get(CardComment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    if comment.user_id != user_id:
        raise HTTPException(status_code=403, detail="작성자만 삭제할 수 있습니다.")

    db.delete(comment)
    db.commit()
    return {"message": "댓글이 삭제되었습니다."}

# 1. 프로젝트 내 모든 카드 연결 조회 (프론트엔드 포맷 맞춤)
@router.get("/projects/{project_id}/connections", response_model=List[CardConnectionResponse])
@vectorize(search_description="Get project card connections", capture_return_value=True)
def get_project_connections(
        project_id: int,
        db: Session = Depends(get_db)
):
    # ✅ 수정: Card.project_id로 직접 필터링 (column_id JOIN 제거)
    statement = (
        select(CardDependency)
        .join(Card, CardDependency.from_card_id == Card.id)
        .where(Card.project_id == project_id)  # 👈 직접 project_id 사용
    )
    connections = db.exec(statement).all()

    results = []
    for conn in connections:
        results.append(CardConnectionResponse(
            id=conn.id,
            from_card_id=conn.from_card_id,
            to_card_id=conn.to_card_id,
            board_id=project_id,
            style=conn.style,
            shape=conn.shape
        ))

    return results


@router.post("/cards/connections")
@vectorize(search_description="Create dependency between cards", capture_return_value=True)
def create_card_connection(
        connection_data: CardConnectionCreate,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 1. 카드 조회
    from_card = db.get(Card, connection_data.from_card_id)
    to_card = db.get(Card, connection_data.to_card_id)

    if not from_card or not to_card:
        raise HTTPException(status_code=404, detail="카드를 찾을 수 없습니다.")

    # 2. 프로젝트 일치 확인
    if from_card.project_id != to_card.project_id:
        raise HTTPException(status_code=400, detail="다른 프로젝트의 카드끼리는 연결할 수 없습니다.")

    # 3. 연결 생성 (수정됨)
    new_dependency = CardDependency(
        from_card_id=from_card.id,
        to_card_id=to_card.id,

        # 🚨 [수정] 스키마에 없는 값을 읽으려던 코드 제거
        # dependency_type=connection_data.dependency_type  <-- (삭제)

        # ✅ [대체] 기본값으로 고정하거나, 필요하면 스키마에 추가해야 함
        dependency_type="finish_to_start"
    )

    # (선택 사항) 만약 DB 모델(CardDependency)에 style, shape 필드가 있다면 아래처럼 저장 가능
    # if hasattr(new_dependency, "style"): new_dependency.style = connection_data.style
    # if hasattr(new_dependency, "shape"): new_dependency.shape = connection_data.shape

    db.add(new_dependency)
    db.commit()
    db.refresh(new_dependency)

    # 4. 로그 기록
    project = db.get(Project, from_card.project_id)
    user = db.get(User, user_id)

    log_activity(
        db=db,
        user_id=user_id,
        workspace_id=project.workspace_id,
        action_type="UPDATE",
        content=f"🔗 '{user.name}'님이 카드 '{from_card.title}'와(과) '{to_card.title}'을(를) 연결했습니다."
    )

    return {"message": "카드가 연결되었습니다."}

# 3. 카드 연결 삭제 (ID로 삭제)
@router.delete("/cards/connections/{connection_id}")
@vectorize(search_description="Delete card connection", capture_return_value=True)
def delete_card_connection(
        connection_id: int,
        db: Session = Depends(get_db),
        user_id: int = Depends(get_current_user_id)
):
    connection = db.get(CardDependency, connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    db.delete(connection)
    db.commit()

    return {"message": "연결이 삭제되었습니다."}
