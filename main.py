"""
NOI Social Media Command Center
A legitimate social media management and discovery platform
"""
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
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

load_dotenv()

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
DATABASE_URL = os.getenv("DATABASE_URL", "")
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

# ==================== STATIC FILES & DASHBOARD ====================

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the main dashboard"""
    return FileResponse("dashboard.html")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)