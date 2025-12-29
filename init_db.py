"""
Database Initialization Script
Run this to set up your database tables
"""
from main import Base, engine
from sqlalchemy import inspect

def init_database():
    """Initialize database tables"""
    
    # Check if tables already exist
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    if existing_tables:
        print(f"Found {len(existing_tables)} existing tables:")
        for table in existing_tables:
            print(f"  - {table}")
        
        response = input("\nDo you want to recreate all tables? This will DELETE ALL DATA! (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted. Database unchanged.")
            return
        
        print("Dropping all existing tables...")
        Base.metadata.drop_all(bind=engine)
    
    # Create all tables
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    
    print("\n✅ Database initialized successfully!")
    print("\nTables created:")
    print("  - content")
    print("  - quotes")
    print("  - scheduled_posts")
    print("  - discovered_profiles")
    print("  - affiliate_links")
    print("  - analytics")
    
    print("\n🚀 You can now run the application:")
    print("   python main.py")

def add_sample_data():
    """Add sample data for testing"""
    from sqlalchemy.orm import sessionmaker
    from main import Quote, AffiliateLink
    from datetime import datetime
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    print("\nAdding sample data...")
    
    # Sample quotes
    quotes = [
        Quote(
            quote_text="Accept truth wherever you find it, no matter which tongue utters it.",
            author="Minister Louis Farrakhan",
            category="wisdom",
            ai_generated=False
        ),
        Quote(
            quote_text="Knowledge is the foundation of all in existence.",
            author="Elijah Muhammad",
            category="knowledge",
            ai_generated=False
        ),
        Quote(
            quote_text="We must combine the best of two worlds: the spiritual wisdom of the East and the technological power of the West.",
            author="Minister Louis Farrakhan",
            category="empowerment",
            ai_generated=False
        )
    ]
    
    for quote in quotes:
        session.add(quote)
    
    # Sample affiliate links
    links = [
        AffiliateLink(
            name="The Final Call Newspaper",
            url="https://www.finalcall.com",
            category="products",
            active=True
        ),
        AffiliateLink(
            name="NOI Online Store",
            url="https://store.noi.org",
            category="products",
            active=True
        )
    ]
    
    for link in links:
        session.add(link)
    
    session.commit()
    print("✅ Sample data added!")
    print("  - 3 quotes")
    print("  - 2 affiliate links")
    
    session.close()

if __name__ == "__main__":
    print("=" * 60)
    print("NOI Social Command Center - Database Setup")
    print("=" * 60)
    
    # Initialize database
    init_database()
    
    # Ask if user wants sample data
    response = input("\nDo you want to add sample data? (yes/no): ")
    if response.lower() == 'yes':
        add_sample_data()
    
    print("\n" + "=" * 60)
    print("Setup complete! 🎉")
    print("=" * 60)