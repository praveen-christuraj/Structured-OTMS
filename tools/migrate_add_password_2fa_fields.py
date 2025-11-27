"""
Database Migration: Add Password and 2FA Policy Fields to Users Table

Adds the following columns to the users table:
- force_password_change (Boolean, default False)
- force_2fa (Boolean, default False)
- password_never_expires (Boolean, default False)
- password_expiry_days (Integer, default 30)

Run this script once to migrate your database.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from db import get_session, engine
from models import User
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table"""
    with engine.connect() as conn:
        # SQLite-specific query
        result = conn.execute(text(f"PRAGMA table_info({table_name})"))
        columns = [row[1] for row in result]
        return column_name in columns


def migrate_add_password_2fa_fields():
    """Add new password and 2FA policy fields to users table"""
    
    logger.info("Starting migration: Add password and 2FA policy fields")
    
    try:
        with engine.connect() as conn:
            # Check which columns need to be added
            columns_to_add = [
                ("force_password_change", "BOOLEAN DEFAULT 0"),
                ("force_2fa", "BOOLEAN DEFAULT 0"),
                ("password_never_expires", "BOOLEAN DEFAULT 0"),
                ("password_expiry_days", "INTEGER DEFAULT 30"),
            ]
            
            for column_name, column_def in columns_to_add:
                if check_column_exists("users", column_name):
                    logger.info(f"Column '{column_name}' already exists, skipping")
                else:
                    logger.info(f"Adding column '{column_name}'...")
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {column_name} {column_def}"))
                    conn.commit()
                    logger.info(f"✓ Column '{column_name}' added successfully")
            
            logger.info("Migration completed successfully!")
            
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        raise


def set_admin_defaults():
    """Set default values for existing admin users"""
    
    logger.info("Setting default values for existing admin users...")
    
    try:
        with get_session() as session:
            # Set password_never_expires=True for all admin users
            admin_users = session.query(User).filter(
                User.role.in_(["admin-it", "admin-operations"])
            ).all()
            
            for user in admin_users:
                user.password_never_expires = True
                user.force_password_change = False
                user.force_2fa = False
                logger.info(f"Updated admin user: {user.username}")
            
            # Set defaults for non-admin users
            non_admin_users = session.query(User).filter(
                ~User.role.in_(["admin-it", "admin-operations"])
            ).all()
            
            for user in non_admin_users:
                if user.password_never_expires is None:
                    user.password_never_expires = False
                if user.password_expiry_days is None:
                    user.password_expiry_days = 30
                if user.force_password_change is None:
                    user.force_password_change = False
                if user.force_2fa is None:
                    user.force_2fa = False
                logger.info(f"Updated non-admin user: {user.username}")
            
            session.commit()
            logger.info(f"✓ Updated {len(admin_users)} admin users and {len(non_admin_users)} non-admin users")
            
    except Exception as e:
        logger.error(f"Failed to set defaults: {str(e)}")
        raise


def main():
    """Run the migration"""
    print("=" * 60)
    print("Database Migration: Add Password and 2FA Policy Fields")
    print("=" * 60)
    print()
    
    try:
        # Step 1: Add columns
        migrate_add_password_2fa_fields()
        print()
        
        # Step 2: Set defaults for existing users
        set_admin_defaults()
        print()
        
        print("=" * 60)
        print("✓ Migration completed successfully!")
        print("=" * 60)
        print()
        print("Summary of changes:")
        print("- Added 'force_password_change' column (Boolean, default False)")
        print("- Added 'force_2fa' column (Boolean, default False)")
        print("- Added 'password_never_expires' column (Boolean, default False)")
        print("- Added 'password_expiry_days' column (Integer, default 30)")
        print("- Set 'password_never_expires=True' for all admin users")
        print("- Set default values for all existing non-admin users")
        print()
        print("You can now restart your application!")
        
    except Exception as e:
        print()
        print("=" * 60)
        print("✗ Migration failed!")
        print("=" * 60)
        print(f"Error: {str(e)}")
        print()
        print("Please check the error above and try again.")
        sys.exit(1)


if __name__ == "__main__":
    main()
