# fso_operations.py
from __future__ import annotations

from datetime import date, datetime, timedelta, time as dt_time
from io import BytesIO
from typing import Any, Dict, Optional, List

import base64
import re

import pandas as pd
import streamlit as st

from db import get_session
from ui import header
from security import SecurityManager
from logger import log_error
from action_logger_utils import log_export_action

from models import (
    Location,
    FSOOperation,
    Vessel,
    LocationVessel,
)

from permission_manager import PermissionManager
from fso_config import FSOConfig
from location_manager import LocationManager

# Optional helpers – fall back to simple behaviours if not available
try:
    from dashboard_utils import (
        _st_safe_rerun,
        _deny_edit_for_lock,
        _render_remote_delete_request_ui,
        _supervisor_dropdown,
    )
except Exception:  # graceful fallbacks
    def _st_safe_rerun():
        try:
            st.rerun()
        except Exception:
            try:
                st.experimental_rerun()
            except Exception:
                pass

    def _deny_edit_for_lock(*args, **kwargs) -> bool:
        # No locking if helper not available
        return False

    def _render_remote_delete_request_ui(*args, **kwargs):
        # No remote delete workflow if helper not available
        return None

    def _supervisor_dropdown(label: str, key: str, location_id: int):
        # Fallback: no supervisor selected
        return None, None

try:
    from recycle_bin import RecycleBinManager
    def _archive_record_for_delete(session, record, resource_type, reason=None, label=None):
        try:
            user_ctx = st.session_state.get("auth_user") or {}
            username = user_ctx.get("username", "unknown")
            user_id = user_ctx.get("id")
            location_id = st.session_state.get("active_location_id")
            entry = RecycleBinManager.archive_record(
                session,
                record,
                resource_type,
                username=username,
                user_id=user_id,
                location_id=location_id,
                reason=reason,
                label=label,
            )
            try:
                SecurityManager.log_audit(
                    session,
                    username,
                    "DELETE",
                    resource_type=resource_type,
                    resource_id=str(label or getattr(record, "id", "")),
                    details=reason or f"Moved {resource_type} to Deleted Records",
                    user_id=user_id,
                    location_id=location_id,
                )
            except Exception:
                pass
            return entry
        except Exception:
            return None
except Exception:
    def _archive_record_for_delete(*args, **kwargs):
        return None

try:
    from task_manager import TaskManager, TaskStatus
except Exception:
    class _DummyTaskStatus:
        APPROVED = type("X", (), {"value": "APPROVED"})()
    class _DummyTaskManager:
        @staticmethod
        def complete_tasks_for_resource(*args, **kwargs):
            return None
    TaskManager = _DummyTaskManager()
    TaskStatus = _DummyTaskStatus()


# -------------------------------------------------------------------
# Small helper (from your old code)
# -------------------------------------------------------------------
def convert_to_time_object(time_value):
    """Convert various time formats to Python time object"""
    if isinstance(time_value, dt_time):
        return time_value
    elif isinstance(time_value, str):
        try:
            parts = time_value.split(':')
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            second = int(parts[2]) if len(parts) > 2 else 0
            return dt_time(hour, minute, second)
        except Exception:
            raise ValueError(f"Invalid time string format: {time_value}")
    elif isinstance(time_value, datetime):
        return time_value.time()
    else:
        raise TypeError(f"Cannot convert {type(time_value)} to time object")


# -------------------------------------------------------------------
# PDF generators – copied from your old FSO-Operations block
# -------------------------------------------------------------------
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER


def generate_fso_pdf(
    df,
    fso_vessel,
    date_from,
    date_to,
    total_receipts,
    total_exports,
    total_water_in,
    total_water_out,
    total_variance,
    net_water_value,
    loss_gain_value,
    total_entries,
    username,
):
    """Generate FSO OTR PDF report with enhanced formatting"""
    buffer = BytesIO()

    df = df.copy()
    if not df.empty:
        sort_key = pd.to_datetime(
            df["Date"].astype(str).str.strip() + " " + df["Time"].astype(str).str.strip(),
            errors="coerce",
        )
        date_key = pd.to_datetime(df["Date"], errors="coerce")
        sort_key = sort_key.fillna(date_key)
        df = (
            df.assign(_sort_key=sort_key)
            .sort_values("_sort_key", ascending=True)
            .drop(columns="_sort_key")
            .reset_index(drop=True)
        )

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
        f"<b>FSO OUT-TURN REPORT</b><br/><font size=14>{fso_vessel}</font>",
        title_style,
    )
    elements.append(title)
    elements.append(Spacer(1, 0.3 * cm))

    # Subtitle
    subtitle = Paragraph(
        f"Period: <b>{date_from}</b> to <b>{date_to}</b>"
        f"<br/>Generated: {datetime.now().strftime('%d-%b-%Y %H:%M')}",
        subtitle_style,
    )
    elements.append(subtitle)
    elements.append(Spacer(1, 0.4 * cm))

    # Calculate available width (page width minus margins)
    page_width = landscape(A4)[0] - (1.0 * cm)
    table_width = page_width

    # Corrected proportions (total 100%)
    col_widths = [
        table_width * 0.07,   # Date
        table_width * 0.04,   # Time
        table_width * 0.06,   # Shuttle
        table_width * 0.11,   # Vessel
        table_width * 0.09,   # Operation
        table_width * 0.06,   # Opening Stock
        table_width * 0.055,  # Opening Water
        table_width * 0.06,   # Closing Stock
        table_width * 0.055,  # Closing Water
        table_width * 0.06,   # Net R/E
        table_width * 0.055,  # Net Water
        table_width * 0.06,   # Vessel Qty
        table_width * 0.05,   # Variance
        table_width * 0.17,   # Remarks
    ]

    # header style
    header_style = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Normal'],
        fontSize=8,
        leading=9,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
    )

    # Table headers
    table_data = [[
        Paragraph("<b><font color='white'>Date</font></b>", header_style),
        Paragraph("<b><font color='white'>Time</font></b>", header_style),
        Paragraph("<b><font color='white'>Shuttle<br/>No</font></b>", header_style),
        Paragraph("<b><font color='white'>Vessel<br/>Name</font></b>", header_style),
        Paragraph("<b><font color='white'>Operation</font></b>", header_style),
        Paragraph("<b><font color='white'>Opening<br/>Stock</font></b>", header_style),
        Paragraph("<b><font color='white'>Opening<br/>Water</font></b>", header_style),
        Paragraph("<b><font color='white'>Closing<br/>Stock</font></b>", header_style),
        Paragraph("<b><font color='white'>Closing<br/>Water</font></b>", header_style),
        Paragraph("<b><font color='white'>Net<br/>R/E</font></b>", header_style),
        Paragraph("<b><font color='white'>Net<br/>Water</font></b>", header_style),
        Paragraph("<b><font color='white'>Vessel<br/>Qty</font></b>", header_style),
        Paragraph("<b><font color='white'>Variance</font></b>", header_style),
        Paragraph("<b><font color='white'>Remarks</font></b>", header_style),
    ]]

    # cell style
    cell_style = ParagraphStyle(
        'CellStyle',
        parent=styles['Normal'],
        fontSize=7,
        leading=8,
        alignment=TA_CENTER,
    )

    # Data rows
    for _, row in df.iterrows():
        operation_label = str(row.get("Operation", "")).strip().lower()
        variance_val = 0.0 if operation_label == "stock opening" else row["Variance"]
        if abs(variance_val) < 1.0:
            variance_color = '#28a745'
        elif abs(variance_val) < 10.0:
            variance_color = '#ffc107'
        else:
            variance_color = '#dc3545'

        table_data.append([
            Paragraph(row['Date'], cell_style),
            Paragraph(row['Time'], cell_style),
            Paragraph(str(row['Shuttle No']), cell_style),
            Paragraph(str(row['Vessel Name'])[:35], cell_style),
            Paragraph(str(row['Operation'])[:9], cell_style),
            Paragraph(f"{row['Opening Stock']:,.0f}", cell_style),
            Paragraph(f"{row['Opening Water']:,.0f}", cell_style),
            Paragraph(f"{row['Closing Stock']:,.0f}", cell_style),
            Paragraph(f"{row['Closing Water']:,.0f}", cell_style),
            Paragraph(
                f"<font color='{'#28a745' if row['Net R/E'] >= 0 else '#dc3545'}'>"
                f"{row['Net R/E']:,.0f}</font>",
                header_style,
            ),
            Paragraph(f"{row['Net Water']:,.0f}", cell_style),
            Paragraph(f"{row['Vessel Qty']:,.0f}", cell_style),
            Paragraph(
                f"<font color='{variance_color}'><b>{variance_val:,.1f}</b></font>",
                header_style,
            ),
            Paragraph(str(row['Remarks'])[:80] if row['Remarks'] else "-", cell_style),
        ])

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
        ('TOPPADDING', (0, 0), (-1, 0), 5),

        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 6),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#333333')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#1f4788')),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 1), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 3),
    ]))

    elements.append(table)

    # Summary
    elements.append(Spacer(1, 0.4 * cm))

    summary_style = ParagraphStyle(
        'Summary',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#333333'),
        spaceAfter=3,
    )

    summary_header_style = ParagraphStyle(
        'SummaryHeader',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.white,
        fontName='Helvetica-Bold',
        alignment=TA_CENTER,
    )

    elements.append(Paragraph("<b>SUMMARY STATISTICS</b>", summary_header_style))

    summary_data = [
        [
            Paragraph(f"<b>Total Receipts:</b> {total_receipts:,.2f} bbls", summary_style),
            Paragraph(f"<b>Total Exports:</b> {total_exports:,.2f} bbls", summary_style),
            Paragraph(f"<b>Water In:</b> {total_water_in:,.2f} bbls", summary_style),
            Paragraph(f"<b>Water Out:</b> {total_water_out:,.2f} bbls", summary_style),
        ],
        [
            Paragraph(f"<b>Net Water:</b> {net_water_value:,.2f} bbls", summary_style),
            Paragraph(
                f"<b>Loss / Gain:</b> "
                f"<font color='{'#28a745' if loss_gain_value >= 0 else '#dc3545'}'>"
                f"<b>{loss_gain_value:,.2f} bbls</b></font>",
                summary_style,
            ),
            Paragraph(
                f"<b>Total Variance:</b> "
                f"<font color='{'#28a745' if abs(total_variance) < 10 else '#dc3545'}'>"
                f"{total_variance:,.2f} bbls</font>",
                summary_style,
            ),
            Paragraph(f"<b>Total Entries:</b> {total_entries}", summary_style),
        ],
    ]

    summary_col_width = table_width / 4
    summary_table = Table(summary_data, colWidths=[summary_col_width] * 4)
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#1f4788')),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))

    elements.append(summary_table)

    # Footer
    elements.append(Spacer(1, 0.3 * cm))
    footer_text = (
        f"<font size=7 color='#666666'>Generated by: {username} | "
        f"OTMS - Oil Terminal Management System | "
        f"{datetime.now().strftime('%d-%b-%Y %H:%M:%S')}</font>"
    )
    elements.append(Paragraph(footer_text, subtitle_style))

    doc.build(elements)
    pdf_data = buffer.getvalue()
    buffer.close()

    return pdf_data


def generate_material_balance_pdf(
    df,
    fso_vessel,
    date_from,
    date_to,
    total_receipts,
    total_exports,
    total_loss_gain,
    username,
):
    """Generate Material Balance PDF report"""
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
        f"<b>FSO MATERIAL BALANCE REPORT</b><br/><font size=14>{fso_vessel}</font>",
        title_style,
    )
    elements.append(title)
    elements.append(Spacer(1, 0.3 * cm))

    # Subtitle
    subtitle = Paragraph(
        f"Period: <b>{date_from}</b> to <b>{date_to}</b>"
        f"<br/>Generated: {datetime.now().strftime('%d-%b-%Y %H:%M')}",
        subtitle_style,
    )
    elements.append(subtitle)
    elements.append(Spacer(1, 0.4 * cm))

    # Widths
    page_width = landscape(A4)[0] - (1.0 * cm)
    table_width = page_width

    col_widths = [
        table_width * 0.12,  # Date
        table_width * 0.13,  # Opening Stock
        table_width * 0.12,  # Opening Water
        table_width * 0.13,  # Receipts
        table_width * 0.13,  # Exports
        table_width * 0.13,  # Closing Stock
        table_width * 0.12,  # Closing Water
        table_width * 0.12,  # Loss/Gain
    ]

    header_style = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Normal'],
        fontSize=7,
        leading=9,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
    )

    table_data = [[
        Paragraph("<b><font color='white'>Date</font></b>", header_style),
        Paragraph("<b><font color='white'>Opening<br/>Stock</font></b>", header_style),
        Paragraph("<b><font color='white'>Opening<br/>Water</font></b>", header_style),
        Paragraph("<b><font color='white'>Receipts</font></b>", header_style),
        Paragraph("<b><font color='white'>Exports</font></b>", header_style),
        Paragraph("<b><font color='white'>Closing<br/>Stock</font></b>", header_style),
        Paragraph("<b><font color='white'>Closing<br/>Water</font></b>", header_style),
        Paragraph("<b><font color='white'>Loss/Gain</font></b>", header_style),
    ]]

    cell_style = ParagraphStyle(
        'CellStyle',
        parent=styles['Normal'],
        fontSize=7,
        leading=9,
        alignment=TA_CENTER,
    )

    for _, row in df.iterrows():
        loss_gain_val = row['Loss/Gain']
        loss_gain_color = '#28a745' if loss_gain_val >= 0 else '#dc3545'

        table_data.append([
            Paragraph(row['Date'], cell_style),
            Paragraph(f"{row['Opening Stock']:,.0f}", cell_style),
            Paragraph(f"{row['Opening Water']:,.0f}", cell_style),
            Paragraph(f"{row['Receipts']:,.0f}", cell_style),
            Paragraph(f"{row['Exports']:,.0f}", cell_style),
            Paragraph(f"{row['Closing Stock']:,.0f}", cell_style),
            Paragraph(f"{row['Closing Water']:,.0f}", cell_style),
            Paragraph(
                f"<font color='{loss_gain_color}'><b>{loss_gain_val:,.2f}</b></font>",
                cell_style,
            ),
        ])

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
        ('TOPPADDING', (0, 0), (-1, 0), 5),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#333333')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#1f4788')),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
    ]))

    elements.append(table)

    # Summary section
    elements.append(Spacer(1, 0.4 * cm))

    summary_style = ParagraphStyle(
        'Summary',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#333333'),
        spaceAfter=3,
    )

    summary_header_style = ParagraphStyle(
        'SummaryHeader',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.white,
        fontName='Helvetica-Bold',
        alignment=TA_CENTER,
    )

    loss_gain_status = "GAIN" if total_loss_gain >= 0 else "LOSS"
    loss_gain_color = '#28a745' if total_loss_gain >= 0 else '#dc3545'

    summary_data = [
        [
            Paragraph("<b>SUMMARY STATISTICS</b>", summary_header_style),
            "",
            "",
            "",
        ],
        [
            Paragraph(f"<b>Total Receipts:</b> {total_receipts:,.2f} bbls", summary_style),
            Paragraph(f"<b>Total Exports:</b> {total_exports:,.2f} bbls", summary_style),
            Paragraph(
                f"<b>Total Loss/Gain:</b> "
                f"<font color='{loss_gain_color}'>{total_loss_gain:,.2f} bbls ({loss_gain_status})</font>",
                summary_style,
            ),
            Paragraph(f"<b>Total Days:</b> {len(df)}", summary_style),
        ],
        [
            Paragraph(
                f"<b>Net Movement:</b> {(total_receipts - total_exports):,.2f} bbls",
                summary_style,
            ),
            Paragraph(
                f"<b>Avg Receipt/Day:</b> "
                f"{(total_receipts/len(df) if len(df) > 0 else 0):,.2f} bbls",
                summary_style,
            ),
            Paragraph(
                f"<b>Avg Export/Day:</b> "
                f"{(total_exports/len(df) if len(df) > 0 else 0):,.2f} bbls",
                summary_style,
            ),
            Paragraph(
                f"<b>Loss/Gain %:</b> "
                f"{(total_loss_gain/total_receipts*100 if total_receipts > 0 else 0):.3f}%",
                summary_style,
            ),
        ],
    ]

    summary_col_width = table_width / 4
    summary_table = Table(summary_data, colWidths=[summary_col_width] * 4)
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('SPAN', (0, 0), (-1, 0)),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#1f4788')),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))

    elements.append(summary_table)

    # Footer
    elements.append(Spacer(1, 0.3 * cm))
    footer_text = (
        f"<font size=7 color='#666666'>Generated by: {username} | "
        f"OTMS - Oil Terminal Management System | "
        f"{datetime.now().strftime('%d-%b-%Y %H:%M:%S')}</font>"
    )
    elements.append(Paragraph(footer_text, subtitle_style))

    doc.build(elements)
    pdf_data = buffer.getvalue()
    buffer.close()

    return pdf_data


# -------------------------------------------------------------------
# PUBLIC ENTRY: render_fso_operations_page
# (full logic copied from your old `elif page == "FSO-Operations":` block)
# -------------------------------------------------------------------
def render_fso_operations_page(active_location_id: Optional[int], user: Optional[dict]):
    """PUBLIC ENTRY — called from main_app.py"""

    header("FSO-Operations")

    # ===== Check Admin-IT access restriction =====
    if st.session_state.get("auth_user", {}).get("role") == "admin-it":
        st.error("🚫 Access Denied: Admin-IT users do not have access to operational pages.")
        st.stop()

    # ===== LocationConfig page-access guard (old code) =====
    try:
        _user_role = st.session_state.get("auth_user", {}).get("role")
        _loc_id = st.session_state.get("active_location_id")
        if _user_role not in ["admin-operations", "manager"] and _loc_id:
            from location_config import LocationConfig
            with get_session() as _s:
                _cfg = LocationConfig.get_config(_s, _loc_id)
            if _cfg.get("page_access", {}).get("FSO-Operations") is False:
                st.caption("FSO-Operations Access: **⛔ Denied**")
                st.stop()
    except Exception:
        pass

    # ============ MAIN CODE (unchanged logic) ============

    if not user:
        st.error("Please login to access this page")
        st.stop()

    # ---------- LOCATION ACCESS CHECK ----------
    if not active_location_id:
        st.error("No active location selected")
        st.stop()

    from location_config import get_location_page_visibility

    with get_session() as s:
        loc = LocationManager.get_location_by_id(s, active_location_id)
        if not loc:
            st.error("❌ Location not found.")
            st.stop()

        # Check if FSO-Operations is allowed by PermissionManager + LocationConfig
        if not PermissionManager.can_access_feature(s, active_location_id, "fso_operations", user["role"]):
            st.error("🚫 **Access Denied**")
            st.warning(f"**FSO-Operations** is not available at **{loc.name}**")

            allowed_locs = PermissionManager.get_allowed_locations_for_feature(s, "fso_operations")
            if allowed_locs:
                st.info(f"ℹ️ This feature is available at: **{', '.join(allowed_locs)}**")

            st.markdown("---")
            st.caption(f"Current Location: **{loc.name} ({loc.code})**")
            st.caption("FSO-Operations Access: **⛔ Denied**")
            st.stop()

        can_make_entries = PermissionManager.can_make_entries_user(s, user, active_location_id)
        can_delete_direct = user["role"].lower() in ["admin-operations", "supervisor"]
        can_delete_with_approval = user["role"].lower() == "operator"

    # ============ FSO VESSEL SELECTOR ============
    st.markdown("---")

    # Force FSO selection based on Asset Management assignments only (no fallback)
    try:
        with get_session() as s:
            assigned_fsos = (
                s.query(Vessel)
                .join(LocationVessel, LocationVessel.vessel_id == Vessel.id)
                .filter(
                    LocationVessel.location_id == active_location_id,
                    LocationVessel.is_active == True,
                    Vessel.vessel_type == "FSO",
                    (Vessel.status == "ACTIVE")
                )
                .order_by(Vessel.name.asc())
                .all()
            )
    except Exception:
        assigned_fsos = []

    vessel_options = [v.name for v in assigned_fsos] if assigned_fsos else []

    col1, col2 = st.columns([0.7, 0.3])
    with col1:
        st.info(f"📍 **Active Location:** {loc.name} ({loc.code})")

    if vessel_options:
        with col2:
            if "selected_fso_vessel" not in st.session_state:
                st.session_state.selected_fso_vessel = vessel_options[0]
            selected_fso = st.selectbox(
                "⛴️ Select FSO Vessel",
                options=vessel_options,
                index=(
                    vessel_options.index(st.session_state.selected_fso_vessel)
                    if st.session_state.get("selected_fso_vessel") in vessel_options
                    else 0
                ),
                key="fso_vessel_selector",
            )
            st.session_state.selected_fso_vessel = selected_fso
    else:
        with col2:
            st.info("⛴️ **FSO Vessel:** N/A")
            st.warning("No FSO assigned to this location. Add it in Asset Management.")
        st.session_state.selected_fso_vessel = "N/A"

    st.markdown("---")
    st.success(f"✅ **Active FSO:** {st.session_state.selected_fso_vessel}")
    no_fso_assigned = (st.session_state.selected_fso_vessel == "N/A")

    # ============ VESSEL DROPDOWN OPTIONS FOR OTR ============
    try:
        with get_session() as s:
            assigned_vessels_query = (
                s.query(Vessel)
                .join(LocationVessel, LocationVessel.vessel_id == Vessel.id)
                .filter(
                    LocationVessel.location_id == active_location_id,
                    LocationVessel.is_active == True,
                    Vessel.status == "ACTIVE",
                )
                .order_by(Vessel.name)
                .all()
            )
    except Exception as ex:
        st.error(f"❌ Failed to load vessels for this location: {ex}")
        assigned_vessels_query = []

    vessel_name_options = [v.name for v in assigned_vessels_query] if assigned_vessels_query else []

    # ============ TABS ============
    tab_otr, tab_material_balance = st.tabs(["🧾 OTR", "📊 Material Balance"])

    # -------------------------------------------------------------------
    # TAB 1: OTR
    # (body lifted directly from your old code, with no logic changes)
    # -------------------------------------------------------------------
    from html import escape
    import traceback

    with tab_otr:
        st.markdown(f"### 🧾 FSO Out-Turn Report - {st.session_state.selected_fso_vessel}")
        st.caption("Record vessel operations and stock movements")
        
        # ========== FILTERS ==========
        st.markdown("#### 🔎 Filters")
        
        filter_col1, filter_col2, filter_col3, filter_col4, filter_col5 = st.columns(5)
        
        with filter_col1:
            filter_date_from = st.date_input(
                "From Date",
                value=date.today() - timedelta(days=30),
                max_value=date.today(),
                key="fso_otr_date_from"
            )
        
        with filter_col2:
            filter_date_to = st.date_input(
                "To Date",
                value=date.today(),
                max_value=date.today(),
                key="fso_otr_date_to"
            )
        
        with filter_col3:
            filter_shuttle = st.text_input(
                "Shuttle No",
                placeholder="Search...",
                key="fso_otr_filter_shuttle"
            )
        
        with filter_col4:
            filter_vessel = st.text_input(
                "Vessel Name",
                placeholder="Search...",
                key="fso_otr_filter_vessel"
            )
        
        with filter_col5:
            filter_operation = st.selectbox(
                "Operation",
                ["All", "Receipt", "Export", "Stock Opening"],
                key="fso_otr_filter_operation"
            )
        
        st.markdown("---")
        
        # ========== ADD NEW ENTRY ==========
        if can_make_entries and not no_fso_assigned:
            with st.expander("➕ Add New Entry", expanded=False):
                with st.form("add_fso_entry_form", clear_on_submit=True):
                    st.markdown(f"##### New FSO Entry - {st.session_state.selected_fso_vessel}")
                    
                    form_col1, form_col2, form_col3, form_col4 = st.columns(4)
                    
                    with form_col1:
                        entry_date = st.date_input("Date *", value=date.today(), max_value=date.today(), key="fso_new_date")
                        entry_time_input = st.text_input(
                            "Time * (HH:MM)",
                            value=datetime.now().strftime("%H:%M"),
                            placeholder="HH:MM",
                            key="fso_new_time"
                        )
                        entry_shuttle = st.text_input("Shuttle No *", placeholder="SH-001", key="fso_new_shuttle")
                    
                    with form_col2:
                        # Vessel name from vessels assigned to this location
                        if vessel_name_options:
                            entry_vessel = st.selectbox(
                                "Vessel Name *",
                                options=vessel_name_options,
                                key="fso_new_vessel",
                            )
                        else:
                            # Fallback to manual entry if no vessels are assigned yet
                            entry_vessel = st.text_input(
                                "Vessel Name *",
                                placeholder="MT Vessel",
                                key="fso_new_vessel",
                            )
                            st.caption(
                                "No vessels assigned to this location. "
                                "Assign vessels in Asset Management → Location Vessel Mapping to enable dropdown."
                            )

                        try:
                            with get_session() as s_ops:
                                from location_config import list_operations
                                op_rows = list_operations(s_ops, active_location_id, asset="fso", category="Operation")
                                op_options = [r["name"] for r in op_rows if r.get("active", True)]
                        except Exception:
                            op_options = []
                        if not op_options:
                            op_options = ["Receipt", "Export", "Stock Opening"]
                        entry_operation = st.selectbox(
                            "Operation *",
                            op_options,
                            key="fso_new_operation",
                        )
                        entry_vessel_qty = st.number_input(
                            "Vessel Quantity (bbls)",
                            min_value=0.0,
                            step=0.01,
                            key="fso_new_vessel_qty",
                        )

                    
                    with form_col3:
                        entry_opening = st.number_input("Opening Stock (bbls) *", min_value=0.0, step=0.01, key="fso_new_opening")
                        entry_opening_water = st.number_input("Opening Water (bbls)", min_value=0.0, step=0.01, value=0.0, key="fso_new_opening_water")
                        entry_closing = st.number_input("Closing Stock (bbls) *", min_value=0.0, step=0.01, key="fso_new_closing")
                    
                    with form_col4:
                        entry_closing_water = st.number_input("Closing Water (bbls)", min_value=0.0, step=0.01, value=0.0, key="fso_new_closing_water")
                    
                    entry_remarks = st.text_area("Remarks", key="fso_new_remarks", max_chars=500)
                    
                    # Calculate values
                    net_stock = entry_closing - entry_opening
                    net_water = entry_closing_water - entry_opening_water
                    abs_net_stock = abs(net_stock)
                    variance = abs_net_stock - entry_vessel_qty if entry_vessel_qty > 0 else 0.0
                    
                    # Display calculations
                    calc_col1, calc_col2, calc_col3 = st.columns(3)
                    
                    with calc_col1:
                        if net_stock >= 0:
                            st.success(f"**Net Stock:** +{net_stock:,.2f} bbls")
                        else:
                            st.info(f"**Net Stock:** {net_stock:,.2f} bbls")
                    
                    with calc_col2:
                        if net_water >= 0:
                            st.success(f"**Net Water:** +{net_water:,.2f} bbls")
                        else:
                            st.info(f"**Net Water:** {net_water:,.2f} bbls")
                    
                    with calc_col3:
                        if abs(variance) < 1.0:
                            st.success(f"**Variance:** {variance:,.2f} bbls ✅")
                        elif abs(variance) < 10.0:
                            st.warning(f"**Variance:** {variance:,.2f} bbls ⚠️")
                        else:
                            st.error(f"**Variance:** {variance:,.2f} bbls ❌")
                    
                    submit_btn = st.form_submit_button("💾", type="primary", use_container_width=True, help="Save Entry", disabled=not can_make_entries)
                    
                    if submit_btn:
                        time_text = (entry_time_input or "").strip()
                        if not entry_shuttle.strip():
                            st.error("Shuttle No is required")
                        elif not entry_vessel.strip():
                            st.error("Vessel Name is required")
                        elif not time_text:
                            st.error("Time is required")
                        else:
                            try:
                                entry_time_obj = convert_to_time_object(time_text)
                            except Exception:
                                st.error("Enter time in HH:MM (24h) format")
                            else:
                                try:
                                    with get_session() as s:
                                        new_entry = FSOOperation(
                                            location_id=active_location_id,
                                            fso_vessel=st.session_state.selected_fso_vessel,
                                            date=entry_date,
                                            time=entry_time_obj,
                                            shuttle_no=entry_shuttle.strip(),
                                            vessel_name=entry_vessel.strip(),
                                            operation=entry_operation,
                                            opening_stock=float(entry_opening),
                                            opening_water=float(entry_opening_water),
                                            closing_stock=float(entry_closing),
                                            closing_water=float(entry_closing_water),
                                            net_receipt_dispatch=float(net_stock),
                                            net_water=float(net_water),
                                            vessel_quantity=float(entry_vessel_qty) if entry_vessel_qty > 0 else None,
                                            variance=float(variance) if entry_vessel_qty > 0 else None,
                                            remarks=entry_remarks.strip() if entry_remarks else None,
                                            created_by=user["username"],
                                            created_at=datetime.now(),
                                        )
                                        
                                        s.add(new_entry)
                                        # Ensure ID is generated before audit logging
                                        s.flush()
                                        
                                        from security import SecurityManager
                                        SecurityManager.log_audit(
                                            s,
                                            user["username"],
                                            "CREATE",
                                            resource_type="FSOOperation",
                                            resource_id=str(new_entry.id),
                                            location_id=active_location_id,
                                            details=f"FSO: {st.session_state.selected_fso_vessel}, Vessel: {entry_vessel}",
                                            user_id=user.get("id"),
                                        )
                                        s.commit()
                                        new_id = new_entry.id
                                    st.success(f"Entry saved! ID: {new_id}")
                                    st.balloons()
                                    import time
                                    time.sleep(1)
                                    _st_safe_rerun()
                            
                                except Exception as ex:
                                    st.error(f"Failed to save: {ex}")
                                    import traceback
                                    with st.expander("⚠️ Error Details"):
                                        st.code(traceback.format_exc())
        else:
            if no_fso_assigned:
                st.info("ℹ️ No FSO assigned to this location. Add it in Asset Management.")
            else:
                st.info("ℹ️ You don't have permission to add entries")
        
        st.markdown("---")

        
        # ========== LOAD AND DISPLAY DATA ==========
        if no_fso_assigned:
            st.info("No data to display — no FSO assigned to this location.")
            st.stop()
        try:
            with get_session() as s:
                query = s.query(FSOOperation).filter(
                    FSOOperation.location_id == active_location_id,
                    FSOOperation.fso_vessel == st.session_state.selected_fso_vessel,
                    FSOOperation.date >= filter_date_from,
                    FSOOperation.date <= filter_date_to
                )
                
                if filter_shuttle:
                    query = query.filter(FSOOperation.shuttle_no.contains(filter_shuttle))
                
                if filter_vessel:
                    query = query.filter(FSOOperation.vessel_name.contains(filter_vessel))
                
                if filter_operation != "All":
                    query = query.filter(FSOOperation.operation == filter_operation)
                
                entries = query.order_by(FSOOperation.date.desc(), FSOOperation.time.desc()).all()
            
            if not entries:
                st.info(f"ℹ️ No entries found for **{st.session_state.selected_fso_vessel}**. Add your first entry above!")
            else:
                st.markdown(f"#### ⛴️ FSO Entries ({len(entries)} records)")
                
                # Create DataFrame for full data (used in PDF)
                data = []
                for entry in entries:
                    try:
                        if isinstance(entry.time, dt_time):
                            time_str = entry.time.strftime("%H:%M")
                        elif isinstance(entry.time, str):
                            time_str = entry.time
                        else:
                            time_str = str(entry.time)
                    except:
                        time_str = "N/A"
                    
                    vessel_qty = float(entry.vessel_quantity or 0.0)
                    net_re = float(entry.net_receipt_dispatch or 0.0)
                    display_variance = abs(net_re) - vessel_qty

                    data.append({
                        "ID": entry.id,
                        "Date": entry.date.strftime("%Y-%m-%d"),
                        "Time": time_str,
                        "Shuttle No": entry.shuttle_no,
                        "Vessel Name": entry.vessel_name,
                        "Operation": entry.operation,
                        "Opening Stock": entry.opening_stock,
                        "Opening Water": getattr(entry, 'opening_water', 0.0),
                        "Closing Stock": entry.closing_stock,
                        "Closing Water": getattr(entry, 'closing_water', 0.0),
                        "Net R/E": entry.net_receipt_dispatch,
                        "Net Water": getattr(entry, 'net_water', 0.0),
                        "Vessel Qty": vessel_qty,
                        "Variance": display_variance,
                        "Remarks": entry.remarks if entry.remarks else "",
                        "Created By": entry.created_by,
                        "Updated By": getattr(entry, 'updated_by', None),
                        "Updated At": getattr(entry, 'updated_at', None)
                    })

                df = pd.DataFrame(data)
                if not df.empty:
                    sort_key = pd.to_datetime(
                        df["Date"].astype(str).str.strip() + " " + df["Time"].astype(str).str.strip(),
                        errors="coerce",
                    )
                    date_key = pd.to_datetime(df["Date"], errors="coerce")
                    sort_key = sort_key.fillna(date_key)
                    df = (
                        df.assign(_sort_key=sort_key)
                        .sort_values("_sort_key", ascending=True)
                        .drop(columns="_sort_key")
                        .reset_index(drop=True)
                    )
            
                # ========== ULTRA-COMPACT TABLE DISPLAY ==========
                
                st.markdown("---")
                
                # Table header
                st.markdown("""
                    <style>
                    .compact-table {
                        font-size: 0.85rem;
                        line-height: 1.4;
                    }
                    .table-header {
                        background: #1f4788;
                        color: white;
                        font-weight: bold;
                        padding: 8px;
                        border-radius: 5px 5px 0 0;
                    }
                    .table-row {
                        border: 1px solid #dee2e6;
                        padding: 8px;
                        margin-bottom: 5px;
                        border-radius: 5px;
                        background: white;
                        transition: background 0.2s;
                    }
                    .table-row:hover {
                        background: #f8f9fa;
                    }
                    </style>
                """, unsafe_allow_html=True)
                
                # Display each entry as a single compact row
                for idx, row in df.iterrows():
                    entry_id = row["ID"]
                    
                    # Build variance badge
                    variance_val = row['Variance']
                    if abs(variance_val) < 1.0:
                        var_color = "#28a745"
                        var_icon = "?"
                    elif abs(variance_val) < 10.0:
                        var_color = "#ffc107"
                        var_icon = "⚠️"
                    else:
                        var_color = "#dc3545"
                        var_icon = "?"
                    
                    # Build net R/E color
                    net_val = row['Net R/E']
                    net_color = "#28a745" if net_val >= 0 else "#dc3545"
                    net_sign = "+" if net_val >= 0 else ""
                    
                    with st.container():
                        # Single row with all info
                        col1, col2, col3, col4, col5, col6, col7, col8, col9 = st.columns([1, 1.2, 1.5, 1, 1, 1, 1, 1.5, 0.8])
                        
                        with col1:
                            date_label = escape(str(row["Date"]))
                            creator_val = row.get("Created By")
                            if isinstance(creator_val, str):
                                creator_val = creator_val.strip()
                            creator_display = "-" if not creator_val else escape(str(creator_val))
                            updated_by = row.get("Updated By")
                            updated_at = row.get("Updated At")
                            badge_html = ""
                            if updated_by:
                                tooltip_ts = ""
                                if updated_at:
                                    try:
                                        tooltip_ts = pd.to_datetime(updated_at).strftime("%Y-%m-%d %H:%M")
                                    except Exception:
                                        tooltip_ts = str(updated_at)
                                tooltip_text = f"Edited by {updated_by}"
                                if tooltip_ts:
                                    tooltip_text += f" on {tooltip_ts}"
                                badge_html = f" <span style='color:#f59e0b;' title='{escape(tooltip_text, quote=True)}'>⚠️</span>"
                            user_line = f"By {creator_display}{badge_html}"
                            st.markdown(
                                f"**{date_label}**<br/><span style='color:#6b7280; font-size:0.75rem;'>{user_line}</span>",
                                unsafe_allow_html=True
                            )
                        
                        with col2:
                            st.markdown(f"**Shuttle:**<br/>{row['Shuttle No']}", unsafe_allow_html=True)
                        
                        with col3:
                            st.markdown(f"**Vessel:**<br/>{row['Vessel Name'][:25]}", unsafe_allow_html=True)
                        
                        with col4:
                            st.markdown(f"**Open:**<br/><span style='color: #666;'>{row['Opening Stock']:,.0f}</span>", unsafe_allow_html=True)
                        
                        with col5:
                            st.markdown(f"**Close:**<br/><span style='color: #666;'>{row['Closing Stock']:,.0f}</span>", unsafe_allow_html=True)
                        
                        with col6:
                            st.markdown(f"**Net R/E:**<br/><span style='color: {net_color}; font-weight: bold;'>{net_sign}{net_val:,.0f}</span>", unsafe_allow_html=True)
                        
                        with col7:
                            st.markdown(f"**Variance:**<br/><span style='color: {var_color}; font-weight: bold;'>{variance_val:,.1f} {var_icon}</span>", unsafe_allow_html=True)
                        
                        with col8:
                            if row['Remarks']:
                                st.markdown(f"**Remarks:**<br/><span style='color: #666; font-size: 0.8rem;'>{row['Remarks'][:40]}...</span>", unsafe_allow_html=True)
                            else:
                                st.markdown("**Remarks:**<br/><span style='color: #999;'>-</span>", unsafe_allow_html=True)
                        
                        with col9:
                            # Action buttons
                            btn_col1, btn_col2 = st.columns(2)
                            
                            with btn_col1:
                                if st.button("✏️", key=f"edit_fso_{entry_id}", help="Edit", use_container_width=True, disabled=not can_make_entries):
                                    allow_edit = True
                                    with get_session() as _lock_s:
                                        entry_obj = (
                                            _lock_s.query(FSOOperation)
                                            .filter(FSOOperation.id == entry_id)
                                            .one_or_none()
                                        )
                                        if entry_obj and _deny_edit_for_lock(
                                            entry_obj,
                                            "FSOOperation",
                                            f"{entry_obj.vessel_name or entry_obj.id}",
                                        ):
                                            allow_edit = False
                                    if allow_edit:
                                        st.session_state[f"editing_fso_{entry_id}"] = True
                                        _st_safe_rerun()
                            
                            with btn_col2:
                                if (can_delete_direct or can_delete_with_approval) and can_make_entries:
                                    if st.button("🗑️", key=f"delete_fso_{entry_id}", help="Delete", use_container_width=True, disabled=not can_make_entries):
                                        st.session_state[f"confirm_delete_fso_{entry_id}"] = True
                                        _st_safe_rerun()
                        
                        # Edit form (expands below when clicked)
                        if st.session_state.get(f"editing_fso_{entry_id}", False):
                            st.markdown("---")
                            with st.form(f"edit_form_fso_{entry_id}"):
                                st.markdown("#### ✏️ Edit Entry")
                                
                                with get_session() as s:
                                    original_entry = s.query(FSOOperation).filter(FSOOperation.id == entry_id).first()

                                if original_entry and _deny_edit_for_lock(
                                    original_entry,
                                    "FSOOperation",
                                    f"{original_entry.vessel_name or entry_id}",
                                ):
                                    st.session_state.pop(f"editing_fso_{entry_id}", None)
                                    _st_safe_rerun()
                                
                                ecol1, ecol2, ecol3, ecol4 = st.columns(4)
                                
                                with ecol1:
                                    edit_date = st.date_input("Date", value=original_entry.date, max_value=date.today())
                                    try:
                                        if isinstance(original_entry.time, dt_time):
                                            time_val = original_entry.time
                                        else:
                                            time_val = convert_to_time_object(original_entry.time)
                                    except:
                                        time_val = datetime.now().time()
                                    
                                    edit_time = st.text_input(
                                        "Time (HH:MM)",
                                        value=time_val.strftime("%H:%M"),
                                        key=f"fso_edit_time_{entry_id}"
                                    )
                                    edit_shuttle = st.text_input("Shuttle No", value=original_entry.shuttle_no)
                                
                                with ecol2:
                                    edit_vessel = st.text_input("Vessel Name", value=original_entry.vessel_name)
                                    edit_operation = st.selectbox("Operation", ["Receipt", "Export", "Stock Opening"], 
                                                                 index=["Receipt", "Export", "Stock Opening"].index(original_entry.operation) if original_entry.operation in ["Receipt", "Export", "Stock Opening"] else 0)
                                    edit_vessel_qty = st.number_input("Vessel Qty", value=float(original_entry.vessel_quantity) if original_entry.vessel_quantity else 0.0)
                                
                                with ecol3:
                                    edit_opening = st.number_input("Opening Stock", value=float(original_entry.opening_stock))
                                    edit_opening_water = st.number_input("Opening Water", value=float(getattr(original_entry, 'opening_water', 0.0)))
                                    edit_closing = st.number_input("Closing Stock", value=float(original_entry.closing_stock))
                                
                                with ecol4:
                                    edit_closing_water = st.number_input("Closing Water", value=float(getattr(original_entry, 'closing_water', 0.0)))
                                
                                edit_remarks = st.text_area("Remarks", value=original_entry.remarks if original_entry.remarks else "")
                                
                                new_net_stock = edit_closing - edit_opening
                                new_net_water = edit_closing_water - edit_opening_water
                                new_variance = abs(new_net_stock) - edit_vessel_qty if edit_vessel_qty > 0 else 0.0
                                
                                st.info(f"Net Stock: {new_net_stock:,.2f} | Net Water: {new_net_water:,.2f} | Variance: {new_variance:,.2f}")
                                
                                save_col, cancel_col = st.columns(2)
                                
                                with save_col:
                                    if st.form_submit_button("💾", type="primary", use_container_width=True, help="Save Changes", disabled=not can_make_entries):
                                        time_text = (edit_time or "").strip()
                                        parsed_time = None
                                        if not time_text:
                                            st.error("Time is required")
                                        else:
                                            try:
                                                parsed_time = convert_to_time_object(time_text)
                                            except Exception:
                                                st.error("Enter time in HH:MM (24h) format")
                                        if parsed_time:
                                            try:
                                                with get_session() as s:
                                                    entry_to_update = s.query(FSOOperation).filter(FSOOperation.id == entry_id).first()
                                                    
                                                    entry_to_update.date = edit_date
                                                    entry_to_update.time = parsed_time
                                                    entry_to_update.shuttle_no = edit_shuttle
                                                    entry_to_update.vessel_name = edit_vessel
                                                    entry_to_update.operation = edit_operation
                                                    entry_to_update.opening_stock = float(edit_opening)
                                                    entry_to_update.opening_water = float(edit_opening_water)
                                                    entry_to_update.closing_stock = float(edit_closing)
                                                    entry_to_update.closing_water = float(edit_closing_water)
                                                    entry_to_update.net_receipt_dispatch = float(new_net_stock)
                                                    entry_to_update.net_water = float(new_net_water)
                                                    entry_to_update.vessel_quantity = float(edit_vessel_qty) if edit_vessel_qty > 0 else None
                                                    entry_to_update.variance = float(new_variance) if edit_vessel_qty > 0 else None
                                                    entry_to_update.remarks = edit_remarks.strip() if edit_remarks else None
                                                    entry_to_update.updated_by = user["username"]
                                                    entry_to_update.updated_at = datetime.now()
                                                    
                                                    s.commit()
                                                    
                                                    # ----------------------- Audit log for FSO operation update -----------------------
                                                    try:
                                                        from security import SecurityManager  # type: ignore
                                                        user_ctx = st.session_state.get("auth_user") or {}
                                                        username = user_ctx.get("username", "unknown")
                                                        user_id = user_ctx.get("id")
                                                        location_id = active_location_id
                                                        res_id = str(entry_to_update.id)
                                                        SecurityManager.log_audit(
                                                            None,
                                                            username,
                                                            "UPDATE",
                                                            resource_type="FSOOperation",
                                                            resource_id=res_id,
                                                            details=f"Updated FSO operation {res_id}",
                                                            user_id=user_id,
                                                            location_id=location_id,
                                                        )
                                                    except Exception:
                                                        pass
                                                    
                                                    st.success("Entry updated!")
                                                    del st.session_state[f"editing_fso_{entry_id}"]
                                                    import time
                                                    time.sleep(1)
                                                    _st_safe_rerun()
                                            
                                            except Exception as ex:
                                                st.error(f"Update failed: {ex}")
                                
                                with cancel_col:
                                    if st.form_submit_button("❌", use_container_width=True):
                                        del st.session_state[f"editing_fso_{entry_id}"]
                                        _st_safe_rerun()
                        
                        # Delete confirmation (expands below when clicked)
                        if st.session_state.get(f"confirm_delete_fso_{entry_id}", False):
                            st.markdown("---")
                            st.warning("⚠️ **Confirm Delete**")
                            
                            def _execute_fso_delete(approver_label: str):
                                try:
                                    # Delete the entry and capture details before deletion
                                    with get_session() as s:
                                        entry_to_delete = s.query(FSOOperation).filter(FSOOperation.id == entry_id).first()
                                        del_details = ""
                                        if entry_to_delete:
                                            del_details = (
                                                f"{entry_to_delete.vessel_name or 'Unknown'} - {entry_to_delete.shuttle_no or ''}"
                                            )
                                            _archive_record_for_delete(
                                                s,
                                                entry_to_delete,
                                                "FSOOperation",
                                                reason=f"Marked FSO operation {del_details} for deletion. Approved by {approver_label}.",
                                                label=str(entry_id),
                                            )
                                        s.commit()
                                    TaskManager.complete_tasks_for_resource(
                                        "FSOOperation",
                                        entry_id,
                                        user.get("username", "unknown"),
                                        notes=f"Approved by {approver_label}",
                                    )
                                    st.success("Entry moved to Deleted Records")
                                    del st.session_state[f"confirm_delete_fso_{entry_id}"]
                                    import time

                                    time.sleep(1)
                                    _st_safe_rerun()
                                except Exception as ex:
                                    st.error(f"Delete failed: {ex}")

                            if can_delete_direct:
                                st.write("Are you sure you want to delete this entry?")
                                del_col1, del_col2 = st.columns(2)

                                with del_col1:
                                    if st.button("🗑️", key=f"confirm_del_{entry_id}", type="primary", use_container_width=True, help="Delete", disabled=not can_make_entries):
                                        approver_name = user.get("username", "admin")
                                        _execute_fso_delete(f"{approver_name} ({user.get('role')})")

                                with del_col2:
                                    if st.button("❌", key=f"cancel_del_{entry_id}", use_container_width=True, help="Cancel"):
                                        del st.session_state[f"confirm_delete_fso_{entry_id}"]
                                        _st_safe_rerun()

                            elif can_delete_with_approval:
                                remote_task = _render_remote_delete_request_ui(
                                    "FSOOperation",
                                    entry_id,
                                    f"FSO entry #{entry_id}",
                                    "FSO Operations",
                                    metadata={
                                        "date": row["Date"],
                                        "shuttle": row["Shuttle No"],
                                        "vessel": row["Vessel Name"],
                                    },
                                )
                                if remote_task and remote_task.get("status") == TaskStatus.APPROVED.value:
                                    approver_label = remote_task.get("approved_by") or "Supervisor"
                                    if st.button(
                                        "🗑️",
                                        
                                        key=f"fso_remote_delete_{entry_id}",
                                        type="primary",
                                        use_container_width=True,
                                        help="Delete (approved request)",
                                    ):
                                        _execute_fso_delete(f"{approver_label} (remote)")

                                st.write("Enter supervisor code to confirm deletion:")

                                with st.form(f"delete_confirm_fso_{entry_id}"):
                                    sup_username, sup_label = _supervisor_dropdown(
                                        "Supervisor",
                                        f"fso_delete_sup_{entry_id}",
                                        active_location_id,
                                    )
                                    supervisor_code = st.text_input("Supervisor Code", type="password")

                                    del_col1, del_col2 = st.columns(2)

                                    with del_col1:
                                        if st.form_submit_button("🗑️", type="primary", use_container_width=True, help="Confirm Delete", disabled=not can_make_entries):
                                            if not supervisor_code:
                                                st.error("Supervisor code is required.")
                                            elif not sup_username:
                                                st.error("No supervisor available for approval.")
                                            elif SecurityManager.verify_supervisor_code(supervisor_code, sup_username):
                                                label = sup_label or sup_username or "Supervisor"
                                                _execute_fso_delete(f"{label}")
                                            else:
                                                st.error("Invalid supervisor code!")

                                    with del_col2:
                                        if st.form_submit_button("❌", use_container_width=True, help="Cancel"):
                                            del st.session_state[f"confirm_delete_fso_{entry_id}"]
                                            _st_safe_rerun()
                        
                        st.markdown("---")
                
                # Summary statistics
                st.markdown("---")
                st.markdown("#### 📊 Summary")

                def _normalize_operation_value(value):
                    return (str(value).strip().lower()) if value else ""

                def _safe_float(value):
                    try:
                        return float(value or 0.0)
                    except (TypeError, ValueError):
                        return 0.0

                total_receipts = sum(
                    max(_safe_float(e.net_receipt_dispatch), 0.0)
                    for e in entries
                    if _normalize_operation_value(e.operation) == "receipt"
                )
                total_exports = sum(
                    abs(_safe_float(e.net_receipt_dispatch))
                    for e in entries
                    if _normalize_operation_value(e.operation) == "export"
                )
                total_water_in = sum(
                    _safe_float(getattr(e, 'net_water', 0.0))
                    for e in entries
                    if _safe_float(getattr(e, 'net_water', 0.0)) > 0
                )
                total_water_out = sum(
                    abs(_safe_float(getattr(e, 'net_water', 0.0)))
                    for e in entries
                    if _safe_float(getattr(e, 'net_water', 0.0)) < 0
                )
                loss_gain_value = sum(
                    _safe_float(e.net_receipt_dispatch)
                    for e in entries
                    if _normalize_operation_value(e.operation) == "stock opening"
                )
                net_water_value = total_water_in - total_water_out
                total_entries = len(entries)

                total_variance = 0.0
                for entry in entries:
                    if _normalize_operation_value(entry.operation) == "export":
                        continue
                    vessel_qty = _safe_float(entry.vessel_quantity)
                    net_val = _safe_float(entry.net_receipt_dispatch)
                    total_variance += abs(net_val) - vessel_qty

                row1_cols = st.columns(4)
                row1_cols[0].metric("Total Receipts", f"{total_receipts:,.2f} bbls")
                row1_cols[1].metric("Total Exports", f"{total_exports:,.2f} bbls")
                row1_cols[2].metric("Water In", f"{total_water_in:,.2f} bbls")
                row1_cols[3].metric("Water Out", f"{total_water_out:,.2f} bbls")

                row2_cols = st.columns(4)
                row2_cols[0].metric("Net Water", f"{net_water_value:,.2f} bbls")
                row2_cols[1].metric("Loss / Gain", f"{loss_gain_value:,.2f} bbls")
                variance_abs = abs(total_variance)
                variance_delta = "Good" if variance_abs < 1.0 else "OK" if variance_abs < 10.0 else "Check"
                row2_cols[2].metric("Total Variance", f"{total_variance:,.2f} bbls", delta=variance_delta)
                row2_cols[3].metric("Total Entries", f"{total_entries}")
                
                # Export options
                st.markdown("---")
                st.markdown("#### 📤 Export")
                
                export_col1, export_col2, export_col3, export_col4 = st.columns(4)
                
                with export_col1:
                    csv = df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Download CSV",
                        data=csv,
                        file_name=f"FSO_OTR_{st.session_state.selected_fso_vessel}_{date.today()}.csv",
                        mime="text/csv",
                        on_click=lambda: log_export_action("FSO-OTR", "CSV", len(df), user, active_location_id)
                    )
                
                with export_col2:
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False, sheet_name='FSO OTR')
                    excel_data = output.getvalue()
                    
                    st.download_button(
                        label="⬇️ Download Excel",
                        data=excel_data,
                        file_name=f"FSO_OTR_{st.session_state.selected_fso_vessel}_{date.today()}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        on_click=lambda: log_export_action("FSO-OTR", "XLSX", len(df), user, active_location_id)
                    )
                
                with export_col3:
                    if st.button("📥", use_container_width=True, help="Download PDF"):
                        try:
                            pdf_data = generate_fso_pdf(
                                df,
                                st.session_state.selected_fso_vessel,
                                filter_date_from.strftime("%d-%b-%Y"),
                                filter_date_to.strftime("%d-%b-%Y"),
                                total_receipts,
                                total_exports,
                                total_water_in,
                                total_water_out,
                                total_variance,
                                net_water_value,
                                loss_gain_value,
                                total_entries,
                                user["username"],
                            )
                            
                            st.download_button(
                                label="💾",
                                data=pdf_data,
                                file_name=f"FSO_OTR_{st.session_state.selected_fso_vessel}_{date.today()}.pdf",
                                mime="application/pdf",
                                key="download_pdf_btn",
                                on_click=lambda: log_export_action("FSO-OTR", "PDF", len(df), user, active_location_id)
                            )
                        except Exception as ex:
                            st.error(f"PDF generation failed: {ex}")
                
                with export_col4:
                    if st.button("👁️", key="fso_otr_pdf_view", use_container_width=True, help="View PDF"):
                        try:
                            pdf_data = generate_fso_pdf(
                                df,
                                st.session_state.selected_fso_vessel,
                                filter_date_from.strftime("%d-%b-%Y"),
                                filter_date_to.strftime("%d-%b-%Y"),
                                total_receipts,
                                total_exports,
                                total_water_in,
                                total_water_out,
                                total_variance,
                                net_water_value,
                                loss_gain_value,
                                total_entries,
                                user["username"],
                            )
                            
                            # Encode to base64
                            base64_pdf = base64.b64encode(pdf_data).decode('utf-8')
                            
                            # JavaScript to open in new tab
                            pdf_html = f"""
                            <script>
                                var pdfWindow = window.open("");
                                pdfWindow.document.write(
                                    '<html><head><title>FSO OTR Report - {st.session_state.selected_fso_vessel}</title></head>' +
                                    '<body style="margin:0"><iframe width="100%" height="100%" src="data:application/pdf;base64,{base64_pdf}"></iframe></body></html>'
                                );
                            </script>
                            """
                            
                            import streamlit.components.v1 as components
                            components.html(pdf_html, height=0)
                            st.success("PDF opened in new tab!")
                            
                        except Exception as ex:
                            st.error(f"PDF generation failed: {ex}")
                            import traceback
                            with st.expander("⚠️ Error Details"):
                                st.code(traceback.format_exc())
        
        except Exception as ex:
            st.error(f"Failed to load: {ex}")
            import traceback
            with st.expander("⚠️ Error Details"):
                st.code(traceback.format_exc())

        st.markdown(f"### 🧾 FSO Out-Turn Report - {st.session_state.selected_fso_vessel}")
        st.caption("Record vessel operations and stock movements")

        # 👉 paste your OTR filters + Add New Entry + table + summary + export block here
        # (the same code you pasted in the prompt)

        st.info("⚠️ OTR body omitted in snippet. Paste your existing OTR block here unchanged.")

    # -------------------------------------------------------------------
    # TAB 2: MATERIAL BALANCE
    # (body also lifted from your old code)
    # -------------------------------------------------------------------
    with tab_material_balance:
        st.markdown(f"### 📊 FSO Material Balance - {st.session_state.selected_fso_vessel}")
        st.caption("Auto-calculated material balance (06:01 - 06:00) | Updates automatically when data is saved")

        # Determine full FSO data range (keeps opening/closing constant)
        with get_session() as s_bounds:
            from sqlalchemy import func as sa_func
            min_max = (
                s_bounds.query(sa_func.min(FSOOperation.date), sa_func.max(FSOOperation.date))
                .filter(
                    FSOOperation.location_id == active_location_id,
                    FSOOperation.fso_vessel == st.session_state.selected_fso_vessel,
                )
                .first()
            )
        min_fso_date, max_fso_date = (min_max or (None, None))
        if not min_fso_date or not max_fso_date:
            st.info("No FSO material balance data available yet for this vessel.")
            st.stop()

        default_fso_from = max(max_fso_date - timedelta(days=30), min_fso_date)
        default_fso_to = max_fso_date

        
        # Date range selector (for filtering display, not for calculation trigger)
        st.markdown("#### 📆 Display Period")
        
        mb_col1, mb_col2, mb_col3 = st.columns([1, 1, 2])
        
        with mb_col1:
            mb_date_from = st.date_input(
                "From Date",
                value=default_fso_from,
                min_value=min_fso_date,
                max_value=max_fso_date,
                key="mb_date_from"
            )
        
        with mb_col2:
            mb_date_to = st.date_input(
                "To Date",
                value=default_fso_to,
                min_value=min_fso_date,
                max_value=max_fso_date,
                key="mb_date_to"
            )

        if mb_date_from < min_fso_date:
            mb_date_from = min_fso_date
            st.session_state["mb_date_from"] = mb_date_from

        with mb_col3:
            st.info(f"📅 Showing: {mb_date_from.strftime('%d-%b-%Y')} to {mb_date_to.strftime('%d-%b-%Y')}")
        
        st.markdown("---")
        
        # AUTO-CALCULATE Material Balance (no button needed)
        try:
            with get_session() as s:
                # Fetch all entries for calculation
                # We need to fetch from a wider range to properly calculate 06:01-06:00 periods
                extended_date_from = min_fso_date - timedelta(days=1)  # Get previous day for 06:01 calculation
                extended_date_to = max_fso_date + timedelta(days=1)  # Get next day for 06:00 calculation
                
                all_entries = s.query(FSOOperation).filter(
                    FSOOperation.location_id == active_location_id,
                    FSOOperation.fso_vessel == st.session_state.selected_fso_vessel,
                    FSOOperation.date >= extended_date_from,
                    FSOOperation.date <= extended_date_to
                ).order_by(FSOOperation.date, FSOOperation.time).all()
            
            if not all_entries:
                st.warning("⚠️ No data available for material balance calculation.")
                st.info("ℹ️ Add entries in the **OTR** tab to see material balance here.")
            else:
                # Process material balance by date
                material_balance_data = []
                
                # Generate full date range for computation (filters will hide rows later)
                calc_start = min_fso_date
                calc_end = max_fso_date
                current_date = calc_start
                while current_date <= calc_end:
                    # Define period: 06:01 of current_date to 06:00 of next_date
                    period_start = datetime.combine(current_date, dt_time(6, 1))
                    period_end = datetime.combine(current_date + timedelta(days=1), dt_time(6, 0))
                    
                    # Get entries within this period
                    period_entries = []
                    for entry in all_entries:
                        try:
                            # Convert entry time to datetime
                            if isinstance(entry.time, dt_time):
                                entry_time = entry.time
                            else:
                                entry_time = convert_to_time_object(entry.time)
                            
                            entry_datetime = datetime.combine(entry.date, entry_time)
                            
                            if period_start <= entry_datetime <= period_end:
                                period_entries.append(entry)
                        except:
                            continue
                    
                    if not period_entries:
                        # No entries for this date, skip
                        current_date += timedelta(days=1)
                        continue
                    
                    # Sort period entries by datetime
                    period_entries.sort(key=lambda e: datetime.combine(
                        e.date, 
                        e.time if isinstance(e.time, dt_time) else convert_to_time_object(e.time)
                    ))
                    
                    # 1. OPENING STOCK & WATER - First entry of the period
                    first_entry = period_entries[0]
                    opening_stock = first_entry.opening_stock
                    opening_water = getattr(first_entry, 'opening_water', 0.0)
                    if getattr(first_entry, "operation", "") == "Stock Opening":
                        try:
                            opening_stock = float(first_entry.closing_stock or opening_stock or 0.0)
                        except Exception:
                            opening_stock = float(opening_stock or 0.0)
                        try:
                            opening_water = float(getattr(first_entry, 'closing_water', opening_water) or 0.0)
                        except Exception:
                            opening_water = float(opening_water or 0.0)
                    
                    # 2. RECEIPTS - Sum of Net R/E where operation is "Receipt"
                    receipts = sum(
                        e.net_receipt_dispatch 
                        for e in period_entries 
                        if e.operation == "Receipt" and e.net_receipt_dispatch > 0
                    )
                    
                    # 3. EXPORTS - Sum of absolute Net R/E where operation is "Export"
                    exports = sum(
                        abs(e.net_receipt_dispatch) 
                        for e in period_entries 
                        if e.operation == "Export" and e.net_receipt_dispatch < 0
                    )
                    
                    # 4. CLOSING STOCK & WATER - Last entry of the period
                    last_entry = period_entries[-1]
                    closing_stock = last_entry.closing_stock
                    closing_water = getattr(last_entry, 'closing_water', 0.0)
                    
                    # 5. LOSS/GAIN CALCULATION
                    # Find Stock Opening operation in this period
                    stock_opening_entries = [e for e in period_entries if e.operation == "Stock Opening"]
                    
                    if stock_opening_entries:
                        # Method 1: Stock Opening exists
                        stock_opening_entry = stock_opening_entries[0]
                        stock_opening_closing = stock_opening_entry.closing_stock
                        
                        # Find last entry BEFORE Stock Opening
                        try:
                            stock_opening_time = stock_opening_entry.time if isinstance(stock_opening_entry.time, dt_time) else convert_to_time_object(stock_opening_entry.time)
                            stock_opening_datetime = datetime.combine(stock_opening_entry.date, stock_opening_time)
                            
                            entries_before_opening = [
                                e for e in period_entries 
                                if datetime.combine(
                                    e.date, 
                                    e.time if isinstance(e.time, dt_time) else convert_to_time_object(e.time)
                                ) < stock_opening_datetime
                            ]
                            
                            if entries_before_opening:
                                last_before_opening = entries_before_opening[-1]
                                last_operation_closing = last_before_opening.closing_stock
                                
                                # Loss/Gain = Stock Opening Closing - Last Operation Closing
                                loss_gain = stock_opening_closing - last_operation_closing
                            else:
                                # No entries before Stock Opening, calculate from opening
                                loss_gain = stock_opening_closing - opening_stock
                        except:
                            loss_gain = 0.0
                    else:
                        # Method 2: No Stock Opening - Calculate from balance
                        # Loss/Gain = Closing - (Opening + Receipts - Exports)
                        theoretical_closing = opening_stock + receipts - exports
                        loss_gain = closing_stock - theoretical_closing
                    
                    # Add to material balance data
                    material_balance_data.append({
                        "Date": current_date.strftime("%Y-%m-%d"),
                        "Opening Stock": opening_stock,
                        "Opening Water": opening_water,
                        "Receipts": receipts,
                        "Exports": exports,
                        "Closing Stock": closing_stock,
                        "Closing Water": closing_water,
                        "Loss/Gain": loss_gain
                    })
                    
                    current_date += timedelta(days=1)
                
                if not material_balance_data:
                    st.warning("⚠️ No material balance data available for the selected period.")
                    st.info("ℹ️ Make sure entries exist between 06:01 and 06:00 for each day.")
                else:
                    # Create DataFrame for full range then apply view filters
                    mb_df_full = pd.DataFrame(material_balance_data)

                    # Cache the raw MB data so other dashboard sections (e.g. Utapate summary cards)
                    # can reuse the "Exports (bbls)" column without recomputing.
                    try:
                        mb_cache_df = mb_df_full.copy()
                        mb_cache_df["Date"] = pd.to_datetime(mb_cache_df["Date"], errors="coerce").dt.date
                        try:
                            from models import Location
                            with get_session() as s_loc:
                                loc_obj = s_loc.query(Location).filter(Location.id == active_location_id).one_or_none()
                            mb_cache_df["Location"] = getattr(loc_obj, "code", "") or ""
                        except Exception:
                            mb_cache_df["Location"] = ""
                        mb_cache_df["FSO Vessel"] = st.session_state.selected_fso_vessel
                        st.session_state["fso_material_balance_df"] = mb_cache_df
                        st.session_state["fso_mb_df"] = mb_cache_df
                        st.session_state["fso_mb_table"] = mb_cache_df

                        with get_session() as s_persist:
                            try:
                                from models import FSOMaterialBalance
                                from db import engine as _engine
                                FSOMaterialBalance.__table__.create(bind=_engine, checkfirst=True)
                                for _, r in mb_cache_df.iterrows():
                                    try:
                                        obj = s_persist.query(FSOMaterialBalance).filter(
                                            FSOMaterialBalance.location_id == active_location_id,
                                            FSOMaterialBalance.fso_vessel == st.session_state.selected_fso_vessel,
                                            FSOMaterialBalance.date == r["Date"],
                                        ).one_or_none()
                                        if not obj:
                                            obj = FSOMaterialBalance(
                                                location_id=active_location_id,
                                                fso_vessel=st.session_state.selected_fso_vessel,
                                                date=r["Date"],
                                                opening_stock=float(r["Opening Stock"] or 0.0),
                                                opening_water=float(r.get("Opening Water", 0.0) or 0.0),
                                                receipts=float(r["Receipts"] or 0.0),
                                                exports=float(r["Exports"] or 0.0),
                                                closing_stock=float(r["Closing Stock"] or 0.0),
                                                closing_water=float(r.get("Closing Water", 0.0) or 0.0),
                                                loss_gain=float(r["Loss/Gain"] or 0.0),
                                                created_by=user["username"],
                                            )
                                            s_persist.add(obj)
                                        else:
                                            obj.opening_stock = float(r["Opening Stock"] or 0.0)
                                            obj.opening_water = float(r.get("Opening Water", 0.0) or 0.0)
                                            obj.receipts = float(r["Receipts"] or 0.0)
                                            obj.exports = float(r["Exports"] or 0.0)
                                            obj.closing_stock = float(r["Closing Stock"] or 0.0)
                                            obj.closing_water = float(r.get("Closing Water", 0.0) or 0.0)
                                            obj.loss_gain = float(r["Loss/Gain"] or 0.0)
                                            obj.updated_by = user["username"]
                                        s_persist.flush()
                                    except Exception:
                                        pass
                                try:
                                    s_persist.commit()
                                except Exception:
                                    pass
                            except Exception:
                                pass
                    except Exception:
                        st.session_state["fso_material_balance_df"] = mb_df_full.copy()
                    
                    if mb_df_full.empty:
                        st.warning("dY\"- No material balance data available for this vessel.")
                        st.stop()
                    
                    mb_df_full["Date"] = pd.to_datetime(mb_df_full["Date"], errors="coerce")
                    mb_df_full = mb_df_full.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
                    total_days = len(mb_df_full)
                    
                    opening_stock_full = float(mb_df_full["Opening Stock"].iloc[0]) if total_days else 0.0
                    closing_stock_full = float(mb_df_full["Closing Stock"].iloc[-1]) if total_days else 0.0
                    
                    view_mask = (
                        (mb_df_full["Date"].dt.date >= mb_date_from) &
                        (mb_df_full["Date"].dt.date <= mb_date_to)
                    )
                    mb_df = mb_df_full.loc[view_mask].copy()
                    shown_days = len(mb_df)
                    if shown_days == 0:
                        st.info("dY\"- No material balance rows within the selected display period.")
                    
                    if not mb_df.empty:
                        mb_df["Date"] = mb_df["Date"].dt.strftime("%Y-%m-%d")
                    
                    st.markdown(f"#### 📊 Material Balance Report ({shown_days} / {total_days} days)")
                    st.caption("Auto-updates when new entries are saved in OTR section")
                    
                    # Display as styled dataframe with variance coloring
                    rename_map = {
                        "Opening Stock": "Opening Stock (bbls)",
                        "Opening Water": "Opening Water (bbls)",
                        "Receipts": "Receipts (bbls)",
                        "Exports": "Exports (bbls)",
                        "Closing Stock": "Closing Stock (bbls)",
                        "Closing Water": "Closing Water (bbls)",
                        "Loss/Gain": "Loss/Gain (bbls)"
                    }
                    display_columns = ["Date"] + list(rename_map.keys())
                    display_df = mb_df[display_columns].copy()
                    display_df = display_df.rename(columns=rename_map)
                    
                    variance_column = rename_map["Loss/Gain"]
                    
                    def _variance_color(val):
                        if pd.isna(val):
                            return ""
                        color = "#16a34a" if val >= 0 else "#dc2626"
                        return f"color: {color}; font-weight: 600;"
                    
                    style_formats = {col_label: "{:,.2f}" for col_label in rename_map.values()}
                    styled_df = (
                        display_df.style
                        .format(style_formats, na_rep="-")
                        .applymap(_variance_color, subset=[variance_column])
                    )
                    
                    st.dataframe(
                        styled_df,
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    # Summary Statistics
                    st.markdown("---")
                    st.markdown("#### 📊 Summary")
                    
                    summary_col1, summary_col2, summary_col3, summary_col4, summary_col5 = st.columns(5)
                    
                    total_receipts = mb_df["Receipts"].sum()
                    total_exports = mb_df["Exports"].sum()
                    total_loss_gain = mb_df["Loss/Gain"].sum()
                    opening_metric = opening_stock_full
                    closing_metric = closing_stock_full
                    
                    with summary_col1:
                        st.metric("Total Receipts", f"{total_receipts:,.0f} bbls")
                    
                    with summary_col2:
                        st.metric("Total Exports", f"{total_exports:,.0f} bbls")
                    
                    with summary_col3:
                        st.metric("Total Loss/Gain", f"{total_loss_gain:,.2f} bbls", 
                                delta="Gain" if total_loss_gain >= 0 else "Loss",
                                delta_color="normal" if total_loss_gain >= 0 else "inverse")
                    
                    with summary_col4:
                        st.metric("Opening Stock (full range)", f"{opening_metric:,.0f} bbls")
                    
                    with summary_col5:
                        st.metric("Closing Stock (full range)", f"{closing_metric:,.0f} bbls")

                    st.caption("Opening/Closing values always reference the full data range; other totals follow the active filters.")
                    
                    # Export Material Balance
                    st.markdown("---")
                    st.markdown("#### 📤 Export Material Balance")
                    
                    mb_export_col1, mb_export_col2, mb_export_col3, mb_export_col4 = st.columns(4)
                    
                    # CSV Export
                    with mb_export_col1:
                        csv_mb = mb_df.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label="📥 Download CSV",
                            data=csv_mb,
                            file_name=f"FSO_Material_Balance_{st.session_state.selected_fso_vessel}_{date.today()}.csv",
                            mime="text/csv",
                            use_container_width=True,
                            on_click=lambda: log_export_action("FSO-MaterialBalance", "CSV", len(mb_df), user, active_location_id)
                        )
                    
                    # Excel Export
                    with mb_export_col2:
                        mb_output = BytesIO()
                        with pd.ExcelWriter(mb_output, engine='openpyxl') as writer:
                            mb_df.to_excel(writer, index=False, sheet_name='Material Balance')
                        mb_excel_data = mb_output.getvalue()
                        
                        st.download_button(
                            label="⬇️ Download Excel",
                            data=mb_excel_data,
                            file_name=f"FSO_Material_Balance_{st.session_state.selected_fso_vessel}_{date.today()}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                            on_click=lambda: log_export_action("FSO-MaterialBalance", "XLSX", len(mb_df), user, active_location_id)
                        )
                    
                    # PDF Download
                    with mb_export_col3:
                        if st.button("📥", key="mb_pdf_download", use_container_width=True, help="Download PDF"):
                            try:
                                # Generate Material Balance PDF
                                mb_pdf_data = generate_material_balance_pdf(
                                    mb_df,
                                    st.session_state.selected_fso_vessel,
                                    mb_date_from.strftime("%d-%b-%Y"),
                                    mb_date_to.strftime("%d-%b-%Y"),
                                    total_receipts,
                                    total_exports,
                                    total_loss_gain,
                                    user["username"]
                                )
                                
                                st.download_button(
                                    label="💾",
                                    data=mb_pdf_data,
                                    file_name=f"FSO_Material_Balance_{st.session_state.selected_fso_vessel}_{date.today()}.pdf",
                                    mime="application/pdf",
                                    key="mb_save_pdf_btn",
                                    use_container_width=True,
                                    on_click=lambda: log_export_action("FSO-MaterialBalance", "PDF", len(mb_df), user, active_location_id)
                                )
                            except Exception as ex:
                                st.error(f"PDF generation failed: {ex}")
                    
                    # PDF View
                    with mb_export_col4:
                        if st.button("👁️", key="mb_pdf_view_fso", use_container_width=True, help="View PDF"):
                            try:
                                # Generate Material Balance PDF
                                mb_pdf_data = generate_material_balance_pdf(
                                    mb_df,
                                    st.session_state.selected_fso_vessel,
                                    mb_date_from.strftime("%d-%b-%Y"),
                                    mb_date_to.strftime("%d-%b-%Y"),
                                    total_receipts,
                                    total_exports,
                                    total_loss_gain,
                                    user["username"]
                                )
                                
                                # Encode to base64
                                base64_pdf = base64.b64encode(mb_pdf_data).decode('utf-8')
                                
                                # JavaScript to open in new tab
                                pdf_html = f"""
                                <script>
                                    var pdfWindow = window.open("");
                                    pdfWindow.document.write(
                                        '<html><head><title>FSO Material Balance - {st.session_state.selected_fso_vessel}</title></head>' +
                                        '<body style="margin:0"><iframe width="100%" height="100%" src="data:application/pdf;base64,{base64_pdf}"></iframe></body></html>'
                                    );
                                </script>
                                """
                                
                                import streamlit.components.v1 as components
                                components.html(pdf_html, height=0)
                                st.success("PDF opened in new tab!")
                                try:
                                    SecurityManager.log_audit(
                                        None,
                                        user.get("username", "system"),
                                        "VIEW",
                                        resource_type="FSO-MaterialBalance",
                                        resource_id=str(active_location_id),
                                        details="Viewed FSO Material Balance PDF",
                                        user_id=user.get("id"),
                                        location_id=active_location_id,
                                        success=True,
                                    )
                                except Exception:
                                    pass
                                
                            except Exception as ex:
                                st.error(f"PDF view failed: {ex}")
                                import traceback
                                with st.expander("⚠️ Error Details"):
                                    st.code(traceback.format_exc())
                    
                    # Visualization
                    st.markdown("---")
                    st.markdown("#### 📈 Visual Trends")
                    
                    # Check if plotly is available
                    try:
                        import plotly.graph_objects as go
                        
                        # Create trend chart
                        fig = go.Figure()
                        
                        fig.add_trace(go.Scatter(
                            x=mb_df["Date"],
                            y=mb_df["Opening Stock"],
                            mode='lines+markers',
                            name='Opening Stock',
                            line=dict(color='#3b82f6', width=2),
                            marker=dict(size=6)
                        ))
                        
                        fig.add_trace(go.Scatter(
                            x=mb_df["Date"],
                            y=mb_df["Closing Stock"],
                            mode='lines+markers',
                            name='Closing Stock',
                            line=dict(color='#10b981', width=2),
                            marker=dict(size=6)
                        ))
                        
                        fig.add_trace(go.Bar(
                            x=mb_df["Date"],
                            y=mb_df["Receipts"],
                            name='Receipts',
                            marker_color='#60a5fa',
                            opacity=0.7
                        ))
                        
                        fig.add_trace(go.Bar(
                            x=mb_df["Date"],
                            y=mb_df["Exports"],
                            name='Exports',
                            marker_color='#f97316',
                            opacity=0.7
                        ))
                        
                        fig.update_layout(
                            title=f"FSO Material Balance Trends - {st.session_state.selected_fso_vessel}",
                            xaxis_title="Date",
                            yaxis_title="Volume (bbls)",
                            barmode='group',
                            hovermode='x unified',
                            height=500,
                            template='plotly_white'
                        )
                        
                        st.plotly_chart(fig, use_container_width=True)
                        
                        # Loss/Gain chart
                        fig_lg = go.Figure()
                        
                        colors_lg = ['#10b981' if x >= 0 else '#ef4444' for x in mb_df["Loss/Gain"]]
                        
                        fig_lg.add_trace(go.Bar(
                            x=mb_df["Date"],
                            y=mb_df["Loss/Gain"],
                            name='Loss/Gain',
                            marker_color=colors_lg,
                            text=mb_df["Loss/Gain"].apply(lambda x: f"{x:,.1f}"),
                            textposition='outside'
                        ))
                        
                        fig_lg.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
                        
                        fig_lg.update_layout(
                            title="Daily Loss/Gain Analysis",
                            xaxis_title="Date",
                            yaxis_title="Loss/Gain (bbls)",
                            hovermode='x',
                            height=400,
                            template='plotly_white',
                            showlegend=False
                        )
                        
                        st.plotly_chart(fig_lg, use_container_width=True)
                        
                    except ImportError:
                        st.info("ℹ️ Install plotly to see visual charts: `pip install plotly`")
        
        except Exception as ex:
            st.error(f"Failed to calculate material balance: {ex}")
            import traceback
            with st.expander("⚠️ Error Details"):
                st.code(traceback.format_exc())   
        # 👉 paste your material balance full logic here (same as old file)

        st.info("⚠️ Material Balance body omitted in snippet. Paste your existing MB block here unchanged.")
