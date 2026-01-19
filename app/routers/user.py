import os
import shutil
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlmodel import Session, select

from app.database import get_db
from app.routers.workspace import get_current_user_id
from app.models.user import User
from app.schemas import UserResponse, UserUpdate
from vectorwave import vectorize  # 로그/추적용 (선택 사항)

router = APIRouter(tags=["User"])

UPLOAD_DIR = "/app/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.patch("/users/me/profile-image", response_model=UserResponse)
@vectorize(search_description="Update user profile image", capture_return_value=True)
def update_profile_image(
        file: UploadFile = File(...),
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 1. 유저 확인
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 2. 이미지 파일 검증 (간단히 확장자 체크)
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="이미지 파일만 업로드 가능합니다.")

    # 3. 파일 저장
    file_ext = os.path.splitext(file.filename)[1]
    filename = f"profile_{user_id}_{uuid.uuid4().hex[:8]}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 4. DB 업데이트 (접근 가능한 URL 경로로 저장)
    # /static/ 경로로 접근할 수 있게 저장합니다.
    image_url = f"/static/{filename}"
    user.profile_image = image_url

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@router.get("/users/me", response_model=UserResponse)
def get_my_info(
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.patch("/users/me", response_model=UserResponse)
@vectorize(search_description="Update user name", capture_return_value=True)
def update_my_info(
        user_data: UserUpdate,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user_data.name is not None:
        user.name = user_data.name

    db.add(user)
    db.commit()
    db.refresh(user)

    return user
