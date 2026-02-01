# app/routers/file.py

import os
import uuid
import shutil
from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.encoders import jsonable_encoder  # 👈 [핵심] 직렬화 해결사 임포트
from sqlmodel import Session, select, desc

from app.database import get_db
from app.routers.workspace import get_current_user_id
from app.models.file import FileMetadata, FileVersion
from app.models.workspace import Project
from app.models.user import User
from app.schemas import FileResponse, FileVersionResponse
from app.utils.logger import log_activity
from app.utils.connection_manager import board_event_manager
from vectorwave import vectorize

router = APIRouter(tags=["Files"])

UPLOAD_DIR = "/app/uploads/files"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/projects/{project_id}/files", response_model=FileResponse)
@vectorize(search_description="Upload file to project", capture_return_value=True, replay=True)
async def upload_file(
        project_id: int,
        file: UploadFile = File(...),
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 1. 프로젝트 확인
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    user = db.get(User, user_id)

    # 2. 파일 저장
    file_ext = os.path.splitext(file.filename)[1]
    saved_filename = f"{uuid.uuid4()}{file_ext}"
    saved_path = os.path.join(UPLOAD_DIR, saved_filename)

    with open(saved_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file_size = os.path.getsize(saved_path)

    # 3. DB 메타데이터 확인 및 버전 관리
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
        db.commit()
        db.refresh(new_file)
        target_file_id = new_file.id
        existing_file = new_file

    # 4. 버전 정보 저장
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

    # 5. 응답 데이터 생성
    response_data = FileResponse(
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

    # 6. 로그 기록
    action_msg = "업로드" if current_version_num == 1 else f"새 버전(v{current_version_num}) 업데이트"
    log_activity(
        db=db, user_id=user_id, workspace_id=project.workspace_id, action_type="UPLOAD",
        content=f"💾 '{user.name}'님이 파일 '{file.filename}'을(를) {action_msg}했습니다."
    )

    # 🔥 [SSE] 파일 업로드 알림 (jsonable_encoder 적용!)
    await board_event_manager.broadcast(project_id, {
        "type": "FILE_UPLOADED",
        "user_id": user_id,
        "data": jsonable_encoder(response_data)  # 👈 여기가 핵심!
    })

    return response_data

# 📦 [신규] 다중 파일 업로드 (배치)
@router.post("/projects/{project_id}/files/batch", response_model=List[FileResponse])
@vectorize(search_description="Batch upload files", capture_return_value=True)
async def upload_files_batch(
        project_id: int,
        files: List[UploadFile] = File(...),
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    user = db.get(User, user_id)
    results = []

    for file in files:
        # A. 파일 저장
        file_ext = os.path.splitext(file.filename)[1]
        saved_filename = f"{uuid.uuid4()}{file_ext}"
        saved_path = os.path.join(UPLOAD_DIR, saved_filename)

        with open(saved_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        file_size = os.path.getsize(saved_path)

        # B. DB 처리 (단건과 동일 로직)
        existing_file = db.exec(
            select(FileMetadata)
            .where(FileMetadata.project_id == project_id)
            .where(FileMetadata.filename == file.filename)
        ).first()

        current_version_num = 1
        target_file_id = None

        if existing_file:
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

        # D. 결과 리스트 추가
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

        # E. 로그 기록
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

    # 🔥 [SSE] 배치 업로드 알림 (jsonable_encoder 적용!)
    if results:
        await board_event_manager.broadcast(project_id, {
            "type": "FILES_BATCH_UPLOADED",
            "user_id": user_id,
            "data": jsonable_encoder(results)  # 👈 여기가 핵심!
        })

    return results

@router.get("/projects/{project_id}/files", response_model=List[FileResponse])
@vectorize(search_description="List project files", capture_return_value=True)
def get_project_files(
        project_id: int,
        db: Session = Depends(get_db)
):
    files = db.exec(select(FileMetadata).where(FileMetadata.project_id == project_id)).all()

    results = []
    for f in files:
        latest_v = db.exec(
            select(FileVersion)
            .where(FileVersion.file_id == f.id)
            .order_by(desc(FileVersion.version))
        ).first()

        if latest_v:
            results.append(FileResponse(
                id=f.id,
                project_id=f.project_id,
                filename=f.filename,
                owner_id=f.owner_id,
                created_at=f.created_at,
                latest_version=FileVersionResponse(
                    id=latest_v.id,
                    version=latest_v.version,
                    file_size=latest_v.file_size,
                    created_at=latest_v.created_at,
                    uploader_id=latest_v.uploader_id
                )
            ))

    return results

@router.delete("/files/{file_id}")
@vectorize(search_description="Delete file", capture_return_value=True)
async def delete_file(
        file_id: int,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 1. 파일 메타데이터 조회
    file_meta = db.get(FileMetadata, file_id)
    if not file_meta:
        raise HTTPException(status_code=404, detail="File not found")

    project = db.get(Project, file_meta.project_id)
    filename = file_meta.filename
    project_id = file_meta.project_id

    # 2. [핵심] 연관된 버전 정보(FileVersion) 먼저 삭제
    #    부모(FileMetadata)를 지우기 전에 자식(FileVersion)을 먼저 지워야
    #    FK 제약 조건(NotNullViolation) 에러가 나지 않습니다.
    versions = db.exec(select(FileVersion).where(FileVersion.file_id == file_id)).all()

    for v in versions:
        # 실제 디스크에 있는 파일 삭제 (선택 사항)
        if os.path.exists(v.saved_path):
            try:
                os.remove(v.saved_path)
            except OSError:
                pass # 파일이 이미 없으면 무시

        # DB에서 버전 행 삭제
        db.delete(v)

    # 3. 이제 안전하게 메타데이터 삭제
    db.delete(file_meta)
    db.commit()

    # 4. 활동 로그 기록
    if project:
        user = db.get(User, user_id)
        log_activity(
            db=db, user_id=user_id, workspace_id=project.workspace_id, action_type="DELETE",
            content=f"🗑️ '{user.name}'님이 파일 '{filename}'을(를) 삭제했습니다."
        )

    # 5. [SSE] 실시간 알림 (jsonable_encoder 사용)
    #    id는 int라 괜찮지만, 확장성을 위해 encoder 사용 권장
    await board_event_manager.broadcast(project_id, {
        "type": "FILE_DELETED",
        "user_id": user_id,
        "data": {"id": file_id}
    })

    return {"message": "파일이 삭제되었습니다."}