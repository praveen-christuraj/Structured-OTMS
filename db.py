# db.py
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta

load_dotenv()

DB_URL = os.getenv("DB_URL", "sqlite:///otms.db")
connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}

engine = create_engine(DB_URL, echo=False, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# Unified database: flex_engine now points to the same database as main engine
flex_engine = engine
FlexibleSessionLocal = SessionLocal

# Import AFTER engine so models bind to this MetaData one time
from models import Base  # noqa: E402

def get_session():
    return SessionLocal()

def get_flex_session():
    return FlexibleSessionLocal()

def init_db():
    Base.metadata.create_all(bind=engine)
    _ensure_schema_updates()


def _ensure_schema_updates():
    """Apply lightweight schema updates without full migrations."""
    try:
        backend = engine.url.get_backend_name()
    except Exception:
        backend = "sqlite"

    if backend != "sqlite":
        return

    try:
        with engine.begin() as conn:
            # Locations: Head Office flag
            try:
                cols_locations = {row[1] for row in conn.execute(text("PRAGMA table_info('locations')")).fetchall()}
                if "is_head_office" not in cols_locations:
                    conn.execute(text("ALTER TABLE locations ADD COLUMN is_head_office BOOLEAN DEFAULT 0"))
            except Exception:
                pass

            cols_users = {row[1] for row in conn.execute(text("PRAGMA table_info('users')")).fetchall()}
            if "supervisor_code_hash" not in cols_users:
                conn.execute(text("ALTER TABLE users ADD COLUMN supervisor_code_hash VARCHAR(255)"))
            if "supervisor_code_set_at" not in cols_users:
                conn.execute(text("ALTER TABLE users ADD COLUMN supervisor_code_set_at DATETIME"))
            if "export_ops_access" not in cols_users:
                conn.execute(text("ALTER TABLE users ADD COLUMN export_ops_access BOOLEAN DEFAULT 0"))

            cols_tanker_cal = {row[1] for row in conn.execute(text("PRAGMA table_info('tanker_calibration')")).fetchall()}
            if "tanker_id" not in cols_tanker_cal:
                conn.execute(text("ALTER TABLE tanker_calibration ADD COLUMN tanker_id INTEGER"))
            if "chassis_no" not in cols_tanker_cal:
                conn.execute(text("ALTER TABLE tanker_calibration ADD COLUMN chassis_no VARCHAR(100)"))

            # Ensure new OTR net columns exist (added after initial table creation)
            try:
                cols_otr = {row[1] for row in conn.execute(text("PRAGMA table_info('otr_records')")).fetchall()}
                if "net_rece_disp_bbls" not in cols_otr:
                    conn.execute(text("ALTER TABLE otr_records ADD COLUMN net_rece_disp_bbls FLOAT"))
                if "net_water_rece_disp_bbls" not in cols_otr:
                    conn.execute(text("ALTER TABLE otr_records ADD COLUMN net_water_rece_disp_bbls FLOAT"))
            except Exception:
                pass
            # Ensure new export stage progress columns exist
            try:
                cols_exp_stage = {row[1] for row in conn.execute(text("PRAGMA table_info('export_stage_progress')")).fetchall()}
                if "due_date" not in cols_exp_stage:
                    conn.execute(text("ALTER TABLE export_stage_progress ADD COLUMN due_date DATE"))
                if "status_changed_at" not in cols_exp_stage:
                    conn.execute(text("ALTER TABLE export_stage_progress ADD COLUMN status_changed_at DATETIME"))
                if "due_notified_at" not in cols_exp_stage:
                    conn.execute(text("ALTER TABLE export_stage_progress ADD COLUMN due_notified_at DATETIME"))
                if "remarks" not in cols_exp_stage:
                    conn.execute(text("ALTER TABLE export_stage_progress ADD COLUMN remarks TEXT"))
                if "completed_at" not in cols_exp_stage:
                    conn.execute(text("ALTER TABLE export_stage_progress ADD COLUMN completed_at DATETIME"))
                if "completed_by" not in cols_exp_stage:
                    conn.execute(text("ALTER TABLE export_stage_progress ADD COLUMN completed_by VARCHAR(64)"))
                if "completed_overdue" not in cols_exp_stage:
                    conn.execute(text("ALTER TABLE export_stage_progress ADD COLUMN completed_overdue BOOLEAN DEFAULT 0"))
                if "overdue_reason" not in cols_exp_stage:
                    conn.execute(text("ALTER TABLE export_stage_progress ADD COLUMN overdue_reason TEXT"))
            except Exception:
                pass

            # Ensure laycan columns exist on export_processes
            try:
                cols_export = {row[1] for row in conn.execute(text("PRAGMA table_info('export_processes')")).fetchall()}
                if "laycan_start" not in cols_export:
                    conn.execute(text("ALTER TABLE export_processes ADD COLUMN laycan_start DATE"))
                if "laycan_end" not in cols_export:
                    conn.execute(text("ALTER TABLE export_processes ADD COLUMN laycan_end DATE"))
            except Exception:
                pass

            # Normalize legacy audit_log timestamps (older builds stored local WAT as naive)
            try:
                max_ts_val = conn.execute(text("SELECT MAX(timestamp) FROM audit_log")).scalar()
                max_ts = None
                if isinstance(max_ts_val, datetime):
                    max_ts = max_ts_val
                elif isinstance(max_ts_val, str) and max_ts_val.strip():
                    s = max_ts_val.strip().replace("T", " ")
                    try:
                        max_ts = datetime.fromisoformat(s)
                    except Exception:
                        max_ts = None

                # If newest audit timestamp is ahead of UTC "now", assume it was stored in local WAT (UTC+1)
                if max_ts and (max_ts - datetime.utcnow()) > timedelta(minutes=30):
                    conn.execute(text("UPDATE audit_log SET timestamp = datetime(timestamp, '-1 hour')"))
            except Exception:
                pass
    except Exception:
        pass
