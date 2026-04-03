import os
from sqlalchemy import create_engine, Column, Integer, BigInteger, Text, String, TIMESTAMP
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import json
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Automatically detect and recover from closed connections
    pool_recycle=300,    # Refresh connections every 5 minutes
    pool_size=10,        # Standard pool size
    max_overflow=20      # Allow additional connections if needed
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Post(Base):
    __tablename__ = "posts"
    
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(BigInteger, nullable=False)
    media_url = Column(Text, nullable=False)
    file_paths = Column(Text, nullable=False)
    public_urls = Column(Text, nullable=False)
    caption = Column(Text, nullable=True)
    post_type = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    ig_media_id = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default="now()")

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_post(chat_id: int, media_url: str, post_type: str, caption: str = "") -> Post:
    db = SessionLocal()
    try:
        post = Post(
            chat_id=chat_id,
            media_url=media_url,
            file_paths="[]",
            public_urls="[]",
            caption=caption,
            post_type=post_type,
            status="pending"
        )
        db.add(post)
        db.commit()
        db.refresh(post)
        return post
    finally:
        db.close()

def update_status(post_id: int, status: str, ig_media_id: str = None) -> None:
    db = SessionLocal()
    try:
        post = db.query(Post).filter(Post.id == post_id).first()
        if post:
            post.status = status
            if ig_media_id:
                post.ig_media_id = ig_media_id
            db.commit()
    finally:
        db.close()

def update_file_paths(post_id: int, file_paths: list, public_urls: list) -> None:
    db = SessionLocal()
    try:
        post = db.query(Post).filter(Post.id == post_id).first()
        if post:
            post.file_paths = json.dumps(file_paths)
            post.public_urls = json.dumps(public_urls)
            db.commit()
    finally:
        db.close()

def set_caption(post_id: int, caption: str) -> None:
    db = SessionLocal()
    try:
        post = db.query(Post).filter(Post.id == post_id).first()
        if post:
            post.caption = caption
            db.commit()
    finally:
        db.close()

def update_caption(post_id: int, new_caption: str) -> None:
    db = SessionLocal()
    try:
        post = db.query(Post).filter(Post.id == post_id).first()
        if post:
            post.caption = new_caption
            db.commit()
    finally:
        db.close()

def get_post(post_id: int) -> Post:
    db = SessionLocal()
    try:
        return db.query(Post).filter(Post.id == post_id).first()
    finally:
        db.close()

def delete_post(post_id: int) -> None:
    db = SessionLocal()
    try:
        post = db.query(Post).filter(Post.id == post_id).first()
        if post:
            db.delete(post)
            db.commit()
    finally:
        db.close()
