from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List

from app.database import get_db
from app.models.user import User
from app.models.session import UserSession
from app.models.workspace import Workspace, WorkspaceMember, Project
from app.schemas import WorkspaceCreate, WorkspaceResponse, ProjectCreate, ProjectResponse
from datetime import datetime

router = APIRouter(tags=["Workspace & Project"])

# 쿠키에서 세션 ID를 추출하여 유저 ID 반환하는 의존성 함수
from fastapi import Cookie
def get_current_user_id(session_id: str = Cookie(None), db: Session = Depends(get_db)):
    if not session_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    session = db.get(UserSession, session_id)
    if not session or session.expires_at < datetime.now():
        raise HTTPException(status_code=401, detail="세션이 만료되었습니다.")

    return session.user_id


# 1. 워크스페이스 생성 (팀 만들기)
@router.post("/workspaces", response_model=WorkspaceResponse)
def create_workspace(
        ws_data: WorkspaceCreate,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 워크스페이스 생성
    new_ws = Workspace(
        name=ws_data.name,
        description=ws_data.description,
        owner_id=user_id
    )
    db.add(new_ws)
    db.commit()
    db.refresh(new_ws)

    # 생성자를 멤버(Admin)로 추가
    member = WorkspaceMember(workspace_id=new_ws.id, user_id=user_id, role="admin")
    db.add(member)
    db.commit()

    return new_ws

# 2. 내 워크스페이스 목록 조회
@router.get("/workspaces", response_model=List[WorkspaceResponse])
def get_my_workspaces(
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 내가 멤버로 속한 워크스페이스 찾기 (Join 쿼리)
    statement = (
        select(Workspace)
        .join(WorkspaceMember)
        .where(WorkspaceMember.user_id == user_id)
    )
    results = db.exec(statement).all()
    return results

# 3. 프로젝트 생성 (워크스페이스 안에)
@router.post("/workspaces/{workspace_id}/projects", response_model=ProjectResponse)
def create_project(
        workspace_id: int,
        project_data: ProjectCreate,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 권한 확인: 내가 이 워크스페이스 멤버인가?
    member = db.get(WorkspaceMember, (workspace_id, user_id))
    if not member:
        raise HTTPException(status_code=403, detail="워크스페이스 멤버가 아닙니다.")

    new_project = Project(
        name=project_data.name,
        description=project_data.description,
        workspace_id=workspace_id
    )
    db.add(new_project)
    db.commit()
    db.refresh(new_project)

    return new_project

@router.get("/workspaces/{workspace_id}/projects", response_model=List[ProjectResponse])
def get_workspace_projects(
        workspace_id: int,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 1. 권한 확인: 내가 이 워크스페이스의 멤버인지 확인 (보안 필수!)
    member = db.get(WorkspaceMember, (workspace_id, user_id))
    if not member:
        raise HTTPException(status_code=403, detail="워크스페이스 멤버가 아니거나 존재하지 않는 워크스페이스입니다.")

    # 2. 해당 워크스페이스의 프로젝트들만 조회
    projects = db.exec(select(Project).where(Project.workspace_id == workspace_id)).all()
    return projects