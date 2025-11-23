"""
Migration to remove old NOT NULL columns from toa_yade_summary.
SQLite doesn't support DROP COLUMN, so we recreate the table.
"""

from sqlalchemy import text
from db import get_session

def migrate_drop_old_columns():
    """Remove old columns (date, time, yade_name, etc.) from toa_yade_summary."""
    
    with get_session() as session:
        try:
            print("Backing up data...")
            # Backup existing data
            result = session.execute(text("SELECT * FROM toa_yade_summary"))
            backup_data = result.fetchall()
            print(f"Found {len(backup_data)} records to migrate")
            
            print("Dropping old table...")
            session.execute(text("DROP TABLE IF EXISTS toa_yade_summary"))
            session.commit()
            
            print("Creating new table structure...")
            session.execute(text("""
                CREATE TABLE toa_yade_summary (
                    id INTEGER PRIMARY KEY,
                    voyage_id INTEGER UNIQUE,
                    before_gov_bbl REAL DEFAULT 0.0,
                    before_gsv_bbl REAL DEFAULT 0.0,
                    before_bsw_bbl REAL DEFAULT 0.0,
                    before_nsv_bbl REAL DEFAULT 0.0,
                    before_lt_bbl REAL DEFAULT 0.0,
                    before_mt REAL DEFAULT 0.0,
                    after_gov_bbl REAL DEFAULT 0.0,
                    after_gsv_bbl REAL DEFAULT 0.0,
                    after_bsw_bbl REAL DEFAULT 0.0,
                    after_nsv_bbl REAL DEFAULT 0.0,
                    after_lt_bbl REAL DEFAULT 0.0,
                    after_mt REAL DEFAULT 0.0,
                    net_gov_bbl REAL DEFAULT 0.0,
                    net_gsv_bbl REAL DEFAULT 0.0,
                    net_bsw_bbl REAL DEFAULT 0.0,
                    net_nsv_bbl REAL DEFAULT 0.0,
                    net_lt_bbl REAL DEFAULT 0.0,
                    net_mt REAL DEFAULT 0.0,
                    FOREIGN KEY (voyage_id) REFERENCES yade_voyage(id) ON DELETE CASCADE
                )
            """))
            session.execute(text("CREATE INDEX idx_toa_yade_summary_voyage ON toa_yade_summary(voyage_id)"))
            session.commit()
            
            print("Restoring data (only new columns)...")
            if backup_data:
                for row in backup_data:
                    # Extract only the columns that exist in both old and new
                    voyage_id = row[1] if len(row) > 1 else None
                    if voyage_id:
                        # Map old column indices to new structure
                        # Old: id, voyage_id, ticket_id, date, time, yade_name, convoy_no, destination, loading_berth, 
                        #      gsv_before_bbl(9), gsv_after_bbl(10), gsv_loaded_bbl(11), before_gov_bbl(12)...
                        before_gov = row[12] if len(row) > 12 else 0.0
                        before_gsv = row[13] if len(row) > 13 else 0.0
                        before_bsw = row[14] if len(row) > 14 else 0.0
                        before_nsv = row[15] if len(row) > 15 else 0.0
                        before_lt = row[16] if len(row) > 16 else 0.0
                        before_mt = row[17] if len(row) > 17 else 0.0
                        after_gov = row[18] if len(row) > 18 else 0.0
                        after_gsv = row[19] if len(row) > 19 else 0.0
                        after_bsw = row[20] if len(row) > 20 else 0.0
                        after_nsv = row[21] if len(row) > 21 else 0.0
                        after_lt = row[22] if len(row) > 22 else 0.0
                        after_mt = row[23] if len(row) > 23 else 0.0
                        net_gov = row[24] if len(row) > 24 else 0.0
                        net_gsv = row[25] if len(row) > 25 else 0.0
                        net_bsw = row[26] if len(row) > 26 else 0.0
                        net_nsv = row[27] if len(row) > 27 else 0.0
                        net_lt = row[28] if len(row) > 28 else 0.0
                        net_mt = row[29] if len(row) > 29 else 0.0
                        
                        session.execute(text("""
                            INSERT INTO toa_yade_summary 
                            (voyage_id, before_gov_bbl, before_gsv_bbl, before_bsw_bbl, before_nsv_bbl, 
                             before_lt_bbl, before_mt, after_gov_bbl, after_gsv_bbl, after_bsw_bbl, 
                             after_nsv_bbl, after_lt_bbl, after_mt, net_gov_bbl, net_gsv_bbl, net_bsw_bbl, 
                             net_nsv_bbl, net_lt_bbl, net_mt)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """), {
                            'voyage_id': voyage_id,
                            'before_gov_bbl': before_gov, 'before_gsv_bbl': before_gsv,
                            'before_bsw_bbl': before_bsw, 'before_nsv_bbl': before_nsv,
                            'before_lt_bbl': before_lt, 'before_mt': before_mt,
                            'after_gov_bbl': after_gov, 'after_gsv_bbl': after_gsv,
                            'after_bsw_bbl': after_bsw, 'after_nsv_bbl': after_nsv,
                            'after_lt_bbl': after_lt, 'after_mt': after_mt,
                            'net_gov_bbl': net_gov, 'net_gsv_bbl': net_gsv,
                            'net_bsw_bbl': net_bsw, 'net_nsv_bbl': net_nsv,
                            'net_lt_bbl': net_lt, 'net_mt': net_mt
                        })
                session.commit()
                print(f"✓ Restored {len(backup_data)} records")
            else:
                print("✓ No data to restore")
            
            print("✓ Migration complete!")
                
        except Exception as e:
            print(f"✗ Migration failed: {e}")
            session.rollback()
            raise


if __name__ == "__main__":
    print("Starting toa_yade_summary table restructure...")
    migrate_drop_old_columns()
    print("Done!")
