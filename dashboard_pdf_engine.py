import base64
from io import BytesIO
from datetime import date, datetime, timedelta
import pandas as pd
from typing import Dict, Any, List
from reportlab.lib.pagesizes import A4, A3, LETTER, LEGAL, landscape, portrait
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from sqlalchemy import text, inspect
from db import get_session, engine

def _get_date_range(section_id: str) -> tuple[date, date]:
    d1 = None
    d2 = None
    import streamlit as st
    if st.session_state.get(f"section_start_{section_id}") and st.session_state.get(f"section_end_{section_id}"):
        d1 = st.session_state.get(f"section_start_{section_id}")
        d2 = st.session_state.get(f"section_end_{section_id}")
    elif st.session_state.get(f"section_date_{section_id}"):
        val = st.session_state.get(f"section_date_{section_id}")
        if isinstance(val, tuple) and len(val) == 2:
            d1, d2 = val
        else:
            d1 = val
            d2 = val
    else:
        d2 = date.today()
        d1 = d2 - timedelta(days=30)
    return d1, d2

def _sum_table_range(table: str, field: str, location_id: int, d1: date, d2: date) -> float:
    insp = inspect(engine)
    cols = [c.get("name") for c in insp.get_columns(table)]
    date_col = None
    for cand in ["date","Date","tx_date","transaction_date","created_at","timestamp"]:
        if cand in cols:
            date_col = cand
            break
    has_loc = "location_id" in cols
    try:
        backend = engine.url.get_backend_name()
    except Exception:
        backend = "sqlite"
    def q(x: str) -> str:
        return f"`{x}`" if backend == "mysql" else f'"{x}"'
    where = []
    params = {}
    if date_col:
        where.append(f"{q(date_col)} >= :d1 AND {q(date_col)} <= :d2")
        params["d1"] = str(d1) if date_col == "Date" else d1
        params["d2"] = str(d2) if date_col == "Date" else d2
    if has_loc:
        where.append(f"{q('location_id')} = :loc")
        params["loc"] = location_id
    sql = f"SELECT SUM({q(field)}) AS v FROM {q(table)}" + (" WHERE " + " AND ".join(where) if where else "")
    with get_session() as s:
        try:
            val = s.execute(text(sql), params).scalar()
        except Exception:
            val = None
    try:
        return float(val or 0.0)
    except Exception:
        return 0.0

def _series_per_day(ds: str, field: str, location_id: int, d1: date, d2: date) -> List[Dict[str, Any]]:
    rows = []
    cur = d1
    while cur <= d2:
        v = 0.0
        try:
            if ds == "material_balance":
                v = _sum_table_range("material_balance", field, location_id, cur, cur)
            elif ds == "fso_operations":
                v = _sum_table_range("fso_operations", field, location_id, cur, cur)
            else:
                v = 0.0
        except Exception:
            v = 0.0
        rows.append({"Date": str(cur), "Value": float(v)})
        cur = cur + timedelta(days=1)
    return rows

class DashboardPdfEngine:
    @staticmethod
    def export_pdf(config: Dict[str, Any], location_id: int, user: Dict[str, Any]) -> bytes:
        pdf_buffer = BytesIO()
        
        # Get page settings from PDF layout config
        pdf_layout_cfg = config.get("pdf_layout", {})
        page_size_name = pdf_layout_cfg.get("page_size", "A4").upper()
        orientation_name = pdf_layout_cfg.get("orientation", "Landscape").lower()
        
        # Map page size names to ReportLab page sizes
        page_size_map = {
            "A4": A4,
            "A3": A3,
            "LETTER": LETTER,
            "LEGAL": LEGAL
        }
        page_size = page_size_map.get(page_size_name, A4)
        
        # Apply orientation
        if orientation_name == "landscape":
            page_size = landscape(page_size)
        else:
            page_size = portrait(page_size)
        
        doc = SimpleDocTemplate(pdf_buffer, pagesize=page_size)
        elements = []
        styles = getSampleStyleSheet()
        
        # Title
        title = Paragraph("Dashboard Export", styles['Heading1'])
        subtitle = Paragraph(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), styles['Normal'])
        elements.append(title)
        elements.append(Spacer(1, 0.2 * inch))
        elements.append(subtitle)
        elements.append(Spacer(1, 0.2 * inch))
        
        # Get widget configuration
        widgets = pdf_layout_cfg.get("widgets", [])
        
        if not widgets:
            # Fallback to old method if no widgets configured
            return DashboardPdfEngine._export_pdf_legacy(config, location_id, user, page_size)
        
        # Check if using grid layout (new Power BI style) or position layout (old style)
        is_grid_layout = any("col" in w and "row" in w for w in widgets)
        
        if is_grid_layout:
            # Use grid-based layout (Power BI style)
            return DashboardPdfEngine._export_pdf_grid(config, location_id, user, page_size, widgets, pdf_layout_cfg, elements, styles, doc)
        else:
            # Use position-based layout (old style)
            return DashboardPdfEngine._export_pdf_position(config, location_id, user, page_size, widgets, elements, styles, doc)
    
    @staticmethod
    def _export_pdf_grid(config: Dict[str, Any], location_id: int, user: Dict[str, Any], 
                         page_size, widgets: List[Dict], pdf_layout_cfg: Dict, 
                         elements: list, styles, doc) -> bytes:
        """Export PDF using grid-based layout (Power BI style)"""
        grid_cols = pdf_layout_cfg.get("grid_columns", 12)
        
        # Calculate page dimensions
        page_width = page_size[0] - 100  # Account for margins
        page_height = page_size[1] - 150  # Account for header and margins
        
        col_width = page_width / grid_cols
        row_height = 30  # Base row height in points
        
        # Sort widgets by row, then by col
        sorted_widgets = sorted(widgets, key=lambda w: (w.get("row", 0), w.get("col", 0)))
        
        # Group widgets by rows to create table structure
        rows_dict = {}
        for widget in sorted_widgets:
            row_idx = widget.get("row", 0)
            if row_idx not in rows_dict:
                rows_dict[row_idx] = []
            rows_dict[row_idx].append(widget)
        
        # Render widgets row by row
        for row_idx in sorted(rows_dict.keys()):
            row_widgets = rows_dict[row_idx]
            
            # Create a table for this row
            row_data = []
            row_heights = []
            
            # Sort widgets in this row by column
            row_widgets.sort(key=lambda w: w.get("col", 0))
            
            # Calculate spans and create table data
            table_row = []
            col_widths = []
            
            for widget in row_widgets:
                widget_elem = DashboardPdfEngine._render_widget(widget, config, location_id, styles)
                if widget_elem:
                    table_row.append(widget_elem)
                    # Calculate width based on widget's grid width
                    widget_width = widget.get("width", 6)
                    col_widths.append(col_width * widget_width)
            
            if table_row:
                row_data.append(table_row)
                
                # Create table with proper widths
                widget_table = Table(row_data, colWidths=col_widths)
                widget_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 5),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                    ('TOPPADDING', (0, 0), (-1, -1), 5),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 5)
                ]))
                elements.append(widget_table)
                elements.append(Spacer(1, 0.2 * inch))
        
        # Build PDF
        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=page_size)
        doc.build(elements)
        pdf_buffer.seek(0)
        return pdf_buffer.getvalue()
    
    @staticmethod
    def _export_pdf_position(config: Dict[str, Any], location_id: int, user: Dict[str, Any],
                            page_size, widgets: List[Dict], elements: list, styles, doc) -> bytes:
        """Export PDF using position-based layout (old style)"""
        # Sort widgets by order
        widgets.sort(key=lambda x: x.get("order", 999))
        
        # Group widgets by position
        top_widgets = [w for w in widgets if w.get("position") == "top"]
        left_widgets = [w for w in widgets if w.get("position") == "left"]
        center_widgets = [w for w in widgets if w.get("position") == "center"]
        right_widgets = [w for w in widgets if w.get("position") == "right"]
        bottom_widgets = [w for w in widgets if w.get("position") == "bottom"]
        
        # Render top widgets
        for widget in top_widgets:
            widget_element = DashboardPdfEngine._render_widget(widget, config, location_id, styles)
            if widget_element:
                elements.append(widget_element)
                elements.append(Spacer(1, 0.1 * inch))
        
        # Render middle section (left, center, right) in columns
        if left_widgets or center_widgets or right_widgets:
            middle_data = []
            max_middle = max(len(left_widgets), len(center_widgets), len(right_widgets))
            
            for i in range(max_middle):
                row = []
                
                # Left column
                if i < len(left_widgets):
                    left_elem = DashboardPdfEngine._render_widget(left_widgets[i], config, location_id, styles)
                    row.append(left_elem if left_elem else Spacer(1, 0.1 * inch))
                else:
                    row.append(Spacer(1, 0.1 * inch))
                
                # Center column
                if i < len(center_widgets):
                    center_elem = DashboardPdfEngine._render_widget(center_widgets[i], config, location_id, styles)
                    row.append(center_elem if center_elem else Spacer(1, 0.1 * inch))
                else:
                    row.append(Spacer(1, 0.1 * inch))
                
                # Right column
                if i < len(right_widgets):
                    right_elem = DashboardPdfEngine._render_widget(right_widgets[i], config, location_id, styles)
                    row.append(right_elem if right_elem else Spacer(1, 0.1 * inch))
                else:
                    row.append(Spacer(1, 0.1 * inch))
                
                middle_data.append(row)
            
            if middle_data:
                # Calculate column widths based on page size
                page_width = page_size[0] if orientation_name == "portrait" else page_size[1]
                col_width = (page_width - 100) / 3  # 3 columns with margins
                
                middle_table = Table(middle_data, colWidths=[col_width, col_width, col_width])
                middle_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 5),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 5)
                ]))
                elements.append(middle_table)
                elements.append(Spacer(1, 0.1 * inch))
        
        # Render bottom widgets
        for widget in bottom_widgets:
            widget_element = DashboardPdfEngine._render_widget(widget, config, location_id, styles)
            if widget_element:
                elements.append(widget_element)
                elements.append(Spacer(1, 0.1 * inch))
        
        doc.build(elements)
        pdf_buffer.seek(0)
        return pdf_buffer.getvalue()
    
    @staticmethod
    def _render_widget(widget: Dict[str, Any], config: Dict[str, Any], location_id: int, styles) -> Any:
        """Render a single widget based on its type and display_type"""
        widget_type = widget.get("type")
        widget_id = widget.get("id")
        display_type = widget.get("display_type", "table")  # Default to table for backward compatibility
        
        # Find the section configuration
        sections = config.get("sections", [])
        section = next((s for s in sections if s.get("id") == widget_id), None)
        
        if not section:
            return None
        
        d1, d2 = _get_date_range(widget_id)
        
        # Route to appropriate renderer based on display_type
        if display_type == "visual":
            # Render as visual/graphical format
            if widget_type == "summary_cards":
                return DashboardPdfEngine._render_summary_cards_visual(config, location_id, d1, d2, styles)
            elif widget_type == "tank_visuals":
                return DashboardPdfEngine._render_tank_visuals_visual(config, location_id, styles)
            elif widget_type == "monthly_data":
                return DashboardPdfEngine._render_monthly_data_visual(config, location_id, d1, d2, styles)
            elif widget_type == "trend_chart":
                return DashboardPdfEngine._render_trend_chart_visual(config, location_id, d1, d2, styles)
            else:
                return None
        else:
            # Render as table format (default)
            if widget_type == "summary_cards":
                return DashboardPdfEngine._render_summary_cards(config, location_id, d1, d2, styles)
            elif widget_type == "tank_visuals":
                return DashboardPdfEngine._render_tank_visuals(config, location_id, styles)
            elif widget_type == "monthly_data":
                return DashboardPdfEngine._render_monthly_data(config, location_id, d1, d2, styles)
            elif widget_type == "trend_chart":
                return DashboardPdfEngine._render_trend_chart(config, location_id, d1, d2, styles)
            else:
                return None
    
    @staticmethod
    def _render_summary_cards(config: Dict[str, Any], location_id: int, d1: date, d2: date, styles) -> Any:
        """Render summary cards as a table"""
        layout = config.get("layout", {}).get("summary_cards", {})
        cards = layout.get("cards") or []
        card_data = []
        
        for c in cards:
            name = c.get("name") or c.get("title") or "Metric"
            ds = str(c.get("data_source", "material_balance")).lower()
            field = c.get("field")
            unit = c.get("unit") or ""
            val = 0.0
            
            if ds == "calculated" and c.get("calculation") == "ullage":
                val = 0.0
            elif ds == "calculated" and c.get("calculation") == "pumpable":
                val = 0.0
            elif ds == "table":
                table = c.get("table_name")
                if table and field:
                    val = _sum_table_range(table, field, location_id, d1, d2)
            else:
                if field:
                    series = _series_per_day(ds, field, location_id, d1, d2)
                    val = float(pd.Series([r["Value"] for r in series]).sum()) if series else 0.0
            
            card_data.append([name, f"{val:,.2f}", unit])
        
        if card_data:
            tbl = Table([
                [d[0] for d in card_data],
                [d[1] for d in card_data],
                [d[2] for d in card_data],
            ])
            tbl.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER')
            ]))
            return tbl
        return None
    
    @staticmethod
    def _render_tank_visuals(config: Dict[str, Any], location_id: int, styles) -> Any:
        """Render tank visuals as a table"""
        layout = config.get("layout", {}).get("tank_visuals", {})
        tanks = layout.get("tanks") or []
        rows = []
        
        with get_session() as s:
            for t in tanks:
                nm = t.get("display_name") or t.get("name") or "Tank"
                rows.append([nm, "", ""])
        
        if rows:
            tbl = Table([["Tank", "Current", "Fill %"]] + rows, colWidths=[80, 60, 60])
            tbl.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563eb')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('ALIGN', (1, 1), (-1, -1), 'RIGHT')
            ]))
            return tbl
        return None
    
    @staticmethod
    def _render_monthly_data(config: Dict[str, Any], location_id: int, d1: date, d2: date, styles) -> Any:
        """Render monthly data as a table"""
        layout = config.get("layout", {}).get("monthly_data", {})
        visuals = layout.get("cards") or []
        data = []
        
        for v in visuals:
            name = v.get("name") or "Visual"
            ds = str(v.get("data_source", "material_balance")).lower()
            field = v.get("field")
            series = _series_per_day(ds, field, location_id, d1, d2) if field else []
            total = float(pd.Series([r["Value"] for r in series]).sum()) if series else 0.0
            data.append([name, f"{total:,.2f}"])
        
        if data:
            tbl = Table([["Visual", "Total"]] + data)
            tbl.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('ALIGN', (1, 1), (-1, -1), 'RIGHT')
            ]))
            return tbl
        return None
    
    @staticmethod
    def _render_trend_chart(config: Dict[str, Any], location_id: int, d1: date, d2: date, styles) -> Any:
        """Render trend chart as a table"""
        layout = config.get("layout", {}).get("trend_chart", {})
        series_cfg = layout.get("series") or []
        data = []
        
        for s in series_cfg:
            name = s.get("name") or "Series"
            ds = str(s.get("data_source", "material_balance")).lower()
            field = s.get("field")
            series = _series_per_day(ds, field, location_id, d1, d2) if field else []
            total = float(pd.Series([r["Value"] for r in series]).sum()) if series else 0.0
            data.append([name, f"{total:,.2f}"])
        
        if data:
            tbl = Table([["Series", "Total"]] + data)
            tbl.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('ALIGN', (1, 1), (-1, -1), 'RIGHT')
            ]))
            return tbl
        return None
    
    # ===== VISUAL RENDERING METHODS (for display_type = "visual") =====
    
    @staticmethod
    def _render_summary_cards_visual(config: Dict[str, Any], location_id: int, d1: date, d2: date, styles) -> Any:
        """Render summary cards with visual styling (colored boxes)"""
        layout = config.get("layout", {}).get("summary_cards", {})
        cards = layout.get("cards") or []
        card_data = []
        
        colors_list = [
            colors.HexColor('#3b82f6'),  # blue
            colors.HexColor('#10b981'),  # green
            colors.HexColor('#f59e0b'),  # amber
            colors.HexColor('#ef4444'),  # red
            colors.HexColor('#8b5cf6'),  # purple
            colors.HexColor('#06b6d4'),  # cyan
        ]
        
        for idx, c in enumerate(cards):
            name = c.get("name") or c.get("title") or "Metric"
            ds = str(c.get("data_source", "material_balance")).lower()
            field = c.get("field")
            unit = c.get("unit") or ""
            val = 0.0
            
            if ds == "calculated" and c.get("calculation") == "ullage":
                val = 0.0
            elif ds == "calculated" and c.get("calculation") == "pumpable":
                val = 0.0
            elif ds == "table":
                table = c.get("table_name")
                if table and field:
                    val = _sum_table_range(table, field, location_id, d1, d2)
            else:
                if field:
                    series = _series_per_day(ds, field, location_id, d1, d2)
                    val = float(pd.Series([r["Value"] for r in series]).sum()) if series else 0.0
            
            # Create visual card with colored background
            card_color = colors_list[idx % len(colors_list)]
            card_row = [
                Paragraph(f"<b>{name}</b>", styles['Normal']),
                Paragraph(f"<b>{val:,.2f}</b>", styles['Heading3']),
                Paragraph(unit, styles['Normal'])
            ]
            card_data.append(card_row)
        
        if card_data:
            tbl = Table(card_data, colWidths=[80, 100, 50])
            tbl.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f3f4f6')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#1f2937')),
                ('GRID', (0, 0), (-1, -1), 1.5, colors.HexColor('#9ca3af')),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('FONTSIZE', (0, 1), (-1, 1), 14),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8)
            ]))
            return tbl
        return None
    
    @staticmethod
    def _render_tank_visuals_visual(config: Dict[str, Any], location_id: int, styles) -> Any:
        """Render tank visuals with visual indicators"""
        layout = config.get("layout", {}).get("tank_visuals", {})
        tanks = layout.get("tanks") or []
        rows = []
        
        with get_session() as s:
            for t in tanks:
                nm = t.get("display_name") or t.get("name") or "Tank"
                # In visual mode, we'd show fill percentage as a bar
                fill_pct = 65  # Default for demo
                rows.append([nm, f"{fill_pct}%", "■" * int(fill_pct / 10)])  # Simple bar representation
        
        if rows:
            tbl = Table([["Tank Name", "Fill %", "Visual Indicator"]] + rows, colWidths=[80, 60, 100])
            tbl.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563eb')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#d1d5db')),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f0f9ff')),
                ('TEXTCOLOR', (2, 1), (2, -1), colors.HexColor('#0284c7'))
            ]))
            return tbl
        return None
    
    @staticmethod
    def _render_monthly_data_visual(config: Dict[str, Any], location_id: int, d1: date, d2: date, styles) -> Any:
        """Render monthly data with visual formatting"""
        layout = config.get("layout", {}).get("monthly_data", {})
        visuals = layout.get("cards") or []
        data = []
        
        for v in visuals:
            name = v.get("name") or "Visual"
            ds = str(v.get("data_source", "material_balance")).lower()
            field = v.get("field")
            series = _series_per_day(ds, field, location_id, d1, d2) if field else []
            total = float(pd.Series([r["Value"] for r in series]).sum()) if series else 0.0
            avg = total / len(series) if series else 0.0
            data.append([name, f"{total:,.2f}", f"{avg:,.2f}"])
        
        if data:
            tbl = Table([["Metric", "Total", "Average"]] + data)
            tbl.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#059669')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#d1d5db')),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ecfdf5'))
            ]))
            return tbl
        return None
    
    @staticmethod
    def _render_trend_chart_visual(config: Dict[str, Any], location_id: int, d1: date, d2: date, styles) -> Any:
        """Render trend chart with visual trend indicators"""
        layout = config.get("layout", {}).get("trend_chart", {})
        series_cfg = layout.get("series") or []
        data = []
        
        for s in series_cfg:
            name = s.get("name") or "Series"
            ds = str(s.get("data_source", "material_balance")).lower()
            field = s.get("field")
            series = _series_per_day(ds, field, location_id, d1, d2) if field else []
            values = [r["Value"] for r in series]
            total = float(pd.Series(values).sum()) if values else 0.0
            
            # Calculate trend indicator (up/down/stable)
            if len(values) >= 2:
                trend_change = values[-1] - values[0]
                if trend_change > 0:
                    trend_indicator = "↑ Increasing"
                elif trend_change < 0:
                    trend_indicator = "↓ Decreasing"
                else:
                    trend_indicator = "→ Stable"
            else:
                trend_indicator = "→ Stable"
            
            data.append([name, f"{total:,.2f}", trend_indicator])
        
        if data:
            tbl = Table([["Series", "Total", "Trend"]] + data)
            tbl.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#7c3aed')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#d1d5db')),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f5f3ff'))
            ]))
            return tbl
        return None
    
    @staticmethod
    def _export_pdf_legacy(config: Dict[str, Any], location_id: int, user: Dict[str, Any], page_size) -> bytes:
        """Legacy PDF export for backward compatibility"""
        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=page_size)
        elements = []
        styles = getSampleStyleSheet()
        
        title = Paragraph("Dashboard Export", styles['Heading1'])
        subtitle = Paragraph(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), styles['Normal'])
        elements.append(title)
        elements.append(Spacer(1, 0.2 * inch))
        elements.append(subtitle)
        elements.append(Spacer(1, 0.2 * inch))
        
        sections_cfg = config.get("sections") or []
        pdf_cfg = config.setdefault("pdf_export", {})
        enabled_map = pdf_cfg.get("enabled_sections") or {}
        
        for sec in sections_cfg:
            sid = sec.get("id")
            if enabled_map and enabled_map.get(sid) is False:
                continue
            sname = sec.get("name") or sid
            elements.append(Paragraph(sname, styles['Heading2']))
            elements.append(Spacer(1, 0.1 * inch))
            d1, d2 = _get_date_range(sid)
            
            if sec.get("type") == "summary_cards":
                elem = DashboardPdfEngine._render_summary_cards(config, location_id, d1, d2, styles)
                if elem:
                    elements.append(elem)
            elif sec.get("type") == "tank_visuals":
                elem = DashboardPdfEngine._render_tank_visuals(config, location_id, styles)
                if elem:
                    elements.append(elem)
            elif sec.get("type") == "monthly_data":
                elem = DashboardPdfEngine._render_monthly_data(config, location_id, d1, d2, styles)
                if elem:
                    elements.append(elem)
            elif sec.get("type") == "trend_chart":
                elem = DashboardPdfEngine._render_trend_chart(config, location_id, d1, d2, styles)
                if elem:
                    elements.append(elem)
            
            elements.append(Spacer(1, 0.2 * inch))
        
        doc.build(elements)
        pdf_buffer.seek(0)
        return pdf_buffer.getvalue()

    @staticmethod
    def get_pdf_base64(config: Dict[str, Any], location_id: int, user: Dict[str, Any]) -> str:
        pdf_bytes = DashboardPdfEngine.export_pdf(config, location_id, user)
        return base64.b64encode(pdf_bytes).decode('utf-8')
