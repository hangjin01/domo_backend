# [파일 안내] backend/app/utils/email.py
# SMTP 설정과 인증 메일 발송을 모읍니다. 인증 코드의 저장/만료 판단은 인증 라우터의 책임입니다.
# 환경변수는 로컬 placeholder일 수 있습니다. 함수 존재/서버 기동만으로 실제 메일 발송이 보장되지 않으며 비밀번호/코드를 로그에 남기지 않습니다.

import os
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr

# 환경 변수에서 설정 가져오기 (없으면 기본값 또는 에러)
conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME", "your_email@gmail.com"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD", "your_app_password"),
    MAIL_FROM=os.getenv("MAIL_FROM", "your_email@gmail.com"),
    MAIL_PORT=int(os.getenv("MAIL_PORT", 587)),
    MAIL_SERVER=os.getenv("MAIL_SERVER", "smtp.gmail.com"),
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)

async def send_verification_email(email: EmailStr, code: str):
    """인증 번호 이메일 발송"""

    html = f"""
    <h3>Domo 협업 플랫폼 회원가입 인증</h3>
    <p>아래 인증 코드를 입력하여 회원가입을 완료해주세요.</p>
    <h1>{code}</h1>
    <p>이 코드는 3분간 유효합니다.</p>
    """

    message = MessageSchema(
        subject="[Domo] 회원가입 인증 코드",
        recipients=[email],
        body=html,
        subtype=MessageType.html
    )

    fm = FastMail(conf)
    await fm.send_message(message)
