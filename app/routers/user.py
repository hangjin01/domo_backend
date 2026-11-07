# [파일 안내] backend/app/routers/user.py
# 인증 사용자 정보·프로필·탈퇴 요청을 처리하는 FastAPI 라우터입니다.
# 경로 접두사는 main.py의 include_router에서 붙습니다. 아래 데코레이터는 파일 내부 상대 경로이며 응답 DTO는 schemas.py에 있습니다.
# 일반 흐름은 입력 검증 → 세션/대상 확인 → DB 조회/변경 → commit/refresh → 응답/실시간 알림입니다. 모든 함수가 같은 권한 검사를 하는 것은 아닙니다.
# 현재 WS·파일 접근 등 권한 보강 과제가 남아 있습니다. Depends 존재 여부와 함수 본문의 팀원/소유자 검사를 모두 확인하세요.

import os
import shutil
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlmodel import Session, select

from app.database import get_db
from app.routers.workspace import get_current_user_id
from app.models.user import User
from app.schemas import UserResponse, UserUpdate
from app.utils.vectorwave import vectorize
from app.utils.logger import log_activity
from datetime import datetime

router = APIRouter(tags=["User"])

UPLOAD_DIR = "/app/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# 엔드포인트: PATCH /users/me/profile-image → update_profile_image.
# 주입 의존성: Depends(get_current_user_id), Depends(get_db).
# DB commit이 포함된 변경 요청입니다. 저장 전에 대상/권한을 확인하고, 실패 시 부분 저장 여부를 점검해야 합니다.
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

    log_activity(
        db=db, user_id=user_id, workspace_id=None, action_type="UPDATE",
        content=f"🖼️ '{user.name}'님이 프로필 사진을 변경했습니다."
    )

    return user


# 엔드포인트: GET /users/me → get_my_info.
# 주입 의존성: Depends(get_current_user_id), Depends(get_db).
@router.get("/users/me", response_model=UserResponse)
def get_my_info(
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# 엔드포인트: PATCH /users/me → update_my_info.
# 주입 의존성: Depends(get_current_user_id), Depends(get_db).
# DB commit이 포함된 변경 요청입니다. 저장 전에 대상/권한을 확인하고, 실패 시 부분 저장 여부를 점검해야 합니다.
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

    if user_data.nickname is not None:
        user.nickname = user_data.nickname

    db.add(user)
    db.commit()
    db.refresh(user)

    log_activity(
        db=db, user_id=user_id, workspace_id=None, action_type="UPDATE",
        content=f"✏️ '{user.name}'님이 이름을 수정했습니다."
    )

    return user

# 엔드포인트: DELETE /users/me → withdraw_user.
# 주입 의존성: Depends(get_current_user_id), Depends(get_db).
# DB commit이 포함된 변경 요청입니다. 저장 전에 대상/권한을 확인하고, 실패 시 부분 저장 여부를 점검해야 합니다.
@router.delete("/users/me")
def withdraw_user(
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    user = db.get(User, user_id)

    # 1. 개인 정보 삭제 (선택)
    user.password_hash = ""
    user.email = f"deleted_{user.id}@anonymous.com" # 재가입 방지용

    # 2. 상태 변경 (Soft Delete)
    user.is_active = False
    user.deleted_at = datetime.now()

    db.add(user)
    db.commit()
    return {"message": "탈퇴 처리되었습니다."}
