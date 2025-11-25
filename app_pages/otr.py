from __future__ import annotations

import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, datetime, time, timedelta
from typing import Dict, Any, List, Optional
from io import BytesIO

from db import get_session
from ui import header

try:
    from models import Location, Tank, OTRRecord, TankTransaction
except Exception:
    Location, Tank, OTRRecord, TankTransaction = None, None, None, None

# OTR Reporting Period: 06:01 to 06:00
REPORT_DAY_START_TIME = time(6, 1)


def _guard_location(active_location_id: Optional[int]):
    """Guard against invalid location access."""
    if not active_location_id:
        st.warning("No active location is selected. Go to Home and select a location first.")
        return None, None
    with get_session() as s:
        loc = s.query(Location).get(active_location_id)
        if not loc:
            st.warning("Selected location was not found. Please re-select from Home.")
            return None, None
        return loc, f"{loc.name} ({loc.code})"


def _get_date_bounds(location_id: int) -> tuple[date, date]:
    """Get the earliest and latest OTR record dates for a location."""
    today = date.today()
    if not OTRRecord:
        return today, today
    try:
        from sqlalchemy import func
        with get_session() as s:
            dmin = s.query(func.min(OTRRecord.date)).filter(OTRRecord.location_id == location_id).scalar()
            dmax = s.query(func.max(OTRRecord.date)).filter(OTRRecord.location_id == location_id).scalar()
        dmin = dmin or today
        dmax = dmax or today
        if dmax > today:
            dmax = today
        if dmin > dmax:
            dmin = dmax
        return dmin, dmax
    except Exception:
        return today, today


def _safe_str(x):
    """Safely convert any value to string."""
    try:
        if x is None:
            return ""
        # Handle Enum - extract only the value part
        if hasattr(x, "value"):
            return str(x.value)
        s = str(x)
        # Remove "Operation." prefix if present
        if s.startswith("Operation."):
            return s.replace("Operation.", "")
        return s
    except Exception:
        return ""


def _op_label(op: Any) -> str:
    """Extract operation label from enum or string."""
    try:
        return op.value if hasattr(op, "value") else str(op or "")
    except Exception:
        return str(op or "")


def _is_receipt(op_label: str) -> bool:
    """Check if operation is a receipt (excluding ITT)."""
    v = (op_label or "").lower()
    return ("receipt" in v) and ("itt" not in v)


def _is_dispatch(op_label: str) -> bool:
    """Check if operation is a dispatch (excluding ITT)."""
    v = (op_label or "").lower()
    return ("dispatch" in v) and ("itt" not in v)


def generate_otr_pdf(dataframe, selected_tank, filter_text, location_name, location_code):
    """Generate PDF for OTR with FSO-style formatting and layout."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from pathlib import Path

    buffer = BytesIO()

    # Create document with 0.5cm margins
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=0.5 * cm,
        rightMargin=0.5 * cm,
        topMargin=0.5 * cm,
        bottomMargin=0.5 * cm,
    )

    elements = []
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#1f4788'),
        spaceAfter=8,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
    )

    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#666666'),
        spaceAfter=6,
        alignment=TA_CENTER,
    )

    # Title
    title = Paragraph(
        f"<b>OUT-TURN REPORT</b><br/><font size=14>{location_name} ({location_code})</font>",
        title_style,
    )
    elements.append(title)
    elements.append(Spacer(1, 0.3 * cm))

    # Subtitle
    subtitle = Paragraph(
        f"Filter: <b>{filter_text}</b>"
        f"<br/>Generated: {datetime.now().strftime('%d-%b-%Y %H:%M')}",
        subtitle_style,
    )
    elements.append(subtitle)
    elements.append(Spacer(1, 0.4 * cm))
    
    # Clean dataframe for PDF
    df_pdf = dataframe.copy()
    for drop_col in ["DT"]:
        if drop_col in df_pdf.columns:
            df_pdf = df_pdf.drop(columns=[drop_col])
    
    # Calculate available width
    page_width = landscape(A4)[0] - (1.0 * cm)
    
    # Header and cell styles
    header_style = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Normal'],
        fontSize=7,
        leading=8,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
    )
    
    cell_style = ParagraphStyle(
        'CellStyle',
        parent=styles['Normal'],
        fontSize=6.5,
        leading=7,
        alignment=TA_CENTER,
    )
    
    # Build table data
    cols = list(df_pdf.columns)
    table_data = []
    
    # Headers with white text on blue background
    headers = [Paragraph(f"<b><font color='white'>{col}</font></b>", header_style) for col in cols]
    table_data.append(headers)
    
    # Data rows
    for _, row in df_pdf.iterrows():
        table_data.append([Paragraph(str(row[col]), cell_style) for col in cols])
    
    # Create table
    table = Table(table_data, repeatRows=1)
    
    # Apply table style with FSO colors
    table.setStyle(TableStyle([
        # Header styling
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        
        # Data rows styling
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 6.5),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        
        # Alternating row colors
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        
        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#1f4788')),
    ]))
    
    elements.append(table)
    
    # Build PDF
    doc.build(elements)
    return buffer.getvalue()


def render_otr_page(active_location_id: Optional[int], user: Dict[str, Any] | None):
    """Render the Out-Turn Report page with all features from old app."""
    header("Out-Turn Report")

    # Location guard
    loc, loc_label = _guard_location(active_location_id)
    if not loc:
        return

    # Display location info with refresh button
    col_info, col_refresh = st.columns([0.85, 0.15])
    with col_info:
        st.info(f"📍 **Active Location:** {loc.name} ({loc.code})")
    with col_refresh:
        if st.button("🔄 Refresh", key="otr_refresh", use_container_width=True):
            st.rerun()

    # Determine earliest/latest OTR entry dates for default filter bounds
    dmin, dmax = _get_date_bounds(loc.id)

    # Tank list - FILTERED BY LOCATION
    with get_session() as s:
        tanks_all = s.query(Tank).filter(Tank.location_id == loc.id).order_by(Tank.name).all()
    tank_name_list = [t.name for t in tanks_all]
    tank_opts = ["(All Tanks)"] + tank_name_list

    # --- Filters ---
    with st.container(border=True):
        st.caption("Live filters")
        c1, c2, c3, c4 = st.columns([0.25, 0.25, 0.25, 0.25])

        with c1:
            f_tank = st.selectbox("Tank", tank_opts, index=0, key="otr_f_tank")
        with c2:
            f_ticket = st.text_input("Ticket ID", key="otr_f_ticket")
        with c3:
            f_from = st.date_input(
                "From date",
                value=dmin,
                min_value=dmin,
                max_value=dmax,
                key="otr_f_from",
            )
        with c4:
            f_to = st.date_input(
                "To date",
                value=dmax,
                min_value=dmin,
                max_value=dmax,
                key="otr_f_to",
            )

    # --- Load OTR from DB - FILTERED BY LOCATION ---
    try:
        from models import ensure_otr_net_columns
        ensure_otr_net_columns()
    except Exception:
        pass
    rows = []
    use_tank_transactions = False
    
    # First try OTRRecord
    if OTRRecord:
        try:
            with get_session() as s:
                q = s.query(OTRRecord).filter(OTRRecord.location_id == loc.id)
                # Exclude soft-deleted records if the column exists
                if hasattr(OTRRecord, 'is_deleted'):
                    q = q.filter(OTRRecord.is_deleted != True)
                rows = q.order_by(OTRRecord.date.asc(), OTRRecord.time.asc()).all()
        except Exception:
            pass
    
    # Fallback to TankTransaction if no OTR records
    if not rows and TankTransaction:
        use_tank_transactions = True
        try:
            with get_session() as s:
                q = s.query(TankTransaction).filter(TankTransaction.location_id == loc.id)
                # Exclude soft-deleted records if the column exists
                if hasattr(TankTransaction, 'is_deleted'):
                    q = q.filter(TankTransaction.is_deleted != True)
                rows = q.order_by(TankTransaction.date.asc(), TankTransaction.time.asc()).all()
        except Exception:
            pass

    if not rows:
        st.info(f"No OTR or Tank Transaction records yet for {loc.name}.")
        st.stop()

    # --- Build dataframe from records ---
    # Build tank name lookup map for all cases
    tank_name_map = {}
    try:
        with get_session() as s:
            tanks = s.query(Tank).filter(Tank.location_id == loc.id).all()
            tank_name_map = {t.id: t.name for t in tanks}
            # Also map by string ID in case tank_id is stored as string
            for t in tanks:
                tank_name_map[str(t.id)] = t.name
    except Exception:
        pass
    
    if use_tank_transactions:
        # Map TankTransaction fields to OTR format
        # These values are already calculated and stored during transaction entry
        df = pd.DataFrame([{
            "Ticket ID": getattr(r, "ticket_id", ""),
            "Tank": (
                getattr(r, "tank_name", None) 
                or tank_name_map.get(getattr(r, "tank_id", None))
                or tank_name_map.get(str(getattr(r, "tank_id", "")))
                or f"Tank-{getattr(r, 'tank_id', 'N/A')}"
            ),
            "Date": getattr(r, "date", None),
            "Time": getattr(r, "time", None),
            "Operation": _safe_str(getattr(r, "operation", "")),
            "Dip (cm)": float(getattr(r, "dip_cm", 0.0) or 0.0),
            "Total Volume (bbl)": float(getattr(r, "tov_bbl", 0.0) or 0.0),
            "Water (cm)": float(getattr(r, "water_cm", 0.0) or 0.0),
            "Free Water (bbl)": float(getattr(r, "fw_bbl", 0.0) or 0.0),
            "GOV (bbl)": float(getattr(r, "gov_bbl", 0.0) or 0.0),
            "API @ 60°F": float(getattr(r, "api_at60", getattr(r, "api60", getattr(r, "api_60", 0.0))) or 0.0),
            "VCF": float(getattr(r, "vcf", 1.0) or 1.0),
            "GSV (bbl)": float(getattr(r, "gsv_bbl", 0.0) or 0.0),
            "BS&W Vol (bbl)": float(getattr(r, "bsw_bbl", 0.0) or 0.0),
            "NSV (bbl)": float(getattr(r, "nsv_bbl", getattr(r, "qty_bbls", 0.0)) or 0.0),
            "LT": float(getattr(r, "lt", 0.0) or 0.0),
            "MT": float(getattr(r, "mt", 0.0) or 0.0),
        } for r in rows])
    else:
        # OTRRecord format - lookup tank names if needed
        df = pd.DataFrame([{
            "Ticket ID": r.ticket_id,
            "Tank": (
                getattr(r, "tank_name", None)
                or tank_name_map.get(getattr(r, "tank_id", None))
                or tank_name_map.get(str(getattr(r, "tank_id", "")))
                or f"Tank-{getattr(r, 'tank_id', 'N/A')}"
            ),
            "Date": r.date,
            "Time": r.time,
            "Operation": _safe_str(getattr(r, "operation", None)),
            "Dip (cm)": r.dip_cm,
            "Total Volume (bbl)": r.total_volume_bbl,
            "Water (cm)": r.water_cm,
            "Free Water (bbl)": r.free_water_bbl,
            "GOV (bbl)": r.gov_bbl,
            "API @ 60°F": r.api60,
            "VCF": r.vcf,
            "GSV (bbl)": r.gsv_bbl,
            "BS&W Vol (bbl)": r.bsw_vol_bbl,
            "NSV (bbl)": r.nsv_bbl,
            "LT": r.lt,
            "MT": r.mt,
        } for r in rows])

    # Build a proper timestamp column for correct per-tank ordering
    _date = pd.to_datetime(df["Date"], errors="coerce")
    _time = pd.to_datetime(df["Time"].astype(str), errors="coerce").dt.time
    df["DT"] = [
        (datetime.combine(d.date(), t) if (pd.notna(d) and t is not pd.NaT and t is not None) else pd.NaT)
        for d, t in zip(_date, _time)
    ]

    # --- Apply filters ---
    fdf = df.copy()
    if f_tank and f_tank != "(All Tanks)":
        fdf = fdf[fdf["Tank"] == f_tank]
    if f_ticket:
        fdf = fdf[fdf["Ticket ID"].astype(str).str.contains(f_ticket.strip(), case=False, na=False)]
    if f_from:
        fdf = fdf[pd.to_datetime(fdf["Date"], errors="coerce").dt.date >= f_from]
    if f_to:
        fdf = fdf[pd.to_datetime(fdf["Date"], errors="coerce").dt.date <= f_to]

    st.caption(f"📊 Showing {len(fdf)} / {len(df)} records for **{loc.name}** | Auto-calculated from OTR records (06:01 - 06:00)")
    st.markdown("### Out-Turn Report (OTR)")
    
    columns_2dec = [
        "Dip (cm)", "Total Volume (bbl)", "Water (cm)", "Free Water (bbl)",
        "GOV (bbl)", "API @ 60°F", "GSV (bbl)", "BS&W Vol (bbl)",
        "NSV (bbl)", "LT", "MT", "Net Rece/Disp (bbls)", "Net Water Rece/Disp (bbls)"
    ]
    column_5dec = "VCF"

    # Cast/round numeric columns for display
    for col in columns_2dec:
        if col in fdf.columns:
            fdf[col] = pd.to_numeric(fdf[col], errors="coerce").round(2)
    if column_5dec in fdf.columns:
        fdf[column_5dec] = pd.to_numeric(fdf[column_5dec], errors="coerce").round(5)
    
    # --- Chronological sort (global for display) ---
    fdf = fdf.sort_values(["Date", "Time"], ascending=[True, True]).reset_index(drop=True)

    # ---------------- Tank-aware net calculations for OTR ----------------
    # Ensure source numeric columns exist
    if "NSV (bbl)" not in fdf.columns:
        fdf["NSV (bbl)"] = 0.0
    if "Free Water (bbl)" not in fdf.columns:
        fdf["Free Water (bbl)"] = 0.0

    # Cast numerics safely
    fdf["NSV (bbl)"] = pd.to_numeric(fdf["NSV (bbl)"], errors="coerce").fillna(0.0)
    fdf["Free Water (bbl)"] = pd.to_numeric(fdf["Free Water (bbl)"], errors="coerce").fillna(0.0)

    # Sort by Tank + DT so "previous" truly means previous entry of the same tank
    sort_key = pd.Series(pd.to_datetime(fdf["DT"], errors="coerce"))
    orig_index = fdf.index
    fdf_sorted = fdf.assign(__sort_time=sort_key).sort_values(
        by=["Tank", "__sort_time", orig_index.name or "__sort_time"],
        kind="mergesort"
    )

    # Per-tank previous values using groupby+shift
    prev_nsv = fdf_sorted.groupby("Tank")["NSV (bbl)"].shift(1)
    prev_fw  = fdf_sorted.groupby("Tank")["Free Water (bbl)"].shift(1)

    # Deltas = current - previous
    net_nsv  = fdf_sorted["NSV (bbl)"] - prev_nsv
    net_fw   = fdf_sorted["Free Water (bbl)"] - prev_fw

    # First entries per tank → blank
    first_of_tank_mask = prev_nsv.isna()
    net_nsv  = net_nsv.mask(first_of_tank_mask, np.nan)
    net_fw   = net_fw.mask(first_of_tank_mask, np.nan)

    # Align back to original order
    net_nsv_aligned = pd.Series(net_nsv.values, index=fdf_sorted.index).reindex(orig_index)
    net_fw_aligned  = pd.Series(net_fw.values,  index=fdf_sorted.index).reindex(orig_index)

    # Write columns; blank string for first-of-tank rows
    def _fmt_net(s):
        return s.where(~s.isna(), "")

    fdf["Net Rece/Disp (bbls)"]       = _fmt_net(pd.to_numeric(net_nsv_aligned, errors="coerce").round(2))
    fdf["Net Water Rece/Disp (bbls)"] = _fmt_net(pd.to_numeric(net_fw_aligned,  errors="coerce").round(2))

    # Cleanup helper columns
    for col in ["__sort_time", "DT"]:
        if col in fdf.columns:
            fdf.drop(columns=col, inplace=True, errors="ignore")

    # --- Display ---
    st.dataframe(fdf, use_container_width=True, hide_index=True)
    
    # --- Persist computed nets ---
    try:
        with get_session() as s:
            for _, row in fdf.iterrows():
                tid = str(row.get("Ticket ID") or "")
                if not tid:
                    continue
                rx = s.query(OTRRecord).filter(OTRRecord.location_id == loc.id, OTRRecord.ticket_id == tid).first()
                if not rx:
                    continue
                nv = row.get("Net Rece/Disp (bbls)")
                wf = row.get("Net Water Rece/Disp (bbls)")
                changed = False
                if nv != "" and nv is not None:
                    try:
                        val = float(nv)
                        if getattr(rx, "net_rece_disp_bbls", None) != val:
                            setattr(rx, "net_rece_disp_bbls", val)
                            changed = True
                    except Exception:
                        pass
                if wf != "" and wf is not None:
                    try:
                        val = float(wf)
                        if getattr(rx, "net_water_rece_disp_bbls", None) != val:
                            setattr(rx, "net_water_rece_disp_bbls", val)
                            changed = True
                    except Exception:
                        pass
                if changed:
                    try:
                        s.commit()
                    except Exception:
                        s.rollback()
    except Exception:
        pass

    # --- Export controls (CSV / XLSX / PDF) ---
    st.markdown("---")
    st.markdown("#### Export Options")
    
    ec1, ec2, ec3 = st.columns([0.25, 0.25, 0.5])

    # CSV / XLSX
    with ec1:
        fmt = st.selectbox("Download as", ["CSV", "XLSX"], index=0, key="otr_dl_fmt")
        if fmt == "CSV":
            data_bytes = fdf.to_csv(index=False).encode("utf-8")
            filename = f"OTR_{loc.code}_{f_from}_{f_to}.csv"
            st.download_button("📥 Download", data=data_bytes, file_name=filename, mime="text/csv", key="otr_dl_csv", use_container_width=True)
        else:
            bio = BytesIO()
            with pd.ExcelWriter(bio, engine="xlsxwriter") as writer:
                fdf.to_excel(writer, sheet_name="OTR", index=False)
            filename = f"OTR_{loc.code}_{f_from}_{f_to}.xlsx"
            st.download_button("⬇️ Download", data=bio.getvalue(), file_name=filename,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="otr_dl_xlsx", use_container_width=True)

    # PDF export
    import base64
    import streamlit.components.v1 as components

    with ec2:
        selected_tank = f_tank if f_tank and f_tank != "(All Tanks)" else "All Tanks"
        filter_text_parts = []
        filter_text_parts.append(f"Tank: {selected_tank}")
        if f_from: 
            filter_text_parts.append(f"From: {f_from}")
        if f_to: 
            filter_text_parts.append(f"To: {f_to}")
        if f_ticket: 
            filter_text_parts.append(f"Ticket: {f_ticket}")
        filter_text = ", ".join(filter_text_parts) if filter_text_parts else "No filters applied"

        if st.button("📄 Download PDF", key="otr_pdf_dl", use_container_width=True):
            pdf_bytes = generate_otr_pdf(fdf, selected_tank, filter_text, loc.name, loc.code)
            filename = f"OTR_{loc.code}_{f_from}_{f_to}.pdf"
            st.download_button("⬇️ Download PDF", data=pdf_bytes, file_name=filename,
                            mime="application/pdf", key="otr_pdf_dl_real", use_container_width=True)
        
        if st.button("👁️ View PDF", key="otr_pdf_view", use_container_width=True):
            pdf_bytes = generate_otr_pdf(fdf, selected_tank, filter_text, loc.name, loc.code)
            b64 = base64.b64encode(pdf_bytes).decode("utf-8")
            components.html(
                f"""
                <script>
                (function(){{
                const b64="{b64}";
                const byteChars=atob(b64);
                const byteNums=new Array(byteChars.length);
                for (let i=0;i<byteChars.length;i++) byteNums[i]=byteChars.charCodeAt(i);
                const blob=new Blob([new Uint8Array(byteNums)],{{type:'application/pdf'}});
                const url=URL.createObjectURL(blob);
                window.open(url,'_blank');
                setTimeout(()=>URL.revokeObjectURL(url),60000);
                }})();
                </script>
                """,
                height=0
            )
    
    # --- Summary Statistics ---
    st.markdown("---")
    st.markdown("#### Summary Statistics")
    
    sum_col1, sum_col2, sum_col3, sum_col4, sum_col5 = st.columns(5)
    
    sum_col1.metric("Total Records", len(fdf))
    sum_col2.metric("Total GOV (bbl)", f"{pd.to_numeric(fdf['GOV (bbl)'], errors='coerce').sum():,.2f}")
    sum_col3.metric("Total GSV (bbl)", f"{pd.to_numeric(fdf['GSV (bbl)'], errors='coerce').sum():,.2f}")
    sum_col4.metric("Total NSV (bbl)", f"{pd.to_numeric(fdf['NSV (bbl)'], errors='coerce').sum():,.2f}")
    sum_col5.metric("Avg API @ 60°F", f"{pd.to_numeric(fdf['API @ 60°F'], errors='coerce').mean():.2f}")

