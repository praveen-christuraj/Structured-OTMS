"""
Location-specific configuration management.
Allows each location to have customized settings for operations, validations, etc.
"""

from typing import Dict, Any, List, Optional
import json
from sqlalchemy.orm import Session
import uuid


# ==================== DEFAULT CONFIGURATION ====================
DEFAULT_CONFIG = {
    "page_visibility": {
        "show_tank_transactions": True,
        "show_tanker_transactions": True,
        "show_yade_transactions": True,
        "show_yade_vessel_mapping": True,
        "show_yade_tracking": True,
        "show_view_transactions": True,
        "show_vessel_operations": True,
        "show_fso_operations": True,
        "show_otr": True,
        "show_reporting": True,
        "show_reports": True,
        "show_material_balance": True,
        "show_bccr": True,
        "show_convoy_status": True,
        "show_toa_yade": True,
        "show_sharing": True,
    },

    "page_access": {
        "Tank Transactions": True,
        "Yade Transactions": True,
        "Tanker Transactions": True,
        "Yade Tracking": True,
        "Yade-Vessel Mapping": True,
        "Convoy Status": True,
        "OTR-Vessel": True,
        "FSO-Operations": True,
        "TOA-Yade": True,
        "OTR": True,
        "BCCR": True,
        "Material Balance": True,
        "Reporting": True,
    },
    # NOTE: We will use the nested "tabs_access" -> "Tank Transactions" for per-tab toggles.
    "tabs_access": {
        "Tank Transactions": {
            # Canonical tab labels (exactly as shown in UI)
            "Tank Entry": True,
            "Meter Records": False,
            "Condensate Records": False,
            "Produced Water Records": False,
            "Production": False,
        },
        "FSO-Operations": {
            "📊 OTR": True,
            "📈 Material Balance": True
        },
        "BCCR": {
            "Mapping": True,
            "BCCR Report": True
        },
        "Yade-Vessel Mapping": {
            "Mapping": True,
            "Comparison": True
        }
    },
    "tank_transactions": {
        # Legacy list (kept for backward compatibility with older code paths)
        "enabled_operations": [
            "Opening Stock",
            "Receipt",
            "Receipt from Agu",
            "Receipt from OFS",
            "OKW Receipt",
            "ANZ Receipt",
            "Other Receipts",
            "ITT - Receipt",
            "Dispatch to barge",
            "Other Dispatch",
            "ITT - Dispatch",
            "Settling",
            "Draining"
        ],
        "product_types": ["CRUDE", "CONDENSATE", "DPK", "AGO", "PMS"],
        "max_days_backward": 30,
        "allow_future_dates": False,
        "auto_generate_ticket_id": True,
        "ticket_id_prefix": ""
    },
    "yade_transactions": {
        "enabled_cargo_types": ["OKW", "ANZ", "CONDENSATE", "CRUDE"],
        "enabled_destinations": [
            "NEMBE CK", "BONNY", "BRASS", "FORCADOS",
            "ESCRAVOS", "WARRI", "PORT HARCOURT"
        ],
        "enabled_loading_berths": ["BERTH 1", "BERTH 2", "BERTH 3"],
        "enable_seal_tracking": True,
        "auto_generate_voyage_no": False
    },
    "otr": {
        "auto_calculate_volumes": True,
        "require_calibration_data": True,
        "enable_temperature_correction": True,
        "decimal_precision": 2,
        "volume_unit": "BBL",
        "temperature_unit": "C"
    },
    "otr_vessel": {
        "preferred_vessel_ids": []
    },
    "ui_customization": {
        "show_quick_entry_mode": True,
        "enable_bulk_upload": False,
        "default_date": "today"
    },

    "convoy_status": {
        "yade_statuses": [],
        "vessel_statuses": [],
    }
    ,
    "service_types": []
}


# ==================== LocationConfig CLASS ====================
class LocationConfig:
    """Manage location-specific configurations"""

    @staticmethod
    def get_config(session: Session, location_id: int) -> Dict[str, Any]:
        """
        Get configuration for a specific location.

        Order of precedence (lowest → highest):
        1. Global defaults (DEFAULT_CONFIG)
        2. Location-based defaults (by location code)
        3. Saved configuration from Location Settings (DB overrides)
        """
        from models import Location, LocationConfiguration

        # Start with default config (deep-copy nested dicts to avoid mutation)
        config = DEFAULT_CONFIG.copy()
        config["page_visibility"] = DEFAULT_CONFIG["page_visibility"].copy()
        config["tank_transactions"] = DEFAULT_CONFIG["tank_transactions"].copy()
        config["yade_transactions"] = DEFAULT_CONFIG["yade_transactions"].copy()
        config["otr"] = DEFAULT_CONFIG["otr"].copy()
        config["otr_vessel"] = DEFAULT_CONFIG["otr_vessel"].copy()
        config["ui_customization"] = DEFAULT_CONFIG["ui_customization"].copy()
        config["tabs_access"] = {
            k: (v.copy() if isinstance(v, dict) else v)
            for k, v in DEFAULT_CONFIG.get("tabs_access", {}).items()
        }

        # -------- 2) Location-based defaults (by code) --------
        loc = session.query(Location).filter(Location.id == location_id).one_or_none()
        if loc:
            code = (loc.code or "").upper()

            # TANKER LOCATIONS (Ndoni, Aggu, Oguali, Ogini)
            if code in ["NDONI", "AGGU", "OGUALI", "OGINI"]:
                config["page_visibility"]["show_tanker_transactions"] = True

            # YADE LOCATIONS (Ndoni only for now) – defaults only
            if code == "NDONI":
                config["page_visibility"]["show_yade_transactions"] = True
                config["page_visibility"]["show_toa_yade"] = True

            # Tank transactions (enabled for all locations by default)
            config["page_visibility"]["show_tank_transactions"] = True

        # -------- 3) Load from database if exists (DB overrides) --------
        db_config = session.query(LocationConfiguration).filter(
            LocationConfiguration.location_id == location_id
        ).one_or_none()

        if db_config and db_config.config_json:
            try:
                stored_config = json.loads(db_config.config_json)
                # Deep merge stored config into current config
                for key, value in stored_config.items():
                    if isinstance(value, dict) and key in config:
                        # nested deep-merge
                        if key == "tabs_access":
                            tabs_def = config["tabs_access"]
                            for page_name, tab_dict in value.items():
                                if isinstance(tab_dict, dict):
                                    tabs_def.setdefault(page_name, {})
                                    tabs_def[page_name].update(tab_dict)
                                else:
                                    tabs_def[page_name] = tab_dict
                        else:
                            config[key].update(value)
                    else:
                        config[key] = value
            except Exception:
                # Use defaults + location-based if parsing fails
                pass

        return config

    @staticmethod
    def save_config(session: Session, location_id: int, config: Dict[str, Any]) -> bool:
        """Save configuration for a location"""
        from models import LocationConfiguration

        try:
            db_config = session.query(LocationConfiguration).filter(
                LocationConfiguration.location_id == location_id
            ).one_or_none()

            config_json = json.dumps(config)

            if db_config:
                db_config.config_json = config_json
            else:
                db_config = LocationConfiguration(
                    location_id=location_id,
                    config_json=config_json
                )
                session.add(db_config)

            session.commit()
            return True
        except Exception as e:
            session.rollback()
            raise e

    @staticmethod
    def reset_to_default(session: Session, location_id: int) -> bool:
        """Reset location configuration to default"""
        from models import LocationConfiguration

        try:
            db_config = session.query(LocationConfiguration).filter(
                LocationConfiguration.location_id == location_id
            ).one_or_none()

            if db_config:
                session.delete(db_config)
                session.commit()

            return True
        except Exception as e:
            session.rollback()
            raise e

    @staticmethod
    def get_enabled_operations(session: Session, location_id: int) -> list:
        """Legacy helper for old code paths (tank_transactions.enabled_operations)."""
        config = LocationConfig.get_config(session, location_id)
        return config.get("tank_transactions", {}).get("enabled_operations", [])

    @staticmethod
    def is_operation_enabled(session: Session, location_id: int, operation: str) -> bool:
        """Check if a specific legacy operation is enabled for a location."""
        enabled_ops = LocationConfig.get_enabled_operations(session, location_id)
        return operation in enabled_ops

    @staticmethod
    def enable_tanker_transactions_for_location(session: Session, location_code: str) -> bool:
        """
        Enable tanker transactions for a specific location.
        Helper method for one-time setup.
        """
        from models import Location

        loc = session.query(Location).filter(Location.code == location_code).one_or_none()
        if not loc:
            return False

        config = LocationConfig.get_config(session, loc.id)
        config["page_visibility"]["show_tanker_transactions"] = True
        LocationConfig.save_config(session, loc.id, config)
        return True


# ==================== ONE-TIME SETUP UTILITY ====================
def setup_tanker_locations():
    """
    One-time setup to enable tanker transactions for the 4 locations.
    Run this once after adding locations (or it will auto-enable via get_config).
    """
    from db import get_session

    tanker_locations = ["NDONI", "AGGU", "OGUALI", "OGINI"]

    with get_session() as s:
        for code in tanker_locations:
            result = LocationConfig.enable_tanker_transactions_for_location(s, code)
            if result:
                print(f"✅ Enabled tanker transactions for {code}")
            else:
                print(f"⚠️ Location {code} not found")
        s.commit()


# ==================== SIMPLE PAGE VISIBILITY HELPERS ====================
def get_location_page_visibility(session: Session, location_id: int) -> Dict[str, bool]:
    """
    Quick helper to get page visibility settings for a location.
    Returns: {"show_tank_transactions": bool, "show_tanker_transactions": bool, ...}
    """
    config = LocationConfig.get_config(session, location_id)
    return config.get("page_visibility", {})


def get_service_types(session: Session, location_id: int) -> List[str]:
    cfg = LocationConfig.get_config(session, location_id)
    types = cfg.get("service_types", []) or []
    return [str(t) for t in types]

def add_service_type(session: Session, location_id: int, name: str) -> None:
    name = (name or "").strip()
    if not name:
        raise ValueError("Service type name required")
    cfg = LocationConfig.get_config(session, location_id)
    types = list(cfg.get("service_types", []) or [])
    if any(str(t).strip().lower() == name.lower() for t in types):
        raise ValueError("Service type already exists")
    types.append(name)
    cfg["service_types"] = types
    LocationConfig.save_config(session, location_id, cfg)

def delete_service_type(session: Session, location_id: int, name: str) -> None:
    cfg = LocationConfig.get_config(session, location_id)
    types = list(cfg.get("service_types", []) or [])
    types = [t for t in types if str(t).strip().lower() != (name or "").strip().lower()]
    cfg["service_types"] = types
    LocationConfig.save_config(session, location_id, cfg)


# ==================== TANK TRANSACTIONS TAB VISIBILITY ====================
# Canonical labels for the 5 tabs as shown in UI
_TT_TAB_LABELS = [
    "Tank Entry",
    "Meter Records",
    "Condensate Records",
    "Produced Water Records",
    "Production",
]

def get_tank_transactions_tab_visibility(session: Session, location_id: int) -> Dict[str, bool]:
    """
    Return per-tab visibility for 'Tank Transactions' page for a location.
    Keys are friendly labels exactly as shown in UI (see _TT_TAB_LABELS).
    """
    cfg = LocationConfig.get_config(session, location_id)
    tabs_access = cfg.get("tabs_access", {})
    tt_tabs = tabs_access.get("Tank Transactions", {}) or {}

    # Merge defaults with stored
    defaults = {
        "Tank Entry": True,
        "Meter Records": False,
        "Condensate Records": False,
        "Produced Water Records": False,
        "Production": False,
    }
    out = defaults.copy()
    out.update({k: bool(v) for k, v in tt_tabs.items() if k in defaults})
    return out

def save_tank_transactions_tab_visibility(session: Session, location_id: int, new_flags: Dict[str, bool]) -> None:
    """
    Persist per-tab visibility for 'Tank Transactions' under cfg['tabs_access']['Tank Transactions'].
    Only recognized tab names are stored.
    """
    cfg = LocationConfig.get_config(session, location_id)
    tabs_access = cfg.get("tabs_access", {})
    current = tabs_access.get("Tank Transactions", {}) or {}

    sanitized = {}
    for label in _TT_TAB_LABELS:
        if label in new_flags:
            sanitized[label] = bool(new_flags[label])
        else:
            # keep existing or fall back to default if not present
            sanitized[label] = bool(current.get(label, {
                "Tank Entry": True,
                "Meter Records": False,
                "Condensate Records": False,
                "Produced Water Records": False,
                "Production": False,
            }[label]))

    tabs_access["Tank Transactions"] = sanitized
    cfg["tabs_access"] = tabs_access
    LocationConfig.save_config(session, location_id, cfg)


# ==================== METERS (ASSET) & ASSIGNMENT ====================
def get_all_meters(session: Session):
    """Return all meter assets (ordered by name)."""
    from models import Meter
    return session.query(Meter).order_by(Meter.name.asc()).all()

def create_meter(session: Session, code: str, name: str, status: str = "active") -> int:
    """Create a meter asset and return its ID."""
    from models import Meter
    m = Meter(code=code.strip(), name=name.strip(), status=(status or "active"))
    session.add(m)
    session.commit()
    return int(m.id)

def delete_meter(session: Session, meter_id: int) -> None:
    """
    Delete a meter asset and any location mappings referencing it.
    Safe to call even if meter_id does not exist.
    """
    from models import Meter, LocationMeter
    session.query(LocationMeter).filter(LocationMeter.meter_id == int(meter_id)).delete()
    session.query(Meter).filter(Meter.id == int(meter_id)).delete()
    session.commit()

def get_location_meters(session: Session, location_id: int):
    """Return meter assets assigned to a location (as Meter rows)."""
    from models import Meter, LocationMeter
    q = (
        session.query(Meter)
        .join(LocationMeter, LocationMeter.meter_id == Meter.id)
        .filter(LocationMeter.location_id == int(location_id))
        .order_by(Meter.name.asc())
    )
    return q.all()

def set_location_meters(session: Session, location_id: int, meter_ids: List[int]) -> None:
    """Replace all meter assignments for a location."""
    from models import LocationMeter
    session.query(LocationMeter).filter(LocationMeter.location_id == int(location_id)).delete()
    for mid in (meter_ids or []):
        session.add(LocationMeter(location_id=int(location_id), meter_id=int(mid)))
    session.commit()


# ==================== GENERIC PER-PAGE SECTION CONFIG ====================
# Used to store JSON configs per location/page/section (e.g., meters config, condensate meters,
# produced-water dynamic columns, production dynamic columns, etc.)

def _get_cfg_row(session: Session, location_id: int, page: str, section: str):
    from models import LocationPageConfig
    return (
        session.query(LocationPageConfig)
        .filter(LocationPageConfig.location_id == int(location_id))
        .filter(LocationPageConfig.page == str(page))
        .filter(LocationPageConfig.section == str(section))
        .one_or_none()
    )

def get_page_section_config(session: Session, location_id: int, page: str, section: str) -> Dict[str, Any]:
    """
    Read a JSON config for a location/page/section.
    Returns {} if not found or JSON invalid.
    """
    row = _get_cfg_row(session, location_id, page, section)
    if not row or not getattr(row, "config_json", None):
        return {}
    try:
        return json.loads(row.config_json)
    except Exception:
        return {}

def set_page_section_config(session: Session, location_id: int, page: str, section: str, cfg: Dict[str, Any]) -> None:
    """
    Upsert a JSON config for a location/page/section.
    """
    from models import LocationPageConfig
    row = _get_cfg_row(session, location_id, page, section)
    cfg_str = json.dumps(cfg or {}, ensure_ascii=False)
    if row:
        row.config_json = cfg_str
    else:
        row = LocationPageConfig(
            location_id=int(location_id),
            page=str(page),
            section=str(section),
            config_json=cfg_str,
        )
        session.add(row)
    session.commit()


# ==================== Soft-table helpers (Produced Water / Production) ====================
def get_dynamic_table_def(session: Session, location_id: int, page: str, section: str) -> Dict[str, Any]:
    """
    Returns definition dict:
      {
        "columns": [
            {"name": "date", "label": "Date", "type": "date", "required": True},
            {"name": "stream_a", "label": "Stream A (bbl)", "type": "number"},
            {"name": "remarks", "label": "Remarks", "type": "text"}
        ]
      }
    If not configured, returns {"columns": []}.
    """
    cfg = LocationConfig.get_config(session, location_id)
    pc = cfg.setdefault("page_customization", {})
    page_bucket = pc.setdefault(page, {})
    section_bucket = page_bucket.setdefault(section, {})
    cols = section_bucket.get("columns") or []
    return {"columns": cols}

def set_dynamic_table_def(session: Session, location_id: int, page: str, section: str, new_def: Dict[str, Any]) -> None:
    """
    Save the dynamic table definition under:
      cfg["page_customization"][page][section] = {"columns": [...]}
    Only allows text/number/date types; ensures at most one 'date' column.
    Supports formula field for calculated columns.
    """
    allowed_types = {"text", "number", "date"}

    columns = list(new_def.get("columns") or [])
    # sanitize
    cleaned = []
    seen_date = False
    for c in columns:
        name = (c.get("name") or "").strip()
        label = (c.get("label") or name or "").strip()
        ctype = (c.get("type") or "text").lower()
        required = bool(c.get("required", False))
        formula = c.get("formula") or None  # New: formula support
        if not name:
            continue
        if ctype not in allowed_types:
            ctype = "text"
        if ctype == "date":
            if seen_date:
                # ignore extra date columns
                ctype = "text"
            else:
                seen_date = True
        col_def = {
            "name": name,
            "label": label or name,
            "type": ctype,
            "required": required,
        }
        # Add formula if present (for calculated columns)
        if formula:
            col_def["formula"] = formula
        cleaned.append(col_def)

    cfg = LocationConfig.get_config(session, location_id)
    pc = cfg.setdefault("page_customization", {})
    page_bucket = pc.setdefault(page, {})
    page_bucket[section] = {"columns": cleaned}

    LocationConfig.save_config(session, location_id, cfg)


# ==================== Soft-coded Operations (per-location / per-asset / per-category) ====================
OP_ASSETS = ["tank", "yade", "tanker", "vessel", "fso"]
OP_CATEGORIES = [
    "Operation",
    "FSO Vessel",
    "Opening", "Closing", "Receipt", "Dispatch", "Draining", "Others",
    "Cargo Type", "Destination", "Loading Berth"
]


def _ensure_ops_root(cfg: Dict[str, Any]) -> Dict[str, Any]:
    ops = cfg.setdefault("operations", {})
    for asset in OP_ASSETS:
        ops.setdefault(asset, {})
        for cat in OP_CATEGORIES:
            ops[asset].setdefault(cat, [])  # list of dicts: {id,name,active}
    return ops

def list_operations(
    session: Session,
    location_id: int,
    *,
    asset: Optional[str] = None,
    category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return operations defined for this location (optionally filtered)."""
    cfg = LocationConfig.get_config(session, location_id)
    ops = _ensure_ops_root(cfg)

    out = []
    assets = [asset] if asset in OP_ASSETS else OP_ASSETS
    for a in assets:
        cats = [category] if category in OP_CATEGORIES else OP_CATEGORIES
        for c in cats:
            for item in (ops[a][c] or []):
                if not isinstance(item, dict):
                    # backward compatibility (list of names)
                    item = {"id": str(uuid.uuid4()), "name": str(item), "active": True}
                out.append({"asset": a, "category": c, **item})
    return out

def add_operation(
    session: Session,
    location_id: int,
    *,
    asset: str,
    category: str,
    name: str,
    active: bool = True,
) -> Dict[str, Any]:
    """Add a new operation entry (id, name, active) to config."""
    assert asset in OP_ASSETS, "Invalid asset"
    assert category in OP_CATEGORIES, "Invalid category"
    name = (name or "").strip()
    if not name:
        raise ValueError("Operation name required")

    cfg = LocationConfig.get_config(session, location_id)
    ops = _ensure_ops_root(cfg)

    # prevent duplicates (case-insensitive) within same asset/category
    exists = any((i.get("name","").strip().lower() == name.lower()) for i in ops[asset][category])
    if exists:
        raise ValueError("Operation already exists in this category")

    new_item = {"id": str(uuid.uuid4()), "name": name, "active": bool(active)}
    ops[asset][category].append(new_item)

    cfg["operations"] = ops
    LocationConfig.save_config(session, location_id, cfg)
    return new_item

def set_operation_active(
    session: Session,
    location_id: int,
    *,
    op_id: str,
    active: bool,
) -> bool:
    cfg = LocationConfig.get_config(session, location_id)
    ops = _ensure_ops_root(cfg)
    changed = False
    for a in OP_ASSETS:
        for c in OP_CATEGORIES:
            for i in ops[a][c]:
                if i.get("id") == op_id:
                    i["active"] = bool(active)
                    changed = True
                    break
    if changed:
        cfg["operations"] = ops
        LocationConfig.save_config(session, location_id, cfg)
    return changed

def delete_operation(
    session: Session,
    location_id: int,
    *,
    op_id: str,
) -> bool:
    cfg = LocationConfig.get_config(session, location_id)
    ops = _ensure_ops_root(cfg)
    changed = False
    for a in OP_ASSETS:
        for c in OP_CATEGORIES:
            before = len(ops[a][c])
            ops[a][c] = [i for i in ops[a][c] if i.get("id") != op_id]
            if len(ops[a][c]) != before:
                changed = True
    if changed:
        cfg["operations"] = ops
        LocationConfig.save_config(session, location_id, cfg)
    return changed

def get_active_operation_names(
    session: Session,
    location_id: int,
    *,
    asset: str,
) -> List[str]:
    """Flatten active operation names for a given asset (all categories)."""
    ops = list_operations(session, location_id, asset=asset)
    return [o["name"] for o in ops if o.get("active", True)]


# ==================== Custom Tabs Management ====================
def get_custom_tabs(session: Session, location_id: int, page: str) -> List[Dict[str, Any]]:
    """
    Get all custom tabs defined for a specific page (e.g., 'tank_transactions', 'tanker_transactions').
    
    Returns list of tab definitions:
    [
        {
            "id": "unique_id",
            "name": "Custom Tab Name",
            "table_name": "custom_tab_name",  # DB table name
            "columns": [...],  # Column definitions with formulas
            "active": True
        }
    ]
    """
    cfg = LocationConfig.get_config(session, location_id)
    custom_tabs = cfg.setdefault("custom_tabs", {})
    page_tabs = custom_tabs.setdefault(page, [])
    return list(page_tabs)


def add_custom_tab(
    session: Session,
    location_id: int,
    page: str,
    tab_name: str,
    columns: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Add a new custom tab to a page.
    
    Args:
        session: Database session
        location_id: Location ID
        page: Page name (e.g., 'tank_transactions')
        tab_name: Display name for the tab
        columns: List of column definitions
    
    Returns:
        The created tab definition
    """
    import uuid
    import re
    
    tab_name = (tab_name or "").strip()
    if not tab_name:
        raise ValueError("Tab name is required")
    
    # Generate table name from tab name (sanitize for DB)
    table_name = re.sub(r'[^a-z0-9_]', '_', tab_name.lower())
    table_name = f"custom_{table_name}_{location_id}"
    
    # Check for duplicate tab names
    cfg = LocationConfig.get_config(session, location_id)
    custom_tabs = cfg.setdefault("custom_tabs", {})
    page_tabs = custom_tabs.setdefault(page, [])
    
    # Check if tab name already exists
    if any(t.get("name", "").lower() == tab_name.lower() for t in page_tabs):
        raise ValueError(f"Tab '{tab_name}' already exists for this page")
    
    # Check if table name already exists
    if any(t.get("table_name") == table_name for t in page_tabs):
        raise ValueError(f"Table name '{table_name}' already exists")
    
    # Create tab definition
    tab_id = str(uuid.uuid4())
    new_tab = {
        "id": tab_id,
        "name": tab_name,
        "table_name": table_name,
        "columns": columns,
        "active": True,
        "created_at": datetime.now().isoformat()
    }
    
    page_tabs.append(new_tab)
    cfg["custom_tabs"] = custom_tabs
    LocationConfig.save_config(session, location_id, cfg)
    
    return new_tab


def update_custom_tab(
    session: Session,
    location_id: int,
    page: str,
    tab_id: str,
    tab_name: str = None,
    columns: List[Dict[str, Any]] = None,
    active: bool = None
) -> bool:
    """Update an existing custom tab."""
    cfg = LocationConfig.get_config(session, location_id)
    custom_tabs = cfg.setdefault("custom_tabs", {})
    page_tabs = custom_tabs.setdefault(page, [])
    
    for tab in page_tabs:
        if tab.get("id") == tab_id:
            if tab_name is not None:
                tab["name"] = tab_name.strip()
            if columns is not None:
                tab["columns"] = columns
            if active is not None:
                tab["active"] = bool(active)
            tab["updated_at"] = datetime.now().isoformat()
            
            cfg["custom_tabs"] = custom_tabs
            LocationConfig.save_config(session, location_id, cfg)
            return True
    
    return False


def delete_custom_tab(session: Session, location_id: int, page: str, tab_id: str) -> bool:
    """Delete a custom tab."""
    cfg = LocationConfig.get_config(session, location_id)
    custom_tabs = cfg.setdefault("custom_tabs", {})
    page_tabs = custom_tabs.setdefault(page, [])
    
    original_len = len(page_tabs)
    page_tabs[:] = [t for t in page_tabs if t.get("id") != tab_id]
    
    if len(page_tabs) < original_len:
        cfg["custom_tabs"] = custom_tabs
        LocationConfig.save_config(session, location_id, cfg)
        return True
    
    return False


def get_all_custom_table_names(session: Session) -> List[str]:
    """
    Get all custom table names across all locations for report data source.
    
    Returns:
        List of table names
    """
    from models import Location
    
    all_tables = []
    locations = session.query(Location).all()
    
    for loc in locations:
        cfg = LocationConfig.get_config(session, loc.id)
        custom_tabs = cfg.get("custom_tabs", {})
        
        for page, tabs in custom_tabs.items():
            for tab in tabs:
                if tab.get("active", True):
                    table_name = tab.get("table_name")
                    if table_name and table_name not in all_tables:
                        all_tables.append(table_name)
    
    return sorted(all_tables)
