"""
NOI Social Media Command Center
A legitimate social media management and discovery platform
"""
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, JSON, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timedelta
from typing import List, Optional
import os
from dotenv import load_dotenv
import openai
from pydantic import BaseModel
import json
from pathlib import Path
import hashlib
import uuid
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Progress tracking for real-time updates
import asyncio
from collections import defaultdict
from typing import AsyncGenerator
import time

# Global progress tracker
progress_tracker = defaultdict(lambda: {
    "status": "idle",
    "progress": 0,
    "message": "",
    "current_step": "",
    "total_steps": 0,
    "completed_steps": 0
})


def process_file_background(
    task_id: str,
    file_path: str,
    content_type: str,
    title: str,
    source: str,
    num_quotes: int
):
    """Background task for file processing with progress updates"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    # Use DATABASE_URL from environment directly
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        logger.error("DATABASE_URL not found in environment")
        progress_tracker[task_id].update({
            "status": "failed",
            "message": "Database configuration error"
        })
        return
    
    # Create new DB session for background task
    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        # Update: Starting processing
        progress_tracker[task_id].update({
            "status": "processing",
            "progress": 25,
            "message": "Starting transcription...",
            "current_step": "transcribe",
            "completed_steps": 1,
            "total_steps": 5
        })
        
        time.sleep(0.5)  # Give frontend time to connect
        
        # Process the file
        result = content_processor.process_file(
            file_path=file_path,
            file_type=content_type,
            source=source,
            num_quotes=num_quotes,
            upload_to_s3=True,
            task_id=task_id  # Pass task_id for progress updates
        )
        
        if not result['success']:
            progress_tracker[task_id].update({
                "status": "failed",
                "progress": 0,
                "message": result['error']
            })
            db.close()
            return
        
        # Update: Quote extraction complete
        progress_tracker[task_id].update({
            "progress": 80,
            "message": f"Extracted {len(result['quotes'])} quotes, saving to database...",
            "completed_steps": 4,
            "current_step": "saving"
        })
        
        # Save content to DB
        db_content = Content(
            title=title,
            content_type=content_type,
            file_path=result.get('s3_url') or file_path,
            transcription=result['transcription'],
            extracted_quotes=result['quotes'],
            source=source
        )
        db.add(db_content)
        db.commit()
        db.refresh(db_content)
        
        # Save quotes to DB
        saved_quotes = []
        for quote_data in result['quotes']:
            quote = Quote(
                quote_text=quote_data['quote_text'],
                author=quote_data.get('author', source or 'Unknown'),
                category=quote_data.get('category', 'wisdom'),
                content_id=db_content.id,
                ai_generated=True
            )
            db.add(quote)
            saved_quotes.append(quote)
        
        db.commit()
        
        logger.info(f"✅ Successfully processed {title}: {len(saved_quotes)} quotes extracted")
        
        # Mark as complete
        progress_tracker[task_id].update({
            "status": "complete",
            "progress": 100,
            "message": f"✅ Complete! Extracted {len(saved_quotes)} quotes",
            "completed_steps": 5,
            "current_step": "done",
            "quotes_count": len(saved_quotes),
            "content_id": db_content.id
        })
        
    except Exception as e:
        logger.error(f"Background processing failed: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        progress_tracker[task_id].update({
            "status": "failed",
            "progress": 0,
            "message": str(e)
        })
    finally:
        db.close()

# Initialize FastAPI
app = FastAPI(title="NOI Social Command Center")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/noi_social")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# OpenAI setup
openai.api_key = os.getenv("OPENAI_API_KEY")

# ==================== MODELS ====================

class Content(Base):
    """Uploaded content library"""
    __tablename__ = "content"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255))
    content_type = Column(String(50))  # video, audio, text, image
    file_path = Column(String(500))
    transcription = Column(Text, nullable=True)
    extracted_quotes = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    tags = Column(JSON, nullable=True)
    source = Column(String(255), nullable=True)  # Minister Farrakhan, Elijah Muhammad, etc.

class Quote(Base):
    """Generated quotes for posting"""
    __tablename__ = "quotes"
    
    id = Column(Integer, primary_key=True, index=True)
    quote_text = Column(Text)
    author = Column(String(255))
    category = Column(String(100))  # wisdom, faith, unity, empowerment, etc.
    content_id = Column(Integer, nullable=True)  # Reference to source content
    used_count = Column(Integer, default=0)
    last_used = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    ai_generated = Column(Boolean, default=False)

class ScheduledPost(Base):
    """Scheduled social media posts"""
    __tablename__ = "scheduled_posts"
    
    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(50))  # twitter, facebook, instagram
    post_content = Column(Text)
    media_urls = Column(JSON, nullable=True)
    affiliate_links = Column(JSON, nullable=True)
    scheduled_time = Column(DateTime)
    status = Column(String(50), default="pending")  # pending, posted, failed
    posted_at = Column(DateTime, nullable=True)
    post_id = Column(String(255), nullable=True)  # Platform's post ID
    engagement = Column(JSON, nullable=True)  # likes, shares, comments
    created_at = Column(DateTime, default=datetime.utcnow)

class DiscoveredProfile(Base):
    """Profiles discovered through research"""
    __tablename__ = "discovered_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(50))
    username = Column(String(255))
    profile_url = Column(String(500))
    display_name = Column(String(255), nullable=True)
    bio = Column(Text, nullable=True)
    follower_count = Column(Integer, nullable=True)
    is_member = Column(Boolean, default=False)  # Determined by manual review
    engagement_score = Column(Float, nullable=True)
    recent_posts = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    contact_status = Column(String(50), default="discovered")  # discovered, contacted, responded, member
    discovered_at = Column(DateTime, default=datetime.utcnow)


class CommunityTweet(Base):
    """NOI-related tweets discovered for community engagement"""
    __tablename__ = "community_tweets"
    
    id = Column(Integer, primary_key=True, index=True)
    tweet_id = Column(String(255), unique=True, index=True)
    author_username = Column(String(255))
    author_name = Column(String(255))
    author_id = Column(String(255))
    tweet_text = Column(Text)
    tweet_url = Column(String(500))
    created_at_twitter = Column(DateTime)
    
    # Engagement metrics from Twitter
    like_count = Column(Integer, default=0)
    retweet_count = Column(Integer, default=0)
    reply_count = Column(Integer, default=0)
    
    # Our engagement tracking
    we_liked = Column(Boolean, default=False)
    we_retweeted = Column(Boolean, default=False)
    we_replied = Column(Boolean, default=False)
    we_followed = Column(Boolean, default=False)
    
    # Engagement timestamps
    liked_at = Column(DateTime, nullable=True)
    retweeted_at = Column(DateTime, nullable=True)
    replied_at = Column(DateTime, nullable=True)
    followed_at = Column(DateTime, nullable=True)
    
    # Metadata
    search_query = Column(String(500))
    sentiment = Column(String(50), default="positive")  # positive, neutral, negative
    discovered_at = Column(DateTime, default=datetime.utcnow)
    our_reply_text = Column(Text, nullable=True)
    last_activity = Column(DateTime, nullable=True)
    tags = Column(JSON, nullable=True)

class AffiliateLink(Base):
    """NOI affiliate links"""
    __tablename__ = "affiliate_links"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255))
    url = Column(String(500))
    category = Column(String(100))  # books, events, products
    click_count = Column(Integer, default=0)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Analytics(Base):
    """Analytics and engagement tracking"""
    __tablename__ = "analytics"
    
    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(50))
    metric_type = Column(String(100))  # followers, engagement_rate, reach, etc.
    value = Column(Float)
    date = Column(DateTime, default=datetime.utcnow)
    extra_data = Column(JSON, nullable=True)  # Renamed from 'metadata' (reserved by SQLAlchemy)

# Create all tables
Base.metadata.create_all(bind=engine)

# ==================== DEPENDENCIES ====================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==================== PYDANTIC MODELS ====================

class QuoteCreate(BaseModel):
    quote_text: str
    author: str
    category: str
    content_id: Optional[int] = None

class PostCreate(BaseModel):
    platform: str
    post_content: str
    media_urls: Optional[List[str]] = None
    affiliate_links: Optional[List[str]] = None
    scheduled_time: datetime

class ProfileNote(BaseModel):
    profile_id: int
    notes: str
    contact_status: Optional[str] = None

class ContentAnalysis(BaseModel):
    content: str
    num_quotes: int = 5

from content_processor import ContentProcessor

# Initialize content processor
content_processor = ContentProcessor()

# ==================== PROGRESS TRACKING ====================

async def progress_stream(task_id: str) -> AsyncGenerator[str, None]:
    """Stream progress updates via Server-Sent Events"""
    while True:
        progress = progress_tracker[task_id]
        
        # Send progress update
        yield f"data: {json.dumps(progress)}\n\n"
        
        # Stop streaming if complete or failed
        if progress["status"] in ["complete", "failed"]:
            break
        
        await asyncio.sleep(0.5)  # Update every 500ms

@app.get("/api/progress/{task_id}")
async def get_progress(task_id: str):
    """Stream real-time progress updates"""
    return StreamingResponse(
        progress_stream(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

# ==================== CONTENT MANAGEMENT ====================

@app.post("/api/content/upload")
async def upload_content(
    file: UploadFile = File(...),
    title: str = Form(...),
    content_type: str = Form(...),
    source: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Upload media content (video, audio, text)"""
    
    # Create upload directory
    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)
    
    # Generate unique filename
    file_ext = file.filename.split('.')[-1]
    unique_filename = f"{uuid.uuid4()}.{file_ext}"
    file_path = upload_dir / unique_filename
    
    # Save file
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    # Create database record
    db_content = Content(
        title=title,
        content_type=content_type,
        file_path=str(file_path),
        source=source
    )
    db.add(db_content)
    db.commit()
    db.refresh(db_content)
    
    return {
        "id": db_content.id,
        "message": "Content uploaded successfully",
        "file_path": str(file_path)
    }

@app.post("/api/content/process-and-extract")
async def process_and_extract_quotes(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(...),
    content_type: str = Form(...),
    source: Optional[str] = Form(None),
    num_quotes: int = Form(10),
    db: Session = Depends(get_db)
):
    """
    AUTOMATED PIPELINE: Upload file → Transcribe → Extract quotes → Save all to DB
    Returns task_id immediately for progress tracking
    """
    
    # Generate task ID for progress tracking
    task_id = str(uuid.uuid4())
    
    # Create upload directory
    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)
    
    # Generate unique filename with robust extension handling
    original_filename = file.filename or "uploaded_file"
    logger.info(f"📤 Processing upload: {original_filename}")
    
    # Get file extension safely
    if '.' in original_filename:
        file_ext = original_filename.rsplit('.', 1)[-1].lower()
        if not file_ext or len(file_ext) > 10 or not file_ext.isalnum():
            if content_type == 'audio':
                file_ext = 'mp3'
            elif content_type == 'video':
                file_ext = 'mp4'
            else:
                file_ext = 'txt'
    else:
        if content_type == 'audio':
            file_ext = 'mp3'
        elif content_type == 'video':
            file_ext = 'mp4'
        else:
            file_ext = 'txt'
    
    unique_filename = f"{uuid.uuid4()}.{file_ext}"
    file_path = upload_dir / unique_filename
    
    logger.info(f"📁 Saving as: {unique_filename}")
    
    # Save file
    file_content = await file.read()
    with open(file_path, "wb") as f:
        f.write(file_content)
    
    # Verify file was written successfully
    file_size = os.path.getsize(file_path)
    logger.info(f"📊 File saved: {file_size:,} bytes")
    
    if file_size == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty or upload failed")
    
    # Initialize progress
    progress_tracker[task_id] = {
        "status": "uploaded",
        "progress": 10,
        "message": f"File uploaded: {file_size / 1024 / 1024:.1f} MB",
        "current_step": "upload",
        "total_steps": 5,
        "completed_steps": 1,
        "task_id": task_id
    }
    
    # Start background processing
    background_tasks.add_task(
        process_file_background,
        task_id=task_id,
        file_path=str(file_path),
        content_type=content_type,
        title=title,
        source=source,
        num_quotes=num_quotes
    )
    
    # Return task_id immediately so frontend can start SSE
    return {
        "success": True,
        "task_id": task_id,
        "message": "Processing started",
        "file_size": file_size
    }


@app.post("/api/content/batch-process")
async def batch_process_files(
    files: List[UploadFile] = File(...),
    sources: Optional[str] = Form(None),  # Comma-separated sources
    num_quotes_per_file: int = Form(10),
    db: Session = Depends(get_db)
):
    """
    BATCH PROCESSING: Upload multiple files at once and process them all
    Perfect for processing hours of content quickly!
    """
    
    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)
    
    # Parse sources (comma-separated)
    source_list = sources.split(',') if sources else []
    
    # Save all files first
    saved_files = []
    for i, file in enumerate(files):
        file_ext = file.filename.split('.')[-1]
        unique_filename = f"{uuid.uuid4()}.{file_ext}"
        file_path = upload_dir / unique_filename
        
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Determine file type from extension
        if file_ext.lower() in ['mp3', 'wav', 'm4a', 'aac']:
            file_type = 'audio'
        elif file_ext.lower() in ['mp4', 'mov', 'avi', 'mkv']:
            file_type = 'video'
        else:
            file_type = 'text'
        
        source = source_list[i] if i < len(source_list) else None
        
        saved_files.append((str(file_path), file_type, source, file.filename))
    
    # Batch process all files
    try:
        batch_results = []
        total_quotes = 0
        
        for file_path, file_type, source, original_name in saved_files:
            result = content_processor.process_file(
                file_path=file_path,
                file_type=file_type,
                source=source,
                num_quotes=num_quotes_per_file,
                upload_to_s3=True
            )
            
            if result['success']:
                # Save to database
                db_content = Content(
                    title=Path(original_name).stem,
                    content_type=file_type,
                    file_path=result.get('s3_url') or file_path,
                    transcription=result['transcription'],
                    extracted_quotes=result['quotes'],
                    source=source
                )
                db.add(db_content)
                db.commit()
                db.refresh(db_content)
                
                # Save quotes
                for quote_data in result['quotes']:
                    quote = Quote(
                        quote_text=quote_data['quote_text'],
                        author=quote_data.get('author', source or 'Unknown'),
                        category=quote_data.get('category', 'wisdom'),
                        content_id=db_content.id,
                        ai_generated=True
                    )
                    db.add(quote)
                
                db.commit()
                total_quotes += len(result['quotes'])
            
            batch_results.append({
                "filename": original_name,
                "success": result['success'],
                "quotes_extracted": len(result['quotes']) if result['success'] else 0,
                "error": result.get('error')
            })
        
        return {
            "success": True,
            "files_processed": len(files),
            "total_quotes_extracted": total_quotes,
            "results": batch_results,
            "message": f"✅ Batch processed {len(files)} files: {total_quotes} total quotes extracted"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch processing failed: {str(e)}")


@app.post("/api/content/transcribe/{content_id}")
async def transcribe_content(content_id: int, db: Session = Depends(get_db)):
    """Transcribe audio/video using OpenAI Whisper"""
    
    content = db.query(Content).filter(Content.id == content_id).first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    
    try:
        # Use OpenAI Whisper for transcription
        with open(content.file_path, "rb") as audio_file:
            transcript = openai.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )
        
        content.transcription = transcript
        db.commit()
        
        return {
            "id": content.id,
            "transcription": transcript
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")

@app.post("/api/content/analyze")
async def analyze_content(data: ContentAnalysis, db: Session = Depends(get_db)):
    """Use OpenAI to extract quotes from text/transcription"""
    
    try:
        response = openai.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {
                    "role": "system",
                    "content": """You are analyzing Nation of Islam content to extract powerful, 
                    meaningful quotes. Focus on wisdom, empowerment, unity, faith, and self-improvement. 
                    Return quotes in JSON format with: quote_text, author (if mentioned), and category."""
                },
                {
                    "role": "user",
                    "content": f"""Extract {data.num_quotes} powerful quotes from this content. 
                    Focus on themes of wisdom, empowerment, faith, unity, and self-improvement.
                    
                    Content: {data.content}
                    
                    Return as JSON array: [{{"quote_text": "...", "author": "...", "category": "..."}}]"""
                }
            ],
            response_format={"type": "json_object"}
        )
        
        quotes_data = json.loads(response.choices[0].message.content)
        
        # Save quotes to database
        saved_quotes = []
        for quote_data in quotes_data.get("quotes", []):
            quote = Quote(
                quote_text=quote_data.get("quote_text"),
                author=quote_data.get("author", "Unknown"),
                category=quote_data.get("category", "wisdom"),
                ai_generated=True
            )
            db.add(quote)
            saved_quotes.append(quote)
        
        db.commit()
        
        return {
            "message": f"Extracted {len(saved_quotes)} quotes",
            "quotes": quotes_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.get("/api/quotes")
async def get_quotes(
    category: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """Get quotes from library"""
    query = db.query(Quote)
    
    if category:
        query = query.filter(Quote.category == category)
    
    quotes = query.order_by(Quote.created_at.desc()).limit(limit).all()
    
    return quotes

@app.post("/api/quotes")
async def create_quote(quote: QuoteCreate, db: Session = Depends(get_db)):
    """Manually add a quote"""
    db_quote = Quote(**quote.dict())
    db.add(db_quote)
    db.commit()
    db.refresh(db_quote)
    return db_quote

# ==================== SOCIAL MEDIA POSTING ====================

@app.post("/api/posts/post-now")
async def post_now(
    platform: str = Form(...),
    content: str = Form(...),
    db: Session = Depends(get_db)
):
    """Post immediately to social media platform"""
    
    try:
        if platform == "twitter":
            # Twitter posting
            import tweepy
            
            api_key = os.getenv("TWITTER_API_KEY")
            api_secret = os.getenv("TWITTER_API_SECRET")
            access_token = os.getenv("TWITTER_ACCESS_TOKEN")
            access_secret = os.getenv("TWITTER_ACCESS_SECRET")
            
            if not all([api_key, api_secret, access_token, access_secret]):
                raise HTTPException(status_code=500, detail="Twitter credentials not configured")
            
            client = tweepy.Client(
                consumer_key=api_key,
                consumer_secret=api_secret,
                access_token=access_token,
                access_token_secret=access_secret
            )
            
            # Post tweet
            response = client.create_tweet(text=content)
            
            logger.info(f"✅ Posted to Twitter: {response.data['id']}")
            
            return {
                "success": True,
                "platform": "twitter",
                "post_id": str(response.data['id']),
                "message": "Posted to Twitter successfully!",
                "url": f"https://twitter.com/i/web/status/{response.data['id']}"
            }
            
        elif platform == "facebook":
            # Facebook posting
            import facebook
            
            access_token = os.getenv("FACEBOOK_ACCESS_TOKEN")
            page_id = os.getenv("FACEBOOK_PAGE_ID")
            
            if not access_token:
                raise HTTPException(
                    status_code=500, 
                    detail="Facebook access token not configured. Please add FACEBOOK_ACCESS_TOKEN to Railway variables."
                )
            
            if not page_id:
                raise HTTPException(
                    status_code=500,
                    detail="Facebook Page ID not configured. Please add FACEBOOK_PAGE_ID to Railway variables."
                )
            
            # Initialize Facebook Graph API
            graph = facebook.GraphAPI(access_token)
            
            # Post to Facebook Page
            response = graph.put_object(
                parent_object=page_id,
                connection_name="feed",
                message=content
            )
            
            logger.info(f"✅ Posted to Facebook: {response['id']}")
            
            return {
                "success": True,
                "platform": "facebook",
                "post_id": response['id'],
                "message": "Posted to Facebook successfully!",
                "url": f"https://facebook.com/{response['id']}"
            }
            
        else:
            raise HTTPException(status_code=400, detail=f"Platform '{platform}' not supported yet")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to post to {platform}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to post: {str(e)}")


@app.post("/api/posts/schedule")
async def schedule_post(post: PostCreate, db: Session = Depends(get_db)):
    """Schedule a post to social media"""
    
    db_post = ScheduledPost(**post.dict())
    db.add(db_post)
    db.commit()
    db.refresh(db_post)
    
    return {
        "id": db_post.id,
        "message": "Post scheduled successfully",
        "scheduled_time": db_post.scheduled_time
    }

@app.get("/api/posts/scheduled")
async def get_scheduled_posts(
    platform: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get scheduled posts"""
    query = db.query(ScheduledPost)
    
    if platform:
        query = query.filter(ScheduledPost.platform == platform)
    if status:
        query = query.filter(ScheduledPost.status == status)
    
    posts = query.order_by(ScheduledPost.scheduled_time.asc()).all()
    return posts

@app.post("/api/posts/generate")
async def generate_post_content(
    theme: str = Form(...),
    include_quote: bool = Form(True),
    include_affiliate: bool = Form(False),
    db: Session = Depends(get_db)
):
    """Use AI to generate post content"""
    
    try:
        # Get a random quote if requested
        quote_text = ""
        if include_quote:
            quote = db.query(Quote).order_by(Quote.used_count.asc()).first()
            if quote:
                quote_text = f'"{quote.quote_text}" - {quote.author}'
                quote.used_count += 1
                quote.last_used = datetime.utcnow()
                db.commit()
        
        # Generate post
        response = openai.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {
                    "role": "system",
                    "content": """You are a social media content creator for the Nation of Islam. 
                    Create engaging, respectful posts that inspire, educate, and build community. 
                    Keep posts under 280 characters for Twitter compatibility."""
                },
                {
                    "role": "user",
                    "content": f"""Create a social media post about: {theme}
                    
                    {'Include this quote: ' + quote_text if quote_text else ''}
                    
                    Make it inspiring and shareable."""
                }
            ]
        )
        
        post_content = response.choices[0].message.content
        
        return {
            "content": post_content,
            "quote_used": quote_text
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")

# ==================== DISCOVERY & RESEARCH ====================

@app.post("/api/discovery/search")
async def search_profiles(
    platform: str = Form(...),
    keywords: str = Form(...),
    max_results: int = Form(50),
    db: Session = Depends(get_db)
):
    """Search for profiles using platform APIs (placeholder for actual API integration)"""
    
    # NOTE: This is a placeholder. You'll need to implement actual API calls
    # based on which platforms you want to use. Each requires OAuth setup.
    
    return {
        "message": "Search initiated",
        "platform": platform,
        "keywords": keywords,
        "note": "Implement actual API integration for: Twitter API v2, Instagram Graph API, Facebook Graph API"
    }

@app.post("/api/discovery/save-profile")
async def save_discovered_profile(
    platform: str = Form(...),
    username: str = Form(...),
    profile_url: str = Form(...),
    display_name: Optional[str] = Form(None),
    bio: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Save a discovered profile for manual review"""
    
    # Check if profile already exists
    existing = db.query(DiscoveredProfile).filter(
        DiscoveredProfile.platform == platform,
        DiscoveredProfile.username == username
    ).first()
    
    if existing:
        return {"message": "Profile already in database", "id": existing.id}
    
    profile = DiscoveredProfile(
        platform=platform,
        username=username,
        profile_url=profile_url,
        display_name=display_name,
        bio=bio
    )
    
    db.add(profile)
    db.commit()
    db.refresh(profile)
    
    return {
        "id": profile.id,
        "message": "Profile saved successfully"
    }

@app.get("/api/discovery/profiles")
async def get_discovered_profiles(
    platform: Optional[str] = None,
    contact_status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get discovered profiles"""
    query = db.query(DiscoveredProfile)
    
    if platform:
        query = query.filter(DiscoveredProfile.platform == platform)
    if contact_status:
        query = query.filter(DiscoveredProfile.contact_status == contact_status)
    
    profiles = query.order_by(DiscoveredProfile.discovered_at.desc()).limit(limit).all()
    
    return profiles

@app.post("/api/discovery/update-profile")
async def update_profile_notes(note: ProfileNote, db: Session = Depends(get_db)):
    """Update notes and contact status for a profile"""
    
    profile = db.query(DiscoveredProfile).filter(
        DiscoveredProfile.id == note.profile_id
    ).first()
    
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    profile.notes = note.notes
    if note.contact_status:
        profile.contact_status = note.contact_status
    
    db.commit()
    
    return {"message": "Profile updated successfully"}

# ==================== AFFILIATE LINKS ====================

@app.post("/api/affiliates")
async def create_affiliate_link(
    name: str = Form(...),
    url: str = Form(...),
    category: str = Form(...),
    db: Session = Depends(get_db)
):
    """Add an affiliate link"""
    
    link = AffiliateLink(
        name=name,
        url=url,
        category=category
    )
    
    db.add(link)
    db.commit()
    db.refresh(link)
    
    return link

@app.get("/api/affiliates")
async def get_affiliate_links(
    category: Optional[str] = None,
    active: bool = True,
    db: Session = Depends(get_db)
):
    """Get affiliate links"""
    query = db.query(AffiliateLink).filter(AffiliateLink.active == active)
    
    if category:
        query = query.filter(AffiliateLink.category == category)
    
    links = query.all()
    return links

# ==================== ANALYTICS ====================

@app.get("/api/analytics/overview")
async def get_analytics_overview(db: Session = Depends(get_db)):
    """Get overview analytics"""
    
    # Count stats
    total_quotes = db.query(Quote).count()
    total_scheduled = db.query(ScheduledPost).filter(
        ScheduledPost.status == "pending"
    ).count()
    total_profiles = db.query(DiscoveredProfile).count()
    total_content = db.query(Content).count()
    
    # Recent activity
    recent_posts = db.query(ScheduledPost).filter(
        ScheduledPost.status == "posted"
    ).order_by(ScheduledPost.posted_at.desc()).limit(5).all()
    
    return {
        "total_quotes": total_quotes,
        "scheduled_posts": total_scheduled,
        "discovered_profiles": total_profiles,
        "content_library": total_content,
        "recent_posts": len(recent_posts)
    }


# ==================== COMMUNITY FINDER ====================

@app.post("/api/community/add-manual")
async def add_tweet_manually(
    tweet_url: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Manually add a tweet to community finder
    For users without elevated Twitter API access
    """
    import re
    
    # Extract tweet ID from URL
    # Formats: twitter.com/username/status/123456 or x.com/username/status/123456
    match = re.search(r'/status/(\d+)', tweet_url)
    if not match:
        raise HTTPException(status_code=400, detail="Invalid Twitter URL. Must be in format: https://twitter.com/username/status/123456")
    
    tweet_id = match.group(1)
    
    # Check if already exists
    existing = db.query(CommunityTweet).filter(
        CommunityTweet.tweet_id == tweet_id
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="This tweet is already in your community list!")
    
    # Try to fetch tweet details with Twitter API
    try:
        import tweepy
        
        api_key = os.getenv("TWITTER_API_KEY")
        api_secret = os.getenv("TWITTER_API_SECRET")
        access_token = os.getenv("TWITTER_ACCESS_TOKEN")
        access_secret = os.getenv("TWITTER_ACCESS_SECRET")
        
        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret
        )
        
        # Fetch tweet details
        tweet = client.get_tweet(
            id=tweet_id,
            tweet_fields=['created_at', 'public_metrics', 'author_id'],
            expansions=['author_id'],
            user_fields=['username', 'name']
        )
        
        if not tweet.data:
            raise HTTPException(status_code=404, detail="Tweet not found or is private")
        
        # Get author info
        author = tweet.includes['users'][0] if tweet.includes and 'users' in tweet.includes else None
        if not author:
            raise HTTPException(status_code=404, detail="Could not fetch author information")
        
        # Save to database
        community_tweet = CommunityTweet(
            tweet_id=tweet_id,
            author_username=author.username,
            author_name=author.name,
            author_id=str(tweet.data.author_id),
            tweet_text=tweet.data.text,
            tweet_url=tweet_url,
            created_at_twitter=tweet.data.created_at,
            like_count=tweet.data.public_metrics.get('like_count', 0),
            retweet_count=tweet.data.public_metrics.get('retweet_count', 0),
            reply_count=tweet.data.public_metrics.get('reply_count', 0),
            search_query="manual_add",
            sentiment="positive"
        )
        
        db.add(community_tweet)
        db.commit()
        
        logger.info(f"✅ Manually added tweet from @{author.username}")
        
        return {
            "success": True,
            "message": f"Added tweet from @{author.username}!"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add tweet: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add tweet: {str(e)}")


@app.post("/api/community/search")
async def search_noi_tweets(db: Session = Depends(get_db)):
    """Search Twitter for NOI-related content"""
    import tweepy
    
    # Twitter API setup
    api_key = os.getenv("TWITTER_API_KEY")
    api_secret = os.getenv("TWITTER_API_SECRET")
    access_token = os.getenv("TWITTER_ACCESS_TOKEN")
    access_secret = os.getenv("TWITTER_ACCESS_SECRET")
    
    if not all([api_key, api_secret, access_token, access_secret]):
        raise HTTPException(status_code=500, detail="Twitter API credentials not configured")
    
    try:
        # Try v2 API first (requires Basic/Pro tier - $100/month)
        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
            wait_on_rate_limit=True
        )
        
        # Search queries for positive NOI content
        search_queries = [
            '("Nation of Islam" OR #NOI OR "Minister Farrakhan") (wisdom OR truth OR powerful OR inspiring) -hate -controversial lang:en',
            '#MinisterFarrakhan (knowledge OR unity OR empowerment) -hate lang:en',
            '"Nation of Islam" (education OR self-reliance OR community) -hate lang:en'
        ]
        
        new_tweets_count = 0
        
        for query in search_queries:
            try:
                # Try v2 API search
                tweets = client.search_recent_tweets(
                    query=query,
                    max_results=20,
                    tweet_fields=['created_at', 'public_metrics', 'author_id'],
                    expansions=['author_id'],
                    user_fields=['username', 'name']
                )
                
                if not tweets.data:
                    continue
                
                # Create user lookup
                users = {user.id: user for user in tweets.includes['users']} if tweets.includes else {}
                
                for tweet in tweets.data:
                    # Check if we already have this tweet
                    existing = db.query(CommunityTweet).filter(
                        CommunityTweet.tweet_id == str(tweet.id)
                    ).first()
                    
                    if existing:
                        continue
                    
                    # Get author info
                    author = users.get(tweet.author_id)
                    if not author:
                        continue
                    
                    # Simple sentiment filter - exclude tweets with negative keywords
                    negative_keywords = ['hate', 'controversial', 'attack', 'against', 'anti']
                    if any(keyword in tweet.text.lower() for keyword in negative_keywords):
                        continue
                    
                    # Save new tweet
                    community_tweet = CommunityTweet(
                        tweet_id=str(tweet.id),
                        author_username=author.username,
                        author_name=author.name,
                        author_id=str(tweet.author_id),
                        tweet_text=tweet.text,
                        tweet_url=f"https://twitter.com/{author.username}/status/{tweet.id}",
                        created_at_twitter=tweet.created_at,
                        like_count=tweet.public_metrics.get('like_count', 0),
                        retweet_count=tweet.public_metrics.get('retweet_count', 0),
                        reply_count=tweet.public_metrics.get('reply_count', 0),
                        search_query=query[:200],
                        sentiment="positive"
                    )
                    
                    db.add(community_tweet)
                    new_tweets_count += 1
                
            except tweepy.errors.Forbidden as e:
                # v2 API not available - provide helpful message
                logger.warning(f"Twitter v2 API not available: {e}")
                raise HTTPException(
                    status_code=403,
                    detail="Twitter API search requires elevated access. Your current API tier (Free/Essential) doesn't support automated search. Please use Manual Search feature instead, or upgrade to Basic tier ($100/month) at https://developer.twitter.com/en/portal/products"
                )
            except tweepy.errors.Unauthorized as e:
                logger.error(f"Twitter auth failed: {e}")
                raise HTTPException(
                    status_code=401,
                    detail="Twitter API authentication failed. Please verify your API credentials in Railway are correct and that your Twitter app has Read permissions enabled."
                )
        
        db.commit()
        
        logger.info(f"✅ Found {new_tweets_count} new NOI tweets")
        
        return {
            "success": True,
            "new_tweets": new_tweets_count,
            "message": f"Discovered {new_tweets_count} new NOI-related tweets"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Twitter search failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500, 
            detail=f"Search failed: {str(e)}. Your Twitter API tier may not support automated search. Try the Manual Search feature instead."
        )


@app.get("/api/community/tweets")
async def get_community_tweets(
    limit: int = 20,
    skip: int = 0,
    engaged_only: bool = False,
    db: Session = Depends(get_db)
):
    """Get discovered NOI tweets"""
    
    query = db.query(CommunityTweet)
    
    if engaged_only:
        query = query.filter(
            (CommunityTweet.we_liked == True) |
            (CommunityTweet.we_retweeted == True) |
            (CommunityTweet.we_replied == True)
        )
    else:
        # Show non-engaged tweets first
        query = query.filter(
            CommunityTweet.we_liked == False,
            CommunityTweet.we_retweeted == False,
            CommunityTweet.we_replied == False
        )
    
    tweets = query.order_by(CommunityTweet.created_at_twitter.desc()).offset(skip).limit(limit).all()
    
    return [
        {
            "id": tweet.id,
            "tweet_id": tweet.tweet_id,
            "author_username": tweet.author_username,
            "author_name": tweet.author_name,
            "tweet_text": tweet.tweet_text,
            "tweet_url": tweet.tweet_url,
            "created_at": tweet.created_at_twitter.isoformat() if tweet.created_at_twitter else None,
            "like_count": tweet.like_count,
            "retweet_count": tweet.retweet_count,
            "reply_count": tweet.reply_count,
            "we_liked": tweet.we_liked,
            "we_retweeted": tweet.we_retweeted,
            "we_replied": tweet.we_replied,
            "we_followed": tweet.we_followed,
            "our_reply_text": tweet.our_reply_text
        }
        for tweet in tweets
    ]


@app.post("/api/community/engage/{tweet_db_id}")
async def engage_with_tweet(
    tweet_db_id: int,
    action: str = Form(...),  # 'like', 'retweet', 'reply', 'follow'
    reply_text: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Engage with a community tweet"""
    import tweepy
    
    # Get tweet from database
    tweet = db.query(CommunityTweet).filter(CommunityTweet.id == tweet_db_id).first()
    if not tweet:
        raise HTTPException(status_code=404, detail="Tweet not found")
    
    # Twitter API setup
    api_key = os.getenv("TWITTER_API_KEY")
    api_secret = os.getenv("TWITTER_API_SECRET")
    access_token = os.getenv("TWITTER_ACCESS_TOKEN")
    access_secret = os.getenv("TWITTER_ACCESS_SECRET")
    
    try:
        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret
        )
        
        if action == "like":
            client.like(tweet.tweet_id)
            tweet.we_liked = True
            tweet.liked_at = datetime.utcnow()
            message = "Tweet liked!"
            
        elif action == "retweet":
            client.retweet(tweet.tweet_id)
            tweet.we_retweeted = True
            tweet.retweeted_at = datetime.utcnow()
            message = "Tweet retweeted!"
            
        elif action == "reply":
            if not reply_text:
                raise HTTPException(status_code=400, detail="Reply text required")
            client.create_tweet(text=reply_text, in_reply_to_tweet_id=tweet.tweet_id)
            tweet.we_replied = True
            tweet.replied_at = datetime.utcnow()
            tweet.our_reply_text = reply_text
            message = "Reply posted!"
            
        elif action == "follow":
            client.follow_user(tweet.author_id)
            tweet.we_followed = True
            tweet.followed_at = datetime.utcnow()
            message = f"Followed @{tweet.author_username}!"
            
        else:
            raise HTTPException(status_code=400, detail="Invalid action")
        
        db.commit()
        
        logger.info(f"✅ {action} - @{tweet.author_username}")
        
        return {
            "success": True,
            "action": action,
            "message": message
        }
        
    except Exception as e:
        logger.error(f"Engagement failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to {action}: {str(e)}")


@app.get("/api/community/stats")
async def get_community_stats(db: Session = Depends(get_db)):
    """Get community engagement statistics"""
    
    total_discovered = db.query(CommunityTweet).count()
    total_liked = db.query(CommunityTweet).filter(CommunityTweet.we_liked == True).count()
    total_retweeted = db.query(CommunityTweet).filter(CommunityTweet.we_retweeted == True).count()
    total_replied = db.query(CommunityTweet).filter(CommunityTweet.we_replied == True).count()
    total_followed = db.query(CommunityTweet).filter(CommunityTweet.we_followed == True).count()
    
    # New this week
    week_ago = datetime.utcnow() - timedelta(days=7)
    new_this_week = db.query(CommunityTweet).filter(
        CommunityTweet.discovered_at >= week_ago
    ).count()
    
    return {
        "total_discovered": total_discovered,
        "total_engaged": total_liked + total_retweeted + total_replied,
        "total_liked": total_liked,
        "total_retweeted": total_retweeted,
        "total_replied": total_replied,
        "total_followed": total_followed,
        "new_this_week": new_this_week
    }


# ==================== STATIC FILES & DASHBOARD ====================

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the main dashboard"""
    return FileResponse("dashboard.html")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)