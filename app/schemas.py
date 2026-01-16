from pydantic import BaseModel, EmailStr
from typing import Optional


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
