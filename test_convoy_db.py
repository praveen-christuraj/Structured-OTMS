"""
Test script to verify convoy status tables exist and can save data
"""
from db import init_db, get_session
from models import ConvoyStatusYade, ConvoyStatusVessel, Location, YadeBarge
from sqlalchemy import inspect
from datetime import date

print("=" * 60)
print("Testing Convoy Status Database Tables")
print("=" * 60)

# Ensure tables are created
print("\n1. Initializing database...")
init_db()
print("   ✓ Database initialized")

# Check if tables exist
print("\n2. Checking if convoy tables exist...")
with get_session() as session:
    inspector = inspect(session.bind)
    tables = inspector.get_table_names()
    
    yade_exists = 'convoy_status_yade' in tables
    vessel_exists = 'convoy_status_vessel' in tables
    
    print(f"   convoy_status_yade: {'✓ EXISTS' if yade_exists else '✗ NOT FOUND'}")
    print(f"   convoy_status_vessel: {'✓ EXISTS' if vessel_exists else '✗ NOT FOUND'}")
    
    if not yade_exists or not vessel_exists:
        print("\n   ERROR: Tables are missing! Running init_db() again...")
        from models import Base
        Base.metadata.create_all(bind=session.bind)
        print("   ✓ Tables should now be created")

# Count existing records
print("\n3. Counting existing records...")
with get_session() as session:
    yade_count = session.query(ConvoyStatusYade).count()
    vessel_count = session.query(ConvoyStatusVessel).count()
    location_count = session.query(Location).count()
    barge_count = session.query(YadeBarge).count()
    
    print(f"   ConvoyStatusYade: {yade_count} records")
    print(f"   ConvoyStatusVessel: {vessel_count} records")
    print(f"   Locations: {location_count} records")
    print(f"   YadeBarges: {barge_count} records")

# Show sample data if exists
print("\n4. Sample YADE convoy status records:")
with get_session() as session:
    samples = session.query(ConvoyStatusYade).limit(5).all()
    if samples:
        for rec in samples:
            print(f"   - ID: {rec.id}, Date: {rec.date}, Location: {rec.location_id}, "
                  f"Barge: {rec.yade_barge_id}, Status: {rec.status}")
    else:
        print("   (No records found)")

print("\n5. Sample Vessel convoy status records:")
with get_session() as session:
    samples = session.query(ConvoyStatusVessel).limit(5).all()
    if samples:
        for rec in samples:
            print(f"   - ID: {rec.id}, Date: {rec.date}, Location: {rec.location_id}, "
                  f"Vessel: {rec.vessel_name}, Status: {rec.status}")
    else:
        print("   (No records found)")

print("\n" + "=" * 60)
print("Test Complete!")
print("=" * 60)
