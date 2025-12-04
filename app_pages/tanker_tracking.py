# app_pages/tanker_tracking.py
from __future__ import annotations

from datetime import date, datetime, time as dt_time, timedelta
from typing import Any, Dict, List, Optional, Tuple
import bisect
import io
import base64

import streamlit as st
import streamlit.components.v1 as components
from sqlalchemy import and_
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from db import get_session
from ui import header
from security import SecurityManager
from models import (
    Location,
    TankerCalibration,
    TankerReceipt,
    TankerReceiptStatus,
    TankerTransaction,
)
from location_config import get_tanker_tracking_config
from deletion_approval import render_deletion_ui
from utils_calc import (
    api60_from_api_obs,
    api60_from_density_obs,
    api_from_density,
    c_to_f,
    density_from_api,
    f_to_c,
    get_lt_factor,
    normalize_temp_unit,
    vcf_from_api60_and_tank_temp,
)

try:  # pragma: no cover
    from permission_manager import PermissionManager
except Exception:  # pragma: no cover
    PermissionManager = None


LITRES_PER_BBL = 158.987
API_LIMITS = (15.0, 70.0)
DENSITY_LIMITS = (600.0, 1000.0)
RECEIPT_STATUSES = [s.value for s in TankerReceiptStatus]


def _safe_rerun() -> None:
    st.rerun()


def _normalize_token(text: Optional[str]) -> str:
    raw = (text or "").strip().lower()
    for ch in (" ", "-", "_"):
        raw = raw.replace(ch, "")
    return raw


def _destination_matches(value: Optional[str], aliases: List[str]) -> bool:
    if not aliases:
        return True
    needle = _normalize_token(value)
    if not needle:
        return False
    alias_tokens = {_normalize_token(a) for a in aliases if a}
    return needle in alias_tokens


def _guard_location(active_location_id: Optional[int]) -> Tuple[Optional[Location], Optional[str]]:
    if not active_location_id:
        st.warning("No active location selected. Go to Home and pick a location first.")
        return None, None
    with get_session() as session:
        loc = session.query(Location).get(active_location_id)
        if not loc:
            st.warning("Selected location could not be found. Please re-select on Home.")
            return None, None
        return loc, f"{loc.name} ({loc.code})"


def _guard_permissions(user: Optional[Dict[str, Any]], location_id: int, cfg: Dict[str, Any]) -> Tuple[bool, bool]:
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
        except Exception:
            return False, False

    if not cfg.get("page_enabled", False):
        st.warning("Tanker Tracking is disabled for this location. Enable it from Location Settings.")
        return False, False

    feature_allowed = True
    can_make_entries = True
    allowed_locations: List[str] = []
    if PermissionManager and user:
        try:
            with get_session() as session:
                feature_allowed = PermissionManager.can_access_feature(
                    session, location_id, "tanker_tracking", role
                )
                can_make_entries = PermissionManager.can_make_entries(session, role, location_id)
                if not feature_allowed:
                    allowed_locations = PermissionManager.get_allowed_locations_for_feature(
                        session, "tanker_tracking"
                    )
        except Exception:
            feature_allowed = True
            can_make_entries = True

    if not feature_allowed:
        st.error("Access denied. Tanker Tracking is not available at this location.")
        if allowed_locations:
            st.info("Feature currently enabled at: " + ", ".join(sorted(set(allowed_locations))))
        return False, False

    return True, can_make_entries


def _load_location_lookup(session) -> Dict[int, Dict[str, str]]:
    out: Dict[int, Dict[str, str]] = {}
    for loc in session.query(Location).all():
        out[loc.id] = {"name": loc.name, "code": loc.code}
    return out


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


def _calibration_max_cm(session, tanker_name: str, compartment: str) -> float:
    row = (
        session.query(TankerCalibration.dip_mm)
        .filter(TankerCalibration.tanker_name == tanker_name)
        .order_by(TankerCalibration.dip_mm.desc())
        .first()
    )
    if not row or not row[0]:
        return 0.0
    return float(row[0]) / 10.0


def _calculate_receipt_payload(
    session,
    dispatch: TankerTransaction,
    *,
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
) -> Dict[str, Any]:
    if total_dip_cm <= 0:
        raise ValueError("Total dip must be greater than zero.")
    max_dip_cm = _calibration_max_cm(session, dispatch.tanker_name, dispatch.manhole)
    if max_dip_cm and (total_dip_cm > max_dip_cm or water_dip_cm > max_dip_cm):
        raise ValueError(f"Dip exceeds calibration maximum ({max_dip_cm:.1f} cm).")

    total_l = _interpolate_tanker_volume(session, dispatch.tanker_name, dispatch.manhole, total_dip_cm * 10.0)
    water_l = _interpolate_tanker_volume(session, dispatch.tanker_name, dispatch.manhole, water_dip_cm * 10.0)
    if total_l <= 0:
        raise ValueError("No calibration data for this tanker/compartment.")

    total_bbl = total_l / LITRES_PER_BBL
    water_bbl = water_l / LITRES_PER_BBL
    gov_bbl = max(total_bbl - water_bbl, 0.0)

    tank_unit_norm = normalize_temp_unit(tank_temp_unit)
    sample_unit_norm = normalize_temp_unit(sample_temp_unit)

    if obs_mode == "Observed API":
        api60 = api60_from_api_obs(api_observed, sample_temp_value, sample_unit_norm)
        density_val = density_from_api(api_observed)
    else:
        api60 = api60_from_density_obs(density_observed, sample_temp_value, sample_unit_norm)
        density_val = density_observed
        api_observed = api_from_density(density_observed)

    vcf_val = vcf_from_api60_and_tank_temp(api60, tank_temp_value, tank_unit_norm)
    gsv_bbl = gov_bbl * vcf_val
    bsw_val = max(min(float(bsw_pct or 0.0), 100.0), 0.0)
    bsw_vol_bbl = gsv_bbl * (bsw_val / 100.0)
    nsv_bbl = gsv_bbl - bsw_vol_bbl
    try:
        lt_factor = get_lt_factor(session, api60) if api60 > 0 else 0.0
    except Exception:
        lt_factor = 0.0
    lt_val = nsv_bbl * lt_factor
    mt_val = lt_val * 1.01605

    if tank_unit_norm == "C":
        tank_temp_c, tank_temp_f = tank_temp_value, c_to_f(tank_temp_value)
    else:
        tank_temp_f, tank_temp_c = tank_temp_value, f_to_c(tank_temp_value)
    if sample_unit_norm == "C":
        sample_temp_c, sample_temp_f = sample_temp_value, c_to_f(sample_temp_value)
    else:
        sample_temp_f, sample_temp_c = sample_temp_value, f_to_c(sample_temp_value)

    return {
        "total_dip_cm": float(total_dip_cm),
        "water_dip_cm": float(water_dip_cm),
        "bsw_pct": float(bsw_val),
        "tank_temp_c": float(tank_temp_c),
        "tank_temp_f": float(tank_temp_f),
        "sample_temp_c": float(sample_temp_c),
        "sample_temp_f": float(sample_temp_f),
        "api_observed": float(api_observed),
        "density_observed": float(density_val),
        "api60": float(api60),
        "vcf": float(vcf_val),
        "total_volume_bbl": float(total_bbl),
        "water_volume_bbl": float(water_bbl),
        "gov_bbl": float(gov_bbl),
        "gsv_bbl": float(gsv_bbl),
        "bsw_vol_bbl": float(bsw_vol_bbl),
        "nsv_bbl": float(nsv_bbl),
        "lt": float(lt_val),
        "mt": float(mt_val),
    }


def _load_dispatches(
    session, source_ids: List[int], start_date: Optional[date], end_date: Optional[date]
) -> List[TankerTransaction]:
    if not source_ids:
        return []
    query = session.query(TankerTransaction).filter(TankerTransaction.location_id.in_(source_ids))
    if start_date:
        query = query.filter(TankerTransaction.transaction_date >= start_date)
    if end_date:
        query = query.filter(TankerTransaction.transaction_date <= end_date)
    return (
        query.order_by(TankerTransaction.transaction_date.desc(), TankerTransaction.transaction_time.desc())
        .limit(400)
        .all()
    )


def _map_receipts(session, dispatch_ids: List[int]) -> Dict[int, TankerReceipt]:
    if not dispatch_ids:
        return {}
    rows = (
        session.query(TankerReceipt)
        .filter(TankerReceipt.dispatch_id.in_(dispatch_ids))
        .all()
    )
    return {r.dispatch_id: r for r in rows}


def _split_receiver_lists(
    dispatches: List[TankerTransaction], receipts: Dict[int, TankerReceipt]
) -> tuple[List[TankerTransaction], List[TankerTransaction]]:
    pending: List[TankerTransaction] = []
    completed: List[TankerTransaction] = []
    for tx in dispatches:
        status = _status_value(receipts.get(tx.id)).upper()
        if status == "PENDING":
            pending.append(tx)
        else:
            completed.append(tx)
    return pending, completed


def _status_value(receipt: Optional[TankerReceipt]) -> str:
    if not receipt:
        return "PENDING"
    val = getattr(receipt, "status", None)
    return val.value if hasattr(val, "value") else str(val)


def _build_rows(
    dispatches: List[TankerTransaction],
    receipts: Dict[int, TankerReceipt],
    loc_lookup: Dict[int, Dict[str, str]],
    receiver_location_id: Optional[int] = None,
    mismatch_ids: Optional[set[int]] = None,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    receiver_label = ""
    if receiver_location_id is not None:
        receiver_label = loc_lookup.get(receiver_location_id, {}).get("name") or str(receiver_location_id)
    for tx in dispatches:
        rec = receipts.get(tx.id)
        status = _status_value(rec)
        rec_nsv = getattr(rec, "nsv_bbl", None)
        dispatch_nsv = float(getattr(tx, "nsv_bbl", 0.0) or 0.0)
        variance = rec_nsv - dispatch_nsv if rec_nsv is not None else None
        loc_meta = loc_lookup.get(tx.location_id, {})
        row = {
            "ID": tx.id,
            "Date": tx.transaction_date,
            "Convoy": tx.convoy_no,
            "Tanker": tx.tanker_name,
            "From": loc_meta.get("name") or tx.location_id,
            "Destination": tx.destination,
            "Cargo": tx.cargo,
            "Dispatch NSV (bbl)": round(dispatch_nsv, 2),
            "Received NSV (bbl)": round(rec_nsv, 2) if rec_nsv is not None else None,
            "Variance (bbl)": round(variance, 2) if variance is not None else None,
            "Status": status,
            "Receiver": receiver_label,
        }
        if mismatch_ids is not None:
            row["Dest Match"] = "✅" if tx.id not in mismatch_ids else "⚠️"
        if rec and getattr(rec, "updated_by", None):
            row["Edited"] = f"⚠️ {rec.updated_by} @ {rec.updated_at.strftime('%Y-%m-%d %H:%M') if rec.updated_at else ''}"
        rows.append(row)
    return rows


def _prefill_receipt_state(selected_id: int, dispatch: TankerTransaction, receipt: Optional[TankerReceipt]) -> None:
    ss = st.session_state
    if ss.get("tt_prefill_id") == selected_id:
        return
    ss["tt_prefill_id"] = selected_id
    ss["tt_arrival_date"] = receipt.arrival_date if receipt else date.today()
    ss["tt_arrival_time"] = receipt.arrival_time if receipt else (dispatch.transaction_time or dt_time(8, 0))
    ss["tt_total_dip_cm"] = float(getattr(receipt, "total_dip_cm", dispatch.total_dip_cm or 0.0) or 0.0)
    ss["tt_water_dip_cm"] = float(getattr(receipt, "water_dip_cm", dispatch.water_dip_cm or 0.0) or 0.0)
    ss["tt_bsw_pct"] = float(getattr(receipt, "bsw_pct", dispatch.bsw_pct or 0.0) or 0.0)
    ss["tt_obs_mode"] = "Observed API"

    if receipt and receipt.api_observed:
        ss["tt_obs_mode"] = "Observed API"
        ss["tt_api_observed"] = float(receipt.api_observed)
        ss["tt_density_observed"] = float(receipt.density_observed or density_from_api(receipt.api_observed))
    else:
        ss["tt_api_observed"] = float(dispatch.api_observed or API_LIMITS[0])
        ss["tt_density_observed"] = float(dispatch.density_observed or density_from_api(ss["tt_api_observed"]))

    tank_temp_c = getattr(receipt, "tank_temp_c", dispatch.tank_temp_c)
    tank_temp_f = getattr(receipt, "tank_temp_f", dispatch.tank_temp_f)
    sample_temp_c = getattr(receipt, "sample_temp_c", dispatch.sample_temp_c)
    sample_temp_f = getattr(receipt, "sample_temp_f", dispatch.sample_temp_f)

    if tank_temp_c is not None:
        ss["tt_tank_temp_unit"] = "C"
        ss["tt_tank_temp_value"] = float(tank_temp_c)
    elif tank_temp_f is not None:
        ss["tt_tank_temp_unit"] = "F"
        ss["tt_tank_temp_value"] = float(tank_temp_f)
    else:
        ss["tt_tank_temp_unit"] = "C"
        ss["tt_tank_temp_value"] = 30.0

    if sample_temp_c is not None:
        ss["tt_sample_temp_unit"] = "C"
        ss["tt_sample_temp_value"] = float(sample_temp_c)
    elif sample_temp_f is not None:
        ss["tt_sample_temp_unit"] = "F"
        ss["tt_sample_temp_value"] = float(sample_temp_f)
    else:
        ss["tt_sample_temp_unit"] = "F"
        ss["tt_sample_temp_value"] = 80.0

    ss["tt_status"] = _status_value(receipt)
    ss["tt_notes"] = getattr(receipt, "receiver_notes", "") or ""


def _render_sender_tab(
    loc: Location,
    rows: List[Dict[str, Any]],
    can_edit: bool,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> None:
    st.markdown("#### Sender Desk")
    st.caption("Shows dispatches from this location and whether the receiver has acknowledged them.")
    if not rows:
        st.info("No tanker dispatches recorded for this location in the selected window.")
        return

    # Filters (date range, convoy, tanker, status)
    dates = [r.get("Date") for r in rows if isinstance(r.get("Date"), date)]
    min_date = min(dates) if dates else date.today()
    max_date = max(dates) if dates else date.today()
    d_start = start_date or max(min_date, max_date - timedelta(days=7))
    d_end = end_date or max_date
    if d_start > d_end:
        d_start, d_end = d_end, d_start

    convoys = sorted({r.get("Convoy") for r in rows if r.get("Convoy")})
    tankers = sorted({r.get("Tanker") for r in rows if r.get("Tanker")})
    statuses = sorted({r.get("Status") for r in rows if r.get("Status")})

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        dr = st.date_input("Date Range", value=(d_start, d_end), key="tt_sender_dates")
        if isinstance(dr, (list, tuple)) and len(dr) == 2:
            d_start, d_end = dr
        elif isinstance(dr, date):
            d_start = d_end = dr
        if d_start > d_end:
            d_start, d_end = d_end, d_start
    with c2:
        sel_convoys = st.multiselect("Convoy No", convoys, default=convoys, key="tt_sender_convoys")
    with c3:
        sel_tankers = st.multiselect("Tanker No", tankers, default=tankers, key="tt_sender_tankers")
    with c4:
        sel_status = st.multiselect("Status", statuses or ["PENDING", "RECEIVED"], default=statuses or ["PENDING", "RECEIVED"], key="tt_sender_status")

    filtered = [
        r for r in rows
        if d_start <= r.get("Date", d_start) <= d_end
        and (not sel_convoys or r.get("Convoy") in sel_convoys)
        and (not sel_tankers or r.get("Tanker") in sel_tankers)
        and (not sel_status or r.get("Status") in sel_status)
    ]

    pending = sum(1 for r in filtered if (r.get("Status") or "").upper() == "PENDING")
    received = sum(1 for r in filtered if (r.get("Status") or "").upper() == "RECEIVED")
    st.metric("Pending Receipts", pending)
    st.metric("Received", received)

    st.dataframe(filtered, use_container_width=True, hide_index=True)


def _render_receiver_tab(
    loc: Location,
    dispatches: List[TankerTransaction],
    receipts: Dict[int, TankerReceipt],
    loc_lookup: Dict[int, Dict[str, str]],
    aliases: List[str],
    can_edit: bool,
) -> None:
    st.markdown("#### Receiver Desk")
    st.caption("Select a tanker to record dips, quality and acknowledge receipt.")

    if not dispatches:
        st.info("No incoming tanker dispatches match the selected filters.")
        return

    _render_receipt_editor(
        loc=loc,
        dispatches=dispatches,
        receipts=receipts,
        loc_lookup=loc_lookup,
        aliases=aliases,
        can_edit=can_edit,
        tab_key="pending",
        show_delete=False,
    )


def _save_receipt(
    session,
    dispatch_id: int,
    receiver_location_id: int,
    status: str,
    arrival_date: date,
    arrival_time: dt_time,
    notes: str,
    payload: Dict[str, Any],
) -> None:
    username = (st.session_state.get("auth_user") or {}).get("username", "system")
    user_id = (st.session_state.get("auth_user") or {}).get("id")
    ts = datetime.combine(arrival_date, arrival_time) if arrival_date else None

    tx = session.query(TankerTransaction).get(dispatch_id)
    if not tx:
        raise ValueError("Dispatch not found.")

    receipt = session.query(TankerReceipt).filter(TankerReceipt.dispatch_id == dispatch_id).one_or_none()
    creating = False
    if not receipt:
        receipt = TankerReceipt(dispatch_id=dispatch_id, receiver_location_id=receiver_location_id, created_by=username)
        session.add(receipt)
        creating = True
    if receipt.receiver_location_id != receiver_location_id:
        receipt.receiver_location_id = receiver_location_id

    for key, value in payload.items():
        setattr(receipt, key, value)

    try:
        receipt.status = TankerReceiptStatus(status)
    except Exception:
        receipt.status = TankerReceiptStatus.PENDING

    receipt.arrival_date = arrival_date
    receipt.arrival_time = arrival_time
    receipt.received_at = ts
    receipt.receiver_notes = notes.strip() or None
    receipt.updated_by = username
    receipt.updated_at = datetime.utcnow()

    session.commit()

    try:
        SecurityManager.log_audit(
            None,
            username,
            "CREATE" if creating else "UPDATE",
            resource_type="TankerReceipt",
            resource_id=str(receipt.id),
            details=f"{'Created' if creating else 'Updated'} tanker receipt for dispatch {dispatch_id}",
            user_id=user_id,
            location_id=receiver_location_id,
        )
    except Exception:
        pass


def _render_receipt_editor(
    loc: Location,
    dispatches: List[TankerTransaction],
    receipts: Dict[int, TankerReceipt],
    loc_lookup: Dict[int, Dict[str, str]],
    aliases: List[str],
    can_edit: bool,
    tab_key: str,
    show_delete: bool,
) -> None:
    options = []
    mismatches: set[int] = set()
    tx_by_label: Dict[str, TankerTransaction] = {}
    for tx in dispatches:
        matches_alias = _destination_matches(tx.destination, aliases)
        if not matches_alias:
            mismatches.add(tx.id)
        label = (
            f"{tx.transaction_date} | Convoy {tx.convoy_no} | {tx.tanker_name} "
            f"| From {loc_lookup.get(tx.location_id, {}).get('name', tx.location_id)} "
            f"| Dest {tx.destination or 'N/A'}"
        )
        if not matches_alias:
            label += " (dest mismatch)"
        options.append(label)
        tx_by_label[label] = tx

    if not options:
        st.info("No dispatches found for the configured sender locations.")
        return

    select_key = f"tt_selector_{tab_key}"
    selected_label = st.selectbox("Incoming tanker", options, key=select_key)
    dispatch = tx_by_label[selected_label]
    receipt = receipts.get(dispatch.id)

    if dispatch.id in mismatches:
        st.warning(
            "Destination on the dispatch does not match this receiver's aliases. Entry is still shown because the sender "
            "location is allowed. Update the destination on the dispatch or adjust aliases in Location Settings."
        )

    _prefill_receipt_state(dispatch.id, dispatch, receipt)
    ss = st.session_state

    info_cols = st.columns(4)
    info_cols[0].metric("Dispatch GOV (bbl)", f"{dispatch.gov_bbl:,.2f}")
    info_cols[1].metric("Dispatch GSV (bbl)", f"{dispatch.gsv_bbl:,.2f}")
    info_cols[2].metric("Dispatch NSV (bbl)", f"{dispatch.nsv_bbl:,.2f}")
    info_cols[3].metric("BSW %", f"{dispatch.bsw_pct:,.2f}")

    if receipt and receipt.updated_by and receipt.updated_at:
        st.caption(f"⚠️ Edited by {receipt.updated_by} on {receipt.updated_at.strftime('%Y-%m-%d %H:%M')}")

    with st.container():
        meta_c1, meta_c2 = st.columns(2)
        arrival_date = meta_c1.date_input("Arrival Date", value=ss.get("tt_arrival_date", date.today()), max_value=date.today())
        arrival_time = meta_c2.time_input("Arrival Time", value=ss.get("tt_arrival_time", dt_time(8, 0)))

        dip_c1, dip_c2, dip_c3 = st.columns(3)
        total_dip_cm = dip_c1.number_input("Total Dip (cm)", min_value=0.0, step=0.1, value=float(ss.get("tt_total_dip_cm", 0.0)))
        water_dip_cm = dip_c2.number_input("Water Dip (cm)", min_value=0.0, step=0.1, value=float(ss.get("tt_water_dip_cm", 0.0)))
        bsw_pct = dip_c3.number_input("BS&W %", min_value=0.0, max_value=100.0, step=0.1, value=float(ss.get("tt_bsw_pct", 0.0)))

        temp_c1, temp_c2 = st.columns(2)
        tank_temp_unit = temp_c1.selectbox("Tank Temp Unit", ["C", "F"], index=0 if ss.get("tt_tank_temp_unit", "C") == "C" else 1)
        tank_temp_value = temp_c1.number_input("Tank Temperature", min_value=-50.0, max_value=120.0, step=0.1, value=float(ss.get("tt_tank_temp_value", 30.0)))
        obs_mode = temp_c2.selectbox("Observed Property", ["Observed API", "Observed Density"], index=0 if ss.get("tt_obs_mode", "Observed API") == "Observed API" else 1)
        sample_temp_unit = temp_c2.selectbox("Sample Temp Unit", ["F", "C"], index=0 if ss.get("tt_sample_temp_unit", "F") == "F" else 1)
        sample_temp_value = temp_c2.number_input(
            "Sample Temperature",
            min_value=-50.0,
            max_value=120.0,
            step=0.1,
            value=float(ss.get("tt_sample_temp_value", 80.0)),
        )

        if obs_mode == "Observed API":
            api_observed = temp_c2.number_input(
                "Observed API",
                min_value=API_LIMITS[0],
                max_value=API_LIMITS[1],
                step=0.1,
                value=float(ss.get("tt_api_observed", API_LIMITS[0])),
            )
            density_observed = density_from_api(api_observed)
        else:
            density_observed = temp_c2.number_input(
                "Observed Density (kg/m3)",
                min_value=DENSITY_LIMITS[0],
                max_value=DENSITY_LIMITS[1],
                step=0.1,
                value=float(ss.get("tt_density_observed", DENSITY_LIMITS[0])),
            )
            api_observed = api_from_density(density_observed)

        status_default = ss.get("tt_status", "RECEIVED")
        status_idx = RECEIPT_STATUSES.index(status_default) if status_default in RECEIPT_STATUSES else 0
        status = st.selectbox(
            "Receipt Status",
            RECEIPT_STATUSES,
            index=status_idx,
        )
        notes = st.text_area("Receiver Notes", value=ss.get("tt_notes", ""))

    preview = {}
    preview_error = None
    try:
        with get_session() as session:
            preview = _calculate_receipt_payload(
                session,
                dispatch,
                total_dip_cm=total_dip_cm,
                water_dip_cm=water_dip_cm,
                bsw_pct=bsw_pct,
                tank_temp_unit=tank_temp_unit,
                tank_temp_value=tank_temp_value,
                sample_temp_unit=sample_temp_unit,
                sample_temp_value=sample_temp_value,
                obs_mode=obs_mode,
                api_observed=api_observed,
                density_observed=density_observed,
            )
    except Exception as exc:
        preview_error = str(exc)

    if preview:
        st.markdown("##### Auto-calculated Volumes")
        met1, met2, met3, met4 = st.columns(4)
        met1.metric("GOV (bbl)", f"{preview['gov_bbl']:,.2f}")
        met2.metric("GSV (bbl)", f"{preview['gsv_bbl']:,.2f}")
        met3.metric("NSV (bbl)", f"{preview['nsv_bbl']:,.2f}")
        met4.metric("VCF", f"{preview['vcf']:.5f}")

        variance = preview["nsv_bbl"] - float(dispatch.nsv_bbl or 0.0)
        st.info(f"Variance vs dispatch NSV: {variance:+.2f} bbl")
    elif preview_error:
        st.warning(f"Volume preview unavailable: {preview_error}")

    disabled = not can_edit
    if disabled:
        st.caption("You have read-only access at this location.")

    if st.button("💾", type="primary", disabled=disabled, key=f"tt_save_receipt_{tab_key}", help="Save Receipt"):
        if not arrival_date or not isinstance(arrival_date, date):
            st.error("Arrival date is required.")
            return
        try:
            with get_session() as session:
                payload = preview or _calculate_receipt_payload(
                    session,
                    dispatch,
                    total_dip_cm=total_dip_cm,
                    water_dip_cm=water_dip_cm,
                    bsw_pct=bsw_pct,
                    tank_temp_unit=tank_temp_unit,
                    tank_temp_value=tank_temp_value,
                    sample_temp_unit=sample_temp_unit,
                    sample_temp_value=sample_temp_value,
                    obs_mode=obs_mode,
                    api_observed=api_observed,
                    density_observed=density_observed,
                )
                _save_receipt(
                    session,
                    dispatch.id,
                    loc.id,
                    status,
                    arrival_date,
                    arrival_time or dt_time(0, 0),
                    notes,
                    payload,
                )
            st.success("Receipt saved.")
            _safe_rerun()
        except Exception as exc:
            st.error(f"Failed to save receipt: {exc}")

    if show_delete and receipt:
        st.markdown("---")
        st.markdown("#### Delete Receipt (requires supervisor approval for operators)")

        def _delete():
            with get_session() as s:
                rec = s.query(TankerReceipt).filter(TankerReceipt.id == receipt.id).one_or_none()
                if rec:
                    s.delete(rec)
                    s.commit()

        render_deletion_ui(
            resource_type="TankerReceipt",
            resource_id=receipt.id,
            resource_label=f"Tanker receipt #{receipt.id}",
            delete_func=_delete,
            user=st.session_state.get("auth_user") or {},
            location_id=loc.id,
            on_success_message="Receipt deleted and moved back to Pending.",
            button_key_prefix=f"tt_del_{tab_key}_{receipt.id}",
        )

    rec_rows = _build_rows(dispatches, receipts, loc_lookup, receiver_location_id=loc.id, mismatch_ids=mismatches)
    st.markdown("##### Comparison")
    st.dataframe(rec_rows, use_container_width=True, hide_index=True)


def render_tanker_tracking_page(active_location_id: Optional[int], user: Optional[Dict[str, Any]]) -> None:
    header("Tanker Tracking")
    loc, loc_label = _guard_location(active_location_id)
    if not loc:
        return

    with get_session() as session:
        tt_cfg = get_tanker_tracking_config(session, loc.id)
    allowed, can_make_entries = _guard_permissions(user, loc.id, tt_cfg)
    if not allowed:
        return

    st.caption(f"Active Location: {loc_label}")
    if not tt_cfg.get("is_sender") and not tt_cfg.get("is_receiver"):
        st.warning("This location is not configured as a sender or receiver for tanker tracking.")
        return

    start_date = date.today() - timedelta(days=7)
    end_date = date.today()

    with get_session() as session:
        loc_lookup = _load_location_lookup(session)
        sender_dispatches = _load_dispatches(session, [loc.id], start_date, end_date) if tt_cfg.get("is_sender") else []
        receiver_sources = tt_cfg.get("receiver_sources", [])
        receiver_dispatches = (
            _load_dispatches(session, receiver_sources, start_date, end_date) if tt_cfg.get("is_receiver") else []
        )
        receipts = _map_receipts(
            session, [tx.id for tx in sender_dispatches] + [tx.id for tx in receiver_dispatches]
        )

    pending_dispatches, completed_dispatches = _split_receiver_lists(receiver_dispatches, receipts)

    tab_labels: List[str] = []
    if tt_cfg.get("is_sender"):
        tab_labels.append("Sender Desk")
    if tt_cfg.get("is_receiver"):
        tab_labels += ["Receiver Desk", "Completed Trips", "Comparison Report"]

    if not tab_labels:
        st.info("This location is neither sender nor receiver for tanker tracking.")
        return

    tabs = st.tabs(tab_labels) if len(tab_labels) > 1 else [st.container()]
    tab_idx = 0

    if tt_cfg.get("is_sender"):
        with tabs[tab_idx]:
            rows = _build_rows(sender_dispatches, receipts, loc_lookup)
            _render_sender_tab(loc, rows, can_make_entries, start_date=start_date, end_date=end_date)
        tab_idx += 1

    if tt_cfg.get("is_receiver"):
        with tabs[tab_idx]:
            aliases = tt_cfg.get("receiver_aliases") or [loc.name, loc.code]
            _render_receipt_editor(
                loc=loc,
                dispatches=pending_dispatches,
                receipts=receipts,
                loc_lookup=loc_lookup,
                aliases=aliases,
                can_edit=can_make_entries,
                tab_key="pending",
                show_delete=False,
            )
        tab_idx += 1

        with tabs[tab_idx]:
            aliases = tt_cfg.get("receiver_aliases") or [loc.name, loc.code]
            _render_receipt_editor(
                loc=loc,
                dispatches=completed_dispatches,
                receipts=receipts,
                loc_lookup=loc_lookup,
                aliases=aliases,
                can_edit=can_make_entries,
                tab_key="completed",
                show_delete=True,
            )
        tab_idx += 1

        with tabs[tab_idx]:
            aliases = tt_cfg.get("receiver_aliases") or [loc.name, loc.code]
            _render_comparison_tab(
                loc,
                receiver_dispatches,
                receipts,
                loc_lookup,
                aliases,
                start_date,
                end_date,
            )


def _render_comparison_tab(
    loc: Location,
    dispatches: List[TankerTransaction],
    receipts: Dict[int, TankerReceipt],
    loc_lookup: Dict[int, Dict[str, str]],
    aliases: List[str],
    start_date: date,
    end_date: date,
) -> None:
    st.markdown("#### Comparison Report")
    st.caption("Same comparison table with filters and export.")

    mismatch_ids: set[int] = set()
    for tx in dispatches:
        if not _destination_matches(tx.destination, aliases):
            mismatch_ids.add(tx.id)

    rows = _build_rows(dispatches, receipts, loc_lookup, receiver_location_id=loc.id, mismatch_ids=mismatch_ids)
    if not rows:
        st.info("No records in range.")
        return

    # Filters in one row
    tankers = sorted({r["Tanker"] for r in rows if r.get("Tanker")})
    senders = sorted({r["From"] for r in rows if r.get("From")})
    convoys = sorted({r["Convoy"] for r in rows if r.get("Convoy")})
    f1, f2, f3, f4, f5 = st.columns([1, 1, 1, 1, 1])
    with f1:
        f_start = st.date_input("Start", value=start_date, key="tt_cmp_start")
    with f2:
        f_end = st.date_input("End", value=end_date, key="tt_cmp_end")
    with f3:
        sel_tankers = st.multiselect("Tanker", tankers, default=tankers, key="tt_cmp_tankers")
    with f4:
        sel_senders = st.multiselect("From", senders, default=senders, key="tt_cmp_senders")
    with f5:
        sel_convoys = st.multiselect("Convoy", convoys, default=convoys, key="tt_cmp_convoys")

    if f_start and f_end and f_start > f_end:
        f_start, f_end = f_end, f_start

    filtered = [
        r for r in rows
        if r.get("Tanker") in sel_tankers
        and r.get("From") in sel_senders
        and r.get("Convoy") in sel_convoys
        and f_start <= r.get("Date", f_start) <= f_end
    ]

    st.dataframe(filtered, use_container_width=True, hide_index=True)

    # Totals summary (on-screen)
    if filtered:
        total_dispatch_nsv = sum(float(r.get("Dispatch NSV (bbl)", 0) or 0) for r in filtered)
        total_received_nsv = sum(float(r.get("Received NSV (bbl)", 0) or 0) for r in filtered)
        variance_total = total_received_nsv - total_dispatch_nsv
        st.caption(
            f"Totals — Dispatch NSV: {total_dispatch_nsv:,.2f} bbl | "
            f"Received NSV: {total_received_nsv:,.2f} bbl | "
            f"Variance: {variance_total:+,.2f} bbl"
        )

    # Downloads / View (icon buttons, one row)
    try:
        import pandas as pd  # type: ignore

        df = pd.DataFrame(filtered)
        # Remove columns not needed in PDF/export view
        pdf_df = df.drop(columns=[c for c in ["ID", "Edited", "Dest Match"] if c in df.columns], errors="ignore")

        csv_data = pdf_df.to_csv(index=False).encode("utf-8")

        xlsx_buffer = io.BytesIO()
        with pd.ExcelWriter(xlsx_buffer, engine="xlsxwriter") as writer:
            pdf_df.to_excel(writer, index=False, sheet_name="Comparison")
        xlsx_buffer.seek(0)

        # Build real PDF with ReportLab (styled table)
        pdf_buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            pdf_buffer,
            pagesize=landscape(A4),
            topMargin=24,
            bottomMargin=24,
            leftMargin=24,
            rightMargin=24,
        )
        styles = getSampleStyleSheet()
        story = [
            Paragraph("Tanker Comparison Report", styles["Heading1"]),
            Paragraph(f"Date Range: {f_start} to {f_end}", styles["Normal"]),
            Spacer(1, 12),
        ]
        table_data = [list(pdf_df.columns)] + pdf_df.fillna("").values.tolist()
        tbl = Table(table_data, repeatRows=1)
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor("#f8fafc")]),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(tbl)

        # Totals summary
        total_dispatch_nsv = sum(float(r.get("Dispatch NSV (bbl)", 0) or 0) for r in filtered)
        total_received_nsv = sum(float(r.get("Received NSV (bbl)", 0) or 0) for r in filtered)
        variance_total = total_received_nsv - total_dispatch_nsv
        story.append(Spacer(1, 12))
        story.append(
            Paragraph(
                f"Totals — Dispatch NSV: {total_dispatch_nsv:,.2f} bbl | "
                f"Received NSV: {total_received_nsv:,.2f} bbl | "
                f"Variance: {variance_total:+,.2f} bbl",
                styles["Normal"],
            )
        )
        doc.build(story)
        pdf_buffer.seek(0)
        pdf_bytes = pdf_buffer.getvalue()
        pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

        btns = st.columns(4)
        with btns[0]:
            st.download_button("📄", data=pdf_bytes, file_name="tanker_comparison.pdf", mime="application/pdf", help="Download PDF")
        with btns[1]:
            st.download_button("📑", data=csv_data, file_name="tanker_comparison.csv", mime="text/csv", help="Download CSV")
        with btns[2]:
            st.download_button("📊", data=xlsx_buffer.getvalue(), file_name="tanker_comparison.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", help="Download XLSX")
        with btns[3]:
            if st.button("🖨️", help="View PDF", key="tt_cmp_viewpdf"):
                components.html(
                    f"""
                    <script>
                    const b64 = "{pdf_b64}";
                    const byteChars = atob(b64);
                    const byteNumbers = new Array(byteChars.length);
                    for (let i = 0; i < byteChars.length; i++) {{
                        byteNumbers[i] = byteChars.charCodeAt(i);
                    }}
                    const byteArray = new Uint8Array(byteNumbers);
                    const blob = new Blob([byteArray], {{type: "application/pdf"}});
                    const url = URL.createObjectURL(blob);
                    window.open(url, "_blank");
                    </script>
                    """,
                    height=0,
                )
    except Exception as exc:
        st.warning(f"Export unavailable: {exc}")
