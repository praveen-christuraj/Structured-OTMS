# toa_yade_calculator.py
from __future__ import annotations
from typing import Optional, Dict
from math import isfinite

from sqlalchemy.orm import Session
from sqlalchemy import func

# Import calculation helpers from utils_calc
from utils_calc import (
    api60_from_api_obs,
    api60_from_density_obs,
    vcf_from_api60_and_tank_temp,
)

# DB models
from models import (
    TOAYadeSummary,
    TOAYadeStage,
    YadeVoyage,
    YadeCalibration,
    YadeDip,
    YadeSampleParam,
)

# Table11 for LT factor lookup
try:
    from models import Table11
except Exception:
    Table11 = None


def _afloat(x) -> float:
    """Safe float conversion."""
    try:
        v = float(x)
        return v if isfinite(v) else 0.0
    except Exception:
        return 0.0


def _interp_volume_bbl(session: Session, yade_name: str, tank_id: str, dip_cm: float) -> float:
    """
    Interpolate volume (bbl) from YadeCalibration table.
    YadeCalibration stores dip_mm (millimeters) and vol_bbl.
    Convert cm to mm (multiply by 10), then interpolate.
    """
    if dip_cm <= 0:
        return 0.0
    
    dip_mm = dip_cm * 10.0  # convert cm to mm
    
    rows = (
        session.query(YadeCalibration)
        .filter(
            YadeCalibration.yade_name == yade_name,
            YadeCalibration.tank_id == tank_id
        )
        .order_by(YadeCalibration.dip_mm.asc())
        .all()
    )
    
    if not rows:
        return 0.0
    
    xs = [float(r.dip_mm) for r in rows]
    ys = [float(r.vol_bbl) for r in rows]
    
    # Boundary cases
    if dip_mm <= xs[0]:
        return ys[0]
    if dip_mm >= xs[-1]:
        return ys[-1]
    
    # Linear interpolation
    import bisect
    i = bisect.bisect_left(xs, dip_mm)
    x0, x1 = xs[i-1], xs[i]
    y0, y1 = ys[i-1], ys[i]
    
    if x1 == x0:
        return y0
    
    return y0 + (y1 - y0) * ((dip_mm - x0) / (x1 - x0))


def _lt_factor_from_table11(session: Session, api60: float) -> float:
    """Lookup/interpolate LT factor from Table11 based on API@60."""
    if not Table11:
        return 0.0
    
    rows = session.query(Table11).order_by(Table11.api60).all()
    if not rows:
        return 0.0
    
    xs = [float(r.api60) for r in rows]
    ys = [float(r.lt_factor) for r in rows]
    
    if api60 <= xs[0]:
        return ys[0]
    if api60 >= xs[-1]:
        return ys[-1]
    
    import bisect
    i = bisect.bisect_left(xs, api60)
    x0, x1 = xs[i-1], xs[i]
    y0, y1 = ys[i-1], ys[i]
    
    if x1 == x0:
        return y0
    
    return y0 + (y1 - y0) * ((api60 - x0) / (x1 - x0))


def compute_stage(
    session: Session,
    voyage_id: int,
    stage_label: str,  # "BEFORE" or "AFTER"
    created_by: Optional[str] = None,
) -> Dict:
    """
    Calculate TOA for a given stage using:
    1. YadeDip entries (tank_id, total_cm, water_cm)
    2. YadeSampleParam for the stage (obs_mode, obs_val, temps, ccf, bsw_pct)
    3. YadeCalibration for volume lookup/interpolation
    
    Calculation Steps:
    1. TOV & FW from calibration lookup for each tank, sum all tanks
    2. GOV = (TOV - FW) * CCF
    3. API@60 from sample parameters
    4. VCF from API@60 and tank temperature
    5. GSV = GOV * VCF [round to 0 decimals]
    6. BS&W = GSV * BS&W% [round to 0 decimals]
    7. NSV = GSV - BS&W [round to 0 decimals]
    8. LT = NSV * LT factor [round to 0 decimals]
    9. MT = LT * 1.01605 [round to 0 decimals]
    
    Returns: {"stage": "BEFORE"/"AFTER", "totals": {TOV, FW, GOV, GSV, BSW, NSV, LT, MT, API60, VCF}}
    """
    stage_label = stage_label.upper()
    assert stage_label in {"BEFORE", "AFTER"}
    
    # Get voyage to determine yade_name for calibration lookup
    voyage = session.query(YadeVoyage).get(voyage_id)
    if not voyage:
        return {"stage": stage_label, "totals": {k: 0.0 for k in ["TOV", "FW", "GOV", "GSV", "BSW", "NSV", "LT", "MT", "API60", "VCF"]}}
    
    yade_name = voyage.yade_name
    
    # Get sample parameters for this stage
    sample_param = (
        session.query(YadeSampleParam)
        .filter(
            YadeSampleParam.voyage_id == voyage_id,
            func.upper(YadeSampleParam.stage) == stage_label
        )
        .one_or_none()
    )
    
    if not sample_param:
        # No sample params - return zeros
        return {"stage": stage_label, "totals": {k: 0.0 for k in ["TOV", "FW", "GOV", "GSV", "BSW", "NSV", "LT", "MT", "API60", "VCF"]}}
    
    # Extract sample parameters
    obs_mode = sample_param.obs_mode or "Observed API"
    obs_val = float(sample_param.obs_val or 0.0)
    sample_temp = float(sample_param.sample_temp or 0.0)
    tank_temp = float(sample_param.tank_temp or 0.0)
    sample_unit = sample_param.sample_unit or "F"
    ccf = float(sample_param.ccf or 1.0)
    bsw_pct = float(sample_param.bsw_pct or 0.0)
    
    # Step 3: Calculate API@60 (round to 2 decimal places)
    if "API" in obs_mode:
        # Observed API mode
        api60 = round(api60_from_api_obs(obs_val, sample_temp, f"°{sample_unit}"), 2)
    else:
        # Observed Density mode (kg/m³)
        api60 = round(api60_from_density_obs(obs_val, sample_temp, f"°{sample_unit}"), 2)
    
    # Step 3: Calculate VCF (round to 5 decimal places)
    vcf = round(vcf_from_api60_and_tank_temp(api60, tank_temp, f"°{sample_unit}"), 5)
    
    # Step 1: Get all dips for this stage and calculate TOV & FW
    dips = (
        session.query(YadeDip)
        .filter(
            YadeDip.voyage_id == voyage_id,
            func.upper(YadeDip.stage) == stage_label
        )
        .all()
    )
    
    total_tov = 0.0
    total_fw = 0.0
    
    for dip in dips:
        tank_id = dip.tank_id
        total_cm = float(dip.total_cm or 0.0)
        water_cm = float(dip.water_cm or 0.0)
        
        # Lookup volumes via interpolation
        tov_bbl = _interp_volume_bbl(session, yade_name, tank_id, total_cm)
        fw_bbl = _interp_volume_bbl(session, yade_name, tank_id, water_cm) if water_cm > 0 else 0.0
        
        total_tov += tov_bbl
        total_fw += fw_bbl
    
    # Step 2: GOV = (TOV - FW) * CCF
    gov = (total_tov - total_fw) * ccf
    
    # Step 4: GSV = GOV * VCF (round to 0 decimals)
    gsv = round(gov * vcf, 0)
    
    # Step 5: BS&W = GSV * BS&W% (round to 0 decimals)
    bsw_bbl = round(gsv * (bsw_pct / 100.0), 0)
    
    # Step 6: NSV = GSV - BS&W (round to 0 decimals)
    nsv = round(gsv - bsw_bbl, 0)
    
    # Step 7: LT = NSV * LT factor (round to 0 decimals)
    lt_factor = _lt_factor_from_table11(session, api60)
    lt = round(nsv * lt_factor, 0)
    
    # Step 8: MT = LT * 1.01605 (round to 0 decimals)
    mt = round(lt * 1.01605, 0)
    
    totals = {
        "TOV": round(total_tov, 2),
        "FW": round(total_fw, 2),
        "GOV": round(gov, 2),
        "GSV": float(gsv),
        "BSW": float(bsw_bbl),
        "NSV": float(nsv),
        "LT": float(lt),
        "MT": float(mt),
        "API60": api60,
        "VCF": vcf,
    }
    
    return {"stage": stage_label, "totals": totals}


def compute_and_save_summary(
    session: Session,
    voyage_id: int,
    before_inputs: Optional[list] = None,  # Not used - we read from DB
    after_inputs: Optional[list] = None,    # Not used - we read from DB
    created_by: Optional[str] = None,
) -> Dict:
    """
    Calculate TOA for BEFORE and AFTER stages, then compute NET values.
    Save results to TOAYadeSummary table.
    
    NET Calculation:
    1. NET TOV = AFTER TOV - BEFORE TOV
    2. NET FW = AFTER FW - BEFORE FW
    3. NET GOV = AFTER GOV - BEFORE GOV
    4. NET GSV = AFTER GSV - BEFORE GSV
    5. NET NSV = AFTER NSV - BEFORE NSV
    6. NET LT = AFTER LT - BEFORE LT
    7. NET MT = AFTER MT - BEFORE MT
    """
    # Calculate both stages
    before = compute_stage(session, voyage_id, "BEFORE", created_by=created_by)
    after = compute_stage(session, voyage_id, "AFTER", created_by=created_by)
    
    b = before["totals"]
    a = after["totals"]
    
    # Get or create summary record
    summary = (
        session.query(TOAYadeSummary)
        .filter(TOAYadeSummary.voyage_id == voyage_id)
        .one_or_none()
    )
    
    if not summary:
        summary = TOAYadeSummary(voyage_id=voyage_id)
        session.add(summary)
    
    # Store BEFORE totals
    summary.before_gov_bbl = b["GOV"]
    summary.before_gsv_bbl = b["GSV"]
    summary.before_bsw_bbl = b["BSW"]
    summary.before_nsv_bbl = b["NSV"]
    summary.before_lt_bbl = b["LT"]
    summary.before_mt = b["MT"]
    
    # Store AFTER totals
    summary.after_gov_bbl = a["GOV"]
    summary.after_gsv_bbl = a["GSV"]
    summary.after_bsw_bbl = a["BSW"]
    summary.after_nsv_bbl = a["NSV"]
    summary.after_lt_bbl = a["LT"]
    summary.after_mt = a["MT"]
    
    # Calculate NET (AFTER - BEFORE)
    summary.net_gov_bbl = round(a["GOV"] - b["GOV"], 2)
    summary.net_gsv_bbl = round(a["GSV"] - b["GSV"], 0)
    summary.net_bsw_bbl = round(a["BSW"] - b["BSW"], 0)
    summary.net_nsv_bbl = round(a["NSV"] - b["NSV"], 0)
    summary.net_lt_bbl = round(a["LT"] - b["LT"], 0)
    summary.net_mt = round(a["MT"] - b["MT"], 0)

    # Upsert stage rows for BEFORE and AFTER
    before_row = (
        session.query(TOAYadeStage)
        .filter(TOAYadeStage.voyage_id == voyage_id, TOAYadeStage.stage == "BEFORE")
        .one_or_none()
    )
    if not before_row:
        before_row = TOAYadeStage(voyage_id=voyage_id, stage="BEFORE")
        session.add(before_row)
    before_row.gov_bbl = b["GOV"]
    before_row.gsv_bbl = b["GSV"]
    before_row.bsw_bbl = b["BSW"]
    before_row.nsv_bbl = b["NSV"]
    before_row.lt = b["LT"]
    before_row.mt = b["MT"]
    before_row.fw_bbl = b["FW"]

    after_row = (
        session.query(TOAYadeStage)
        .filter(TOAYadeStage.voyage_id == voyage_id, TOAYadeStage.stage == "AFTER")
        .one_or_none()
    )
    if not after_row:
        after_row = TOAYadeStage(voyage_id=voyage_id, stage="AFTER")
        session.add(after_row)
    after_row.gov_bbl = a["GOV"]
    after_row.gsv_bbl = a["GSV"]
    after_row.bsw_bbl = a["BSW"]
    after_row.nsv_bbl = a["NSV"]
    after_row.lt = a["LT"]
    after_row.mt = a["MT"]
    after_row.fw_bbl = a["FW"]
    
    session.commit()
    
    return {
        "before": before,
        "after": after,
        "net": {
            "GOV": summary.net_gov_bbl,
            "GSV": summary.net_gsv_bbl,
            "BSW": summary.net_bsw_bbl,
            "NSV": summary.net_nsv_bbl,
            "LT": summary.net_lt_bbl,
            "MT": summary.net_mt,
        }
    }


def build_inputs_from_dips(session: Session, voyage_id: int, stage: str):
    """
    Compatibility function - not used in new implementation.
    The new compute_stage() reads directly from DB tables.
    """
    return []


def preview_or_summary_totals(session: Session, voyage_id: int) -> Dict[str, Dict[str, float]]:
    """
    Returns stage totals preferring TOAYadeSummary if it exists, else computes live.
    Output: {"before": {}, "after": {}, "net": {}}
    """
    summ = session.query(TOAYadeSummary).filter(TOAYadeSummary.voyage_id == voyage_id).one_or_none()
    
    if summ:
        # Use saved summary for GOV/GSV/BSW/NSV/LT/MT, but recompute TOV/FW live
        before = {
            "TOV": 0.0,
            "FW": 0.0,
            "GOV": _afloat(summ.before_gov_bbl),
            "GSV": _afloat(summ.before_gsv_bbl),
            "BSW": _afloat(summ.before_bsw_bbl),
            "NSV": _afloat(summ.before_nsv_bbl),
            "LT": _afloat(summ.before_lt_bbl),
            "MT": _afloat(summ.before_mt),
        }
        after = {
            "TOV": 0.0,
            "FW": 0.0,
            "GOV": _afloat(summ.after_gov_bbl),
            "GSV": _afloat(summ.after_gsv_bbl),
            "BSW": _afloat(summ.after_bsw_bbl),
            "NSV": _afloat(summ.after_nsv_bbl),
            "LT": _afloat(summ.after_lt_bbl),
            "MT": _afloat(summ.after_mt),
        }

        try:
            b_live = compute_stage(session, voyage_id, "BEFORE")
            a_live = compute_stage(session, voyage_id, "AFTER")
            before["TOV"] = _afloat(b_live["totals"].get("TOV"))
            before["FW"]  = _afloat(b_live["totals"].get("FW"))
            after["TOV"]  = _afloat(a_live["totals"].get("TOV"))
            after["FW"]   = _afloat(a_live["totals"].get("FW"))
        except Exception:
            pass
        net = {
            "GOV": _afloat(summ.net_gov_bbl),
            "GSV": _afloat(summ.net_gsv_bbl),
            "BSW": _afloat(summ.net_bsw_bbl),
            "NSV": _afloat(summ.net_nsv_bbl),
            "LT": _afloat(summ.net_lt_bbl),
            "MT": _afloat(summ.net_mt),
        }
        return {"before": before, "after": after, "net": net}
    
    # Compute live from DB
    before_result = compute_stage(session, voyage_id, "BEFORE")
    after_result = compute_stage(session, voyage_id, "AFTER")
    
    before = before_result["totals"]
    after = after_result["totals"]
    
    net = {
        "TOV": 0.0,  # Not calculated for net
        "FW": 0.0,   # Not calculated for net
        "GOV": round(after["GOV"] - before["GOV"], 2),
        "GSV": round(after["GSV"] - before["GSV"], 0),
        "BSW": round(after["BSW"] - before["BSW"], 0),
        "NSV": round(after["NSV"] - before["NSV"], 0),
        "LT": round(after["LT"] - before["LT"], 0),
        "MT": round(after["MT"] - before["MT"], 0),
    }
    
    return {"before": before, "after": after, "net": net}


# ===== PDF GENERATION =====
from io import BytesIO

def build_toa_pdf_yade(voyage_id: int) -> bytes:
    """
    Generate a professional TOA PDF for YADE voyage.
    """
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.colors import HexColor, grey, whitesmoke
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    
    from db import get_session
    
    with get_session() as s:
        v = s.query(YadeVoyage).filter(YadeVoyage.id == int(voyage_id)).one_or_none()
        if not v:
            return b""
        
        totals = preview_or_summary_totals(s, voyage_id)
        
        def _fmt(x, nd=2):
            try:
                return f"{float(x):,.{nd}f}"
            except Exception:
                return "-"
        
        before = totals["before"]
        after = totals["after"]
        net = totals["net"]
        
        buf = BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            leftMargin=1.5*cm, rightMargin=1.5*cm, topMargin=2*cm, bottomMargin=2*cm
        )
        
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "Title",
            parent=styles["Heading1"],
            fontSize=16,
            textColor=HexColor("#1f4788"),
            alignment=TA_CENTER,
            spaceAfter=12
        )
        sub_style = ParagraphStyle(
            "Subtitle",
            parent=styles["Normal"],
            fontSize=11,
            textColor=HexColor("#666666"),
            alignment=TA_CENTER,
            spaceAfter=20
        )
        
        elems = []
        
        # Title
        elems.append(Paragraph("<b>TABLE OF ANALYSIS (TOA) - YADE</b>", title_style))
        
        # Header info
        date_str = str(v.date or "")
        header_line = f"<b>Date:</b> {date_str} &nbsp;&nbsp;|&nbsp;&nbsp; <b>YADE:</b> {v.yade_name or ''} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Voyage:</b> {v.voyage_no or ''} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Convoy:</b> {v.convoy_no or ''}"
        elems.append(Paragraph(header_line, sub_style))
        
        elems.append(Spacer(1, 0.5*cm))
        
        # Main data table
        headers = ["Parameter", "Before", "After", "Net"]
        rows = [
            ["TOV (bbls)", _fmt(before.get("TOV", 0)), _fmt(after.get("TOV", 0)), "-"],
            ["FW (bbls)", _fmt(before.get("FW", 0)), _fmt(after.get("FW", 0)), "-"],
            ["GOV (bbls)", _fmt(before.get("GOV", 0)), _fmt(after.get("GOV", 0)), _fmt(net.get("GOV", 0))],
            ["GSV (bbls)", _fmt(before.get("GSV", 0), 0), _fmt(after.get("GSV", 0), 0), _fmt(net.get("GSV", 0), 0)],
            ["BS&W (bbls)", _fmt(before.get("BSW", 0), 0), _fmt(after.get("BSW", 0), 0), _fmt(net.get("BSW", 0), 0)],
            ["NSV (bbls)", _fmt(before.get("NSV", 0), 0), _fmt(after.get("NSV", 0), 0), _fmt(net.get("NSV", 0), 0)],
            ["LT (bbl LT)", _fmt(before.get("LT", 0), 0), _fmt(after.get("LT", 0), 0), _fmt(net.get("LT", 0), 0)],
            ["MT (tonnes)", _fmt(before.get("MT", 0), 0), _fmt(after.get("MT", 0), 0), _fmt(net.get("MT", 0), 0)],
        ]
        
        data = [headers] + rows
        
        tbl = Table(data, colWidths=[4*cm, 3.5*cm, 3.5*cm, 3.5*cm])
        tbl.setStyle(TableStyle([
            # Header row
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#1f4788")),
            ("TEXTCOLOR", (0, 0), (-1, 0), "white"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 11),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
            
            # Data rows
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 10),
            ("ALIGN", (0, 1), (0, -1), "LEFT"),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [whitesmoke, "white"]),
            ("TOPPADDING", (0, 1), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 8),
            
            # Grid
            ("GRID", (0, 0), (-1, -1), 0.5, grey),
            ("BOX", (0, 0), (-1, -1), 1, HexColor("#1f4788")),
        ]))
        
        elems.append(tbl)
        elems.append(Spacer(1, 1*cm))
        
        # Footer
        footer_text = f"<i>Generated: {date_str} | Cargo: {v.cargo or 'N/A'} | Destination: {v.destination or 'N/A'}</i>"
        footer_style = ParagraphStyle(
            "Footer",
            parent=styles["Normal"],
            fontSize=9,
            textColor=HexColor("#999999"),
            alignment=TA_CENTER
        )
        elems.append(Paragraph(footer_text, footer_style))
        
        doc.build(elems)
        return buf.getvalue()
