# app/routers/community.py

import os
import uuid
import shutil
from typing import List, Optional
from datetime import datetime

import json

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from sqlmodel import Session, select
from app.database import get_db
from app.models.user import User
from app.models.community import CommunityPost, CommunityComment
from app.routers.workspace import get_current_user_id
from app.schemas import (
    CommunityPostResponse,
    CommunityCommentResponse,
    CommunityCommentCreate,
    CommunityCommentUpdate
)
from app.utils.logger import log_activity
from app.utils.connection_manager import community_event_manager
from vectorwave import vectorize

router = APIRouter(tags=["Community"])

UPLOAD_DIR = "/app/uploads/community"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------------------------------------------------------
# 🔌 WebSocket 엔드포인트 (실시간 커뮤니티 이벤트)
# ---------------------------------------------------------
@router.websocket("/ws/community")
async def community_ws(websocket: WebSocket):
    await community_event_manager.connect(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        community_event_manager.disconnect(websocket)


# ---------------------------------------------------------
# 📋 게시글 목록 조회 (전체 공개)
# ---------------------------------------------------------
@router.get("/community", response_model=List[CommunityPostResponse])
@vectorize(search_description="List community posts", capture_return_value=True)
def get_community_posts(
        skip: int = 0,
        limit: int = 20,
        db: Session = Depends(get_db)
):
    posts = db.exec(
        select(CommunityPost).order_by(CommunityPost.created_at.desc()).offset(skip).limit(limit)
    ).all()

    # 응답 변환 (User 객체 포함)
    results = []
    for post in posts:
        comments_resp = [
            CommunityCommentResponse(
                id=c.id, content=c.content, user_id=c.user_id,
                user=c.user,  # 👈 작성자 정보 전체 전달 (UserResponse로 자동 변환)
                created_at=c.created_at
            ) for c in post.comments
        ]
        results.append(CommunityPostResponse(
            id=post.id, title=post.title, content=post.content, image_url=post.image_url,
            user_id=post.user_id,
            user=post.user,  # 👈 작성자 정보 전체 전달
            created_at=post.created_at, updated_at=post.updated_at,
            comments=comments_resp
        ))
    return results

# ---------------------------------------------------------
# 📝 게시글 작성 (사진 1장 포함 가능)
# ---------------------------------------------------------
@router.post("/community", response_model=CommunityPostResponse)
@vectorize(search_description="Create community post", capture_return_value=True)
async def create_community_post(
        title: str = Form(...),
        content: str = Form(...),
        file: Optional[UploadFile] = File(None),  # ✅ 사진 1장 (선택)
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 1. 이미지 저장 처리
    image_url = None
    if file:
        if not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="이미지 파일만 업로드 가능합니다.")

        file_ext = os.path.splitext(file.filename)[1]
        filename = f"{uuid.uuid4().hex}{file_ext}"
        file_path = os.path.join(UPLOAD_DIR, filename)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        image_url = f"/static/community/{filename}"

    # 2. 게시글 저장
    new_post = CommunityPost(
        title=title,
        content=content,
        image_url=image_url,
        user_id=user_id
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    # 3. 작성자 정보 조회 (응답용)
    user = db.get(User, user_id)

    # 4. 로그 기록
    log_activity(
        db=db, user_id=user_id, workspace_id=None, action_type="POST",
        content=f"📢 '{user.name}'님이 전체 게시판에 글을 남겼습니다: {title}"
    )

    # 5. 응답 반환
    response = CommunityPostResponse(
        id=new_post.id, title=new_post.title, content=new_post.content, image_url=new_post.image_url,
        user_id=new_post.user_id,
        user=user,
        created_at=new_post.created_at, updated_at=new_post.updated_at,
        comments=[]
    )

    # 6. 실시간 broadcast
    await community_event_manager.broadcast({
        "type": "POST_CREATED",
        "user_id": user_id,
        "data": jsonable_encoder(response)
    })

    return response

# ---------------------------------------------------------
# 💬 댓글 작성
# ---------------------------------------------------------
@router.post("/community/{post_id}/comments", response_model=CommunityCommentResponse)
@vectorize(search_description="Add community comment", capture_return_value=True)
async def create_community_comment(
        post_id: int,
        comment_data: CommunityCommentCreate,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    post = db.get(CommunityPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")

    new_comment = CommunityComment(
        post_id=post_id,
        user_id=user_id,
        content=comment_data.content
    )
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)

    # 작성자 정보 조회
    user = db.get(User, user_id)

    response = CommunityCommentResponse(
        id=new_comment.id, content=new_comment.content, user_id=new_comment.user_id,
        user=user,
        created_at=new_comment.created_at
    )

    # 댓글 추가 시 게시글 업데이트 이벤트 broadcast
    await community_event_manager.broadcast({
        "type": "COMMENT_CREATED",
        "user_id": user_id,
        "data": {"post_id": post_id, "comment": jsonable_encoder(response)}
    })

    return response

# ---------------------------------------------------------
# 📖 게시글 상세 조회
# ---------------------------------------------------------
@router.get("/community/{post_id}", response_model=CommunityPostResponse)
@vectorize(search_description="Get community post detail", capture_return_value=True)
def get_community_post(
        post_id: int,
        db: Session = Depends(get_db)
):
    post = db.get(CommunityPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")

    # 댓글 목록 변환
    comments_resp = [
        CommunityCommentResponse(
            id=c.id, content=c.content, user_id=c.user_id,
            user=c.user,  # 👈 User 객체 전달
            created_at=c.created_at
        ) for c in post.comments
    ]

    return CommunityPostResponse(
        id=post.id, title=post.title, content=post.content, image_url=post.image_url,
        user_id=post.user_id,
        user=post.user,  # 👈 User 객체 전달
        created_at=post.created_at, updated_at=post.updated_at,
        comments=comments_resp
    )

# ---------------------------------------------------------
# 🗑️ 게시글 삭제
# ---------------------------------------------------------
@router.delete("/community/{post_id}")
@vectorize(search_description="Delete community post", capture_return_value=True)
async def delete_community_post(
        post_id: int,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    post = db.get(CommunityPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="게시글이 없습니다.")

    if post.user_id != user_id:
        raise HTTPException(status_code=403, detail="작성자만 삭제할 수 있습니다.")

    # 이미지 파일도 삭제 (선택 사항)
    if post.image_url:
        try:
            filename = os.path.basename(post.image_url)
            file_path = os.path.join(UPLOAD_DIR, filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass # 파일 삭제 실패는 무시

    db.delete(post)
    db.commit()

    await community_event_manager.broadcast({
        "type": "POST_DELETED",
        "user_id": user_id,
        "data": {"id": post_id}
    })

    return {"message": "게시글이 삭제되었습니다."}

# ---------------------------------------------------------
# 🗑️ 댓글 삭제
# ---------------------------------------------------------
@router.delete("/community/comments/{comment_id}")
@vectorize(search_description="Delete community comment", capture_return_value=True)
async def delete_community_comment(
        comment_id: int,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 1. 댓글 조회
    comment = db.get(CommunityComment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="댓글을 찾을 수 없습니다.")

    # 2. 권한 검사 (본인 댓글인지 확인)
    if comment.user_id != user_id:
        raise HTTPException(status_code=403, detail="작성자만 삭제할 수 있습니다.")

    post_id = comment.post_id

    # 3. 삭제
    db.delete(comment)
    db.commit()

    await community_event_manager.broadcast({
        "type": "COMMENT_DELETED",
        "user_id": user_id,
        "data": {"post_id": post_id, "comment_id": comment_id}
    })

    return {"message": "댓글이 삭제되었습니다."}

# ---------------------------------------------------------
# ✏️ 게시글 수정
# ---------------------------------------------------------
@router.patch("/community/{post_id}", response_model=CommunityPostResponse)
@vectorize(search_description="Update community post", capture_return_value=True)
async def update_community_post(
        post_id: int,
        title: Optional[str] = Form(None),
        content: Optional[str] = Form(None),
        file: Optional[UploadFile] = File(None),
        remove_image: Optional[str] = Form(None),
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 1. 게시글 조회
    post = db.get(CommunityPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")

    # 2. 권한 검사 (작성자만 수정 가능)
    if post.user_id != user_id:
        raise HTTPException(status_code=403, detail="작성자만 수정할 수 있습니다.")

    # 3. 데이터 업데이트 (입력된 값만 변경)
    if title is not None:
        post.title = title
    if content is not None:
        post.content = content

    # 4. 이미지 처리
    if remove_image == "true" and post.image_url:
        # 기존 이미지 삭제
        try:
            old_filename = os.path.basename(post.image_url)
            old_path = os.path.join(UPLOAD_DIR, old_filename)
            if os.path.exists(old_path):
                os.remove(old_path)
        except Exception:
            pass
        post.image_url = None

    if file:
        if not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="이미지 파일만 업로드 가능합니다.")

        # 기존 이미지가 있으면 삭제
        if post.image_url:
            try:
                old_filename = os.path.basename(post.image_url)
                old_path = os.path.join(UPLOAD_DIR, old_filename)
                if os.path.exists(old_path):
                    os.remove(old_path)
            except Exception:
                pass

        # 새 이미지 저장
        file_ext = os.path.splitext(file.filename)[1]
        new_filename = f"{uuid.uuid4().hex}{file_ext}"
        new_path = os.path.join(UPLOAD_DIR, new_filename)
        with open(new_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        post.image_url = f"/static/community/{new_filename}"

    post.updated_at = datetime.now()

    db.add(post)
    db.commit()
    db.refresh(post)

    # 응답 형식 맞추기 (댓글 목록 포함)
    comments_resp = [
        CommunityCommentResponse(
            id=c.id, content=c.content, user_id=c.user_id,
            user=c.user,
            created_at=c.created_at
        ) for c in post.comments
    ]

    response = CommunityPostResponse(
        id=post.id, title=post.title, content=post.content, image_url=post.image_url,
        user_id=post.user_id,
        user=post.user,
        created_at=post.created_at, updated_at=post.updated_at,
        comments=comments_resp
    )

    await community_event_manager.broadcast({
        "type": "POST_UPDATED",
        "user_id": user_id,
        "data": jsonable_encoder(response)
    })

    return response

# ---------------------------------------------------------
# ✏️ 댓글 수정
# ---------------------------------------------------------
@router.patch("/community/comments/{comment_id}", response_model=CommunityCommentResponse)
@vectorize(search_description="Update community comment", capture_return_value=True)
async def update_community_comment(
        comment_id: int,
        comment_data: CommunityCommentUpdate,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 1. 댓글 조회
    comment = db.get(CommunityComment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="댓글을 찾을 수 없습니다.")

    # 2. 권한 검사
    if comment.user_id != user_id:
        raise HTTPException(status_code=403, detail="작성자만 수정할 수 있습니다.")

    # 3. 내용 수정
    comment.content = comment_data.content
    db.add(comment)
    db.commit()
    db.refresh(comment)

    response = CommunityCommentResponse(
        id=comment.id, content=comment.content, user_id=comment.user_id,
        user=comment.user,
        created_at=comment.created_at
    )

    await community_event_manager.broadcast({
        "type": "COMMENT_UPDATED",
        "user_id": user_id,
        "data": {"post_id": comment.post_id, "comment": jsonable_encoder(response)}
    })

    return response
