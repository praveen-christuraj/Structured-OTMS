import sqlite3
import os

db_path = 'otms_flex.db'
print(f'Checking database: {os.path.abspath(db_path)}')
print(f'Database file exists: {os.path.exists(db_path)}')
print(f'Database file size: {os.path.getsize(db_path) if os.path.exists(db_path) else 0} bytes')
print()

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Check if table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='flex_production_5'")
    table_exists = cursor.fetchone()
    print(f'Table flex_production_5 exists: {table_exists is not None}')
    
    if not table_exists:
        print('Table does not exist!')
        # List all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f'\nAvailable tables: {[t[0] for t in tables]}')
    else:
        # Get table schema
        cursor.execute('PRAGMA table_info(flex_production_5)')
        columns = cursor.fetchall()
        print('\nTable schema:')
        for col in columns:
            print(f'  {col[1]} ({col[2]}) - PK: {col[5]}, NotNull: {col[3]}, Default: {col[4]}')
        
        # Count records
        cursor.execute('SELECT COUNT(*) FROM flex_production_5')
        count = cursor.fetchone()[0]
        print(f'\nTotal records in flex_production_5: {count}')
        
        if count > 0:
            # Get all records
            cursor.execute('SELECT * FROM flex_production_5 ORDER BY id DESC')
            print('\nAll records:')
            records = cursor.fetchall()
            for row in records:
                print(f'  {row}')
        else:
            print('No records found in table!')
            
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
finally:
    conn.close()
