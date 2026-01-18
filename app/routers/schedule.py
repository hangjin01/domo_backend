from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from datetime import time, datetime, timedelta

from app.database import get_db
from app.routers.workspace import get_current_user_id
from app.models.schedule import Schedule
from app.models.workspace import WorkspaceMember
from app.models.user import User
from app.schemas import ScheduleCreate, ScheduleResponse, FreeTimeSlot
from app.utils.logger import log_activity
from vectorwave import *



router = APIRouter(tags=["Schedule & Free Time"])

# 1. 내 시간표 등록 (수업 추가)
@router.post("/schedules", response_model=ScheduleResponse)
@vectorize(search_description="Create a personal schedule", capture_return_value=True, replay=True)
def add_schedule(s_data: ScheduleCreate,
                 user_id: int = Depends(get_current_user_id),
                 db: Session = Depends(get_db)):
    new_schedule = Schedule(**s_data.model_dump(), user_id=user_id)
    db.add(new_schedule)
    db.commit()
    db.refresh(new_schedule)
    user = db.get(User, user_id)

    log_activity(
        db=db,
        user_id=user_id,
        workspace_id=None, # 개인 활동
        action_type="SCHEDULE",
        content=f"📅 '{user.name}'님이 새로운 일정 '{new_schedule.description or '일정'}'을(를) 등록했습니다."
    )

    return new_schedule

# 2. 특정 워크스페이스 팀원들의 공통 빈 시간 계산 (핵심!)
@router.get("/workspaces/{workspace_id}/free-time", response_model=List[FreeTimeSlot])
def get_common_free_time(workspace_id: int, db: Session = Depends(get_db)):
    # 1. 워크스페이스 모든 멤버 ID 조회
    members = db.exec(select(WorkspaceMember.user_id).where(WorkspaceMember.workspace_id == workspace_id)).all()
    if not members:
        raise HTTPException(status_code=404, detail="멤버가 없습니다.")

    # 2. 모든 멤버의 시간표 가져오기
    all_schedules = db.exec(select(Schedule).where(Schedule.user_id.in_(members))).all()

    # 3. 빈 시간 계산 로직 (단순화된 버전)
    # 09:00 ~ 22:00 사이를 비어있는 시간의 후보로 잡고, 수업 시간을 뺍니다.
    free_slots = []

    for day in range(5):  # 월~금
        # 해당 요일의 모든 팀원 수업 시간 (시작 시간 순 정렬)
        day_schedules = sorted(
            [s for s in all_schedules if s.day_of_week == day],
            key=lambda x: x.start_time
        )

        current_time = datetime.combine(datetime.today(), time(9, 0)) # 오전 9시 시작
        end_limit = datetime.combine(datetime.today(), time(22, 0))   # 오후 10시 종료

        for s in day_schedules:
            s_start = datetime.combine(datetime.today(), s.start_time)
            s_end = datetime.combine(datetime.today(), s.end_time)

            # 수업 시작 전까지 시간이 비어있다면 추가 (최소 30분 이상인 경우만)
            if s_start > current_time + timedelta(minutes=30):
                free_slots.append(FreeTimeSlot(
                    day_of_week=day,
                    start_time=current_time.time(),
                    end_time=s_start.time()
                ))

            # 현재 시간을 수업 종료 시간으로 갱신 (더 늦은 시간 기준)
            if s_end > current_time:
                current_time = s_end

        # 마지막 수업 이후부터 밤 10시까지 비어있다면 추가
        if end_limit > current_time + timedelta(minutes=30):
            free_slots.append(FreeTimeSlot(
                day_of_week=day,
                start_time=current_time.time(),
                end_time=end_limit.time()
            ))

    return free_slots