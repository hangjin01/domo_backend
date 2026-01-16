from sqlmodel import SQLModel, create_engine, Session

DATABASE_URL = "postgresql://user:password@db:5432/project_db"

engine = create_engine(DATABASE_URL, echo=True)

def get_db():
    with Session(engine) as session:
        yield session

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)