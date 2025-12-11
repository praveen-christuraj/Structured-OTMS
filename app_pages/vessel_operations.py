# app_pages/vessel_operations.py
from __future__ import annotations

from datetime import datetime, date, timedelta
from io import BytesIO
from typing import Dict, List, Optional
import base64
import re
import pandas as pd
import streamlit as st
from sqlalchemy import func

from db import get_session
from security import SecurityManager
from ui import header
from action_logger_utils import log_export_action
try:
    from recycle_bin import RecycleBinManager
except Exception:
    RecycleBinManager = None

# models
from models import Location, Vessel, LocationVessel, VesselOperation

# Use OTRVessel as the entry table
try:
    from models import OTRVessel as VesselOpsEntry
except Exception:
    VesselOpsEntry = None

# Optional permissions
try:
    from permission_manager import PermissionManager
except Exception:
    PermissionManager = None


# ---------- small helpers ----------
def _st_safe_rerun():
    try:
        st.experimental_rerun()
    except Exception:
        st.rerun()

def _fmt_num(x: float | int, nd: int = 0) -> str:
    try:
        return f"{float(x):,.{nd}f}"
    except Exception:
        return "0"


def _build_pdf(df: pd.DataFrame,
               date_from: str,
               date_to: str,
               totals: Dict[str, float],
               username: str,
               location_name: str) -> bytes:
    """Landscape A4 vessel-ops PDF (conventional style)."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib import colors
    from reportlab.lib.units import cm

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=0.5*cm, rightMargin=0.5*cm, topMargin=0.5*cm, bottomMargin=0.5*cm
    )
    styles = getSampleStyleSheet()
    H = ParagraphStyle("H", parent=styles["Heading1"], fontSize=16, alignment=TA_CENTER,
                       textColor=colors.HexColor("#1f4788"))
    sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9, alignment=TA_CENTER,
                         textColor=colors.HexColor("#666"))

    story = []
    story.append(Paragraph(f"<b>VESSEL OPERATIONS REPORT</b><br/><font size=14>{location_name}</font>", H))
    story.append(Spacer(1, 0.25*cm))
    story.append(Paragraph(f"Period: <b>{date_from}</b> to <b>{date_to}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
                           f"Generated: {datetime.now():%d-%b-%Y %H:%M}", sub))
    story.append(Spacer(1, 0.4*cm))

    head_color = colors.HexColor("#1f4788")
    table_data = [[
        Paragraph("<b><font color='white'>Date</font></b>", styles["BodyText"]),
        Paragraph("<b><font color='white'>Time</font></b>", styles["BodyText"]),
        Paragraph("<b><font color='white'>Shuttle No</font></b>", styles["BodyText"]),
        Paragraph("<b><font color='white'>Vessel Name</font></b>", styles["BodyText"]),
        Paragraph("<b><font color='white'>Operation</font></b>", styles["BodyText"]),
        Paragraph("<b><font color='white'>Opening Stock</font></b>", styles["BodyText"]),
        Paragraph("<b><font color='white'>Opening Water</font></b>", styles["BodyText"]),
        Paragraph("<b><font color='white'>Closing Stock</font></b>", styles["BodyText"]),
        Paragraph("<b><font color='white'>Closing Water</font></b>", styles["BodyText"]),
        Paragraph("<b><font color='white'>Net R/D</font></b>", styles["BodyText"]),
        Paragraph("<b><font color='white'>Net Water</font></b>", styles["BodyText"]),
        Paragraph("<b><font color='white'>Remarks</font></b>", styles["BodyText"]),
    ]]

    cell = ParagraphStyle("cell", parent=styles["Normal"], fontSize=8, leading=9)
    for _, r in df.iterrows():
        rd = r["Net R/D"]
        rd_col = "#28a745" if rd >= 0 else "#dc3545"
        table_data.append([
            Paragraph(str(r["Date"]), cell),
            Paragraph(str(r["Time"]), cell),
            Paragraph(str(r["Shuttle No"]), cell),
            Paragraph(str(r["Vessel Name"])[:30], cell),
            Paragraph(str(r["Operation"])[:24], cell),
            Paragraph(_fmt_num(r["Opening Stock"], 0), cell),
            Paragraph(_fmt_num(r["Opening Water"], 0), cell),
            Paragraph(_fmt_num(r["Closing Stock"], 0), cell),
            Paragraph(_fmt_num(r["Closing Water"], 0), cell),
            Paragraph(f"<font color='{rd_col}'><b>{_fmt_num(rd, 0)}</b></font>", cell),
            Paragraph(_fmt_num(r["Net Water"], 0), cell),
            Paragraph((r["Remarks"] or "-")[:60], cell),
        ])

    col_widths = [
        2.3*cm, 1.9*cm, 2.6*cm, 3.4*cm, 2.4*cm,
        2.1*cm, 1.9*cm, 2.1*cm, 1.9*cm, 2.1*cm,
        1.9*cm, 3.4*cm,
    ]
    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), head_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
    ]))
    story.append(tbl)

    from reportlab.platypus import Table as T2, TableStyle as TS2, Paragraph as P2
    story.append(Spacer(1, 0.4*cm))
    summ = [
        [P2("<b>SUMMARY</b>", styles["Heading5"]), "", "", ""],
        [P2(f"Total Receipts: {_fmt_num(totals['receipts'], 2)} bbls", styles["Normal"]),
         P2(f"Total Dispatches: {_fmt_num(totals['dispatches'], 2)} bbls", styles["Normal"]),
         P2(f"Water In: {_fmt_num(totals['water_in'], 2)} bbls", styles["Normal"]),
         P2(f"Water Out: {_fmt_num(totals['water_out'], 2)} bbls", styles["Normal"])],
        [P2(f"Net Movement: {_fmt_num(totals['receipts'] - totals['dispatches'], 2)} bbls", styles["Normal"]),
         P2(f"Net Water: {_fmt_num(totals['water_in'] - totals['water_out'], 2)} bbls", styles["Normal"]),
         "", P2(f"Total Entries: {int(totals['entries'])}", styles["Normal"])],
    ]
    t2 = T2(summ, colWidths=[7.0*cm, 7.0*cm, 7.0*cm, 7.0*cm])
    t2.setStyle(TS2([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), head_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(t2)

    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        f"<font size=7 color='#666'>Generated by: {username} &nbsp;|&nbsp; OTMS &nbsp;|&nbsp; {datetime.now():%d-%b-%Y %H:%M:%S}</font>",
        styles["Normal"]
    ))

    doc.build(story)
    return buf.getvalue()


# ---------- operations helpers ----------
_DEFAULT_OPS = ["Loading", "Discharging"]

def _get_operation_labels(session) -> List[str]:
    """Read active VesselOperation names; fallback to defaults if none exist."""
    rows = session.query(VesselOperation.operation_name).filter(VesselOperation.is_active == True).order_by(VesselOperation.operation_name.asc()).all()
    labels = [r[0] for r in rows if r and r[0]]
    return labels or list(_DEFAULT_OPS)

def _ensure_operation_id(session, op_name: str) -> int:
    """Get (or create) VesselOperation row for the given name, return its id."""
    op_name = (op_name or "").strip()
    if not op_name:
        op_name = _DEFAULT_OPS[0]
    rec = session.query(VesselOperation).filter(VesselOperation.operation_name == op_name).one_or_none()
    if rec:
        # ensure active
        if getattr(rec, "is_active", True) is not True:
            rec.is_active = True
            session.flush()
        return rec.id
    # create it
    new_op = VesselOperation(operation_name=op_name, is_active=True)
    session.add(new_op)
    session.flush()
    return new_op.id


# ---------- main renderer ----------
def render_vessel_operations_page(active_location_id: Optional[int], user: Dict):
    header("Vessel Operations")

    if active_location_id is None:
        active_location_id = st.session_state.get("active_location_id")
    if user is None:
        user = st.session_state.get("auth_user")
        
    # guards
    if not user:
        st.error("Please login to access this page.")
        st.stop()
    if not active_location_id:
        st.error("No active location selected.")
        st.stop()
    if user.get("role") == "admin-it":
        st.error("🚫 Access Denied: Admin-IT users do not have access to operational pages.")
        st.stop()

    # permissions
    can_make_entries = True
    if PermissionManager:
        with get_session() as s:
            can_make_entries = PermissionManager.can_make_entries_user(s, user, active_location_id)

    # vessels strictly from Asset Management assignment
    with get_session() as s:
        loc = s.query(Location).filter(Location.id == active_location_id).first()
        location_name = loc.name if loc else "—"
        st.caption(f"📍 Active Location: **{location_name}**")

        vessels = (
            s.query(Vessel)
             .join(LocationVessel, LocationVessel.vessel_id == Vessel.id)
             .filter(LocationVessel.location_id == active_location_id,
                     LocationVessel.is_active == True,
                     Vessel.status == "ACTIVE")
             .order_by(Vessel.name.asc())
             .all()
        )
        if not vessels:
            st.warning("No vessels assigned to this location. Use **Asset Management → assign vessels** to this location.")
            st.stop()

        vessel_options = [(v.id, v.name) for v in vessels]
        vessel_dict = {vid: vname for vid, vname in vessel_options}

        # operations labels (from master; fallback to defaults, no blocking)
        op_labels = _get_operation_labels(s)

    # ---------- filters ----------
    st.markdown("### 🔎 Filters")
    # Determine earliest and latest entry dates for this location
    with get_session() as s:
        dmin = s.query(func.min(VesselOpsEntry.date)).filter(VesselOpsEntry.location_id == active_location_id).scalar() if VesselOpsEntry else None
        dmax = s.query(func.max(VesselOpsEntry.date)).filter(VesselOpsEntry.location_id == active_location_id).scalar() if VesselOpsEntry else None
    today = date.today()
    default_from = dmin or today
    default_to = (dmax or today)
    if default_to > today:
        default_to = today

    fc1, fc2, fc3, fc4, fc5 = st.columns(5)
    with fc1:
        f_from = st.date_input("From", value=default_from, min_value=default_from, max_value=today, key="vop_f_from")
    with fc2:
        f_to = st.date_input("To", value=default_to, min_value=default_from, max_value=today, key="vop_f_to")
    # Clamp in case of manual edits
    if f_to > today:
        f_to = today
    if f_from < default_from:
        f_from = default_from
    if f_from > f_to:
        f_from = default_from
        f_to = default_to
    with fc3:
        f_shuttle = st.text_input("Shuttle No", placeholder="Filter…", key="vop_f_shuttle")
    with fc4:
        f_vessel = st.selectbox("Vessel", ["All"] + [v[1] for v in vessel_options], key="vop_f_vessel")
    with fc5:
        f_op = st.selectbox("Operation", ["All"] + op_labels, key="vop_f_op")

    st.markdown("---")

    # ---------- add entry ----------
    if can_make_entries and VesselOpsEntry:
        with st.expander("➕ Add New Entry", expanded=False):
            with st.form("vop_add_form", clear_on_submit=True):
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    e_date = st.date_input("Date *", value=date.today(), max_value=date.today())
                    e_time = st.text_input("Time (HH:MM) *", value=datetime.now().strftime("%H:%M"), max_chars=5)
                    e_shuttle = st.text_input("Shuttle No *", placeholder="SH-001")
                with c2:
                    e_vessel_id = st.selectbox("Vessel Name *", options=[v[0] for v in vessel_options],
                                               format_func=lambda x: vessel_dict.get(x, "Unknown"))
                    e_op_label = st.selectbox("Operation *", options=op_labels)
                with c3:
                    e_open = st.number_input("Opening Stock (bbls) *", min_value=0.0, value=0.0, step=0.01, format="%.2f")
                    e_open_w = st.number_input("Opening Water (bbls)", min_value=0.0, value=0.0, step=0.01, format="%.2f")
                    e_close = st.number_input("Closing Stock (bbls) *", min_value=0.0, value=0.0, step=0.01, format="%.2f")
                with c4:
                    e_close_w = st.number_input("Closing Water (bbls)", min_value=0.0, value=0.0, step=0.01, format="%.2f")
                    e_remarks = st.text_area("Remarks", placeholder="Optional …", max_chars=500)

                net_stock = e_close - e_open
                net_water = e_close_w - e_open_w
                st.info(f"Net Stock: {_fmt_num(net_stock, 2)} bbls  |  Net Water: {_fmt_num(net_water, 2)} bbls")

                if op_labels == _DEFAULT_OPS:
                    st.caption("⚙️ Tip: you can add custom operation labels in master (VesselOperation). Using defaults for now.")

                submit = st.form_submit_button("💾", type="primary", help="Save Entry", disabled=not can_make_entries)
                if submit:
                    if not e_shuttle.strip():
                        st.error("Shuttle No is required.")
                    elif not e_time or not re.match(r"^\d{2}:\d{2}$", e_time):
                        st.error("Time must be in HH:MM.")
                    else:
                        try:
                            with get_session() as s:
                                # ensure an operation id exists for the chosen label
                                op_id = _ensure_operation_id(s, e_op_label)

                                row = VesselOpsEntry(
                                    location_id=active_location_id,
                                    date=e_date,
                                    time=e_time.strip(),
                                    shuttle_no=e_shuttle.strip(),
                                    vessel_id=int(e_vessel_id),
                                    operation_id=int(op_id),
                                    opening_stock=float(e_open),
                                    opening_water=float(e_open_w),
                                    closing_stock=float(e_close),
                                    closing_water=float(e_close_w),
                                    net_receipt_dispatch=float(net_stock),
                                    net_water=float(net_water),
                                    remarks=e_remarks.strip() if e_remarks else None,
                                    created_by=user["username"],
                                )
                                s.add(row)
                                s.flush()
                                rid = row.id
                                s.commit()

                            SecurityManager.log_audit(
                                None, user["username"], "CREATE",
                                resource_type="VesselOpsEntry", resource_id=str(rid),
                                location_id=active_location_id,
                                details=f"Add vessel entry: {vessel_dict.get(e_vessel_id, 'Unknown')}",
                                user_id=user.get("id")
                            )
                            st.write(f"Saved. ID: {rid}")
                            _st_safe_rerun()
                        except Exception as ex:
                            st.error(f"Save failed: {ex}")
    elif not VesselOpsEntry:
        st.warning("VesselOpsEntry model not found (expected models.OTRVessel).")

    st.markdown("---")

    # ---------- fetch entries ----------
    with get_session() as s:
        q = (s.query(VesselOpsEntry)
               .filter(VesselOpsEntry.location_id == active_location_id,
                       VesselOpsEntry.date >= f_from,
                       VesselOpsEntry.date <= f_to))
        if f_shuttle:
            q = q.filter(VesselOpsEntry.shuttle_no.contains(f_shuttle))
        if f_vessel != "All":
            vid = next((i for i, n in vessel_options if n == f_vessel), None)
            if vid:
                q = q.filter(VesselOpsEntry.vessel_id == vid)
        if f_op != "All":
            # map label to id if exists
            op_row = s.query(VesselOperation.id).filter(VesselOperation.operation_name == f_op).one_or_none()
            if op_row:
                q = q.filter(VesselOpsEntry.operation_id == op_row[0])

        rows = q.order_by(VesselOpsEntry.date.desc(), VesselOpsEntry.time.desc()).all()

        # maps for display
        vdict = {v.id: v.name for v in s.query(Vessel).all()}
        odict = {o.id: o.operation_name for o in s.query(VesselOperation).all()}

    if not rows:
        st.info("No entries.")
        return

    st.markdown(f"### ⛴️ Vessel Operations ({len(rows)})")

    header_cols = st.columns([0.06, 0.10, 0.08, 0.12, 0.14, 0.12, 0.09, 0.09, 0.09, 0.09, 0.09, 0.12, 0.05, 0.05])
    header_labels = [
        "ID", "Date", "Time", "Shuttle", "Vessel", "Operation",
        "Open", "Open W", "Close", "Close W", "Net R/D", "Remarks",
        "Edit", "Del"
    ]
    for col, lbl in zip(header_cols, header_labels):
        with col:
            st.markdown(f"**{lbl}**")

    # compact table with single-row data and actions
    for entry in rows:
        vname = vdict.get(entry.vessel_id, "Unknown")
        oname = odict.get(entry.operation_id, "Unknown")
        with st.container(border=True):
            cols = st.columns([0.06, 0.10, 0.08, 0.12, 0.14, 0.12, 0.09, 0.09, 0.09, 0.09, 0.09, 0.12, 0.05, 0.05])
            with cols[0]:
                st.markdown(f"**{entry.id}**")
            with cols[1]:
                dtxt = entry.date.strftime("%Y-%m-%d")
                if getattr(entry, "updated_at", None):
                    ub = getattr(entry, "updated_by", "unknown")
                    ut = getattr(entry, "updated_at", None)
                    ts = ut.strftime("%Y-%m-%d %H:%M") if hasattr(ut, 'strftime') else str(ut)
                    st.markdown(f"<span>{dtxt}</span> <span title='Edited by {ub} on {ts}'>⚠️</span>", unsafe_allow_html=True)
                else:
                    st.write(dtxt)
            with cols[2]:
                st.write(entry.time)
            with cols[3]:
                st.write(entry.shuttle_no)
            with cols[4]:
                st.write(vname)
            with cols[5]:
                st.write(oname)
            with cols[6]:
                st.write(_fmt_num(entry.opening_stock, 0))
            with cols[7]:
                st.write(_fmt_num(getattr(entry, "opening_water", 0.0), 0))
            with cols[8]:
                st.write(_fmt_num(entry.closing_stock, 0))
            with cols[9]:
                st.write(_fmt_num(getattr(entry, "closing_water", 0.0), 0))
            with cols[10]:
                st.write(_fmt_num(entry.net_receipt_dispatch, 0))
            with cols[11]:
                rtxt = entry.remarks or "-"
                short = rtxt if len(rtxt) <= 40 else (rtxt[:37] + "...")
                st.markdown(
                    f"<span title='{rtxt.replace("'", "&#39;")}'>{short}</span>",
                    unsafe_allow_html=True,
                )
            with cols[12]:
                if st.button("✏️", key=f"vop_edit_{entry.id}", help="Edit entry", disabled=not can_make_entries):
                    st.session_state[f"vop_editing_{entry.id}"] = True
                    _st_safe_rerun()
            with cols[13]:
                created_at = getattr(entry, "created_at", None)
                age_ok = True
                if created_at:
                    try:
                        age_ok = (datetime.now() - created_at).total_seconds() <= 24 * 3600
                    except Exception:
                        age_ok = True
                if not age_ok:
                    st.button("🗑️", key=f"vop_del_{entry.id}", help="Delete disabled after 24 hours", disabled=True)
                else:
                    if st.button("🗑️", key=f"vop_del_{entry.id}", help="Delete entry", disabled=not can_make_entries):
                        st.session_state[f"vop_deleting_{entry.id}"] = True
                        _st_safe_rerun()

            # edit form
            if st.session_state.get(f"vop_editing_{entry.id}", False):
                st.markdown("---")
                with st.form(f"vop_edit_form_{entry.id}"):
                    ec1, ec2, ec3, ec4 = st.columns(4)
                    with ec1:
                        ed_date = st.date_input("Date", value=entry.date, max_value=date.today(), key=f"vop_ed_date_{entry.id}")
                        ed_time = st.text_input("Time (HH:MM)", value=str(entry.time), max_chars=5,
                                                key=f"vop_ed_time_{entry.id}")
                        ed_shuttle = st.text_input("Shuttle No", value=entry.shuttle_no, key=f"vop_ed_sh_{entry.id}")
                    with ec2:
                        # vessel dropdown by id
                        try:
                            v_idx = [i for i, _ in vessel_options].index(entry.vessel_id)
                        except ValueError:
                            v_idx = 0
                        ed_vid = st.selectbox("Vessel Name",
                                              options=[i for i, _ in vessel_options],
                                              index=v_idx,
                                              format_func=lambda x: vessel_dict.get(x, "Unknown"),
                                              key=f"vop_ed_vid_{entry.id}")
                        # operation dropdown by label; we will upsert to id on save
                        ed_op_label = st.selectbox("Operation", options=op_labels,
                                                   index=max(0, op_labels.index(oname) if oname in op_labels else 0),
                                                   key=f"vop_ed_oplbl_{entry.id}")
                    with ec3:
                        ed_open = st.number_input("Opening Stock (bbls)", value=float(entry.opening_stock),
                                                  key=f"vop_ed_open_{entry.id}")
                        ed_open_w = st.number_input("Opening Water (bbls)", value=float(entry.opening_water or 0.0),
                                                    key=f"vop_ed_openw_{entry.id}")
                        ed_close = st.number_input("Closing Stock (bbls)", value=float(entry.closing_stock),
                                                   key=f"vop_ed_close_{entry.id}")
                    with ec4:
                        ed_close_w = st.number_input("Closing Water (bbls)", value=float(entry.closing_water or 0.0),
                                                     key=f"vop_ed_closew_{entry.id}")
                        ed_rem = st.text_area("Remarks", value=entry.remarks or "", key=f"vop_ed_rem_{entry.id}")

                    ed_net = (ed_close - ed_open)
                    ed_netw = (ed_close_w - ed_open_w)
                    st.info(f"Net Stock: {_fmt_num(ed_net, 2)} bbls | Net Water: {_fmt_num(ed_netw, 2)} bbls")

                    sc, cc = st.columns(2)
                    with sc:
                        save = st.form_submit_button("💾", type="primary", help="Save", disabled=not can_make_entries)
                    with cc:
                        cancel = st.form_submit_button("✖️", help="Cancel")
                    if save:
                        ttxt = (ed_time or "").strip()
                        if not ed_shuttle.strip():
                            st.error("Shuttle No is required.")
                        elif not ttxt or not re.match(r"^\d{2}:\d{2}$", ttxt):
                            st.error("Time must be in HH:MM.")
                        else:
                            try:
                                with get_session() as s:
                                    # upsert operation by label -> id
                                    op_id = _ensure_operation_id(s, ed_op_label)

                                    row = s.query(VesselOpsEntry).filter(VesselOpsEntry.id == entry.id).one_or_none()
                                    if not row:
                                        st.error("Record no longer exists.")
                                    else:
                                        row.date = ed_date
                                        row.time = ttxt
                                        row.shuttle_no = ed_shuttle.strip()
                                        row.vessel_id = int(ed_vid)
                                        row.operation_id = int(op_id)
                                        row.opening_stock = float(ed_open)
                                        row.opening_water = float(ed_open_w or 0.0)
                                        row.closing_stock = float(ed_close)
                                        row.closing_water = float(ed_close_w or 0.0)
                                        row.net_receipt_dispatch = float(ed_net)
                                        row.net_water = float(ed_netw)
                                        row.remarks = ed_rem.strip() if ed_rem else None
                                        row.updated_by = user["username"]
                                        row.updated_at = datetime.now()
                                        SecurityManager.log_audit(
                                            s, user["username"], "UPDATE",
                                            resource_type="VesselOpsEntry",
                                            resource_id=str(entry.id),
                                            location_id=active_location_id,
                                            details=f"Edit vessel entry {entry.id}",
                                            user_id=user.get("id")
                                        )
                                        s.commit()
                                st.write("Updated.")
                                st.session_state.pop(f"vop_editing_{entry.id}", None)
                                _st_safe_rerun()
                            except Exception as ex:
                                st.error(f"Update failed: {ex}")
                    if cancel:
                        st.session_state.pop(f"vop_editing_{entry.id}", None)
                        _st_safe_rerun()

            # delete confirm
            if st.session_state.get(f"vop_deleting_{entry.id}", False):
                st.warning("Confirm delete?")
                dc1, dc2 = st.columns(2)
                with dc1:
                    if st.button("🗑️", key=f"vop_del_yes_{entry.id}", type="primary", help="Yes, delete", disabled=not can_make_entries):
                        try:
                            with get_session() as s:
                                row = s.query(VesselOpsEntry).filter(VesselOpsEntry.id == entry.id).one_or_none()
                                if not row:
                                    st.info("Already removed.")
                                else:
                                    created_at = getattr(row, "created_at", None)
                                    age_ok = True
                                    if created_at:
                                        try:
                                            age_ok = (datetime.now() - created_at).total_seconds() <= 24 * 3600
                                        except Exception:
                                            age_ok = True
                                    if not age_ok:
                                        SecurityManager.log_audit(
                                            s, user["username"], "DELETE",
                                            resource_type="VesselOpsEntry",
                                            resource_id=str(entry.id),
                                            location_id=active_location_id,
                                            details=f"Delete blocked (older than 24h) for vessel entry {entry.id}",
                                            user_id=user.get("id"),
                                            success=False,
                                        )
                                        st.error("Delete restricted after 24 hours.")
                                    else:
                                        if RecycleBinManager:
                                            try:
                                                RecycleBinManager.archive_record(
                                                    s,
                                                    row,
                                                    "VesselOpsEntry",
                                                    username=user.get("username", "unknown"),
                                                    user_id=user.get("id"),
                                                    location_id=active_location_id,
                                                    reason=f"User deleted vessel entry {entry.id}",
                                                    label=str(entry.id),
                                                )
                                                SecurityManager.log_audit(
                                                    s,
                                                    user["username"],
                                                    "DELETE",
                                                    resource_type="VesselOpsEntry",
                                                    resource_id=str(entry.id),
                                                    location_id=active_location_id,
                                                    details=f"Moved vessel entry {entry.id} to deleted records",
                                                    user_id=user.get("id"),
                                                )
                                                s.commit()
                                            except Exception:
                                                # Fallback to hard delete if archiving fails
                                                s.delete(row)
                                                SecurityManager.log_audit(
                                                    s, user["username"], "DELETE",
                                                    resource_type="VesselOpsEntry",
                                                    resource_id=str(entry.id),
                                                    location_id=active_location_id,
                                                    details=f"Delete vessel entry {entry.id} (fallback)",
                                                    user_id=user.get("id")
                                                )
                                                s.commit()
                                        else:
                                            s.delete(row)
                                            SecurityManager.log_audit(
                                                s, user["username"], "DELETE",
                                                resource_type="VesselOpsEntry",
                                                resource_id=str(entry.id),
                                                location_id=active_location_id,
                                                details=f"Delete vessel entry {entry.id}",
                                                user_id=user.get("id")
                                            )
                                            s.commit()
                            st.write("Entry moved to Deleted Records")
                            st.session_state.pop(f"vop_deleting_{entry.id}", None)
                            _st_safe_rerun()
                        except Exception as ex:
                            st.error(f"Delete failed: {ex}")
                with dc2:
                    if st.button("✖️", key=f"vop_del_no_{entry.id}", help="Cancel"):
                        st.session_state.pop(f"vop_deleting_{entry.id}", None)
                        _st_safe_rerun()

    st.markdown("---")

    # ---------- export ----------
    export_rows = []
    for e in rows:
        export_rows.append({
            "Date": e.date.strftime("%Y-%m-%d"),
            "Time": e.time,
            "Shuttle No": e.shuttle_no,
            "Vessel Name": vdict.get(e.vessel_id, "Unknown"),
            "Operation": odict.get(e.operation_id, "Unknown"),
            "Opening Stock": float(getattr(e, "opening_stock", 0.0) or 0.0),
            "Opening Water": float(getattr(e, "opening_water", 0.0) or 0.0),
            "Closing Stock": float(getattr(e, "closing_stock", 0.0) or 0.0),
            "Closing Water": float(getattr(e, "closing_water", 0.0) or 0.0),
            "Net R/D": float(getattr(e, "net_receipt_dispatch", 0.0) or 0.0),
            "Net Water": float(getattr(e, "net_water", 0.0) or 0.0),
            "Remarks": e.remarks or "",
        })
    df = pd.DataFrame(export_rows)

    st.markdown("### 📤 Export")
    ex1, ex2, ex3, ex4 = st.columns(4)

    with ex1:
        st.download_button(
            "📥 CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=f"vessel_ops_{location_name.replace(' ', '_')}_{datetime.now():%Y%m%d_%H%M%S}.csv",
            mime="text/csv",
            use_container_width=True,
            on_click=lambda: log_export_action("VesselOperations", "CSV", len(df), user, active_location_id)
        )
    with ex2:
        excel_buf = BytesIO()
        try:
            with pd.ExcelWriter(excel_buf, engine="openpyxl") as w:
                df.to_excel(w, sheet_name="Vessel Ops", index=False)
            st.download_button(
                "📊 Excel",
                data=excel_buf.getvalue(),
                file_name=f"vessel_ops_{location_name.replace(' ', '_')}_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                on_click=lambda: log_export_action("VesselOperations", "XLSX", len(df), user, active_location_id)
            )
        except ImportError:
            st.button("📊", disabled=True, help="Install openpyxl", use_container_width=True)

    totals = {
        "receipts": sum(r.net_receipt_dispatch or 0 for r in rows if (r.net_receipt_dispatch or 0) > 0),
        "dispatches": abs(sum(r.net_receipt_dispatch or 0 for r in rows if (r.net_receipt_dispatch or 0) < 0)),
        "water_in": sum(getattr(r, "net_water", 0.0) or 0.0 for r in rows if (getattr(r, "net_water", 0.0) or 0.0) > 0),
        "water_out": abs(sum(getattr(r, "net_water", 0.0) or 0.0 for r in rows if (getattr(r, "net_water", 0.0) or 0.0) < 0)),
        "entries": len(rows),
    }

    pdf_bytes = _build_pdf(
        df,
        date_from=f_from.strftime("%d-%b-%Y"),
        date_to=f_to.strftime("%d-%b-%Y"),
        totals=totals,
        username=user["username"],
        location_name=location_name,
    )

    with ex3:
        st.download_button(
            "💾 Save PDF",
            data=pdf_bytes,
            file_name=f"vessel_ops_{location_name.replace(' ', '_')}_{date.today()}.pdf",
            mime="application/pdf",
            use_container_width=True,
            on_click=lambda: log_export_action("VesselOperations", "PDF", len(df), user, active_location_id)
        )

    with ex4:
        if st.button("👁️", use_container_width=True, help="View PDF"):
            b64 = base64.b64encode(pdf_bytes).decode("utf-8")
            html = f"""
                <script>
                    var w = window.open("");
                    w.document.write('<html><head><title>Vessel Operations - {location_name}</title></head>'+
                                     '<body style="margin:0"><iframe width="100%" height="100%" src="data:application/pdf;base64,{b64}"></iframe></body></html>');
                </script>
            """
            import streamlit.components.v1 as components
            components.html(html, height=0)
            st.write("PDF opened in a new tab.")
            try:
                SecurityManager.log_audit(
                    None,
                    user.get("username", "system"),
                    "VIEW",
                    resource_type="VesselOperations",
                    resource_id=str(active_location_id),
                    details="Viewed Vessel Operations PDF",
                    user_id=user.get("id"),
                    location_id=active_location_id,
                    success=True,
                )
            except Exception:
                pass
