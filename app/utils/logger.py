# [파일 안내] backend/app/utils/logger.py
# 업무 변경 내용을 ActivityLog로 기록하는 공통 헬퍼입니다.
# 기록할 사용자·작업 종류·팀 범위를 호출부가 전달합니다. 업무 데이터 저장과 활동 기록의 트랜잭션/실패 처리를 함께 확인하세요.

from sqlmodel import Session
from app.models.activity import ActivityLog

def log_activity(
        db: Session,
        user_id: int,
        content: str,
        action_type: str,
        workspace_id: int = None
):
    """
    활동 로그를 DB에 저장하는 헬퍼 함수
    """
    log = ActivityLog(
        user_id=user_id,
        content=content,
        action_type=action_type,
        workspace_id=workspace_id
    )
    db.add(log)
    db.commit()
