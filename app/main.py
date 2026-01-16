from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.database import create_db_and_tables
import time
import asyncio

#routers
from app.routers import auth


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
                    break # 성공하면 루프 탈출

            except Exception as e:
                # 에러가 나도 죽지 않고 출력함
                print(f"⚠️ [VectorWave] Connection attempt failed: {e}", flush=True)

            # 실패 시 대기 (마지막 시도가 아닐 때만)
            if i < max_retries - 1:
                print(f"⏳ [VectorWave] DB not ready. Retrying in 3s... ({i+1}/{max_retries})", flush=True)
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

#routers
app.include_router(auth.router, prefix="/api/auth")


@app.get("/")
def read_root():
    return {
        "message": "Team Project API Server is Running!",
        "system": "FastAPI + PostgreSQL + VectorWave",
        "status": "Healthy"
    }
