from pydantic import BaseModel, EmailStr
from datetime import time as dt_time, datetime
from typing import Optional, List


# data for register
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str


# data for login
class UserLogin(BaseModel):
    email: EmailStr
    password: str


# data for response
class UserResponse(BaseModel):
    id: int
    email: EmailStr
    name: str
    is_student_verified: bool
    profile_image: Optional[str] = None


class WorkspaceCreate(BaseModel):
    name: str
    description: Optional[str] = None


class WorkspaceResponse(BaseModel):
    id: int
    name: str
    owner_id: int
    description: Optional[str] = None


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    workspace_id: int


class BoardColumnCreate(BaseModel):
    title: str
    order: Optional[int] = 0


class BoardColumnResponse(BaseModel):
    id: int
    title: str
    order: int
    project_id: int


class CardCreate(BaseModel):
    title: str
    content: Optional[str] = None
    order: Optional[int] = 0
    x: Optional[float] = 0.0
    y: Optional[float] = 0.0
    assignee_ids: List[int] = [] # 👈 여러 명의 ID를 리스트로 받음

class CardUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    column_id: Optional[int] = None
    order: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None
    assignee_ids: Optional[List[int]] = None # 👈 수정 시에도 리스트로 받음

# 2. 카드 응답 스키마 변경
class CardResponse(BaseModel):
    id: int
    title: str
    content: Optional[str] = None
    order: int
    column_id: int
    x: float
    y: float
    created_at: datetime
    updated_at: datetime

    # ✅ 담당자들의 상세 정보를 리스트로 반환
    assignees: List[UserResponse] = []


class ScheduleCreate(BaseModel):
    day_of_week: int
    start_time: dt_time
    end_time: dt_time
    description: Optional[str] = None


class ScheduleResponse(BaseModel):
    id: int
    user_id: int
    day_of_week: int
    start_time: dt_time
    end_time: dt_time
    description: Optional[str] = None


class FreeTimeSlot(BaseModel):
    day_of_week: int
    start_time: dt_time
    end_time: dt_time


class AddMemberRequest(BaseModel):
    email: EmailStr


class WorkspaceMemberResponse(BaseModel):
    user_id: int
    name: str
    email: EmailStr
    role: str  # admin 또는 member

    class Config:
        from_attributes = True


class FileVersionResponse(BaseModel):
    id: int
    version: int
    file_size: int
    created_at: datetime
    uploader_id: int


class FileResponse(BaseModel):
    id: int
    project_id: int
    filename: str
    owner_id: int
    created_at: datetime
    # 가장 최신 버전을 보여주기 위해
    latest_version: Optional[FileVersionResponse] = None


class VerificationRequest(BaseModel):
    email: EmailStr
    code: str