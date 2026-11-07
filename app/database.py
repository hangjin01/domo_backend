# [파일 안내] backend/app/database.py
# DATABASE_URL로 SQLModel 엔진을 만들고 요청 단위 Session을 제공하는 DB 경계입니다.
# get_db의 yield 동안 라우터가 세션을 사용하며 컨텍스트 종료 시 닫습니다. 데이터 변경의 commit/rollback 책임은 호출부에 있습니다.
# create_db_and_tables는 등록된 모델의 없는 테이블을 생성합니다. 운영 스키마 변경/데이터 이행은 별도 migration이 필요합니다.

import os

from sqlmodel import SQLModel, create_engine, Session

# Docker Compose에서는 `db` 서비스명을 사용하고, 로컬 실행에서는 .env의
# DATABASE_URL로 localhost 등의 접속 주소를 지정한다.
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://user:password@db:5432/project_db")

engine = create_engine(DATABASE_URL, echo=True)

def get_db():
    with Session(engine) as session:
        yield session

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
