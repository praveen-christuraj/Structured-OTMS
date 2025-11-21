# app_pages/tank_transactions.py
import streamlit as st
from datetime import datetime, date, time as dt_time

from db import get_session
from models import Location, Tank, TankTransaction, Operation, CalibrationTank
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
from location_config import get_location_meters
from location_config import get_page_section_config  # for dynamic condensate config
from typing import Optional
from location_config import get_page_section_config

# Optional helpers
try:
    from permission_manager import PermissionManager
except Exception:
    PermissionManager = None

try:
    from location_config import get_location_page_visibility, get_tank_transactions_tab_visibility
except Exception:
    get_location_page_visibility = None
    get_tank_transactions_tab_visibility = None

# ---- Compatibility shims so old calls keep working ----
from utils_calc import (
    api_observed_to_api60, density_obs_to_api60,
    c_to_f, f_to_c, normalize_temp_unit
)

def api60_from_api_obs(api_obs: float, sample_temp: float, sample_unit: str) -> float:
    unit = normalize_temp_unit(sample_unit)
    temp_f = float(sample_temp or 0.0) if unit == "F" else c_to_f(float(sample_temp or 0.0))
    return api_observed_to_api60(float(api_obs or 0.0), temp_f)

def api60_from_density_obs(density_obs: float, sample_temp: float, sample_unit: str) -> float:
    unit = normalize_temp_unit(sample_unit)
    temp_c = float(sample_temp or 0.0) if unit == "C" else f_to_c(float(sample_temp or 0.0))
    api60, _ = density_obs_to_api60(float(density_obs or 0.0), temp_c)
    return api60


# -------- small utils --------
def _get_client_ip() -> str:
    """Return client IP if captured somewhere (e.g., via a small JS snippet into session_state)."""
    return str(st.session_state.get("client_ip") or "N/A")


# -------- guards / loaders --------
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

def _get_operation_choices():
    choices = []
    for op in Operation:
        choices.append((op.value, op))
    return choices

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

def _get_client_ip() -> str:
    return str(st.session_state.get("client_ip", "unknown"))


def _get_condensate_model():
    import models as db_models
    for name in ("CondensateTransaction", "CondensateRecord", "CondensateLog"):
        m = getattr(db_models, name, None)
        if m is not None:
            return m
    return None

def _get_produced_water_model():
    import models as db_models
    for name in ("ProducedWaterRecord", "ProducedWaterTransaction", "ProducedWaterLog"):
        m = getattr(db_models, name, None)
        if m is not None:
            return m
    return None

def _get_production_model():
    import models as db_models
    for name in ("ProductionRecord", "DailyProduction", "ProductionLog"):
        m = getattr(db_models, name, None)
        if m is not None:
            return m
    return None

# -------- calibration interpolation --------
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


# -------- TAB: Tank Entry (kept as you provided) --------
def _render_tab_tank_entry(loc, loc_label, user):
    st.markdown("#### 📝 Tank Entry")

    with get_session() as session:
        tanks = _load_tanks(session, loc.id)
    tank_labels = [f"{t.name}" for t in tanks]
    tank_by_label = {lbl: t for lbl, t in zip(tank_labels, tanks)}

    op_choices = _get_operation_choices()
    op_labels = [lbl for lbl, _ in op_choices]
    op_map = {lbl: op for lbl, op in op_choices}

    if not tanks:
        st.info("No tanks found for this location. Please add tanks in **Asset Management → Tanks**.")
        return

    # --- Inputs (live) ---
    c1, c2, c3 = st.columns(3)
    with c1:
        tx_date = st.date_input("📅 Date", value=date.today(), key="tx_date")
    with c2:
        now = datetime.now().time().replace(microsecond=0)
        tx_time = st.time_input("⏰ Time", value=now, key="tx_time")
    with c3:
        selected_tank_label = st.selectbox("🛢️ Tank", tank_labels, key="tx_tank_sel")

    c4, c5, c6 = st.columns(3)
    with c4:
        default_idx = max(0, op_labels.index("Receipt") if "Receipt" in op_labels else 0)
        selected_op_label = st.selectbox("🔁 Operation", op_labels, index=default_idx, key="tx_op")
    with c5:
        dip_cm = st.number_input("📏 Dip (cm) *", min_value=0.0, step=0.1, format="%.1f", key="tx_dip")
    with c6:
        water_cm = st.number_input("💧 Water Level (cm) *", min_value=0.0, step=0.1, format="%.1f", key="tx_water")

    with get_session() as _s:
        tnk_id = tank_by_label[selected_tank_label].id if selected_tank_label in tank_by_label else None
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
                tnk = tank_by_label[selected_tank_label]
                ticket_id = _generate_ticket_id(session, loc_label.split("(")[-1].split(")")[0])

                tx = TankTransaction(
                    location_id=loc.id,
                    ticket_id=ticket_id,
                    operation=op_map.get(selected_op_label),
                    tank_id=tnk.id,
                    tank_name=tnk.name,
                    date=tx_date,
                    time=tx_time if isinstance(tx_time, dt_time) else dt_time(hour=tx_time.hour, minute=tx_time.minute),

                    dip_cm=float(dip_cm or 0.0),
                    water_cm=float(water_cm or 0.0),

                    tank_temp_c=None,
                    tank_temp_f=None,

                    api_observed=float(api_obs_val or 0.0),
                    density_observed=float(dens_obs_val or 0.0),
                    api_at60=float(api60_val or 0.0),
                    vcf=float(vcf_val or 1.0),

                    tov_bbl=float(tov_bbl or 0.0),
                    fw_bbl=float(fw_bbl or 0.0),
                    gov_bbl=float(gov_bbl or 0.0),
                    gsv_bbl=float(gsv_bbl or 0.0),
                    bsw_pct=float(bsw_pct or 0.0),
                    bsw_bbl=float((gsv_bbl - nsv_bbl) if gsv_bbl >= nsv_bbl else 0.0),
                    qty_bbls=float(nsv_bbl or 0.0),   # NSV as stored qty
                    mt=float(mt or 0.0),
                    lt=float(lt or 0.0),

                    remarks=(remarks.strip() or None),
                    created_by=(user or {}).get("username", "system"),
                )
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

            st.success(f"Saved. Ticket ID: **{ticket_id}**  |  NSV: **{nsv_bbl:,.2f} bbl**  |  MT: **{mt:,.3f}**  |  LT: **{lt:,.3f}**")
            st.rerun()
        except Exception as ex:
            st.error(f"Failed to save transaction: {ex}")


# -------- METER RECORDS helpers --------
def _get_meter_model():
    """
    Resolve the meter ORM class by common names.
    Adjust if your class name differs.
    """
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

# -------- CONDENSATE & PRODUCED WATER helpers --------
def _get_condensate_model():
    import models as db_models
    for name in ("CondensateRecord", "CondensateTransaction", "CondensateTxn", "Condensate_Log"):
        model = getattr(db_models, name, None)
        if model is not None:
            return model
    return None

def _get_pw_model():
    import models as db_models
    for name in ("ProducedWaterRecord", "ProducedWaterTransaction", "ProducedWaterTxn", "PW_Record"):
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

def _fetch_pw_rows(session, location_id: int, limit: int = 1000):
    Pw = _get_pw_model()
    if Pw is None:
        return [], "ProducedWater model not found in models.py."
    q = session.query(Pw).filter(getattr(Pw, "location_id") == location_id)
    try:
        q = q.order_by(getattr(Pw, "date").desc(), getattr(Pw, "id").desc())
    except Exception:
        pass
    return q.limit(limit).all(), None

def _cond_row_to_dict(r):
    get = lambda *names, default=None: next((getattr(r, n) for n in names if hasattr(r, n)), default)
    om = float(get("opening_reading", "opening_meter", default=0.0) or 0.0)
    cm = float(get("closing_reading", "closing_meter", default=0.0) or 0.0)
    net = get("net_qty", default=None)
    if net is None:
        net = cm - om
    return {
        "ID": get("id"),
        "Date": get("date"),
        "Opening": om,
        "Closing": cm,
        "Net Qty": net,
        "Remarks": get("remarks", default=""),
        "Created By": get("created_by", default=""),
        "Created At": get("created_at", default=None),
    }

def _pw_row_to_dict(r):
    get = lambda *names, default=None: next((getattr(r, n) for n in names if hasattr(r, n)), default)
    om = float(get("opening_reading", "opening_meter", default=0.0) or 0.0)
    cm = float(get("closing_reading", "closing_meter", default=0.0) or 0.0)
    net = get("net_qty", default=None)
    if net is None:
        net = cm - om
    return {
        "ID": get("id"),
        "Date": get("date"),
        "Opening": om,
        "Closing": cm,
        "Net Qty": net,
        "Remarks": get("remarks", default=""),
        "Created By": get("created_by", default=""),
        "Created At": get("created_at", default=None),
    }


# -------- TAB: Meter Records (entry + list + edit/delete) --------
def _render_tab_meter_records(loc, user):
    st.markdown("#### ⛽ Meter Records")

    # 1) Load meters assigned to this location
    with get_session() as s:
        meters = get_location_meters(s, loc.id)

    if not meters:
        st.info("No meters assigned to this location. Go to **Page Customization → Meters** and assign meters.")
        return

    # 2) Date + remarks
    c1, c2 = st.columns([1, 1])
    with c1:
        m_date = st.date_input("Date", value=st.session_state.get("m_date", date.today()), key="m_date")
    with c2:
        remarks = st.text_area("Remarks", value=st.session_state.get("m_remarks", ""), key="m_remarks", help="Optional notes.")

    st.markdown("**Readings**")
    totals = 0.0
    per_meter_nets = []
    # 3) Render a row for each meter
    for m in meters:
        oc1, oc2, oc3 = st.columns([0.4, 0.3, 0.3])
        with oc1:
            st.caption(f"🧪 {m.name} [{m.code}]")
        with oc2:
            om = st.number_input(f"Opening — {m.code}", value=0.0, step=0.01, format="%.2f", key=f"m_om_{m.id}")
        with oc3:
            cm = st.number_input(f"Closing — {m.code}", value=0.0, step=0.01, format="%.2f", key=f"m_cm_{m.id}")

        net = (cm - om)
        per_meter_nets.append((m.code, om, cm, net))
        st.caption(f"Net: **{net:,.2f}**")

        totals += net

    st.markdown("---")
    st.caption(f"**Total Net Quantity (live):** {totals:,.2f}")

    # 4) Save (stores total and details in remarks tail if model has no JSON column)
    save_clicked = st.button("💾 Save to DB", type="primary", use_container_width=True, key="m_save_btn")
    if save_clicked:
        try:
            # Resolve meter model dynamically (as before)
            Mt = _get_meter_model()
            if Mt is None:
                st.error("MeterTransaction model not found in models.py.")
                return

            # Build a compact details string (compatible with any existing schema)
            detail_parts = [f"{code}:{om:.2f}->{cm:.2f}({net:.2f})" for (code, om, cm, net) in per_meter_nets]
            tail = f" [details: {'; '.join(detail_parts)}]"
            remarks_final = (remarks or "") + tail

            with get_session() as s:
                row = Mt(
                    location_id=loc.id,
                    date=m_date,
                    net_qty=float(totals),
                    remarks=remarks_final.strip(),
                )
                # Best-effort: if your model has per-meter columns (legacy 1–2), we won’t fill them here
                # Optionally stamp audit fields
                try:
                    setattr(row, "created_by", (user or {}).get("username", "system"))
                    setattr(row, "created_at", datetime.utcnow())
                except Exception:
                    pass

                s.add(row)
                s.flush()
                rid = getattr(row, "id", None)
                s.commit()

                # Audit with IP
                try:
                    SecurityManager.log_audit(
                        None,
                        (user or {}).get("username", "system"),
                        "CREATE",
                        resource_type="MeterTransaction",
                        resource_id=str(rid or ""),
                        details=f"Created meter entry {m_date}; total_net={totals:.2f}; ip={_get_client_ip()}",
                        user_id=(user or {}).get("id"),
                        location_id=loc.id,
                    )
                except Exception:
                    pass

            st.success("✅ Meter entry saved.")
            st.rerun()
        except Exception as ex:
            st.error(f"Failed to save: {ex}")

# --- REPLACE your current _render_tab_condensate(...) with this ---
def _render_tab_condensate(loc, user):
    st.markdown("#### 🧪 Condensate Records")

    # Load dynamic config: number of streams + labels (from Page Customization)
    with get_session() as s:
        cfg = get_page_section_config(s, loc.id, page="tank_transactions", section="condensate")

    streams = int(cfg.get("streams", 1))
    labels = cfg.get("labels", [f"Stream {i+1}" for i in range(streams)])
    # Normalize labels length
    if len(labels) != streams:
        labels = [labels[i] if i < len(labels) else f"Stream {i+1}" for i in range(streams)]

    # Date + optional remarks
    c1, c2 = st.columns([1, 1])
    with c1:
        c_date = st.date_input("Date", value=st.session_state.get("c_date", date.today()), key="c_date")
    with c2:
        remarks = st.text_area("Remarks", value=st.session_state.get("c_remarks", ""), key="c_remarks")

    st.markdown("**Readings (per stream)**")
    total_net = 0.0
    details = []  # for compact tail in remarks

    # Render opening/closing for each configured stream
    for idx in range(streams):
        label = labels[idx]
        oc1, oc2, oc3, oc4 = st.columns([0.38, 0.20, 0.20, 0.22])
        with oc1:
            st.caption(f"🧷 {label}")
        with oc2:
            op = st.number_input(f"Opening — {label}", value=0.00, step=0.01, format="%.2f", key=f"cond_open_{idx}")
        with oc3:
            cl = st.number_input(f"Closing — {label}", value=0.00, step=0.01, format="%.2f", key=f"cond_close_{idx}")
        net = cl - op
        with oc4:
            st.caption(f"Net: **{net:,.2f}**")

        total_net += net
        details.append(f"{label}:{op:.2f}->{cl:.2f}({net:.2f})")

    st.markdown("---")
    st.caption(f"**Total Net (live):** {total_net:,.2f}")

    # Save to DB
    if st.button("💾 Save to DB", type="primary", use_container_width=True, key="cond_save_btn"):
        # Resolve model
        Cond = _get_condensate_model()
        if Cond is None:
            st.error("Condensate model not found (expected CondensateTransaction / CondensateRecord / CondensateLog).")
            return

        try:
            with get_session() as s:
                row = Cond(
                    location_id=loc.id,
                    date=c_date,
                    total_net=float(total_net),
                    remarks=((remarks or "") + f" [details: {'; '.join(details)}]").strip(),
                )
                # Best-effort audit columns if present on your model
                try:
                    setattr(row, "created_by", (user or {}).get("username", "system"))
                    setattr(row, "created_at", datetime.utcnow())
                except Exception:
                    pass

                s.add(row)
                s.flush()
                rec_id = getattr(row, "id", None)
                s.commit()

            # Audit
            try:
                SecurityManager.log_audit(
                    None,
                    (user or {}).get("username", "system"),
                    "CREATE",
                    resource_type="CondensateRecord",
                    resource_id=str(rec_id or ""),
                    details=f"Created condensate record {c_date}; total_net={total_net:.2f}; ip={_get_client_ip()}",
                    user_id=(user or {}).get("id"),
                    location_id=loc.id,
                )
            except Exception:
                pass

            st.success("✅ Condensate record saved.")
            st.rerun()
        except Exception as ex:
            st.error(f"Failed to save condensate record: {ex}")


def _render_tab_produced_water(loc, user):
    st.markdown("#### 💧 Produced Water Records")

    # Pull dynamic configuration for this location
    with get_session() as s:
        cfg = get_page_section_config(s, loc.id, page="tank_transactions", section="produced_water")

    streams = int(cfg.get("streams", 1))
    labels = cfg.get("labels", [f"Stream {i+1}" for i in range(streams)])
    if len(labels) != streams:
        labels = [labels[i] if i < len(labels) else f"Stream {i+1}" for i in range(streams)]

    # Date + remarks
    c1, c2 = st.columns([1, 1])
    with c1:
        p_date = st.date_input("Date", value=st.session_state.get("pw_date", date.today()), key="pw_date")
    with c2:
        remarks = st.text_area("Remarks", value=st.session_state.get("pw_remarks", ""), key="pw_remarks")

    st.markdown("**Readings (per stream)**")
    total_net = 0.0
    details = []

    for idx in range(streams):
        label = labels[idx]
        oc1, oc2, oc3, oc4 = st.columns([0.38, 0.20, 0.20, 0.22])
        with oc1:
            st.caption(f"🧷 {label}")
        with oc2:
            op = st.number_input(f"Opening — {label}", value=0.00, step=0.01, format="%.2f", key=f"pw_open_{idx}")
        with oc3:
            cl = st.number_input(f"Closing — {label}", value=0.00, step=0.01, format="%.2f", key=f"pw_close_{idx}")
        net = cl - op
        with oc4:
            st.caption(f"Net: **{net:,.2f}**")
        total_net += net
        details.append(f"{label}:{op:.2f}->{cl:.2f}({net:.2f})")

    st.markdown("---")
    st.caption(f"**Total Net (live):** {total_net:,.2f}")

    if st.button("💾 Save to DB", type="primary", use_container_width=True, key="pw_save_btn"):
        PW = _get_produced_water_model()
        if PW is None:
            st.error("Produced Water model not found (expected ProducedWaterRecord / ProducedWaterTransaction / ProducedWaterLog).")
            return
        try:
            with get_session() as s:
                row = PW(
                    location_id=loc.id,
                    date=p_date,
                    total_net=float(total_net),
                    remarks=((remarks or "") + f" [details: {'; '.join(details)}]").strip(),
                )
                try:
                    setattr(row, "created_by", (user or {}).get("username", "system"))
                    setattr(row, "created_at", datetime.utcnow())
                except Exception:
                    pass

                s.add(row)
                s.flush()
                rid = getattr(row, "id", None)
                s.commit()

            try:
                SecurityManager.log_audit(
                    None,
                    (user or {}).get("username", "system"),
                    "CREATE",
                    resource_type="ProducedWaterRecord",
                    resource_id=str(rid or ""),
                    details=f"Created PW {p_date}; total_net={total_net:.2f}; ip={_get_client_ip()}",
                    user_id=(user or {}).get("id"),
                    location_id=loc.id,
                )
            except Exception:
                pass

            st.success("✅ Produced water record saved.")
            st.rerun()
        except Exception as ex:
            st.error(f"Failed to save produced water record: {ex}")

def _render_tab_production(loc, user):
    st.markdown("#### 🏭 Production")

    # Pull dynamic configuration for production rows
    with get_session() as s:
        cfg = get_page_section_config(s, loc.id, page="tank_transactions", section="production")

    streams = int(cfg.get("streams", 1))
    labels = cfg.get("labels", [f"Item {i+1}" for i in range(streams)])
    if len(labels) != streams:
        labels = [labels[i] if i < len(labels) else f"Item {i+1}" for i in range(streams)]

    c1, c2 = st.columns([1, 1])
    with c1:
        d_prod = st.date_input("Date", value=st.session_state.get("prod_date", date.today()), key="prod_date")
    with c2:
        remarks = st.text_area("Remarks", value=st.session_state.get("prod_remarks", ""), key="prod_remarks")

    st.markdown("**Entries**")
    total_qty = 0.0
    details = []

    for idx in range(streams):
        label = labels[idx]
        cols = st.columns([0.55, 0.45])
        with cols[0]:
            st.caption(f"🔧 {label}")
        with cols[1]:
            qty = st.number_input(f"Quantity — {label} (bbl)", value=0.00, step=0.01, format="%.2f", key=f"prod_qty_{idx}")
        total_qty += qty
        details.append(f"{label}:{qty:.2f}")

    st.markdown("---")
    st.caption(f"**Total Production (live):** {total_qty:,.2f} bbl")

    if st.button("💾 Save to DB", type="primary", use_container_width=True, key="prod_save_btn"):
        Prod = _get_production_model()
        if Prod is None:
            st.error("Production model not found (expected ProductionRecord / DailyProduction / ProductionLog).")
            return
        try:
            with get_session() as s:
                row = Prod(
                    location_id=loc.id,
                    date=d_prod,
                    total_qty=float(total_qty),
                    remarks=((remarks or "") + f" [details: {'; '.join(details)}]").strip(),
                )
                try:
                    setattr(row, "created_by", (user or {}).get("username", "system"))
                    setattr(row, "created_at", datetime.utcnow())
                except Exception:
                    pass

                s.add(row)
                s.flush()
                rid = getattr(row, "id", None)
                s.commit()

            try:
                SecurityManager.log_audit(
                    None,
                    (user or {}).get("username", "system"),
                    "CREATE",
                    resource_type="ProductionRecord",
                    resource_id=str(rid or ""),
                    details=f"Created production {d_prod}; total={total_qty:.2f} bbl; ip={_get_client_ip()}",
                    user_id=(user or {}).get("id"),
                    location_id=loc.id,
                )
            except Exception:
                pass

            st.success("✅ Production entry saved.")
            st.rerun()
        except Exception as ex:
            st.error(f"Failed to save production entry: {ex}")

# -------- page entry --------
def render_tank_transactions_page(active_location_id, user):
    st.markdown("### 🛢️ Tank Transactions")

    loc, loc_label = _guard_location(active_location_id)
    if not loc:
        return
    if not _guard_permissions(user, active_location_id):
        return

    st.caption(f"Active Location: **{loc_label}**")

    # per-tab flags
    tab_cfg = {
        "Tank Entry": True,
        "Meter Records": True,            # enabled now
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
