"""
Social Media API Integrations
Handles posting to Twitter, Facebook, Instagram using official APIs
"""
import os
import tweepy
from facebook import GraphAPI
import requests
from typing import Optional, Dict, List
from datetime import datetime

class SocialMediaManager:
    """Manages posting to multiple social media platforms"""
    
    def __init__(self):
        # Twitter/X Setup (API v2)
        self.twitter_client = None
        if all([
            os.getenv('TWITTER_API_KEY'),
            os.getenv('TWITTER_API_SECRET'),
            os.getenv('TWITTER_ACCESS_TOKEN'),
            os.getenv('TWITTER_ACCESS_SECRET')
        ]):
            try:
                self.twitter_client = tweepy.Client(
                    consumer_key=os.getenv('TWITTER_API_KEY'),
                    consumer_secret=os.getenv('TWITTER_API_SECRET'),
                    access_token=os.getenv('TWITTER_ACCESS_TOKEN'),
                    access_token_secret=os.getenv('TWITTER_ACCESS_SECRET')
                )
            except Exception as e:
                print(f"Twitter client initialization failed: {e}")
        
        # Facebook/Instagram Setup
        self.facebook_token = os.getenv('FACEBOOK_ACCESS_TOKEN')
        self.facebook_page_id = os.getenv('FACEBOOK_PAGE_ID')
        self.instagram_account_id = os.getenv('INSTAGRAM_ACCOUNT_ID')
    
    def post_to_twitter(self, text: str, media_urls: Optional[List[str]] = None) -> Dict:
        """
        Post to Twitter/X
        
        Args:
            text: Tweet text (max 280 chars)
            media_urls: Optional list of image URLs to attach
            
        Returns:
            Dict with post_id and status
        """
        if not self.twitter_client:
            return {"success": False, "error": "Twitter client not configured"}
        
        try:
            # For tweets with media, you'll need to upload media first
            # This is a simplified version
            response = self.twitter_client.create_tweet(text=text)
            
            return {
                "success": True,
                "post_id": response.data['id'],
                "url": f"https://twitter.com/user/status/{response.data['id']}"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def post_to_facebook(self, text: str, media_urls: Optional[List[str]] = None, link: Optional[str] = None) -> Dict:
        """
        Post to Facebook Page
        
        Args:
            text: Post text
            media_urls: Optional list of image URLs
            link: Optional URL to share
            
        Returns:
            Dict with post_id and status
        """
        if not self.facebook_token or not self.facebook_page_id:
            return {"success": False, "error": "Facebook credentials not configured"}
        
        try:
            graph = GraphAPI(access_token=self.facebook_token)
            
            # Simple text post
            if not media_urls and not link:
                response = graph.put_object(
                    parent_object=self.facebook_page_id,
                    connection_name='feed',
                    message=text
                )
            # Post with link
            elif link:
                response = graph.put_object(
                    parent_object=self.facebook_page_id,
                    connection_name='feed',
                    message=text,
                    link=link
                )
            # Post with photo
            elif media_urls:
                # Upload first image
                response = graph.put_photo(
                    image=requests.get(media_urls[0]).content,
                    message=text
                )
            
            return {
                "success": True,
                "post_id": response['id'],
                "url": f"https://facebook.com/{response['id']}"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def post_to_instagram(self, text: str, image_url: str) -> Dict:
        """
        Post to Instagram (requires image)
        
        Args:
            text: Caption text
            image_url: URL of image to post
            
        Returns:
            Dict with post_id and status
        """
        if not self.facebook_token or not self.instagram_account_id:
            return {"success": False, "error": "Instagram credentials not configured"}
        
        try:
            # Step 1: Create media container
            url = f"https://graph.facebook.com/v18.0/{self.instagram_account_id}/media"
            params = {
                "image_url": image_url,
                "caption": text,
                "access_token": self.facebook_token
            }
            response = requests.post(url, params=params)
            container_id = response.json()['id']
            
            # Step 2: Publish the container
            publish_url = f"https://graph.facebook.com/v18.0/{self.instagram_account_id}/media_publish"
            publish_params = {
                "creation_id": container_id,
                "access_token": self.facebook_token
            }
            publish_response = requests.post(publish_url, params=publish_params)
            
            return {
                "success": True,
                "post_id": publish_response.json()['id']
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def search_twitter(self, query: str, max_results: int = 100) -> List[Dict]:
        """
        Search Twitter for recent tweets matching query
        
        Args:
            query: Search query (e.g., "Nation of Islam" OR #NOI)
            max_results: Number of results (max 100)
            
        Returns:
            List of tweet dictionaries
        """
        if not self.twitter_client:
            return []
        
        try:
            tweets = self.twitter_client.search_recent_tweets(
                query=query,
                max_results=max_results,
                tweet_fields=['created_at', 'author_id', 'public_metrics'],
                user_fields=['username', 'name', 'description', 'public_metrics']
            )
            
            results = []
            if tweets.data:
                for tweet in tweets.data:
                    results.append({
                        'tweet_id': tweet.id,
                        'text': tweet.text,
                        'created_at': tweet.created_at,
                        'author_id': tweet.author_id,
                        'metrics': tweet.public_metrics
                    })
            
            return results
        except Exception as e:
            print(f"Twitter search failed: {e}")
            return []
    
    def get_twitter_user(self, username: str) -> Optional[Dict]:
        """
        Get Twitter user information
        
        Args:
            username: Twitter username (without @)
            
        Returns:
            User information dictionary
        """
        if not self.twitter_client:
            return None
        
        try:
            user = self.twitter_client.get_user(
                username=username,
                user_fields=['description', 'created_at', 'public_metrics']
            )
            
            if user.data:
                return {
                    'id': user.data.id,
                    'username': user.data.username,
                    'name': user.data.name,
                    'description': user.data.description,
                    'followers': user.data.public_metrics['followers_count'],
                    'following': user.data.public_metrics['following_count'],
                    'created_at': user.data.created_at
                }
            return None
        except Exception as e:
            print(f"Failed to get user: {e}")
            return None
    
    def search_facebook_hashtag(self, hashtag: str) -> List[Dict]:
        """
        Search Facebook for posts with specific hashtag
        Note: Requires appropriate permissions
        
        Args:
            hashtag: Hashtag to search (without #)
            
        Returns:
            List of post dictionaries
        """
        if not self.facebook_token:
            return []
        
        # Note: This requires specific permissions and may be limited
        # You may need to use Facebook's Search API
        try:
            graph = GraphAPI(access_token=self.facebook_token)
            search_url = f"https://graph.facebook.com/v18.0/search"
            params = {
                "q": hashtag,
                "type": "post",
                "access_token": self.facebook_token
            }
            response = requests.get(search_url, params=params)
            return response.json().get('data', [])
        except Exception as e:
            print(f"Facebook search failed: {e}")
            return []

# Example usage functions
def test_posting():
    """Test posting to platforms"""
    sm = SocialMediaManager()
    
    # Test Twitter post
    result = sm.post_to_twitter("Testing NOI Social Command Center! #NOI")
    print(f"Twitter: {result}")
    
    # Test Facebook post
    result = sm.post_to_facebook("Building community with technology! #NOI", link="https://example.com")
    print(f"Facebook: {result}")

def test_search():
    """Test searching platforms"""
    sm = SocialMediaManager()
    
    # Search Twitter
    tweets = sm.search_twitter("Nation of Islam", max_results=10)
    print(f"Found {len(tweets)} tweets")
    
    # Get user info
    user = sm.get_twitter_user("example_user")
    if user:
        print(f"User: {user['name']} (@{user['username']}) - {user['followers']} followers")

if __name__ == "__main__":
    print("Social Media Manager initialized")
    print("Set environment variables to test posting and searching")