"""
Database migration script to add description column to courses table
Run this script to update your existing database schema
"""
import sqlite3
import os

# Path to your database
DB_PATH = os.path.join('instance', 'courses.db')

def migrate_database():
    """Add description column to courses table if it doesn't exist"""
    try:
        # Connect to the database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if the description column already exists
        cursor.execute("PRAGMA table_info(courses)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'description' not in columns:
            print("Adding 'description' column to courses table...")
            cursor.execute("ALTER TABLE courses ADD COLUMN description TEXT")
            conn.commit()
            print("✓ Migration completed successfully!")
        else:
            print("✓ Description column already exists. No migration needed.")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"✗ Error during migration: {e}")
        return False
    
    return True

if __name__ == '__main__':
    if os.path.exists(DB_PATH):
        print(f"Database found at: {DB_PATH}")
        migrate_database()
    else:
        print(f"Database not found at: {DB_PATH}")
        print("The database will be created with the new schema when you run the app.")
