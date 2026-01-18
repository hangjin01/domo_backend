import random
import string
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, BackgroundTasks
from sqlmodel import Session, select
from datetime import datetime, timedelta
import bcrypt
from vectorwave import *

from app.database import get_db
from app.models.user import User
from app.models.session import UserSession
from app.models.verification import EmailVerification # 👈 추가
from app.schemas import UserCreate, UserLogin, UserResponse, VerificationRequest # 👈 추가
from app.utils.email import send_verification_email # 👈 추가

router = APIRouter(tags=["Authentication"])

# --- 헬퍼 함수 ---
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def generate_code(length=6):
    return ''.join(random.choices(string.digits, k=length))

# --- 1. 회원가입 (1단계: 정보 등록 & 메일 발송) ---
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
@router.post("/login")
@vectorize(search_description="User login", capture_return_value=True, replay=True) # 👈 추가
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
        secure=False,
        samesite="lax",
        max_age=60 * 60 * 24
    )

    return {"message": "로그인 성공", "user": {"email": user.email, "name": user.name}}

# --- 4. 로그아웃 API ---
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