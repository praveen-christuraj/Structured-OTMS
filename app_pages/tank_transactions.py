import streamlit as st
from datetime import datetime, date, time as dt_time
from typing import Optional
import json
import re
import enum
from sqlalchemy import Enum as SAEnum

from db import get_session
from models import Location, Tank, TankTransaction, CalibrationTank
from security import SecurityManager
from utils_calc import (
    normalize_temp_unit, temp_bounds, bounded_temp,
    c_to_f, f_to_c,
    density_from_api, api_from_density,
    api_observed_to_api60, density_obs_to_api60,
    calculate_vcf, get_lt_factor, vcf_from_api60_and_tank_temp,
    api60_from_api_obs, api60_from_density_obs,
    gsv_from_gov_vcf, bsw_volume_from_gsv_pct, nsv_from_gsv_bsw,
    lt_from_nsv_api, mt_from_lt,
    mass_mt_from_gsv_api60, mass_lt_from_mt
)
from location_config import (
    get_location_page_visibility,
    get_tank_transactions_tab_visibility,
    get_page_section_config,
    get_dynamic_table_def,
    get_location_meters,
    get_active_operation_names,
)

# ----- Optional helpers -----
try:
    from permission_manager import PermissionManager
except Exception:
    PermissionManager = None


# ---------------- small utils ----------------
def _get_client_ip() -> str:
    return str(st.session_state.get("client_ip") or "N/A")


# ---------------- guards / loaders ----------------
def _guard_location(active_location_id):
    if not active_location_id:
        st.warning("No active location is selected. Go to **Home** and select a location first.")
        return None, None
    with get_session() as session:
        loc = session.query(Location).get(active_location_id)
        if not loc:
            st.warning("Selected location was not found. Please re-select from **Home**.")
            return None, None
        return loc, f"{loc.name} ({loc.code})"

def _guard_permissions(user, active_location_id) -> bool:
    role = (user or {}).get("role", "")
    if PermissionManager and user:
        if not PermissionManager.can_access_operational_pages(user):
            st.error(f"Your role **{role}** cannot access operational pages.")
            return False
    if get_location_page_visibility and active_location_id:
        try:
            with get_session() as session:
                flags = get_location_page_visibility(session, active_location_id) or {}
            if not flags.get("show_tank_transactions", True):
                st.error("Tank Transactions are disabled for this location (see **Location Settings**).")
                return False
        except Exception:
            pass
    return True

def _load_tanks(session, location_id: int):
    q = session.query(Tank).filter(Tank.location_id == location_id)
    try:
        from models import TankStatus
        q = q.order_by(Tank.status.desc(), Tank.name.asc())
    except Exception:
        q = q.order_by(Tank.name.asc())
    return q.all()

def _generate_ticket_id(session, location_code: str) -> str:
    today = datetime.utcnow().strftime("%Y%m%d")
    prefix = f"{location_code.upper()}-{today}"
    existing = session.query(TankTransaction.ticket_id).filter(
        TankTransaction.ticket_id.like(f"{prefix}-%")
    ).all()
    if not existing:
        seq = 1
    else:
        seqs = []
        for (tid,) in existing:
            try:
                parts = str(tid).split("-")
                seqs.append(int(parts[-1]))
            except Exception:
                continue
        seq = max(seqs) + 1 if seqs else 1
    return f"{prefix}-{seq:04d}"

# --- Back-compat: old code may call this helper; we define it here too ---
def _detect_operation_enum_info(model_cls, colname: str):
    """
    Return (enum_class, enum_choices) for the given column if it is a SQLAlchemy Enum.
    - enum_class: a Python Enum subclass if present, else None
    - enum_choices: list of string choices if present, else None
    """
    try:
        col = getattr(model_cls.__table__.c, colname)
        typ = getattr(col, "type", None)
        if isinstance(typ, SAEnum):
            enum_cls = getattr(typ, "enum_class", None)
            choices = getattr(typ, "enums", None)
            return enum_cls if isinstance(enum_cls, type) and issubclass(enum_cls, enum.Enum) else None, choices
    except Exception:
        pass
    return None, None

_OP_CLEAN_RE = re.compile(r"[^A-Z0-9_]+")

def _normalize_op_text(text: str) -> str:
    if not text:
        return ""
    t = str(text).upper().replace("-", " ").replace("/", " ").replace("&", " AND ")
    t = "_".join(t.split())
    return _OP_CLEAN_RE.sub("", t)

def _coerce_operation_value(model_cls, colname: str | None, display_text: str):
    """
    Convert a label like 'Opening Stock' into whatever the model column wants:
      - a Python Enum member (if the SA Enum is Python-backed), or
      - one of the allowed strings on a string-backed SA Enum, or
      - fallback to the text.
    """
    if not colname:
        return display_text

    enum_cls, choices = _detect_operation_enum_info(model_cls, colname)
    norm = _normalize_op_text(display_text or "")

    # Python Enum backing
    if enum_cls:
        for member in enum_cls:
            if _normalize_op_text(member.name) == norm or _normalize_op_text(str(member.value)) == norm:
                return member
        for member in enum_cls:  # relaxed prefix match
            n = _normalize_op_text(member.name)
            if n.startswith(norm) or norm.startswith(n):
                return member

    # String-backed SA Enum
    if choices:
        for ch in choices:
            if ch == display_text:
                return ch
        for ch in choices:
            if _normalize_op_text(ch) == norm:
                return ch
        for ch in choices:
            n = _normalize_op_text(ch)
            if n.startswith(norm) or norm.startswith(n):
                return ch

    return display_text

# ---- model-safe helpers ----
def _model_columns(M):
    """Return set of column keys for an SQLAlchemy model class, else fall back to dir()."""
    try:
        return {c.key for c in M.__table__.columns}
    except Exception:
        return set(dir(M))

def _first_present(cols: set, *candidates: str) -> str | None:
    """Return the first name that exists in cols (case-sensitive)."""
    for c in candidates:
        if c in cols:
            return c
    return None


# ---------------- messages ----------------
def _no_meters_message(kind_label: str, user):
    is_admin = False
    try:
        if PermissionManager and user:
            is_admin = PermissionManager.can_access_management_pages(user)
        else:
            is_admin = (user or {}).get("role") in ("admin-it", "admin-operations")
    except Exception:
        is_admin = (user or {}).get("role") in ("admin-it", "admin-operations")

    if is_admin:
        st.info(
            f"No {kind_label} configured for this location. "
            "Go to **Settings → Page Customization** to add meters."
        )
    else:
        st.info(
            f"No {kind_label} configured for this location. "
            "Please contact an admin to add meters in **Settings → Page Customization**."
        )


# ---------------- calibration helpers ----------------
def _interp_vol_bbl(session, tank_id: int, dip_cm_val: float) -> float:
    rows = (
        session.query(CalibrationTank)
        .filter(CalibrationTank.tank_id == tank_id)
        .order_by(CalibrationTank.dip_cm.asc())
        .all()
    )
    if not rows:
        return 0.0
    xs = [float(r.dip_cm) for r in rows]
    ys = [float(r.volume_bbl) for r in rows]
    if dip_cm_val <= xs[0]: return ys[0]
    if dip_cm_val >= xs[-1]: return ys[-1]
    import bisect
    i = bisect.bisect_left(xs, dip_cm_val)
    x0, x1 = xs[i-1], xs[i]
    y0, y1 = ys[i-1], ys[i]
    if x1 == x0: return y0
    return y0 + (y1 - y0) * ((dip_cm_val - x0) / (x1 - x0))

def _get_calibration_min_max(session, tank_id: int) -> tuple[float, float]:
    """Return (min_dip_cm, max_dip_cm) for the tank’s calibration (or (0.0, 0.0) if none)."""
    q = (
        session.query(CalibrationTank)
        .filter(CalibrationTank.tank_id == tank_id)
        .order_by(CalibrationTank.dip_cm.asc())
    )
    rows = q.all()
    if not rows:
        return (0.0, 0.0)
    return float(rows[0].dip_cm or 0.0), float(rows[-1].dip_cm or 0.0)


# ======================= TAB: Tank Entry =======================
def _get_operation_labels_for_tank(location_id: int) -> list[str]:
    try:
        with get_session() as s:
            names = get_active_operation_names(s, location_id, asset="tank")
        return names or []
    except Exception:
        return []

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

def _parse_hhmm(text: str) -> Optional[dt_time]:
    """Parse 'HH:MM' → time or None."""
    if not text:
        return None
    m = _TIME_RE.match(text.strip())
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2))
    return dt_time(hour=hh, minute=mm)

def _render_tab_tank_entry(loc, loc_label, user):
    st.markdown("#### 📝 Tank Entry")

    with get_session() as session:
        tanks = _load_tanks(session, loc.id)
    tank_labels = [f"{t.name}" for t in tanks]
    tank_by_label = {lbl: t for lbl, t in zip(tank_labels, tanks)}

    # Soft-coded operations for asset='tank'
    op_labels = _get_operation_labels_for_tank(loc.id)
    if not op_labels:
        st.warning("No Tank operations configured. Go to **Location Settings → Operations** to create operations.")
        op_labels = ["N/A (configure in Location Settings)"]

    if not tanks:
        st.info("No tanks found for this location. Please add tanks in **Asset Management → Tanks**.")
        return

    # --- Inputs (live) ---
    c1, c2, c3 = st.columns(3)
    with c1:
        tx_date = st.date_input("📅 Date", value=date.today(), key="tx_date")
    with c2:
        # Manual HH:MM (no dropdown) — strict validation
        now_txt = datetime.now().strftime("%H:%M")
        tx_time_txt = st.text_input("⏰ Time (HH:MM)", value=now_txt, key="tx_time_txt", help="Enter time in 24-hour format HH:MM")
        tx_time = _parse_hhmm(tx_time_txt)
        if tx_time is None:
            st.warning("Please enter time in HH:MM (24-hour) format, e.g., 07:30 or 18:05.")
    with c3:
        selected_tank_label = st.selectbox("🛢️ Tank", tank_labels, key="tx_tank_sel")

    # Calibration-bound Dip/Water inputs
    with get_session() as _s:
        tnk = tank_by_label.get(selected_tank_label)
        tnk_id = tnk.id if tnk else None
        if tnk_id:
            min_dip, max_dip = _get_calibration_min_max(_s, tnk_id)
        else:
            min_dip, max_dip = (0.0, 0.0)

    c4, c5, c6 = st.columns(3)
    with c4:
        selected_op_label = st.selectbox("🔁 Operation", op_labels, index=0, key="tx_op")
    with c5:
        # Clamp to calibration; if no calibration, allow any ≥0
        dip_cm = st.number_input(
            f"📏 Dip (cm) *  (max {max_dip:.1f})" if max_dip > 0 else "📏 Dip (cm) *",
            min_value=0.0,
            max_value=max_dip if max_dip > 0 else None,
            step=0.1,
            format="%.1f",
            key="tx_dip",
        )
    with c6:
        water_cm = st.number_input(
            f"💧 Water Level (cm) *  (max {max_dip:.1f})" if max_dip > 0 else "💧 Water Level (cm) *",
            min_value=0.0,
            max_value=max_dip if max_dip > 0 else None,
            step=0.1,
            format="%.1f",
            key="tx_water",
        )

    # Explicit validation if user bypasses UI max (or no calibration exists)
    if max_dip > 0 and (float(dip_cm or 0.0) > max_dip or float(water_cm or 0.0) > max_dip):
        st.error(f"Entered Dip/Water exceeds calibration maximum ({max_dip:.1f} cm) for this tank.")
        return

    # Live TOV/FW/GOV from calibration
    with get_session() as _s:
        if tnk_id:
            tov_bbl = _interp_vol_bbl(_s, tnk_id, float(dip_cm or 0.0))
            fw_bbl  = _interp_vol_bbl(_s, tnk_id, float(water_cm or 0.0)) if float(water_cm or 0.0) > 0 else 0.0
        else:
            tov_bbl, fw_bbl = 0.0, 0.0
    gov_bbl = max(tov_bbl - fw_bbl, 0.0)

    st.caption(f"📊 Live Quantity — TOV: **{tov_bbl:.2f} bbl**  |  FW: **{fw_bbl:.2f} bbl**  |  GOV: **{gov_bbl:.2f} bbl**")
    st.markdown("---")

    # Temperature & observed property
    st.caption("Tank Temperature")
    tcol1, tcol2 = st.columns([0.35, 0.65])
    with tcol1:
        tank_temp_unit = st.selectbox("Unit", ["°C", "°F"], index=0, key="tx_tank_temp_unit")
    with tcol2:
        lo, hi = temp_bounds(tank_temp_unit)
        tank_temp_val = st.number_input(f"Temperature ({tank_temp_unit})", min_value=lo, max_value=hi, step=0.1, format="%.1f", key="tx_tank_temp_val")

    st.caption("Observed Property & Sample Temperature")
    col_mode, col_sample_unit = st.columns([0.48, 0.52])
    with col_mode:
        obs_mode = st.selectbox("Input Type", ["Observed API", "Observed Density (kg/m3)"], index=0, key="tx_obs_mode")
    with col_sample_unit:
        sample_unit = st.selectbox("Sample Temp Unit", ["°F", "°C"], index=0, key="tx_sample_unit")

    slo, shi = temp_bounds(sample_unit)
    sample_temp_val = st.number_input("Sample Temperature", min_value=slo, max_value=shi, step=0.1, format="%.1f", key="tx_sample_temp_val")

    api60_val = 0.0
    api_obs_val = 0.0
    dens_obs_val = 0.0

    if obs_mode == "Observed API":
        api_obs_val = st.number_input("Observed API *", min_value=15.0, max_value=70.0, step=0.1, format="%.1f", key="tx_api_obs")
        api60_val = api60_from_api_obs(api_obs_val or 0.0, sample_temp_val or 0.0, sample_unit)
        dens_obs_val = density_from_api(api_obs_val or 0.0)
        st.caption(f"→ API @ 60°F: **{api60_val:.2f}**   |   ↔ Density (approx): **{dens_obs_val:.1f} kg/m³**")
    else:
        dens_obs_val = st.number_input("Observed Density (kg/m3) *", min_value=600.0, max_value=1000.0, step=0.1, format="%.1f", key="tx_density_obs")
        api_obs_val = api_from_density(dens_obs_val) if dens_obs_val > 0 else 0.0
        api60_val = api60_from_density_obs(dens_obs_val or 0.0, sample_temp_val or 0.0, sample_unit)
        st.caption(f"↔ Observed API (approx): **{api_obs_val:.2f}**   |   → API @ 60°F: **{api60_val:.2f}**")

    bsw_pct = st.number_input("🧯 BS&W (%)", min_value=0.0, max_value=100.0, step=0.01, key="tx_bsw_pct")

    # Computations
    vcf_val = vcf_from_api60_and_tank_temp(api60_val, tank_temp_val, tank_temp_unit)
    gsv_bbl = gsv_from_gov_vcf(gov_bbl, vcf_val)
    bsw_bbl = bsw_volume_from_gsv_pct(gsv_bbl, float(bsw_pct or 0.0))
    nsv_bbl = nsv_from_gsv_bsw(gsv_bbl, bsw_bbl)
    mt = mass_mt_from_gsv_api60(gsv_bbl, api60_val)
    lt = mass_lt_from_mt(mt)

    st.caption(
        f"🧮 Computed — VCF: **{vcf_val:.5f}**  |  GSV: **{gsv_bbl:,.2f} bbl**  |  NSV: **{nsv_bbl:,.2f} bbl**  |  MT: **{mt:,.3f}**  |  LT: **{lt:,.3f}**"
    )

    remarks = st.text_input("📝 Remarks", value="", max_chars=250, key="tx_remarks")

    # Ticket preview
    try:
        with get_session() as s:
            preview_ticket = _generate_ticket_id(s, loc_label.split("(")[-1].split(")")[0])
        st.caption(f"🎫 Ticket (preview): **{preview_ticket}**")
    except Exception:
        st.info("ℹ️ Ticket ID will be generated upon save")

    # Save button
    if st.button("💾 Save to DB", type="primary", key="tx_save_btn"):
        errs = []
        if selected_tank_label not in tank_by_label:
            errs.append("Please select a valid tank.")
        if not tx_date:
            errs.append("Date is required.")
        if not tx_time:
            errs.append("Time is required.")
        if api60_val <= 0:
            errs.append("Computed API @ 60°F is invalid. Please check observed inputs.")
        if vcf_val <= 0:
            errs.append("Computed VCF is invalid. Please check temperatures and API.")
        if errs:
            for e in errs:
                st.error(e)
            return

        try:
            with get_session() as session:
                # Resolve model + columns
                from models import TankTransaction as TT
                cols = _model_columns(TT)

                tnk = tank_by_label[selected_tank_label]
                ticket_id = _generate_ticket_id(session, loc_label.split("(")[-1].split(")")[0])

                # Detect available columns
                api60_col = _first_present(cols, "api_at60", "api60", "api_60", "api_at_60f", "api_60f")
                temp_c_col = _first_present(cols, "tank_temp_c", "tank_temperature_c", "tank_temp_celsius")
                temp_f_col = _first_present(cols, "tank_temp_f", "tank_temperature_f", "tank_temp_fahrenheit")
                op_text_col = _first_present(cols, "operation_text", "op_text", "operation_label")
                op_col = _first_present(cols, "operation")  # enum/string operation column if present

                # Build canonical payload
                time_val = tx_time if isinstance(tx_time, dt_time) else dt_time(hour=tx_time.hour, minute=tx_time.minute)
                payload = {
                    "location_id": loc.id,
                    "ticket_id": ticket_id,
                    "tank_id": tnk.id,
                    "tank_name": tnk.name,
                    "date": tx_date,
                    "time": time_val,

                    "dip_cm": float(dip_cm or 0.0),
                    "water_cm": float(water_cm or 0.0),

                    # observed inputs
                    "api_observed": float(api_obs_val or 0.0),
                    "density_observed": float(dens_obs_val or 0.0),
                    "api60": float(api60_val or 0.0),  # will remap to actual column
                    "vcf": float(vcf_val or 1.0),

                    # volumes
                    "tov_bbl": float(tov_bbl or 0.0),
                    "fw_bbl": float(fw_bbl or 0.0),
                    "gov_bbl": float(gov_bbl or 0.0),
                    "gsv_bbl": float(gsv_bbl or 0.0),
                    "bsw_pct": float(bsw_pct or 0.0),
                    "bsw_bbl": float((gsv_bbl - nsv_bbl) if gsv_bbl >= nsv_bbl else 0.0),
                    "qty_bbls": float(nsv_bbl or 0.0),   # NSV
                    "nsv_bbl": float(nsv_bbl or 0.0),    # provide both; only existing col will be kept
                    "mt": float(mt or 0.0),
                    "lt": float(lt or 0.0),

                    "remarks": (remarks.strip() or None),
                    "created_by": (user or {}).get("username", "system"),
                }

                # Map API@60 into the actual column (or drop if none)
                if api60_col:
                    payload[api60_col] = payload.pop("api60")
                else:
                    payload.pop("api60", None)

                # Handle OPERATION safely (enum-aware)
                selected_label = None if (selected_op_label or "").startswith("N/A") else (selected_op_label or "").strip()
                if selected_label:
                    if op_col:
                        mapped_value = _coerce_operation_value(TT, op_col, selected_label)
                        payload[op_col] = mapped_value
                        if op_text_col:
                            payload[op_text_col] = selected_label
                    elif op_text_col:
                        payload[op_text_col] = selected_label

                # Only pass keys that exist on the model
                safe_kwargs = {k: v for k, v in payload.items() if k in cols}

                # Create row
                tx = TT(**safe_kwargs)

                # Optionally store normalized temps if those columns exist
                try:
                    if temp_c_col and temp_f_col:
                        if st.session_state.get("tx_tank_temp_unit") == "°C":
                            setattr(tx, temp_c_col, float(tank_temp_val))
                            setattr(tx, temp_f_col, float(c_to_f(float(tank_temp_val))))
                        else:
                            setattr(tx, temp_f_col, float(tank_temp_val))
                            setattr(tx, temp_c_col, float(f_to_c(float(tank_temp_val))))
                    elif temp_c_col:
                        val_c = tank_temp_val if st.session_state.get("tx_tank_temp_unit") == "°C" else f_to_c(float(tank_temp_val))
                        setattr(tx, temp_c_col, float(val_c))
                    elif temp_f_col:
                        val_f = tank_temp_val if st.session_state.get("tx_tank_temp_unit") == "°F" else c_to_f(float(tank_temp_val))
                        setattr(tx, temp_f_col, float(val_f))
                except Exception:
                    pass

                session.add(tx)
                session.commit()

                # Audit with IP for CREATE
                try:
                    SecurityManager.log_audit(
                        None,
                        (user or {}).get("username", "system"),
                        "CREATE",
                        resource_type="TankTransaction",
                        resource_id=str(getattr(tx, "id", "")),
                        details=f"Created tank tx {ticket_id} ({selected_op_label}) for tank {tnk.name}; "
                                f"NSV {nsv_bbl:.2f} bbl, MT {mt:.3f}; ip={_get_client_ip()}",
                        user_id=(user or {}).get("id"),
                        location_id=loc.id,
                    )
                except Exception:
                    pass

                # Mirror non-condensate transactions into OTRRecord for OTR page
                try:
                    if selected_label and ("condensate" not in selected_label.lower()):
                        from models import OTRRecord
                        otr = OTRRecord(
                            location_id=loc.id,
                            ticket_id=ticket_id,
                            tank_id=str(tnk.id),
                            date=tx_date,
                            time=time_val,
                            operation=selected_label,
                            dip_cm=float(dip_cm or 0.0),
                            total_volume_bbl=float(tov_bbl or 0.0),
                            water_cm=float(water_cm or 0.0),
                            free_water_bbl=float(fw_bbl or 0.0),
                            gov_bbl=float(gov_bbl or 0.0),
                            api60=float(api60_val or 0.0),
                            vcf=float(vcf_val or 1.0),
                            gsv_bbl=float(gsv_bbl or 0.0),
                            bsw_vol_bbl=float((gsv_bbl - nsv_bbl) if gsv_bbl >= nsv_bbl else 0.0),
                            nsv_bbl=float(nsv_bbl or 0.0),
                            lt=float(lt or 0.0),
                            mt=float(mt or 0.0),
                        )
                        session.add(otr)
                        session.commit()
                        try:
                            SecurityManager.log_audit(
                                None,
                                (user or {}).get("username", "system"),
                                "CREATE",
                                resource_type="OTRRecord",
                                resource_id=str(getattr(otr, "id", "")),
                                details=f"Mirrored OTR for ticket {ticket_id} ({selected_op_label})",
                                user_id=(user or {}).get("id"),
                                location_id=loc.id,
                            )
                        except Exception:
                            pass
                except Exception:
                    pass

            st.success(f"Saved. Ticket ID: **{ticket_id}**  |  NSV: **{nsv_bbl:,.2f} bbl**  |  MT: **{mt:.3f}**  |  LT: **{lt:,.3f}**")
            st.rerun()
        except Exception as ex:
            st.error(f"Failed to save transaction: {ex}")



# ======================= TAB: Meter Records =======================
def _get_meter_model():
    import models as db_models
    for name in ("MeterTransaction", "MeterTransactions", "MeterTxn", "Meter_Record"):
        model = getattr(db_models, name, None)
        if model is not None:
            return model
    return None

def _fetch_meter_rows(session, location_id: int, limit: int = 1000):
    Mt = _get_meter_model()
    if Mt is None:
        return [], "MeterTransaction model not found in models.py."
    q = session.query(Mt).filter(getattr(Mt, "location_id") == location_id)
    try:
        q = q.order_by(getattr(Mt, "date").desc(), getattr(Mt, "id").desc())
    except Exception:
        pass
    rows = q.limit(limit).all()
    return rows, None

def _meter_row_to_dict(r):
    get = lambda *names, default=None: next((getattr(r, n) for n in names if hasattr(r, n)), default)
    om1 = float(get("opening_meter_reading", default=0.0) or 0.0)
    cm1 = float(get("closing_meter_reading", default=0.0) or 0.0)
    om2 = float(get("opening_meter2_reading", default=0.0) or 0.0)
    cm2 = float(get("closing_meter2_reading", default=0.0) or 0.0)
    net = get("net_qty", default=None)
    if net is None:
        net = (cm1 - om1) + (cm2 - om2)
    return {
        "ID": get("id"),
        "Date": get("date"),
        "Opening Meter 1": om1,
        "Closing Meter 1": cm1,
        "Opening Meter 2": om2,
        "Closing Meter 2": cm2,
        "Net Qty": net,
        "Remarks": get("remarks", default=""),
        "Created By": get("created_by", default=""),
        "Created At": get("created_at", default=None),
    }

def _render_tab_meter_records(loc, user):
    st.markdown("#### 🧮 Meter Records")

    try:
        with get_session() as s:
            meters_cfg = get_page_section_config(s, loc.id, page="tank_transactions", section="meters") or {}
    except Exception:
        meters_cfg = {}

    meters = [m for m in (meters_cfg.get("meters") or []) if m.get("active", True)]

    if not meters:
        _no_meters_message("meter(s)", user)
        return

    st.caption(
        "Enter readings for the configured meter(s). Net quantity is computed per meter and summed. "
        "If a meter’s unit is m³, its net is converted to bbls using 6.289811."
    )

    tx_date = st.date_input("📅 Date", value=date.today(), key=f"meter_txdate_{loc.id}")

    net_total_bbl = 0.0
    rows_payload = []

    for i, m in enumerate(meters):
        label = m.get("label") or f"Meter {i+1}"
        factor = float(m.get("factor") or 1.0)
        unit = (m.get("unit") or "bbls").lower()

        c1, c2, c3, c4, c5 = st.columns([0.26, 0.18, 0.18, 0.18, 0.20])
        with c1:
            st.caption(f"**{label}** ({'bbls' if unit=='bbls' else 'm³'})")
        with c2:
            open_v = st.number_input("Opening", value=0.0, step=0.001, format="%.3f", key=f"meter_open_{loc.id}_{i}")
        with c3:
            close_v = st.number_input("Closing", value=0.0, step=0.001, format="%.3f", key=f"meter_close_{loc.id}_{i}")
        with c4:
            factor_v = st.number_input("Factor", value=factor, step=0.0001, format="%.4f", key=f"meter_factor_{loc.id}_{i}")
        with c5:
            net_native = (float(close_v) - float(open_v)) * float(factor_v)
            net_bbl = net_native if unit == "bbls" else net_native * 6.289811
            net_total_bbl += net_bbl
            st.caption(f"Net: **{net_bbl:,.2f} bbl**")

        rows_payload.append({
            "label": label,
            "unit": unit,
            "opening": float(open_v or 0.0),
            "closing": float(close_v or 0.0),
            "factor": float(factor_v or factor),
            "net_bbl": float(net_bbl),
        })

    st.caption(f"📊 **Net Receipt/Dispatch (sum): {net_total_bbl:,.2f} bbl**")

    remarks = st.text_input("📝 Remarks", value="", max_chars=250, key=f"meter_remarks_{loc.id}")

    if st.button("💾 Save Meter Record", type="primary", key=f"meter_save_{loc.id}"):
        if net_total_bbl <= 0:
            st.error("Net total is zero or negative. Please check your inputs.")
            return

        payload = {
            "date": str(tx_date),
            "meters": rows_payload,
            "net_total_bbl": float(net_total_bbl),
            "remarks": (remarks.strip() or None),
        }

        try:
            from models import FlexibleRecord
            with get_session() as s:
                rec = FlexibleRecord(
                    location_id=loc.id,
                    page="tank_transactions",
                    section="meters",
                    tx_date=tx_date,
                    data_json=json.dumps(payload),
                    created_by=(user or {}).get("username", "system"),
                )
                s.add(rec)
                s.commit()

                try:
                    SecurityManager.log_audit(
                        s,
                        (user or {}).get("username", "system"),
                        "CREATE",
                        resource_type="TankTx:MeterRecord",
                        resource_id=str(getattr(rec, "id", "")),
                        details=f"Saved meter record; total {net_total_bbl:.2f} bbl",
                        user_id=(user or {}).get("id"),
                        location_id=loc.id,
                        ip_address=_get_client_ip(),
                        success=True,
                    )
                except Exception:
                    pass

            st.success("Meter record saved.")
            st.rerun()
        except Exception as ex:
            st.info("Generic model `FlexibleRecord` not found. Add it to models.py to persist this row.")
            st.error(f"(Developer hint) Save failed: {ex}")


# ======================= TAB: Condensate Records =======================
def _get_condensate_model():
    import models as db_models
    for name in ("CondensateRecord", "CondensateTransaction", "CondensateTxn", "Condensate_Log"):
        model = getattr(db_models, name, None)
        if model is not None:
            return model
    return None

def _fetch_cond_rows(session, location_id: int, limit: int = 1000):
    Mc = _get_condensate_model()
    if Mc is None:
        return [], "Condensate model not found in models.py."
    q = session.query(Mc).filter(getattr(Mc, "location_id") == location_id)
    try:
        q = q.order_by(getattr(Mc, "date").desc(), getattr(Mc, "id").desc())
    except Exception:
        pass
    return q.limit(limit).all(), None

def _render_tab_condensate(loc, user):
    st.markdown("#### 🧪 Condensate Records")

    try:
        with get_session() as s:
            meters_cfg = get_page_section_config(s, loc.id, page="tank_transactions", section="condensate_meters") or {}
    except Exception:
        meters_cfg = {}

    meters = [m for m in (meters_cfg.get("meters") or []) if m.get("active", True)]

    if not meters:
        _no_meters_message("condensate meter(s)", user)
        return

    st.caption(
        "Enter meter readings for condensate. Sum of meter nets gives **GOV (bbl)**, "
        "then sampling parameters compute **API@60 → VCF → GSV → BS&W → NSV → MT → LT**. "
        "If a meter’s unit is m³, net converts to bbls using 6.289811."
    )

    tx_date = st.date_input("📅 Date", value=date.today(), key=f"cond_txdate_{loc.id}")

    st.markdown("##### Meter Readings")
    GOV_total_bbl = 0.0
    per_meter_rows = []

    for i, m in enumerate(meters):
        mlabel = m.get("label") or f"Meter {i+1}"
        mfactor = float(m.get("factor") or 1.0)
        munit = (m.get("unit") or "bbls").lower()

        c1, c2, c3, c4, c5 = st.columns([0.25, 0.20, 0.20, 0.15, 0.20])
        with c1:
            st.caption(f"**{mlabel}**  ({'bbls' if munit=='bbls' else 'm³'})")
        with c2:
            open_val = st.number_input("Opening", value=0.0, step=0.001, format="%.3f", key=f"cond_open_{loc.id}_{i}")
        with c3:
            close_val = st.number_input("Closing", value=0.0, step=0.001, format="%.3f", key=f"cond_close_{loc.id}_{i}")
        with c4:
            factor_val = st.number_input("Factor", value=mfactor, step=0.0001, format="%.4f", key=f"cond_fac_{loc.id}_{i}")
        with c5:
            net_native = (float(close_val) - float(open_val)) * float(factor_val)
            net_bbl = net_native if munit == "bbls" else net_native * 6.289811
            GOV_total_bbl += net_bbl
            st.caption(f"Net: **{net_bbl:,.2f} bbl**")

        per_meter_rows.append({
            "label": mlabel,
            "unit": munit,
            "opening": float(open_val or 0.0),
            "closing": float(close_val or 0.0),
            "factor": float(factor_val or mfactor),
            "net_bbl": float(net_bbl),
        })

    st.caption(f"📊 **GOV (sum of meters): {GOV_total_bbl:,.2f} bbl**")
    st.markdown("---")

    st.caption("Observed Property & Sample Temperature")
    col_mode, col_sunit = st.columns([0.48, 0.52])
    with col_mode:
        obs_mode = st.selectbox("Input Type", ["Observed API", "Observed Density (kg/m3)"], index=0, key=f"cond_obs_mode_{loc.id}")
    with col_sunit:
        sample_unit = st.selectbox("Sample Temp Unit", ["°F", "°C"], index=0, key=f"cond_sunit_{loc.id}")

    slo, shi = temp_bounds(sample_unit)
    sample_temp_val = st.number_input("Sample Temperature", min_value=slo, max_value=shi, step=0.1, format="%.1f", key=f"cond_sample_temp_{loc.id}")

    api60_val = 0.0
    api_obs_val = 0.0
    dens_obs_val = 0.0

    if obs_mode == "Observed API":
        api_obs_val = st.number_input("Observed API *", min_value=10.0, max_value=100.0, step=0.1, format="%.1f", key=f"cond_api_obs_{loc.id}")
        api60_val = api60_from_api_obs(api_obs_val or 0.0, sample_temp_val or 0.0, sample_unit)
        dens_obs_val = density_from_api(api_obs_val or 0.0)
        st.caption(f"→ API @ 60°F: **{api60_val:.2f}**   |   ↔ Approx Density: **{dens_obs_val:.1f} kg/m³**")
    else:
        dens_obs_val = st.number_input("Observed Density (kg/m3) *", min_value=600.0, max_value=1100.0, step=0.1, format="%.1f", key=f"cond_density_obs_{loc.id}")
        api_obs_val = api_from_density(dens_obs_val) if dens_obs_val > 0 else 0.0
        api60_val = api60_from_density_obs(dens_obs_val or 0.0, sample_temp_val or 0.0, sample_unit)
        st.caption(f"↔ Observed API (approx): **{api_obs_val:.2f}**   |   → API @ 60°F: **{api60_val:.2f}**")

    st.caption("Tank Temperature & BS&W")
    tcol1, tcol2, tcol3 = st.columns([0.35, 0.35, 0.30])
    with tcol1:
        tank_temp_unit = st.selectbox("Tank Temp Unit", ["°C", "°F"], index=0, key=f"cond_tank_unit_{loc.id}")
    with tcol2:
        lo, hi = temp_bounds(tank_temp_unit)
        tank_temp_val = st.number_input(f"Tank Temperature ({tank_temp_unit})", min_value=lo, max_value=hi, step=0.1, format="%.1f", key=f"cond_tank_temp_{loc.id}")
    with tcol3:
        bsw_pct = st.number_input("BS&W (%)", min_value=0.0, max_value=100.0, step=0.01, key=f"cond_bsw_{loc.id}")

    vcf_val = vcf_from_api60_and_tank_temp(api60_val, tank_temp_val, tank_temp_unit)
    gsv_bbl = gsv_from_gov_vcf(GOV_total_bbl, vcf_val)
    bsw_bbl = bsw_volume_from_gsv_pct(gsv_bbl, float(bsw_pct or 0.0))
    nsv_bbl = nsv_from_gsv_bsw(gsv_bbl, bsw_bbl)
    mt_val = mass_mt_from_gsv_api60(gsv_bbl, api60_val)
    lt_val = mass_lt_from_mt(mt_val)

    st.caption(
        f"🧮 Computed — VCF: **{vcf_val:.5f}**  |  GSV: **{gsv_bbl:,.2f} bbl**  |  NSV: **{nsv_bbl:,.2f} bbl**  |  MT: **{mt_val:,.3f}**  |  LT: **{lt_val:,.3f}**"
    )

    remarks = st.text_input("📝 Remarks", value="", max_chars=250, key=f"cond_remarks_{loc.id}")

    if st.button("💾 Save Condensate Record", type="primary", key=f"cond_save_{loc.id}"):
        errs = []
        if GOV_total_bbl <= 0:
            errs.append("Net GOV from meters is zero or negative.")
        if api60_val <= 0:
            errs.append("Computed API @60°F is invalid. Check observed inputs.")
        if vcf_val <= 0:
            errs.append("Computed VCF is invalid. Check temperatures and API.")
        if errs:
            for e in errs:
                st.error(e)
            return

        payload = {
            "date": str(tx_date),
            "meters": per_meter_rows,
            "gov_bbl": float(GOV_total_bbl),
            "observed": {
                "mode": obs_mode,
                "api_obs": float(api_obs_val or 0.0),
                "density_obs": float(dens_obs_val or 0.0),
                "sample_temp": float(sample_temp_val or 0.0),
                "sample_temp_unit": sample_unit,
            },
            "tank_temp": {
                "value": float(tank_temp_val or 0.0),
                "unit": tank_temp_unit,
            },
            "api60": float(api60_val or 0.0),
            "vcf": float(vcf_val or 1.0),
            "gsv_bbl": float(gsv_bbl or 0.0),
            "bsw_pct": float(bsw_pct or 0.0),
            "bsw_bbl": float(bsw_bbl or 0.0),
            "nsv_bbl": float(nsv_bbl or 0.0),
            "mt": float(mt_val or 0.0),
            "lt": float(lt_val or 0.0),
            "remarks": (remarks.strip() or None),
        }

        try:
            from models import FlexibleRecord
            with get_session() as s:
                rec = FlexibleRecord(
                    location_id=loc.id,
                    page="tank_transactions",
                    section="condensate",
                    tx_date=tx_date,
                    data_json=json.dumps(payload),
                    created_by=(user or {}).get("username", "system"),
                )
                s.add(rec)
                s.commit()

                try:
                    SecurityManager.log_audit(
                        s,
                        (user or {}).get("username", "system"),
                        "CREATE",
                        resource_type="TankTx:Condensate",
                        resource_id=str(getattr(rec, "id", "")),
                        details=f"Saved condensate record: GOV {GOV_total_bbl:.2f} bbl; NSV {nsv_bbl:.2f} bbl",
                        user_id=(user or {}).get("id"),
                        location_id=loc.id,
                        ip_address=_get_client_ip(),
                        success=True,
                    )
                except Exception:
                    pass

            st.success("Condensate record saved.")
            st.rerun()
        except Exception as ex:
            st.info("Generic model `FlexibleRecord` not found. Add it to models.py to persist this row.")
            st.error(f"(Developer hint) Save failed: {ex}")


# ======================= Dynamic Forms (Produced Water / Production) =======================
def _evaluate_formula(formula: dict, row_data: dict) -> float:
    """
    Evaluate a formula based on row data.
    
    Formula structure:
    {
        "operation": "sum|subtract|multiply|divide|percentage|maximum|minimum|average",
        "columns": ["col1", "col2", ...]
    }
    
    Returns the calculated value or None if calculation fails.
    """
    if not formula or not isinstance(formula, dict):
        return None
    
    operation = formula.get("operation", "sum")
    columns = formula.get("columns", [])
    
    if not columns:
        return None
    
    # Extract numeric values from row data
    values = []
    for col_name in columns:
        val = row_data.get(col_name)
        if val is not None:
            try:
                values.append(float(val))
            except (ValueError, TypeError):
                pass  # Skip non-numeric values
    
    if not values:
        return None
    
    try:
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
            if len(values) < 2:
                return values[0] if values else None
            result = values[0]
            for v in values[1:]:
                if v == 0:
                    return None  # Avoid division by zero
                result /= v
            return result
        elif operation == "percentage":
            if len(values) < 2:
                return None
            if values[1] == 0:
                return None  # Avoid division by zero
            return (values[0] / values[1]) * 100
        elif operation == "maximum":
            return max(values)
        elif operation == "minimum":
            return min(values)
        elif operation == "average":
            return sum(values) / len(values)
        else:
            return None
    except Exception:
        return None


def _render_dynamic_form(loc, user, page_key: str, section_key: str, title: str):
    st.markdown(f"#### {title}")

    with get_session() as s:
        tdef = get_dynamic_table_def(s, loc.id, page=page_key, section=section_key)
    columns = list(tdef.get("columns") or [])

    if not columns:
        st.info(f"No table definition found. Please configure **{title}** in **Settings → Page Customization** first.")
        return

    date_fields = [c for c in columns if c.get("type") == "date"]
    date_name = date_fields[0]["name"] if date_fields else None
    
    # Separate columns into manual and calculated
    manual_columns = [c for c in columns if not c.get("formula")]
    calculated_columns = [c for c in columns if c.get("formula")]

    with st.form(key=f"dyn_form_{page_key}_{section_key}_{loc.id}"):
        row = {}
        
        # Render manual input columns
        for i, col in enumerate(manual_columns):
            ctype = col.get("type", "text")
            label = col.get("label") or col.get("name")
            name = col.get("name")
            if ctype == "date":
                row[name] = st.date_input(label, key=f"{page_key}_{section_key}_{loc.id}_date_{i}")
            elif ctype == "number":
                row[name] = st.number_input(label, step=0.01, format="%.2f", key=f"{page_key}_{section_key}_{loc.id}_num_{i}")
            else:
                row[name] = st.text_input(label, key=f"{page_key}_{section_key}_{loc.id}_txt_{i}")
        
        # Calculate and display calculated columns (read-only preview)
        if calculated_columns:
            st.markdown("##### 🧮 Calculated Columns (Auto-computed)")
            for calc_col in calculated_columns:
                formula = calc_col.get("formula")
                label = calc_col.get("label") or calc_col.get("name")
                name = calc_col.get("name")
                
                # Try to evaluate formula with current form data
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

    errs = []
    for col in columns:
        if col.get("required", False):
            nm = col["name"]
            val = row.get(nm)
            # Skip validation for calculated columns
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
    
    # Recalculate all formulas with final values before saving
    for calc_col in calculated_columns:
        formula = calc_col.get("formula")
        name = calc_col.get("name")
        calculated_value = _evaluate_formula(formula, row)
        row[name] = calculated_value

    tx_date = None
    if date_name and row.get(date_name):
        tx_date = row[date_name]

    try:
        from models import create_custom_tab_table, get_custom_table_model
        from logger import log_info, log_error, log_warning
        
        # Derive a deterministic table name per location and section
        table_name = f"flex_{section_key}_{loc.id}"
        log_info(f"Saving {section_key} data to table '{table_name}' for location_id={loc.id}, username={(user or {}).get('username', 'system')}")
        
        # Ensure table exists with current columns
        try:
            log_info(f"Attempting to create/verify table '{table_name}' with {len(columns)} columns")
            create_custom_tab_table(table_name, columns, loc.id)
            log_info(f"Table '{table_name}' is ready for use")
        except Exception as e:
            log_error(f"Failed to create table '{table_name}': {str(e)}", exc_info=True)
            st.error(f"❌ Database table '{table_name}' could not be created.")
            st.error(f"**Error details:** {str(e)}")
            st.warning("⚠️ Please check:")
            st.markdown("- Database connection is active")
            st.markdown("- User has CREATE TABLE permissions")
            st.markdown("- Database is not in read-only mode")
            st.markdown("- Column definitions are valid")
            st.info("💡 Check the logs folder for detailed error information.")
            return
            
        CustomModel = get_custom_table_model(table_name)
        if not CustomModel:
            log_error(f"Failed to get model for table '{table_name}' after successful creation")
            st.error(f"❌ Database table '{table_name}' exists but could not be loaded.")
            st.error("**Error details:** Model reflection failed after table creation.")
            st.info("💡 Check the logs folder for detailed error information.")
            return

        log_info(f"Successfully loaded model for table '{table_name}'. Proceeding to save data...")
        
        with get_session() as s:
            record_data = {
                "location_id": loc.id,
                "tx_date": tx_date,
                "created_by": (user or {}).get("username", "system"),
            }
            for col in columns:
                nm = col.get("name")
                if nm and nm in row:
                    record_data[nm] = row[nm]
            
            log_info(f"Inserting record into '{table_name}' with data: {record_data}")
            rec = CustomModel(**record_data)
            s.add(rec)
            s.commit()
            
            record_id = getattr(rec, "id", "unknown")
            log_info(f"✅ Successfully saved record {record_id} to table '{table_name}'")
            
            try:
                SecurityManager.log_audit(
                    s,
                    (user or {}).get("username", "system"),
                    "CREATE",
                    resource_type=f"{page_key}:{section_key}",
                    resource_id=str(record_id),
                    details=f"Saved to {table_name}: {row}",
                    user_id=(user or {}).get("id"),
                    location_id=loc.id,
                    ip_address=_get_client_ip(),
                    success=True,
                )
            except Exception as audit_ex:
                log_warning(f"Failed to log audit trail for {table_name}: {str(audit_ex)}")
                
        st.success("✅ Row saved successfully!")
        log_info(f"User notified of successful save to '{table_name}'")
        
    except Exception as ex:
        log_error(f"Unexpected error while saving {section_key} data to {table_name}: {str(ex)}", exc_info=True)
        st.error(f"❌ Save failed: {str(ex)}")
        st.info("💡 Check the logs folder for detailed error information.")

def _render_tab_produced_water(loc, user):
    _render_dynamic_form(loc, user, page_key="tank_transactions", section_key="produced_water", title="💧 Produced Water Records")

def _render_tab_production(loc, user):
    _render_dynamic_form(loc, user, page_key="tank_transactions", section_key="production", title="🏭 Production")


def _render_custom_tab(loc, user, tab_def: dict):
    """
    Render a custom tab with dynamic columns and save to custom table.
    
    Args:
        loc: Location object
        user: User dict
        tab_def: Tab definition with columns and table_name
    """
    import json
    from models import get_custom_table_model
    
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
    
    with st.form(key=f"custom_tab_form_{table_name}_{loc.id}"):
        row = {}
        
        # Render manual input columns
        for i, col in enumerate(manual_columns):
            ctype = col.get("type", "text")
            label = col.get("label") or col.get("name")
            name = col.get("name")
            
            if ctype == "date":
                row[name] = st.date_input(label, key=f"custom_{table_name}_{loc.id}_date_{i}")
            elif ctype == "number":
                row[name] = st.number_input(label, step=0.01, format="%.2f", key=f"custom_{table_name}_{loc.id}_num_{i}")
            else:
                row[name] = st.text_input(label, key=f"custom_{table_name}_{loc.id}_txt_{i}")
        
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
                    SecurityManager.log_audit(
                        s, (user or {}).get("username", "system"),
                        "CREATE",
                        resource_type=f"CustomTab:{tab_name}",
                        resource_id=str(getattr(record, "id", "")),
                        details=f"Custom tab row saved: {row}",
                        user_id=(user or {}).get("id"),
                        location_id=loc.id,
                        ip_address=_get_client_ip(),
                        success=True
                    )
                except Exception:
                    pass
                
                st.success(f"Row saved to {tab_name}.")
        else:
            st.error(f"Database table `{table_name}` not found. Please contact administrator.")
    except Exception as ex:
        st.error(f"Failed to save: {ex}")


# ======================= page entry =======================
def render_tank_transactions_page(active_location_id, user):
    st.markdown("### 🛢️ Tank Transactions")

    loc, loc_label = _guard_location(active_location_id)
    if not loc:
        return
    if not _guard_permissions(user, active_location_id):
        return

    st.caption(f"Active Location: **{loc_label}**")

    tab_cfg = {
        "Tank Entry": True,
        "Meter Records": True,
        "Condensate Records": True,
        "Produced Water Records": True,
        "Production": False,
    }
    if get_tank_transactions_tab_visibility:
        try:
            with get_session() as session:
                tab_cfg = get_tank_transactions_tab_visibility(session, loc.id)
        except Exception:
            pass

    tab_defs = [
        ("Tank Entry", _render_tab_tank_entry),
        ("Meter Records", _render_tab_meter_records),
        ("Condensate Records", _render_tab_condensate),
        ("Produced Water Records", _render_tab_produced_water),
        ("Production", _render_tab_production),
    ]
    
    # Load custom tabs
    from location_config import get_custom_tabs
    try:
        with get_session() as s:
            custom_tabs = get_custom_tabs(s, loc.id, "tank_transactions")
        
        for custom_tab in custom_tabs:
            if custom_tab.get("active", True):
                tab_label = custom_tab.get("name", "Custom")
                # Create a closure to capture the custom_tab definition
                def make_custom_renderer(tab_def):
                    return lambda loc, user: _render_custom_tab(loc, user, tab_def)
                
                tab_defs.append((tab_label, make_custom_renderer(custom_tab)))
                tab_cfg[tab_label] = True  # Enable custom tabs by default
    except Exception:
        pass  # If custom tabs fail to load, continue with standard tabs
    
    enabled = [(label, fn) for (label, fn) in tab_defs if tab_cfg.get(label, False)]

    if not enabled:
        st.info("No Tank Transactions tabs are enabled for this location. Ask an admin to enable them in **Location Settings → Tank Transactions (Tabs)**.")
        return

    labels = [lbl for lbl, _ in enabled]
    renderers = [fn for _, fn in enabled]

    tabs = st.tabs(labels)
    for t, render_fn, label in zip(tabs, renderers, labels):
        with t:
            if label == "Tank Entry":
                render_fn(loc, loc_label, user)
            else:
                render_fn(loc, user)

    st.caption("To **view saved transactions**, use **🗂️ View Tank Transactions** from the sidebar.")
