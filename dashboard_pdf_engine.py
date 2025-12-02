import base64
from io import BytesIO
from datetime import date, datetime, timedelta
import pandas as pd
from typing import Dict, Any, List
from reportlab.lib.pagesizes import A4
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
        doc = SimpleDocTemplate(pdf_buffer, pagesize=A4)
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
                layout = config.get("layout", {}).get("summary_cards", {})
                cards = layout.get("cards") or []
                data = []
                for c in cards:
                    name = c.get("name") or c.get("title") or "Metric"
                    ds = str(c.get("data_source","material_balance")).lower()
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
                    data.append([name, f"{val:,.2f}", unit])
                if data:
                    tbl = Table([["Metric","Value","Unit"]] + data)
                    tbl.setStyle(TableStyle([
                        ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#374151')),
                        ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
                        ('GRID',(0,0),(-1,-1),0.5,colors.HexColor('#d1d5db')),
                        ('FONTSIZE',(0,0),(-1,-1),9),
                        ('ALIGN',(1,1),(-1,-1),'RIGHT')
                    ]))
                    elements.append(tbl)
            elif sec.get("type") in ("monthly_data","trend_chart"):
                layout = config.get("layout", {}).get("monthly_data", {}) if sec.get("type") == "monthly_data" else config.get("layout", {}).get("trend_chart", {})
                if sec.get("type") == "monthly_data":
                    visuals = layout.get("cards") or []
                    data = []
                    for v in visuals:
                        name = v.get("name") or "Visual"
                        ds = str(v.get("data_source","material_balance")).lower()
                        field = v.get("field")
                        series = _series_per_day(ds, field, location_id, d1, d2) if field else []
                        total = float(pd.Series([r["Value"] for r in series]).sum()) if series else 0.0
                        data.append([name, f"{total:,.2f}"])
                    if data:
                        tbl = Table([["Visual","Total"]] + data)
                        tbl.setStyle(TableStyle([
                            ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#374151')),
                            ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
                            ('GRID',(0,0),(-1,-1),0.5,colors.HexColor('#d1d5db')),
                            ('FONTSIZE',(0,0),(-1,-1),9),
                            ('ALIGN',(1,1),(-1,-1),'RIGHT')
                        ]))
                        elements.append(tbl)
                else:
                    series_cfg = layout.get("series") or []
                    data = []
                    for s in series_cfg:
                        name = s.get("name") or "Series"
                        ds = str(s.get("data_source","material_balance")).lower()
                        field = s.get("field")
                        series = _series_per_day(ds, field, location_id, d1, d2) if field else []
                        total = float(pd.Series([r["Value"] for r in series]).sum()) if series else 0.0
                        data.append([name, f"{total:,.2f}"])
                    if data:
                        tbl = Table([["Series","Total"]] + data)
                        tbl.setStyle(TableStyle([
                            ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#374151')),
                            ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
                            ('GRID',(0,0),(-1,-1),0.5,colors.HexColor('#d1d5db')),
                            ('FONTSIZE',(0,0),(-1,-1),9),
                            ('ALIGN',(1,1),(-1,-1),'RIGHT')
                        ]))
                        elements.append(tbl)
            elif sec.get("type") == "tank_visuals":
                elements.append(Paragraph("Tank Stock Overview", styles['Heading3']))
                layout = config.get("layout", {}).get("tank_visuals", {})
                tanks = layout.get("tanks") or []
                rows = []
                with get_session() as s:
                    for t in tanks:
                        nm = t.get("display_name") or t.get("name") or "Tank"
                        rows.append([nm, "", ""])
                if rows:
                    tbl = Table([["Tank","Current","Fill %"]] + rows)
                    tbl.setStyle(TableStyle([
                        ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#374151')),
                        ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
                        ('GRID',(0,0),(-1,-1),0.5,colors.HexColor('#d1d5db')),
                        ('FONTSIZE',(0,0),(-1,-1),9)
                    ]))
                    elements.append(tbl)
            elements.append(Spacer(1, 0.2 * inch))
        doc.build(elements)
        pdf_buffer.seek(0)
        return pdf_buffer.getvalue()

    @staticmethod
    def get_pdf_base64(config: Dict[str, Any], location_id: int, user: Dict[str, Any]) -> str:
        pdf_bytes = DashboardPdfEngine.export_pdf(config, location_id, user)
        return base64.b64encode(pdf_bytes).decode('utf-8')

