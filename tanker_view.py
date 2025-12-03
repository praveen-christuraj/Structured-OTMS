# tanker_view.py
from __future__ import annotations
from typing import Dict, Any, Optional, List
import io
import base64
from datetime import date, datetime
from html import escape

import streamlit as st
from sqlalchemy.orm import Session
import streamlit.components.v1 as components

from db import get_session
from models import TankerTransaction
from security import SecurityManager

from utils_calc import (
    api60_from_api_obs,
    api60_from_density_obs,
    api_from_density,
    density_from_api,
    normalize_temp_unit,
    temp_bounds,
    vcf_from_api60_and_tank_temp,
    get_lt_factor,
)
try:
    from models import TankerCalibration
except Exception:
    TankerCalibration = None
API_LIMITS = (15.0, 70.0)       # same as entry page
DENSITY_LIMITS = (600.0, 1000.0)
TEMP_LIMITS = {"C": (0.0, 60.0), "F": (32.0, 120.0)}

# ========== Small Utils ==========

def _fmt_date(d: date | None) -> str:
    try:
        return d.strftime("%Y-%m-%d") if isinstance(d, date) else "—"
    except Exception:
        return "—"

def _fmt_time(t) -> str:
    try:
        return t.strftime("%H:%M")
    except Exception:
        return "—"

def _fmt_num(v, nd=0) -> str:
    try:
        return f"{float(v):,.{nd}f}"
    except Exception:
        return "0"

def _caution_badge(created_by: Optional[str], updated_by: Optional[str], updated_at: Optional[datetime]) -> str:
    cb = (created_by or "—")
    if updated_by and updated_at:
        tip = f"Edited by {updated_by} on {updated_at.strftime('%Y-%m-%d %H:%M')}"
        return f'<span>{cb}&nbsp;&nbsp;<span title="{tip}">⚠️</span></span>'
    return f"<span>{cb}</span>"

def _confirm_prompt(key: str, message: str) -> bool:
    ph = st.empty()
    with ph.container():
        st.warning(message)
        c1, c2 = st.columns([1, 1])
        ok = False
        with c1:
            if st.button("✅ Yes, confirm", key=f"{key}_yes"):
                ok = True
        with c2:
            if st.button("❌ Cancel", key=f"{key}_no"):
                ok = False
    ph.empty()
    return ok

# ---------- safe float ----------
def _afloat(x) -> float:
    try:
        v = float(x)
        if v != v or v in (float("inf"), float("-inf")):
            return 0.0
        return v
    except Exception:
        return 0.0

LITRES_PER_BBL = 158.987

# ---------- calibration lookup / interpolation (cm -> litres) ----------
def _interp_tanker_volume_litres(session: Session, tanker_name: str, dip_cm: float) -> float:
    if not TankerCalibration or not tanker_name:
        return 0.0
    dip_mm = _afloat(dip_cm) * 10.0
    if dip_mm <= 0:
        return 0.0
    rows = (
        session.query(TankerCalibration)
        .filter(TankerCalibration.tanker_name == tanker_name)
        .order_by(TankerCalibration.dip_mm.asc())
        .all()
    )
    if not rows:
        return 0.0
    xs = [float(getattr(r, "dip_mm", 0.0) or 0.0) for r in rows]
    ys = [float(getattr(r, "volume_litres", 0.0) or 0.0) for r in rows]
    if dip_mm <= xs[0]:
        return ys[0]
    if dip_mm >= xs[-1]:
        return ys[-1]
    import bisect
    i = bisect.bisect_left(xs, dip_mm)
    x1, y1 = xs[i-1], ys[i-1]
    x2, y2 = xs[i], ys[i]
    if x2 == x1:
        return y1
    t = (dip_mm - x1) / (x2 - x1)
    return y1 + t * (y2 - y1)

def _recompute_quantities(
    session: Session,
    *,
    tanker_name: str,
    total_dip_cm: float,
    water_dip_cm: float,
    obs_mode: str,            # "Observed API" or "Observed Density"
    api_observed: float,
    density_observed: float,
    tank_temp_value: float,
    tank_temp_unit: str,      # "°C" or "°F"
    sample_temp_value: float,
    sample_temp_unit: str,    # "°C" or "°F"
    bsw_pct: float,
    ccf: float = 1.0,
):
    # Step 1: TOV/FW via calibration (litres->bbl)
    total_l = _interp_tanker_volume_litres(session, tanker_name, total_dip_cm)
    water_l = _interp_tanker_volume_litres(session, tanker_name, water_dip_cm) if water_dip_cm > 0 else 0.0
    tov_bbl = total_l / LITRES_PER_BBL if total_l > 0 else 0.0
    fw_bbl  = water_l / LITRES_PER_BBL if water_l > 0 else 0.0

    # Step 2: GOV
    ccf_val = ccf if ccf else 1.0
    gov_bbl = max(tov_bbl - fw_bbl, 0.0) * ccf_val

    # Step 3: API60 + VCF
    api_obs = _afloat(api_observed)
    dens_obs = _afloat(density_observed)
    s_temp = _afloat(sample_temp_value)
    t_temp = _afloat(tank_temp_value)
    mode = (obs_mode or "").strip()

    if "API" in mode:
        api60 = api60_from_api_obs(api_obs, s_temp, sample_temp_unit)
        dens_at_obs = density_from_api(api_obs)
    else:
        api60 = api60_from_density_obs(dens_obs, s_temp, sample_temp_unit)
        dens_at_obs = dens_obs
        api_obs = api_from_density(dens_obs)

    api60 = round(api60, 2)
    vcf = round(vcf_from_api60_and_tank_temp(api60, t_temp, tank_temp_unit), 5)

    # Step 4..8
    gsv = round(gov_bbl * vcf, 0)
    bsw_bbl = round(gsv * (_afloat(bsw_pct) / 100.0), 0)
    nsv = round(gsv - bsw_bbl, 0)
    lt_factor = get_lt_factor(session, api60) if api60 > 0 else 0.0
    lt = round(nsv * lt_factor, 0)
    mt = round(lt * 1.01605, 0)

    return {
        "tov_bbl": round(tov_bbl, 2),
        "fw_bbl": round(fw_bbl, 2),
        "gov_bbl": round(gov_bbl, 2),
        "api_obs": round(api_obs, 2),
        "dens_obs": round(dens_at_obs, 2),
        "api60": api60,
        "vcf": vcf,
        "gsv_bbl": float(gsv),
        "bsw_bbl": float(bsw_bbl),
        "nsv_bbl": float(nsv),
        "lt": float(lt),
        "mt": float(mt),
        "ccf": float(ccf_val),
    }

# ========== PDF Builder (A4) ==========

def _build_tanker_pdf_bytes(row: TankerTransaction) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4

    # Header
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20*mm, H - 20*mm, "Tanker Dispatch Report")
    c.setFont("Helvetica", 9)
    c.drawString(20*mm, H - 26*mm, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Top details box
    y = H - 40*mm
    c.setLineWidth(0.5)
    c.rect(15*mm, y - 28*mm, W - 30*mm, 26*mm)
    left_x = 18*mm
    right_x = W / 2 + 5*mm

    c.setFont("Helvetica-Bold", 10)
    c.drawString(left_x, y - 6*mm,  "Tanker:")
    c.drawString(left_x, y - 12*mm, "Chassis No:")
    c.drawString(left_x, y - 18*mm, "Convoy No:")
    c.drawString(left_x, y - 24*mm, "Cargo:")

    c.drawString(right_x, y - 6*mm,  "Date:")
    c.drawString(right_x, y - 12*mm, "Time:")
    c.drawString(right_x, y - 18*mm, "Loading Bay:")
    c.drawString(right_x, y - 24*mm, "Destination:")

    c.setFont("Helvetica", 10)
    c.drawString(left_x + 30*mm, y - 6*mm,  str(row.tanker_name or "—"))
    c.drawString(left_x + 30*mm, y - 12*mm, str(row.chassis_no or "—"))
    c.drawString(left_x + 30*mm, y - 18*mm, str(row.convoy_no or "—"))
    c.drawString(left_x + 30*mm, y - 24*mm, str(row.cargo or "—"))

    c.drawString(right_x + 25*mm, y - 6*mm,  _fmt_date(getattr(row, "transaction_date", None)))
    c.drawString(right_x + 25*mm, y - 12*mm, _fmt_time(getattr(row, "transaction_time", None)))
    c.drawString(right_x + 25*mm, y - 18*mm, str(getattr(row, "loading_bay", "—") or "—"))
    c.drawString(right_x + 25*mm, y - 24*mm, str(getattr(row, "destination", "—") or "—"))

    # Quantity block
    y2 = y - 38*mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20*mm, y2, "Quantities (bbl)")
    c.line(20*mm, y2 - 2*mm, W - 20*mm, y2 - 2*mm)

    c.setFont("Helvetica", 10)
    labels = [
        ("TOV", getattr(row, "total_volume_bbl", 0)),
        ("FW",  getattr(row, "water_volume_bbl", 0)),
        ("GOV", getattr(row, "gov_bbl", 0)),
        ("API@60", getattr(row, "api60", 0)),
        ("VCF", getattr(row, "vcf", 0)),
        ("GSV", getattr(row, "gsv_bbl", 0)),
        ("BS&W", getattr(row, "bsw_vol_bbl", 0)),
        ("NSV", getattr(row, "nsv_bbl", 0)),
        ("LT",  getattr(row, "lt", 0)),
        ("MT",  getattr(row, "mt", 0)),
    ]
    gx = 22*mm
    gy = y2 - 8*mm
    step = 6.0*mm
    for i, (k, v) in enumerate(labels):
        nd = 2 if k in ("GOV", "API@60", "VCF") else 0
        c.drawString(gx, gy - i * step, f"{k}:  {_fmt_num(v, nd)}")

    # Seals simple grid (C1, C2, M1, M2)
    y3 = gy - len(labels) * step - 10*mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20*mm, y3, "Seal Details")
    c.line(20*mm, y3 - 2*mm, W - 20*mm, y3 - 2*mm)

    top = y3 - 8*mm
    left = 20*mm
    cols = [
        ("C1", getattr(row, "seal_c1", "") or "—"),
        ("C2", getattr(row, "seal_c2", "") or "—"),
        ("M1", getattr(row, "seal_m1", "") or "—"),
        ("M2", getattr(row, "seal_m2", "") or "—"),
    ]
    col_w = (W - 40*mm) / 4.0
    c.setFont("Helvetica-Bold", 9)
    for i, (hdr, _) in enumerate(cols):
        c.rect(left + i * col_w, top - 8*mm, col_w, 8*mm)
        c.drawCentredString(left + i * col_w + col_w / 2, top - 6*mm, hdr)
    c.setFont("Helvetica", 9)
    for i, (_, val) in enumerate(cols):
        c.rect(left + i * col_w, top - 16*mm, col_w, 8*mm)
        c.drawCentredString(left + i * col_w + col_w / 2, top - 14*mm, str(val))

    # Remarks
    y4 = top - 24*mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20*mm, y4, "Remarks")
    c.setFont("Helvetica", 9)
    c.rect(20*mm, y4 - 22*mm, W - 40*mm, 20*mm)
    txt = str(getattr(row, "remarks", "") or "")
    c.drawString(22*mm, y4 - 6*mm, txt[:120])
    if len(txt) > 120:
        c.drawString(22*mm, y4 - 12*mm, txt[120:240])

    c.showPage()
    c.save()
    return buf.getvalue()

def _open_pdf_blob_inline(pdf_bytes: bytes, filename: str = "tanker_report.pdf") -> None:
    b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    href = f'<a href="data:application/pdf;base64,{b64}" download="{filename}">📄 Download PDF</a>'
    st.markdown(href, unsafe_allow_html=True)

def _open_pdf_blob_new_tab(pdf_bytes: bytes) -> None:
    """Open a PDF blob in a new browser tab via JS (aligned with YADE helper)."""
    if not pdf_bytes:
        st.warning("No PDF generated.")
        return
    b64 = base64.b64encode(pdf_bytes).decode("ascii")
    components.html(
        f"""
        <script>
        (function(){{
            const bytes = atob("{b64}");
            const out = new Uint8Array(bytes.length);
            for (let i = 0; i < bytes.length; i++) {{
                out[i] = bytes.charCodeAt(i);
            }}
            const blob = new Blob([out], {{type: "application/pdf"}});
            const url = URL.createObjectURL(blob);
            const w = window.open(url, "_blank");
            if (!w) alert("Please allow pop-ups for OTMS to display the PDF.");
            setTimeout(() => URL.revokeObjectURL(url), 120000);
        }})();
        </script>
        """,
        height=0,
    )


# ========== Main Renderer ==========

def render_tanker_transactions_view(user: Dict[str, Any] | None = None, location_id: Optional[int] = None) -> None:
    st.subheader("Tanker — View Transactions")
    
    # Load custom tabs
    custom_tabs = []
    try:
        from location_config import get_custom_tabs
        if location_id:
            with get_session() as s:
                custom_tabs = get_custom_tabs(s, location_id, "tanker_transactions")
                custom_tabs = [t for t in custom_tabs if t.get("active", True)]
    except Exception:
        pass
    
    # Create tabs if custom tabs exist
    if custom_tabs:
        tab_labels = ["Tanker Dispatch"] + [t.get("name", "Custom") for t in custom_tabs]
        tabs = st.tabs(tab_labels)
        
        # Main tanker dispatch tab
        with tabs[0]:
            _render_main_tanker_view(user, location_id)
        
        # Custom tabs
        for idx, custom_tab in enumerate(custom_tabs, start=1):
            with tabs[idx]:
                _render_custom_tanker_tab_view(location_id, custom_tab, user)
    else:
        # No custom tabs, render normally
        _render_main_tanker_view(user, location_id)


def _render_main_tanker_view(user: Dict[str, Any] | None, location_id: Optional[int]) -> None:
    """Render main tanker transactions view"""
    # Load all (filter in Python to stay consistent with your current pattern)
    with get_session() as s:
        rows: List[TankerTransaction] = (
            s.query(TankerTransaction)
             .order_by(TankerTransaction.transaction_date.desc(),
                       TankerTransaction.transaction_time.desc(),
                       TankerTransaction.id.desc())
             .all()
        )
        if location_id:
            rows = [r for r in rows if int(getattr(r, "location_id", 0) or 0) == int(location_id)]

    if not rows:
        st.info("No tanker transactions found.")
        return

    # Filters (date defaults to latest date range)
    all_dates = [getattr(r, "transaction_date", None) for r in rows if getattr(r, "transaction_date", None)]
    min_date = min(all_dates) if all_dates else date.today()
    max_date = max(all_dates) if all_dates else date.today()

    all_tankers = sorted({r.tanker_name for r in rows if r.tanker_name})
    all_convoys = sorted({r.convoy_no for r in rows if r.convoy_no})
    all_creators = sorted({r.created_by for r in rows if r.created_by})

    f1, f2, f3, f4 = st.columns(4)
    with f1:
        filter_date = st.date_input("📅 Date", value=max_date, min_value=min_date, max_value=max_date,
                                    format="DD/MM/YYYY", key="tanker_filter_date")
    with f2:
        filter_tanker = st.selectbox("🚚 Tanker", ["All"] + all_tankers, key="tanker_filter_name")
    with f3:
        filter_convoy = st.selectbox("🚛 Convoy No", ["All"] + all_convoys, key="tanker_filter_convoy")
    with f4:
        filter_creator = st.selectbox("👤 Created By", ["All"] + all_creators, key="tanker_filter_creator")

    def _pass_filters(r: TankerTransaction) -> bool:
        ok = True
        if filter_date and isinstance(filter_date, date):
            ok = ok and (getattr(r, "transaction_date", None) == filter_date)
        if filter_tanker != "All":
            ok = ok and (r.tanker_name == filter_tanker)
        if filter_convoy != "All":
            ok = ok and (r.convoy_no == filter_convoy)
        if filter_creator != "All":
            ok = ok and (r.created_by == filter_creator)
        return ok

    rows = [r for r in rows if _pass_filters(r)]
    if not rows:
        st.warning("No matching records for the selected filters.")
        return

    # init state
    if "tanker_view_selected" not in st.session_state:
        st.session_state["tanker_view_selected"] = None
    if "tanker_view_edit" not in st.session_state:
        st.session_state["tanker_view_edit"] = False

    # header row + widths reused for alignment
    col_widths = [0.10, 0.08, 0.16, 0.10, 0.16, 0.08, 0.08, 0.12, 0.12]
    headers = ["Date", "Time", "Tanker", "Convoy", "Destination", "GOV", "NSV", "Created", "Actions"]
    header_align = ["left", "left", "left", "left", "left", "right", "right", "left", "center"]
    hcols = st.columns(col_widths)
    for col, label, align in zip(hcols, headers, header_align):
        col.markdown(
            f"<div style='font-weight:600;font-size:12px;padding:4px 0;text-align:{align};'>{label}</div>",
            unsafe_allow_html=True,
        )

    for r in rows:
        cols = st.columns(col_widths)
        with cols[0]:
            st.markdown(
                f"<div style='padding:4px 0;font-weight:600;'>{_fmt_date(r.transaction_date)}</div>",
                unsafe_allow_html=True,
            )
        with cols[1]:
            st.markdown(f"<div style='padding:4px 0;'>{_fmt_time(r.transaction_time)}</div>", unsafe_allow_html=True)
        with cols[2]:
            st.markdown(f"<div style='padding:4px 0;'>{escape(str(r.tanker_name or '—'))}</div>", unsafe_allow_html=True)
        with cols[3]:
            st.markdown(f"<div style='padding:4px 0;'>{escape(str(r.convoy_no or '—'))}</div>", unsafe_allow_html=True)
        with cols[4]:
            st.markdown(
                f"<div style='padding:4px 0;'>{escape(str(getattr(r, 'destination', '') or '—'))}</div>",
                unsafe_allow_html=True,
            )
        with cols[5]:
            st.markdown(
                f"<div style='padding:4px 0;text-align:right;'>{_fmt_num(getattr(r, 'gov_bbl', 0), 0)}</div>",
                unsafe_allow_html=True,
            )
        with cols[6]:
            st.markdown(
                f"<div style='padding:4px 0;text-align:right;'>{_fmt_num(getattr(r, 'nsv_bbl', 0), 0)}</div>",
                unsafe_allow_html=True,
            )
        with cols[7]:
            st.markdown(f"<div style='padding:4px 0;'>{escape(str(r.created_by or 'system'))}</div>", unsafe_allow_html=True)
        with cols[8]:
            a1, a2, a3 = st.columns([1,1,1])
            with a1:
                if st.button("🔍", key=f"tview_{r.id}", help="View / Edit"):
                    st.session_state["tanker_view_selected"] = r.id
                    st.session_state["tanker_view_edit"] = False
                    try:
                        SecurityManager.log_audit(
                            None, (user or {}).get("username","system"), "VIEW",
                            resource_type="TankerTransaction", resource_id=str(r.id),
                            details="View tanker transaction", user_id=(user or {}).get("id"),
                            location_id=location_id, success=True)
                    except Exception:
                        pass
                    st.rerun()
            with a2:
                # Delete button triggers deletion UI
                if st.button("🗑️", key=f"tdel_{r.id}", help="Delete"):
                    st.session_state[f"tanker_show_delete_ui_{r.id}"] = True
            with a3:
                if st.button("🧾", key=f"tpdf_{r.id}", help="Open PDF"):
                    try:
                        pdf_bytes = _build_tanker_pdf_bytes_conventional(r)
                        _open_pdf_blob_new_tab(pdf_bytes)
                        SecurityManager.log_audit(
                            None, (user or {}).get("username","system"), "EXPORT",
                            resource_type="TankerTransaction", resource_id=str(r.id),
                            details="Open tanker PDF", user_id=(user or {}).get("id"),
                            location_id=location_id, success=True)
                    except Exception as ex:
                        SecurityManager.log_audit(
                            None, (user or {}).get("username","system"), "EXPORT",
                            resource_type="TankerTransaction", resource_id=str(r.id),
                            details=f"PDF error: {ex}", user_id=(user or {}).get("id"),
                            location_id=location_id, success=False)
                        st.error(f"PDF generation failed: {ex}")
        
        # Deletion approval UI
        if st.session_state.get(f"tanker_show_delete_ui_{r.id}"):
            def delete_tanker_record():
                _delete_tanker_transaction(r.id, user or {})
            
            deletion_result = render_deletion_ui(
                resource_type="TankerTransaction",
                resource_id=r.id,
                resource_label=f"Tanker Transaction {r.tanker_name or r.id}",
                delete_func=delete_tanker_record,
                user=user,
                location_id=location_id,
                on_success_message="Tanker transaction deleted successfully",
                metadata={"tanker_name": r.tanker_name, "date": str(getattr(r, 'transaction_date', ''))},
                button_key_prefix=f"tanker_{r.id}"
            )
            
            # Close the prompt on any button click (delete success, cancel, or error)
            if deletion_result is not None:
                st.session_state.pop(f"tanker_show_delete_ui_{r.id}", None)
                st.rerun()

    # detail panel
    current_id = st.session_state.get("tanker_view_selected")
    if not current_id:
        return

    tx = next((row for row in rows if row.id == current_id), None)
    if not tx:
        st.warning("Selected record not found.")
        return

    st.markdown("---")
    st.markdown(f"### View: {tx.tanker_name or 'Tanker'} — {_fmt_date(getattr(tx, 'transaction_date', None))} {_fmt_time(getattr(tx, 'transaction_time', None))}")

    # === top action bar (icon-only) ===
    left, right = st.columns([0.8, 0.2])
    editing = bool(st.session_state.get("tanker_view_edit"))

    with left:
        if not editing:
            b1, b2, b3 = st.columns([0.08, 0.08, 0.08])
            with b1:
                if st.button("✏️", key=f"tv_edit_{tx.id}", help="Edit"):
                    st.session_state["tanker_view_edit"] = True
                    st.rerun()
            with b2:
                if st.button("🧾", key=f"tv_pdf_{tx.id}", help="Open PDF"):
                    pdf_bytes = _build_tanker_pdf_bytes_conventional(tx)
                    _open_pdf_blob_new_tab(pdf_bytes)
            with b3:
                pass  # room for future actions
        else:
            b1, b2 = st.columns([0.08, 0.08])
            with b1:
                if st.button("💾", key=f"tv_save_{tx.id}", help="Save changes"):
                    try:
                        with get_session() as s:
                            row = s.query(TankerTransaction).filter(TankerTransaction.id == tx.id).one()

                            # 1) write editable text fields
                            row.tanker_name = st.session_state.get("edit_tanker_name", row.tanker_name)
                            row.convoy_no   = st.session_state.get("edit_convoy_no", row.convoy_no)
                            row.cargo       = st.session_state.get("edit_cargo", row.cargo)
                            row.chassis_no  = st.session_state.get("edit_chassis_no", row.chassis_no)
                            row.destination = st.session_state.get("edit_destination", getattr(row, "destination", None))
                            row.loading_bay = st.session_state.get("edit_loading_bay", getattr(row, "loading_bay", None))
                            row.compartment = st.session_state.get("edit_compartment", getattr(row, "compartment", None))
                            row.manhole     = st.session_state.get("edit_manhole", getattr(row, "manhole", None))

                            # 2) dips & factor
                            row.total_dip_cm = float(st.session_state.get("edit_total_dip_cm", getattr(row, "total_dip_cm", 0.0)) or 0.0)
                            row.water_dip_cm = float(st.session_state.get("edit_water_dip_cm", getattr(row, "water_dip_cm", 0.0)) or 0.0)
                            row.total_dip_mm = round(row.total_dip_cm * 10.0, 1)
                            row.water_dip_mm = round(row.water_dip_cm * 10.0, 1)
                            row.ccf = float(st.session_state.get("edit_ccf", getattr(row, "ccf", 1.0)) or 1.0)

                            # 3) sample params (units + mode like entry page)
                            obs_mode = st.session_state.get("edit_obs_mode", "Observed API")
                            tank_temp_unit = normalize_temp_unit(st.session_state.get("edit_tank_temp_unit", "°C"))
                            sample_temp_unit = normalize_temp_unit(st.session_state.get("edit_sample_temp_unit", "°C"))
                            tank_temp_value = float(st.session_state.get("edit_tank_temp", getattr(row, "tank_temp_c", 0.0)) or 0.0)
                            sample_temp_value = float(st.session_state.get("edit_sample_temp", getattr(row, "sample_temp_c", 0.0)) or 0.0)

                            api_observed = float(st.session_state.get("edit_api_observed", getattr(row, "api_observed", 0.0)) or 0.0)
                            density_observed = float(st.session_state.get("edit_density_observed", getattr(row, "density_observed", 0.0)) or 0.0)
                            bsw_pct = float(st.session_state.get("edit_bsw_pct", getattr(row, "bsw_pct", 0.0) if hasattr(row, "bsw_pct") else 0.0) or 0.0)

                            # 4) recompute (same math path as entry page)
                            if obs_mode == "Observed API":
                                api60 = api60_from_api_obs(api_observed, sample_temp_value, sample_temp_unit)
                                api_obs_final = api_observed
                                dens_obs_final = density_from_api(api_observed)
                            else:
                                api60 = api60_from_density_obs(density_observed, sample_temp_value, sample_temp_unit)
                                api_obs_final = api_from_density(density_observed)
                                dens_obs_final = density_observed

                            api60 = round(api60, 2)
                            vcf = round(vcf_from_api60_and_tank_temp(api60, tank_temp_value, tank_temp_unit), 5)

                            # TOV/FW from calibration (litres -> bbl)
                            # Reuse your tanker calibration interpolation (same logic as entry)
                            # We only need tanker_name + dips; TankerCalibration already used in entry
                            # For simplicity, call the same helper you used in entry or re-implement minimal lookup
                            # (here we re-use your own save-time logic: GOV=(TOV-FW)*CCF)
                            # If you have a shared helper, swap this block for it.
                            from sqlalchemy import asc
                            rows_cal = (
                                s.query(TankerCalibration)
                                .filter(TankerCalibration.tanker_name == row.tanker_name)
                                .order_by(asc(TankerCalibration.dip_mm))
                                .all()
                            )
                            def _interp_mm_to_l(mm: float) -> float:
                                if not rows_cal or mm <= 0:
                                    return 0.0
                                xs = [float(getattr(k, "dip_mm", 0.0) or 0.0) for k in rows_cal]
                                ys = [float(getattr(k, "volume_litres", 0.0) or 0.0) for k in rows_cal]
                                import bisect
                                if mm <= xs[0]: return ys[0]
                                if mm >= xs[-1]: return ys[-1]
                                i = bisect.bisect_left(xs, mm)
                                x1,y1 = xs[i-1], ys[i-1]
                                x2,y2 = xs[i], ys[i]
                                if x2 == x1: return y1
                                t = (mm - x1)/(x2 - x1)
                                return y1 + t*(y2 - y1)

                            total_l = _interp_mm_to_l(row.total_dip_mm)
                            water_l = _interp_mm_to_l(row.water_dip_mm)
                            tov_bbl = (total_l / 158.987) if total_l > 0 else 0.0
                            fw_bbl  = (water_l / 158.987) if water_l > 0 else 0.0
                            gov_bbl = max(tov_bbl - fw_bbl, 0.0) * (row.ccf or 1.0)
                            gsv_bbl = round(gov_bbl * vcf, 0)
                            bsw_bbl = round(gsv_bbl * (bsw_pct/100.0), 0)
                            nsv_bbl = round(gsv_bbl - bsw_bbl, 0)
                            lt_factor = get_lt_factor(s, api60) if api60 > 0 else 0.0
                            lt = round(nsv_bbl * (lt_factor or 0.0), 0)
                            mt = round(lt * 1.01605, 0)

                            # 5) store back
                            row.api_observed = round(api_obs_final, 2)
                            row.density_observed = round(dens_obs_final, 2)
                            row.api60 = api60
                            row.vcf = vcf
                            row.tank_temp_c = tank_temp_value if tank_temp_unit == "°C" else ( (tank_temp_value - 32.0) * 5.0/9.0 )
                            row.sample_temp_c = sample_temp_value if sample_temp_unit == "°C" else ( (sample_temp_value - 32.0) * 5.0/9.0 )

                            row.total_volume_bbl = round(tov_bbl, 2)
                            row.water_volume_bbl = round(fw_bbl, 2)
                            row.gov_bbl = round(gov_bbl, 2)
                            row.gsv_bbl = float(gsv_bbl)
                            row.bsw_vol_bbl = float(bsw_bbl)
                            row.nsv_bbl = float(nsv_bbl)
                            row.lt = float(lt)
                            row.mt = float(mt)

                            if hasattr(row, "bsw_pct"):
                                row.bsw_pct = bsw_pct

                            # seals + remarks
                            row.seal_c1 = st.session_state.get("edit_seal_c1", row.seal_c1)
                            row.seal_c2 = st.session_state.get("edit_seal_c2", row.seal_c2)
                            row.seal_m1 = st.session_state.get("edit_seal_m1", row.seal_m1)
                            row.seal_m2 = st.session_state.get("edit_seal_m2", row.seal_m2)
                            row.remarks = st.session_state.get("edit_remarks", row.remarks)

                            s.commit()

                        st.success("Saved and recomputed.")
                        st.session_state["tanker_view_edit"] = False
                        st.rerun()
                    except Exception as ex:
                        st.error(f"Save failed: {ex}")


            with b2:
                if st.button("✖️", key=f"tv_cancel_{tx.id}", help="Cancel edit"):
                    st.session_state["tanker_view_edit"] = False
                    st.rerun()

    with right:
        if st.button("⬅️", key=f"tv_close_{tx.id}", help="Close"):
            st.session_state.pop("tanker_view_selected", None)
            st.session_state.pop("tanker_view_edit", None)
            st.rerun()

    # details
    _render_tanker_detail_compact(tx, allow_edit=editing)

def _render_tanker_detail_compact(r: TankerTransaction, allow_edit: bool = False) -> None:
    st.markdown('<div style="font-size:13px">', unsafe_allow_html=True)

    # ----- BASIC INFO (editable) -----
    c1, c2, c3, c4 = st.columns([0.23, 0.23, 0.23, 0.31])
    if allow_edit:
        st.session_state.setdefault("edit_tanker_name", r.tanker_name or "")
        st.session_state.setdefault("edit_convoy_no", r.convoy_no or "")
        st.session_state.setdefault("edit_cargo", r.cargo or "")
        st.session_state.setdefault("edit_chassis_no", r.chassis_no or "")
        st.session_state.setdefault("edit_destination", getattr(r, "destination", "") or "")
        st.session_state.setdefault("edit_loading_bay", getattr(r, "loading_bay", "") or "")
        st.session_state.setdefault("edit_compartment", getattr(r, "compartment", "") or "")
        st.session_state.setdefault("edit_manhole", getattr(r, "manhole", "") or "")

        with c1:
            st.text_input("Tanker", key="edit_tanker_name")
            st.text_input("Convoy", key="edit_convoy_no")
        with c2:
            st.text_input("Cargo", key="edit_cargo")
            st.text_input("Chassis", key="edit_chassis_no")
        with c3:
            st.text_input("Destination", key="edit_destination")
            st.text_input("Loading Bay", key="edit_loading_bay")
        with c4:
            st.text_input("Compartment", key="edit_compartment")
            st.text_input("Manhole", key="edit_manhole")
    else:
        with c1:
            st.write(f"**Tanker:** {r.tanker_name or '—'}")
            st.write(f"**Convoy:** {r.convoy_no or '—'}")
        with c2:
            st.write(f"**Cargo:** {r.cargo or '—'}")
            st.write(f"**Chassis:** {r.chassis_no or '—'}")
        with c3:
            st.write(f"**Destination:** {getattr(r, 'destination', '—') or '—'}")
            st.write(f"**Loading Bay:** {getattr(r, 'loading_bay', '—') or '—'}")
        with c4:
            st.write(f"**Compartment:** {getattr(r, 'compartment', '—') or '—'}")
            st.write(f"**Manhole:** {getattr(r, 'manhole', '—') or '—'}")

    st.markdown("---")

    # ----- DIPS + FACTORS (editable) -----
    d1, d2, d3, d4 = st.columns([0.20, 0.20, 0.20, 0.40])
    if allow_edit:
        st.session_state.setdefault("edit_total_dip_cm", getattr(r, "total_dip_cm", 0.0) or 0.0)
        st.session_state.setdefault("edit_water_dip_cm", getattr(r, "water_dip_cm", 0.0) or 0.0)
        st.session_state.setdefault("edit_ccf", getattr(r, "ccf", 1.0) or 1.0)
        with d1:
            st.number_input("Total Dip (cm)", key="edit_total_dip_cm", min_value=0.0, step=0.1, format="%.2f")
            st.number_input("Water Dip (cm)", key="edit_water_dip_cm", min_value=0.0, step=0.1, format="%.2f")
        with d2:
            st.number_input("CCF", key="edit_ccf", min_value=0.0, step=0.0001, format="%.4f")
            st.caption("TOV/FW will be looked up from calibration on Save.")
        with d3:
            st.write(f"**Date:** {_fmt_date(getattr(r, 'transaction_date', None))}")
            st.write(f"**Time:** {_fmt_time(getattr(r, 'transaction_time', None))}")
        with d4:
            st.caption("Unit-consistent, recomputed on Save.")
    else:
        with d1:
            st.write(f"**Total Dip (cm):** {_fmt_num(getattr(r, 'total_dip_cm', 0), 2)}")
            st.write(f"**Water Dip (cm):** {_fmt_num(getattr(r, 'water_dip_cm', 0), 2)}")
        with d2:
            st.write(f"**Total Dip (mm):** {_fmt_num(getattr(r, 'total_dip_mm', 0), 1)}")
            st.write(f"**Water Dip (mm):** {_fmt_num(getattr(r, 'water_dip_mm', 0), 1)}")
        with d3:
            st.write(f"**CCF:** {_fmt_num(getattr(r, 'ccf', 1.0), 4)}")
        with d4:
            st.write(f"**Date:** {_fmt_date(getattr(r, 'transaction_date', None))} • **Time:** {_fmt_time(getattr(r, 'transaction_time', None))}")

    st.markdown("---")

    # ----- SAMPLE PARAMETERS (entry-style dynamic UI) -----
    s1, s2, s3, s4 = st.columns([0.22, 0.22, 0.22, 0.34])
    if allow_edit:
        # defaults and state
        default_mode = "Observed API"
        if (getattr(r, "density_observed", None) or 0) > 0 and (getattr(r, "api_observed", 0) or 0) == 0:
            default_mode = "Observed Density"
        st.session_state.setdefault("edit_obs_mode", default_mode)

        st.session_state.setdefault("edit_tank_temp_unit", "°C")
        st.session_state.setdefault("edit_sample_temp_unit", "°C")
        st.session_state.setdefault("edit_tank_temp", getattr(r, "tank_temp_c", 0.0) or 0.0)
        st.session_state.setdefault("edit_sample_temp", getattr(r, "sample_temp_c", 0.0) or 0.0)
        st.session_state.setdefault("edit_api_observed", getattr(r, "api_observed", 0.0) or 0.0)
        st.session_state.setdefault("edit_density_observed", getattr(r, "density_observed", 0.0) or 0.0)
        st.session_state.setdefault("edit_bsw_pct", getattr(r, "bsw_pct", 0.0) if hasattr(r, "bsw_pct") else 0.0)

        # units + bounds
        with s1:
            tank_unit = st.selectbox(
                "Tank Temp Unit",
                ["°C", "°F"],
                index=0 if st.session_state["edit_tank_temp_unit"] == "°C" else 1,
                key="edit_tank_temp_unit",
            )
            lo, hi = temp_bounds(tank_unit)
            st.number_input("Tank Temperature", min_value=lo, max_value=hi, step=0.1, key="edit_tank_temp")
        with s2:
            sample_unit = st.selectbox(
                "Sample Temp Unit",
                ["°C", "°F"],
                index=0 if st.session_state["edit_sample_temp_unit"] == "°C" else 1,
                key="edit_sample_temp_unit",
            )
            slo, shi = temp_bounds(sample_unit)
            st.number_input("Sample Temperature", min_value=slo, max_value=shi, step=0.1, key="edit_sample_temp")
        with s3:
            st.radio("Mode", ["Observed API", "Observed Density"], key="edit_obs_mode", horizontal=True)
            if st.session_state["edit_obs_mode"] == "Observed API":
                st.number_input("Observed API *",
                                min_value=API_LIMITS[0], max_value=API_LIMITS[1], step=0.1,
                                key="edit_api_observed")
            else:
                st.number_input("Observed Density (kg/m³) *",
                                min_value=DENSITY_LIMITS[0], max_value=DENSITY_LIMITS[1], step=0.1,
                                key="edit_density_observed")
        with s4:
            st.number_input("BS&W %", min_value=0.0, max_value=100.0, step=0.01, key="edit_bsw_pct")
            # live hint like entry page (no DB write here)
            try:
                if st.session_state["edit_obs_mode"] == "Observed API":
                    _api60 = api60_from_api_obs(
                        float(st.session_state["edit_api_observed"] or 0.0),
                        float(st.session_state["edit_sample_temp"] or 0.0),
                        st.session_state["edit_sample_temp_unit"],
                    )
                    _dens = density_from_api(float(st.session_state["edit_api_observed"] or 0.0))
                    st.caption(f"→ API @ 60°F: **{_api60:.2f}**   |   ↔ Density (approx): **{_dens:.1f} kg/m³**")
                else:
                    _api60 = api60_from_density_obs(
                        float(st.session_state["edit_density_observed"] or 0.0),
                        float(st.session_state["edit_sample_temp"] or 0.0),
                        st.session_state["edit_sample_temp_unit"],
                    )
                    _api_obs = api_from_density(float(st.session_state["edit_density_observed"] or 0.0))
                    st.caption(f"→ API @ 60°F: **{_api60:.2f}**   |   ↔ Observed API (approx): **{_api_obs:.2f}**")
            except Exception:
                pass
    else:
        with s1:
            st.write(f"**Obs. API:** {_fmt_num(getattr(r, 'api_observed', 0), 2)}")
            st.write(f"**API @ 60°F:** {_fmt_num(getattr(r, 'api60', 0), 2)}")
        with s2:
            st.write(f"**Obs. Density:** {_fmt_num(getattr(r, 'density_observed', 0), 2)}")
            st.write(f"**VCF:** {_fmt_num(getattr(r, 'vcf', 0), 5)}")
        with s3:
            st.write(f"**Tank Temp (°C):** {_fmt_num(getattr(r, 'tank_temp_c', 0), 1)}")
            st.write(f"**Sample Temp (°C):** {_fmt_num(getattr(r, 'sample_temp_c', 0), 1)}")
        with s4:
            st.write(f"**GOV:** {_fmt_num(getattr(r, 'gov_bbl', 0), 0)}  •  "
                     f"**GSV:** {_fmt_num(getattr(r, 'gsv_bbl', 0), 0)}  •  "
                     f"**NSV:** {_fmt_num(getattr(r, 'nsv_bbl', 0), 0)}  •  "
                     f"**BSW:** {_fmt_num(getattr(r, 'bsw_vol_bbl', 0), 0)}")

    st.markdown("---")

    # ----- SEALS + REMARKS (editable) -----
    st.markdown("**Seals**")
    z1, z2, z3, z4 = st.columns(4)
    if allow_edit:
        st.session_state.setdefault("edit_seal_c1", getattr(r, "seal_c1", "") or "")
        st.session_state.setdefault("edit_seal_c2", getattr(r, "seal_c2", "") or "")
        st.session_state.setdefault("edit_seal_m1", getattr(r, "seal_m1", "") or "")
        st.session_state.setdefault("edit_seal_m2", getattr(r, "seal_m2", "") or "")
        z1.text_input("C1", key="edit_seal_c1", label_visibility="collapsed", placeholder="C1 Seal")
        z2.text_input("C2", key="edit_seal_c2", label_visibility="collapsed", placeholder="C2 Seal")
        z3.text_input("M1", key="edit_seal_m1", label_visibility="collapsed", placeholder="M1 Seal")
        z4.text_input("M2", key="edit_seal_m2", label_visibility="collapsed", placeholder="M2 Seal")
        st.session_state.setdefault("edit_remarks", getattr(r, "remarks", "") or "")
        st.text_area("Remarks", key="edit_remarks", height=80)
    else:
        z1.caption(f"C1: {getattr(r, 'seal_c1', '') or 'N/A'}")
        z2.caption(f"C2: {getattr(r, 'seal_c2', '') or 'N/A'}")
        z3.caption(f"M1: {getattr(r, 'seal_m1', '') or 'N/A'}")
        z4.caption(f"M2: {getattr(r, 'seal_m2', '') or 'N/A'}")
        if getattr(r, "remarks", None):
            st.markdown("**Remarks**")
            st.info(r.remarks)

    st.markdown('</div>', unsafe_allow_html=True)

def _build_tanker_pdf_bytes_conventional(row: TankerTransaction) -> bytes:
    """
    Conventional A4 layout (TOA-style):
      - Header bar with title
      - Top details grid
      - Dip readings box (cm & mm)
      - Quantity table (TOV, FW, GOV, API@60, VCF, GSV, BSW, NSV, LT, MT)
      - Seals grid (C1, C2, M1, M2)
      - Remarks box
    """
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    LM, RM, TM, BM = 15*mm, 15*mm, 15*mm, 15*mm
    x = LM
    y = H - TM

    # ===== Header bar =====
    bar_h = 20*mm
    c.setFillColor(colors.HexColor("#0B3D91"))  # dark blue header
    c.rect(LM, y - bar_h, W - LM - RM, bar_h, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(LM + (W - LM - RM)/2, y - 7*mm, "TANKER DISPATCH REPORT")
    c.setFont("Helvetica", 9)
    c.drawRightString(W - RM - 4*mm, y - 14*mm, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    y = y - bar_h - 6*mm

    # ===== Top details grid =====
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)

    def _grid_row(x, y, w, h, items, cols):
        """Draw a single row grid with 'cols' columns (label:value repeating)."""
        cw = w / cols
        c.rect(x, y - h, w, h, stroke=1, fill=0)
        for i in range(cols):
            c.line(x + i*cw, y, x + i*cw, y - h)
        # draw text
        ty = y - 6*mm
        for i, (lab, val) in enumerate(items[:cols]):
            cell_x = x + i * cw
            label_txt = f"{lab} :"
            c.setFont("Helvetica-Bold", 9)
            c.drawString(cell_x + 2*mm, ty, label_txt)
            label_w = c.stringWidth(label_txt, "Helvetica-Bold", 9)
            c.setFont("Helvetica", 9)
            c.drawString(cell_x + 2*mm + label_w + 2*mm, ty, str(val))

    # two rows of info (3 cells per row)
    row_h = 10*mm
    _grid_row(LM, y, W - LM - RM, row_h,
              [("Tanker", row.tanker_name or "—"),
               ("Convoy", row.convoy_no or "—"),
               ("Cargo",  row.cargo or "—")],
              cols=3)
    y -= (row_h + 3*mm)
    _grid_row(LM, y, W - LM - RM, row_h,
              [("Date", _fmt_date(getattr(row, "transaction_date", None))),
               ("Time", _fmt_time(getattr(row, "transaction_time", None))),
               ("Chassis", row.chassis_no or "—")],
              cols=3)
    y -= (row_h + 3*mm)
    _grid_row(LM, y, W - LM - RM, row_h,
              [("Destination", getattr(row, "destination", "—") or "—"),
               ("Loading Bay", getattr(row, "loading_bay", "—") or "—"),
               ("Comp/MH", f"{getattr(row,'compartment','—')}/{getattr(row,'manhole','—')}")],
              cols=3)
    y -= (row_h + 8*mm)

    # ===== Dip readings (cm/mm) =====
    c.setFont("Helvetica-Bold", 10)
    c.drawString(LM, y, "Dip Readings")
    y -= 6*mm
    box_h = 14*mm
    c.setFont("Helvetica", 9)
    c.rect(LM, y - box_h, W - LM - RM, box_h, stroke=1, fill=0)

    td_cm = getattr(row, "total_dip_cm", 0) or 0
    wd_cm = getattr(row, "water_dip_cm", 0) or 0
    td_mm = getattr(row, "total_dip_mm", 0) or 0
    wd_mm = getattr(row, "water_dip_mm", 0) or 0

    line1 = f"Total Dip: {_fmt_num(td_cm, 2)} cm    •    Water Dip: {_fmt_num(wd_cm, 2)} cm"
    line2 = f"Total Dip: {_fmt_num(td_mm, 1)} mm    •    Water Dip: {_fmt_num(wd_mm, 1)} mm"
    c.drawString(LM + 4*mm, y - 5*mm, line1)
    c.drawString(LM + 4*mm, y - 11*mm, line2)
    y -= (box_h + 8*mm)

    # ===== Quantities table =====
    c.setFont("Helvetica-Bold", 10)
    c.drawString(LM, y, "Quantities")
    y -= 6*mm

    def _qty_row(y, items):
        # items: list of (label, value, ndp)
        col_w = (W - LM - RM) / 3.0
        h = 12*mm
        c.rect(LM, y - h, W - LM - RM, h, stroke=1, fill=0)
        for i in range(1, 3):
            c.line(LM + i*col_w, y, LM + i*col_w, y - h)
        for i, (lab, val, nd) in enumerate(items):
            c.setFont("Helvetica-Bold", 9)
            c.drawString(LM + i*col_w + 2*mm, y - 4*mm, lab)
            c.setFont("Helvetica", 10)
            c.drawString(LM + i*col_w + 2*mm, y - 9*mm, _fmt_num(val, nd))
        return y - (h + 3*mm)

    tov = getattr(row, "total_volume_bbl", 0) or 0
    fw  = getattr(row, "water_volume_bbl", 0) or 0
    gov = getattr(row, "gov_bbl", 0) or 0
    api60 = getattr(row, "api60", 0) or 0
    vcf = getattr(row, "vcf", 0) or 0
    gsv = getattr(row, "gsv_bbl", 0) or 0
    bswv = getattr(row, "bsw_vol_bbl", 0) or 0
    nsv = getattr(row, "nsv_bbl", 0) or 0
    lt = getattr(row, "lt", 0) or 0
    mt = getattr(row, "mt", 0) or 0

    y = _qty_row(y, [("TOV (bbl)", tov, 0), ("FW (bbl)", fw, 0), ("GOV (bbl)", gov, 0)])
    y = _qty_row(y, [("API @ 60", api60, 2), ("VCF", vcf, 5), ("GSV (bbl)", gsv, 0)])
    y = _qty_row(y, [("BS&W (bbl)", bswv, 0), ("NSV (bbl)", nsv, 0), ("LT", lt, 0)])
    y = _qty_row(y, [("MT", mt, 0), ("", "", 0), ("", "", 0)])

    y -= 2*mm

    # ===== Seals grid =====
    c.setFont("Helvetica-Bold", 10)
    c.drawString(LM, y, "Seal Details")
    y -= 6*mm
    cell_h = 10*mm
    labels = [("C1", getattr(row, "seal_c1", "") or "—"),
              ("C2", getattr(row, "seal_c2", "") or "—"),
              ("M1", getattr(row, "seal_m1", "") or "—"),
              ("M2", getattr(row, "seal_m2", "") or "—")]
    col_w = (W - LM - RM) / 4.0
    # header row
    c.rect(LM, y - cell_h, W - LM - RM, cell_h, stroke=1, fill=0)
    for i in range(1, 4):
        c.line(LM + i*col_w, y, LM + i*col_w, y - cell_h)
    for i, (lab, _) in enumerate(labels):
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(LM + i*col_w + col_w/2, y - 6*mm, lab)
    y -= (cell_h)
    # value row
    c.rect(LM, y - cell_h, W - LM - RM, cell_h, stroke=1, fill=0)
    for i in range(1, 4):
        c.line(LM + i*col_w, y, LM + i*col_w, y - cell_h)
    for i, (_, val) in enumerate(labels):
        c.setFont("Helvetica", 9)
        c.drawCentredString(LM + i*col_w + col_w/2, y - 6*mm, str(val))
    y -= (cell_h + 6*mm)

    # ===== Remarks =====
    c.setFont("Helvetica-Bold", 10)
    c.drawString(LM, y, "Remarks")
    y -= 6*mm
    rem_h = 24*mm
    c.rect(LM, y - rem_h, W - LM - RM, rem_h, stroke=1, fill=0)
    txt = str(getattr(row, "remarks", "") or "")
    c.setFont("Helvetica", 9)
    # simple wrap
    max_chars = 95
    lines = [txt[i:i+max_chars] for i in range(0, len(txt), max_chars)] if txt else []
    ty = y - 6*mm
    for ln in lines[:4]:
        c.drawString(LM + 3*mm, ty, ln)
        ty -= 5*mm

    # ===== Authorized signatory =====
    bottom_of_remarks = y - rem_h
    sig_h = 22*mm
    gap = 6*mm
    sig_y = max(BM, bottom_of_remarks - gap - sig_h)
    c.rect(LM, sig_y, W - LM - RM, sig_h, stroke=1, fill=0)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(LM + 3*mm, sig_y + sig_h - 6*mm, "Authorized Signatory")
    c.setFont("Helvetica", 9)
    c.drawString(LM + 3*mm, sig_y + 6*mm, "For SEEPCO")
    c.drawRightString(W - RM - 3*mm, sig_y + 6*mm, "For Tanker Representative")

    c.showPage()
    c.save()
    return buf.getvalue()

def _render_tanker_detail_view(tx: TankerTransaction, user: Dict[str, Any], location_id: Optional[int]) -> None:
    """Display transaction details with Close/Edit buttons - matches tank transactions style"""
    st.markdown(f"#### Transaction #{tx.id} - {tx.tanker_name}")
    
    # Basic Info
    info_col1, info_col2, info_col3 = st.columns(3)
    with info_col1:
        st.metric("Convoy", tx.convoy_no)
        st.metric("Cargo", tx.cargo)
        st.metric("Destination", getattr(tx, "destination", "") or "N/A")
    with info_col2:
        st.metric("Date", _fmt_date(getattr(tx, "transaction_date", None)))
        st.metric("Time", _fmt_time(getattr(tx, "transaction_time", None)))
        st.metric("Loading Bay", getattr(tx, "loading_bay", "") or "N/A")
    with info_col3:
        st.metric("Compartment", f"{getattr(tx, 'compartment', 'N/A')} via {getattr(tx, 'manhole', 'N/A')}")
        st.metric("Chassis No", tx.chassis_no or "N/A")
        st.metric("Created By", tx.created_by or "system")

    # Dip Readings
    st.markdown("##### Dip Readings")
    dip_c1, dip_c2 = st.columns(2)
    with dip_c1:
        st.metric("Total Dip (cm)", _fmt_num(getattr(tx, "total_dip_cm", 0), 2))
        st.metric("Total Dip (mm)", _fmt_num(getattr(tx, "total_dip_mm", 0), 2))
    with dip_c2:
        st.metric("Water Dip (cm)", _fmt_num(getattr(tx, "water_dip_cm", 0), 2))
        st.metric("Water Dip (mm)", _fmt_num(getattr(tx, "water_dip_mm", 0), 2))

    # Temperatures
    st.markdown("##### Temperatures")
    temp_c1, temp_c2 = st.columns(2)
    with temp_c1:
        st.metric("Tank Temp (C)", _fmt_num(getattr(tx, "tank_temp_c", 0), 2))
        st.metric("Tank Temp (F)", _fmt_num(getattr(tx, "tank_temp_f", 0), 2))
    with temp_c2:
        st.metric("Sample Temp (C)", _fmt_num(getattr(tx, "sample_temp_c", 0), 2))
        st.metric("Sample Temp (F)", _fmt_num(getattr(tx, "sample_temp_f", 0), 2))

    # Volumes
    st.markdown("##### Volumes")
    vol_c1, vol_c2, vol_c3 = st.columns(3)
    with vol_c1:
        st.metric("Total Volume", f"{_fmt_num(getattr(tx, 'total_volume_bbl', 0), 0)} bbl")
        st.metric("Water Volume", f"{_fmt_num(getattr(tx, 'water_volume_bbl', 0), 0)} bbl")
    with vol_c2:
        st.metric("GOV", f"{_fmt_num(getattr(tx, 'gov_bbl', 0), 0)} bbl")
        st.metric("GSV", f"{_fmt_num(getattr(tx, 'gsv_bbl', 0), 0)} bbl")
    with vol_c3:
        st.metric("NSV", f"{_fmt_num(getattr(tx, 'nsv_bbl', 0), 0)} bbl")
        st.metric("BSW Volume", f"{_fmt_num(getattr(tx, 'bsw_vol_bbl', 0), 0)} bbl")

    # Quality
    st.markdown("##### Quality")
    q_c1, q_c2, q_c3 = st.columns(3)
    with q_c1:
        st.metric("Observed API", _fmt_num(getattr(tx, "api_observed", 0), 2))
    with q_c2:
        st.metric("Observed Density", _fmt_num(getattr(tx, "density_observed", 0), 4))
    with q_c3:
        st.metric("API @60", _fmt_num(getattr(tx, "api60", 0), 2))
        st.metric("VCF", _fmt_num(getattr(tx, "vcf", 0), 5))

    # Conversion Factors
    st.markdown("##### Conversion Factors")
    cf_c1, cf_c2 = st.columns(2)
    with cf_c1:
        st.metric("LT Factor", _fmt_num(getattr(tx, "lt", 0), 2))
    with cf_c2:
        st.metric("MT", _fmt_num(getattr(tx, "mt", 0), 2))

    # Seal Numbers
    st.markdown("##### Seal Numbers")
    seal_c1, seal_c2, seal_c3, seal_c4 = st.columns(4)
    seal_c1.caption(f"C1: {getattr(tx, 'seal_c1', '') or 'N/A'}")
    seal_c2.caption(f"C2: {getattr(tx, 'seal_c2', '') or 'N/A'}")
    seal_c3.caption(f"M1: {getattr(tx, 'seal_m1', '') or 'N/A'}")
    seal_c4.caption(f"M2: {getattr(tx, 'seal_m2', '') or 'N/A'}")

    if getattr(tx, "remarks", None):
        st.markdown("##### Remarks")
        st.info(tx.remarks)

    # Actions
    action_col1, action_col2 = st.columns([0.4, 0.6])
    with action_col1:
        if st.button("Close Viewer", key=f"close_detail_{tx.id}"):
            st.session_state.pop("tanker_view_selected", None)


# ========== Custom Tab View ==========

def _render_custom_tanker_tab_view(location_id: Optional[int], tab_def: dict, user: Dict[str, Any] | None) -> None:
    """Render custom tab data view with edit/delete functionality"""
    from models import get_custom_table_model
    import pandas as pd
    from datetime import date, timedelta
    
    tab_name = tab_def.get("name", "Custom Tab")
    table_name = tab_def.get("table_name")
    columns = tab_def.get("columns", [])
    
    st.markdown(f"#### {tab_name}")
    
    if not table_name:
        st.error("No table name defined for this custom tab.")
        return
    
    CustomModel = get_custom_table_model(table_name)
    if not CustomModel:
        from logger import log_error, log_info
        error_msg = f"❌ Database table `{table_name}` does not exist!"
        log_error(error_msg)
        st.error(error_msg)
        
        st.warning("The database table is missing. This can happen if the table creation failed previously.")
        
        # Offer to recreate table
        if st.button("🔧 Recreate Database Table", key=f"recreate_view_{table_name}"):
            try:
                from models import create_custom_tab_table
                log_info(f"Attempting to recreate table {table_name}")
                
                table_created = create_custom_tab_table(table_name, columns, location_id)
                
                if table_created:
                    st.success(f"✅ Table `{table_name}` recreated successfully!")
                    log_info(f"Table {table_name} recreated successfully")
                    st.rerun()
                else:
                    st.error("Failed to recreate table. Check logs for details.")
                    log_error(f"Failed to recreate table {table_name}")
            except Exception as recreate_ex:
                error_msg = f"Error recreating table: {recreate_ex}"
                st.error(error_msg)
                log_error(error_msg, exc_info=True)
        
        st.info("💡 Alternative: Use Page Customization to delete this tab completely and create a new one.")
        return
    
    # Get actual columns in the database table
    actual_columns = set()
    try:
        if hasattr(CustomModel, '__table__'):
            actual_columns = {col.name for col in CustomModel.__table__.columns}
    except Exception as ex:
        from logger import log_error
        log_error(f"Failed to get table columns for {table_name}: {ex}")
    
    # Filters
    today = date.today()
    default_from = today - timedelta(days=30)
    
    f1, f2, f3 = st.columns(3)
    with f1:
        date_from = st.date_input("From Date", value=default_from, max_value=today, key=f"ctv_{table_name}_from")
    with f2:
        date_to = st.date_input("To Date", value=today, max_value=today, key=f"ctv_{table_name}_to")
    with f3:
        created_by_filter = st.text_input("Created By (contains)", key=f"ctv_{table_name}_creator")
    
    # Load data
    with get_session() as s:
        query = s.query(CustomModel).filter(CustomModel.location_id == location_id)
        
        if hasattr(CustomModel, 'tx_date'):
            if date_from:
                query = query.filter(CustomModel.tx_date >= date_from)
            if date_to:
                query = query.filter(CustomModel.tx_date <= date_to)
        
        if created_by_filter and hasattr(CustomModel, 'created_by'):
            query = query.filter(CustomModel.created_by.contains(created_by_filter))
        
        records = query.order_by(CustomModel.id.desc()).all()
    
    if not records:
        st.info(f"No records found for {tab_name}.")
        return
    
    st.metric("Total Records", len(records))
    st.markdown("---")
    
    # Prepare table data
    table_data = []
    for rec in records:
        row_dict = {
            "ID": getattr(rec, "id", ""),
            "Date": str(getattr(rec, "tx_date", "")) if hasattr(rec, "tx_date") else "",
            "Created By": getattr(rec, "created_by", "") or "",
            "Created At": getattr(rec, "created_at").strftime("%Y-%m-%d %H:%M") if hasattr(rec, "created_at") and getattr(rec, "created_at") else "",
        }
        
        # Add custom columns (only if they exist in actual table)
        for col in columns:
            col_name = col.get("name")
            col_label = col.get("label", col_name)
            # Check if column exists in actual table, not just in config
            if col_name and col_name in actual_columns:
                try:
                    value = getattr(rec, col_name, None)
                    if col.get("type") == "number" and value is not None:
                        decimal_places = col.get("decimal_places", 2)
                        row_dict[col_label] = f"{float(value):.{decimal_places}f}"
                    elif col.get("type") == "date" and value:
                        row_dict[col_label] = str(value)
                    else:
                        row_dict[col_label] = str(value) if value is not None else ""
                except Exception as ex:
                    from logger import log_error
                    log_error(f"Error reading column {col_name} from record: {ex}")
                    row_dict[col_label] = ""
            else:
                # Column not in table, show as empty
                row_dict[col_label] = ""
        
        table_data.append(row_dict)
    
    # Display table with action buttons
    if table_data:
        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True, height=400)
        
        # Export
        st.markdown("---")
        col1, col2 = st.columns([0.2, 0.8])
        with col1:
            st.markdown("**Export:**")
        with col2:
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Download CSV",
                data=csv,
                file_name=f"{tab_name.lower().replace(' ', '_')}_data.csv",
                mime="text/csv"
            )
        
        st.markdown("---")
        st.markdown("##### 📝 Actions")
        st.markdown("Select a record to edit or delete:")
        st.markdown("")
        
        # Create a cleaner table view with action buttons
        for idx, rec in enumerate(records):
            rec_id = getattr(rec, "id")
            tx_date = getattr(rec, "tx_date", None) if hasattr(rec, "tx_date") else None
            created_by = getattr(rec, "created_by", "") if hasattr(rec, "created_by") else ""
            created_at = getattr(rec, "created_at", None) if hasattr(rec, "created_at") else None
            updated_at = getattr(rec, "updated_at", None) if hasattr(rec, "updated_at") else None
            
            # Show summary data from custom columns
            summary_parts = [f"ID {rec_id}"]
            if tx_date:
                summary_parts.append(str(tx_date))
            
            # Add first 2 custom column values as preview (only from actual table)
            preview_count = 0
            for col in columns[:3]:
                col_name = col.get("name")
                col_label = col.get("label", col_name)
                if col_name and col_name in actual_columns and preview_count < 2:
                    try:
                        value = getattr(rec, col_name, None)
                        if value is not None:
                            if col.get("type") == "number":
                                decimal_places = col.get("decimal_places", 2)
                                summary_parts.append(f"{col_label}: {float(value):.{decimal_places}f}")
                            else:
                                summary_parts.append(f"{col_label}: {value}")
                            preview_count += 1
                    except Exception:
                        pass
            
            summary = " • ".join(summary_parts)
            
            col1, col2, col3, col4 = st.columns([0.50, 0.25, 0.125, 0.125])
            
            with col1:
                edit_indicator = " ⚠️" if updated_at else ""
                st.text(f"{summary}{edit_indicator}")
            
            with col2:
                created_str = created_at.strftime("%Y-%m-%d %H:%M") if created_at else "Unknown"
                st.caption(f"By: {created_by or 'Unknown'} • {created_str}")
            
            with col3:
                if st.button("✏️ Edit", key=f"edit_ctv_{table_name}_{rec_id}"):
                    st.session_state[f"editing_ctv_{table_name}_{rec_id}"] = True
                    st.rerun()
            
            with col4:
                if st.button("🗑️ Delete", key=f"delete_ctv_{table_name}_{rec_id}"):
                    st.session_state[f"deleting_ctv_{table_name}_{rec_id}"] = True
                    st.rerun()
            
            # Edit modal
            if st.session_state.get(f"editing_ctv_{table_name}_{rec_id}"):
                _render_ctv_edit_modal(rec, tab_def, user)
            
            # Delete confirmation
            if st.session_state.get(f"deleting_ctv_{table_name}_{rec_id}"):
                _render_ctv_delete_confirmation(rec, tab_def, user)
            
            st.markdown("---")


def _render_ctv_edit_modal(record, tab_def: dict, user: Dict[str, Any] | None):
    """Edit modal for custom tanker tab record"""
    from models import get_custom_table_model
    from datetime import datetime as dt
    
    tab_name = tab_def.get("name", "Custom Tab")
    table_name = tab_def.get("table_name")
    columns = tab_def.get("columns", [])
    rec_id = getattr(record, "id")
    
    st.markdown(f"### ✏️ Edit {tab_name} Record (ID: {rec_id})")
    
    created_by = getattr(record, "created_by", "") if hasattr(record, "created_by") else ""
    created_at = getattr(record, "created_at", None) if hasattr(record, "created_at") else None
    updated_at = getattr(record, "updated_at", None) if hasattr(record, "updated_at") else None
    
    if updated_at:
        st.warning(f"⚠️ This record was last edited on {updated_at.strftime('%Y-%m-%d %H:%M')}")
    
    st.caption(f"**Created by:** {created_by or 'Unknown'} on {created_at.strftime('%Y-%m-%d %H:%M') if created_at else 'Unknown'}")
    
    with st.form(key=f"edit_ctv_form_{table_name}_{rec_id}"):
        edited_values = {}
        
        # Separate manual and calculated columns
        manual_columns = [c for c in columns if not c.get("formula")]
        calculated_columns = [c for c in columns if c.get("formula")]
        
        # Render editable fields
        for col in manual_columns:
            col_name = col.get("name")
            col_label = col.get("label", col_name)
            col_type = col.get("type", "text")
            current_value = getattr(record, col_name, None) if hasattr(record, col_name) else None
            
            if col_type == "date":
                edited_values[col_name] = st.date_input(col_label, value=current_value, key=f"edit_ctv_{table_name}_{rec_id}_{col_name}")
            elif col_type == "number":
                edited_values[col_name] = st.number_input(col_label, value=float(current_value) if current_value is not None else 0.0, step=0.01, format="%.2f", key=f"edit_ctv_{table_name}_{rec_id}_{col_name}")
            else:
                edited_values[col_name] = st.text_input(col_label, value=str(current_value) if current_value else "", key=f"edit_ctv_{table_name}_{rec_id}_{col_name}")
        
        # Recalculate formulas
        if calculated_columns:
            st.markdown("##### 🧮 Calculated Columns (Auto-updated)")
            from tank_transactions import _evaluate_formula
            
            for calc_col in calculated_columns:
                formula = calc_col.get("formula")
                col_label = calc_col.get("label", calc_col.get("name"))
                col_name = calc_col.get("name")
                
                calculated_value = _evaluate_formula(formula, edited_values)
                if calculated_value is not None:
                    st.metric(col_label, f"{calculated_value:.2f}")
                    edited_values[col_name] = calculated_value
                else:
                    edited_values[col_name] = None
        
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("💾 Save Changes", type="primary"):
                try:
                    CustomModel = get_custom_table_model(table_name)
                    with get_session() as s:
                        rec = s.query(CustomModel).get(rec_id)
                        if rec:
                            # Update fields
                            for col_name, value in edited_values.items():
                                if hasattr(rec, col_name):
                                    setattr(rec, col_name, value)
                            
                            # Set updated_at timestamp
                            if hasattr(rec, "updated_at"):
                                setattr(rec, "updated_at", dt.now())
                            
                            s.commit()
                            
                            # Audit log
                            try:
                                SecurityManager.log_audit(
                                    s, (user or {}).get("username", "system"), "UPDATE",
                                    resource_type=f"CustomTankerTab:{tab_name}",
                                    resource_id=str(rec_id),
                                    details=f"Edited {tab_name} record. Updated by {(user or {}).get('username')} at {dt.now().strftime('%Y-%m-%d %H:%M')}",
                                    user_id=(user or {}).get("id"),
                                    location_id=getattr(record, "location_id"),
                                    ip_address=None,
                                    success=True
                                )
                            except Exception:
                                pass
                            
                            st.success(f"✅ {tab_name} record updated successfully!")
                            del st.session_state[f"editing_ctv_{table_name}_{rec_id}"]
                            st.rerun()
                except Exception as ex:
                    st.error(f"Failed to update: {ex}")
        
        with col2:
            if st.form_submit_button("❌ Cancel"):
                del st.session_state[f"editing_ctv_{table_name}_{rec_id}"]
                st.rerun()


def _render_ctv_delete_confirmation(record, tab_def: dict, user: Dict[str, Any] | None):
    """Delete confirmation for custom tanker tab record"""
    from models import get_custom_table_model
    from logger import log_error
    
    tab_name = tab_def.get("name", "Custom Tab")
    table_name = tab_def.get("table_name")
    rec_id = getattr(record, "id")
    
    st.warning(f"⚠️ Are you sure you want to delete {tab_name} record ID {rec_id}?")
    st.caption("This action cannot be undone.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑️ Confirm Delete", key=f"confirm_delete_ctv_{table_name}_{rec_id}", type="primary"):
            try:
                CustomModel = get_custom_table_model(table_name)
                if not CustomModel:
                    st.error(f"Database table `{table_name}` not found.")
                    return
                    
                with get_session() as s:
                    rec = s.query(CustomModel).filter(CustomModel.id == rec_id).first()
                    if rec:
                        location_id = getattr(rec, "location_id", None)
                        
                        # Audit log before deleting
                        try:
                            SecurityManager.log_audit(
                                s, (user or {}).get("username", "system"), "DELETE",
                                resource_type=f"CustomTankerTab:{tab_name}",
                                resource_id=str(rec_id),
                                details=f"Deleted {tab_name} record ID {rec_id} from table {table_name}",
                                user_id=(user or {}).get("id"),
                                location_id=location_id,
                                ip_address=st.session_state.get("client_ip"),
                                success=True
                            )
                        except Exception as audit_ex:
                            log_error(f"Failed to log audit for custom tab deletion: {audit_ex}")
                        
                        s.delete(rec)
                        s.commit()
                        
                        st.success(f"✅ {tab_name} record deleted successfully!")
                        if f"deleting_ctv_{table_name}_{rec_id}" in st.session_state:
                            del st.session_state[f"deleting_ctv_{table_name}_{rec_id}"]
                        st.rerun()
                    else:
                        st.error(f"Record ID {rec_id} not found.")
                        if f"deleting_ctv_{table_name}_{rec_id}" in st.session_state:
                            del st.session_state[f"deleting_ctv_{table_name}_{rec_id}"]
            except Exception as ex:
                error_msg = f"Failed to delete: {ex}"
                st.error(error_msg)
                log_error(f"Custom tanker tab deletion error for {table_name} record {rec_id}: {ex}", exc_info=True)
                
                # Log failed deletion
                try:
                    with get_session() as s:
                        SecurityManager.log_audit(
                            s, (user or {}).get("username", "system"), "DELETE",
                            resource_type=f"CustomTankerTab:{tab_name}",
                            resource_id=str(rec_id),
                            details=f"Delete failed: {str(ex)}",
                            user_id=(user or {}).get("id"),
                            location_id=getattr(record, "location_id", None),
                            ip_address=st.session_state.get("client_ip"),
                            success=False
                        )
                except Exception:
                    pass
    
    with col2:
        if st.button("❌ Cancel", key=f"cancel_delete_ctv_{table_name}_{rec_id}"):
            if f"deleting_ctv_{table_name}_{rec_id}" in st.session_state:
                del st.session_state[f"deleting_ctv_{table_name}_{rec_id}"]
            st.rerun()


def _delete_tanker_transaction(row_id: int, user: Dict[str, Any]) -> None:
    username = (user or {}).get("username") or (user or {}).get("name") or "system"
    user_id  = (user or {}).get("id")
    with get_session() as s:
        tx = s.query(TankerTransaction).filter(TankerTransaction.id == row_id).one_or_none()
        if not tx:
            st.error("Record not found or already deleted.")
            return
        s.delete(tx)
        s.flush()
        try:
            SecurityManager.log_audit(
                None,
                username,
                "DELETE",
                resource_type="TankerTransaction",
                resource_id=str(row_id),
                details=f"DELETE tanker transaction {row_id}",
                user_id=user_id,
                location_id=getattr(tx, "location_id", None),
            )
        except Exception:
            pass
        s.commit()
        st.success("Tanker transaction deleted.")
