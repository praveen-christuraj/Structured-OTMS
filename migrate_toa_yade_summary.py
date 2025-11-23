"""
Migration script to update TOAYadeSummary table structure.
Adds new columns for complete TOA tracking (GOV, GSV, BSW, NSV, LT, MT for Before/After/Net).
"""

from sqlalchemy import text
from db import get_session, engine

def migrate_toa_yade_summary():
    """Add new columns to toa_yade_summary table."""
    
    with get_session() as session:
        try:
            # Check if table exists
            result = session.execute(text("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='toa_yade_summary'
            """))
            
            if not result.fetchone():
                print("Table toa_yade_summary does not exist. Creating from models...")
                from models import Base
                Base.metadata.create_all(engine, tables=[Base.metadata.tables['toa_yade_summary']])
                session.commit()
                print("✓ Table created successfully")
                return
            
            # Check existing columns
            result = session.execute(text("PRAGMA table_info(toa_yade_summary)"))
            existing_columns = {row[1] for row in result.fetchall()}
            
            print(f"Existing columns: {existing_columns}")
            
            # Define new columns to add
            new_columns = {
                'before_gov_bbl': 'REAL DEFAULT 0.0',
                'before_gsv_bbl': 'REAL DEFAULT 0.0',
                'before_bsw_bbl': 'REAL DEFAULT 0.0',
                'before_nsv_bbl': 'REAL DEFAULT 0.0',
                'before_lt_bbl': 'REAL DEFAULT 0.0',
                'before_mt': 'REAL DEFAULT 0.0',
                'after_gov_bbl': 'REAL DEFAULT 0.0',
                'after_gsv_bbl': 'REAL DEFAULT 0.0',
                'after_bsw_bbl': 'REAL DEFAULT 0.0',
                'after_nsv_bbl': 'REAL DEFAULT 0.0',
                'after_lt_bbl': 'REAL DEFAULT 0.0',
                'after_mt': 'REAL DEFAULT 0.0',
                'net_gov_bbl': 'REAL DEFAULT 0.0',
                'net_gsv_bbl': 'REAL DEFAULT 0.0',
                'net_bsw_bbl': 'REAL DEFAULT 0.0',
                'net_nsv_bbl': 'REAL DEFAULT 0.0',
                'net_lt_bbl': 'REAL DEFAULT 0.0',
                'net_mt': 'REAL DEFAULT 0.0',
            }
            
            # Add missing columns
            added_count = 0
            for col_name, col_type in new_columns.items():
                if col_name not in existing_columns:
                    try:
                        session.execute(text(f"ALTER TABLE toa_yade_summary ADD COLUMN {col_name} {col_type}"))
                        session.commit()
                        print(f"✓ Added column: {col_name}")
                        added_count += 1
                    except Exception as e:
                        print(f"✗ Failed to add {col_name}: {e}")
                        session.rollback()
            
            if added_count == 0:
                print("✓ All columns already exist - no migration needed")
            else:
                print(f"✓ Migration complete: {added_count} columns added")
                
        except Exception as e:
            print(f"✗ Migration failed: {e}")
            session.rollback()
            raise


if __name__ == "__main__":
    print("Starting TOAYadeSummary migration...")
    migrate_toa_yade_summary()
    print("Migration complete!")
