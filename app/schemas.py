from pydantic import BaseModel, EmailStr
from datetime import time as dt_time, datetime
from typing import Optional, List
from pydantic import Field as PydanticField  # 👈 별칭 사용을 위해 필요


# data for register
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    nickname: Optional[str] = None


# data for login
class UserLogin(BaseModel):
    email: EmailStr
    password: str


# data for response
class UserResponse(BaseModel):
    id: int
    email: EmailStr
    name: str
    nickname: Optional[str] = None
    is_student_verified: bool
    profile_image: Optional[str] = None
    class Config:
        from_attributes = True


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

    # 프론트엔드 변수명(camelCase) -> 백엔드 변수명(snake_case) 매핑
    local_x: float = PydanticField(alias="localX", default=0.0)
    local_y: float = PydanticField(alias="localY", default=0.0)
    width: float = 300.0
    height: float = 500.0

    parent_id: Optional[int] = PydanticField(alias="parentId", default=None)
    depth: int = 0

    # UI 속성
    color: Optional[str] = "#ffffff"
    collapsed: bool = False
    order: int = 0


class TransformSchema(BaseModel):
    scaleX: float
    scaleY: float
    rotation: float


class BoardColumnResponse(BaseModel):
    id: int
    title: str

    # 백엔드 데이터 -> 프론트엔드 JSON 키 이름 변경
    local_x: float = PydanticField(serialization_alias="localX")
    local_y: float = PydanticField(serialization_alias="localY")
    width: float
    height: float

    parent_id: Optional[int] = PydanticField(serialization_alias="parentId")
    depth: int

    color: Optional[str]
    collapsed: bool
    order: int
    project_id: int = PydanticField(serialization_alias="boardId")  # project_id -> boardId

    # Transform 객체 조립 (DB 필드 3개 -> 객체 1개)
    # Pydantic v2 computed_field를 쓰거나, 아래처럼 별도 필드로 정의 후 router에서 조립
    transform: Optional[TransformSchema] = None


#todo orders 필드는 추후 라벨로 처리
class CardCreate(BaseModel):
    title: str
    content: Optional[str] = None
    column_id: Optional[int] = None
    order: Optional[int] = 0
    x: Optional[float] = 0.0
    y: Optional[float] = 0.0
    assignee_ids: List[int] = []
    start_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    card_type: str = "task"


class CardUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    column_id: Optional[int] = None
    order: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None
    assignee_ids: Optional[List[int]] = None
    start_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    card_type: str = "task"


# 2. 카드 응답 스키마 변경


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


class CardCommentCreate(BaseModel):
    content: str


class CardCommentResponse(BaseModel):
    id: int
    card_id: int
    user_id: int
    content: str
    created_at: datetime
    updated_at: datetime

    user: Optional[UserResponse] = None  # 작성자 정보 포함


class CardResponse(BaseModel):
    id: int
    title: str
    content: Optional[str] = None
    order: int
    column_id: int
    card_type: str
    x: float
    y: float
    created_at: datetime
    updated_at: datetime
    column_id: Optional[int] = None
    assignees: List[UserResponse] = []
    files: List[FileResponse] = []
    start_date: Optional[datetime] = None
    due_date: Optional[datetime] = None


class VerificationRequest(BaseModel):
    email: EmailStr
    code: str


class InvitationCreate(BaseModel):
    role: str = "member"
    expires_in_hours: int = 24  # 유효기간 (기본 24시간)


# 초대 링크 응답
class InvitationResponse(BaseModel):
    invite_link: str
    expires_at: datetime


# 초대 정보 조회 응답 (수락 전 확인용)
class InvitationInfo(BaseModel):
    workspace_name: str
    inviter_name: str
    role: str


class ActivityLogResponse(BaseModel):
    id: int
    user_id: int
    content: str
    action_type: str
    created_at: datetime


class ProjectEventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    start_datetime: datetime
    end_datetime: datetime


class ProjectEventResponse(BaseModel):
    id: int
    project_id: int
    title: str
    description: Optional[str] = None
    start_datetime: datetime
    end_datetime: datetime
    created_by: int
    created_at: datetime


# [게시판 관련 스키마]
class PostCreate(BaseModel):
    title: str
    content: str


class PostUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


class PostCommentCreate(BaseModel):
    content: str


class PostCommentResponse(BaseModel):
    id: int
    post_id: int
    user_id: int
    content: str
    created_at: datetime
    user: Optional[UserResponse] = None  # 작성자 정보


class PostResponse(BaseModel):
    id: int
    project_id: int
    user_id: int
    title: str
    content: str
    created_at: datetime
    updated_at: datetime
    user: Optional[UserResponse] = None  # 작성자 정보
    # 목록 조회 시에는 댓글 수만 보여주는 등의 최적화가 필요할 수 있음
    comments: List[PostCommentResponse] = []


# [채팅 관련 스키마]
class ChatMessageCreate(BaseModel):
    content: str


class ChatMessageResponse(BaseModel):
    id: int
    project_id: int
    user_id: int
    content: str
    created_at: datetime
    user: Optional[UserResponse] = None


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    nickname: Optional[str] = None


class ScheduleUpdate(BaseModel):
    day_of_week: Optional[int] = None
    start_time: Optional[dt_time] = None
    end_time: Optional[dt_time] = None
    description: Optional[str] = None


class ProjectEventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_datetime: Optional[datetime] = None
    end_datetime: Optional[datetime] = None


# 🔗 [수정] 카드 연결 생성 요청
class CardConnectionCreate(BaseModel):
    from_card_id: int = PydanticField(alias="from")  # 프론트에서 { "from": 1, ... } 로 보냄
    to_card_id: int = PydanticField(alias="to")
    style: Optional[str] = "solid"
    shape: Optional[str] = "bezier"
    source_handle: Optional[str] = PydanticField(alias="sourceHandle", default=None)
    target_handle: Optional[str] = PydanticField(alias="targetHandle", default=None)


# 🔗 [수정] 카드 연결 응답 (프론트엔드 인터페이스와 100% 일치)
class CardConnectionResponse(BaseModel):
    id: int
    from_card_id: int = PydanticField(serialization_alias="from")  # JSON 나갈때 "from"으로 변환
    to_card_id: int = PydanticField(serialization_alias="to")  # JSON 나갈때 "to"로 변환
    board_id: int = PydanticField(serialization_alias="boardId")  # JSON 나갈때 "boardId"로 변환
    style: str
    shape: str
    source_handle: Optional[str] = PydanticField(serialization_alias="sourceHandle", default=None)
    target_handle: Optional[str] = PydanticField(serialization_alias="targetHandle", default=None)


class TransformInput(BaseModel):
    scaleX: Optional[float] = 1.0
    scaleY: Optional[float] = 1.0
    rotation: Optional[float] = 0.0


class BoardColumnUpdate(BaseModel):
    title: Optional[str] = None

    # 위치 & 크기
    local_x: Optional[float] = PydanticField(alias="localX", default=None)
    local_y: Optional[float] = PydanticField(alias="localY", default=None)
    width: Optional[float] = None
    height: Optional[float] = None

    # 계층 구조
    parent_id: Optional[int] = PydanticField(alias="parentId", default=None)
    depth: Optional[int] = None

    # 스타일
    color: Optional[str] = None
    collapsed: Optional[bool] = None
    order: Optional[int] = None

    # 변환 (프론트엔드 { transform: { ... } } 구조 대응)
    transform: Optional[TransformInput] = None


class CardConnectionUpdate(BaseModel):
    from_card_id: Optional[int] = PydanticField(alias="from", default=None)
    to_card_id: Optional[int] = PydanticField(alias="to", default=None)

    style: Optional[str] = None
    shape: Optional[str] = None

    source_handle: Optional[str] = PydanticField(alias="sourceHandle", default=None)
    target_handle: Optional[str] = PydanticField(alias="targetHandle", default=None)


# app/schemas.py

# ... (기존 코드 아래에 추가) ...

class CommunityCommentResponse(BaseModel):
    id: int
    content: str
    user_id: int
    created_at: datetime
    user: Optional[UserResponse] = None


class CommunityPostResponse(BaseModel):
    id: int
    title: str
    content: str
    image_url: Optional[str] = None
    user_id: int
    created_at: datetime
    updated_at: datetime
    comments: List[CommunityCommentResponse] = []  # 댓글 목록 포함
    user: Optional[UserResponse] = None


class CommunityCommentCreate(BaseModel):
    content: str


class CommunityPostUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None

class CommunityCommentUpdate(BaseModel):
    content: str
