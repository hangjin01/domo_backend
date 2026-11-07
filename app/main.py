# [파일 안내] backend/app/main.py
# FastAPI 앱의 조립 지점입니다. CORS, 업로드 정적 경로, 11개 라우터와 시작/종료 수명을 설정합니다.
# 시작 시 SQLModel create_all을 실행하고 선택 설치된 VectorWave를 초기화합니다. create_all은 기존 테이블 변경을 적용하는 migration이 아닙니다.
# 주의: 현재 wildcard CORS와 /static 공개 경로는 로컬 개발 설정입니다. /의 Healthy 응답은 모든 외부 서비스의 종합 건강 검사가 아닙니다.

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.database import create_db_and_tables
import time
import asyncio
from fastapi.staticfiles import StaticFiles

#routers
from app.routers import auth, workspace, board, schedule, file, activity, user, voice, chat, post, community

from fastapi.middleware.cors import CORSMiddleware


try:
    from vectorwave import initialize_database, generate_and_register_metadata
except ImportError:
    print("⚠️ Warning: 'vectorwave' module not found. AI features will be disabled.")
    initialize_database = None
    generate_and_register_metadata = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n========== 🚀 Server Startup Process ==========", flush=True)

    # 1. PostgreSQL 테이블 생성
    print("🛠️  [Database] Checking & Creating Tables...", flush=True)
    create_db_and_tables()
    print("✅ [Database] Ready.", flush=True)

    # 2. VectorWave 연결 (재시도 로직 강화)
    if initialize_database:
        print("🌊 [VectorWave] Connecting to Weaviate...", flush=True)
        client = None
        max_retries = 15

        for i in range(max_retries):
            try:
                # 연결 시도
                client = initialize_database()

                if client:
                    print("✅ [VectorWave] Connected successfully!", flush=True)
                    print("📝 [VectorWave] Syncing function metadata...", flush=True)
                    generate_and_register_metadata()
                    break  # 성공하면 루프 탈출

            except Exception as e:
                # 에러가 나도 죽지 않고 출력함
                print(f"⚠️ [VectorWave] Connection attempt failed: {e}", flush=True)

            # 실패 시 대기 (마지막 시도가 아닐 때만)
            if i < max_retries - 1:
                print(f"⏳ [VectorWave] DB not ready. Retrying in 3s... ({i + 1}/{max_retries})", flush=True)
                await asyncio.sleep(3)

        if not client:
            print("❌ [VectorWave] Failed to connect after multiple attempts.", flush=True)
            print("   -> Weaviate 컨테이너 로그를 확인해보세요.", flush=True)

    print("===============================================\n", flush=True)
    yield
    print("\n👋 Server Shutting Down...", flush=True)


app = FastAPI(
    title="Team Project Collaboration Platform",
    description="FastAPI + VectorWave Backend",
    version="1.0.0",
    lifespan=lifespan
)

origins = [
    "http://localhost:3000",      # 프론트엔드 개발 서버
    "http://localhost:3001",      # (혹시 포트가 다를 경우 대비)
    "http://127.0.0.1:3000",
    "*"                           # 테스트용 (보안상 나중엔 특정 도메인만 허용 추천)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,        # 허용할 출처 목록
    allow_credentials=True,       # 쿠키/인증 정보 포함 허용
    allow_methods=["*"],          # 모든 HTTP 메서드(GET, POST, OPTIONS 등) 허용
    allow_headers=["*"],          # 모든 헤더 허용
)

app.mount("/static", StaticFiles(directory="/app/uploads"), name="static")

#routers
app.include_router(auth.router, prefix="/api/auth")
app.include_router(workspace.router, prefix="/api")
app.include_router(board.router, prefix="/api")
app.include_router(schedule.router, prefix="/api")
app.include_router(file.router, prefix="/api")
app.include_router(activity.router, prefix="/api")
app.include_router(user.router, prefix="/api")
app.include_router(voice.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(post.router, prefix="/api")
app.include_router(community.router, prefix="/api")

@app.get("/")
def read_root():
    return {
        "message": "Team Project API Server is Running!",
        "system": "FastAPI + PostgreSQL + VectorWave",
        "status": "Healthy"
    }
