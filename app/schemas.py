# [파일 안내] backend/app/schemas.py
# FastAPI 입력 검증/응답 직렬화에 쓰는 DTO 모음입니다. DB 테이블 정의는 models에 별도로 있습니다.
# Create는 생성 입력, Update는 부분 변경 입력, Response는 응답 계약입니다. Optional/None과 필드 미전달의 차이는 exclude_unset 처리와 함께 읽습니다.
# PydanticField alias는 프론트 camelCase와 서버 snake_case의 접점입니다. 변경 시 HTTP·WS·프론트 매퍼를 함께 점검해야 합니다.
# 주의: CardResponse에는 현재 project_id가 없고 중복 선언 필드도 있으므로 주석만으로 API 불일치가 해결되지는 않습니다.

from pydantic import BaseModel, EmailStr
from datetime import time as dt_time, datetime
from typing import Optional, List
from pydantic import Field as PydanticField  # 👈 별칭 사용을 위해 필요


# data for register
# UserCreate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: email, password, name. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    nickname: Optional[str] = None


# data for login
# UserLogin: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: email, password. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class UserLogin(BaseModel):
    email: EmailStr
    password: str


# data for response
# UserResponse: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: id, email, name, is_student_verified. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class UserResponse(BaseModel):
    id: int
    email: EmailStr
    name: str
    nickname: Optional[str] = None
    is_student_verified: bool
    profile_image: Optional[str] = None
    class Config:
        from_attributes = True


# WorkspaceCreate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: name. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class WorkspaceCreate(BaseModel):
    name: str
    description: Optional[str] = None


# WorkspaceResponse: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: id, name, owner_id. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class WorkspaceResponse(BaseModel):
    id: int
    name: str
    owner_id: int
    description: Optional[str] = None


# ProjectCreate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: name. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


# ProjectResponse: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: id, name, workspace_id. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class ProjectResponse(BaseModel):
    id: int
    name: str
    workspace_id: int


# BoardColumnCreate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: title. Optional 허용 여부와 alias는 각 필드를 확인합니다.
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


# TransformSchema: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: scaleX, scaleY, rotation. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class TransformSchema(BaseModel):
    scaleX: float
    scaleY: float
    rotation: float


# BoardColumnResponse: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: id, title, width, height, depth, color, collapsed, order. Optional 허용 여부와 alias는 각 필드를 확인합니다.
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
# CardCreate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: title. Optional 허용 여부와 alias는 각 필드를 확인합니다.
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


# CardUpdate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: 없음. Optional 허용 여부와 alias는 각 필드를 확인합니다.
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


# ScheduleCreate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: day_of_week, start_time, end_time. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class ScheduleCreate(BaseModel):
    day_of_week: int
    start_time: dt_time
    end_time: dt_time
    description: Optional[str] = None


# ScheduleResponse: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: id, user_id, day_of_week, start_time, end_time. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class ScheduleResponse(BaseModel):
    id: int
    user_id: int
    day_of_week: int
    start_time: dt_time
    end_time: dt_time
    description: Optional[str] = None


# FreeTimeSlot: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: day_of_week, start_time, end_time. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class FreeTimeSlot(BaseModel):
    day_of_week: int
    start_time: dt_time
    end_time: dt_time


# AddMemberRequest: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: email. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class AddMemberRequest(BaseModel):
    email: EmailStr


# WorkspaceMemberResponse: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: user_id, name, email, role. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class WorkspaceMemberResponse(BaseModel):
    user_id: int
    name: str
    email: EmailStr
    role: str  # admin 또는 member

    class Config:
        from_attributes = True


# FileVersionResponse: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: id, version, file_size, created_at, uploader_id. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class FileVersionResponse(BaseModel):
    id: int
    version: int
    file_size: int
    created_at: datetime
    uploader_id: int


# FileResponse: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: id, project_id, filename, owner_id, created_at. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class FileResponse(BaseModel):
    id: int
    project_id: int
    filename: str
    owner_id: int
    created_at: datetime
    # 가장 최신 버전을 보여주기 위해
    latest_version: Optional[FileVersionResponse] = None


# CardCommentCreate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: content. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class CardCommentCreate(BaseModel):
    content: str


# CardCommentResponse: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: id, card_id, user_id, content, created_at, updated_at. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class CardCommentResponse(BaseModel):
    id: int
    card_id: int
    user_id: int
    content: str
    created_at: datetime
    updated_at: datetime

    user: Optional[UserResponse] = None  # 작성자 정보 포함


# CardResponse: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: id, title, order, column_id, card_type, x, y, created_at, updated_at. Optional 허용 여부와 alias는 각 필드를 확인합니다.
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


# VerificationRequest: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: email, code. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class VerificationRequest(BaseModel):
    email: EmailStr
    code: str


# InvitationCreate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: 없음. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class InvitationCreate(BaseModel):
    role: str = "member"
    expires_in_hours: int = 24  # 유효기간 (기본 24시간)


# 초대 링크 응답
# InvitationResponse: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: invite_link, expires_at. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class InvitationResponse(BaseModel):
    invite_link: str
    expires_at: datetime


# 초대 정보 조회 응답 (수락 전 확인용)
# InvitationInfo: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: workspace_name, inviter_name, role. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class InvitationInfo(BaseModel):
    workspace_name: str
    inviter_name: str
    role: str


# ActivityLogResponse: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: id, user_id, content, action_type, created_at. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class ActivityLogResponse(BaseModel):
    id: int
    user_id: int
    content: str
    action_type: str
    created_at: datetime


# ProjectEventCreate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: title, start_datetime, end_datetime. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class ProjectEventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    start_datetime: datetime
    end_datetime: datetime


# ProjectEventResponse: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: id, project_id, title, start_datetime, end_datetime, created_by, created_at. Optional 허용 여부와 alias는 각 필드를 확인합니다.
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
# PostCreate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: title, content. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class PostCreate(BaseModel):
    title: str
    content: str


# PostUpdate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: 없음. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class PostUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


# PostCommentCreate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: content. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class PostCommentCreate(BaseModel):
    content: str


# PostCommentResponse: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: id, post_id, user_id, content, created_at. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class PostCommentResponse(BaseModel):
    id: int
    post_id: int
    user_id: int
    content: str
    created_at: datetime
    user: Optional[UserResponse] = None  # 작성자 정보


# PostResponse: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: id, project_id, user_id, title, content, created_at, updated_at. Optional 허용 여부와 alias는 각 필드를 확인합니다.
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
# ChatMessageCreate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: content. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class ChatMessageCreate(BaseModel):
    content: str


# ChatMessageResponse: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: id, project_id, user_id, content, created_at. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class ChatMessageResponse(BaseModel):
    id: int
    project_id: int
    user_id: int
    content: str
    created_at: datetime
    user: Optional[UserResponse] = None


# WorkspaceUpdate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: 없음. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class WorkspaceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


# ProjectUpdate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: 없음. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


# UserUpdate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: 없음. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class UserUpdate(BaseModel):
    name: Optional[str] = None
    nickname: Optional[str] = None


# ScheduleUpdate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: 없음. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class ScheduleUpdate(BaseModel):
    day_of_week: Optional[int] = None
    start_time: Optional[dt_time] = None
    end_time: Optional[dt_time] = None
    description: Optional[str] = None


# ProjectEventUpdate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: 없음. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class ProjectEventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_datetime: Optional[datetime] = None
    end_datetime: Optional[datetime] = None


# 🔗 [수정] 카드 연결 생성 요청
# CardConnectionCreate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: 없음. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class CardConnectionCreate(BaseModel):
    from_card_id: int = PydanticField(alias="from")  # 프론트에서 { "from": 1, ... } 로 보냄
    to_card_id: int = PydanticField(alias="to")
    style: Optional[str] = "solid"
    shape: Optional[str] = "bezier"
    source_handle: Optional[str] = PydanticField(alias="sourceHandle", default=None)
    target_handle: Optional[str] = PydanticField(alias="targetHandle", default=None)


# 🔗 [수정] 카드 연결 응답 (프론트엔드 인터페이스와 100% 일치)
# CardConnectionResponse: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: id, style, shape. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class CardConnectionResponse(BaseModel):
    id: int
    from_card_id: int = PydanticField(serialization_alias="from")  # JSON 나갈때 "from"으로 변환
    to_card_id: int = PydanticField(serialization_alias="to")  # JSON 나갈때 "to"로 변환
    board_id: int = PydanticField(serialization_alias="boardId")  # JSON 나갈때 "boardId"로 변환
    style: str
    shape: str
    source_handle: Optional[str] = PydanticField(serialization_alias="sourceHandle", default=None)
    target_handle: Optional[str] = PydanticField(serialization_alias="targetHandle", default=None)


# TransformInput: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: 없음. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class TransformInput(BaseModel):
    scaleX: Optional[float] = 1.0
    scaleY: Optional[float] = 1.0
    rotation: Optional[float] = 0.0


# BoardColumnUpdate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: 없음. Optional 허용 여부와 alias는 각 필드를 확인합니다.
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


# CardConnectionUpdate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: 없음. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class CardConnectionUpdate(BaseModel):
    from_card_id: Optional[int] = PydanticField(alias="from", default=None)
    to_card_id: Optional[int] = PydanticField(alias="to", default=None)

    style: Optional[str] = None
    shape: Optional[str] = None

    source_handle: Optional[str] = PydanticField(alias="sourceHandle", default=None)
    target_handle: Optional[str] = PydanticField(alias="targetHandle", default=None)


# app/schemas.py

# ... (기존 코드 아래에 추가) ...

# CommunityCommentResponse: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: id, content, user_id, created_at. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class CommunityCommentResponse(BaseModel):
    id: int
    content: str
    user_id: int
    created_at: datetime
    user: Optional[UserResponse] = None


# CommunityPostResponse: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: id, title, content, user_id, created_at, updated_at. Optional 허용 여부와 alias는 각 필드를 확인합니다.
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


# CommunityCommentCreate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: content. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class CommunityCommentCreate(BaseModel):
    content: str


# CommunityPostUpdate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: 없음. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class CommunityPostUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None

# CommunityCommentUpdate: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: content. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class CommunityCommentUpdate(BaseModel):
    content: str

# CardUpdateItem: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: id. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class CardUpdateItem(CardUpdate):
    id: int

# BatchCardUpdateRequest: API 경계에서 사용하는 검증/직렬화 모델입니다.
# 기본값이 없는 선언: cards. Optional 허용 여부와 alias는 각 필드를 확인합니다.
class BatchCardUpdateRequest(BaseModel):
    cards: List[CardUpdateItem]
