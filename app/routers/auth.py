# [파일 안내] backend/app/routers/auth.py
# 학교 이메일 가입·인증과 쿠키 세션 로그인 요청을 처리하는 FastAPI 라우터입니다.
# 경로 접두사는 main.py의 include_router에서 붙습니다. 아래 데코레이터는 파일 내부 상대 경로이며 응답 DTO는 schemas.py에 있습니다.
# 일반 흐름은 입력 검증 → 세션/대상 확인 → DB 조회/변경 → commit/refresh → 응답/실시간 알림입니다. 모든 함수가 같은 권한 검사를 하는 것은 아닙니다.
# 현재 WS·파일 접근 등 권한 보강 과제가 남아 있습니다. Depends 존재 여부와 함수 본문의 팀원/소유자 검사를 모두 확인하세요.

import random
import string
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, BackgroundTasks
from sqlmodel import Session, select
from datetime import datetime, timedelta
import bcrypt
from app.utils.vectorwave import vectorize

from app.database import get_db
from app.models.user import User
from app.models.session import UserSession
from app.models.verification import EmailVerification # 👈 추가
from app.schemas import UserCreate, UserLogin, UserResponse, VerificationRequest # 👈 추가
from app.utils.email import send_verification_email # 👈 추가
from app.models.workspace import Workspace, WorkspaceMember # 👈 워크스페이스 모델 필요
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
router = APIRouter(tags=["Authentication"])

# --- 헬퍼 함수 ---
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def generate_code(length=6):
    return ''.join(random.choices(string.digits, k=length))

# 엔드포인트: POST /auth/setup-admin → create_admin_account.
# 주입 의존성: Depends(get_db).
# DB commit이 포함된 변경 요청입니다. 저장 전에 대상/권한을 확인하고, 실패 시 부분 저장 여부를 점검해야 합니다.
@router.post("/auth/setup-admin")
def create_admin_account(db: Session = Depends(get_db)):
    """
    [개발용 치트키] 관리자 계정을 즉시 생성하고 인증까지 완료합니다.
    - 이메일: admin@domo.com
    - 비밀번호: admin1234
    """
    admin_email = "admin@domo.com"

    # 1. 이미 존재하는지 확인
    existing_user = db.exec(select(User).where(User.email == admin_email)).first()
    if existing_user:
        return {"message": "이미 관리자 계정(admin@domo.com)이 존재합니다. 바로 로그인하세요!"}

    # 2. 관리자 유저 생성
    # ✅ [수정 1] 파일 상단에 이미 정의된 hash_password 함수 사용 (passlib 불필요)
    hashed_password = hash_password("admin1234")

    admin_user = User(
        email=admin_email,
        password_hash=hashed_password,  # ✅ [수정 2] password -> password_hash 로 변경!
        name="관리자(Admin)",
        is_student_verified=True,
        profile_image="/static/default_profile.png"
    )
    db.add(admin_user)
    db.commit()
    db.refresh(admin_user)

    # 3. 기본 워크스페이스 생성
    admin_ws = Workspace(
        name="Admin Workspace",
        description="관리자 전용 테스트 공간입니다.",
        owner_id=admin_user.id
    )
    db.add(admin_ws)
    db.commit()
    db.refresh(admin_ws)

    # 4. 워크스페이스 멤버 연결
    ws_member = WorkspaceMember(
        workspace_id=admin_ws.id,
        user_id=admin_user.id,
        role="admin"
    )
    db.add(ws_member)
    db.commit()

    return {
        "message": "🎉 관리자 계정 세팅 완료!",
        "email": admin_email,
        "password": "admin1234",
    }

# --- 1. 회원가입 (1단계: 정보 등록 & 메일 발송) ---
# 엔드포인트: POST /signup → signup.
# 주입 의존성: Depends(get_db).
# DB commit이 포함된 변경 요청입니다. 저장 전에 대상/권한을 확인하고, 실패 시 부분 저장 여부를 점검해야 합니다.
@router.post("/signup", response_model=UserResponse)
@vectorize(search_description="User signup request", capture_return_value=True, replay=True)
async def signup(
        user_data: UserCreate,
        background_tasks: BackgroundTasks, # 👈 비동기 메일 발송용
        db: Session = Depends(get_db)
):
    # 1. 이메일 중복 확인
    existing_user = db.exec(select(User).where(User.email == user_data.email)).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="이미 가입된 이메일입니다.")

    # 2. 전주대 이메일 체크 (@jj.ac.kr)
    if not user_data.email.endswith("@jj.ac.kr"):
        raise HTTPException(status_code=400, detail="전주대학교 이메일(@jj.ac.kr)만 사용 가능합니다.")

    # 3. 유저 생성 (아직 인증 안됨: is_student_verified=False)
    new_user = User(
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        name=user_data.name,
        nickname=user_data.nickname,
        is_student_verified=False # 👈 기본값 False
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 4. 인증 코드 생성 및 저장
    code = generate_code()
    verification = EmailVerification(email=user_data.email, code=code)
    db.merge(verification) # 이미 있으면 덮어쓰기 (Upsert)
    db.commit()

    # 5. 이메일 발송 (백그라운드 작업으로 처리하여 응답 지연 방지)
    background_tasks.add_task(send_verification_email, user_data.email, code)

    return new_user

# --- 2. 이메일 인증 코드 확인 (2단계) ---
# 엔드포인트: POST /verify → verify_email.
# 주입 의존성: Depends(get_db).
# DB commit이 포함된 변경 요청입니다. 저장 전에 대상/권한을 확인하고, 실패 시 부분 저장 여부를 점검해야 합니다.
@router.post("/verify")
@vectorize(search_description="Verify email code", capture_return_value=True, replay=True) # 👈 추가
def verify_email(req: VerificationRequest, db: Session = Depends(get_db)):
    # 1. 인증 코드 조회
    verification = db.get(EmailVerification, req.email)

    if not verification or verification.code != req.code:
        raise HTTPException(status_code=400, detail="인증 코드가 일치하지 않거나 만료되었습니다.")

    # 2. 유저 인증 상태 업데이트
    user = db.exec(select(User).where(User.email == req.email)).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    user.is_student_verified = True
    db.add(user)

    # 3. 사용한 인증 코드 삭제
    db.delete(verification)
    db.commit()

    return {"message": "이메일 인증이 완료되었습니다. 이제 로그인할 수 있습니다."}

# --- 3. 로그인 API (인증 여부 체크 추가) ---
# 엔드포인트: POST /login → login.
# 주입 의존성: Depends(get_db).
# DB commit이 포함된 변경 요청입니다. 저장 전에 대상/권한을 확인하고, 실패 시 부분 저장 여부를 점검해야 합니다.
@router.post("/login")
def login(response: Response, login_data: UserLogin, db: Session = Depends(get_db)):
    user = db.exec(select(User).where(User.email == login_data.email)).first()

    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 일치하지 않습니다.")

    # ✅ [추가] 이메일 인증 여부 확인
    if not user.is_student_verified:
        raise HTTPException(status_code=403, detail="이메일 인증이 완료되지 않았습니다. 메일을 확인해주세요.")

    # 세션 생성
    expires = datetime.now() + timedelta(hours=24)
    session = UserSession(user_id=user.id, expires_at=expires)

    db.add(session)
    db.commit()
    db.refresh(session)

    response.set_cookie(
        key="session_id",
        value=session.session_id,
        httponly=True,
        secure=True,          # False → True
        samesite="none",      # "lax" → "none"
        max_age=60 * 60 * 24
    )

    return {"message": "로그인 성공", "user": {"email": user.email, "name": user.name}}

# --- 4. 로그아웃 API ---
# 엔드포인트: POST /logout → logout.
# 주입 의존성: Depends(get_db).
# DB commit이 포함된 변경 요청입니다. 저장 전에 대상/권한을 확인하고, 실패 시 부분 저장 여부를 점검해야 합니다.
@router.post("/logout")
@vectorize(search_description="User logout", capture_return_value=True, replay=True) # 👈 추가
def logout(response: Response, request: Request, db: Session = Depends(get_db)):
    session_id = request.cookies.get("session_id")
    if session_id:
        session = db.get(UserSession, session_id)
        if session:
            db.delete(session)
            db.commit()

    response.delete_cookie("session_id")
    return {"message": "로그아웃 되었습니다."}
