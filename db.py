# db.py
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

load_dotenv()

DB_URL = os.getenv("DB_URL", "sqlite:///otms.db")
connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}

engine = create_engine(DB_URL, echo=False, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# Import AFTER engine so models bind to this MetaData one time
from models import Base  # noqa: E402

def get_session():
    return SessionLocal()

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
            cols_users = {row[1] for row in conn.execute(text("PRAGMA table_info('users')")).fetchall()}
            if "supervisor_code_hash" not in cols_users:
                conn.execute(text("ALTER TABLE users ADD COLUMN supervisor_code_hash VARCHAR(255)"))
            if "supervisor_code_set_at" not in cols_users:
                conn.execute(text("ALTER TABLE users ADD COLUMN supervisor_code_set_at DATETIME"))

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
    except Exception:
        pass
