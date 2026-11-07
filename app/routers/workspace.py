# [파일 안내] backend/app/routers/workspace.py
# 팀·프로젝트·팀원·초대와 접속 상태 요청을 처리하는 FastAPI 라우터입니다.
# 경로 접두사는 main.py의 include_router에서 붙습니다. 아래 데코레이터는 파일 내부 상대 경로이며 응답 DTO는 schemas.py에 있습니다.
# 일반 흐름은 입력 검증 → 세션/대상 확인 → DB 조회/변경 → commit/refresh → 응답/실시간 알림입니다. 모든 함수가 같은 권한 검사를 하는 것은 아닙니다.
# 현재 WS·파일 접근 등 권한 보강 과제가 남아 있습니다. Depends 존재 여부와 함수 본문의 팀원/소유자 검사를 모두 확인하세요.

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlmodel import Session, select
from typing import List
import uuid
from app.database import get_db
from app.models.user import User
from app.models.session import UserSession
from app.models.workspace import Workspace, WorkspaceMember, Project
from app.schemas import WorkspaceCreate, WorkspaceResponse, ProjectCreate, ProjectResponse, AddMemberRequest, \
    WorkspaceMemberResponse, UserResponse
from app.models.invitation import Invitation
from app.schemas import InvitationCreate, InvitationResponse, InvitationInfo
from datetime import datetime, timedelta
from typing import Any
from app.utils.logger import log_activity
from app.utils.vectorwave import vectorize
from app.schemas import WorkspaceUpdate, ProjectUpdate
from fastapi.concurrency import run_in_threadpool
import asyncio
import json
from fastapi import Request
from fastapi.responses import StreamingResponse
from app.utils.connection_manager import workspace_event_manager

router = APIRouter(tags=["Workspace & Project"])

# 쿠키에서 세션 ID를 추출하여 유저 ID 반환하는 의존성 함수
from fastapi import Cookie


def get_current_user_id(session_id: str = Cookie(None), db: Session = Depends(get_db)):
    # 인증의 신뢰 근거는 요청 body의 user_id가 아니라 쿠키와 DB 세션입니다.
    # 쿠키 부재/세션 만료는 401이며, 이 함수만으로 특정 팀/프로젝트 접근 권한까지 확인하지는 않습니다.
    if not session_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    session = db.get(UserSession, session_id)
    if not session or session.expires_at < datetime.now():
        raise HTTPException(status_code=401, detail="세션이 만료되었습니다.")

    user = db.get(User, session.user_id)
    if user:
        # 요청이 올 때 최근 활동 시각을 갱신하여 온라인 멤버 판정에 활용합니다.
        # 조회 API에서도 이 의존성을 호출하면 DB 쓰기(commit)가 발생한다는 점에 주의합니다.
        user.last_active_at = datetime.now()
        db.add(user)
        db.commit()

    return session.user_id


# 1. 워크스페이스 생성 (팀 만들기)
# 엔드포인트: POST /workspaces → create_workspace.
# 주입 의존성: Depends(get_current_user_id), Depends(get_db).
# DB commit이 포함된 변경 요청입니다. 저장 전에 대상/권한을 확인하고, 실패 시 부분 저장 여부를 점검해야 합니다.
@router.post("/workspaces", response_model=WorkspaceResponse)
@vectorize(search_description="Create workspace", capture_return_value=True, replay=True)  # 👈 추가
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

    user = db.get(User, user_id)
    log_activity(
        db=db,
        user_id=user_id,
        workspace_id=new_ws.id,
        action_type="CREATE",
        content=f"🚩 '{user.name}'님이 새로운 워크스페이스 '{new_ws.name}'을(를) 시작했습니다."
    )

    return new_ws


# 2. 내 워크스페이스 목록 조회
# 엔드포인트: GET /workspaces → get_my_workspaces.
# 주입 의존성: Depends(get_current_user_id), Depends(get_db).
@router.get("/workspaces", response_model=List[WorkspaceResponse])
@vectorize(search_description="List my workspaces", capture_return_value=True, replay=True)  # 👈 추가
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
# 엔드포인트: POST /workspaces/{workspace_id}/projects → create_project.
# 주입 의존성: Depends(get_current_user_id), Depends(get_db).
# DB commit이 포함된 변경 요청입니다. 저장 전에 대상/권한을 확인하고, 실패 시 부분 저장 여부를 점검해야 합니다.
# 연결된 클라이언트에 이벤트를 전파합니다. DB 영속화와 소켓 알림은 동일한 트랜잭션이 아닙니다.
@router.post("/workspaces/{workspace_id}/projects", response_model=ProjectResponse)
@vectorize(search_description="Create project", capture_return_value=True, replay=True)  # 👈 추가
async def create_project(
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

    user = db.get(User, user_id)
    log_activity(
        db=db,
        user_id=user_id,
        workspace_id=workspace_id,
        action_type="CREATE",
        content=f"📂 '{user.name}'님이 프로젝트 '{new_project.name}'을(를) 만들었습니다."
    )

    await workspace_event_manager.broadcast(workspace_id, {
        "type": "PROJECT_CREATED",
        "user_id": user_id,
        "data": {"id": new_project.id, "name": new_project.name, "description": new_project.description, "workspace_id": workspace_id}
    })

    return new_project


# 엔드포인트: GET /workspaces/{workspace_id}/projects → get_workspace_projects.
# 주입 의존성: Depends(get_current_user_id), Depends(get_db).
@router.get("/workspaces/{workspace_id}/projects", response_model=List[ProjectResponse])
@vectorize(search_description="List workspace projects", capture_return_value=True, replay=True)  # 👈 추가
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


# app/routers/workspace.py 맨 아래에 추가

# 5. 워크스페이스에 팀원 초대 (이메일로 추가)
# 엔드포인트: POST /workspaces/{workspace_id}/members → add_workspace_member.
# 주입 의존성: Depends(get_current_user_id), Depends(get_db).
# DB commit이 포함된 변경 요청입니다. 저장 전에 대상/권한을 확인하고, 실패 시 부분 저장 여부를 점검해야 합니다.
# 연결된 클라이언트에 이벤트를 전파합니다. DB 영속화와 소켓 알림은 동일한 트랜잭션이 아닙니다.
@router.post("/workspaces/{workspace_id}/members")
@vectorize(search_description="Add member manually", capture_return_value=True, replay=True)  # 👈 추가
async def add_workspace_member(
        workspace_id: int,
        request: AddMemberRequest,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 1. 권한 확인: 초대하는 사람(나)이 해당 워크스페이스의 admin인지 확인
    my_membership = db.get(WorkspaceMember, (workspace_id, user_id))
    if not my_membership or my_membership.role != "admin":
        raise HTTPException(status_code=403, detail="팀원 초대 권한이 없습니다 (관리자 전용).")

    # 2. 초대할 유저가 존재하는지 확인
    target_user = db.exec(select(User).where(User.email == request.email)).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="해당 이메일을 가진 사용자가 존재하지 않습니다.")

    # 3. 이미 멤버인지 확인
    existing_member = db.get(WorkspaceMember, (workspace_id, target_user.id))
    if existing_member:
        raise HTTPException(status_code=400, detail="이미 워크스페이스의 멤버입니다.")

    # 4. 멤버 추가 (기본 역할은 'member')
    new_member = WorkspaceMember(
        workspace_id=workspace_id,
        user_id=target_user.id,
        role="member"
    )
    db.add(new_member)
    db.commit()

    actor = db.get(User, user_id)
    ws = db.get(Workspace, workspace_id)
    log_activity(
        db=db,
        user_id=user_id,
        workspace_id=workspace_id,
        action_type="MEMBER_ADD",
        content=f"👥 '{actor.name}'님이 '{target_user.name}'님을 '{ws.name}' 워크스페이스 멤버로 추가했습니다."
    )

    await workspace_event_manager.broadcast(workspace_id, {
        "type": "MEMBER_JOINED",
        "user_id": user_id,
        "data": {
            "workspace_id": workspace_id,
            "user": {"id": target_user.id, "name": target_user.name, "email": target_user.email},
            "role": "member",
        }
    })

    return {"message": f"{target_user.name} 님이 팀원으로 추가되었습니다."}


# app/routers/workspace.py 맨 아래에 추가

# 6. 워크스페이스 전체 멤버 목록 조회
# 엔드포인트: GET /workspaces/{workspace_id}/members → get_workspace_members.
# 주입 의존성: Depends(get_current_user_id), Depends(get_db).
@router.get("/workspaces/{workspace_id}/members", response_model=List[WorkspaceMemberResponse])
@vectorize(search_description="List workspace members", capture_return_value=True, replay=True)  # 👈 추가
def get_workspace_members(
        workspace_id: int,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
) -> Any:
    # 1. 권한 확인: 요청한 사람이 이 워크스페이스의 멤버인지 확인
    membership = db.get(WorkspaceMember, (workspace_id, user_id))
    if not membership:
        raise HTTPException(status_code=403, detail="워크스페이스 멤버만 조회 가능합니다.")

    # 2. User 테이블과 WorkspaceMember 테이블을 Join하여 정보 조회
    # SQLModel의 select 문법으로 유저 정보와 역할을 동시에 가져옵니다.
    statement = (
        select(User.id.label("user_id"), User.name, User.email, WorkspaceMember.role)
        .join(WorkspaceMember, User.id == WorkspaceMember.user_id)
        .where(WorkspaceMember.workspace_id == workspace_id)
    )

    results = db.exec(statement).all()

    # 결과를 스키마 형태에 맞게 변환하여 반환
    return [
        WorkspaceMemberResponse(
            user_id=r.user_id,
            name=r.name,
            email=r.email,
            role=r.role
        ) for r in results
    ]

# 엔드포인트: GET /workspaces/{workspace_id}/online-members/stream → stream_online_members.
# 주입 의존성: Depends(get_current_user_id), Depends(get_db).
@router.get("/workspaces/{workspace_id}/online-members/stream")
@vectorize(search_description="Get online members", capture_return_value=True, replay=True)  # 👈 추가
async def stream_online_members(
        workspace_id: int,
        request: Request,
        user_id: int = Depends(get_current_user_id), # 👈 보안: 로그인한 유저만 접근 가능
        db: Session = Depends(get_db)
):
    """
    Server-Sent Events (SSE) 엔드포인트
    클라이언트가 연결하면, 5초마다 온라인 멤버 변경사항을 확인하여 푸시합니다.
    """
    # 1. 권한 확인 (이 워크스페이스 멤버인가?)
    #    스트림 연결 전에 먼저 확인해서, 권한 없으면 즉시 차단합니다.
    member = db.get(WorkspaceMember, (workspace_id, user_id))
    if not member:
        raise HTTPException(status_code=403, detail="워크스페이스 멤버만 조회할 수 있습니다.")

    async def event_generator():
        prev_online_ids: set = set()

        while True:
            # 클라이언트 연결 끊김 체크
            if await request.is_disconnected():
                break

            # 2. 동기 DB 작업을 쓰레드풀에서 실행 (서버 블로킹 방지)
            def fetch_online_users():
                active_threshold = datetime.now() - timedelta(minutes=1)
                statement = (
                    select(User)
                    .join(WorkspaceMember, User.id == WorkspaceMember.user_id)
                    .where(WorkspaceMember.workspace_id == workspace_id)
                    .where(User.last_active_at >= active_threshold)
                )
                return db.exec(statement).all()

            # await로 결과를 기다림 (이 동안 다른 요청 처리 가능)
            online_users = await run_in_threadpool(fetch_online_users)

            current_online_ids = {user.id for user in online_users}

            # 변경사항이 있거나, 최초 연결(prev가 비어있음)인 경우 전송
            # (단, 아무도 없을 때도 빈 리스트를 보내줘야 화면이 갱신되므로 조건 수정)
            if current_online_ids != prev_online_ids or not prev_online_ids:
                data = json.dumps({
                    "online_members": [
                        {
                            "id": user.id,
                            "name": user.name,
                            "email": user.email,
                            "profile_image": user.profile_image
                        }
                        for user in online_users
                    ]
                }, ensure_ascii=False)

                yield f"data: {data}\n\n"
                prev_online_ids = current_online_ids

            # 5초 대기
            await asyncio.sleep(5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# 엔드포인트: POST /workspaces/{workspace_id}/invitations → create_invitation.
# 주입 의존성: Depends(get_current_user_id), Depends(get_db).
# DB commit이 포함된 변경 요청입니다. 저장 전에 대상/권한을 확인하고, 실패 시 부분 저장 여부를 점검해야 합니다.
@router.post("/workspaces/{workspace_id}/invitations", response_model=InvitationResponse)
@vectorize(search_description="Generate invitation link", capture_return_value=True, replay=True)  # 👈 추가
def create_invitation(
        workspace_id: int,
        invite_data: InvitationCreate,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 1. 권한 확인 (관리자만 초대 가능)
    membership = db.get(WorkspaceMember, (workspace_id, user_id))
    if not membership or membership.role != "admin":
        raise HTTPException(status_code=403, detail="관리자만 초대 링크를 만들 수 있습니다.")

    # 2. 초대 토큰 생성
    token = str(uuid.uuid4())
    expires_at = datetime.now() + timedelta(hours=invite_data.expires_in_hours)

    invitation = Invitation(
        token=token,
        workspace_id=workspace_id,
        inviter_id=user_id,
        role=invite_data.role,
        expires_at=expires_at
    )

    db.add(invitation)
    db.commit()

    # 3. 프론트엔드 URL 생성 (환경변수로 도메인 관리 추천)
    import os
    base_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    invite_link = f"{base_url}/invite/{token}"

    return InvitationResponse(invite_link=invite_link, expires_at=expires_at)


# 엔드포인트: GET /invitations/{token} → get_invitation_info.
# 주입 의존성: Depends(get_db).
@router.get("/invitations/{token}", response_model=InvitationInfo)
@vectorize(search_description="Get invitation info", capture_return_value=True)
def get_invitation_info(
        token: str,
        db: Session = Depends(get_db)
):
    """
    초대 링크 정보 조회 (수락 전 확인용)
    로그인 없이도 조회 가능
    """
    # 1. 초대장 조회
    invite = db.exec(select(Invitation).where(Invitation.token == token)).first()
    if not invite:
        raise HTTPException(status_code=404, detail="유효하지 않은 초대 링크입니다.")

    # 2. 만료 확인
    if invite.expires_at < datetime.now():
        raise HTTPException(status_code=400, detail="만료된 초대 링크입니다.")

    # 3. 워크스페이스 & 초대자 정보 조회
    workspace = db.get(Workspace, invite.workspace_id)
    inviter = db.get(User, invite.inviter_id)

    if not workspace:
        raise HTTPException(status_code=404, detail="워크스페이스가 존재하지 않습니다.")

    return InvitationInfo(
        workspace_name=workspace.name,
        inviter_name=inviter.name if inviter else "알 수 없음",
        role=invite.role
    )


# 엔드포인트: POST /invitations/{token}/accept → accept_invitation.
# 주입 의존성: Depends(get_current_user_id), Depends(get_db).
# DB commit이 포함된 변경 요청입니다. 저장 전에 대상/권한을 확인하고, 실패 시 부분 저장 여부를 점검해야 합니다.
# 연결된 클라이언트에 이벤트를 전파합니다. DB 영속화와 소켓 알림은 동일한 트랜잭션이 아닙니다.
@router.post("/invitations/{token}/accept")
@vectorize(search_description="Accept invitation", capture_return_value=True, replay=True)  # 👈 추가
async def accept_invitation(
        token: str,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 1. 초대장 조회
    invite = db.exec(select(Invitation).where(Invitation.token == token)).first()
    if not invite:
        raise HTTPException(status_code=404, detail="유효하지 않은 초대 링크입니다.")

    # 2. 유효성 검사 (만료 확인)
    if invite.expires_at < datetime.now():
        raise HTTPException(status_code=400, detail="만료된 초대 링크입니다.")

    # 3. 이미 멤버인지 확인
    existing_member = db.get(WorkspaceMember, (invite.workspace_id, user_id))
    if existing_member:
        return {"message": "이미 워크스페이스의 멤버입니다."}

    # 4. 멤버 추가
    new_member = WorkspaceMember(
        workspace_id=invite.workspace_id,
        user_id=user_id,
        role=invite.role
    )
    db.add(new_member)
    db.commit()

    new_comer = db.get(User, user_id)
    ws = db.get(Workspace, invite.workspace_id)

    log_activity(
        db=db,
        user_id=user_id,
        workspace_id=invite.workspace_id,
        action_type="JOIN",
        content=f"👋 '{new_comer.name}'님이 '{ws.name}' 워크스페이스에 참여했습니다."
    )

    # 📡 실시간 broadcast: 해당 워크스페이스 멤버들에게 알림
    await workspace_event_manager.broadcast(invite.workspace_id, {
        "type": "MEMBER_JOINED",
        "user_id": user_id,
        "data": {
            "workspace_id": invite.workspace_id,
            "user": {
                "id": new_comer.id,
                "name": new_comer.name,
                "email": new_comer.email,
            },
            "role": invite.role,
        }
    })

    return {"message": "워크스페이스에 성공적으로 참여했습니다!"}


# =================================================================
# 📡 워크스페이스 실시간 WebSocket
# =================================================================

# 엔드포인트: WEBSOCKET /ws/workspaces/{workspace_id} → workspace_events_endpoint.
# 주입 의존성: 선언 없음; 함수 본문에서 별도 검증하는지 확인 필요.
# 연결이 유지되는 동안 메시지를 반복 처리합니다. 종료/예외에서 연결 해제를 수행하고 클라이언트 식별값을 그대로 신뢰하지 않도록 주의합니다.
@router.websocket("/ws/workspaces/{workspace_id}")
async def workspace_events_endpoint(websocket: WebSocket, workspace_id: int, user_id: int = 0):
    # user_id를 query param으로 받음 (쿠키는 Secure 플래그로 인해 HTTP 환경에서 전달 안 됨)
    if not user_id:
        await websocket.close(code=4001, reason="user_id required")
        return

    await workspace_event_manager.connect(websocket, workspace_id, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            # ping/pong heartbeat
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        workspace_event_manager.disconnect(websocket, workspace_id)


# 엔드포인트: DELETE /workspaces/{workspace_id} → delete_workspace.
# 주입 의존성: Depends(get_current_user_id), Depends(get_db).
# DB commit이 포함된 변경 요청입니다. 저장 전에 대상/권한을 확인하고, 실패 시 부분 저장 여부를 점검해야 합니다.
@router.delete("/workspaces/{workspace_id}")
@vectorize(search_description="Delete workspace", capture_return_value=True)
def delete_workspace(
        workspace_id: int,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if workspace.owner_id != user_id:
        raise HTTPException(status_code=403, detail="워크스페이스 소유자만 삭제할 수 있습니다.")

    db.delete(workspace)
    db.commit()
    return {"message": "워크스페이스가 삭제되었습니다."}


# 2. 프로젝트 삭제
# 엔드포인트: DELETE /projects/{project_id} → delete_project.
# 주입 의존성: Depends(get_current_user_id), Depends(get_db).
# DB commit이 포함된 변경 요청입니다. 저장 전에 대상/권한을 확인하고, 실패 시 부분 저장 여부를 점검해야 합니다.
# 연결된 클라이언트에 이벤트를 전파합니다. DB 영속화와 소켓 알림은 동일한 트랜잭션이 아닙니다.
@router.delete("/projects/{project_id}")
@vectorize(search_description="Delete project", capture_return_value=True)
async def delete_project(
        project_id: int,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 권한 체크: 워크스페이스 소유자만 삭제 가능하도록 설정 (필요시 로직 변경 가능)
    workspace = db.get(Workspace, project.workspace_id)
    if workspace.owner_id != user_id:
        raise HTTPException(status_code=403, detail="워크스페이스 소유자만 프로젝트를 삭제할 수 있습니다.")

    project_name = project.name
    workspace_id = project.workspace_id

    user = db.get(User, user_id)
    log_activity(
        db=db, user_id=user_id, workspace_id=workspace.id, action_type="DELETE",
        content=f"🗑️ '{user.name}'님이 프로젝트 '{project_name}'을(를) 삭제했습니다."
    )

    db.delete(project)
    db.commit()

    await workspace_event_manager.broadcast(workspace_id, {
        "type": "PROJECT_DELETED",
        "user_id": user_id,
        "data": {"id": project_id, "workspace_id": workspace_id}
    })

    return {"message": "프로젝트가 삭제되었습니다."}


# 3. 워크스페이스 멤버 삭제 (강퇴 또는 본인 탈퇴)
# 엔드포인트: DELETE /workspaces/{workspace_id}/members/{target_user_id} → remove_workspace_member.
# 주입 의존성: Depends(get_current_user_id), Depends(get_db).
# DB commit이 포함된 변경 요청입니다. 저장 전에 대상/권한을 확인하고, 실패 시 부분 저장 여부를 점검해야 합니다.
# 연결된 클라이언트에 이벤트를 전파합니다. DB 영속화와 소켓 알림은 동일한 트랜잭션이 아닙니다.
@router.delete("/workspaces/{workspace_id}/members/{target_user_id}")
@vectorize(search_description="Remove workspace member", capture_return_value=True)  # 👈 추가
async def remove_workspace_member(
        workspace_id: int,
        target_user_id: int,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 1. 워크스페이스 확인
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # 2. 권한 확인
    # - 소유자는 누구든 내보낼 수 있음
    # - 일반 멤버는 '자기 자신'만 나갈 수 있음 (탈퇴)
    if workspace.owner_id != user_id and user_id != target_user_id:
        raise HTTPException(status_code=403, detail="권한이 없습니다.")

    # - 소유자는 스스로 탈퇴 불가능 (워크스페이스를 삭제하거나 소유권을 넘겨야 함)
    if workspace.owner_id == target_user_id:
        raise HTTPException(status_code=400, detail="소유자는 탈퇴할 수 없습니다. 워크스페이스를 삭제해주세요.")

    # 3. 멤버 조회 및 삭제
    member = db.exec(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .where(WorkspaceMember.user_id == target_user_id)
    ).first()

    if not member:
        raise HTTPException(status_code=404, detail="해당 멤버를 찾을 수 없습니다.")

    actor = db.get(User, user_id)
    target = db.get(User, target_user_id)
    action_type = "LEAVE" if user_id == target_user_id else "KICK"
    content = f"👋 '{target.name}'님이 나갔습니다." if user_id == target_user_id else f"🚫 '{actor.name}'님이 '{target.name}'님을 내보냈습니다."

    log_activity(
        db=db, user_id=user_id, workspace_id=workspace_id, action_type=action_type,
        content=content
    )

    db.delete(member)
    db.commit()

    await workspace_event_manager.broadcast(workspace_id, {
        "type": "MEMBER_LEFT",
        "user_id": user_id,
        "data": {
            "workspace_id": workspace_id,
            "target_user_id": target_user_id,
            "target_user_name": target.name,
        }
    })

    action = "탈퇴" if user_id == target_user_id else "강퇴"
    return {"message": f"멤버가 성공적으로 {action}처리 되었습니다."}


# 엔드포인트: PATCH /workspaces/{workspace_id} → update_workspace.
# 주입 의존성: Depends(get_current_user_id), Depends(get_db).
# DB commit이 포함된 변경 요청입니다. 저장 전에 대상/권한을 확인하고, 실패 시 부분 저장 여부를 점검해야 합니다.
# 연결된 클라이언트에 이벤트를 전파합니다. DB 영속화와 소켓 알림은 동일한 트랜잭션이 아닙니다.
@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
@vectorize(search_description="Update workspace info", capture_return_value=True)
async def update_workspace(
        workspace_id: int,
        ws_data: WorkspaceUpdate,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 1. 워크스페이스 조회
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # 2. 권한 확인 (소유자만 수정 가능)
    if workspace.owner_id != user_id:
        raise HTTPException(status_code=403, detail="워크스페이스 소유자만 정보를 수정할 수 있습니다.")

    # 3. 데이터 업데이트 (입력된 값만 변경)
    if ws_data.name is not None:
        workspace.name = ws_data.name
    if ws_data.description is not None:
        workspace.description = ws_data.description

    db.add(workspace)
    db.commit()
    db.refresh(workspace)

    user = db.get(User, user_id)
    log_activity(
        db=db, user_id=user_id, workspace_id=workspace_id, action_type="UPDATE",
        content=f"⚙️ '{user.name}'님이 워크스페이스 정보를 수정했습니다."
    )

    await workspace_event_manager.broadcast(workspace_id, {
        "type": "WORKSPACE_UPDATED",
        "user_id": user_id,
        "data": {"id": workspace.id, "name": workspace.name, "description": workspace.description}
    })

    return workspace


# 2. 프로젝트 정보 수정
# 엔드포인트: PATCH /projects/{project_id} → update_project.
# 주입 의존성: Depends(get_current_user_id), Depends(get_db).
# DB commit이 포함된 변경 요청입니다. 저장 전에 대상/권한을 확인하고, 실패 시 부분 저장 여부를 점검해야 합니다.
@router.patch("/projects/{project_id}", response_model=ProjectResponse)
@vectorize(search_description="Update project info", capture_return_value=True)
def update_project(
        project_id: int,
        project_data: ProjectUpdate,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 1. 프로젝트 조회
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 2. 권한 확인 (워크스페이스 관리자만 수정 가능)
    #    (프로젝트는 별도 소유자가 없으므로, 워크스페이스 관리자 권한을 확인합니다.)
    membership = db.get(WorkspaceMember, (project.workspace_id, user_id))
    if not membership or membership.role != "admin":
        raise HTTPException(status_code=403, detail="워크스페이스 관리자만 프로젝트 정보를 수정할 수 있습니다.")

    # 3. 데이터 업데이트
    if project_data.name is not None:
        project.name = project_data.name
    if project_data.description is not None:
        project.description = project_data.description

    db.add(project)
    db.commit()
    db.refresh(project)

    user = db.get(User, user_id)
    log_activity(
        db=db, user_id=user_id, workspace_id=project.workspace_id, action_type="UPDATE",
        content=f"⚙️ '{user.name}'님이 프로젝트 '{project.name}' 정보를 수정했습니다."
    )

    return project
