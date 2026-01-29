import os
import shutil
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse as StreamFileResponse
from sqlmodel import Session, select, desc
from datetime import datetime

from app.database import get_db
from app.routers.workspace import get_current_user_id
from app.models.file import FileMetadata, FileVersion
from app.models.workspace import Project, WorkspaceMember
from app.schemas import FileResponse, FileVersionResponse
from typing import List
from app.utils.logger import log_activity
from app.models.workspace import Project
from app.models.user import User
from app.models.board import CardFileLink
from vectorwave import *
from app.utils.connection_manager import board_event_manager

router = APIRouter(tags=["File Management"])

UPLOAD_DIR = "/app/uploads"  # docker-compose에서 마운트한 경로

# 서버 시작 시 폴더가 없으면 생성
os.makedirs(UPLOAD_DIR, exist_ok=True)


# 1. 파일 업로드 (자동 버전 관리)
@router.post("/projects/{project_id}/files", response_model=FileResponse)
@vectorize(search_description="Upload file", capture_return_value=True, replay=True)  # 👈 추가
async def upload_file(
        project_id: int,
        file: UploadFile = File(...),
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 0. 프로젝트 권한 확인 (생략 가능하나 보안상 권장)
    # ... (WorkspaceMember 체크 로직) ...

    # 1. 실제 파일 저장 (이름 충돌 방지를 위해 UUID 사용)
    file_ext = os.path.splitext(file.filename)[1]
    saved_filename = f"{uuid.uuid4()}{file_ext}"
    saved_path = os.path.join(UPLOAD_DIR, saved_filename)

    with open(saved_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file_size = os.path.getsize(saved_path)

    # 2. 같은 이름의 파일이 있는지 확인
    existing_file = db.exec(
        select(FileMetadata)
        .where(FileMetadata.project_id == project_id)
        .where(FileMetadata.filename == file.filename)
    ).first()

    current_version_num = 1

    if existing_file:
        # 이미 존재하면: 메타데이터 업데이트 & 버전 UP
        last_version = db.exec(
            select(FileVersion)
            .where(FileVersion.file_id == existing_file.id)
            .order_by(desc(FileVersion.version))
        ).first()

        if last_version:
            current_version_num = last_version.version + 1

        target_file_id = existing_file.id
        existing_file.updated_at = datetime.now()
        db.add(existing_file)
    else:
        # 없으면: 새로 생성 (v1)
        new_file = FileMetadata(
            project_id=project_id,
            filename=file.filename,
            owner_id=user_id
        )
        db.add(new_file)
        db.commit()
        db.refresh(new_file)
        target_file_id = new_file.id
        existing_file = new_file

    # 3. 버전 정보 저장
    new_version = FileVersion(
        file_id=target_file_id,
        version=current_version_num,
        saved_path=saved_path,
        file_size=file_size,
        uploader_id=user_id
    )
    db.add(new_version)
    db.commit()
    db.refresh(new_version)

    try:
        user = db.get(User, user_id)
        project = db.get(Project, project_id)

        # v1이면 "업로드", v2 이상이면 "업데이트"
        action_msg = "업로드" if current_version_num == 1 else f"새 버전(v{current_version_num}) 업데이트"

        log_activity(
            db=db,
            user_id=user_id,
            workspace_id=project.workspace_id if project else None,
            action_type="UPLOAD",
            content=f"💾 '{user.name}'님이 '{project.name}' 프로젝트에 파일 '{file.filename}'을(를) {action_msg}했습니다."
        )
    except Exception as e:
        print(f"로그 저장 실패: {e}")  # 로그 실패가 파일 업로드를 막으면 안 되므로 예외 처리

    response = FileResponse(
        id=existing_file.id,
        project_id=existing_file.project_id,
        filename=existing_file.filename,
        owner_id=existing_file.owner_id,
        created_at=existing_file.created_at,
        latest_version=FileVersionResponse(
            id=new_version.id,
            version=new_version.version,
            file_size=new_version.file_size,
            created_at=new_version.created_at,
            uploader_id=new_version.uploader_id
        )
    )

    await board_event_manager.broadcast(project_id, {
        "type": "FILE_UPLOADED",
        "data": response.model_dump()
    })

    return response


@router.post("/projects/{project_id}/files/batch", response_model=List[FileResponse])
@vectorize(search_description="Batch upload files", capture_return_value=True)
async def upload_files_batch(
        project_id: int,
        files: List[UploadFile] = File(...),  # 👈 핵심: 파일을 리스트로 받음
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 0. 프로젝트 확인 (한 번만 조회)
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    user = db.get(User, user_id)
    results = []

    # 1. 파일 목록 순회하며 처리
    for file in files:
        # --- (기존 단건 업로드 로직 재사용) ---

        # A. 파일 저장
        file_ext = os.path.splitext(file.filename)[1]
        saved_filename = f"{uuid.uuid4()}{file_ext}"
        saved_path = os.path.join(UPLOAD_DIR, saved_filename)

        # 비동기 파일 읽기/쓰기를 위해 file.read() 등을 쓸 수도 있지만,
        # 대용량 처리를 위해 기존처럼 copyfileobj 사용 (Blocking 방지 위해 run_in_threadpool 등을 고려할 수 있으나 여기선 단순화)
        with open(saved_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        file_size = os.path.getsize(saved_path)

        # B. DB 메타데이터 확인 및 버전 관리
        existing_file = db.exec(
            select(FileMetadata)
            .where(FileMetadata.project_id == project_id)
            .where(FileMetadata.filename == file.filename)
        ).first()

        current_version_num = 1
        target_file_id = None

        if existing_file:
            # 이미 존재하면: 메타데이터 업데이트
            last_version = db.exec(
                select(FileVersion)
                .where(FileVersion.file_id == existing_file.id)
                .order_by(desc(FileVersion.version))
            ).first()

            if last_version:
                current_version_num = last_version.version + 1

            target_file_id = existing_file.id
            existing_file.updated_at = datetime.now()
            db.add(existing_file)
        else:
            # 없으면: 새로 생성
            new_file = FileMetadata(
                project_id=project_id,
                filename=file.filename,
                owner_id=user_id
            )
            db.add(new_file)
            db.commit()  # ID 생성을 위해 커밋
            db.refresh(new_file)
            target_file_id = new_file.id
            existing_file = new_file

        # C. 버전 정보 저장
        new_version = FileVersion(
            file_id=target_file_id,
            version=current_version_num,
            saved_path=saved_path,
            file_size=file_size,
            uploader_id=user_id
        )
        db.add(new_version)
        db.commit()
        db.refresh(new_version)

        # D. 결과 리스트에 추가
        results.append(FileResponse(
            id=existing_file.id,
            project_id=existing_file.project_id,
            filename=existing_file.filename,
            owner_id=existing_file.owner_id,
            created_at=existing_file.created_at,
            latest_version=FileVersionResponse(
                id=new_version.id,
                version=new_version.version,
                file_size=new_version.file_size,
                created_at=new_version.created_at,
                uploader_id=new_version.uploader_id
            )
        ))

        # E. 로그 기록 (개별 파일마다 남김)
        try:
            action_msg = "업로드" if current_version_num == 1 else f"새 버전(v{current_version_num}) 업데이트"
            log_activity(
                db=db,
                user_id=user_id,
                workspace_id=project.workspace_id,
                action_type="UPLOAD",
                content=f"💾 '{user.name}'님이 파일 '{file.filename}'을(를) {action_msg}했습니다."
            )
        except Exception:
            pass

    await board_event_manager.broadcast(project_id, {
        "type": "FILES_UPLOADED",
        "data": [r.model_dump() for r in results]
    })

    return results


@router.get("/projects/{project_id}/files", response_model=List[FileResponse])
@vectorize(search_description="List all files in project", capture_return_value=True)
def get_project_files(
        project_id: int,
        db: Session = Depends(get_db),
        user_id: int = Depends(get_current_user_id)
):
    """
    해당 프로젝트에 업로드된 모든 파일의 목록과 최신 버전 정보를 반환합니다.
    """
    # 1. 프로젝트 존재 여부 확인
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 2. 파일 메타데이터 조회 (최신순 정렬)
    files = db.exec(
        select(FileMetadata)
        .where(FileMetadata.project_id == project_id)
        .order_by(FileMetadata.created_at.desc())
    ).all()

    results = []
    for f in files:
        # 3. 각 파일의 '최신 버전' 정보 가져오기
        latest_ver = db.exec(
            select(FileVersion)
            .where(FileVersion.file_id == f.id)
            .order_by(desc(FileVersion.version))
        ).first()

        # 버전 정보가 있는 경우에만 결과에 포함
        if latest_ver:
            results.append(FileResponse(
                id=f.id,
                project_id=f.project_id,
                filename=f.filename,
                owner_id=f.owner_id,
                created_at=f.created_at,
                latest_version=FileVersionResponse(
                    id=latest_ver.id,
                    version=latest_ver.version,
                    file_size=latest_ver.file_size,
                    created_at=latest_ver.created_at,
                    uploader_id=latest_ver.uploader_id
                )
            ))

    return results


# 2. 파일 다운로드 (특정 버전)
@router.get("/files/download/{version_id}")
@vectorize(search_description="Download file version", capture_return_value=False, replay=True)
def download_file_version(version_id: int, db: Session = Depends(get_db)):
    version = db.get(FileVersion, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="파일 버전을 찾을 수 없습니다.")

    file_meta = db.get(FileMetadata, version.file_id)

    # 다운로드 시 원래 파일명으로 제공
    return StreamFileResponse(
        path=version.saved_path,
        filename=f"v{version.version}_{file_meta.filename}",
        media_type="application/octet-stream"
    )


@router.get("/files/{file_id}/versions", response_model=List[FileVersionResponse])
@vectorize(search_description="Get file version history", capture_return_value=True, replay=True)  # 👈 추가
def get_file_history(
        file_id: int,
        db: Session = Depends(get_db)
):
    # 1. 파일 메타데이터 존재 확인
    file_meta = db.get(FileMetadata, file_id)
    if not file_meta:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")

    # 2. 해당 파일의 모든 버전을 최신순(내림차순)으로 조회
    versions = db.exec(
        select(FileVersion)
        .where(FileVersion.file_id == file_id)
        .order_by(desc(FileVersion.version))
    ).all()

    return versions


@router.delete("/files/{file_id}")
@vectorize(search_description="Delete file", capture_return_value=True, replay=True)  # 👈 추가
async def delete_file(
        file_id: int,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 1. 파일 메타데이터 확인
    file_meta = db.get(FileMetadata, file_id)
    if not file_meta:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    project_id = file_meta.project_id

    # 2. 로그를 위한 정보 미리 저장 (삭제 후엔 조회 불가)
    filename = file_meta.filename
    project = db.get(Project, file_meta.project_id)
    workspace_id = project.workspace_id if project else None

    # 3. 물리적 파일 삭제 (모든 버전 반복)
    versions = db.exec(select(FileVersion).where(FileVersion.file_id == file_id)).all()
    for version in versions:
        # 실제 파일이 디스크에 있으면 삭제
        if os.path.exists(version.saved_path):
            try:
                os.remove(version.saved_path)
            except Exception as e:
                print(f"파일 삭제 실패 (ID: {version.id}): {e}")

        # DB에서 버전 정보 삭제
        db.delete(version)

    # 4. 카드와의 연결 관계(링크) 삭제
    links = db.exec(select(CardFileLink).where(CardFileLink.file_id == file_id)).all()
    for link in links:
        db.delete(link)

    # 5. 메타데이터(껍데기) 삭제
    db.delete(file_meta)
    db.commit()

    # 6. 로그 기록
    try:
        user = db.get(User, user_id)
        log_activity(
            db=db,
            user_id=user_id,
            workspace_id=workspace_id,
            action_type="DELETE",
            content=f"🗑️ '{user.name}'님이 파일 '{filename}'을(를) 영구 삭제했습니다."
        )
    except Exception as e:
        print(f"로그 저장 실패: {e}")

    await board_event_manager.broadcast(project_id, {
        "type": "FILE_DELETED",
        "data": {"id": file_id}
    })

    return {"message": "파일과 모든 버전이 삭제되었습니다."}
