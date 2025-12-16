# models.py
"""
Database models for OTMS (Oil Terminal Management System)
Multi-location support with comprehensive security and audit trails
"""

from datetime import datetime
import enum

from sqlalchemy import (
    Column, Integer, Float, String, Date, Time, DateTime, Boolean, Text,
    ForeignKey, Enum as SAEnum, UniqueConstraint, Index, LargeBinary
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from sqlalchemy import Float, Boolean, LargeBinary, Index, Time, Enum as SAEnum, Table, MetaData

try:
    from db import engine
except Exception:
    engine = None

Base = declarative_base()

# ============================================================================
# ENUMS
# ============================================================================

class FlexibleRecord(Base):
    __tablename__ = "flexible_records"
    id = Column(Integer, primary_key=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    page = Column(String(64), nullable=False)       # e.g., "tank_transactions"
    section = Column(String(64), nullable=False)    # e.g., "produced_water", "production"
    tx_date = Column(Date, nullable=True)           # optional date for filtering
    data_json = Column(Text, nullable=False)        # raw row as JSON
    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    location = relationship("Location", backref="flexible_records")

class TankStatus(enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"

class TankOpStatus(enum.Enum):
    RECEIVING = "RECEIVING"       # not pumpable
    DISPATCHING = "DISPATCHING"   # pumpable
    IDLE = "IDLE"                 # pumpable
    READY = "READY"               # pumpable
    SETTLING = "SETTLING"         # not pumpable
    MAINTENANCE = "MAINTENANCE"   # not pumpable
    DRAINING = "DRAINING"         # not pumpable
    ISOLATED = "ISOLATED"         # not pumpable

class Operation(enum.Enum):
    """Operation types for tank transactions"""
    # Opening / Closing
    OPENING_STOCK = "Opening Stock"
    CLOSING_STOCK = "Closing Stock"
    
    # Receipts
    RECEIPT = "Receipt"
    RECEIPT_CRUDE = "Receipt - Commingled"
    RECEIPT_CONDENSATE = "Receipt - Condensate"
    RECEIPT_FROM_AGU = "Receipt from Agu"
    RECEIPT_FROM_OFS = "Receipt from OFS"
    OKW_RECEIPT = "OKW Receipt"
    ANZ_RECEIPT = "ANZ Receipt"
    OTHER_RECEIPTS = "Other Receipts"
    
    # Dispatches
    DISPATCH = "Dispatch"
    DISPATCH_TO_BARGE = "Dispatch to barge"
    DISPATCH_TO_JETTY = "Dispatch to Jetty"
    OTHER_DISPATCH = "Other Dispatch"
    
    # Inter-Tank Transfers
    ITT_RECEIPT = "ITT - Receipt"
    ITT_DISPATCH = "ITT - Dispatch"
    
    # Maintenance
    SETTLING = "Settling"
    DRAINING = "Draining"


class TaskType(enum.Enum):
    DELETE_REQUEST = "DELETE_REQUEST"
    ERROR_ALERT = "ERROR_ALERT"
    PASSWORD_RESET = "PASSWORD_RESET"
    FORGOT_PASSWORD = "FORGOT_PASSWORD"
    USER_CREATION = "USER_CREATION"
    INFO = "INFO"
    SERVICE_REQUEST = "SERVICE_REQUEST"


class TaskStatus(enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TankerReceiptStatus(enum.Enum):
    PENDING = "PENDING"
    RECEIVED = "RECEIVED"
    REJECTED = "REJECTED"

class TankDailyStatus(Base):
    __tablename__ = "tank_daily_statuses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tank_id = Column(Integer, ForeignKey("tanks.id"), nullable=False)
    date = Column(Date, nullable=False)
    op_status = Column(SAEnum(TankOpStatus), nullable=False, default=TankOpStatus.READY)
    note = Column(Text)
    created_by = Column(String(50))
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tank_id", "date", name="uq_tank_date_status"),
        Index("idx_tank_date", "tank_id", "date"),
    )

    tank = relationship("Tank")

    def __repr__(self):
        return f"<TankDailyStatus tank={self.tank_id} date={self.date} status={self.op_status}>"


class CargoKind(enum.Enum):
    OKWUIBOME_CRUDE = "Okwuibome Blend Crude"
    OKWUIBOME_CONDENSATE = "Okwuibome Condensate"
    AGO = "AGO"
    PMS = "PMS"

class DestinationKind(enum.Enum):
    AGGE = "Agge"
    NDONI = "Ndoni"
    ASEMOKU = "Asemoku"

class LoadingBerthKind(enum.Enum):
    NDONI_JETTY = "Ndoni Jetty"
    ASEMOKU_JETTY = "Asemoku Jetty"
    STS = "STS"

# ============================================================================
# LOCATION SUPPORT
# ============================================================================

class Location(Base):
    """Location/Terminal master - represents different oil terminals"""
    __tablename__ = "locations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    code = Column(String(20), unique=True, nullable=False)
    address = Column(Text)
    is_active = Column(Boolean, default=True)
    is_head_office = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    
    # Relationships - Location has many entities
    tanks = relationship("Tank", back_populates="location", lazy="dynamic", cascade="all, delete-orphan")
    users = relationship("User", back_populates="location", lazy="dynamic")
    tank_transactions = relationship("TankTransaction", back_populates="location", lazy="dynamic")
    gpp_productions = relationship("GPPProductionRecord", back_populates="location", lazy="dynamic", cascade="all, delete-orphan")
    river_draft_entries = relationship(
        "RiverDraftRecord",
        back_populates="location",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    produced_water_entries = relationship(
        "ProducedWaterRecord",
        back_populates="location",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    yade_voyages = relationship("YadeVoyage", back_populates="location", lazy="dynamic")
    tanker_transactions = relationship("TankerTransaction", back_populates="location", lazy="dynamic")
    otr_records = relationship("OTRRecord", back_populates="location", lazy="dynamic")
    calibrations = relationship("CalibrationTank", back_populates="location", lazy="dynamic")
    fso_operations = relationship("FSOOperation", back_populates="location", lazy="dynamic", cascade="all, delete-orphan")  # ✅ ADDED
    tanker_counts = relationship(
        "LocationTankerEntry",
        back_populates="location",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    tanker_receipts = relationship(
        "TankerReceipt",
        primaryjoin="Location.id==TankerReceipt.receiver_location_id",
        lazy="dynamic",
        back_populates="receiver_location",
    )

    # Relationship for OFS production & evacuation records
    ofs_records = relationship(
        "OFSProductionEvacuationRecord",
        back_populates="location",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Location(id={self.id}, name='{self.name}', code='{self.code}')>"
        
#=========================== METER ADDITION =========================================

class LocationConfiguration(Base):
    """Store location-specific configuration as JSON"""
    __tablename__ = "location_configurations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, unique=True)
    config_json = Column(Text, nullable=True)  # JSON configuration
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    # Relationship
    location = relationship("Location")

class Meter(Base):
    __tablename__ = "meters"
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(64), unique=True, nullable=False)   # e.g. "MTR-01"
    name = Column(String(128), nullable=False)               # e.g. "Loading Meter A"
    status = Column(String(16), default="active")            # "active"/"inactive"
    created_at = Column(DateTime, default=datetime.utcnow)

class LocationMeter(Base):
    __tablename__ = "location_meters"
    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    meter_id = Column(Integer, ForeignKey("meters.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("location_id", "meter_id", name="uq_loc_meter"),)

    # optional relationships
    meter = relationship("Meter")

class LocationPageConfig(Base):
    __tablename__ = "location_page_config"
    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    page = Column(String(64), nullable=False)     # e.g. "tank_transactions"
    section = Column(String(64), nullable=False)  # e.g. "meter_records" / "condensate" / "produced_water"
    config_json = Column(Text, nullable=False, default="{}")
    updated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("location_id", "page", "section", name="uq_loc_page_section"),)

# ============================================================================
# OFS PRODUCTION & EVACUATION
# ============================================================================
class OFSProductionEvacuationRecord(Base):
    """
    Capture daily production and evacuation figures for OFS locations (e.g. OML‑157).

    Each record stores volumes for Oguali and Ukpichi production, production from
    other locations, total evacuation, and tanker counts per location. A serial
    number per location ensures a stable ascending index for reporting.
    """

    __tablename__ = "ofs_production_evacuation_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    serial_no = Column(Integer, nullable=False)
    date = Column(Date, nullable=False)
    oguali_production = Column(Float, default=0.0)
    ukpichi_production = Column(Float, default=0.0)
    other_locations = Column(Float, default=0.0)
    evacuation = Column(Float, default=0.0)
    tankers_oguali = Column(Float, default=0.0)
    tankers_ukpichi = Column(Float, default=0.0)
    other_tankers = Column(Float, default=0.0)
    created_by = Column(String(50))
    updated_by = Column(String(50))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    location = relationship("Location", back_populates="ofs_records")

    __table_args__ = (
        UniqueConstraint("location_id", "serial_no", name="uq_ofs_serial_per_location"),
        Index("idx_ofs_location_date", "location_id", "date"),
    )

    def __repr__(self) -> str:
        return (
            f"<OFSProductionEvacuationRecord id={self.id} loc={self.location_id} "
            f"date={self.date} serial={self.serial_no}>"
        )


class LocationTankerEntry(Base):
    """Manual tanker dispatch/receipt logs for Aggu and Ndoni dashboards."""

    __tablename__ = "location_tanker_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    serial_no = Column(Integer, nullable=False)
    date = Column(Date, nullable=False)

    # Metrics (unused columns remain zero for specific locations)
    tankers_dispatched = Column(Float, default=0.0)
    tankers_from_aggu = Column(Float, default=0.0)
    tankers_from_ofs = Column(Float, default=0.0)
    other_tankers = Column(Float, default=0.0)

    remarks = Column(Text)
    created_by = Column(String(50))
    updated_by = Column(String(50))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    location = relationship("Location", back_populates="tanker_counts")

    __table_args__ = (
        UniqueConstraint("location_id", "serial_no", name="uq_tanker_entry_serial"),
        Index("idx_tanker_entry_loc_date", "location_id", "date"),
    )

    def __repr__(self) -> str:
        return f"<LocationTankerEntry id={self.id} loc={self.location_id} serial={self.serial_no} date={self.date}>"


# ============================================================================
# USER & AUTHENTICATION
# ============================================================================

class User(Base):
    """User accounts with location assignment and 2FA support"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(250), nullable=False)
    full_name = Column(String(150), nullable=True)
    role = Column(String(30), nullable=False)  # admin-operations, admin-it, manager, supervisor, operator
    
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    last_login = Column(DateTime, nullable=True)
    
    # Security fields
    must_change_password = Column(Boolean, default=True, nullable=False)
    password_changed_at = Column(DateTime, nullable=True)
    failed_login_attempts = Column(Integer, default=0)
    account_locked_until = Column(DateTime, nullable=True)
    last_activity = Column(DateTime, nullable=True)
    
    # Password policy fields
    force_password_change = Column(Boolean, default=True, nullable=False)  # Mandatory password change on first login
    password_never_expires = Column(Boolean, default=False, nullable=False)  # Admins can be exempt from 30-day rule
    password_expiry_days = Column(Integer, default=30, nullable=False)  # Days before password expires
    
    # 2FA fields
    totp_secret = Column(String(32), nullable=True)
    totp_enabled = Column(Boolean, default=False, nullable=False)
    force_2fa = Column(Boolean, default=True, nullable=False)  # Mandatory 2FA enforcement
    backup_codes = Column(String(500), nullable=True)
    supervisor_code_hash = Column(String(255), nullable=True)
    supervisor_code_set_at = Column(DateTime, nullable=True)
    # Feature access flags
    export_ops_access = Column(Boolean, default=False, nullable=False)
    
    # Relationship
    location = relationship("Location", back_populates="users")

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"


# ============================================================================
# TANK MASTER & CALIBRATION
# ============================================================================

class Tank(Base):
    __tablename__ = "tanks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    name = Column(String(100), nullable=False)
    capacity_bbl = Column(Float, nullable=False)
    product = Column(String(50), nullable=False)
    status = Column(SAEnum(TankStatus), default=TankStatus.ACTIVE, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    
    # Composite unique constraint: Tank name must be unique PER LOCATION
    __table_args__ = (
        UniqueConstraint('location_id', 'name', name='uq_tank_location_name'),
    )
    
    # Relationships
    location = relationship("Location", back_populates="tanks")
    calibration = relationship("CalibrationTank", back_populates="tank", lazy="dynamic", cascade="all, delete-orphan")
    transactions = relationship("TankTransaction", back_populates="tank", lazy="dynamic")

    def __repr__(self):
        return f"<Tank(id={self.id}, name='{self.name}', location_id={self.location_id})>"


class CalibrationTank(Base):
    """Tank calibration - location-specific"""
    __tablename__ = "calibration_tank"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    tank_id = Column(Integer, ForeignKey("tanks.id"), nullable=False)
    tank_name = Column(String(50), index=True, nullable=False)
    dip_cm = Column(Float, nullable=False)
    volume_bbl = Column(Float, nullable=False)
    
    # Relationships
    location = relationship("Location", back_populates="calibrations")
    tank = relationship("Tank", back_populates="calibration")

    def __repr__(self):
        return f"<CalibrationTank(tank='{self.tank_name}', dip={self.dip_cm}cm, vol={self.volume_bbl}bbl)>"


# ============================================================================
# YADE BARGE MASTER & CALIBRATION (SHARED GLOBALLY)
# ============================================================================

class YadeBarge(Base):
    """YADE barge master - shared globally across all locations"""
    __tablename__ = "yade_barges"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    design = Column(String(2), nullable=False)  # "6" or "4"
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<YadeBarge(name='{self.name}', design='{self.design}')>"


class YadeCalibration(Base):
    """YADE calibration - shared globally"""
    __tablename__ = "yade_calibration"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    yade_name = Column(String(100), index=True, nullable=False)
    tank_id = Column(String(10), nullable=False)
    dip_mm = Column(Float, nullable=False)
    vol_bbl = Column(Float, nullable=False)
    mm1 = Column(Float, nullable=True)
    mm2 = Column(Float, nullable=True)
    mm3 = Column(Float, nullable=True)
    mm4 = Column(Float, nullable=True)
    mm5 = Column(Float, nullable=True)
    mm6 = Column(Float, nullable=True)
    mm7 = Column(Float, nullable=True)
    mm8 = Column(Float, nullable=True)
    mm9 = Column(Float, nullable=True)


# ============================================================================
# TANKER MASTER & CALIBRATION (SHARED GLOBALLY)
# ============================================================================

class Tanker(Base):
    """Tanker master - shared globally across all locations"""
    __tablename__ = "tankers"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    registration_no = Column(String(50), nullable=True)
    capacity_litres = Column(Float, nullable=True)
    status = Column(SAEnum(TankStatus), default=TankStatus.ACTIVE, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<Tanker(name='{self.name}')>"


class TankerCalibration(Base):
    """Tanker calibration - shared globally"""
    __tablename__ = "tanker_calibration"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tanker_name = Column(String(100), index=True, nullable=False)
    compartment = Column(String(10), nullable=False)
    tanker_id = Column(Integer, ForeignKey("tankers.id"), nullable=True, index=True)
    chassis_no = Column(String(100), nullable=True)
    dip_mm = Column(Float, nullable=False)
    volume_litres = Column(Float, nullable=False)


class TankerReceipt(Base):
    """Receiver-side intake against a tanker dispatch (one per dispatch)."""

    __tablename__ = "tanker_receipts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dispatch_id = Column(Integer, ForeignKey("tanker_transactions.id"), unique=True, nullable=False, index=True)
    receiver_location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)

    status = Column(SAEnum(TankerReceiptStatus), nullable=False, default=TankerReceiptStatus.PENDING)
    arrival_date = Column(Date, nullable=True)
    arrival_time = Column(Time, nullable=True)
    received_at = Column(DateTime, nullable=True)

    total_dip_cm = Column(Float, default=0.0)
    water_dip_cm = Column(Float, default=0.0)
    tank_temp_c = Column(Float, nullable=True)
    tank_temp_f = Column(Float, nullable=True)
    sample_temp_c = Column(Float, nullable=True)
    sample_temp_f = Column(Float, nullable=True)
    api_observed = Column(Float, nullable=True)
    density_observed = Column(Float, nullable=True)
    api60 = Column(Float, nullable=True)
    vcf = Column(Float, nullable=True)
    bsw_pct = Column(Float, default=0.0)

    total_volume_bbl = Column(Float, default=0.0)
    water_volume_bbl = Column(Float, default=0.0)
    gov_bbl = Column(Float, default=0.0)
    gsv_bbl = Column(Float, default=0.0)
    bsw_vol_bbl = Column(Float, default=0.0)
    nsv_bbl = Column(Float, default=0.0)
    lt = Column(Float, nullable=True)
    mt = Column(Float, nullable=True)

    receiver_notes = Column(String(500), nullable=True)
    created_by = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_by = Column(String(50), nullable=True)
    updated_at = Column(DateTime, onupdate=func.now())

    receiver_location = relationship("Location", back_populates="tanker_receipts", foreign_keys=[receiver_location_id])
    dispatch = relationship("TankerTransaction", back_populates="receipt")

    __table_args__ = (
        Index("idx_tanker_receipt_receiver_date", "receiver_location_id", "arrival_date"),
    )

    def __repr__(self) -> str:
        return f"<TankerReceipt id={self.id} dispatch={self.dispatch_id} status={self.status}>"

# ============================================================================
# VESSEL MASTER (SHARED GLOBALLY LIKE YADE/TANKER)
# ============================================================================

class Vessel(Base):
    """Vessel master - shared globally across all locations"""
    __tablename__ = "vessels"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    vessel_type = Column(String(50), nullable=True)  # MT (Motor Tanker), Barge, etc.
    capacity_bbl = Column(Float, nullable=True)
    registration_no = Column(String(50), nullable=True)
    status = Column(String(20), default="ACTIVE")
    created_at = Column(DateTime, server_default=func.now())
    
    def __repr__(self):
        return f"<Vessel(name='{self.name}', type='{self.vessel_type}')>"


class VesselOperation(Base):
    """Vessel operation types - shared globally"""
    __tablename__ = "vessel_operations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    operation_name = Column(String(50), nullable=False, unique=True)
    category = Column(String(50), nullable=True)  # LOADING, OFFLOADING, TRANSIT, STANDBY
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    
    def __repr__(self):
        return f"<VesselOperation(name='{self.operation_name}')>"


class LocationVessel(Base):
    """Location-Vessel assignment - which vessels are available at which location"""
    __tablename__ = "location_vessels"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    vessel_id = Column(Integer, ForeignKey("vessels.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    assigned_at = Column(DateTime, server_default=func.now())
    
    # Composite unique: Each vessel can only be assigned once per location
    __table_args__ = (
        UniqueConstraint('location_id', 'vessel_id', name='uq_location_vessel'),
    )
    
    # Relationships
    location = relationship("Location")
    vessel = relationship("Vessel")
    
    def __repr__(self):
        return f"<LocationVessel(location_id={self.location_id}, vessel_id={self.vessel_id})>"

# ============================================================================
# ASTM TABLE 11 (SHARED GLOBALLY)
# ============================================================================

class Table11(Base):
    """ASTM Table 11 - LT factors (shared globally)"""
    __tablename__ = "table11"
    
    id = Column(Integer, primary_key=True)
    api60 = Column(Float, nullable=False)
    lt_factor = Column(Float, nullable=False)


# ============================================================================
# TANK TRANSACTIONS (LOCATION-SPECIFIC)
# ============================================================================

class TankTransaction(Base):
    """Tank transactions - location-specific"""
    __tablename__ = "tank_transactions"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    ticket_id = Column(String(100), index=True, nullable=False)
    operation = Column(SAEnum(Operation), nullable=False)
    tank_id = Column(Integer, ForeignKey("tanks.id"), nullable=True)
    tank_name = Column(String(50), nullable=True)
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=False)
    
    dip_cm = Column(Float, default=0)
    water_cm = Column(Float, default=0)
    
    tank_temp_c = Column(Float, nullable=True)
    tank_temp_f = Column(Float, nullable=True)
    
    api_observed = Column(Float, nullable=True)
    density_observed = Column(Float, nullable=True)
    bsw_pct = Column(Float, nullable=True)
    sample_temp_c = Column(Float, nullable=True)
    sample_temp_f = Column(Float, nullable=True)
    
    qty_bbls = Column(Float, nullable=True)
    remarks = Column(String(250), nullable=True)

    # Condensate receipt fields (for BFS meter readings)
    opening_meter_reading = Column(Float, nullable=True)
    closing_meter_reading = Column(Float, nullable=True)
    condensate_qty_m3 = Column(Float, nullable=True)
    
    # Audit fields
    created_by = Column(String(50), nullable=False, default='system')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_by = Column(String(50), nullable=True)
    updated_at = Column(DateTime, nullable=True)
    
    # Relationships
    location = relationship("Location", back_populates="tank_transactions")
    tank = relationship("Tank", back_populates="transactions")


# ============================================================================
# METER TRANSACTIONS (LOCATION-SPECIFIC, E.g., Asemoku Jetty)
# ============================================================================
 
class MeterTransaction(Base):
    """Manual meter transactions for a location (e.g., Asemoku Jetty)."""
    __tablename__ = "meter_transactions"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)

    date = Column(Date, nullable=False)
    opening_meter_reading = Column(Float, nullable=False)
    closing_meter_reading = Column(Float, nullable=False)
    opening_meter2_reading = Column(Float, nullable=True)
    closing_meter2_reading = Column(Float, nullable=True)
    net_qty = Column(Float, nullable=False)  # (M1 close - M1 open) + (M2 close - M2 open)
    remarks = Column(String(250), nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # Relationship
    location = relationship("Location")


Index('idx_meter_tx_location_date', MeterTransaction.location_id, MeterTransaction.date)


# ============================================================================
# GPP PRODUCTION (BENEKU)
# ============================================================================

class GPPProductionRecord(Base):
    """Daily GPP production summary per location."""
    __tablename__ = "gpp_production_records"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)
    date = Column(Date, nullable=False)
    okw_production = Column(Float, nullable=False, default=0.0)
    gpp1_production = Column(Float, nullable=False, default=0.0)
    gpp2_production = Column(Float, nullable=False, default=0.0)
    total_production = Column(Float, nullable=False, default=0.0)
    gpp_closing_stock = Column(Float, nullable=False, default=0.0)
    remarks = Column(Text, nullable=True)

    created_by = Column(String(50), nullable=False, default="system")
    created_at = Column(DateTime, server_default=func.now())
    updated_by = Column(String(50), nullable=True)
    updated_at = Column(DateTime, onupdate=func.now())

    location = relationship("Location", back_populates="gpp_productions")

    def __repr__(self):
        return (
            f"<GPPProductionRecord(id={self.id}, date={self.date}, "
            f"gpp1={self.gpp1_production}, gpp2={self.gpp2_production})>"
        )


Index('idx_gpp_prod_location_date', GPPProductionRecord.location_id, GPPProductionRecord.date)


class RiverDraftRecord(Base):
    """Manual capture of river draft and rainfall per location/date."""
    __tablename__ = "river_draft_records"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)
    date = Column(Date, nullable=False)
    river_draft_m = Column(Float, nullable=False, default=0.0)
    rainfall_cm = Column(Float, nullable=False, default=0.0)

    created_by = Column(String(50), nullable=False, default="system")
    created_at = Column(DateTime, server_default=func.now())
    updated_by = Column(String(50), nullable=True)
    updated_at = Column(DateTime, onupdate=func.now())

    location = relationship("Location", back_populates="river_draft_entries")

    def __repr__(self):
        return f"<RiverDraftRecord(id={self.id}, date={self.date}, river_draft_m={self.river_draft_m}, rainfall_cm={self.rainfall_cm})>"


Index('idx_river_draft_location_date', RiverDraftRecord.location_id, RiverDraftRecord.date)


class ProducedWaterRecord(Base):
    """Manual capture of produced water per location/date."""
    __tablename__ = "produced_water_records"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)
    date = Column(Date, nullable=False)
    produced_water_bbl = Column(Float, nullable=False, default=0.0)

    created_by = Column(String(50), nullable=False, default="system")
    created_at = Column(DateTime, server_default=func.now())
    updated_by = Column(String(50), nullable=True)
    updated_at = Column(DateTime, onupdate=func.now())

    location = relationship("Location", back_populates="produced_water_entries")

    def __repr__(self):
        return f"<ProducedWaterRecord(id={self.id}, date={self.date}, bbl={self.produced_water_bbl})>"


Index('idx_produced_water_location_date', ProducedWaterRecord.location_id, ProducedWaterRecord.date)


# ============================================================================
# YADE VOYAGE TRANSACTIONS (LOCATION-SPECIFIC)
# ============================================================================

class YadeVoyage(Base):
    """YADE voyage - location-specific"""
    __tablename__ = "yade_voyage"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    
    yade_name = Column(String(64), nullable=False)
    design = Column(String(2), nullable=False)
    voyage_no = Column(String(32), nullable=False)
    convoy_no = Column(String(32), nullable=False)
    
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=False)
    
    cargo = Column(String(64), nullable=False)
    destination = Column(String(64), nullable=False)
    loading_berth = Column(String(64), nullable=False)
    
    before_gauge_date = Column(Date, nullable=False)
    before_gauge_time = Column(Time, nullable=False)
    after_gauge_date = Column(Date, nullable=False)
    after_gauge_time = Column(Time, nullable=False)
    
    # Audit fields
    created_by = Column(String(64), default='system')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(DateTime, nullable=True)
    
    # Relationship
    location = relationship("Location", back_populates="yade_voyages")


class YadeDip(Base):
    """YADE dip readings"""
    __tablename__ = "yade_dips"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    voyage_id = Column(Integer, ForeignKey("yade_voyage.id", ondelete="CASCADE"), nullable=False)
    
    tank_id = Column(String(8), nullable=False)
    stage = Column(String(8), nullable=False)
    
    total_cm = Column(Float, nullable=False, default=0.0)
    water_cm = Column(Float, nullable=False, default=0.0)


class YadeSampleParam(Base):
    """YADE sample parameters"""
    __tablename__ = "yade_sample_param"
    
    id = Column(Integer, primary_key=True)
    voyage_id = Column(Integer, ForeignKey("yade_voyage.id", ondelete="CASCADE"), index=True, nullable=False)
    stage = Column(String(10), nullable=False)
    obs_mode = Column(String(32), nullable=False)
    obs_val = Column(Float, nullable=False, default=0.0)
    sample_unit = Column(String(4), nullable=False)
    sample_temp = Column(Float, nullable=False, default=0.0)
    tank_temp = Column(Float, nullable=False, default=0.0)
    ccf = Column(Float, nullable=False, default=1.0)
    bsw_pct = Column(Float, nullable=False, default=0.0)
    
    __table_args__ = (UniqueConstraint("voyage_id", "stage", name="uq_ysp_voyage_stage"),)


class YadeSealDetail(Base):
    """YADE seal details"""
    __tablename__ = "yade_seal_detail"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    voyage_id = Column(Integer, ForeignKey("yade_voyage.id", ondelete="CASCADE"), nullable=False)
    
    c1_mh1 = Column(String(32), nullable=True)
    c1_mh2 = Column(String(32), nullable=True)
    c1_lock = Column(String(32), nullable=True)
    c1_diphatch = Column(String(32), nullable=True)
    
    c2_mh1 = Column(String(32), nullable=True)
    c2_mh2 = Column(String(32), nullable=True)
    c2_lock = Column(String(32), nullable=True)
    c2_diphatch = Column(String(32), nullable=True)
    
    p1_mh1 = Column(String(32), nullable=True)
    p1_mh2 = Column(String(32), nullable=True)
    p1_lock = Column(String(32), nullable=True)
    p1_diphatch = Column(String(32), nullable=True)
    
    p2_mh1 = Column(String(32), nullable=True)
    p2_mh2 = Column(String(32), nullable=True)
    p2_lock = Column(String(32), nullable=True)
    p2_diphatch = Column(String(32), nullable=True)
    
    s1_mh1 = Column(String(32), nullable=True)
    s1_mh2 = Column(String(32), nullable=True)
    s1_lock = Column(String(32), nullable=True)
    s1_diphatch = Column(String(32), nullable=True)
    
    s2_mh1 = Column(String(32), nullable=True)
    s2_mh2 = Column(String(32), nullable=True)
    s2_lock = Column(String(32), nullable=True)
    s2_diphatch = Column(String(32), nullable=True)


class TOAYadeSummary(Base):
    """TOA YADE summary"""
    __tablename__ = "toa_yade_summary"
    
    id = Column(Integer, primary_key=True)
    voyage_id = Column(Integer, ForeignKey("yade_voyage.id", ondelete="CASCADE"), unique=True, index=True)
    
    # BEFORE stage
    before_gov_bbl = Column(Float, default=0.0)
    before_gsv_bbl = Column(Float, default=0.0)
    before_bsw_bbl = Column(Float, default=0.0)
    before_nsv_bbl = Column(Float, default=0.0)
    before_lt_bbl = Column(Float, default=0.0)
    before_mt = Column(Float, default=0.0)
    
    # AFTER stage
    after_gov_bbl = Column(Float, default=0.0)
    after_gsv_bbl = Column(Float, default=0.0)
    after_bsw_bbl = Column(Float, default=0.0)
    after_nsv_bbl = Column(Float, default=0.0)
    after_lt_bbl = Column(Float, default=0.0)
    after_mt = Column(Float, default=0.0)
    
    # NET (AFTER - BEFORE)
    net_gov_bbl = Column(Float, default=0.0)
    net_gsv_bbl = Column(Float, default=0.0)
    net_bsw_bbl = Column(Float, default=0.0)
    net_nsv_bbl = Column(Float, default=0.0)
    net_lt_bbl = Column(Float, default=0.0)
    net_mt = Column(Float, default=0.0)


class TOAYadeStage(Base):
    """TOA YADE stage details"""
    __tablename__ = "toa_yade_stage"
    
    id = Column(Integer, primary_key=True)
    voyage_id = Column(Integer, ForeignKey("yade_voyage.id", ondelete="CASCADE"), index=True, nullable=False)
    stage = Column(String(10), nullable=False)
    
    gov_bbl = Column(Float, default=0.0)
    gsv_bbl = Column(Float, default=0.0)
    bsw_pct = Column(Float, default=0.0)
    bsw_bbl = Column(Float, default=0.0)
    nsv_bbl = Column(Float, default=0.0)
    lt = Column(Float, default=0.0)
    mt = Column(Float, default=0.0)
    fw_bbl = Column(Float, default=0.0)
    
    __table_args__ = (UniqueConstraint("voyage_id", "stage", name="uq_toa_stage_voyage_stage"),)


class YadeVesselMappingRecord(Base):
    __tablename__ = "yade_vessel_mapping"

    id = Column(Integer, primary_key=True, autoincrement=True)
    record_id = Column(String(64), unique=True, nullable=False, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)

    s_no = Column(Integer, nullable=False)
    date = Column(Date, nullable=False, index=True)

    yade_dispatch = Column(Float, nullable=False, default=0.0)
    vessel_receipt = Column(Float, nullable=False, default=0.0)
    diff_y_vs_v = Column(Float, nullable=False, default=0.0)
    fso_receipt = Column(Float, nullable=False, default=0.0)
    diff_v_vs_tt = Column(Float, nullable=False, default=0.0)
    remarks = Column(String(500), nullable=True)

    yade_ids_json = Column(Text, nullable=True)
    vessel_ids_json = Column(Text, nullable=True)
    fso_ids_json = Column(Text, nullable=True)

    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(DateTime, onupdate=func.now())
    laycan_start = Column(Date, nullable=True)
    laycan_end = Column(Date, nullable=True)

    location = relationship("Location")

    __table_args__ = (
        Index('idx_yvm_location_date', 'location_id', 'date'),
    )

class YadeLoadOffload(Base):
    __tablename__ = "yade_load_offload_table"

    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)
    voyage_id = Column(Integer, ForeignKey("yade_voyage.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    date = Column(Date, nullable=False, index=True)
    convoy_no = Column(String(64), nullable=True)
    yade_no = Column(String(64), nullable=True)

    rob_qty_bbl = Column(Float, nullable=False, default=0.0)
    rob_fw_bbl = Column(Float, nullable=False, default=0.0)
    tob_qty_bbl = Column(Float, nullable=False, default=0.0)
    tob_fw_bbl = Column(Float, nullable=False, default=0.0)
    net_qty_bbl = Column(Float, nullable=False, default=0.0)
    net_fw_bbl = Column(Float, nullable=False, default=0.0)

    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(DateTime, onupdate=func.now())

    location = relationship("Location")
    voyage = relationship("YadeVoyage")

    __table_args__ = (
        Index('idx_yllo_location_date', 'location_id', 'date'),
    )

# ============================================================================
# TANKER TRANSACTIONS (LOCATION-SPECIFIC)
# ============================================================================

class TankerTransaction(Base):
    """Tanker dispatch transactions - location-specific"""
    __tablename__ = "tanker_transactions"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    
    # Top metadata
    tanker_name = Column(String(100), nullable=False)
    chassis_no = Column(String(100), nullable=True)
    convoy_no = Column(String(100), nullable=False)
    transaction_date = Column(Date, nullable=False)
    transaction_time = Column(Time, nullable=False)
    cargo = Column(String(50), nullable=False)
    destination = Column(String(100), nullable=False)
    loading_bay = Column(String(100), nullable=True)
    
    # Compartment (single tank) and Manhole (C1 or C2)
    compartment = Column(String(10), nullable=False)
    manhole = Column(String(10), nullable=False)
    
    # Dips
    total_dip_cm = Column(Float, nullable=False)
    total_dip_mm = Column(Float, nullable=False)
    water_dip_cm = Column(Float, nullable=False)
    water_dip_mm = Column(Float, nullable=False)
    
    # Temperatures
    tank_temp_c = Column(Float, nullable=True)
    tank_temp_f = Column(Float, nullable=True)
    sample_temp_c = Column(Float, nullable=True)
    sample_temp_f = Column(Float, nullable=True)
    
    # Observed properties
    api_observed = Column(Float, nullable=True)
    density_observed = Column(Float, nullable=True)
    
    # BS&W
    bsw_pct = Column(Float, nullable=False, default=0.0)
    
    # Volumes (all in bbls, converted from litres using 158.987)
    total_volume_bbl = Column(Float, nullable=False)
    water_volume_bbl = Column(Float, nullable=False)
    gov_bbl = Column(Float, nullable=False)
    api60 = Column(Float, nullable=True)
    vcf = Column(Float, nullable=True)
    gsv_bbl = Column(Float, nullable=False)
    bsw_vol_bbl = Column(Float, nullable=False)
    nsv_bbl = Column(Float, nullable=False)
    lt = Column(Float, nullable=True)
    mt = Column(Float, nullable=True)
    
    # Seal numbers (4 seals: C1, C2, M1, M2)
    seal_c1 = Column(String(100), nullable=True)
    seal_c2 = Column(String(100), nullable=True)
    seal_m1 = Column(String(100), nullable=True)
    seal_m2 = Column(String(100), nullable=True)
    
    # Remarks
    remarks = Column(String(500), nullable=True)
    
    # Audit fields
    created_by = Column(String(50), nullable=False, default='system')
    created_at = Column(DateTime, server_default=func.now())
    updated_by = Column(String(50), nullable=True)
    updated_at = Column(DateTime, nullable=True)

    receipt = relationship("TankerReceipt", back_populates="dispatch", uselist=False)
    
    # Relationship
    location = relationship("Location", back_populates="tanker_transactions")


class TOATanker(Base):
    """TOA (Transfer of Account) for Tanker"""
    __tablename__ = "toa_tanker"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    
    tanker_name = Column(String(100), nullable=False)
    transaction_date = Column(Date, nullable=False)
    waybill_no = Column(String(100), nullable=True)
    destination = Column(String(100), nullable=True)
    
    # Compartment readings
    compartment = Column(String(10), nullable=False)
    dip_mm = Column(Float, nullable=False)
    volume_litres = Column(Float, nullable=False)
    volume_bbl = Column(Float, nullable=False)
    
    # Temperature and density
    temperature_c = Column(Float, nullable=True)
    api_observed = Column(Float, nullable=True)
    api60 = Column(Float, nullable=True)
    
    # Volume calculations
    gov_bbl = Column(Float, nullable=True)
    gsv_bbl = Column(Float, nullable=True)
    nsv_bbl = Column(Float, nullable=True)
    
    created_at = Column(DateTime, server_default=func.now())


# ============================================================================
# OUT-TURN REPORT (LOCATION-SPECIFIC)
# ============================================================================

class OTRRecord(Base):
    """Out-Turn Report records - location-specific"""
    __tablename__ = "otr_records"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    
    ticket_id = Column(String(100), index=True, nullable=False)
    tank_id = Column(String(50), nullable=True)
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=False)
    operation = Column(String(20), nullable=False)
    
    dip_cm = Column(Float, nullable=True)
    total_volume_bbl = Column(Float, nullable=True)
    water_cm = Column(Float, nullable=True)
    free_water_bbl = Column(Float, nullable=True)
    gov_bbl = Column(Float, nullable=True)
    api60 = Column(Float, nullable=True)
    vcf = Column(Float, nullable=True)
    gsv_bbl = Column(Float, nullable=True)
    bsw_vol_bbl = Column(Float, nullable=True)
    nsv_bbl = Column(Float, nullable=True)
    lt = Column(Float, nullable=True)
    mt = Column(Float, nullable=True)
    net_rece_disp_bbls = Column(Float, nullable=True)
    net_water_rece_disp_bbls = Column(Float, nullable=True)
    
    created_at = Column(DateTime, server_default=func.now())
    
    # Relationship
    location = relationship("Location", back_populates="otr_records")

def ensure_otr_net_columns():
    from sqlalchemy import inspect
    from db import engine
    if not engine:
        return False
    insp = inspect(engine)
    cols = set()
    try:
        cols = set([c["name"] if isinstance(c, dict) else c for c in insp.get_columns("otr_records")])
    except Exception:
        pass
    to_add = []
    if "net_rece_disp_bbls" not in cols:
        to_add.append("net_rece_disp_bbls")
    if "net_water_rece_disp_bbls" not in cols:
        to_add.append("net_water_rece_disp_bbls")
    if not to_add:
        return True
    try:
        with engine.begin() as conn:
            for col in to_add:
                conn.execute(f"ALTER TABLE otr_records ADD COLUMN {col} FLOAT")
        return True
    except Exception:
        return False

# ============================================================================
# OTR VESSEL (NEW)
# ============================================================================

# In models.py - Update OTRVessel class

class OTRVessel(Base):
    """OTR Vessel - Direct table entry for vessel operations"""
    __tablename__ = "otr_vessel"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    
    # Entry fields
    date = Column(Date, nullable=False, index=True)
    time = Column(String(5), nullable=False)  # HH:MM format
    shuttle_no = Column(String(50), nullable=False, index=True)
    vessel_id = Column(Integer, ForeignKey("vessels.id"), nullable=False)
    operation_id = Column(Integer, ForeignKey("vessel_operations.id"), nullable=False)
    
    # Stock values
    opening_stock = Column(Float, nullable=False, default=0.0)
    opening_water = Column(Float, nullable=False, default=0.0)  # ✅ NEW
    closing_stock = Column(Float, nullable=False, default=0.0)
    closing_water = Column(Float, nullable=False, default=0.0)  # ✅ NEW
    net_receipt_dispatch = Column(Float, nullable=False, default=0.0)
    net_water = Column(Float, nullable=False, default=0.0)  # ✅ NEW
    
    # Additional info
    remarks = Column(String(500), nullable=True)
    
    # Audit fields
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_by = Column(String(100), nullable=True)
    updated_at = Column(DateTime, onupdate=func.now())
    
    # Relationships
    location = relationship("Location")
    vessel = relationship("Vessel")
    operation = relationship("VesselOperation")

    def __repr__(self):
        return f"<OTRVessel(date='{self.date}', vessel_id={self.vessel_id}, shuttle='{self.shuttle_no}')>"

# ============================================================================
# FSO OPERATIONS
# ============================================================================

# In models.py - Update FSOOperation class

class FSOOperation(Base):
    """FSO-Operations table for Agge, Utapate, and Lagos (HO)"""
    __tablename__ = 'fso_operations'
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey('locations.id'), nullable=False)
    fso_vessel = Column(String(50), nullable=False)
    
    # Entry fields
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=False)
    shuttle_no = Column(String(50), nullable=False)
    vessel_name = Column(String(100), nullable=False)
    operation = Column(String(50), nullable=False)
    
    # Stock values (in bbls)
    opening_stock = Column(Float, nullable=False)
    opening_water = Column(Float, nullable=False, default=0.0)  # ✅ NEW
    closing_stock = Column(Float, nullable=False)
    closing_water = Column(Float, nullable=False, default=0.0)  # ✅ NEW
    net_receipt_dispatch = Column(Float, nullable=False)
    net_water = Column(Float, nullable=False, default=0.0)  # ✅ NEW
    vessel_quantity = Column(Float, nullable=True)
    variance = Column(Float, nullable=True)  # ✅ NEW
    
    remarks = Column(Text, nullable=True)
    
    # Audit fields
    created_by = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_by = Column(String(50), nullable=True)
    updated_at = Column(DateTime, nullable=True)
    
    # Relationship
    location = relationship("Location", back_populates="fso_operations")

    def __repr__(self):
        return f"<FSOOperation(id={self.id}, fso='{self.fso_vessel}', date='{self.date}')>"


class FSOMaterialBalance(Base):
    __tablename__ = "fso_mb_table"

    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)
    fso_vessel = Column(String(50), nullable=False)
    date = Column(Date, nullable=False, index=True)

    opening_stock = Column(Float, nullable=False, default=0.0)
    opening_water = Column(Float, nullable=False, default=0.0)
    receipts = Column(Float, nullable=False, default=0.0)
    exports = Column(Float, nullable=False, default=0.0)
    closing_stock = Column(Float, nullable=False, default=0.0)
    closing_water = Column(Float, nullable=False, default=0.0)
    loss_gain = Column(Float, nullable=False, default=0.0)

    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(DateTime, onupdate=func.now())

    location = relationship("Location")

    __table_args__ = (
        UniqueConstraint("location_id", "fso_vessel", "date", name="uq_fso_mb_loc_vessel_date"),
        Index("idx_fso_mb_location_date", "location_id", "date"),
        Index("idx_fso_mb_vessel", "fso_vessel"),
    )

    def __repr__(self):
        return (
            f"<FSOMaterialBalance(loc={self.location_id}, vessel='{self.fso_vessel}', date='{self.date}')>"
        )

# ============================================================================
# CONVOY STATUS SNAPSHOTS (YADE / VESSEL)
# ============================================================================

class ConvoyStatusYade(Base):
    """Daily YADE convoy status snapshot for dashboards."""
    __tablename__ = "convoy_status_yade"
    __table_args__ = (
        UniqueConstraint("location_id", "date", "yade_barge_id", name="uq_convoy_yade_loc_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    yade_barge_id = Column(Integer, ForeignKey("yade_barges.id"), nullable=False, index=True)
    convoy_no = Column(String(64), nullable=True)
    stock_display = Column(String(200), nullable=True)
    stock_value_bbl = Column(Float, nullable=True)
    status = Column(String(64), nullable=False)
    notes = Column(String(255), nullable=True)
    created_by = Column(String(64), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(DateTime, onupdate=func.now())

    location = relationship("Location")
    yade = relationship("YadeBarge")

    def __repr__(self):
        return (
            f"<ConvoyStatusYade(date={self.date}, yade='{self.yade_barge_id}', "
            f"status='{self.status}')>"
        )


class ConvoyStatusVessel(Base):
    """Daily vessel convoy status snapshot for dashboards."""
    __tablename__ = "convoy_status_vessel"
    __table_args__ = (
        UniqueConstraint("location_id", "date", "vessel_name", name="uq_convoy_vessel_loc_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    vessel_id = Column(Integer, ForeignKey("vessels.id"), nullable=True, index=True)
    vessel_name = Column(String(100), nullable=False)
    shuttle_no = Column(String(64), nullable=True)
    stock_display = Column(String(200), nullable=True)
    stock_value_bbl = Column(Float, nullable=True)
    status = Column(String(64), nullable=False)
    notes = Column(String(255), nullable=True)
    created_by = Column(String(64), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(DateTime, onupdate=func.now())

    location = relationship("Location")
    vessel = relationship("Vessel")

    def __repr__(self):
        return (
            f"<ConvoyStatusVessel(date={self.date}, vessel='{self.vessel_name}', "
            f"status='{self.status}')>"
        )

# ============================================================================
# SECURITY & AUDIT
# ============================================================================

class Task(Base):
    """Workflow tasks for approvals and alerts"""
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    task_type = Column(String(50), nullable=False, default=TaskType.INFO.value)
    status = Column(String(20), nullable=False, default=TaskStatus.PENDING.value)
    priority = Column(String(20), nullable=False, default="NORMAL")
    resource_type = Column(String(100), nullable=True)
    resource_id = Column(String(100), nullable=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    target_role = Column(String(30), nullable=False, default="supervisor")
    raised_by = Column(String(100), nullable=False)
    raised_by_role = Column(String(30), nullable=True)
    raised_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    approved_by = Column(String(100), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String(100), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolution_notes = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)

    # Relationships
    activities = relationship("TaskActivity", back_populates="task", cascade="all, delete-orphan")


# ============================================================================
# SHARING (FILE UPLOADS)
# ============================================================================

class SharedFile(Base):
    """Internal file sharing storage."""
    __tablename__ = "shared_files"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    unique_id = Column(String(64), nullable=False, unique=True, index=True)

    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True, index=True)
    filename = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    data = Column(LargeBinary, nullable=False)
    remarks = Column(Text, nullable=True)

    uploaded_by = Column(String(100), nullable=False)
    uploaded_by_role = Column(String(30), nullable=True)
    uploaded_at = Column(DateTime, server_default=func.now())

    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_by = Column(String(100), nullable=True)
    deleted_at = Column(DateTime, nullable=True)

    last_updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    location = relationship("Location")

    def __repr__(self):
        return f"<SharedFile(unique_id={self.unique_id}, filename='{self.filename}', size={self.size_bytes})>"


class ExportProcess(Base):
    __tablename__ = "export_processes"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)
    terminal_label = Column(String(100), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    ref_no = Column(String(100), nullable=True, index=True)
    status_overall = Column(String(50), nullable=False, default="UPCOMING")
    current_stage_code = Column(String(50), nullable=True, index=True)
    is_completed = Column(Boolean, default=False, nullable=False)
    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(DateTime, onupdate=func.now())
    laycan_start = Column(Date, nullable=True)
    laycan_end = Column(Date, nullable=True)

    location = relationship("Location")
    stages = relationship("ExportStageProgress", back_populates="export", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ExportProcess id={self.id} terminal='{self.terminal_label}' title='{self.title}' status='{self.status_overall}'>"


class ExportStageProgress(Base):
    __tablename__ = "export_stage_progress"
    __table_args__ = (
        UniqueConstraint("export_id", "stage_code", name="uq_export_stage"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    export_id = Column(Integer, ForeignKey("export_processes.id"), nullable=False, index=True)
    stage_code = Column(String(50), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="Pending")
    mandatory_complete = Column(Boolean, default=False, nullable=False)
    due_date = Column(Date, nullable=True)
    status_changed_at = Column(DateTime, onupdate=func.now())
    due_notified_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)
    completed_by = Column(String(64), nullable=True)
    completed_overdue = Column(Boolean, default=False, nullable=False)
    remarks = Column(Text, nullable=True)
    overdue_reason = Column(Text, nullable=True)
    updated_at = Column(DateTime, onupdate=func.now())

    export = relationship("ExportProcess", back_populates="stages")
    attachments = relationship("ExportAttachment", back_populates="stage", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ExportStageProgress export_id={self.export_id} stage='{self.stage_code}' status='{self.status}'>"


class ExportAttachment(Base):
    __tablename__ = "export_attachments"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    stage_id = Column(Integer, ForeignKey("export_stage_progress.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    data = Column(LargeBinary, nullable=False)
    visibility = Column(String(20), nullable=False, default="global")
    assigned_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    uploaded_by = Column(String(64), nullable=True)
    uploaded_at = Column(DateTime, server_default=func.now())

    stage = relationship("ExportStageProgress", back_populates="attachments")
    assignee = relationship("User", foreign_keys=[assigned_to_user_id])

    def __repr__(self):
        return f"<ExportAttachment id={self.id} filename='{self.filename}' visibility='{self.visibility}'>"


class TaskActivity(Base):
    """Timeline entries for each task"""
    __tablename__ = "task_activities"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    username = Column(String(100), nullable=True)
    action = Column(String(50), nullable=False)
    notes = Column(Text, nullable=True)
    
    task = relationship("Task", back_populates="activities")


class RecycleBinEntry(Base):
    """Archived snapshot of deleted records (soft delete bin)."""
    __tablename__ = "recycle_bin_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    resource_type = Column(String(100), nullable=False, index=True)
    resource_id = Column(String(100), nullable=False, index=True)
    resource_label = Column(String(255), nullable=True)
    payload_json = Column(Text, nullable=False)
    reason = Column(String(255), nullable=True)
    location_id = Column(Integer, nullable=True, index=True)
    deleted_by = Column(String(100), nullable=False)
    deleted_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    deleted_at = Column(DateTime, server_default=func.now(), nullable=False)

    deleted_by_user = relationship("User", foreign_keys=[deleted_by_id])

    __table_args__ = (
        Index(
            "idx_recycle_resource_lookup",
            "resource_type",
            "resource_id",
        ),
    )

    def __repr__(self):
        return f"<RecycleBinEntry(resource_type='{self.resource_type}', resource_id='{self.resource_id}')>"


class AuditLog(Base):
    """Audit log for tracking system actions"""
    __tablename__ = "audit_log"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, server_default=func.now())
    username = Column(String(100), nullable=False)
    action = Column(String(50), nullable=False)  # LOGIN, LOGOUT, CREATE, UPDATE, DELETE, etc.
    resource_type = Column(String(100), nullable=True)  # TankTransaction, User, etc.
    resource_id = Column(String(100), nullable=True)
    details = Column(String(500), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    ip_address = Column(String(50), nullable=True)
    success = Column(Boolean, default=True)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    location = relationship("Location", foreign_keys=[location_id])
    
    def __repr__(self):
        return f"<AuditLog(user='{self.username}', action='{self.action}', time='{self.timestamp}')>"


class LoginAttempt(Base):
    """Track login attempts for security monitoring"""
    __tablename__ = "login_attempts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    username = Column(String(100), nullable=False, index=True)
    ip_address = Column(String(50), nullable=True)
    success = Column(Boolean, nullable=False)
    failure_reason = Column(String(200), nullable=True)
    
    # IP tracking fields
    ip_country = Column(String(100), nullable=True)
    ip_city = Column(String(100), nullable=True)
    ip_region = Column(String(100), nullable=True)
    
    # Device tracking fields
    device_type = Column(String(50), nullable=True)  # Desktop, Mobile, Tablet
    browser = Column(String(100), nullable=True)
    os = Column(String(100), nullable=True)
    user_agent = Column(String(500), nullable=True)
    
    # 2FA tracking
    two_factor_used = Column(Boolean, default=False, nullable=False)
    
    # Session tracking
    session_id = Column(String(64), nullable=True)


# ============================================================================
# DATABASE INDEXES FOR PERFORMANCE
# ============================================================================

# Tank transactions
Index('idx_tank_tx_location_date', TankTransaction.location_id, TankTransaction.date)
Index('idx_tank_tx_ticket', TankTransaction.ticket_id)

# OTR records
Index('idx_otr_location_date', OTRRecord.location_id, OTRRecord.date)
Index('idx_otr_ticket', OTRRecord.ticket_id)

# YADE voyages
Index('idx_yade_voyage_location', YadeVoyage.location_id, YadeVoyage.date)

# Tanker transactions
Index('idx_tanker_tx_location', TankerTransaction.location_id, TankerTransaction.transaction_date)

# Calibrations
Index('idx_tank_calibration', CalibrationTank.location_id, CalibrationTank.tank_name)
Index('idx_yade_calibration', YadeCalibration.yade_name, YadeCalibration.tank_id)

# Security & Audit
Index('idx_audit_timestamp', AuditLog.timestamp)
Index('idx_audit_user', AuditLog.user_id, AuditLog.timestamp)
Index('idx_login_attempts', LoginAttempt.username, LoginAttempt.timestamp)

# Vessel indexes
Index('idx_vessel_name', Vessel.name)
Index('idx_vessel_operation_name', VesselOperation.operation_name)
Index('idx_location_vessel', LocationVessel.location_id, LocationVessel.vessel_id)
Index('idx_otr_vessel_vessel_id', OTRVessel.vessel_id)
Index('idx_otr_vessel_operation_id', OTRVessel.operation_id)

# FSO indexes ✅ ADDED
Index('idx_fso_location_date', FSOOperation.location_id, FSOOperation.date)
Index('idx_fso_vessel', FSOOperation.fso_vessel)
Index('idx_fso_shuttle', FSOOperation.shuttle_no)

# Export indexes
Index('idx_export_process_location', ExportProcess.location_id, ExportProcess.created_at)
Index('idx_export_process_terminal', ExportProcess.terminal_label, ExportProcess.created_at)
Index('idx_export_stage_export', ExportStageProgress.export_id, ExportStageProgress.stage_code)
Index('idx_export_attachment_stage', ExportAttachment.stage_id, ExportAttachment.uploaded_at)
# ============================================================================
# NOTE
# ============================================================================
# Avoid side effects at import time: table creation is handled by `db.init_db()`.
class ReportDefinition(Base):
    __tablename__ = "report_definitions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    config_json = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    created_by = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    
class ReportAccess(Base):
    """
    Controls which users/roles/locations can access specific reports.
    Admins can grant access at role level, user level, or location level.
    """
    __tablename__ = "report_access"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("report_definitions.id", ondelete="CASCADE"), nullable=False)
    
    # Access can be granted by role, specific user, or location
    role = Column(String(30), nullable=True)  # e.g., "manager", "supervisor", "operator"
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"), nullable=True)
    
    # Audit fields
    granted_by = Column(String(50), nullable=False)
    granted_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    report = relationship("ReportDefinition", backref="access_grants")
    user = relationship("User")
    location = relationship("Location")
    
    def __repr__(self):
        return f"<ReportAccess(report_id={self.report_id}, role='{self.role}', user_id={self.user_id})>"


# Index for faster access control queries
Index('idx_report_access_lookup', ReportAccess.report_id, ReportAccess.role, ReportAccess.user_id)

# =============================================================================
# REPORT ENHANCEMENT MODELS - Add at the end of models.py
# =============================================================================

class ReportTemplate(Base):
    """Reusable report templates that can be cloned across locations."""
    __tablename__ = "report_templates"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    config_json = Column(Text, nullable=False)  # Full report configuration
    category = Column(String(100), nullable=True)  # e.g., "Operations", "Finance", "Production"
    is_global = Column(Boolean, default=True)  # Available to all locations
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime. utcnow)
    version = Column(Integer, default=1)
    
    def __repr__(self):
        return f"<ReportTemplate(id={self.id}, name='{self. name}')>"


class ReportSchedule(Base):
    """Scheduled report execution configuration."""
    __tablename__ = "report_schedules"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("report_definitions.id"), nullable=False)
    name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    
    # Schedule configuration
    frequency = Column(String(50), nullable=False)  # daily, weekly, monthly, custom
    cron_expression = Column(String(100), nullable=True)  # For custom schedules
    run_time = Column(String(10), nullable=True)  # HH:MM format
    run_day = Column(Integer, nullable=True)  # Day of week (0-6) or day of month (1-31)
    timezone = Column(String(50), default="UTC")
    
    # Filter overrides for scheduled runs
    filter_overrides_json = Column(Text, nullable=True)
    
    # Export configuration
    export_formats = Column(String(255), default="xlsx,pdf")  # Comma-separated
    
    # Destination configuration (JSON array)
    destinations_json = Column(Text, nullable=True)
    
    # Notification settings
    notify_on_success = Column(Boolean, default=False)
    notify_on_failure = Column(Boolean, default=True)
    notification_emails = Column(Text, nullable=True)  # Comma-separated emails
    
    # Execution tracking
    last_run_at = Column(DateTime, nullable=True)
    last_run_status = Column(String(50), nullable=True)  # success, failed, running
    last_run_message = Column(Text, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    report = relationship("ReportDefinition", backref="schedules")
    
    def __repr__(self):
        return f"<ReportSchedule(id={self. id}, report_id={self. report_id}, frequency='{self.frequency}')>"


class ReportDestination(Base):
    """Configured export destinations for reports."""
    __tablename__ = "report_destinations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    destination_type = Column(String(50), nullable=False)  # network, email, sftp, s3, azure, sharepoint
    is_active = Column(Boolean, default=True)
    
    # Connection configuration (encrypted JSON)
    config_json = Column(Text, nullable=False)
    
    # Validation
    last_test_at = Column(DateTime, nullable=True)
    last_test_status = Column(String(50), nullable=True)
    
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<ReportDestination(id={self. id}, name='{self.name}', type='{self. destination_type}')>"


class ReportExecutionLog(Base):
    """Log of all report executions (manual and scheduled)."""
    __tablename__ = "report_execution_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("report_definitions.id"), nullable=False)
    schedule_id = Column(Integer, ForeignKey("report_schedules.id"), nullable=True)
    
    execution_type = Column(String(50), nullable=False)  # manual, scheduled
    status = Column(String(50), nullable=False)  # started, success, failed
    
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    
    row_count = Column(Integer, nullable=True)
    export_format = Column(String(20), nullable=True)
    destination_type = Column(String(50), nullable=True)
    destination_path = Column(Text, nullable=True)
    
    error_message = Column(Text, nullable=True)
    executed_by = Column(String(255), nullable=True)
    
    # Filters used
    filters_json = Column(Text, nullable=True)
    
    def __repr__(self):
        return f"<ReportExecutionLog(id={self.id}, report_id={self.report_id}, status='{self.status}')>"

# ============================================================================
# DYNAMIC TABLE CREATION FOR CUSTOM TABS
# ============================================================================

def create_custom_tab_table(table_name: str, columns: list, location_id: int) -> bool:
    """
    Dynamically create a database table for a custom tab.
    
    Args:
        table_name: Name of the table to create
        columns: List of column definitions with name, label, type, formula
        location_id: Location ID for the table
    
    Returns:
        True if table was created successfully, False otherwise
    """
    from sqlalchemy import Table, MetaData, inspect
    from sqlalchemy.exc import OperationalError, ProgrammingError, DatabaseError
    from db import flex_engine
    from logger import log_info, log_error, log_warning
    
    log_info(f"Attempting to create custom table '{table_name}' for location_id={location_id}")
    
    if not flex_engine:
        log_error("Database engine not available. Check db.py configuration.")
        raise RuntimeError("Database engine not available. Check db.py configuration.")
    
    # Test database connection
    try:
        with flex_engine.connect() as conn:
            log_info(f"Database connection verified for table '{table_name}' creation")
    except Exception as conn_err:
        log_error(f"Failed to connect to database: {str(conn_err)}", exc_info=True)
        raise RuntimeError(f"Database connection failed: {str(conn_err)}")
    
    try:
        # Check if table already exists
        inspector = inspect(flex_engine)
        existing_tables = inspector.get_table_names()
        
        if table_name in existing_tables:
            log_info(f"Table '{table_name}' already exists. Skipping creation.")
            return True  # Table already exists
        
        log_info(f"Table '{table_name}' does not exist. Creating new table...")
        
        # Use the existing Base.metadata to ensure FK references work
        metadata = Base.metadata
        
        # Define standard columns
        table_columns = [
            Column('id', Integer, primary_key=True, autoincrement=True),
            Column('location_id', Integer, nullable=False),
            Column('tx_date', Date, nullable=True),
            Column('created_by', String(64), nullable=True),
            Column('created_at', DateTime, server_default=func.now()),
            Column('updated_by', String(64), nullable=True),
            Column('updated_at', DateTime, onupdate=func.now()),
        ]
        
        log_info(f"Processing {len(columns)} custom column definitions for table '{table_name}'")
        
        # Add custom columns based on definitions
        for col_def in columns:
            col_name = col_def.get('name', '').strip()
            col_type = col_def.get('type', 'text')
            
            if not col_name:
                log_warning(f"Skipping column with empty name in table '{table_name}'")
                continue
                
            if col_name in ['id', 'location_id', 'created_by', 'created_at', 'updated_at', 'tx_date', 'updated_by']:
                log_warning(f"Skipping reserved column name '{col_name}' in table '{table_name}'")
                continue  # Skip reserved names
            
            # Map column types
            if col_type == 'date':
                sql_type = Date
            elif col_type == 'number':
                sql_type = Float
            else:  # text
                sql_type = String(255)
            
            table_columns.append(Column(col_name, sql_type, nullable=True))
            log_info(f"Added column '{col_name}' ({col_type}) to table '{table_name}'")
        
        # Create the table
        log_info(f"Creating table '{table_name}' with {len(table_columns)} columns in database...")
        custom_table = Table(table_name, metadata, *table_columns)
        metadata.create_all(flex_engine)
        log_info(f"✅ Successfully created table '{table_name}'")
        return True
        
    except OperationalError as e:
        error_msg = f"Database operational error creating table '{table_name}': {str(e)}. Check database connection and permissions."
        log_error(f"❌ {error_msg}", exc_info=True)
        raise RuntimeError(error_msg) from e
    except ProgrammingError as e:
        error_msg = f"Database programming error creating table '{table_name}': {str(e)}. Check SQL syntax and column definitions."
        log_error(f"❌ {error_msg}", exc_info=True)
        raise RuntimeError(error_msg) from e
    except DatabaseError as e:
        error_msg = f"Database error creating table '{table_name}': {str(e)}. Check database configuration."
        log_error(f"❌ {error_msg}", exc_info=True)
        raise RuntimeError(error_msg) from e
    except Exception as e:
        error_msg = f"Unexpected error creating custom table '{table_name}': {str(e)}"
        log_error(f"❌ {error_msg}", exc_info=True)
        raise RuntimeError(error_msg) from e


def get_custom_table_model(table_name: str):
    """
    Get a dynamic SQLAlchemy model for a custom tab table.
    
    Args:
        table_name: Name of the custom table
    
    Returns:
        A SQLAlchemy model class or None if table doesn't exist
    """
    from sqlalchemy import Table, MetaData, inspect
    from sqlalchemy.exc import NoSuchTableError, DatabaseError
    from db import flex_engine, engine
    from logger import log_info, log_error, log_warning

    engines_to_try = []
    if flex_engine:
        engines_to_try.append(("flex", flex_engine))
    if engine:
        engines_to_try.append(("primary", engine))

    if not engines_to_try:
        log_error(f"Database engines not available when trying to get model for table '{table_name}'")
        return None

    for eng_name, eng in engines_to_try:
        try:
            inspector = inspect(eng)
            existing_tables = inspector.get_table_names()

            if table_name not in existing_tables:
                continue

            log_info(f"Reflecting table '{table_name}' from {eng_name} database...")
            metadata = MetaData()
            table = Table(table_name, metadata, autoload_with=eng)

            mapper_args = {}
            if not table.primary_key or len(table.primary_key.columns) == 0:
                # Fallback: use first column as a synthetic primary key to allow ORM mapping
                first_col = list(table.columns)[0]
                mapper_args['primary_key'] = [first_col]
                log_warning(f"Table '{table_name}' has no primary key; using '{first_col.name}' as surrogate PK for mapping")

            Model = type(f"Custom_{table_name}", (Base,), {"__table__": table, "__mapper_args__": mapper_args})
            log_info(f"Successfully created model for table '{table_name}' from {eng_name} database")
            return Model

        except NoSuchTableError as e:
            log_warning(f"Table '{table_name}' not found in {eng_name} database: {str(e)}")
            continue
        except DatabaseError as e:
            log_error(f"Database error reflecting table '{table_name}' from {eng_name}: {str(e)}", exc_info=True)
            continue
        except Exception as e:
            log_error(f"Unexpected error reflecting custom table '{table_name}' from {eng_name}: {str(e)}", exc_info=True)
            continue

    log_warning(f"Table '{table_name}' does not exist in primary or flex databases.")
    return None

def drop_custom_tab_table(table_name: str) -> bool:
    """
    Drop a custom tab table from the database.
    
    Args:
        table_name: Name of the table to drop
    
    Returns:
        True if successful, False otherwise
    """
    from sqlalchemy import Table, MetaData, inspect
    from db import flex_engine
    
    if not flex_engine:
        return False
    
    inspector = inspect(flex_engine)
    if table_name not in inspector.get_table_names():
        return True  # Already doesn't exist
    
    try:
        metadata = MetaData()
        table = Table(table_name, metadata, autoload_with=flex_engine)
        table.drop(flex_engine)
        return True
    except Exception as e:
        print(f"Error dropping custom table {table_name}: {e}")
        return False
