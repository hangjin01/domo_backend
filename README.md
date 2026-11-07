# DOMO Backend

DOMO 협업 워크스페이스의 FastAPI 백엔드입니다.
PostgreSQL·SQLModel과 쿠키 세션 인증을 사용하며, WebSocket 기반 실시간 이벤트와 선택 AI 연동 코드를 포함합니다.

프론트 저장소: [hangjin01/domo_frontend](https://github.com/hangjin01/domo_frontend)

## 로컬 실행

Docker Compose 또는 Fedora의 Podman Compose를 사용합니다.

```bash
git clone https://github.com/hangjin01/domo_backend.git
cd domo_backend
cp .env.example .env
docker compose up -d --build
```

Podman 환경에서는 마지막 명령을 `podman-compose up -d --build`로 바꿉니다.
Fedora에서 공유 라이브러리 충돌이 있는 경우에만 `env LD_LIBRARY_PATH=/usr/lib64`를 명령 앞에 붙입니다.

- API: http://localhost:9000
- Swagger: http://localhost:9000/docs
- PostgreSQL: 5432
- Weaviate: 8080 / 50051

현재 Compose의 포트는 호스트 네트워크에 공개될 수 있습니다.
기본 DB 암호·익명 Weaviate 설정을 사용하는 **개발용 구성**이므로 외부망에 그대로 배포하지 마세요.

## 환경변수

`.env.example`을 기준으로 설정하고 실제 비밀키가 담긴 `.env`는 커밋하지 않습니다.

- `DATABASE_URL`: DB 연결. Compose는 내부 `db` 서비스 주소를 직접 지정합니다.
- `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM`, `MAIL_PORT`, `MAIL_SERVER`: SMTP. 예제 값으로 실제 이메일이 발송되지는 않습니다.
- `OPENAI_API_KEY`: AI 기능을 사용할 때만 설정합니다.

VectorWave는 기본 필수 설치에서 제외했습니다.
라이브러리가 없으면 호환 데코레이터가 원래 함수를 반환하며 **AI 벡터화·추적은 수행되지 않습니다**.
Compose에 Weaviate 컨테이너가 있다고 AI 기능이 자동 활성화되는 것은 아닙니다.

## 프론트 연결

프론트 `.env.local`을 설정하고 개발 서버를 재시작합니다.

```dotenv
API_URL=http://localhost:9000
NEXT_PUBLIC_API_URL=http://localhost:9000
NEXT_PUBLIC_USE_MOCK=false
```

프론트 목 모드(`true`)와 데스크톱 앱은 서버 DB 대신 로컬 저장소를 사용합니다.
`test@gmail.com / 1234`는 프론트 데모 계정이며 이 서버에 자동 생성되지 않습니다.
최신 프론트의 금액 카드·카드 크기 저장은 아직 서버 스키마와 연동되지 않았습니다.

## 인증과 주요 기능

회원가입 → 이메일 인증 → 로그인 흐름이며 로그인 후 HttpOnly 세션 쿠키를 사용합니다.

- 사용자·워크스페이스·프로젝트·초대
- 보드·컬럼/그룹·카드·연결선
- 일정·채팅·게시판·파일·활동 기록
- 실시간 이벤트와 음성 시그널링 관련 라우터

라우터가 존재하는 것과 전체 흐름이 검증된 것은 다릅니다.
권한·파일 접근·WebSocket·관리자 초기화 경로에는 운영 전 보안 검토가 필요합니다.

## 구조

```text
app/main.py       앱 시작, 라우터와 미들웨어
app/database.py   DB 엔진과 요청별 세션
app/models/       SQLModel 테이블
app/schemas.py    요청·응답 DTO
app/routers/      HTTP·WebSocket 엔드포인트
app/services/     인증 서비스
app/utils/        이메일·연결 관리·선택 AI 호환 계층
```

주요 파일에 한국어 설명 주석을 추가했습니다. 테이블 자동 생성은 운영 스키마 마이그레이션을 대신하지 않습니다.

## 검증과 종료

```bash
python3 -m compileall -q app
docker compose logs --tail 100 backend
docker compose down
```

구문 검사는 DB·SMTP·다중 사용자 동작 검증을 대체하지 않습니다.
일반 종료 시 `down -v`를 사용하지 마세요. DB와 Weaviate 데이터는 named volume에 보존합니다.
개인 업로드·DB 덤프·인증정보는 Git에 포함하지 않습니다.
