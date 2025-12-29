"""
API Testing Utility
Test your social media API connections
"""
import os
from dotenv import load_dotenv
from social_media import SocialMediaManager

load_dotenv()

def test_openai():
    """Test OpenAI connection"""
    import openai
    
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ OPENAI_API_KEY not set in .env")
        return False
    
    try:
        openai.api_key = api_key
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Say 'test successful'"}],
            max_tokens=10
        )
        print("✅ OpenAI API: Connected")
        print(f"   Response: {response.choices[0].message.content}")
        return True
    except Exception as e:
        print(f"❌ OpenAI API: Failed - {e}")
        return False

def test_twitter():
    """Test Twitter API connection"""
    sm = SocialMediaManager()
    
    if not sm.twitter_client:
        print("❌ Twitter API: Not configured (missing credentials in .env)")
        return False
    
    try:
        # Try to get authenticated user
        me = sm.twitter_client.get_me()
        if me.data:
            print(f"✅ Twitter API: Connected as @{me.data.username}")
            return True
        else:
            print("❌ Twitter API: Authentication failed")
            return False
    except Exception as e:
        print(f"❌ Twitter API: Failed - {e}")
        return False

def test_facebook():
    """Test Facebook API connection"""
    token = os.getenv('FACEBOOK_ACCESS_TOKEN')
    page_id = os.getenv('FACEBOOK_PAGE_ID')
    
    if not token or not page_id:
        print("❌ Facebook API: Not configured (missing credentials in .env)")
        return False
    
    try:
        import requests
        url = f"https://graph.facebook.com/v18.0/{page_id}"
        params = {
            'fields': 'name,followers_count',
            'access_token': token
        }
        response = requests.get(url, params=params)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Facebook API: Connected to page '{data.get('name')}'")
            print(f"   Followers: {data.get('followers_count', 'N/A')}")
            return True
        else:
            print(f"❌ Facebook API: Failed - {response.json()}")
            return False
    except Exception as e:
        print(f"❌ Facebook API: Failed - {e}")
        return False

def test_instagram():
    """Test Instagram API connection"""
    token = os.getenv('FACEBOOK_ACCESS_TOKEN')
    account_id = os.getenv('INSTAGRAM_ACCOUNT_ID')
    
    if not token or not account_id:
        print("❌ Instagram API: Not configured (missing credentials in .env)")
        return False
    
    try:
        import requests
        url = f"https://graph.facebook.com/v18.0/{account_id}"
        params = {
            'fields': 'username,followers_count',
            'access_token': token
        }
        response = requests.get(url, params=params)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Instagram API: Connected as @{data.get('username')}")
            print(f"   Followers: {data.get('followers_count', 'N/A')}")
            return True
        else:
            print(f"❌ Instagram API: Failed - {response.json()}")
            return False
    except Exception as e:
        print(f"❌ Instagram API: Failed - {e}")
        return False

def test_database():
    """Test database connection"""
    db_url = os.getenv('DATABASE_URL')
    
    if not db_url:
        print("❌ Database: DATABASE_URL not set in .env")
        return False
    
    try:
        from sqlalchemy import create_engine
        engine = create_engine(db_url)
        connection = engine.connect()
        connection.close()
        print("✅ Database: Connected")
        print(f"   URL: {db_url.split('@')[1] if '@' in db_url else 'local'}")
        return True
    except Exception as e:
        print(f"❌ Database: Failed - {e}")
        return False

def run_all_tests():
    """Run all API tests"""
    print("=" * 60)
    print("NOI Social Command Center - API Connection Tests")
    print("=" * 60)
    print()
    
    results = {
        "Database": test_database(),
        "OpenAI": test_openai(),
        "Twitter": test_twitter(),
        "Facebook": test_facebook(),
        "Instagram": test_instagram()
    }
    
    print()
    print("=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    
    passed = sum(results.values())
    total = len(results)
    
    for service, status in results.items():
        symbol = "✅" if status else "❌"
        print(f"{symbol} {service}")
    
    print()
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print()
        print("🎉 All systems operational! You're ready to go.")
    elif passed >= 2:  # Database + OpenAI at minimum
        print()
        print("⚠️  Core systems working. Social media APIs are optional.")
        print("   You can still use content management and AI features.")
    else:
        print()
        print("❌ Critical systems not working. Please check your .env file.")
    
    print()
    print("=" * 60)

if __name__ == "__main__":
    run_all_tests()