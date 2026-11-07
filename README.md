# DOMO Backend

DOMO 협업 워크스페이스의 FastAPI 백엔드입니다.
PostgreSQL·SQLModel과 쿠키 세션 인증을 사용하며, WebSocket 기반 실시간 이벤트와 선택 AI 연동 코드를 포함합니다.

프론트 저장소: [hangjin01/domo_frontend](https://github.com/hangjin01/domo_frontend)

## 화면과 함께 보는 API 역할

아래 이미지는 프론트 저장소의 **로컬 목 모드 캡처**입니다.
사용자가 어떤 화면에서 API를 사용하게 되는지 설명하기 위한 참고 자료이며,
이 화면들이 실제 서버와 연결된 상태라는 뜻은 아닙니다.

### 보드 · 그룹 · 카드

작업을 카드로 관리하고 그룹과 연결선으로 관계를 표현합니다.
백엔드의 관련 구현은 [보드 라우터](app/routers/board.py), [보드 모델](app/models/board.py), [요청·응답 DTO](app/schemas.py)입니다.
최신 프론트의 금액·카드 크기 필드는 아직 서버 저장과 연동되지 않았습니다.

![로컬 데모 보드와 그룹 및 카드](https://raw.githubusercontent.com/hangjin01/domo_frontend/main/docs/15-board-zoom.png)

### 카드 상세와 연결선

카드 상세는 작업 내용을, 연결선 메뉴는 카드 사이의 관계를 편집하는 UI입니다.
API 변경 시 카드·연결선 DTO와 프론트 매핑을 함께 확인해야 합니다.
아래 상세 화면은 금액·크기 옵션 추가 전 캡처입니다.

| 카드 상세 | 연결선 메뉴 |
| --- | --- |
| ![카드 제목 설명 첨부 및 활동 영역](https://raw.githubusercontent.com/hangjin01/domo_frontend/main/docs/demo/screenshots/03-card-detail.png) | ![실선 점선 화살표선 메뉴](https://raw.githubusercontent.com/hangjin01/domo_frontend/main/docs/demo/screenshots/10-connection-styles.png) |

### 일정 화면

[일정 라우터](app/routers/schedule.py)와 [일정 모델](app/models/schedule.py)은 일정 도메인을 담당합니다.
프론트의 월간 달력·타임라인과 서버의 개인 시간표/공통 빈 시간 계산은 개념이 같지 않으므로
화면마다 실제 호출과 DTO를 확인해야 합니다. 아래는 일정이 비어 있는 데모 화면입니다.

![일정이 없는 월간 달력](https://raw.githubusercontent.com/hangjin01/domo_frontend/main/docs/demo/screenshots/04-calendar.png)

### 채팅 · 게시판

[채팅 라우터](app/routers/chat.py)는 채팅 관련 요청을,
[커뮤니티 라우터](app/routers/community.py)와 [게시글 라우터](app/routers/post.py)는 커뮤니티·게시글 관련 요청을 담당합니다.
실시간 연결 관리는 [connection_manager.py](app/utils/connection_manager.py)를 함께 확인합니다.

| 채팅 입력 화면 | 게시판 목록 |
| --- | --- |
| ![메시지가 없는 로컬 채팅 화면](https://raw.githubusercontent.com/hangjin01/domo_frontend/main/docs/demo/screenshots/06-chat.png) | ![데모 공지 및 게시글 목록](https://raw.githubusercontent.com/hangjin01/domo_frontend/main/docs/demo/screenshots/07-community.png) |

이 캡처는 로컬 저장 기반입니다. 서버 모드의 인증·권한·다중 사용자 이벤트 전달은 별도 검증이 필요합니다.
금액·테마·데스크톱 등 전체 화면 소개는 [프론트 기능 갤러리](https://github.com/hangjin01/domo_frontend#화면으로-보는-기능)를 참고하세요.

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
