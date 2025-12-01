# tanker_transactions.py
from __future__ import annotations

from datetime import date, datetime, time as dt_time, timedelta
from typing import Any, Dict, List, Optional

import bisect
import streamlit as st

from db import get_session
from ui import header
from logger import log_error
from security import SecurityManager
from models import Location, Tanker, TankerCalibration, TankerTransaction
from location_config import LocationConfig, get_active_operation_names, list_operations
from timezone_utils import format_local_datetime
from utils_calc import (
    api60_from_api_obs,
    api60_from_density_obs,
    api_from_density,
    c_to_f,
    density_from_api,
    f_to_c,
    get_lt_factor,
    normalize_temp_unit,
    temp_bounds,
    vcf_from_api60_and_tank_temp,
)

try:  # pragma: no cover
    from permission_manager import PermissionManager
except Exception:  # pragma: no cover
    PermissionManager = None


LITRES_PER_BBL = 158.987
API_LIMITS = (15.0, 70.0)
DENSITY_LIMITS = (600.0, 1000.0)
TEMP_LIMITS = {"C": (0.0, 60.0), "F": (32.0, 120.0)}
CARGO_OPTIONS = ["OKW", "ANZ", "CONDENSATE", "CRUDE"]
DESTINATION_OPTIONS = ["Aggu", "OFS", "Ogini", "GPP", "Ndoni", "Other"]
LOADING_BAY_OPTIONS = ["Aggu", "Ogini", "OFS", "N/A"]
MANHOLE_OPTIONS = ["C1", "C2"]
OBS_MODES = ["Observed API", "Observed Density"]
DEFAULT_TIME = "08:00"
EDIT_LOCK_HOURS = 24


def _safe_rerun() -> None:
    st.rerun()


def _user_audit_context() -> tuple[str, Optional[int], Optional[int]]:
    user = st.session_state.get("auth_user") or {}
    username = user.get("username", "system")
    user_id = user.get("id")
    location_id = st.session_state.get("active_location_id")
    return username, user_id, location_id


def _guard_location(active_location_id: Optional[int]) -> tuple[Optional[Location], Optional[str]]:
    if not active_location_id:
        st.warning("No active location selected. Go to Home and pick a location first.")
        return None, None
    with get_session() as session:
        loc = session.query(Location).get(active_location_id)
        if not loc:
            st.warning("Selected location could not be found. Please re-select on Home.")
            return None, None
        return loc, f"{loc.name} ({loc.code})"


def _load_location_config(location_id: int) -> Dict[str, Any]:
    with get_session() as session:
        return LocationConfig.get_config(session, location_id) or {}


def _list_names_from_ops(session, location_id: int, *, asset: str, category: str) -> List[str]:
    """
    Return ACTIVE operation names for a given asset/category from Location Settings → Operations.
    """
    try:
        rows = list_operations(session, location_id, asset=asset, category=category)
        return [str(r.get("name") or "").strip() for r in rows if r.get("active", True)]
    except Exception:
        return []


def _guard_permissions(user: Optional[Dict[str, Any]], location_id: int, cfg: Dict[str, Any]) -> tuple[bool, bool]:
    role = (user or {}).get("role", "")
    role_lc = role.lower()
    if role_lc == "admin-it":
        st.error("Access denied. Admin-IT users cannot open operational pages.")
        return False, False

    if PermissionManager and user:
        try:
            if not PermissionManager.can_access_operational_pages(user):
                st.error(f"Access denied. Role {role} cannot open operational pages.")
                return False, False
        except Exception as exc:  # pragma: no cover
            log_error(f"Operational access check failed: {exc}", exc_info=True)

    page_flags = (cfg or {}).get("page_visibility", {}) or {}
    if not page_flags.get("show_tanker_transactions", False):
        st.warning("Tanker Transactions are disabled for this location. Enable it from Location Settings.")
        return False, False

    feature_allowed = True
    can_make_entries = True
    allowed_locations: List[str] = []
    if PermissionManager and user:
        try:
            with get_session() as session:
                feature_allowed = PermissionManager.can_access_feature(
                    session, location_id, "tanker_transactions", role
                )
                can_make_entries = PermissionManager.can_make_entries(session, role, location_id)
                if not feature_allowed:
                    allowed_locations = PermissionManager.get_allowed_locations_for_feature(
                        session, "tanker_transactions"
                    )
        except Exception as exc:  # pragma: no cover
            log_error(f"Tanker permission lookup failed: {exc}", exc_info=True)
            feature_allowed = True
            can_make_entries = True

    if not feature_allowed:
        st.error("Access denied. Tanker Transactions are not available at this location.")
        if allowed_locations:
            st.info("Feature currently enabled at: " + ", ".join(sorted(set(allowed_locations))))
        return False, False

    return True, can_make_entries


def _load_tankers() -> List[Tanker]:
    try:
        with get_session() as session:
            tankers = (
                session.query(Tanker)
                .filter(Tanker.status == "ACTIVE")
                .order_by(Tanker.name.asc())
                .all()
            )
        return tankers
    except Exception as exc:
        log_error(f"Failed to load tanker master: {exc}", exc_info=True)
        return []


def _interpolate_tanker_volume(session, tanker_name: str, compartment: str, dip_mm: float) -> float:
    if not tanker_name or not compartment:
        return 0.0
    rows = (
        session.query(TankerCalibration)
        .filter(TankerCalibration.tanker_name == tanker_name)
        .order_by(TankerCalibration.dip_mm.asc())
        .all()
    )
    if not rows:
        return 0.0

    xs = [float(r.dip_mm or 0.0) for r in rows]
    ys = [float(r.volume_litres or 0.0) for r in rows]

    if dip_mm <= xs[0]:
        return ys[0]
    if dip_mm >= xs[-1]:
        return ys[-1]

    idx = bisect.bisect_left(xs, dip_mm)
    if idx == 0:
        return ys[0]
    x1, y1 = xs[idx - 1], ys[idx - 1]
    x2, y2 = xs[idx], ys[idx]
    if x2 == x1:
        return y1
    t = (dip_mm - x1) / (x2 - x1)
    return y1 + t * (y2 - y1)

def _get_calibration_min_max_cm(session, tanker_name: str, compartment: str) -> tuple[float, float]:
    rows = (
        session.query(TankerCalibration.dip_mm)
        .filter(TankerCalibration.tanker_name == tanker_name)
        .order_by(TankerCalibration.dip_mm.asc())
        .all()
    )
    if not rows:
        return 0.0, 0.0
    mins = float(rows[0][0] or 0.0) / 10.0
    maxs = float(rows[-1][0] or 0.0) / 10.0
    return mins, maxs


def _record_created_timestamp(record: TankerTransaction) -> Optional[datetime]:
    ts = getattr(record, "created_at", None)
    if isinstance(ts, datetime):
        return ts.replace(tzinfo=None)
    dt_val = getattr(record, "transaction_date", None)
    tm_val = getattr(record, "transaction_time", None)
    if dt_val:
        tm_val = tm_val or dt_time.min
        return datetime.combine(dt_val, tm_val)
    return None


def _is_edit_lock_active(record: TankerTransaction) -> tuple[bool, Optional[datetime]]:
    created_at = _record_created_timestamp(record)
    if not created_at:
        return False, None
    locked = (datetime.utcnow() - created_at) > timedelta(hours=EDIT_LOCK_HOURS)
    return locked, created_at


def _deny_edit_for_lock(record: TankerTransaction, resource_label: str) -> bool:
    locked, created_at = _is_edit_lock_active(record)
    if not locked:
        return False

    ts_display = format_local_datetime(created_at) if created_at else "unknown time"
    message = (
        f"Editing locked. {resource_label} was created on {ts_display}. "
        f"Records older than {EDIT_LOCK_HOURS} hours cannot be updated."
    )
    st.warning(message)
    try:
        username, user_id, location_id = _user_audit_context()
        SecurityManager.log_audit(
            None,
            username,
            "UPDATE_BLOCKED",
            resource_type="TankerTransaction",
            resource_id=str(getattr(record, "id", resource_label)),
            details=message,
            user_id=user_id,
            location_id=location_id,
            success=False,
        )
    except Exception:  # pragma: no cover
        pass
    return True


def _ensure_option(options: List[str], value: Optional[str]) -> List[str]:
    if value and value not in options:
        return options + [value]
    return options


def _init_form_state(tanker_names: List[str]) -> None:
    ss = st.session_state
    ss.setdefault("tanker_form_mode", "new")
    ss.setdefault("tanker_edit_id", None)
    if tanker_names:
        ss.setdefault("tanker_tx_tanker_name", tanker_names[0])
    ss.setdefault("tanker_tx_chassis_no", "")
    ss.setdefault("tanker_tx_convoy_no", "")
    ss.setdefault("tanker_tx_date", date.today())
    ss.setdefault("tanker_tx_time", DEFAULT_TIME)
    ss.setdefault("tanker_tx_cargo", CARGO_OPTIONS[0])
    ss.setdefault("tanker_tx_operation", "")
    ss.setdefault("tanker_tx_destination", DESTINATION_OPTIONS[0])
    ss.setdefault("tanker_tx_loading_bay", LOADING_BAY_OPTIONS[0])
    ss.setdefault("tanker_tx_manhole", MANHOLE_OPTIONS[0])
    ss.setdefault("tanker_tx_total_dip_cm", 0.0)
    ss.setdefault("tanker_tx_water_dip_cm", 0.0)
    ss.setdefault("tanker_tx_bsw_pct", 0.0)
    ss.setdefault("tanker_tx_tank_temp_unit", "C")
    ss.setdefault("tanker_tx_tank_temp_value", 30.0)
    ss.setdefault("tanker_tx_sample_temp_unit", "F")
    ss.setdefault("tanker_tx_sample_temp_value", 80.0)
    ss.setdefault("tanker_tx_obs_mode", OBS_MODES[0])

    # Ensure observed property defaults are within valid bounds so number_input()
    # does not raise StreamlitValueBelowMinError on first render.
    api_val = ss.get("tanker_tx_api_observed", API_LIMITS[0])
    try:
        api_val_f = float(api_val)
    except (TypeError, ValueError):
        api_val_f = API_LIMITS[0]
    if api_val_f < API_LIMITS[0]:
        api_val_f = API_LIMITS[0]
    if api_val_f > API_LIMITS[1]:
        api_val_f = API_LIMITS[1]
    ss["tanker_tx_api_observed"] = api_val_f

    dens_val = ss.get("tanker_tx_density_observed", DENSITY_LIMITS[0])
    try:
        dens_val_f = float(dens_val)
    except (TypeError, ValueError):
        dens_val_f = DENSITY_LIMITS[0]
    if dens_val_f < DENSITY_LIMITS[0]:
        dens_val_f = DENSITY_LIMITS[0]
    if dens_val_f > DENSITY_LIMITS[1]:
        dens_val_f = DENSITY_LIMITS[1]
    ss["tanker_tx_density_observed"] = dens_val_f
    ss.setdefault("tanker_tx_seal_c1", "")
    ss.setdefault("tanker_tx_seal_c2", "")
    ss.setdefault("tanker_tx_seal_m1", "")
    ss.setdefault("tanker_tx_seal_m2", "")
    ss.setdefault("tanker_tx_remarks", "")


def _clear_form_state(tanker_names: List[str]) -> None:
    ss = st.session_state
    ss["tanker_form_mode"] = "new"
    ss["tanker_edit_id"] = None
    if tanker_names:
        ss["tanker_tx_tanker_name"] = tanker_names[0]
    ss["tanker_tx_chassis_no"] = ""
    ss["tanker_tx_convoy_no"] = ""
    ss["tanker_tx_date"] = date.today()
    ss["tanker_tx_time"] = DEFAULT_TIME
    ss["tanker_tx_cargo"] = CARGO_OPTIONS[0]
    ss["tanker_tx_operation"] = ""
    ss["tanker_tx_destination"] = DESTINATION_OPTIONS[0]
    ss["tanker_tx_loading_bay"] = LOADING_BAY_OPTIONS[0]
    ss["tanker_tx_manhole"] = MANHOLE_OPTIONS[0]
    ss["tanker_tx_total_dip_cm"] = 0.0
    ss["tanker_tx_water_dip_cm"] = 0.0
    ss["tanker_tx_bsw_pct"] = 0.0
    ss["tanker_tx_tank_temp_unit"] = "C"
    ss["tanker_tx_tank_temp_value"] = 30.0
    ss["tanker_tx_sample_temp_unit"] = "F"
    ss["tanker_tx_sample_temp_value"] = 80.0
    ss["tanker_tx_obs_mode"] = OBS_MODES[0]
    ss["tanker_tx_api_observed"] = API_LIMITS[0]
    ss["tanker_tx_density_observed"] = DENSITY_LIMITS[0]
    ss["tanker_tx_seal_c1"] = ""
    ss["tanker_tx_seal_c2"] = ""
    ss["tanker_tx_seal_m1"] = ""
    ss["tanker_tx_seal_m2"] = ""
    ss["tanker_tx_remarks"] = ""


def _prefill_form_state(tx: TankerTransaction) -> None:
    ss = st.session_state
    ss["tanker_form_mode"] = "edit"
    ss["tanker_edit_id"] = tx.id
    ss["tanker_tx_tanker_name"] = tx.tanker_name
    ss["tanker_tx_chassis_no"] = tx.chassis_no or ""
    ss["tanker_tx_convoy_no"] = tx.convoy_no or ""
    ss["tanker_tx_date"] = tx.transaction_date or date.today()
    if tx.transaction_time:
        ss["tanker_tx_time"] = tx.transaction_time.strftime("%H:%M")
    ss["tanker_tx_cargo"] = tx.cargo or CARGO_OPTIONS[0]
    ss["tanker_tx_destination"] = tx.destination or DESTINATION_OPTIONS[0]
    ss["tanker_tx_loading_bay"] = tx.loading_bay or LOADING_BAY_OPTIONS[0]
    ss["tanker_tx_manhole"] = tx.manhole or MANHOLE_OPTIONS[0]
    ss["tanker_tx_total_dip_cm"] = float(tx.total_dip_cm or 0.0)
    ss["tanker_tx_water_dip_cm"] = float(tx.water_dip_cm or 0.0)
    ss["tanker_tx_bsw_pct"] = float(tx.bsw_pct or 0.0)
    if tx.tank_temp_c is not None:
        ss["tanker_tx_tank_temp_unit"] = "C"
        ss["tanker_tx_tank_temp_value"] = float(tx.tank_temp_c)
    elif tx.tank_temp_f is not None:
        ss["tanker_tx_tank_temp_unit"] = "F"
        ss["tanker_tx_tank_temp_value"] = float(tx.tank_temp_f)
    if tx.sample_temp_c is not None:
        ss["tanker_tx_sample_temp_unit"] = "C"
        ss["tanker_tx_sample_temp_value"] = float(tx.sample_temp_c)
    elif tx.sample_temp_f is not None:
        ss["tanker_tx_sample_temp_unit"] = "F"
        ss["tanker_tx_sample_temp_value"] = float(tx.sample_temp_f)
    api_obs = float(tx.api_observed or 0.0)
    dens_obs = float(tx.density_observed or 0.0)
    if api_obs > 0:
        ss["tanker_tx_obs_mode"] = "Observed API"
        ss["tanker_tx_api_observed"] = api_obs
        ss["tanker_tx_density_observed"] = density_from_api(api_obs)
    else:
        ss["tanker_tx_obs_mode"] = "Observed Density"
        ss["tanker_tx_density_observed"] = dens_obs
        ss["tanker_tx_api_observed"] = api_from_density(dens_obs)
    ss["tanker_tx_seal_c1"] = tx.seal_c1 or ""
    ss["tanker_tx_seal_c2"] = tx.seal_c2 or ""
    ss["tanker_tx_seal_m1"] = tx.seal_m1 or ""
    ss["tanker_tx_seal_m2"] = tx.seal_m2 or ""
    ss["tanker_tx_remarks"] = tx.remarks or ""


def _select_index(options: List[str], selected: Optional[str]) -> int:
    if selected and selected in options:
        return options.index(selected)
    return 0


def _fmt_float(value: Optional[float], decimals: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):,.{decimals}f}"

def _render_transaction_view(tx: TankerTransaction, can_edit: bool) -> None:
    st.markdown(f"#### Transaction #{tx.id} - {tx.tanker_name}")
    info_col1, info_col2, info_col3 = st.columns(3)
    with info_col1:
        st.metric("Convoy", tx.convoy_no)
        st.metric("Cargo", tx.cargo)
        st.metric("Destination", tx.destination)
    with info_col2:
        st.metric("Date", tx.transaction_date.strftime("%Y-%m-%d"))
        st.metric("Time", tx.transaction_time.strftime("%H:%M"))
        st.metric("Loading Bay", tx.loading_bay or "N/A")
    with info_col3:
        st.metric("Compartment", f"{tx.compartment} via {tx.manhole}")
        st.metric("Chassis No", tx.chassis_no or "N/A")
        st.metric("Created By", tx.created_by or "system")

    st.markdown("##### Dip Readings")
    dip_c1, dip_c2 = st.columns(2)
    with dip_c1:
        st.metric("Total Dip (cm)", _fmt_float(tx.total_dip_cm))
        st.metric("Total Dip (mm)", _fmt_float(tx.total_dip_mm))
    with dip_c2:
        st.metric("Water Dip (cm)", _fmt_float(tx.water_dip_cm))
        st.metric("Water Dip (mm)", _fmt_float(tx.water_dip_mm))

    st.markdown("##### Temperatures")
    temp_c1, temp_c2 = st.columns(2)
    with temp_c1:
        st.metric("Tank Temp (C)", _fmt_float(tx.tank_temp_c))
        st.metric("Tank Temp (F)", _fmt_float(tx.tank_temp_f))
    with temp_c2:
        st.metric("Sample Temp (C)", _fmt_float(tx.sample_temp_c))
        st.metric("Sample Temp (F)", _fmt_float(tx.sample_temp_f))

    st.markdown("##### Volumes")
    vol_c1, vol_c2, vol_c3 = st.columns(3)
    with vol_c1:
        st.metric("Total Volume", f"{_fmt_float(tx.total_volume_bbl)} bbl")
        st.metric("Water Volume", f"{_fmt_float(tx.water_volume_bbl)} bbl")
    with vol_c2:
        st.metric("GOV", f"{_fmt_float(tx.gov_bbl)} bbl")
        st.metric("GSV", f"{_fmt_float(tx.gsv_bbl)} bbl")
    with vol_c3:
        st.metric("NSV", f"{_fmt_float(tx.nsv_bbl)} bbl")
        st.metric("BSW Volume", f"{_fmt_float(tx.bsw_vol_bbl)} bbl")

    st.markdown("##### Quality")
    q_c1, q_c2, q_c3 = st.columns(3)
    with q_c1:
        st.metric("Observed API", _fmt_float(tx.api_observed))
    with q_c2:
        st.metric("Observed Density", _fmt_float(tx.density_observed))
    with q_c3:
        st.metric("API @60", _fmt_float(tx.api60))
        st.metric("VCF", _fmt_float(tx.vcf, 5))

    st.markdown("##### Conversion Factors")
    cf_c1, cf_c2 = st.columns(2)
    with cf_c1:
        st.metric("LT Factor", _fmt_float(tx.lt))
    with cf_c2:
        st.metric("MT", _fmt_float(tx.mt))

    st.markdown("##### Seal Numbers")
    seal_c1, seal_c2, seal_c3, seal_c4 = st.columns(4)
    seal_c1.caption(f"C1: {tx.seal_c1 or 'N/A'}")
    seal_c2.caption(f"C2: {tx.seal_c2 or 'N/A'}")
    seal_c3.caption(f"M1: {tx.seal_m1 or 'N/A'}")
    seal_c4.caption(f"M2: {tx.seal_m2 or 'N/A'}")

    if tx.remarks:
        st.markdown("##### Remarks")
        st.info(tx.remarks)

    st.markdown("##### Audit Trail")
    audit_c1, audit_c2 = st.columns(2)
    with audit_c1:
        created_at = format_local_datetime(tx.created_at) if tx.created_at else "N/A"
        st.caption(f"Created By: {tx.created_by or 'system'} at {created_at}")
    with audit_c2:
        if tx.updated_by:
            updated_at = format_local_datetime(tx.updated_at) if tx.updated_at else "N/A"
            st.caption(f"Updated By: {tx.updated_by} at {updated_at}")
        else:
            st.caption("Updated By: N/A")

    action_col1, action_col2 = st.columns([0.4, 0.6])
    with action_col1:
        if st.button("Close Viewer", key=f"close_{tx.id}"):
            st.session_state.pop("tanker_view_selected", None)
            _safe_rerun()
    with action_col2:
        if can_edit:
            if st.button("Edit This Transaction", key=f"edit_{tx.id}"):
                if not _deny_edit_for_lock(tx, f"{tx.tanker_name}-{tx.convoy_no}"):
                    # Store transaction data in flag to prefill on next render
                    st.session_state["tanker_tx_prefill_data"] = tx
                    st.info("Form below pre-filled for editing.")
                    _safe_rerun()


def _render_saved_transactions(location_id: int, can_edit: bool) -> None:
    st.markdown("### Saved Tanker Transactions")
    if "tanker_view_selected" not in st.session_state:
        st.session_state["tanker_view_selected"] = None

    try:
        with get_session() as session:
            rows = (
                session.query(TankerTransaction)
                .filter(TankerTransaction.location_id == location_id)
                .order_by(
                    TankerTransaction.transaction_date.desc(),
                    TankerTransaction.transaction_time.desc(),
                )
                .limit(50)
                .all()
            )
    except Exception as exc:
        st.error("Could not load tanker transactions.")
        log_error(f"Failed to load tanker transactions: {exc}", exc_info=True)
        return

    if not rows:
        st.info("No tanker transactions recorded yet.")
        return

    options = []
    id_by_label = {}
    for tx in rows:
        label = f"{tx.tanker_name} | Convoy {tx.convoy_no} | {tx.transaction_date} | {tx.destination}"
        options.append(label)
        id_by_label[label] = tx.id

    selected_label = st.selectbox("Select transaction", options, key="tanker_tx_selector")
    selected_id = id_by_label[selected_label]

    view_col, refresh_col = st.columns([0.4, 0.6])
    with view_col:
        if st.button("View Details", key="view_tanker_details"):
            st.session_state["tanker_view_selected"] = selected_id
    with refresh_col:
        if st.button("Refresh Transactions", key="refresh_tanker_transactions"):
            st.session_state["tanker_view_selected"] = selected_id
            _safe_rerun()

    current_id = st.session_state.get("tanker_view_selected")
    if current_id:
        tx = next((row for row in rows if row.id == current_id), None)
        if tx:
            st.markdown("---")
            _render_transaction_view(tx, can_edit)

def _calc_volume_preview(tanker_name: str, compartment: str, total_cm: float, water_cm: float) -> tuple[float, float, float]:
    if total_cm <= 0:
        return 0.0, 0.0, 0.0
    try:
        with get_session() as session:
            total_l = _interpolate_tanker_volume(session, tanker_name, compartment, total_cm * 10.0)
            water_l = _interpolate_tanker_volume(session, tanker_name, compartment, water_cm * 10.0)
    except Exception as exc:
        log_error(f"Tanker calibration lookup failed: {exc}", exc_info=True)
        return 0.0, 0.0, 0.0
    total_bbl = total_l / LITRES_PER_BBL
    water_bbl = water_l / LITRES_PER_BBL
    gov_bbl = max(total_bbl - water_bbl, 0.0)
    return total_bbl, water_bbl, gov_bbl

def _render_entry_form(location: Location, can_submit: bool, tankers: List[Tanker]) -> None:
    """
    New interactive tanker entry form without st.form(), so that
    dropdowns (obs mode, temp units) immediately drive labels,
    bounds, and live API@60 previews similar to tank_transactions.
    """
    tanker_names = [t.name for t in tankers]
    _init_form_state(tanker_names)
    ss = st.session_state
    
    # Handle clear/prefill flags BEFORE creating any widgets
    if ss.get("tanker_tx_clear_form_flag"):
        ss.pop("tanker_tx_clear_form_flag", None)
        _clear_form_state(tanker_names)
    
    if ss.get("tanker_tx_prefill_data"):
        tx_data = ss.pop("tanker_tx_prefill_data")
        _prefill_form_state(tx_data)
    
    mode = ss.get("tanker_form_mode", "new")
    editing_id = ss.get("tanker_edit_id")

    if not can_submit:
        st.info("Your role is read-only here. Form controls are disabled.")

    st.markdown("### Add / Edit Tanker Transaction")

    if not tanker_names:
        st.warning("No tankers available for entry. Please create a tanker in Asset Management first.")
        return

    tanker_by_name: Dict[str, Tanker] = {t.name: t for t in tankers}

    op_options: List[str] = []
    dest_options_cfg: List[str] = []
    loading_options_cfg: List[str] = []
    try:
        with get_session() as s:
            op_options = get_active_operation_names(s, location.id, asset="tanker") or []
            dest_options_cfg = _list_names_from_ops(s, location.id, asset="tanker", category="Destination")
            loading_options_cfg = _list_names_from_ops(s, location.id, asset="tanker", category="Loading Berth")
    except Exception as exc:
        log_error(f"Tanker operations lookup failed: {exc}", exc_info=True)

    if not op_options:
        op_options = ["N/A (configure in Location Settings)"]
    if not dest_options_cfg:
        dest_options_cfg = ["N/A (configure in Location Settings)"]
    if not loading_options_cfg:
        loading_options_cfg = ["N/A (configure in Location Settings)"]

    submitted = False
    try:
        # ---------------- TANKER DETAILS ----------------
        st.markdown("#### Tanker Details")
        meta_c1, meta_c2, meta_c3 = st.columns(3)
        with meta_c1:
            tanker_name = st.selectbox(
                "Tanker Name *",
                tanker_names,
                index=_select_index(tanker_names, ss.get("tanker_tx_tanker_name")),
                key="tanker_tx_tanker_name",
            )

            if mode == "new":
                selected_tanker = tanker_by_name.get(tanker_name)
                master_chassis = (selected_tanker.registration_no or "") if selected_tanker else ""
                prev_name = ss.get("tanker_prev_name_for_chassis")
                if master_chassis and (not ss.get("tanker_tx_chassis_no") or tanker_name != prev_name):
                    ss["tanker_tx_chassis_no"] = master_chassis
                    ss["tanker_prev_name_for_chassis"] = tanker_name

            chassis_no = st.text_input("Chassis No", key="tanker_tx_chassis_no")
        with meta_c2:
            convoy_no = st.text_input("Convoy No *", key="tanker_tx_convoy_no")
            tx_date = st.date_input("Date *", max_value=date.today(), key="tanker_tx_date")
        with meta_c3:
            cargo = st.selectbox(
                "Cargo *",
                CARGO_OPTIONS,
                index=_select_index(CARGO_OPTIONS, ss.get("tanker_tx_cargo")),
                key="tanker_tx_cargo",
            )
            tx_time_str = st.text_input("Time (HH:MM) *", key="tanker_tx_time")

        op_c1, op_c2, op_c3 = st.columns(3)
        with op_c1:
            operation = st.selectbox(
                "Operation",
                op_options,
                index=_select_index(op_options, ss.get("tanker_tx_operation")),
                key="tanker_tx_operation",
            )
        with op_c2:
            destination_options = dest_options_cfg
            destination = st.selectbox(
                "Destination *",
                destination_options,
                index=_select_index(destination_options, ss.get("tanker_tx_destination")),
                key="tanker_tx_destination",
            )
        with op_c3:
            loading_options = loading_options_cfg
            loading_bay = st.selectbox(
                "Loading Bay",
                loading_options,
                index=_select_index(loading_options, ss.get("tanker_tx_loading_bay")),
                key="tanker_tx_loading_bay",
            )

        # ---------------- DIP DETAILS ----------------
        st.markdown("#### Dip Details")
        manhole = st.selectbox(
            "Manhole Used *",
            MANHOLE_OPTIONS,
            index=_select_index(MANHOLE_OPTIONS, ss.get("tanker_tx_manhole")),
            key="tanker_tx_manhole",
        )
        compartment = manhole

        with get_session() as _s:
            _, max_dip_cm = _get_calibration_min_max_cm(_s, tanker_name, compartment)
        st.caption(f"Max calibration: {max_dip_cm:.1f} cm")
        dip_c1, dip_c2 = st.columns(2)
        with dip_c1:
            if max_dip_cm > 0:
                total_dip_cm = st.number_input(
                    f"Total Dip (cm) *  (max {max_dip_cm:.1f})",
                    min_value=0.0,
                    max_value=max_dip_cm,
                    step=0.1,
                    format="%.1f",
                    key="tanker_tx_total_dip_cm",
                )
            else:
                total_dip_cm = st.number_input(
                    "Total Dip (cm) *",
                    min_value=0.0,
                    step=0.1,
                    format="%.1f",
                    key="tanker_tx_total_dip_cm",
                )
        with dip_c2:
            if max_dip_cm > 0:
                water_dip_cm = st.number_input(
                    f"Water Dip (cm)  (max {max_dip_cm:.1f})",
                    min_value=0.0,
                    max_value=max_dip_cm,
                    step=0.1,
                    format="%.1f",
                    key="tanker_tx_water_dip_cm",
                )
            else:
                water_dip_cm = st.number_input(
                    "Water Dip (cm)",
                    min_value=0.0,
                    step=0.1,
                    format="%.1f",
                    key="tanker_tx_water_dip_cm",
                )

        total_bbl, water_bbl, gov_bbl = _calc_volume_preview(
            tanker_name,
            compartment,
            float(total_dip_cm),
            float(water_dip_cm),
        )
        if total_bbl > 0:
            st.caption(
                f"Live volumes: Total **{total_bbl:,.2f} bbl**, "
                f"Water **{water_bbl:,.2f} bbl**, GOV **{gov_bbl:,.2f} bbl**."
            )
        else:
            st.caption("Volume preview unavailable (check calibration or dip values).")

        bsw_pct = st.number_input(
            "BS&W % *",
            min_value=0.0,
            max_value=100.0,
            step=0.01,
            key="tanker_tx_bsw_pct",
        )

        # ---------------- SAMPLE PARAMETERS ----------------
        st.markdown("#### Sample Parameters")
        temp_c1, temp_c2 = st.columns(2)
        with temp_c1:
            tank_temp_unit = st.selectbox(
                "Tank Temp Unit",
                ["°C", "°F"],
                index=_select_index(["°C", "°F"], ss.get("tanker_tx_tank_temp_unit")),
                key="tanker_tx_tank_temp_unit",
            )
            lo, hi = temp_bounds(tank_temp_unit)
            tank_temp_value = st.number_input(
                f"Tank Temperature ({tank_temp_unit})",
                min_value=lo,
                max_value=hi,
                step=0.1,
                key="tanker_tx_tank_temp_value",
            )
        with temp_c2:
            st.caption("Observed Property & Sample Temperature")
            obs_mode = st.selectbox(
                "Input Type",
                ["Observed API", "Observed Density (kg/m3)"],
                index=_select_index(["Observed API", "Observed Density (kg/m3)"], ss.get("tanker_tx_obs_mode")),
                key="tanker_tx_obs_mode",
            )
            sample_temp_unit = st.selectbox(
                "Sample Temp Unit",
                ["°F", "°C"],
                index=_select_index(["°F", "°C"], ss.get("tanker_tx_sample_temp_unit")),
                key="tanker_tx_sample_temp_unit",
            )
            slo, shi = temp_bounds(sample_temp_unit)
            sample_temp_value = st.number_input(
                "Sample Temperature",
                min_value=slo,
                max_value=shi,
                step=0.1,
                key="tanker_tx_sample_temp_value",
            )

        if obs_mode == "Observed API":
            api_observed = st.number_input(
                "Observed API *",
                min_value=API_LIMITS[0],
                max_value=API_LIMITS[1],
                step=0.1,
                key="tanker_tx_api_observed",
            )
            api60_val = api60_from_api_obs(
                float(api_observed or 0.0),
                float(sample_temp_value or 0.0),
                sample_temp_unit,
            )
            density_observed = density_from_api(float(api_observed or 0.0))
            st.caption(
                f"→ API @ 60°F: **{api60_val:.2f}**   |   ↔"
                f" Density (approx): **{density_observed:.1f} kg/m³**"
            )
        else:
            density_observed = st.number_input(
                "Observed Density (kg/m3) *",
                min_value=DENSITY_LIMITS[0],
                max_value=DENSITY_LIMITS[1],
                step=0.1,
                key="tanker_tx_density_observed",
            )
            api_observed = (
                api_from_density(float(density_observed or 0.0))
                if float(density_observed or 0.0) > 0
                else 0.0
            )
            api60_val = api60_from_density_obs(
                float(density_observed or 0.0),
                float(sample_temp_value or 0.0),
                sample_temp_unit,
            )
            st.caption(
                f"↔ Observed API (approx): **{api_observed:.2f}**   |   → API @ 60°F: **{api60_val:.2f}**"
            )

        # ---------------- SEAL DETAILS ----------------
        st.markdown("#### Seal Details")
        seal_row = st.columns(4)
        seal_c1 = seal_row[0].text_input("Seal C1", key="tanker_tx_seal_c1")
        seal_c2 = seal_row[1].text_input("Seal C2", key="tanker_tx_seal_c2")
        seal_m1 = seal_row[2].text_input("Seal M1", key="tanker_tx_seal_m1")
        seal_m2 = seal_row[3].text_input("Seal M2", key="tanker_tx_seal_m2")

        remarks = st.text_area("Remarks", key="tanker_tx_remarks")

        submit_label = "Update Tanker Transaction" if mode == "edit" else "Save Tanker Transaction"
        submitted = st.button(
            submit_label,
            type="primary",
            disabled=not can_submit,
            key="tanker_tx_submit",
        )
    except Exception as ex:
        st.error("Form initialization error.")
        log_error(f"Tanker form initialization failed: {ex}", exc_info=True)

    if submitted:
        _handle_form_submission(
            location,
            editing_id,
            tanker_name,
            chassis_no,
            convoy_no,
            tx_date,
            tx_time_str,
            cargo,
            destination,
            loading_bay,
            compartment,
            float(total_dip_cm),
            float(water_dip_cm),
            float(bsw_pct),
            tank_temp_unit,
            float(tank_temp_value),
            sample_temp_unit,
            float(sample_temp_value),
            obs_mode,
            float(api_observed),
            float(density_observed),
            seal_c1,
            seal_c2,
            seal_m1,
            seal_m2,
            remarks,
            tanker_names,
        )

def _render_entry_form_legacy(location: Location, can_submit: bool, tankers: List[Tanker]) -> None:
    tanker_names = [t.name for t in tankers]
    _init_form_state(tanker_names)
    ss = st.session_state
    mode = ss.get("tanker_form_mode", "new")
    editing_id = ss.get("tanker_edit_id")

    if not can_submit:
        st.info("Your role is read-only here. Form controls are disabled.")

    st.markdown("### Add / Edit Tanker Transaction")

    if not tanker_names:
        st.warning("No tankers available for entry. Please create a tanker in Asset Management first.")
        return

    # Lookup for tanker → chassis no. (registration_no field in Tanker master)
    tanker_by_name: Dict[str, Tanker] = {t.name: t for t in tankers}

    # Location Settings driven dropdowns for tanker asset
    op_options: List[str] = []
    dest_options_cfg: List[str] = []
    loading_options_cfg: List[str] = []
    try:
        with get_session() as s:
            op_options = get_active_operation_names(s, location.id, asset="tanker") or []
            dest_options_cfg = _list_names_from_ops(s, location.id, asset="tanker", category="Destination")
            loading_options_cfg = _list_names_from_ops(s, location.id, asset="tanker", category="Loading Berth")
    except Exception as exc:
        log_error(f"Tanker operations lookup failed: {exc}", exc_info=True)

    if not op_options:
        op_options = ["N/A (configure in Location Settings)"]
    if not dest_options_cfg:
        dest_options_cfg = ["N/A (configure in Location Settings)"]
    if not loading_options_cfg:
        loading_options_cfg = ["N/A (configure in Location Settings)"]

    with st.form("tanker_transaction_form", clear_on_submit=True):
        try:
            # ---------------- TANKER DETAILS ----------------
            st.markdown("#### Tanker Details")
            meta_c1, meta_c2, meta_c3 = st.columns(3)
            with meta_c1:
                tanker_name = st.selectbox(
                    "Tanker Name *",
                    tanker_names,
                    index=_select_index(tanker_names, ss.get("tanker_tx_tanker_name")),
                    key="tanker_tx_tanker_name",
                )

                # Auto-fill chassis from tanker master when creating a new entry
                if mode == "new":
                    selected_tanker = tanker_by_name.get(tanker_name)
                    master_chassis = (selected_tanker.registration_no or "") if selected_tanker else ""
                    prev_name = ss.get("tanker_prev_name_for_chassis")
                    if master_chassis and (not ss.get("tanker_tx_chassis_no") or tanker_name != prev_name):
                        ss["tanker_tx_chassis_no"] = master_chassis
                        ss["tanker_prev_name_for_chassis"] = tanker_name

                chassis_no = st.text_input("Chassis No", key="tanker_tx_chassis_no")
            with meta_c2:
                convoy_no = st.text_input("Convoy No *", key="tanker_tx_convoy_no")
                tx_date = st.date_input("Date *", max_value=date.today(), key="tanker_tx_date")
            with meta_c3:
                cargo = st.selectbox(
                    "Cargo *",
                    CARGO_OPTIONS,
                    index=_select_index(CARGO_OPTIONS, ss.get("tanker_tx_cargo")),
                    key="tanker_tx_cargo",
                )
                tx_time_str = st.text_input("Time (HH:MM) *", key="tanker_tx_time")

            # Operation / Destination / Loading Bay in a single row
            op_c1, op_c2, op_c3 = st.columns(3)
            with op_c1:
                operation = st.selectbox(
                    "Operation",
                    op_options,
                    index=_select_index(op_options, ss.get("tanker_tx_operation")),
                    key="tanker_tx_operation",
                )
            with op_c2:
                destination_options = dest_options_cfg
                destination = st.selectbox(
                    "Destination *",
                    destination_options,
                    index=_select_index(destination_options, ss.get("tanker_tx_destination")),
                    key="tanker_tx_destination",
                )
            with op_c3:
                loading_options = loading_options_cfg
                loading_bay = st.selectbox(
                    "Loading Bay",
                    loading_options,
                    index=_select_index(loading_options, ss.get("tanker_tx_loading_bay")),
                    key="tanker_tx_loading_bay",
                )

            # ---------------- DIP DETAILS ----------------
            st.markdown("#### Dip Details")
            manhole = st.selectbox(
                "Manhole Used *",
                MANHOLE_OPTIONS,
                index=_select_index(MANHOLE_OPTIONS, ss.get("tanker_tx_manhole")),
                key="tanker_tx_manhole",
            )
            compartment = manhole

            with get_session() as _s:
                _, max_dip_cm = _get_calibration_min_max_cm(_s, tanker_name, compartment)
            st.caption(f"Max calibration: {max_dip_cm:.1f} cm")
            dip_c1, dip_c2 = st.columns(2)
            with dip_c1:
                if max_dip_cm > 0:
                    total_dip_cm = st.number_input(
                        f"Total Dip (cm) *  (max {max_dip_cm:.1f})",
                        min_value=0.0,
                        max_value=max_dip_cm,
                        step=0.1,
                        format="%.1f",
                        key="tanker_tx_total_dip_cm",
                    )
                else:
                    total_dip_cm = st.number_input(
                        "Total Dip (cm) *",
                        min_value=0.0,
                        step=0.1,
                        format="%.1f",
                        key="tanker_tx_total_dip_cm",
                    )
            with dip_c2:
                if max_dip_cm > 0:
                    water_dip_cm = st.number_input(
                        f"Water Dip (cm)  (max {max_dip_cm:.1f})",
                        min_value=0.0,
                        max_value=max_dip_cm,
                        step=0.1,
                        format="%.1f",
                        key="tanker_tx_water_dip_cm",
                    )
                else:
                    water_dip_cm = st.number_input(
                        "Water Dip (cm)",
                        min_value=0.0,
                        step=0.1,
                        format="%.1f",
                        key="tanker_tx_water_dip_cm",
                    )

            total_bbl, water_bbl, gov_bbl = _calc_volume_preview(
                tanker_name,
                compartment,
                float(total_dip_cm),
                float(water_dip_cm),
            )
            if total_bbl > 0:
                st.caption(
                    f"Live volumes: Total **{total_bbl:,.2f} bbl**, "
                    f"Water **{water_bbl:,.2f} bbl**, GOV **{gov_bbl:,.2f} bbl**."
                )
            else:
                st.caption("Volume preview unavailable (check calibration or dip values).")

            bsw_pct = st.number_input(
                "BS&W % *",
                min_value=0.0,
                max_value=100.0,
                step=0.01,
                key="tanker_tx_bsw_pct",
            )

            # ---------------- SAMPLE PARAMETERS ----------------
            st.markdown("#### Sample Parameters")
            temp_c1, temp_c2 = st.columns(2)
            with temp_c1:
                tank_temp_unit = st.selectbox(
                    "Tank Temp Unit",
                    ["°C", "°F"],
                    index=_select_index(["°C", "°F"], ss.get("tanker_tx_tank_temp_unit")),
                    key="tanker_tx_tank_temp_unit",
                )
                _ttu = "C" if str(tank_temp_unit).startswith("°C") else "F"
                lo, hi = temp_bounds(tank_temp_unit)
                tank_temp_value = st.number_input(
                    f"Tank Temperature ({tank_temp_unit})",
                    min_value=lo,
                    max_value=hi,
                    step=0.1,
                    key="tanker_tx_tank_temp_value",
                )
            with temp_c2:
                st.caption("Observed Property & Sample Temperature")
                obs_mode = st.selectbox(
                    "Input Type",
                    ["Observed API", "Observed Density (kg/m3)"],
                    index=_select_index(["Observed API", "Observed Density (kg/m3)"], ss.get("tanker_tx_obs_mode")),
                    key="tanker_tx_obs_mode",
                )
                sample_temp_unit = st.selectbox(
                    "Sample Temp Unit",
                    ["°F", "°C"],
                    index=_select_index(["°F", "°C"], ss.get("tanker_tx_sample_temp_unit")),
                    key="tanker_tx_sample_temp_unit",
                )
                _stu = "F" if str(sample_temp_unit).startswith("°F") else "C"
                slo, shi = temp_bounds(sample_temp_unit)
                sample_temp_value = st.number_input(
                    "Sample Temperature",
                    min_value=slo,
                    max_value=shi,
                    step=0.1,
                    key="tanker_tx_sample_temp_value",
                )

            if obs_mode == "Observed API":
                api_observed = st.number_input(
                    "Observed API *",
                    min_value=API_LIMITS[0],
                    max_value=API_LIMITS[1],
                    step=0.1,
                    key="tanker_tx_api_observed",
                )
                api60_val = api60_from_api_obs(float(api_observed or 0.0), float(sample_temp_value or 0.0), sample_temp_unit)
                density_observed = density_from_api(float(api_observed or 0.0))
                st.caption(f"→ API @ 60°F: {api60_val:.2f}   |   ↔ Density (approx): {density_observed:.1f} kg/m³")
            else:
                density_observed = st.number_input(
                    "Observed Density (kg/m3) *",
                    min_value=DENSITY_LIMITS[0],
                    max_value=DENSITY_LIMITS[1],
                    step=0.1,
                    key="tanker_tx_density_observed",
                )
                api_observed = api_from_density(float(density_observed or 0.0)) if float(density_observed or 0.0) > 0 else 0.0
                api60_val = api60_from_density_obs(float(density_observed or 0.0), float(sample_temp_value or 0.0), sample_temp_unit)
                st.caption(f"↔ Observed API (approx): {api_observed:.2f}   |   → API @ 60°F: {api60_val:.2f}")

            # ---------------- SEAL DETAILS ----------------
            st.markdown("#### Seal Details")
            seal_row = st.columns(4)
            seal_c1 = seal_row[0].text_input("Seal C1", key="tanker_tx_seal_c1")
            seal_c2 = seal_row[1].text_input("Seal C2", key="tanker_tx_seal_c2")
            seal_m1 = seal_row[2].text_input("Seal M1", key="tanker_tx_seal_m1")
            seal_m2 = seal_row[3].text_input("Seal M2", key="tanker_tx_seal_m2")

            remarks = st.text_area("Remarks", key="tanker_tx_remarks")
        except Exception as ex:
            st.error("Form initialization error.")
        submit_label = "Update Tanker Transaction" if mode == "edit" else "Save Tanker Transaction"
        submitted = st.form_submit_button(submit_label, disabled=not can_submit)

    if submitted:
        _handle_form_submission(
            location,
            editing_id,
            tanker_name,
            chassis_no,
            convoy_no,
            tx_date,
            tx_time_str,
            cargo,
            destination,
            loading_bay,
            compartment,
            float(total_dip_cm),
            float(water_dip_cm),
            float(bsw_pct),
            tank_temp_unit,
            float(tank_temp_value),
            sample_temp_unit,
            float(sample_temp_value),
            obs_mode,
            float(api_observed),
            float(density_observed),
            seal_c1,
            seal_c2,
            seal_m1,
            seal_m2,
            remarks,
            tanker_names,
        )

def _handle_form_submission(
    location: Location,
    editing_id: Optional[int],
    tanker_name: str,
    chassis_no: str,
    convoy_no: str,
    tx_date: date,
    tx_time_str: str,
    cargo: str,
    destination: str,
    loading_bay: str,
    compartment: str,
    total_dip_cm: float,
    water_dip_cm: float,
    bsw_pct: float,
    tank_temp_unit: str,
    tank_temp_value: float,
    sample_temp_unit: str,
    sample_temp_value: float,
    obs_mode: str,
    api_observed: float,
    density_observed: float,
    seal_c1: str,
    seal_c2: str,
    seal_m1: str,
    seal_m2: str,
    remarks: str,
    tanker_names: List[str],
) -> None:
    errors = []
    if not convoy_no.strip():
        errors.append("Convoy number is required.")
    if total_dip_cm <= 0:
        errors.append("Total dip must be greater than zero.")
    if obs_mode == "Observed API" and api_observed <= 0:
        errors.append("Observed API must be greater than zero.")
    if obs_mode == "Observed Density" and density_observed <= 0:
        errors.append("Observed density must be greater than zero.")

    try:
        tx_time_obj = datetime.strptime(tx_time_str.strip(), "%H:%M").time()
    except ValueError:
        errors.append("Time must be provided in HH:MM (24-hour) format.")
        tx_time_obj = None

    if errors:
        for err in errors:
            st.error(err)
        return
    if not tx_time_obj:
        return

    try:
        with get_session() as session:
            max_row = (
                session.query(TankerCalibration.dip_mm)
                .filter(TankerCalibration.tanker_name == tanker_name)
                .order_by(TankerCalibration.dip_mm.desc())
                .first()
            )
            if max_row and max_row[0]:
                max_dip_cm = float(max_row[0]) / 10.0
                if float(total_dip_cm or 0.0) > max_dip_cm or float(water_dip_cm or 0.0) > max_dip_cm:
                    st.error(
                        f"Entered Dip exceeds calibration maximum ({max_dip_cm:.1f} cm) for this tanker/compartment."
                    )
                    return
            total_l = _interpolate_tanker_volume(session, tanker_name, compartment, total_dip_cm * 10.0)
            water_l = _interpolate_tanker_volume(session, tanker_name, compartment, water_dip_cm * 10.0)
            if total_l <= 0:
                st.error("No calibration data for this tanker/compartment. Please upload calibration first.")
                return

            total_bbl = total_l / LITRES_PER_BBL
            water_bbl = water_l / LITRES_PER_BBL
            gov_bbl = max(total_bbl - water_bbl, 0.0)

            # Normalize temperature units before using them
            tank_temp_unit_norm = normalize_temp_unit(tank_temp_unit)
            sample_temp_unit_norm = normalize_temp_unit(sample_temp_unit)

            if obs_mode == "Observed API":
                api60 = api60_from_api_obs(api_observed, sample_temp_value, sample_temp_unit_norm)
                density_val = density_from_api(api_observed)
            else:
                api60 = api60_from_density_obs(density_observed, sample_temp_value, sample_temp_unit_norm)
                density_val = density_observed
                api_observed = api_from_density(density_observed)

            vcf_val = vcf_from_api60_and_tank_temp(api60, tank_temp_value, tank_temp_unit_norm)
            gsv_bbl = gov_bbl * vcf_val
            bsw_vol_bbl = gsv_bbl * (bsw_pct / 100.0)
            nsv_bbl = gsv_bbl - bsw_vol_bbl
            try:
                lt_factor = get_lt_factor(session, api60) if api60 > 0 else 0.0
            except Exception:
                lt_factor = 0.0
            lt_val = nsv_bbl * lt_factor
            mt_val = lt_val * 1.01605

            # Convert temperatures to both C and F
            if tank_temp_unit_norm == "C":
                tank_temp_c = tank_temp_value
                tank_temp_f = c_to_f(tank_temp_value)
            else:
                tank_temp_f = tank_temp_value
                tank_temp_c = f_to_c(tank_temp_value)
            if sample_temp_unit_norm == "C":
                sample_temp_c = sample_temp_value
                sample_temp_f = c_to_f(sample_temp_value)
            else:
                sample_temp_f = sample_temp_value
                sample_temp_c = f_to_c(sample_temp_value)

            payload = dict(
                location_id=location.id,
                tanker_name=tanker_name,
                chassis_no=chassis_no.strip() or None,
                convoy_no=convoy_no.strip(),
                transaction_date=tx_date,
                transaction_time=tx_time_obj,
                cargo=cargo,
                destination=destination,
                loading_bay=None if loading_bay == "N/A" else loading_bay,
                compartment=compartment,
                manhole=compartment,
                total_dip_cm=float(total_dip_cm),
                total_dip_mm=float(total_dip_cm) * 10.0,
                water_dip_cm=float(water_dip_cm),
                water_dip_mm=float(water_dip_cm) * 10.0,
                tank_temp_c=float(tank_temp_c),
                tank_temp_f=float(tank_temp_f),
                sample_temp_c=float(sample_temp_c),
                sample_temp_f=float(sample_temp_f),
                api_observed=float(api_observed),
                density_observed=float(density_val),
                bsw_pct=float(bsw_pct),
                total_volume_bbl=float(total_bbl),
                water_volume_bbl=float(water_bbl),
                gov_bbl=float(gov_bbl),
                api60=float(api60),
                vcf=float(vcf_val),
                gsv_bbl=float(gsv_bbl),
                bsw_vol_bbl=float(bsw_vol_bbl),
                nsv_bbl=float(nsv_bbl),
                lt=float(lt_factor),
                mt=float(mt_val),
                seal_c1=seal_c1.strip() or None,
                seal_c2=seal_c2.strip() or None,
                seal_m1=seal_m1.strip() or None,
                seal_m2=seal_m2.strip() or None,
                remarks=remarks.strip() or None,
            )

            action = _persist_tanker_transaction(editing_id, payload)
            # Set flag to clear form on next render instead of modifying widget keys
            st.session_state["tanker_tx_clear_form_flag"] = True
            if action == "CREATE":
                st.success("Tanker transaction saved.")
            else:
                st.success("Tanker transaction updated.")
            _safe_rerun()

    except Exception as exc:
        st.error(f"Failed to save tanker transaction: {exc}")
        log_error(f"Failed to save tanker transaction: {exc}", exc_info=True)

def _persist_tanker_transaction(editing_id: Optional[int], payload: Dict[str, Any]) -> None:
    username, user_id, location_id = _user_audit_context()
    action = "CREATE"
    resource_id = ""

    with get_session() as session:
        if editing_id:
            tx = session.query(TankerTransaction).filter(
                TankerTransaction.id == editing_id,
                TankerTransaction.location_id == payload["location_id"],
            ).one_or_none()
            if not tx:
                st.error("Selected transaction was not found (reload the page).")
                return
            for key, value in payload.items():
                setattr(tx, key, value)
            tx.updated_by = username
            tx.updated_at = datetime.utcnow()
            action = "UPDATE"
            resource_id = str(tx.id)
        else:
            tx = TankerTransaction(**payload, created_by=username)
            session.add(tx)
            session.flush()
            action = "CREATE"
            resource_id = str(tx.id)
        session.commit()

    try:
        SecurityManager.log_audit(
            None,
            username,
            action,
            resource_type="TankerTransaction",
            resource_id=resource_id,
            details=f"{action} tanker transaction {resource_id}",
            user_id=user_id,
            location_id=location_id,
        )
    except Exception:  # pragma: no cover
        pass

    return action

def render_tanker_transactions_page(active_location_id: Optional[int], user: Optional[Dict[str, Any]]) -> None:
    try:
        header("Tanker Transactions")
        loc, loc_label = _guard_location(active_location_id)
        if not loc:
            return

        cfg = _load_location_config(loc.id)
        allowed, can_make_entries = _guard_permissions(user, loc.id, cfg)
        if not allowed:
            return

        st.caption(f"Active Location: {loc_label}")
        st.success("Tanker Transactions enabled at this location.")

        tankers = _load_tankers()
        if not tankers:
            st.warning("No active tankers found. Add tankers in Asset Management first.")
            return

        # Check if there are custom tabs
        custom_tabs = []
        try:
            from location_config import get_custom_tabs
            with get_session() as s:
                custom_tabs = get_custom_tabs(s, loc.id, "tanker_transactions")
                custom_tabs = [t for t in custom_tabs if t.get("active", True)]
        except Exception:
            pass
        
        if custom_tabs:
            # Use tabs if custom tabs exist
            tab_labels = ["Tanker Dispatch"] + [t.get("name", "Custom") for t in custom_tabs]
            tabs = st.tabs(tab_labels)
            
            # Main tanker dispatch tab
            with tabs[0]:
                _render_saved_transactions(loc.id, can_make_entries)
                st.markdown("---")
                _render_entry_form(loc, can_make_entries, tankers)
            
            # Custom tabs
            for idx, custom_tab in enumerate(custom_tabs, start=1):
                with tabs[idx]:
                    _render_custom_tanker_tab(loc, user, custom_tab)
        else:
            # No custom tabs, render normally
            _render_saved_transactions(loc.id, can_make_entries)
            st.markdown("---")
            _render_entry_form(loc, can_make_entries, tankers)

    except Exception as exc:  # pragma: no cover
        st.error("Unexpected error while rendering Tanker Transactions.")
        log_error(f"Tanker Transactions page failed: {exc}", exc_info=True)


def _render_custom_tanker_tab(loc, user, tab_def: dict):
    """
    Render a custom tab for tanker transactions with dynamic columns.
    
    Args:
        loc: Location object
        user: User dict
        tab_def: Tab definition with columns and table_name
    """
    import json
    from models import get_custom_table_model
    
    # Import the formula evaluator from tank_transactions
    try:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from tank_transactions import _evaluate_formula
    except Exception:
        # Fallback: define a simple evaluator
        def _evaluate_formula(formula, row_data):
            if not formula:
                return None
            operation = formula.get("operation", "sum")
            columns = formula.get("columns", [])
            values = []
            for col in columns:
                val = row_data.get(col)
                if val is not None:
                    try:
                        values.append(float(val))
                    except (ValueError, TypeError):
                        pass
            if not values:
                return None
            if operation == "sum":
                return sum(values)
            elif operation == "subtract":
                result = values[0]
                for v in values[1:]:
                    result -= v
                return result
            elif operation == "multiply":
                result = values[0]
                for v in values[1:]:
                    result *= v
                return result
            elif operation == "divide":
                result = values[0]
                for v in values[1:]:
                    if v == 0:
                        return None
                    result /= v
                return result
            elif operation == "percentage":
                if len(values) >= 2 and values[1] != 0:
                    return (values[0] / values[1]) * 100
                return None
            elif operation == "maximum":
                return max(values)
            elif operation == "minimum":
                return min(values)
            elif operation == "average":
                return sum(values) / len(values)
            return None
    
    tab_name = tab_def.get("name", "Custom Tab")
    table_name = tab_def.get("table_name")
    columns = tab_def.get("columns", [])
    
    st.markdown(f"#### {tab_name}")
    
    if not columns:
        st.info(f"No columns defined for {tab_name}. Configure in **Page Customization**.")
        return
    
    if not table_name:
        st.error("No table name defined for this custom tab.")
        return
    
    # Separate manual and calculated columns
    date_fields = [c for c in columns if c.get("type") == "date"]
    date_name = date_fields[0]["name"] if date_fields else None
    manual_columns = [c for c in columns if not c.get("formula")]
    calculated_columns = [c for c in columns if c.get("formula")]
    
    with st.form(key=f"custom_tanker_tab_form_{table_name}_{loc.id}"):
        row = {}
        
        # Render manual input columns
        for i, col in enumerate(manual_columns):
            ctype = col.get("type", "text")
            label = col.get("label") or col.get("name")
            name = col.get("name")
            
            if ctype == "date":
                row[name] = st.date_input(label, max_value=date.today(), key=f"custom_tanker_{table_name}_{loc.id}_date_{i}")
            elif ctype == "number":
                row[name] = st.number_input(label, step=0.01, format="%.2f", key=f"custom_tanker_{table_name}_{loc.id}_num_{i}")
            else:
                row[name] = st.text_input(label, key=f"custom_tanker_{table_name}_{loc.id}_txt_{i}")
        
        # Calculate and display calculated columns
        if calculated_columns:
            st.markdown("##### 🧮 Calculated Columns (Auto-computed)")
            for calc_col in calculated_columns:
                formula = calc_col.get("formula")
                label = calc_col.get("label") or calc_col.get("name")
                name = calc_col.get("name")
                
                calculated_value = _evaluate_formula(formula, row)
                
                if calculated_value is not None:
                    st.metric(label, f"{calculated_value:.2f}")
                    row[name] = calculated_value
                else:
                    operation = formula.get("operation", "N/A")
                    cols_used = ", ".join(formula.get("columns", []))
                    st.info(f"**{label}**: {operation.upper()}({cols_used}) - Will be calculated after input")
                    row[name] = None
        
        submitted = st.form_submit_button("💾 Save Row", type="primary")
    
    if not submitted:
        return
    
    # Validate required fields
    errs = []
    for col in columns:
        if col.get("required", False):
            nm = col["name"]
            val = row.get(nm)
            if col.get("formula"):
                continue
            if col.get("type") == "text" and (val is None or str(val).strip() == ""):
                errs.append(f"'{col.get('label')}' is required.")
            elif col.get("type") in ("number", "date") and val is None:
                errs.append(f"'{col.get('label')}' is required.")
    
    if errs:
        for e in errs:
            st.error(e)
        return
    
    # Recalculate all formulas before saving
    for calc_col in calculated_columns:
        formula = calc_col.get("formula")
        name = calc_col.get("name")
        calculated_value = _evaluate_formula(formula, row)
        row[name] = calculated_value
    
    # Get tx_date
    tx_date = None
    if date_name and row.get(date_name):
        tx_date = row[date_name]
    
    # Save to custom table
    try:
        CustomModel = get_custom_table_model(table_name)
        
        if CustomModel:
            with get_session() as s:
                # Prepare data for insertion
                record_data = {
                    "location_id": loc.id,
                    "tx_date": tx_date,
                    "created_by": (user or {}).get("username", "system"),
                }
                
                # Add custom columns
                for col in columns:
                    col_name = col.get("name")
                    if col_name and col_name in row:
                        record_data[col_name] = row[col_name]
                
                # Create record
                record = CustomModel(**record_data)
                s.add(record)
                s.commit()
                
                try:
                    from security import SecurityManager
                    SecurityManager.log_audit(
                        s, (user or {}).get("username", "system"),
                        "CREATE",
                        resource_type=f"CustomTab:{tab_name}",
                        resource_id=str(getattr(record, "id", "")),
                        details=f"Custom tanker tab row saved: {row}",
                        user_id=(user or {}).get("id"),
                        location_id=loc.id,
                        ip_address=st.session_state.get("client_ip"),
                        success=True
                    )
                except Exception:
                    pass
                
                st.success(f"Row saved to {tab_name}.")
        else:
            st.error(f"Database table `{table_name}` not found. Please contact administrator.")
    except Exception as ex:
        st.error(f"Failed to save: {ex}")
