"""
Migration script to consolidate otms_flex.db into otms.db
This will merge all data from the flex database into the main database.
"""
import sqlite3
import os
from datetime import datetime

def migrate_database():
    print("="*70)
    print("DATABASE CONSOLIDATION MIGRATION")
    print("="*70)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Connect to both databases
    main_conn = sqlite3.connect('otms.db')
    flex_conn = sqlite3.connect('otms_flex.db')
    
    main_cursor = main_conn.cursor()
    flex_cursor = flex_conn.cursor()
    
    try:
        # Get list of tables in flex database
        flex_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        flex_tables = [row[0] for row in flex_cursor.fetchall()]
        
        print(f"Found {len(flex_tables)} tables in otms_flex.db\n")
        
        tables_migrated = 0
        tables_skipped = 0
        total_records_migrated = 0
        
        for table_name in sorted(flex_tables):
            # Check if table exists in main database
            main_cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
            table_exists = main_cursor.fetchone()
            
            if not table_exists:
                print(f"⚠️  Table '{table_name}' does not exist in otms.db - SKIPPING")
                tables_skipped += 1
                continue
            
            # Get row count from flex database
            flex_cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            flex_count = flex_cursor.fetchone()[0]
            
            # Get row count from main database
            main_cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            main_count = main_cursor.fetchone()[0]
            
            if flex_count == 0:
                print(f"⏭️  Table '{table_name}': No data in flex database - SKIPPING")
                tables_skipped += 1
                continue
            
            # Get all data from flex table
            flex_cursor.execute(f"SELECT * FROM {table_name}")
            flex_data = flex_cursor.fetchall()
            
            # Get column info
            flex_cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [col[1] for col in flex_cursor.fetchall()]
            
            # Check if data already exists (by comparing primary key if it's 'id')
            if 'id' in columns:
                # Get existing IDs from main database
                main_cursor.execute(f"SELECT id FROM {table_name}")
                existing_ids = {row[0] for row in main_cursor.fetchall()}
                
                # Filter out records that already exist
                new_records = [row for row in flex_data if row[0] not in existing_ids]
                
                if not new_records:
                    print(f"✓ Table '{table_name}': All {flex_count} records already exist in main database")
                    tables_skipped += 1
                    continue
                
                records_to_insert = new_records
            else:
                # No ID column, insert all records (may create duplicates)
                records_to_insert = flex_data
            
            # Insert records into main database
            placeholders = ','.join(['?' for _ in columns])
            insert_sql = f"INSERT INTO {table_name} ({','.join(columns)}) VALUES ({placeholders})"
            
            try:
                main_cursor.executemany(insert_sql, records_to_insert)
                main_conn.commit()
                
                print(f"✅ Table '{table_name}': Migrated {len(records_to_insert)} records (flex: {flex_count}, main before: {main_count})")
                tables_migrated += 1
                total_records_migrated += len(records_to_insert)
            except sqlite3.IntegrityError as e:
                print(f"⚠️  Table '{table_name}': Integrity error - {e}")
                main_conn.rollback()
                tables_skipped += 1
            except Exception as e:
                print(f"❌ Table '{table_name}': Error - {e}")
                main_conn.rollback()
                tables_skipped += 1
        
        print("\n" + "="*70)
        print("MIGRATION SUMMARY")
        print("="*70)
        print(f"Tables successfully migrated: {tables_migrated}")
        print(f"Tables skipped: {tables_skipped}")
        print(f"Total records migrated: {total_records_migrated}")
        print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ MIGRATION FAILED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        main_conn.close()
        flex_conn.close()

if __name__ == "__main__":
    # Backup otms.db before migration
    backup_file = f"otms_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    print(f"Creating backup: {backup_file}")
    
    import shutil
    shutil.copy2('otms.db', backup_file)
    print(f"✓ Backup created successfully\n")
    
    # Run migration
    migrate_database()
    
    print("\n⚠️  IMPORTANT: After verifying the migration, you should:")
    print("   1. Test the application to ensure everything works")
    print("   2. Update db.py to use only otms.db")
    print("   3. Delete otms_flex.db after confirming success")
