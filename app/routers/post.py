from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlmodel import Session, select
from typing import List
from vectorwave import vectorize
from datetime import datetime
from app.database import get_db
from app.routers.workspace import get_current_user_id
from app.models.post import Post, PostComment
from app.models.user import User
from app.schemas import PostCreate, PostUpdate, PostResponse, PostCommentCreate, PostCommentResponse
from app.utils.logger import log_activity
from app.models.workspace import Project
from app.utils.connection_manager import board_event_manager

router = APIRouter(tags=["Project Board"])


# 1. 게시글 목록 조회
@router.get("/projects/{project_id}/posts", response_model=List[PostResponse])
@vectorize(search_description="List project posts", capture_return_value=True) # 👈 추가
def get_project_posts(project_id: int, db: Session = Depends(get_db)):
    posts = db.exec(
        select(Post).where(Post.project_id == project_id).order_by(Post.created_at.desc())
    ).all()
    return posts


# 2. 게시글 작성
@router.post("/projects/{project_id}/posts", response_model=PostResponse)
@vectorize(search_description="Create board post", capture_return_value=True)
async def create_post(
        project_id: int,
        post_data: PostCreate,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    new_post = Post(project_id=project_id, user_id=user_id, **post_data.model_dump())
    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    user = db.get(User, user_id)
    project = db.get(Project, project_id)
    log_activity(
        db=db, user_id=user_id, workspace_id=project.workspace_id, action_type="POST",
        content=f"📝 '{user.name}'님이 프로젝트 '{project.name}'에 새 글 '{new_post.title}'을(를) 올렸습니다."
    )

    await board_event_manager.broadcast(project_id, {
        "type": "POST_CREATED",
        "user_id": user_id,
        "data": jsonable_encoder(new_post)
    })

    return new_post


# 3. 게시글 상세 조회
@router.get("/posts/{post_id}", response_model=PostResponse)
@vectorize(search_description="Get post detail", capture_return_value=True)
def get_post(post_id: int, db: Session = Depends(get_db)):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


# 4. 게시글 삭제
@router.delete("/posts/{post_id}")
@vectorize(search_description="Delete post", capture_return_value=True)
async def delete_post(post_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.user_id != user_id:
        raise HTTPException(status_code=403, detail="작성자만 삭제할 수 있습니다.")

    user = db.get(User, user_id)
    project = db.get(Project, post.project_id)
    project_id = post.project_id
    log_activity(
        db=db, user_id=user_id, workspace_id=project.workspace_id, action_type="POST",
        content=f"🗑️ '{user.name}'님이 글 '{post.title}'을(를) 삭제했습니다."
    )

    db.delete(post)
    db.commit()

    await board_event_manager.broadcast(project_id, {
        "type": "POST_DELETED",
        "user_id": user_id,
        "data": {"id": post_id}
    })

    return {"message": "게시글이 삭제되었습니다."}


@router.post("/posts/{post_id}/comments", response_model=PostCommentResponse)
@vectorize(search_description="Create post comment", capture_return_value=True)
async def create_post_comment(
        post_id: int,
        comment_data: PostCommentCreate,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    comment = PostComment(post_id=post_id, user_id=user_id, content=comment_data.content)
    db.add(comment)
    db.commit()
    db.refresh(comment)

    user = db.get(User, user_id)
    post = db.get(Post, post_id)
    project = db.get(Project, post.project_id)
    log_activity(
        db=db, user_id=user_id, workspace_id=project.workspace_id, action_type="COMMENT",
        content=f"💬 '{user.name}'님이 글 '{post.title}'에 댓글을 남겼습니다."
    )

    await board_event_manager.broadcast(post.project_id, {
        "type": "POST_COMMENT_CREATED",
        "user_id": user_id,
        "data": {"post_id": post_id, "comment": jsonable_encoder(comment)}
    })

    return comment


@router.delete("/posts/comments/{comment_id}")
@vectorize(search_description="Delete post comment", capture_return_value=True)
async def delete_post_comment(
        comment_id: int,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    comment = db.get(PostComment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    if comment.user_id != user_id:
        raise HTTPException(status_code=403, detail="작성자만 삭제할 수 있습니다.")

    post = db.get(Post, comment.post_id)
    post_id = comment.post_id

    db.delete(comment)
    db.commit()

    if post:
        await board_event_manager.broadcast(post.project_id, {
            "type": "POST_COMMENT_DELETED",
            "user_id": user_id,
            "data": {"post_id": post_id, "comment_id": comment_id}
        })

    return {"message": "댓글이 삭제되었습니다."}

@router.patch("/posts/{post_id}", response_model=PostResponse)
@vectorize(search_description="Update post", capture_return_value=True)
async def update_post(
        post_id: int,
        post_data: PostUpdate,
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # 1. 게시글 조회
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # 2. 권한 확인 (작성자만 수정 가능)
    if post.user_id != user_id:
        raise HTTPException(status_code=403, detail="작성자만 수정할 수 있습니다.")

    # 3. 데이터 업데이트
    if post_data.title is not None:
        post.title = post_data.title
    if post_data.content is not None:
        post.content = post_data.content

    # 수정 시간 갱신
    post.updated_at = datetime.now()

    db.add(post)
    db.commit()
    db.refresh(post)

    user = db.get(User, user_id)
    project = db.get(Project, post.project_id)
    log_activity(
        db=db, user_id=user_id, workspace_id=project.workspace_id, action_type="POST",
        content=f"✏️ '{user.name}'님이 글 '{post.title}'을(를) 수정했습니다."
    )

    await board_event_manager.broadcast(post.project_id, {
        "type": "POST_UPDATED",
        "user_id": user_id,
        "data": jsonable_encoder(post)
    })

    return post
