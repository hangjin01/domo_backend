# [파일 안내] backend/app/routers/activity.py
# 사용자/팀 활동 로그 조회 요청을 처리하는 FastAPI 라우터입니다.
# 경로 접두사는 main.py의 include_router에서 붙습니다. 아래 데코레이터는 파일 내부 상대 경로이며 응답 DTO는 schemas.py에 있습니다.
# 일반 흐름은 입력 검증 → 세션/대상 확인 → DB 조회/변경 → commit/refresh → 응답/실시간 알림입니다. 모든 함수가 같은 권한 검사를 하는 것은 아닙니다.
# 현재 WS·파일 접근 등 권한 보강 과제가 남아 있습니다. Depends 존재 여부와 함수 본문의 팀원/소유자 검사를 모두 확인하세요.

from fastapi import APIRouter, Depends
from sqlmodel import Session, select, desc
from typing import List

from app.database import get_db
from app.routers.workspace import get_current_user_id
from app.models.activity import ActivityLog
from app.schemas import ActivityLogResponse
from app.utils.vectorwave import vectorize

router = APIRouter(tags=["Activity Logs"])


# 1. 내 활동 기록 전체 보기
# 엔드포인트: GET /users/me/activities → get_my_activities.
# 주입 의존성: Depends(get_current_user_id), Depends(get_db).
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
# 엔드포인트: GET /workspaces/{workspace_id}/activities → get_workspace_activities.
# 주입 의존성: Depends(get_current_user_id), Depends(get_db).
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
