"""
Post Scheduler
Background task to post scheduled content to social media platforms
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import logging

from social_media import SocialMediaManager

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/noi_social")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class PostScheduler:
    """Manages scheduled posting to social media"""
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.social_manager = SocialMediaManager()
        
    def start(self):
        """Start the scheduler"""
        # Check for posts to publish every minute
        self.scheduler.add_job(
            self.check_and_post,
            'interval',
            minutes=1,
            id='post_checker'
        )
        
        # Clean up old posts daily
        self.scheduler.add_job(
            self.cleanup_old_posts,
            'cron',
            hour=3,
            minute=0,
            id='cleanup'
        )
        
        self.scheduler.start()
        logger.info("Post scheduler started")
    
    def stop(self):
        """Stop the scheduler"""
        self.scheduler.shutdown()
        logger.info("Post scheduler stopped")
    
    def check_and_post(self):
        """Check for posts that need to be published"""
        db = SessionLocal()
        
        try:
            # Import here to avoid circular imports
            from main import ScheduledPost
            
            # Get posts scheduled for the current minute
            now = datetime.utcnow()
            current_minute = now.replace(second=0, microsecond=0)
            next_minute = current_minute + timedelta(minutes=1)
            
            pending_posts = db.query(ScheduledPost).filter(
                ScheduledPost.status == "pending",
                ScheduledPost.scheduled_time >= current_minute,
                ScheduledPost.scheduled_time < next_minute
            ).all()
            
            logger.info(f"Found {len(pending_posts)} posts to publish")
            
            for post in pending_posts:
                self.publish_post(post, db)
                
        except Exception as e:
            logger.error(f"Error checking posts: {e}")
        finally:
            db.close()
    
    def publish_post(self, post, db):
        """Publish a single post to the appropriate platform"""
        try:
            logger.info(f"Publishing post {post.id} to {post.platform}")
            
            # Prepare content
            content = post.post_content
            
            # Add affiliate links if present
            if post.affiliate_links:
                content += "\n\n" + "\n".join(post.affiliate_links)
            
            # Post to platform
            result = None
            if post.platform == "twitter":
                result = self.social_manager.post_to_twitter(
                    text=content,
                    media_urls=post.media_urls
                )
            elif post.platform == "facebook":
                result = self.social_manager.post_to_facebook(
                    text=content,
                    media_urls=post.media_urls,
                    link=post.affiliate_links[0] if post.affiliate_links else None
                )
            elif post.platform == "instagram":
                if post.media_urls:
                    result = self.social_manager.post_to_instagram(
                        text=content,
                        image_url=post.media_urls[0]
                    )
                else:
                    result = {"success": False, "error": "Instagram requires image"}
            
            # Update post status
            if result and result.get('success'):
                post.status = "posted"
                post.posted_at = datetime.utcnow()
                post.post_id = result.get('post_id')
                logger.info(f"Successfully posted {post.id}")
            else:
                post.status = "failed"
                logger.error(f"Failed to post {post.id}: {result.get('error')}")
            
            db.commit()
            
        except Exception as e:
            logger.error(f"Error publishing post {post.id}: {e}")
            post.status = "failed"
            db.commit()
    
    def cleanup_old_posts(self):
        """Clean up old posted/failed posts (older than 30 days)"""
        db = SessionLocal()
        
        try:
            from main import ScheduledPost
            
            cutoff_date = datetime.utcnow() - timedelta(days=30)
            
            deleted = db.query(ScheduledPost).filter(
                ScheduledPost.status.in_(["posted", "failed"]),
                ScheduledPost.created_at < cutoff_date
            ).delete()
            
            db.commit()
            logger.info(f"Cleaned up {deleted} old posts")
            
        except Exception as e:
            logger.error(f"Error cleaning up posts: {e}")
        finally:
            db.close()
    
    def schedule_daily_quote_posts(self):
        """
        Create scheduled posts with random quotes
        This can be called manually or on a schedule
        """
        db = SessionLocal()
        
        try:
            from main import ScheduledPost, Quote
            import random
            
            # Get random quotes
            quotes = db.query(Quote).order_by(Quote.used_count.asc()).limit(10).all()
            
            if not quotes:
                logger.warning("No quotes available for scheduling")
                return
            
            # Schedule posts for the next 7 days
            for i in range(7):
                post_time = datetime.utcnow() + timedelta(days=i+1, hours=12)  # Post at noon
                quote = random.choice(quotes)
                
                # Create post content
                content = f'"{quote.quote_text}"\n\n— {quote.author}\n\n#NOI #Wisdom'
                
                # Create scheduled post for each platform
                for platform in ['twitter', 'facebook']:
                    scheduled_post = ScheduledPost(
                        platform=platform,
                        post_content=content,
                        scheduled_time=post_time,
                        status="pending"
                    )
                    db.add(scheduled_post)
                
                # Update quote usage
                quote.used_count += 1
                quote.last_used = datetime.utcnow()
            
            db.commit()
            logger.info("Created daily quote posts for next 7 days")
            
        except Exception as e:
            logger.error(f"Error scheduling daily posts: {e}")
        finally:
            db.close()

def run_scheduler():
    """Run the scheduler as a standalone process"""
    scheduler = PostScheduler()
    scheduler.start()
    
    try:
        # Keep the scheduler running
        import time
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.stop()

if __name__ == "__main__":
    logger.info("Starting NOI Social Post Scheduler...")
    run_scheduler()