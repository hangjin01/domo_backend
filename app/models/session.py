import uuid
from datetime import datetime
from sqlmodel import SQLModel, Field


class UserSession(SQLModel, table=True):
    __tablename__ = "user_sessions"

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: int = Field(index=True)

    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: datetime
    ip_address: str | None = None
