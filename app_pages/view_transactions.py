# app_pages/view_transactions.py
from __future__ import annotations

import json, re
from datetime import date, datetime, timedelta, time as dt_time
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from db import get_session
from security import SecurityManager
from models import Location
try:
    from recycle_bin import RecycleBinManager
except Exception:
    RecycleBinManager = None

from yade_view import render_yade_transactions_view
from tanker_view import render_tanker_transactions_view
from deletion_approval import render_deletion_ui, DeletionApprovalManager

# Optional permissions
try:
    from permission_manager import PermissionManager
except Exception:
    PermissionManager = None

# Tank models
try:
    from models import TankTransaction, Tank, CalibrationTank
except Exception:
    TankTransaction, Tank, CalibrationTank = None, None, None

# Per-location tab flags (reuse entry-page toggles)
try:
    from location_config import get_tank_transactions_tab_visibility, get_active_operation_names
except Exception:
    get_tank_transactions_tab_visibility = None

    def get_active_operation_names(*args, **kwargs):
        return []


# ========================= shared utils =========================
def _audit_error(details: str, user: dict | None = None, location_id: int | None = None):
    try:
        SecurityManager.log_audit(
            None,
            (user or {}).get("username", "system"),
            "ERROR",
            resource_type="UI",
            resource_id="ViewTransactions",
            details=details[:900],
            user_id=(user or {}).get("id"),
            location_id=location_id,
            ip_address=str(st.session_state.get("client_ip") or "N/A"),
            success=False,
        )
    except Exception:
        pass


def _model_columns(model) -> set[str]:
    try:
        return {c.key for c in model.__table__.columns}
    except Exception:
        return set()


def _first_present(cols: set[str], *candidates: str) -> Optional[str]:
    for c in candidates:
        if c in cols:
            return c
    return None


def _nice_time(v: Any) -> str:
    if isinstance(v, dt_time):
        return v.strftime("%H:%M")
    if isinstance(v, str):
        if re.match(r"^\d{2}:\d{2}$", v.strip()):
            return v
        try:
            t = datetime.fromisoformat(v)
            return t.strftime("%H:%M")
        except Exception:
            return v
    return ""


def _nice_dt(v: Any) -> str:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M")
    if isinstance(v, str):
        try:
            t = datetime.fromisoformat(v)
            return t.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return v
    return ""


def _since(v: Any) -> Optional[timedelta]:
    if not v:
        return None
    if isinstance(v, datetime):
        return datetime.utcnow() - v
    if isinstance(v, str):
        try:
            t = datetime.fromisoformat(v)
            return datetime.utcnow() - t
        except Exception:
            return None
    return None


def _get_client_ip() -> str:
    return str(st.session_state.get("client_ip") or "N/A")


def _as_date(v: Any) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        try:
            # handle 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'
            return date.fromisoformat(v.split(" ")[0])
        except Exception:
            return None
    return None


# ------- small calibration helper (local to View page) -------
def _interp_vol_bbl(session, tank_id: int, dip_cm_val: float) -> float:
    """Linear interpolation on CalibrationTank(dip_cm -> volume_bbl)."""
    if not CalibrationTank or not tank_id:
        return 0.0
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
    if dip_cm_val <= xs[0]:
        return ys[0]
    if dip_cm_val >= xs[-1]:
        return ys[-1]
    import bisect

    i = bisect.bisect_left(xs, dip_cm_val)
    x0, x1 = xs[i - 1], xs[i]
    y0, y1 = ys[i - 1], ys[i]
    if x1 == x0:
        return y0
    return y0 + (y1 - y0) * ((dip_cm_val - x0) / (x1 - x0))


# ========================= guards =========================
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
        try:
            if not PermissionManager.can_access_operational_pages(user):
                st.error(f"Your role **{role}** cannot access operational pages.")
                return False
        except Exception as ex:
            _audit_error(f"Permission check failed: {ex}", user, active_location_id)
    return True


# ========================= CSS =========================
def _inject_css_once():
    if st.session_state.get("_vt_css_injected"):
        return
    st.session_state["_vt_css_injected"] = True
    st.markdown(
        """
        <style>
        .vt-compact * { font-size: 10.5px !important; line-height: 1.15 !important; }
        .ellip { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .kv-grid { display:grid; grid-template-columns: 0.35fr 0.65fr; gap:6px; }
        .kv { padding:2px 4px; }
        .vt-editline { background:#fcfcff; border:1px solid #e6e6ff; padding:8px; border-radius:6px; margin:6px 0; }
        .vt-mini-grid {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr 1fr 0.6fr;
            gap: 6px; align-items: center;
        }
        .vt-mini-header { font-weight:700; border-bottom:1px solid #ddd; padding:6px 2px; background:#fafafa; }
        .vt-mini-row { border-bottom:1px dashed #eee; padding:4px 2px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ========================= date bounds helpers =========================
def _get_tank_date_bounds(location_id: int) -> Tuple[date, date]:
    """Return (min_date, max_date) for TankTransaction at this location, clamped to today."""
    today = date.today()
    if not TankTransaction:
        return today, today
    try:
        from sqlalchemy import text

        table = TankTransaction.__table__
        cols = {c.key: c for c in table.columns}
        c_loc = _first_present(set(cols.keys()), "location_id", "locationId")
        c_date = _first_present(set(cols.keys()), "date", "tx_date")
        if not c_date:
            return today, today
        loc_col = cols[c_loc].name if c_loc else None
        date_col = cols[c_date].name

        sql = f"SELECT MIN({date_col}) AS dmin, MAX({date_col}) AS dmax FROM {table.name} WHERE 1=1"
        params = {}
        if loc_col:
            sql += f" AND {loc_col} = :loc_id"
            params["loc_id"] = location_id

        with get_session() as s:
            res = s.execute(text(sql), params).mappings().first()
        if not res or (res["dmin"] is None) or (res["dmax"] is None):
            return today, today

        d_min = _as_date(res["dmin"]) or today
        d_max = _as_date(res["dmax"]) or today
        if d_max > today:
            d_max = today
        if d_min > d_max:
            d_min = d_max
        return d_min, d_max
    except Exception:
        return today, today


def _get_flex_date_bounds(location_id: int, section: str) -> Tuple[date, date]:
    """Date bounds for FlexibleRecord(tx_date) per location/section."""
    from models import FlexibleRecord  # local import

    today = date.today()
    try:
        with get_session() as s:
            col = FlexibleRecord.tx_date
            q = s.query(col).filter(
                FlexibleRecord.location_id == location_id,
                FlexibleRecord.page == "tank_transactions",
                FlexibleRecord.section == section,
            )
            first = q.order_by(col.asc()).first()
            last = q.order_by(col.desc()).first()
            if not first or not last:
                return today, today
            d_min = _as_date(first[0]) or today
            d_max = _as_date(last[0]) or today
            if d_max > today:
                d_max = today
            if d_min > d_max:
                d_min = d_max
            return d_min, d_max
    except Exception:
        return today, today


# ========================= Filters (Tank) =========================
def _tank_filters_ui(location_id: int) -> dict:
    _inject_css_once()

    # Tanks
    tank_options: List[Tuple[str, Optional[int]]] = [("All Tanks", None)]
    if Tank:
        try:
            with get_session() as s:
                q = s.query(Tank).filter(Tank.location_id == location_id).order_by(Tank.name.asc())
                for t in q.all():
                    tank_options.append((f"{t.name}", t.id))
        except Exception as ex:
            _audit_error(f"Load tanks failed: {ex}", None, location_id)

    # Distinct Operations → LABELS ONLY (we'll filter in Python)
    op_labels: List[str] = ["All Operations"]
    if TankTransaction:
        try:
            from sqlalchemy import text

            table = TankTransaction.__table__
            cols = {c.key: c for c in table.columns}
            c_loc = _first_present(set(cols.keys()), "location_id", "locationId")
            c_op = _first_present(set(cols.keys()), "operation", "operation_text")
            if c_op:
                loc_col = cols[c_loc].name if c_loc else None
                op_col = cols[c_op].name
                sql = f"SELECT DISTINCT {op_col} AS op FROM {table.name} WHERE 1=1"
                params = {}
                if loc_col:
                    sql += f" AND {loc_col} = :loc_id"
                    params["loc_id"] = location_id
                with get_session() as s:
                    rows = s.execute(text(sql), params).mappings().all()
                labels_set = set()
                for r in rows:
                    val = r["op"]
                    if val is None:
                        continue
                    if isinstance(val, str):
                        label = val.replace("_", " ").title()
                    else:
                        label = str(val)
                    if label:
                        labels_set.add(label)
                op_labels.extend(sorted(labels_set))
        except Exception as ex:
            _audit_error(f"Load operations failed: {ex}", None, location_id)

    # Date bounds: from first entry date to last entry date, no future
    d_min, d_max = _get_tank_date_bounds(location_id)
    default_date = d_max

    # Single-row filters (DATE instead of range)
    c1, c2, c3, c4, c5 = st.columns([0.20, 0.20, 0.20, 0.20, 0.20], gap="small")
    with c1:
        d = st.date_input(
            "Date",
            value=default_date,
            min_value=d_min,
            max_value=d_max,
            key="vt_tank_date",
        )
        d1, d2 = d, d
    with c2:
        sel_asset = st.selectbox(
            "Asset (Tank)",
            tank_options,
            index=0,
            key="vt_tank_asset",
            format_func=lambda x: x[0] if isinstance(x, (list, tuple)) else str(x),
        )
        tank_id = sel_asset[1] if isinstance(sel_asset, (list, tuple)) and len(sel_asset) > 1 else None
    with c3:
        op_sel = st.selectbox("Operation", op_labels, index=0, key="vt_tank_op")
        op_label = None if op_sel == "All Operations" else op_sel
    with c4:
        ticket_id = (st.text_input("Ticket ID", key="vt_tank_ticket") or "").strip()
    with c5:
        created_by = (st.text_input("Created by", key="vt_tank_createdby") or "").strip()

    return {
        "d1": d1,
        "d2": d2,
        "tank_id": tank_id,
        "operation_label": op_label,  # label for Python-side filter
        "ticket": ticket_id,
        "created_by": created_by,
        "limit": 500,
    }


# ========================= Load Tank rows (TEXT query, bypass Enum) =========================
def _load_tank_rows(location_id: int, f: dict) -> List[Dict[str, Any]]:
    """
    Load TankTransaction rows via a raw SQL text query so that SQLAlchemy Enum
    conversion is bypassed. This prevents errors like:
    `'Receipt' is not among the defined enum values ...`
    """
    if not TankTransaction:
        return []

    from sqlalchemy import text

    try:
        table = TankTransaction.__table__
        cols = {c.key: c for c in table.columns}
        col_keys = set(cols.keys())

        def _col_name(key: Optional[str]) -> Optional[str]:
            if not key:
                return None
            c = cols.get(key)
            return c.name if c is not None else None

        c_loc = _first_present(col_keys, "location_id", "locationId")
        c_date = _first_present(col_keys, "date", "tx_date")
        c_time = _first_present(col_keys, "time", "tx_time")
        c_ticket = _first_present(col_keys, "ticket_id", "ticket", "ticketId")
        c_tank_id = _first_present(col_keys, "tank_id", "tankId")
        c_tank_name = _first_present(col_keys, "tank_name", "tankName")
        c_op = _first_present(col_keys, "operation", "operation_text")
        c_dip = _first_present(col_keys, "dip_cm", "dip")
        c_qty = _first_present(col_keys, "qty_bbls", "nsv_bbl", "nsv", "quantity_bbls")
        c_remarks = _first_present(col_keys, "remarks", "comment")
        c_by = _first_present(col_keys, "created_by", "createdBy", "user")
        c_at = _first_present(col_keys, "created_at", "createdAt", "created")
        c_uat = _first_present(col_keys, "updated_at", "updatedAt", "modified_at")
        c_uby = _first_present(col_keys, "updated_by", "edited_by", "modified_by")
        c_id = _first_present(col_keys, "id", "ID")

        loc_col = _col_name(c_loc)
        date_col = _col_name(c_date)
        time_col = _col_name(c_time)
        ticket_col = _col_name(c_ticket)
        tank_id_col = _col_name(c_tank_id)
        tank_name_col = _col_name(c_tank_name)
        op_col = _col_name(c_op)
        dip_col = _col_name(c_dip)
        qty_col = _col_name(c_qty)
        remarks_col = _col_name(c_remarks)
        by_col = _col_name(c_by)
        at_col = _col_name(c_at)
        uat_col = _col_name(c_uat)
        uby_col = _col_name(c_uby)
        id_col = _col_name(c_id)

        sql = f"SELECT * FROM {table.name} WHERE 1=1"
        params: Dict[str, Any] = {}

        if loc_col:
            sql += f" AND {loc_col} = :loc_id"
            params["loc_id"] = location_id

        d1 = f.get("d1")
        d2 = f.get("d2")
        if date_col and d1:
            sql += f" AND {date_col} >= :d1"
            params["d1"] = d1
        if date_col and d2:
            sql += f" AND {date_col} <= :d2"
            params["d2"] = d2

        if f.get("tank_id") and tank_id_col:
            sql += f" AND {tank_id_col} = :tank_id"
            params["tank_id"] = f["tank_id"]

        if f.get("ticket") and ticket_col:
            sql += f" AND {ticket_col} LIKE :ticket"
            params["ticket"] = f"%{f['ticket']}%"

        if f.get("created_by") and by_col:
            sql += f" AND {by_col} LIKE :created_by"
            params["created_by"] = f"%{f['created_by']}%"

        # Order by date and created_at if present
        order_clauses = []
        if date_col:
            order_clauses.append(f"{date_col} DESC")
        if at_col:
            order_clauses.append(f"{at_col} DESC")
        if order_clauses:
            sql += " ORDER BY " + ", ".join(order_clauses)

        with get_session() as s:
            res = s.execute(text(sql), params).mappings().all()

        out: List[Dict[str, Any]] = []
        for r in res:
            # row is a RowMapping; keys are DB column names
            def rv(name: Optional[str]):
                return r.get(name) if name in r else None

            ticket = rv(ticket_col)
            dval_raw = rv(date_col)
            dval = _as_date(dval_raw) or dval_raw
            tval = rv(time_col)
            tank_name = rv(tank_name_col) or rv(tank_id_col)

            op_val = rv(op_col)
            if isinstance(op_val, str):
                op_txt = op_val.replace("_", " ").title()
            else:
                op_txt = str(op_val) if op_val is not None else ""

            dip = rv(dip_col)
            qty = rv(qty_col)
            remarks = rv(remarks_col)
            cby = rv(by_col)
            cat = rv(at_col)

            edited_by = rv(uby_col)
            edited_at = rv(uat_col)
            edited = False
            try:
                if edited_at is not None and cat is not None:
                    edited = edited_at != cat
            except Exception:
                edited = False

            out.append(
                {
                    "_row": dict(r),  # store raw mapping as plain dict
                    "Ticket ID": ticket,
                    "Date": dval,
                    "Time": _nice_time(tval),
                    "Tank": tank_name,
                    "Operation": op_txt,
                    "Dip (cm)": dip,
                    "NSV (bbls)": qty,
                    "Remarks": remarks,
                    "Created By": cby,
                    "Created At": cat,
                    "_edited": edited,
                    "_edited_by": edited_by,
                    "_edited_at": edited_at,
                    "_id_col": id_col,
                    "_op_col": op_col,
                    "_tank_id_col": tank_id_col,
                    "_date_col": date_col,
                    "_time_col": time_col,
                    "_dip_col": dip_col,
                    "_water_col": _col_name(_first_present(col_keys, "water_cm", "water_level_cm")),
                    "_t_c_col": _col_name(
                        _first_present(col_keys, "tank_temp_c", "tank_temperature_c", "tank_temp_celsius")
                    ),
                    "_t_f_col": _col_name(
                        _first_present(col_keys, "tank_temp_f", "tank_temperature_f", "tank_temp_fahrenheit")
                    ),
                    "_api_obs_col": _col_name(_first_present(col_keys, "api_observed", "api_obs")),
                    "_dens_obs_col": _col_name(_first_present(col_keys, "density_observed", "density_obs")),
                    "_bsw_col": _col_name(_first_present(col_keys, "bsw_pct")),
                    "_api60_col": _col_name(
                        _first_present(col_keys, "api_at60", "api60", "api_60", "api_at_60f", "api_60f")
                    ),
                    "_vcf_col": _col_name(_first_present(col_keys, "vcf")),
                    "_tov_col": _col_name(_first_present(col_keys, "tov_bbl")),
                    "_fw_col": _col_name(_first_present(col_keys, "fw_bbl")),
                    "_gov_col": _col_name(_first_present(col_keys, "gov_bbl")),
                    "_gsv_col": _col_name(_first_present(col_keys, "gsv_bbl")),
                    "_qty_col": _col_name(_first_present(col_keys, "qty_bbls", "nsv_bbl")),
                    "_mt_col": _col_name(_first_present(col_keys, "mt")),
                    "_lt_col": _col_name(_first_present(col_keys, "lt")),
                    "_remarks_col": remarks_col,
                }
            )

        # Python-side operation filter using label
        op_label = f.get("operation_label")
        if op_label:
            op_label_l = op_label.lower()
            out = [row for row in out if str(row.get("Operation") or "").lower() == op_label_l]

        return out
    except Exception as ex:
        _audit_error(f"Load tank rows failed: {ex}")
        st.error(f"Failed to load tank transactions. (Logged: {ex})")
        return []


# ========================= Inline VIEW (read-only) & EDITOR =========================
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _inline_tank_viewer(idx: int, row: Dict[str, Any], user: dict | None, location_id: int):
    """Read-only compact detail of the main entry fields."""
    data = row["_row"]  # plain dict from text query

    def gv(*cands):
        for c in cands:
            if c in data:
                return data[c]
        return None

    ticket = gv("ticket_id", "ticket", "ticketId") or ""
    v_date = _as_date(gv("date", "tx_date")) or gv("date", "tx_date") or ""
    v_time = _nice_time(gv("time", "tx_time"))
    tank_name = gv("tank_name", "tankName") or row.get("Tank", "")
    op_val = gv("operation", "operation_text")
    if isinstance(op_val, str):
        op_txt = op_val.replace("_", " ").title()
    else:
        op_txt = str(op_val) if op_val is not None else ""

    def _fmt(x, fmt=",.2f"):
        try:
            return format(float(x), fmt)
        except Exception:
            return x if x is not None else ""

    dip = _fmt(gv("dip_cm", "dip"), ".1f")
    water = _fmt(gv("water_cm", "water_level_cm"), ".1f")
    temp_c = gv("tank_temp_c", "tank_temperature_c", "tank_temp_celsius")
    temp_f = gv("tank_temp_f", "tank_temperature_f", "tank_temp_fahrenheit")
    if isinstance(temp_c, (int, float)) and temp_c != 0:
        tdisp = f"{float(temp_c):.1f} °C"
    elif isinstance(temp_f, (int, float)) and temp_f != 0:
        tdisp = f"{float(temp_f):.1f} °F"
    else:
        tdisp = ""
    api_obs = _fmt(gv("api_observed", "api_obs"), ".2f")
    dens_obs = _fmt(gv("density_observed", "density_obs"), ".1f")
    bsw = _fmt(gv("bsw_pct"), ".2f")
    remarks = gv("remarks", "comment") or ""
    gov = _fmt(gv("gov_bbl"), ",.2f")
    gsv = _fmt(gv("gsv_bbl"), ",.2f")
    nsv = _fmt(gv("qty_bbls", "nsv_bbl"), ",.2f")
    created_at = gv("created_at", "createdAt", "created")

    with st.container():
        st.markdown('<div class="vt-editline vt-compact">', unsafe_allow_html=True)

        # Top row: Close + ticket
        c1, c2 = st.columns([0.06, 0.94])
        with c1:
            if st.button("✖️", key=f"vt_tank_view_close_{idx}", help="Close"):
                st.session_state[f"vt_tank_view_open_{idx}"] = False
                st.rerun()
        with c2:
            st.caption(f"Ticket: **{ticket}**")

        # Single-row compact summary (multiple columns)
        cols_row1 = st.columns([0.14, 0.10, 0.16, 0.18, 0.10, 0.10, 0.10, 0.12])
        with cols_row1[0]:
            st.markdown("**Date**")
            st.markdown(f"{v_date}")
        with cols_row1[1]:
            st.markdown("**Time**")
            st.markdown(f"{v_time}")
        with cols_row1[2]:
            st.markdown("**Tank**")
            st.markdown(f"{tank_name}")
        with cols_row1[3]:
            st.markdown("**Operation**")
            st.markdown(f"{op_txt}")
        with cols_row1[4]:
            st.markdown("**Dip (cm)**")
            st.markdown(f"{dip}")
        with cols_row1[5]:
            st.markdown("**Water (cm)**")
            st.markdown(f"{water}")
        with cols_row1[6]:
            st.markdown("**Tank Temp**")
            st.markdown(f"{tdisp}")
        with cols_row1[7]:
            st.markdown("**BS&W (%)**")
            st.markdown(f"{bsw}")

        cols_row2 = st.columns([0.14, 0.14, 0.14, 0.14, 0.14, 0.16])
        with cols_row2[0]:
            st.markdown("**Observed API**")
            st.markdown(f"{api_obs}")
        with cols_row2[1]:
            st.markdown("**Obs Density**")
            st.markdown(f"{dens_obs}")
        with cols_row2[2]:
            st.markdown("**GOV (bbl)**")
            st.markdown(f"{gov}")
        with cols_row2[3]:
            st.markdown("**GSV (bbl)**")
            st.markdown(f"{gsv}")
        with cols_row2[4]:
            st.markdown("**NSV (bbl)**")
            st.markdown(f"{nsv}")
        with cols_row2[5]:
            st.markdown("**Created At**")
            st.markdown(f"{_nice_dt(created_at)}")

        # Remarks full-width
        st.markdown("---")
        st.markdown("**Remarks**")
        st.markdown(remarks or "—")

        st.markdown("</div>", unsafe_allow_html=True)


def _inline_tank_editor(idx: int, row: Dict[str, Any], user: dict | None, location_id: int):
    """
    Full-detail editor (calculation logic like Tank Entry) operating on raw dict row
    and updating via text SQL to avoid Enum conversion issues.
    """
    data = row["_row"]  # plain dict from text query

    def gv(*cands):
        for c in cands:
            if c in data:
                return data[c]
        return None

    id_col = row.get("_id_col") or "id"
    rec_id = data.get(id_col, data.get("id"))

    if rec_id is None:
        st.error("Cannot edit: record id not found.")
        return

    # created_at for edit lock
    created_at = gv("created_at", "createdAt", "created")
    allow_edit = True
    diff = _since(created_at)
    if diff and diff > timedelta(hours=24):
        allow_edit = False

    # current values
    v_date = _as_date(gv("date", "tx_date")) or date.today()
    v_time = _nice_time(gv("time", "tx_time")) or datetime.now().strftime("%H:%M")
    tank_name = gv("tank_name", "tankName") or row.get("Tank", "")
    tank_id_val = gv("tank_id", "tankId")

    op_val = gv("operation", "operation_text")
    if isinstance(op_val, str):
        v_op_text = op_val.replace("_", " ").title()
    else:
        v_op_text = str(op_val) if op_val is not None else ""

    v_dip = float(gv("dip_cm", "dip") or 0.0)
    v_water = float(gv("water_cm", "water_level_cm") or 0.0)
    temp_c = gv("tank_temp_c", "tank_temperature_c", "tank_temp_celsius")
    temp_f = gv("tank_temp_f", "tank_temperature_f", "tank_temp_fahrenheit")
    temp_c = float(temp_c or 0.0) if temp_c is not None else None
    temp_f = float(temp_f or 0.0) if temp_f is not None else None
    if temp_c not in (None, 0):
        v_temp_val, v_temp_unit = temp_c, "°C"
    elif temp_f not in (None, 0):
        v_temp_val, v_temp_unit = temp_f, "°F"
    else:
        v_temp_val, v_temp_unit = 0.0, "°C"
    v_bsw = float(gv("bsw_pct") or 0.0)
    v_api_obs = float(gv("api_observed", "api_obs") or 0.0)
    v_dens_obs = float(gv("density_observed", "density_obs") or 0.0)
    v_remarks = gv("remarks", "comment") or ""

    # operation dropdown
    try:
        with get_session() as s:
            op_choices = get_active_operation_names(s, location_id, asset="tank") or []
    except Exception:
        op_choices = []
    if not op_choices:
        op_choices = [v_op_text] if v_op_text else ["N/A (configure in Location Settings)"]
    try:
        op_index = op_choices.index(v_op_text)
    except ValueError:
        op_index = 0

    # calculators
    from utils_calc import (
        temp_bounds,
        c_to_f,
        f_to_c,
        api60_from_api_obs,
        api60_from_density_obs,
        density_from_api,
        vcf_from_api60_and_tank_temp,
        gsv_from_gov_vcf,
        bsw_volume_from_gsv_pct,
        nsv_from_gsv_bsw,
        mass_mt_from_gsv_api60,
        mass_lt_from_mt,
    )

    with st.container():
        st.markdown('<div class="vt-editline vt-compact">', unsafe_allow_html=True)

        # compact icon-only action bar, single row
        b1, b2, b3, _ = st.columns([0.05, 0.05, 0.05, 0.85])
        save_clicked = st.button("💾", key=f"vt_tank_sv_{idx}", disabled=not allow_edit, help="Save changes")
        cancel_clicked = st.button("↩️", key=f"vt_tank_cx_{idx}", help="Cancel edit")
        close_clicked = st.button("✖️", key=f"vt_tank_cl_{idx}", help="Close")

        # row 1
        r1c1, r1c2, r1c3, r1c4 = st.columns([0.16, 0.14, 0.30, 0.40], gap="small")
        with r1c1:
            e_date = st.date_input("Date", value=v_date, key=f"vt_tank_edit_date_{idx}", disabled=not allow_edit)
        with r1c2:
            e_time = st.text_input("Time (HH:MM)", value=v_time, key=f"vt_tank_edit_time_{idx}", disabled=not allow_edit)
        with r1c3:
            st.text_input("Tank", value=tank_name or "", key=f"vt_tank_edit_tname_{idx}", disabled=True)
        with r1c4:
            e_op = st.selectbox("Operation", op_choices, index=op_index, key=f"vt_tank_edit_op_{idx}", disabled=not allow_edit)

        # row 2
        r2c1, r2c2, r2c3, r2c4 = st.columns([0.18, 0.18, 0.36, 0.28], gap="small")
        with r2c1:
            e_dip = st.number_input(
                "Dip (cm)",
                min_value=0.0,
                step=0.1,
                format="%.1f",
                value=float(v_dip),
                key=f"vt_tank_edit_dip_{idx}",
                disabled=not allow_edit,
            )
        with r2c2:
            e_water = st.number_input(
                "Water (cm)",
                min_value=0.0,
                step=0.1,
                format="%.1f",
                value=float(v_water),
                key=f"vt_tank_edit_water_{idx}",
                disabled=not allow_edit,
            )
        with r2c3:
            cA, cB = st.columns([0.45, 0.55])
            with cA:
                e_tunit = st.selectbox(
                    "Tank Temp Unit",
                    ["°C", "°F"],
                    index=(0 if v_temp_unit == "°C" else 1),
                    key=f"vt_tank_edit_tunit_{idx}",
                    disabled=not allow_edit,
                )
            with cB:
                lo, hi = temp_bounds(e_tunit)
                e_tval = st.number_input(
                    f"Temperature ({e_tunit})",
                    min_value=lo,
                    max_value=hi,
                    step=0.1,
                    format="%.1f",
                    value=float(v_temp_val),
                    key=f"vt_tank_edit_tval_{idx}",
                    disabled=not allow_edit,
                )
        with r2c4:
            e_bsw = st.number_input(
                "BS&W (%)",
                min_value=0.0,
                max_value=100.0,
                step=0.01,
                value=float(v_bsw),
                key=f"vt_tank_edit_bsw_{idx}",
                disabled=not allow_edit,
            )

        # row 3: observed mode
        mode_index = 0 if (v_api_obs and v_api_obs > 0) else 1
        r3c1, r3c2, r3c3 = st.columns([0.24, 0.38, 0.38], gap="small")
        with r3c1:
            obs_mode = st.selectbox(
                "Observed Type",
                ["Observed API", "Observed Density (kg/m3)"],
                index=mode_index,
                key=f"vt_tank_edit_obsmode_{idx}",
                disabled=not allow_edit,
            )
        with r3c2:
            if obs_mode == "Observed API":
                e_api = st.number_input(
                    "Observed API *",
                    min_value=10.0,
                    max_value=100.0,
                    step=0.1,
                    value=float(v_api_obs or 0.0),
                    key=f"vt_tank_edit_api_{idx}",
                    disabled=not allow_edit,
                )
                e_density = 0.0
            else:
                e_density = st.number_input(
                    "Observed Density (kg/m3) *",
                    min_value=600.0,
                    max_value=1100.0,
                    step=0.1,
                    value=float(v_dens_obs or 0.0),
                    key=f"vt_tank_edit_density_{idx}",
                    disabled=not allow_edit,
                )
                e_api = 0.0
        with r3c3:
            sA, sB = st.columns([0.45, 0.55])
            with sA:
                s_unit = st.selectbox(
                    "Sample Temp Unit",
                    ["°F", "°C"],
                    index=0,
                    key=f"vt_tank_edit_sunit_{idx}",
                    disabled=not allow_edit,
                )
            with sB:
                from utils_calc import temp_bounds as _tb

                s_lo, s_hi = _tb(s_unit)
                s_temp = st.number_input(
                    "Sample Temp",
                    min_value=s_lo,
                    max_value=s_hi,
                    step=0.1,
                    format="%.1f",
                    value=float(60.0 if s_unit == "°F" else 15.56),
                    key=f"vt_tank_edit_stemp_{idx}",
                    disabled=not allow_edit,
                )

        # row 4: remarks
        e_rem = st.text_input(
            "Remarks",
            value=v_remarks or "",
            key=f"vt_tank_edit_remarks_{idx}",
            disabled=not allow_edit,
        )

        # ----- Live recompute preview (FULL: calibration + sample params) -----
        try:
            with get_session() as s:
                tov_bbl = (
                    _interp_vol_bbl(s, int(tank_id_val or 0), float(e_dip or 0.0))
                    if tank_id_val
                    else 0.0
                )
                fw_bbl = (
                    _interp_vol_bbl(s, int(tank_id_val or 0), float(e_water or 0.0))
                    if tank_id_val and float(e_water or 0) > 0
                    else 0.0
                )
        except Exception:
            tov_bbl, fw_bbl = 0.0, 0.0
        gov_bbl = max(tov_bbl - fw_bbl, 0.0)

        # API@60 from observed
        if obs_mode == "Observed API":
            api60_val = api60_from_api_obs(float(e_api or 0.0), float(s_temp or 0.0), s_unit)
            dens_obs_val = density_from_api(float(e_api or 0.0))
        else:
            api60_val = api60_from_density_obs(float(e_density or 0.0), float(s_temp or 0.0), s_unit)
            dens_obs_val = float(e_density or 0.0)

        vcf_val = vcf_from_api60_and_tank_temp(api60_val, float(e_tval or 0.0), e_tunit)
        gsv_preview = gsv_from_gov_vcf(gov_bbl, vcf_val)
        bsw_bbl = bsw_volume_from_gsv_pct(gsv_preview, float(e_bsw or 0.0))
        nsv_preview = nsv_from_gsv_bsw(gsv_preview, bsw_bbl)
        mt_preview = mass_mt_from_gsv_api60(gsv_preview, api60_val)
        lt_preview = mass_lt_from_mt(mt_preview)

        st.caption(
            f"Live → TOV: **{tov_bbl:,.2f}** | FW: **{fw_bbl:,.2f}** | GOV: **{gov_bbl:,.2f}** | "
            f"API@60: **{api60_val:.2f}** | VCF: **{vcf_val:.5f}** | "
            f"GSV: **{gsv_preview:,.2f}** | NSV: **{nsv_preview:,.2f}** | MT: **{mt_preview:,.3f}** | LT: **{lt_preview:,.3f}**"
        )
        st.markdown("</div>", unsafe_allow_html=True)

    # actions
    if save_clicked and allow_edit:
        if not _TIME_RE.match((e_time or "").strip()):
            st.error("Time must be in HH:MM (24-hour) format.")
            _audit_error("Edit failed: invalid HH:MM", user, location_id)
            return
        try:
            from sqlalchemy import text as sql_text

            # helper to map label -> enum DB value (UPPERCASE with underscores)
            def label_to_enum(label: str) -> str:
                return label.upper().replace(" ", "_") if label else ""

            enum_val = label_to_enum(e_op if isinstance(e_op, str) else str(e_op))

            # recompute final values (same as preview) for persistence
            try:
                with get_session() as s:
                    tov_bbl = (
                        _interp_vol_bbl(s, int(tank_id_val or 0), float(e_dip or 0.0))
                        if tank_id_val
                        else 0.0
                    )
                    fw_bbl = (
                        _interp_vol_bbl(s, int(tank_id_val or 0), float(e_water or 0.0))
                        if tank_id_val and float(e_water or 0) > 0
                        else 0.0
                    )
            except Exception:
                tov_bbl, fw_bbl = 0.0, 0.0
            gov_bbl = max(tov_bbl - fw_bbl, 0.0)

            if obs_mode == "Observed API":
                api60_val = api60_from_api_obs(float(e_api or 0.0), float(s_temp or 0.0), s_unit)
                dens_obs_val = density_from_api(float(e_api or 0.0))
            else:
                api60_val = api60_from_density_obs(float(e_density or 0.0), float(s_temp or 0.0), s_unit)
                dens_obs_val = float(e_density or 0.0)

            vcf_val = vcf_from_api60_and_tank_temp(api60_val, float(e_tval or 0.0), e_tunit)
            gsv_val = gsv_from_gov_vcf(gov_bbl, vcf_val)
            bsw_bbl = bsw_volume_from_gsv_pct(gsv_val, float(e_bsw or 0.0))
            nsv_val = nsv_from_gsv_bsw(gsv_val, bsw_bbl)
            mt_val = mass_mt_from_gsv_api60(gsv_val, api60_val)
            lt_val = mass_lt_from_mt(mt_val)

            table = TankTransaction.__table__
            cols = {c.key: c for c in table.columns}
            col_keys = set(cols.keys())

            def _col_name_by_key_or_name(*names: str) -> Optional[str]:
                # try keys, then direct column names
                key = _first_present(col_keys, *names)
                if key and key in cols:
                    return cols[key].name
                # fallback: maybe the DB column uses the raw provided name
                for n in names:
                    if n in table.c.keys():
                        return table.c[n].name
                return None

            date_col = _col_name_by_key_or_name(row.get("_date_col") or "date", "tx_date")
            time_col = _col_name_by_key_or_name(row.get("_time_col") or "time", "tx_time")
            op_col = _col_name_by_key_or_name(row.get("_op_col") or "operation", "operation_text")
            dip_col = _col_name_by_key_or_name(row.get("_dip_col") or "dip_cm", "dip")
            water_col = _col_name_by_key_or_name(row.get("_water_col") or "water_cm", "water_level_cm")
            t_c_col = _col_name_by_key_or_name(
                row.get("_t_c_col") or "tank_temp_c", "tank_temperature_c", "tank_temp_celsius"
            )
            t_f_col = _col_name_by_key_or_name(
                row.get("_t_f_col") or "tank_temp_f", "tank_temperature_f", "tank_temp_fahrenheit"
            )
            api_obs_col = _col_name_by_key_or_name(row.get("_api_obs_col") or "api_observed", "api_obs")
            dens_obs_col = _col_name_by_key_or_name(
                row.get("_dens_obs_col") or "density_observed", "density_obs"
            )
            bsw_col = _col_name_by_key_or_name(row.get("_bsw_col") or "bsw_pct")
            api60_col = _col_name_by_key_or_name(
                row.get("_api60_col") or "api_at60", "api60", "api_60", "api_at_60f", "api_60f"
            )
            vcf_col = _col_name_by_key_or_name(row.get("_vcf_col") or "vcf")
            tov_col = _col_name_by_key_or_name(row.get("_tov_col") or "tov_bbl")
            fw_col = _col_name_by_key_or_name(row.get("_fw_col") or "fw_bbl")
            gov_col = _col_name_by_key_or_name(row.get("_gov_col") or "gov_bbl")
            gsv_col = _col_name_by_key_or_name(row.get("_gsv_col") or "gsv_bbl")
            qty_col = _col_name_by_key_or_name(row.get("_qty_col") or "qty_bbls", "nsv_bbl")
            mt_col = _col_name_by_key_or_name(row.get("_mt_col") or "mt")
            lt_col = _col_name_by_key_or_name(row.get("_lt_col") or "lt")
            remarks_col = _col_name_by_key_or_name(row.get("_remarks_col") or "remarks", "comment")
            updated_at_col = _col_name_by_key_or_name("updated_at", "edited_at", "modified_at")
            updated_by_col = _col_name_by_key_or_name("updated_by", "edited_by", "modified_by")

            # Build UPDATE statement dynamically
            set_parts = []
            params: Dict[str, Any] = {"id_val": rec_id}

            if date_col:
                set_parts.append(f"{date_col} = :p_date")
                params["p_date"] = (e_date.isoformat() if hasattr(e_date, "isoformat") else str(e_date))
            if time_col:
                set_parts.append(f"{time_col} = :p_time")
                hh, mm = map(int, (e_time or "00:00").split(":"))
                params["p_time"] = f"{hh:02d}:{mm:02d}:00"
            if op_col:
                set_parts.append(f"{op_col} = :p_op")
                # Use enum-style value if available, else keep existing stored value
                params["p_op"] = enum_val or op_val
            if dip_col:
                set_parts.append(f"{dip_col} = :p_dip")
                params["p_dip"] = float(e_dip)
            if water_col:
                set_parts.append(f"{water_col} = :p_water")
                params["p_water"] = float(e_water)

            # store temp both units if available
            if e_tunit == "°C":
                if t_c_col:
                    set_parts.append(f"{t_c_col} = :p_tc")
                    params["p_tc"] = float(e_tval)
                if t_f_col:
                    set_parts.append(f"{t_f_col} = :p_tf")
                    params["p_tf"] = float(c_to_f(float(e_tval)))
            else:
                if t_f_col:
                    set_parts.append(f"{t_f_col} = :p_tf")
                    params["p_tf"] = float(e_tval)
                if t_c_col:
                    set_parts.append(f"{t_c_col} = :p_tc")
                    params["p_tc"] = float(f_to_c(float(e_tval)))

            if obs_mode == "Observed API":
                if api_obs_col:
                    set_parts.append(f"{api_obs_col} = :p_apiobs")
                    params["p_apiobs"] = float(e_api)
                if dens_obs_col:
                    set_parts.append(f"{dens_obs_col} = :p_densobs")
                    params["p_densobs"] = float(dens_obs_val)
            else:
                if dens_obs_col:
                    set_parts.append(f"{dens_obs_col} = :p_densobs")
                    params["p_densobs"] = float(e_density)
                if api_obs_col:
                    set_parts.append(f"{api_obs_col} = :p_apiobs")
                    params["p_apiobs"] = 0.0

            if bsw_col:
                set_parts.append(f"{bsw_col} = :p_bsw")
                params["p_bsw"] = float(e_bsw)

            if remarks_col is not None:
                set_parts.append(f"{remarks_col} = :p_rem")
                params["p_rem"] = (e_rem or "").strip() or None

            # volumes and masses
            if tov_col:
                set_parts.append(f"{tov_col} = :p_tov")
                params["p_tov"] = float(tov_bbl)
            if fw_col:
                set_parts.append(f"{fw_col} = :p_fw")
                params["p_fw"] = float(fw_bbl)
            if gov_col:
                set_parts.append(f"{gov_col} = :p_gov")
                params["p_gov"] = float(gov_bbl)
            if gsv_col:
                set_parts.append(f"{gsv_col} = :p_gsv")
                params["p_gsv"] = float(gsv_val)
            if qty_col:
                set_parts.append(f"{qty_col} = :p_qty")
                params["p_qty"] = float(nsv_val)
            if mt_col:
                set_parts.append(f"{mt_col} = :p_mt")
                params["p_mt"] = float(mt_val)
            if lt_col:
                set_parts.append(f"{lt_col} = :p_lt")
                params["p_lt"] = float(lt_val)
            if api60_col:
                set_parts.append(f"{api60_col} = :p_api60")
                params["p_api60"] = float(api60_val)
            if vcf_col:
                set_parts.append(f"{vcf_col} = :p_vcf")
                params["p_vcf"] = float(vcf_val)

            if updated_at_col:
                set_parts.append(f"{updated_at_col} = :p_uat")
                params["p_uat"] = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
            if updated_by_col:
                set_parts.append(f"{updated_by_col} = :p_uby")
                params["p_uby"] = (user or {}).get("username", "system")

            if not set_parts:
                st.info("Nothing to update.")
                return

            set_clause = ", ".join(set_parts)
            pk_col = list(table.primary_key.columns)[0].name if table.primary_key.columns else id_col
            sql = f"UPDATE {table.name} SET {set_clause} WHERE {pk_col} = :id_val"

            with get_session() as s:
                s.execute(sql_text(sql), params)
                s.commit()

                # Audit
                try:
                    SecurityManager.log_audit(
                        s,
                        (user or {}).get("username", "system"),
                        "UPDATE",
                        resource_type="TankTransaction",
                        resource_id=str(rec_id),
                        details="Inline edit via View Transactions (full recompute, text UPDATE)",
                        user_id=(user or {}).get("id"),
                        location_id=location_id,
                        ip_address=_get_client_ip(),
                        success=True,
                    )
                except Exception:
                    pass

            st.success("Saved.")
            st.session_state[f"vt_tank_edit_open_{idx}"] = False
            st.rerun()
        except Exception as ex:
            _audit_error(f"Edit save failed: {ex}", user, location_id)
            st.error("Save failed. (Logged)")

    if cancel_clicked:
        st.info("Canceled changes.")
    if close_clicked:
        st.session_state[f"vt_tank_edit_open_{idx}"] = False
        st.rerun()


# ========================= Tank list renderer =========================
def _render_tank_list(location_id: int, user: dict | None):
    _inject_css_once()
    f = _tank_filters_ui(location_id)
    data = _load_tank_rows(location_id, f)

    if not data:
        st.info("No records found.")
        return

    st.markdown("#### Tank Transactions")

    # Header row using columns
    h1, h2, h3, h4, h5, h6, h7, h8, h9, h10, h11 = st.columns(
        [1.0, 0.9, 0.7, 1.0, 1.2, 0.7, 0.9, 1.6, 0.8, 1.0, 0.8]
    )
    with h1:
        st.markdown("**Ticket ID**")
    with h2:
        st.markdown("**Date**")
    with h3:
        st.markdown("**Time**")
    with h4:
        st.markdown("**Tank**")
    with h5:
        st.markdown("**Operation**")
    with h6:
        st.markdown("**Dip (cm)**")
    with h7:
        st.markdown("**NSV (bbls)**")
    with h8:
        st.markdown("**Remarks**")
    with h9:
        st.markdown("**Created By**")
    with h10:
        st.markdown("**Created At**")
    with h11:
        st.markdown("**Actions**")

    # Rows
    for idx, r in enumerate(data):
        ticket = r.get("Ticket ID") or "—"
        edited_badge = ""
        if r.get("_edited"):
            who = str(r.get("_edited_by") or "unknown")
            when = _nice_dt(r.get("_edited_at"))
            edited_badge = f" <span title='Edited by {who} at {when}'>⚠️</span>"

        c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11 = st.columns(
            [1.0, 0.9, 0.7, 1.0, 1.2, 0.7, 0.9, 1.6, 0.8, 1.0, 0.8]
        )

        with c1:
            st.markdown(f"<div class='ellip'>{ticket}{edited_badge}</div>", unsafe_allow_html=True)
        with c2:
            st.markdown(f"<div class='ellip'>{str(r.get('Date') or '')}</div>", unsafe_allow_html=True)
        with c3:
            st.markdown(f"<div class='ellip'>{str(r.get('Time') or '')}</div>", unsafe_allow_html=True)
        with c4:
            st.markdown(f"<div class='ellip'>{str(r.get('Tank') or '')}</div>", unsafe_allow_html=True)
        with c5:
            st.markdown(f"<div class='ellip'>{str(r.get('Operation') or '')}</div>", unsafe_allow_html=True)
        with c6:
            dipv = r.get("Dip (cm)")
            st.markdown(
                f"<div class='ellip'>{(f'{dipv:.1f}' if isinstance(dipv,(int,float)) else '—')}</div>",
                unsafe_allow_html=True,
            )
        with c7:
            qv = r.get("NSV (bbls)")
            st.markdown(
                f"<div class='ellip'>{(f'{qv:,.2f}' if isinstance(qv,(int,float)) else '—')}</div>",
                unsafe_allow_html=True,
            )
        with c8:
            st.markdown(f"<div class='ellip'>{(r.get('Remarks') or '')}</div>", unsafe_allow_html=True)
        with c9:
            st.markdown(f"<div class='ellip'>{str(r.get('Created By') or '')}</div>", unsafe_allow_html=True)
        with c10:
            st.markdown(f"<div class='ellip'>{_nice_dt(r.get('Created At'))}</div>", unsafe_allow_html=True)
        with c11:
            a1, a2, a3 = st.columns([0.34, 0.33, 0.33], gap="small")
            with a1:
                if st.button("👁️", key=f"vt_tank_view_{idx}", help="View"):
                    st.session_state[f"vt_tank_view_open_{idx}"] = not st.session_state.get(
                        f"vt_tank_view_open_{idx}", False
                    )
                    st.session_state[f"vt_tank_edit_open_{idx}"] = False
            with a2:
                if st.button("✏️", key=f"vt_tank_edit_{idx}", help="Edit"):
                    st.session_state[f"vt_tank_edit_open_{idx}"] = not st.session_state.get(
                        f"vt_tank_edit_open_{idx}", False
                    )
                    st.session_state[f"vt_tank_view_open_{idx}"] = False
            with a3:
                if st.button("🗑️", key=f"vt_tank_del_{idx}", help="Delete"):
                    st.session_state[f"vt_tank_show_delete_ui_{idx}"] = True

        # Deletion approval UI
        if st.session_state.get(f"vt_tank_show_delete_ui_{idx}"):
            from sqlalchemy import text as sql_text

            data_row = r["_row"]
            table = TankTransaction.__table__
            pk_col = list(table.primary_key.columns)[0].name if table.primary_key.columns else "id"
            rec_id = data_row.get(pk_col, data_row.get("id"))
            
            if rec_id is None:
                st.error("Record ID not found for deletion")
            else:
                def delete_tank_record():
                    with get_session() as s:
                        if TankTransaction and RecycleBinManager:
                            try:
                                obj = s.query(TankTransaction).get(rec_id)
                                if obj:
                                    RecycleBinManager.archive_record(
                                        s, obj, "TankTransaction",
                                        username=(user or {}).get("username", "system"),
                                        user_id=(user or {}).get("id"),
                                        location_id=location_id,
                                        reason=f"Deleted ticket {r.get('Ticket ID')}",
                                        label=str(rec_id)
                                    )
                                    s.commit()
                            except Exception:
                                s.execute(
                                    sql_text(f"DELETE FROM {table.name} WHERE {pk_col} = :id_val"),
                                    {"id_val": rec_id}
                                )
                                s.commit()
                        else:
                            s.execute(
                                sql_text(f"DELETE FROM {table.name} WHERE {pk_col} = :id_val"),
                                {"id_val": rec_id}
                            )
                            s.commit()
                
                if render_deletion_ui(
                    resource_type="TankTransaction",
                    resource_id=rec_id,
                    resource_label=f"Tank Transaction Ticket #{r.get('Ticket ID', rec_id)}",
                    delete_func=delete_tank_record,
                    user=user,
                    location_id=location_id,
                    on_success_message="Tank transaction moved to Deleted Records",
                    metadata={"ticket_id": r.get('Ticket ID'), "tank_name": r.get('Tank Name')},
                    button_key_prefix=f"vt_tank_{idx}"
                ):
                    st.session_state[f"vt_tank_show_delete_ui_{idx}"] = False
                    st.rerun()        # inline viewer/editor rows
        if st.session_state.get(f"vt_tank_view_open_{idx}", False):
            _inline_tank_viewer(idx, r, user, location_id)
        if st.session_state.get(f"vt_tank_edit_open_{idx}", False):
            _inline_tank_editor(idx, r, user, location_id)


# ========================= Flexible viewers (other tabs) =========================
def _flex_list(location_id: int, section: str, user: dict | None, title: str):
    """
    Universal custom table viewer and editor for ALL flex_* tables.
    
    This function automatically handles any custom table (production, meters, condensate, etc.)
    by dynamically loading table structure and creating appropriate edit forms.
    
    Features:
    - Automatic detection of all columns (system and user-defined)
    - Individual input fields based on data types (date, number, text, checkbox)
    - 24-hour edit restriction with visual lock indicator
    - Edit tracking (who edited and when) with visual badge
    - Comprehensive error logging for debugging
    - Works with ANY flex_{section}_{location_id} table without code changes
    
    Parameters:
        location_id: The location ID for the custom table
        section: The section name (production, meters, condensate, etc.)
        user: Current user dict with username and permissions
        title: Display title for the UI section
    
    Future custom tables will automatically work with this code - no modifications needed.
    """
    _inject_css_once()
    try:
        from models import FlexibleRecord
    except Exception:
        st.info("FlexibleRecord model not found. Please define it in models.py to view this section.")
        return

    # Date bounds for this section
    d_min, d_max = _get_flex_date_bounds(location_id, section)
    default_date = d_max

    c1, c2, c3 = st.columns([0.25, 0.35, 0.40], gap="small")
    with c1:
        d = st.date_input(
            "Date",
            value=default_date,
            min_value=d_min,
            max_value=d_max,
            key=f"vt_{section}_d",
        )
    with c2:
        created_by = (st.text_input("Created by", key=f"vt_{section}_by") or "").strip()
    with c3:
        search = (st.text_input("Search text", key=f"vt_{section}_q") or "").strip()

    # Automatically detect if this is a custom table (flex_*) or legacy FlexibleRecord
    # This works for ALL current and future custom tables without code changes
    is_custom = False
    rows = []
    try:
        from models import get_custom_table_model
        table_name = f"flex_{section}_{location_id}"
        Model = get_custom_table_model(table_name)
        with get_session() as s:
            if Model:
                is_custom = True
                q = s.query(Model).filter(getattr(Model, "location_id") == location_id)
                if d and hasattr(Model, "tx_date"):
                    q = q.filter(getattr(Model, "tx_date") == d)
                if created_by and hasattr(Model, "created_by"):
                    q = q.filter(getattr(Model, "created_by").ilike(f"%{created_by}%"))
                # best-effort search on 'remarks' column if present
                if search and hasattr(Model, "remarks"):
                    q = q.filter(getattr(Model, "remarks").ilike(f"%{search}%"))
                # order by date then id
                if hasattr(Model, "tx_date"):
                    q = q.order_by(getattr(Model, "tx_date").desc())
                if hasattr(Model, "id"):
                    q = q.order_by(getattr(Model, "id").desc())
                rows = q.limit(500).all()
            else:
                with get_session() as s2:
                    q = s2.query(FlexibleRecord).filter(
                        FlexibleRecord.location_id == location_id,
                        FlexibleRecord.page == "tank_transactions",
                        FlexibleRecord.section == section,
                    )
                    if d:
                        q = q.filter(FlexibleRecord.tx_date == d)
                    if created_by:
                        q = q.filter(getattr(FlexibleRecord, "created_by").ilike(f"%{created_by}%"))
                    if search:
                        q = q.filter(getattr(FlexibleRecord, "data_json").ilike(f"%{search}%"))
                    q = q.order_by(FlexibleRecord.tx_date.desc(), FlexibleRecord.id.desc()).limit(500)
                    rows = q.all()
    except Exception as ex:
        _audit_error(f"Load {section} failed: {ex}", user, location_id)
        st.error(f"Failed to load {title}. (Logged)")
        return

    if not rows:
        st.info("No records found.")
        return

    # Automatically detect all columns from the table structure
    # This works for any number of custom columns defined in any flex_* table
    keyset = set()  # User-visible columns for display
    all_columns_set = set()  # ALL columns including system ones for edit operations
    
    if is_custom:
        try:
            cols = [c.name for c in rows[0].__table__.columns] if rows else []
        except Exception:
            cols = []
        for k in cols:
            all_columns_set.add(k)  # Store all columns
            # Only add non-system columns to keyset for display
            if k in {"id", "location_id", "tx_date", "created_by", "created_at", "updated_by", "updated_at"}:
                continue
            keyset.add(k)
    else:
        for rr in rows:
            try:
                p = json.loads(getattr(rr, "data_json", "") or "{}")
            except Exception:
                p = {}
            if isinstance(p, dict):
                for k, v in p.items():
                    all_columns_set.add(k)  # Store all columns
                    if k in ("remarks", "__edited_by__", "__edited_at__"):
                        continue
                    if isinstance(v, (dict, list, tuple)):
                        continue
                    keyset.add(k)
    
    display_keys: List[str] = sorted(list(keyset))
    # Keep ALL columns for edit operations (excluding system columns like id, location_id, etc.)
    all_keys = [k for k in sorted(list(all_columns_set)) 
                if k not in {"id", "location_id", "created_at", "updated_at"}]
    
    # Filter out date-related fields that will be shown separately to avoid duplication
    display_keys = [k for k in display_keys if k not in ('tx_date', 'date', 'transaction_date')]
    
    widths = [0.16] + ([0.12] * len(display_keys)) + [0.20, 0.20, 0.10]
    cols = st.columns(widths if display_keys else [0.18, 0.42, 0.20, 0.20, 0.10], gap="small")
    if display_keys:
        cols[0].markdown("**Date**")
        for i, k in enumerate(display_keys, start=1):
            cols[i].markdown(f"**{k.replace('_',' ').title()}**")
        cols[-3].markdown("**Remarks**")
        cols[-2].markdown("**Created By / At**")
        cols[-1].markdown("**Actions**")
    else:
        cols[0].markdown("**Date**")
        cols[1].markdown("**Summary**")
        cols[2].markdown("**Remarks**")
        cols[3].markdown("**Created By / At**")
        cols[4].markdown("**Actions**")

    def _fmt_val(v):
        try:
            if v is None:
                return ""
            if isinstance(v, (int, float)):
                return f"{float(v):,.2f}"
            s = str(v)
            return s if len(s) <= 140 else (s[:137] + "…")
        except Exception:
            return ""

    def _build_summary(payload: dict) -> str:
        try:
            if section == "meters":
                total = payload.get("net_total_bbl") or 0.0
                return f"Net Total: {float(total):,.2f} bbl"
            if section == "condensate":
                gov = payload.get("gov_bbl") or 0.0
                nsv = payload.get("nsv_bbl") or 0.0
                api60 = payload.get("api60") or 0.0
                return f"GOV {float(gov):,.2f} | NSV {float(nsv):,.2f} | API@60 {float(api60):.2f}"
            parts = []
            for k, v in payload.items():
                if k in ("remarks", "__edited_by__", "__edited_at__"):
                    continue
                if isinstance(v, (dict, list, tuple)):
                    continue
                parts.append(f"{k}: {_fmt_val(v)}")
                if len(parts) >= 4:
                    break
            return " • ".join(parts) if parts else ""
        except Exception:
            return ""

    for i, r in enumerate(rows):
        try:
            if is_custom:
                payload = None
                summ = ""
            else:
                try:
                    payload = json.loads(r.data_json or "{}")
                except Exception:
                    payload = {}
                summ = _build_summary(payload)
            
            remarks = (payload or {}).get("remarks") or getattr(r, "remarks", "")
            created = _nice_dt(getattr(r, "created_at", None))
            created_by = getattr(r, "created_by", "")
            
            # Get edit tracking info (works for all custom tables automatically)
            edited_by = getattr(r, "updated_by", None) if is_custom else (payload or {}).get("__edited_by__")
            edited_at = getattr(r, "updated_at", None) if is_custom else (payload or {}).get("__edited_at__")
            edited_badge = ""
            if edited_by or edited_at:
                wh = str(edited_by or "unknown")
                wn = _nice_dt(edited_at) if edited_at else "unknown time"  # Format timestamp properly
                edited_badge = f" <span title='Edited by {wh} on {wn}'>⚠️</span>"

            
            # Check if record is editable (within 24 hours)
            rec_created_at = getattr(r, 'created_at', None)
            is_editable = True
            if rec_created_at:
                try:
                    if isinstance(rec_created_at, str):
                        rec_created_at = datetime.fromisoformat(rec_created_at)
                    time_diff = datetime.utcnow() - rec_created_at
                    is_editable = time_diff.total_seconds() < (24 * 3600)
                except Exception:
                    is_editable = True
            
            if display_keys:
                row_cols = st.columns(widths, gap="small")
                # Display date with edited badge (no duplicate)
                tx_date_str = str(getattr(r, 'tx_date', '') or '')
                row_cols[0].markdown(f"<div class='ellip'>{tx_date_str}{edited_badge}</div>", unsafe_allow_html=True)
                for j, k in enumerate(display_keys, start=1):
                    v = getattr(r, k) if is_custom else (payload or {}).get(k)
                    row_cols[j].markdown(f"<div class='ellip'>{_fmt_val(v)}</div>", unsafe_allow_html=True)
                row_cols[-3].markdown(f"<div class='ellip'>{remarks}</div>", unsafe_allow_html=True)
                row_cols[-2].markdown(f"<div class='ellip'>{created_by} | {created}</div>", unsafe_allow_html=True)
                
                # Action buttons - different for production section
                if section == "production":
                    # Production: Only Edit and Delete buttons
                    act1, act2 = row_cols[-1].columns([0.50, 0.50], gap="small")
                    with act1:
                        if is_editable:
                            edit_state_key = f"vt_{section}_edit_{i}"
                            is_editing = st.session_state.get(edit_state_key, False)
                            if st.button("✏️" if not is_editing else "✖️", key=f"vt_{section}_edit_btn_{i}", help="Edit (within 24hrs)" if not is_editing else "Close"):
                                st.session_state[edit_state_key] = not is_editing
                                st.rerun()
                        else:
                            st.button("🔒", key=f"vt_{section}_edit_{i}_locked", help="Edit locked (>24hrs)", disabled=True)
                    with act2:
                        if st.button("🗑️", key=f"vt_{section}_del_{i}", help="Delete"):
                            st.session_state[f"vt_{section}_del_confirm_{i}"] = True
                else:
                    # Other sections: View, Edit, Delete buttons
                    act1, act2, act3 = row_cols[-1].columns([0.34, 0.33, 0.33], gap="small")
                    with act1:
                        view_state_key = f"vt_{section}_open_{i}"
                        is_viewing = st.session_state.get(view_state_key, False)
                        if st.button("👁️", key=f"vt_{section}_view_btn_{i}", help="View"):
                            st.session_state[view_state_key] = not is_viewing
                            st.session_state[f"vt_{section}_edit_{i}"] = False
                            st.rerun()
                    with act2:
                        if is_editable:
                            edit_state_key = f"vt_{section}_edit_{i}"
                            is_editing = st.session_state.get(edit_state_key, False)
                            if st.button("✏️" if not is_editing else "✖️", key=f"vt_{section}_edit_btn_{i}", help="Edit" if not is_editing else "Close"):
                                st.session_state[edit_state_key] = not is_editing
                                st.session_state[f"vt_{section}_open_{i}"] = False
                                st.rerun()
                        else:
                            st.button("🔒", key=f"vt_{section}_edit_{i}_locked", help="Edit locked (>24hrs)", disabled=True)
                    with act3:
                        if st.button("🗑️", key=f"vt_{section}_del_{i}", help="Delete"):
                            st.session_state[f"vt_{section}_show_delete_ui_{i}"] = True
            else:
                c1, c2, c3, c4, c5 = st.columns([0.18, 0.42, 0.20, 0.20, 0.10], gap="small")
                with c1:
                    st.markdown(f"<div class='ellip'>{str(getattr(r, 'tx_date', '') or '')}{edited_badge}</div>", unsafe_allow_html=True)
                with c2:
                    st.markdown(f"<div class='ellip'>{summ}</div>", unsafe_allow_html=True)
                with c3:
                    st.markdown(f"<div class='ellip'>{remarks}</div>", unsafe_allow_html=True)
                with c4:
                    st.markdown(f"<div class='ellip'>{created_by} | {created}</div>", unsafe_allow_html=True)
                with c5:
                    # Action buttons - different for production section
                    if section == "production":
                        # Production: Only Edit and Delete buttons
                        a1, a2 = st.columns([0.50, 0.50], gap="small")
                        with a1:
                            if is_editable:
                                edit_state_key = f"vt_{section}_edit_{i}"
                                is_editing = st.session_state.get(edit_state_key, False)
                                if st.button("✏️" if not is_editing else "✖️", key=f"vt_{section}_edit_btn2_{i}", help="Edit (within 24hrs)" if not is_editing else "Close"):
                                    st.session_state[edit_state_key] = not is_editing
                                    st.rerun()
                            else:
                                st.button("🔒", key=f"vt_{section}_edit2_{i}_locked", help="Edit locked (>24hrs)", disabled=True)
                        with a2:
                            if st.button("🗑️", key=f"vt_{section}_del2_{i}", help="Delete"):
                                st.session_state[f"vt_{section}_show_delete_ui_{i}"] = True
                    else:
                        # Other sections: View, Edit, Delete buttons
                        a1, a2, a3 = st.columns([0.34, 0.33, 0.33], gap="small")
                        with a1:
                            view_state_key = f"vt_{section}_open_{i}"
                            is_viewing = st.session_state.get(view_state_key, False)
                            if st.button("👁️", key=f"vt_{section}_view_btn2_{i}", help="View"):
                                st.session_state[view_state_key] = not is_viewing
                                st.session_state[f"vt_{section}_edit_{i}"] = False
                                st.rerun()
                        with a2:
                            if is_editable:
                                edit_state_key = f"vt_{section}_edit_{i}"
                                is_editing = st.session_state.get(edit_state_key, False)
                                if st.button("✏️" if not is_editing else "✖️", key=f"vt_{section}_edit_btn2_{i}", help="Edit" if not is_editing else "Close"):
                                    st.session_state[edit_state_key] = not is_editing
                                    st.session_state[f"vt_{section}_open_{i}"] = False
                                    st.rerun()
                            else:
                                st.button("🔒", key=f"vt_{section}_edit2_{i}_locked", help="Edit locked (>24hrs)", disabled=True)
                        with a3:
                            if st.button("🗑️", key=f"vt_{section}_del2_{i}", help="Delete"):
                                st.session_state[f"vt_{section}_show_delete_ui_{i}"] = True

            # Deletion approval UI for flexible records
            if st.session_state.get(f"vt_{section}_show_delete_ui_{i}"):
                def delete_flex_record():
                    with get_session() as s:
                        if is_custom:
                            M = get_custom_table_model(f"flex_{section}_{location_id}")
                            rec = s.query(M).get(getattr(r, "id")) if M else None
                            if rec:
                                s.delete(rec)
                                s.commit()
                        else:
                            if RecycleBinManager:
                                try:
                                    RecycleBinManager.archive_record(
                                        s, r, f"FlexibleRecord:{section}",
                                        username=(user or {}).get("username", "system"),
                                        user_id=(user or {}).get("id"),
                                        location_id=location_id,
                                        reason=f"Deleted {section} record on {getattr(r,'tx_date', '')}",
                                        label=str(getattr(r, "id", ""))
                                    )
                                    s.commit()
                                except Exception:
                                    s.delete(r)
                                    s.commit()
                            else:
                                s.delete(r)
                                s.commit()
                
                if render_deletion_ui(
                    resource_type=f"FlexibleRecord:{section}",
                    resource_id=getattr(r, "id"),
                    resource_label=f"{section.title()} Record #{getattr(r, 'id')}",
                    delete_func=delete_flex_record,
                    user=user,
                    location_id=location_id,
                    on_success_message=f"{section.title()} record deleted successfully",
                    metadata={"section": section, "tx_date": str(getattr(r, 'tx_date', ''))},
                    button_key_prefix=f"vt_{section}_{i}"
                ):
                    st.session_state[f"vt_{section}_show_delete_ui_{i}"] = False
                    st.rerun()

            if st.session_state.get(f"vt_{section}_open_{i}", False):
                with st.container():
                    st.markdown('<div class="vt-editline vt-compact">', unsafe_allow_html=True)
                    if is_custom:
                        # Use all_keys to show all columns in view mode
                        data_dict = {k: getattr(r, k, None) for k in all_keys}
                        st.code(json.dumps(data_dict, indent=2, default=str), language="json")
                    else:
                        st.code(json.dumps(payload, indent=2, default=str), language="json")
                    if st.button("✖️ Close", key=f"vt_{section}_close_{i}"):
                        st.session_state[f"vt_{section}_open_{i}"] = False
                        st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)

            if st.session_state.get(f"vt_{section}_edit_{i}", False):
                # Check if editing is still allowed (24-hour window)
                if not is_editable:
                    st.warning("⏱️ This record cannot be edited (more than 24 hours old)")
                    if st.button("Close", key=f"vt_{section}_edit_close_{i}"):
                        st.session_state[f"vt_{section}_edit_{i}"] = False
                        st.rerun()
                else:
                    try:
                        with st.form(key=f"vt_{section}_edit_form_{i}"):
                            st.info(f"🔒 System columns (id, location_id, created_by, etc.) are protected and cannot be edited.")
                            
                            if is_custom:
                                # Automatically determine editable columns (exclude system/protected columns)
                                # This works for ANY custom table with any number of custom fields
                                editable_cols = [k for k in all_keys if k not in {'id', 'location_id', 'created_by', 'created_at', 'updated_by', 'updated_at'}]
                                
                                # Automatically generate appropriate input fields based on data types
                                # Works for dates, numbers, text, checkboxes - all auto-detected
                                edited_values = {}
                                for col_name in editable_cols:
                                    current_value = getattr(r, col_name, None)
                                    label = col_name.replace('_', ' ').title()
                                    
                                    # Determine input type based on column name and value type
                                    if col_name in ('tx_date', 'date', 'transaction_date', 'start_date', 'end_date'):
                                        # Date fields
                                        if isinstance(current_value, date):
                                            edited_values[col_name] = st.date_input(label, value=current_value, key=f"edit_{section}_{i}_{col_name}")
                                        elif isinstance(current_value, str):
                                            try:
                                                parsed_date = datetime.strptime(current_value, "%Y-%m-%d").date()
                                                edited_values[col_name] = st.date_input(label, value=parsed_date, key=f"edit_{section}_{i}_{col_name}")
                                            except:
                                                edited_values[col_name] = st.date_input(label, value=date.today(), key=f"edit_{section}_{i}_{col_name}")
                                        else:
                                            edited_values[col_name] = st.date_input(label, value=date.today(), key=f"edit_{section}_{i}_{col_name}")
                                    elif current_value is None:
                                        edited_values[col_name] = st.text_input(label, value="", key=f"edit_{section}_{i}_{col_name}")
                                    elif isinstance(current_value, (int, float)):
                                        edited_values[col_name] = st.number_input(label, value=float(current_value), key=f"edit_{section}_{i}_{col_name}")
                                    elif isinstance(current_value, bool):
                                        edited_values[col_name] = st.checkbox(label, value=current_value, key=f"edit_{section}_{i}_{col_name}")
                                    elif isinstance(current_value, str) and len(str(current_value)) > 100:
                                        edited_values[col_name] = st.text_area(label, value=str(current_value), height=100, key=f"edit_{section}_{i}_{col_name}")
                                    else:
                                        edited_values[col_name] = st.text_input(label, value=str(current_value) if current_value else "", key=f"edit_{section}_{i}_{col_name}")
                            else:
                                # For non-custom tables, use JSON editor
                                ed_json = st.text_area("Data (JSON)", value=json.dumps(payload, indent=2, default=str), height=220)
                            
                            bcol1, bcol2 = st.columns([0.20, 0.80])
                            with bcol1:
                                save = st.form_submit_button("💾 Save", type="primary")
                            with bcol2:
                                cancel = st.form_submit_button("↩️ Cancel")
                        
                        if save:
                            from logger import log_info, log_error
                            log_info(f"Save button clicked for {section} record {getattr(r, 'id', 'unknown')}")
                            
                            if is_custom:
                                try:
                                    from logger import log_info, log_error
                                    log_info(f"Attempting to save {section} record ID: {getattr(r, 'id', 'unknown')}")
                                    log_info(f"Editable columns: {editable_cols}")
                                    log_info(f"Edited values: {edited_values}")
                                    
                                    with get_session() as s:
                                        M = get_custom_table_model(f"flex_{section}_{location_id}")
                                        if not M:
                                            log_error(f"Failed to get model for flex_{section}_{location_id}")
                                            raise Exception(f"Could not load table model for flex_{section}_{location_id}")
                                        
                                        rec = s.query(M).get(getattr(r, "id"))
                                        if not rec:
                                            log_error(f"Record with ID {getattr(r, 'id')} not found in database")
                                            raise Exception(f"Record not found in database")
                                        
                                        log_info(f"Found record in database, updating fields...")
                                        
                                        # Automatically save all user-editable columns
                                        # Works for any custom table with any field types
                                        editable_cols = [k for k in all_keys if k not in {'id', 'location_id', 'created_by', 'created_at', 'updated_by', 'updated_at'}]
                                        for k in editable_cols:
                                            if k in edited_values:
                                                old_val = getattr(rec, k, None)
                                                new_val = edited_values[k]
                                                
                                                # Automatic type conversion for SQLite compatibility
                                                # Handles dates, strings, numbers, booleans automatically
                                                if k in ('tx_date', 'date', 'transaction_date', 'start_date', 'end_date'):
                                                    # Ensure date fields are Python date objects
                                                    if isinstance(new_val, str):
                                                        try:
                                                            new_val = datetime.strptime(new_val, "%Y-%m-%d").date()
                                                        except:
                                                            log_error(f"Failed to parse date string '{new_val}' for column {k}")
                                                            continue
                                                    elif isinstance(new_val, datetime):
                                                        new_val = new_val.date()
                                                    # If already a date object, keep as is
                                                elif isinstance(new_val, str) and new_val == "":
                                                    # Convert empty strings to None for optional fields
                                                    new_val = None
                                                
                                                setattr(rec, k, new_val)
                                                log_info(f"Updated {k}: {old_val} -> {new_val}")
                                        
                                        if hasattr(rec, "updated_by"):
                                            setattr(rec, "updated_by", (user or {}).get("username", "system"))
                                            log_info(f"Set updated_by to {(user or {}).get('username', 'system')}")
                                        
                                        s.commit()
                                        log_info(f"Successfully committed changes to database")
                                        
                                        try:
                                            SecurityManager.log_audit(
                                                s,
                                                (user or {}).get("username", "system"),
                                                "UPDATE",
                                                resource_type=f"Custom:{section}",
                                                resource_id=str(getattr(r, "id")),
                                                details=f"Inline edit via View Transactions - Updated fields: {', '.join(editable_cols)}",
                                                user_id=(user or {}).get("id"),
                                                location_id=location_id,
                                                ip_address=_get_client_ip(),
                                                success=True,
                                            )
                                            log_info("Audit log created successfully")
                                        except Exception as audit_ex:
                                            log_error(f"Failed to create audit log: {str(audit_ex)}")
                                    
                                    st.success("✅ Saved successfully!")
                                    st.session_state[f"vt_{section}_edit_{i}"] = False
                                    st.rerun()
                                except Exception as ex:
                                    from logger import log_error
                                    log_error(f"Edit {section} failed: {str(ex)}", exc_info=True)
                                    _audit_error(f"Edit {section} record {getattr(r, 'id', 'unknown')} failed: {ex}", user, location_id)
                                    st.error(f"❌ Save failed: {str(ex)} (Logged)")
                            else:
                                # Non-custom table handling
                                try:
                                    new_payload = json.loads(ed_json or "{}")
                                except Exception as json_err:
                                    from logger import log_error
                                    log_error(f"Invalid JSON in edit form: {str(json_err)}")
                                    st.error(f"Invalid JSON: {str(json_err)}")
                                    new_payload = None
                                
                                if new_payload:
                                    new_payload["__edited_by__"] = (user or {}).get("username", "system")
                                    new_payload["__edited_at__"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                                    try:
                                        from logger import log_info, log_error
                                        log_info(f"Attempting to save non-custom {section} record ID: {getattr(r, 'id', 'unknown')}")
                                        
                                        with get_session() as s:
                                            rec = s.query(FlexibleRecord).get(getattr(r, "id"))
                                            if rec:
                                                rec.data_json = json.dumps(new_payload, default=str)
                                                s.commit()
                                                log_info(f"Successfully updated FlexibleRecord ID: {getattr(r, 'id')}")
                                                try:
                                                    SecurityManager.log_audit(
                                                        s,
                                                        (user or {}).get("username", "system"),
                                                        "UPDATE",
                                                        resource_type=f"FlexibleRecord:{section}",
                                                        resource_id=str(getattr(r, "id")),
                                                        details="Inline edit via View Transactions",
                                                        user_id=(user or {}).get("id"),
                                                        location_id=location_id,
                                                        ip_address=_get_client_ip(),
                                                        success=True,
                                                    )
                                                except Exception as audit_ex:
                                                    log_error(f"Audit log failed: {str(audit_ex)}")
                                            else:
                                                log_error(f"FlexibleRecord with ID {getattr(r, 'id')} not found")
                                        st.success("✅ Saved successfully!")
                                        st.session_state[f"vt_{section}_edit_{i}"] = False
                                        st.rerun()
                                    except Exception as ex:
                                        from logger import log_error
                                        log_error(f"Save non-custom {section} failed: {str(ex)}", exc_info=True)
                                        _audit_error(f"Save non-custom {section} failed: {ex}", user, location_id)
                                        st.error(f"❌ Save failed: {str(ex)} (Logged)")
                        
                        if cancel:
                            from logger import log_info
                            log_info(f"Edit cancelled for {section} record {getattr(r, 'id', 'unknown')}")
                            st.session_state[f"vt_{section}_edit_{i}"] = False
                            st.rerun()
                    except Exception as ex:
                        from logger import log_error
                        log_error(f"Edit render failed for {section} row {i}: {str(ex)}", exc_info=True)
                        _audit_error(f"Edit render failed: {ex}", user, location_id)
                        st.error("Edit UI failed. (Logged)")
        except Exception as ex:
            from logger import log_error
            log_error(f"Render {section} row {i} failed: {str(ex)}", exc_info=True)
            _audit_error(f"Render {section} row failed: {ex}", user, location_id)
            st.warning(f"Skipped one {title.lower()} row due to an error. (Logged)")

def _render_meters_tab(location_id: int, user: dict | None):
    _flex_list(location_id, "meters", user, "Meter Records")


def _render_condensate_tab(location_id: int, user: dict | None):
    _flex_list(location_id, "condensate", user, "Condensate Records")


def _render_pw_tab(location_id: int, user: dict | None):
    _flex_list(location_id, "produced_water", user, "Produced Water Records")


def _render_production_tab(location_id: int, user: dict | None):
    _flex_list(location_id, "production", user, "Production")


# ========================= Tank tabs wrapper (viewer) =========================
def _render_tank_view_tabs(location_id: int, location_label: str, user: dict | None):
    flags = {
        "Tank Entry": True,
        "Meter Records": True,
        "Condensate Records": True,
        "Produced Water Records": True,
        "Production": False,
    }
    if get_tank_transactions_tab_visibility:
        try:
            with get_session() as s:
                flags = get_tank_transactions_tab_visibility(s, location_id) or flags
        except Exception:
            pass

    tab_defs = [
        ("Tank Entry", _render_tank_list),
        ("Meter Records", _render_meters_tab),
        ("Condensate Records", _render_condensate_tab),
        ("Produced Water Records", _render_pw_tab),
        ("Production", _render_production_tab),
    ]
    enabled = [(label, fn) for (label, fn) in tab_defs if flags.get(label, False)]
    if not enabled:
        st.info("No tabs are enabled for this location.")
        return

    labels = [lbl for lbl, _ in enabled]
    fns = [fn for _, fn in enabled]
    tabs = st.tabs(labels)
    for t, fn, lbl in zip(tabs, fns, labels):
        with t:
            fn(location_id, user)


# ========================= main page =========================
def render_view_transactions_page(active_location_id, user):
    try:
        st.markdown("### 🗂️ View Transactions")
        loc, loc_label = _guard_location(active_location_id)
        if not loc:
            return
        if not _guard_permissions(user, active_location_id):
            return

        st.caption(f"Active Location: **{loc_label}**")

        source = st.selectbox("Source", ["Tank", "Yade", "Tanker"], index=0, key="vt_source_sel")
        if source == "Tank":
            _render_tank_view_tabs(loc.id, loc_label, user)
        elif source == "Yade":
            # ⬇️ UPDATED: call the new YADE list + inline editor + PDF renderer
            render_yade_transactions_view(user=user or {}, location_id=loc.id)
        else:
            render_tanker_transactions_view(user=user or {}, location_id=loc.id)
    except Exception as ex:
        _audit_error(f"Render failed: {ex}", user, active_location_id)
        st.error("Unexpected error while rendering View Transactions. (Logged)")
