from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from datetime import time, datetime, timedelta

from app.database import get_db
from app.routers.workspace import get_current_user_id
from app.models.schedule import Schedule, ProjectEvent
from app.models.workspace import WorkspaceMember
from app.models.user import User
from app.schemas import ScheduleCreate, ScheduleResponse, FreeTimeSlot, ProjectEventCreate, ProjectEventResponse
from app.utils.logger import log_activity
from app.models.workspace import Project
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
        workspace_id=None,  # 개인 활동
        action_type="SCHEDULE",
        content=f"📅 '{user.name}'님이 새로운 일정 '{new_schedule.description or '일정'}'을(를) 등록했습니다."
    )

    return new_schedule


@router.delete("/schedules/{schedule_id}")
@vectorize(search_description="Delete personal schedule", capture_return_value=True)
def delete_personal_schedule(
        schedule_id: int,
        db: Session = Depends(get_db),
        user_id: int = Depends(get_current_user_id)
):
    # 1. 일정 조회
    schedule = db.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다.")

    # 2. 본인 확인 (내 일정만 삭제 가능)
    if schedule.user_id != user_id:
        raise HTTPException(status_code=403, detail="본인의 일정만 삭제할 수 있습니다.")

    # 3. 삭제
    db.delete(schedule)
    db.commit()

    return {"message": "개인 일정이 삭제되었습니다."}

@router.get("/schedules/me", response_model=List[ScheduleResponse])
def get_my_schedules(
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    내가 등록한 개인 시간표(수업 등) 목록을 조회합니다.
    """
    schedules = db.exec(select(Schedule).where(Schedule.user_id == user_id)).all()
    return schedules


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

        current_time = datetime.combine(datetime.today(), time(9, 0))  # 오전 9시 시작
        end_limit = datetime.combine(datetime.today(), time(22, 0))  # 오후 10시 종료

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


@router.get("/projects/{project_id}/events", response_model=List[ProjectEventResponse])
@vectorize(search_description="List project calendar events", capture_return_value=True)
def get_project_events(
        project_id: int,
        db: Session = Depends(get_db),
        user_id: int = Depends(get_current_user_id)
):
    # (선택) 여기서 사용자가 프로젝트 멤버인지 체크하는 로직을 추가할 수 있습니다.
    events = db.exec(select(ProjectEvent).where(ProjectEvent.project_id == project_id)).all()
    return events


# 2. 프로젝트 일정 등록
@router.post("/projects/{project_id}/events", response_model=ProjectEventResponse)
@vectorize(search_description="Create project calendar event", capture_return_value=True)
def create_project_event(
        project_id: int,
        event_data: ProjectEventCreate,
        db: Session = Depends(get_db),
        user_id: int = Depends(get_current_user_id)
):
    # 프로젝트 존재 확인
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    new_event = ProjectEvent(
        project_id=project_id,
        created_by=user_id,
        **event_data.model_dump()
    )

    db.add(new_event)
    db.commit()
    db.refresh(new_event)

    # 활동 로그 기록
    user = db.get(User, user_id)
    log_activity(
        db=db,
        user_id=user_id,
        workspace_id=project.workspace_id,  # 프로젝트가 속한 워크스페이스에 로그 남김
        action_type="CALENDAR",
        content=f"📅 '{user.name}'님이 프로젝트 '{project.name}'에 일정 '{new_event.title}'을(를) 등록했습니다."
    )

    return new_event


# 3. 프로젝트 일정 삭제
@router.delete("/events/{event_id}")
@vectorize(search_description="Delete project event", capture_return_value=True)
def delete_project_event(
        event_id: int,
        db: Session = Depends(get_db),
        user_id: int = Depends(get_current_user_id)
):
    event = db.get(ProjectEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    db.delete(event)
    db.commit()

    return {"message": "일정이 삭제되었습니다."}
