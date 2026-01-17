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

router = APIRouter(tags=["File Management"])

UPLOAD_DIR = "/app/uploads"  # docker-compose에서 마운트한 경로

# 서버 시작 시 폴더가 없으면 생성
os.makedirs(UPLOAD_DIR, exist_ok=True)


# 1. 파일 업로드 (자동 버전 관리)
@router.post("/projects/{project_id}/files", response_model=FileResponse)
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

    # 응답 생성
    return FileResponse(
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


# 2. 파일 다운로드 (특정 버전)
@router.get("/files/download/{version_id}")
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
