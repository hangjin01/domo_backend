from fastapi import APIRouter, Depends
from sqlmodel import Session, select, desc
from typing import List

from app.database import get_db
from app.routers.workspace import get_current_user_id
from app.models.activity import ActivityLog
from app.schemas import ActivityLogResponse
from vectorwave import *

router = APIRouter(tags=["Activity Logs"])


# 1. 내 활동 기록 전체 보기
@router.get("/users/me/activities", response_model=List[ActivityLogResponse])
@vectorize(search_description="View my activity logs", capture_return_value=True, replay=True) # 👈 추가
def get_my_activities(
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 내 ID로 필터링, 최신순 정렬
    statement = select(ActivityLog).where(ActivityLog.user_id == user_id).order_by(desc(ActivityLog.created_at))
    return db.exec(statement).all()


# 2. 특정 워크스페이스의 활동 기록 보기 (팀원들이 뭘 했는지)
@router.get("/workspaces/{workspace_id}/activities", response_model=List[ActivityLogResponse])
@vectorize(search_description="View workspace activity logs", capture_return_value=True, replay=True) # 👈 추가
def get_workspace_activities(
        workspace_id: int,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # (여기서 멤버 권한 체크 로직을 넣는 것이 좋습니다)

    statement = select(ActivityLog).where(ActivityLog.workspace_id == workspace_id).order_by(
        desc(ActivityLog.created_at))
    return db.exec(statement).all()
