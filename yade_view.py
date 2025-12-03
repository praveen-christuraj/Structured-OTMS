# yade_view.py
from __future__ import annotations
from typing import Dict, Any, Optional, List, Tuple

import streamlit as st
import pandas as pd
from datetime import date, datetime

from sqlalchemy.orm import Session
from sqlalchemy import func

from db import get_session
from models import YadeVoyage, YadeDip, TOAYadeSummary, TOAYadeStage, YadeLoadOffload
from security import SecurityManager
from deletion_approval import render_deletion_ui, DeletionApprovalManager

from toa_yade_calculator import (
    preview_or_summary_totals,
    build_toa_pdf_yade,
    build_inputs_from_dips,
    compute_and_save_summary,
)

# ----------------------------- small UI helpers -----------------------------

def _open_pdf_blob_inline(pdf_bytes: bytes) -> None:
    """Open a PDF blob in a new browser tab via JS (no circular imports)."""
    import base64, streamlit.components.v1 as components
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
            for (let i=0; i<bytes.length; i++) out[i] = bytes.charCodeAt(i);
            const blob = new Blob([out], {{type: "application/pdf"}});
            const url = URL.createObjectURL(blob);
            const w = window.open(url, "_blank");
            if(!w) alert("Please allow pop-ups to view the PDF.");
            setTimeout(()=>URL.revokeObjectURL(url), 120000);
        }})();
        </script>
        """,
        height=0,
    )

def _caution_badge(created_by: Optional[str], updated_by: Optional[str], updated_at: Optional[datetime]) -> str:
    """
    Return HTML for 'Created by' with a caution badge if edited.
    Hover shows "Edited by X on Y".
    """
    cb = (created_by or "—")
    if updated_by and updated_at:
        tip = f"Edited by {updated_by} on {updated_at.strftime('%Y-%m-%d %H:%M')}"
        return f'<span>{cb}&nbsp;&nbsp;<span title="{tip}">⚠️</span></span>'
    return f"<span>{cb}</span>"

def _two_col_header(labels: List[str], widths: List[float]) -> None:
    cols = st.columns(widths)
    for c, lbl in zip(cols, labels):
        c.markdown(f"**{lbl}**")

def _confirm_prompt(key: str, message: str) -> bool:
    """
    Simple confirm emulation (Streamlit has no native confirm).
    Returns True if user clicks Yes.
    """
    ph = st.empty()
    with ph.container(border=True):
        st.warning(message)
        c1, c2 = st.columns(2)
        yes = c1.button("✅ Yes", key=f"{key}_yes")
        no  = c2.button("✖️ No",  key=f"{key}_no")
    if yes:
        ph.empty()
        return True
    if no:
        ph.empty()
        return False
    return False

# For dips editing we support multiple possible column names found in your codebase
_DIP_COLS = [
    "id", "stage", "tank_id",
    "total_cm", "water_cm",
]

def _dip_df_for_stage(sess: Session, voyage_id: int, stage: str) -> pd.DataFrame:
    rows: List[YadeDip] = (
        sess.query(YadeDip)
        .filter(YadeDip.voyage_id == voyage_id, func.upper(YadeDip.stage) == stage.upper())
        .order_by(YadeDip.tank_id.asc())
        .all()
    )
    recs = []
    for r in rows:
        rec = {}
        for c in _DIP_COLS:
            rec[c] = getattr(r, c, None)
        recs.append(rec)
    df = pd.DataFrame(recs)
    if not df.empty and "id" in df.columns:
        df["id"] = df["id"].astype(int)
    return df

def _apply_dip_edits(sess: Session, df_before: pd.DataFrame, df_after: pd.DataFrame, voyage_id: int, user: Dict[str, Any]) -> int:
    """
    Persist edited dips for BEFORE and AFTER.
    Returns count of updated rows.
    """
    n_updated = 0
    def _update_rows(df: pd.DataFrame):
        nonlocal n_updated
        if df.empty:
            return
        for _, r in df.iterrows():
            dip_id = int(r.get("id", 0) or 0)
            if dip_id <= 0:
                continue
            obj: YadeDip = sess.query(YadeDip).filter(YadeDip.id == dip_id, YadeDip.voyage_id == voyage_id).one_or_none()
            if not obj:
                continue
            # Write back supported fields if present in DF
            for name in _DIP_COLS:
                if name in ("id", "stage"):  # don’t change id/stage here
                    continue
                if name in df.columns:
                    try:
                        setattr(obj, name, r[name] if pd.notna(r[name]) else None)
                    except Exception:
                        pass
            n_updated += 1

    _update_rows(df_before)
    _update_rows(df_after)
    # audit on voyage-level
    u = user or {}
    SecurityManager.log_audit(
        sess,
        u.get("username", "unknown"),
        "UPDATE",
        resource_type="YadeDip",
        resource_id=str(voyage_id),
        details=f"Edited YADE dips for voyage {voyage_id}",
        user_id=u.get("id"),
        location_id=st.session_state.get("active_location_id"),
    )
    return n_updated

# ----------------------------- TOA-YADE PDF helpers -----------------------------

def _kind_text(x):
    """Safe text for enums / choice fields"""
    try:
        return x.value if hasattr(x, "value") else (str(x) if x is not None else "")
    except Exception:
        return str(x or "")


def _fmt_date(d):
    try:
        return d.strftime("%d/%m/%Y")
    except Exception:
        return str(d or "")


def _fmt_time(t):
    try:
        return d.strftime("%H:%M")
    except Exception:
        return str(t or "")


def _toa_pdf_support_ok() -> bool:
    """Check if ReportLab is available."""
    try:
        import reportlab  # noqa: F401
        return True
    except ImportError:
        return False


def _build_toa_pdf_bytes(voyage_id: int) -> bytes | None:
    """
    Builds the TOA-YADE PDF using the same layout/design as the old TOA-Yade page.
    """
    if not _toa_pdf_support_ok():
        st.error("❌ PDF export failed. Please install `reportlab` (pip install reportlab).")
        return None

    try:
        # --- imports used only for PDF generation ---
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
        from io import BytesIO
        from pathlib import Path

        from models import YadeVoyage, YadeSealDetail, YadeDip
        from db import get_session
        from toa_yade_calculator import preview_or_summary_totals

        with get_session() as sess:
            # --------- Fetch core data (same as old page) ----------
            v = (
                sess.query(YadeVoyage)
                .filter(YadeVoyage.id == voyage_id)
                .one()
            )
            totals = preview_or_summary_totals(sess, voyage_id)
            before = totals.get("before", {})
            after  = totals.get("after", {})

            # --------- Create canvas ----------
            buf = BytesIO()
            c = canvas.Canvas(buf, pagesize=A4)
            W, H = A4
            LM, RM, TM, BM = 15 * mm, 15 * mm, 15 * mm, 15 * mm
            x = LM
            y = H - TM

            # ================== Section 1: Header bar + logos + title ==================
            bar_h = 22 * mm
            c.setFillColorRGB(0.98, 0.98, 0.98)
            c.setStrokeColorRGB(0.85, 0.85, 0.85)
            c.roundRect(x, y - bar_h, W - LM - RM, bar_h, 4, fill=1, stroke=1)
            c.setFillColor(colors.black)
            c.setStrokeColor(colors.black)

            Lx, Ly, Lw, Lh = x + 6 * mm, y - bar_h + 3 * mm, 26 * mm, bar_h - 6 * mm
            Rx, Ry, Rw, Rh = x + (W - LM - RM) - 26 * mm - 6 * mm, Ly, 26 * mm, Lh

            def _draw_img_or_box(path: Path | None, x0, y0, w0, h0, label: str):
                try:
                    if path and path.exists():
                        img = ImageReader(str(path))
                        iw, ih = img.getSize()
                        if iw > 0 and ih > 0:
                            scale = min(w0 / iw, h0 / ih)
                            dw, dh = iw * scale, ih * scale
                            ox = x0 + (w0 - dw) / 2.0
                            oy = y0 + (h0 - dh) / 2.0
                            c.drawImage(
                                img,
                                ox,
                                oy,
                                dw,
                                dh,
                                preserveAspectRatio=True,
                                mask="auto",
                            )
                            return
                except Exception:
                    pass

                # fallback box
                c.setStrokeColor(colors.black)
                c.rect(x0, y0, w0, h0, stroke=1, fill=0)
                c.setFont("Helvetica", 7)
                c.drawCentredString(x0 + w0 / 2, y0 - 10, label)

            def _first_existing(paths: list[str]) -> Path | None:
                for p in paths:
                    pth = Path(p)
                    if pth.exists():
                        return pth
                return None

            COMPANY_LOGO = _first_existing(
                [
                    "assets/logos/company_logo.png",
                    "assets/icons/company_logo.png",
                    "assets/company_logo.png",
                ]
            )
            YADE_LOGO = _first_existing(
                [
                    "assets/logos/yade_logo.png",
                    "assets/icons/yade_logo.png",
                    "assets/yade_logo.png",
                ]
            )

            _draw_img_or_box(COMPANY_LOGO, Lx, Ly, Lw, Lh, "Company Logo")
            _draw_img_or_box(YADE_LOGO, Rx, Ry, Rw, Rh, "YADE Logo")

            c.setFont("Helvetica-Bold", 13)
            c.drawCentredString(
                LM + (W - LM - RM) / 2, y - 7 * mm, "TRANSHIPMENT ORDER & ADVICE"
            )
            c.setFont("Helvetica", 9)
            c.drawCentredString(
                LM + (W - LM - RM) / 2,
                y - 13 * mm,
                f"Report for {v.yade_name} – Voyage {v.voyage_no}",
            )
            y -= bar_h + 6 * mm

            # ================== Section 2: Voyage metadata box ==================
            meta_h = 34 * mm
            c.setStrokeColor(colors.black)
            c.rect(LM, y - meta_h, W - LM - RM, meta_h, stroke=1, fill=0)
            c.setFont("Helvetica-Bold", 10)
            c.setFillColor(colors.black)
            c.drawString(LM + 4 * mm, y - 7 * mm, "Voyage Details")

            c.setFont("Helvetica", 9)
            mrow = y - 14 * mm
            meta_items = [
                ("Date", _fmt_date(v.date)),
                ("Time", _fmt_time(v.time)),
                ("YADE No", v.yade_name),
                ("Voyage No", v.voyage_no),
                ("Convoy No", v.convoy_no or ""),
                ("Cargo", _kind_text(getattr(v, "cargo", ""))),
                ("Destination", _kind_text(getattr(v, "destination", ""))),
                ("Loading Berth", _kind_text(getattr(v, "loading_berth", ""))),
            ]
            left = meta_items[:4]
            right = meta_items[4:]
            xL = LM + 6 * mm
            xR = LM + (W - LM - RM) / 2 + 6 * mm

            for k, vv in left:
                c.drawString(xL, mrow, f"{k}:  {vv}")
                mrow -= 6 * mm

            mrow = y - 14 * mm
            for k, vv in right:
                c.drawString(xR, mrow, f"{k}:  {vv}")
                mrow -= 6 * mm

            y -= meta_h + 10 * mm

            # ================== Section 3: Quantity table (Before / After / Loaded) ==================
            B_TOV = float(before.get("TOV", 0.0) or 0.0)
            A_TOV = float(after.get("TOV", 0.0) or 0.0)
            B_FW  = float(before.get("FW", 0.0) or 0.0)
            A_FW  = float(after.get("FW", 0.0) or 0.0)
            B_GOV = float(before.get("GOV", 0.0) or 0.0)
            A_GOV = float(after.get("GOV", 0.0) or 0.0)
            B_GSV = float(before.get("GSV", 0.0) or 0.0)
            A_GSV = float(after.get("GSV", 0.0) or 0.0)
            B_NSV = float(before.get("NSV", 0.0) or 0.0)
            A_NSV = float(after.get("NSV", 0.0) or 0.0)
            B_LT  = float(before.get("LT", 0.0) or 0.0)
            A_LT  = float(after.get("LT", 0.0) or 0.0)
            B_MT  = float(before.get("MT", 0.0) or 0.0)
            A_MT  = float(after.get("MT", 0.0) or 0.0)

            L_TOV = A_TOV - B_TOV
            L_FW  = A_FW  - B_FW
            L_GOV = A_GOV - B_GOV
            L_GSV = A_GSV - B_GSV
            L_NSV = A_NSV - B_NSV
            L_LT  = A_LT  - B_LT
            L_MT  = A_MT  - B_MT

            rows = [
                ("Total Volume (bbl)", B_TOV, A_TOV, L_TOV),
                ("Free Water (bbl)", B_FW, A_FW, L_FW),
                ("GOV (bbl)", B_GOV, A_GOV, L_GOV),
                ("GSV (bbl)", B_GSV, A_GSV, L_GSV),
                ("NSV (bbl)", B_NSV, A_NSV, L_NSV),
                ("Long Tons (LT)", B_LT, A_LT, L_LT),
                ("MT", B_MT, A_MT, L_MT),
            ]

            table_h = 7 * 18 + 28
            col_w = (W - LM - RM) / 4.0
            x_before = LM + 1.2 * col_w - 6
            x_after = LM + 2.3 * col_w - 6
            x_loaded = LM + 3.5 * col_w - 6

            c.setFont("Helvetica-Bold", 10)
            c.drawString(
                LM + 4 * mm,
                y - 7 * mm,
                "Certified Quantity loaded in the Barge",
            )
            y -= 10 * mm

            c.setFont("Helvetica-Bold", 9)
            c.drawString(LM + 6, y - 12, "Quantity")
            c.drawRightString(x_before, y - 12, "Before")
            c.drawRightString(x_after, y - 12, "After")
            c.drawRightString(x_loaded, y - 12, "Loaded")

            c.setStrokeColor(colors.black)
            c.rect(
                LM,
                y - (table_h + 18),
                (W - LM - RM),
                (table_h + 18),
                stroke=1,
                fill=0,
            )

            c.setFont("Helvetica", 9)

            def _fmt_num(v):
                try:
                    return f"{(v or 0):,.2f}"
                except Exception:
                    return "0.00"

            ry = y - 28
            for name, vb, va, vl in rows:
                c.line(LM, ry + 6, W - RM, ry + 6)
                c.drawString(LM + 6, ry - 6, str(name))
                c.drawRightString(
                    x_before, ry - 6, "" if vb is None else _fmt_num(vb)
                )
                c.drawRightString(
                    x_after, ry - 6, "" if va is None else _fmt_num(va)
                )
                c.drawRightString(
                    x_loaded, ry - 6, "" if vl is None else _fmt_num(vl)
                )
                ry -= 18

            y -= table_h + 30

            # ================== Section 4: Seal & Dip details ==================
            c.setFont("Helvetica-Bold", 10)
            c.setFillColor(colors.black)
            c.drawString(LM + 4 * mm, y - 5 * mm, "Seal & Dip Details")

            seals = (
                sess.query(YadeSealDetail)
                .filter(YadeSealDetail.voyage_id == voyage_id)
                .one_or_none()
            )
            dips_after = (
                sess.query(YadeDip)
                .filter(
                    YadeDip.voyage_id == voyage_id,
                    func.upper(YadeDip.stage) == "AFTER",
                )
                .all()
            )
            dips_map = {d.tank_id.upper(): d for d in dips_after}

            tanks = (
                ["C1", "C2", "P1", "P2", "S1", "S2"]
                if str(getattr(v, "design", "")) == "6"
                else ["P1", "P2", "S1", "S2"]
            )

            row_height = 8 * mm
            col_widths = [
                20 * mm,
                24 * mm,
                24 * mm,
                28 * mm,
                28 * mm,
                28 * mm,
                28 * mm,
            ]
            table_left_x = LM
            table_top_y = y - 7 * mm
            table_width = sum(col_widths)
            table_height = (len(tanks) + 1) * row_height

            c.setLineWidth(1)
            c.rect(
                table_left_x,
                table_top_y - table_height,
                table_width,
                table_height,
                stroke=1,
                fill=0,
            )

            # vertical lines
            current_x = table_left_x
            for w in col_widths:
                c.line(
                    current_x,
                    table_top_y,
                    current_x,
                    table_top_y - table_height,
                )
                current_x += w
            c.line(
                table_left_x + table_width,
                table_top_y,
                table_left_x + table_width,
                table_top_y - table_height,
            )

            # horizontal lines
            for i in range(len(tanks) + 2):
                row_y = table_top_y - i * row_height
                c.line(
                    table_left_x,
                    row_y,
                    table_left_x + table_width,
                    row_y,
                )

            # header row
            hdrs = [
                "Tank",
                "Total Dip (cm)",
                "Water Dip (cm)",
                "Manhole-1",
                "Manhole-2",
                "Lock No",
                "Dip Hatch",
            ]
            c.setFont("Helvetica-Bold", 9)
            header_y = table_top_y - row_height / 2 + 3
            current_x = table_left_x
            for i, h in enumerate(hdrs):
                c.drawCentredString(
                    current_x + col_widths[i] / 2,
                    header_y,
                    h,
                )
                current_x += col_widths[i]

            # data rows
            c.setFont("Helvetica", 8)
            for r_idx, tnk in enumerate(tanks):
                key = tnk.upper()
                dip_row = dips_map.get(key)
                total_dip = (
                    f"{dip_row.total_cm:.2f}" if dip_row else ""
                )
                water_dip = (
                    f"{dip_row.water_cm:.2f}" if dip_row else ""
                )

                seals_key = tnk.lower()
                mh1 = getattr(seals, f"{seals_key}_mh1", "") if seals else ""
                mh2 = getattr(seals, f"{seals_key}_mh2", "") if seals else ""
                lk = getattr(seals, f"{seals_key}_lock", "") if seals else ""
                dh = (
                    getattr(seals, f"{seals_key}_diphatch", "")
                    if seals
                    else ""
                )

                vals = [tnk, total_dip, water_dip, mh1, mh2, lk, dh]
                row_y = (
                    table_top_y
                    - (r_idx + 1) * row_height
                    - row_height / 2
                    + 3
                )
                current_x = table_left_x
                for i, vv in enumerate(vals):
                    c.drawCentredString(
                        current_x + col_widths[i] / 2,
                        row_y,
                        str(vv or ""),
                    )
                    current_x += col_widths[i]

            y -= table_height + 12 * mm

            # ================== Section 5: Authorized signatory box ==================
            sig_h = 40 * mm
            sig_y = BM + 5 * mm
            c.rect(
                LM,
                sig_y,
                W - LM - RM,
                sig_h,
                stroke=1,
                fill=0,
            )
            c.setFont("Helvetica-Bold", 10)
            c.drawString(
                LM + 4 * mm,
                sig_y + sig_h - 6 * mm,
                "Authorized Signatory",
            )

            c.setFont("Helvetica", 9)
            c.drawString(
                LM + 4 * mm,
                sig_y + 6 * mm,
                "For SEEPCO                                                         For Yade Barge Operators Ltd",
            )
            c.drawRightString(
                W - RM - 4 * mm,
                sig_y + 6 * mm,
                f"For Barge Master of {v.yade_name}",
            )

            # finish page
            c.showPage()
            c.save()
            out = buf.getvalue()
            buf.close()
            return out

    except Exception as e:
        import traceback

        st.error(f"PDF generation error: {e}")
        st.code(traceback.format_exc())
        return None

# -------------------------- main YADE view (list + actions) --------------------------

def render_yade_transactions_view(user: Dict[str, Any] | None = None, location_id: Optional[int] = None) -> None:
    """
    Shows YADE voyages with: Date, Voyage No, Convoy No, Before(NSV), After(NSV), Net(NSV),
    Created by (with caution hover if edited), and Action icons (view/delete/pdf).
    Inline "View" reveals editable Voyage fields and editable Dips (Before & After).
    Saving recomputes TOA and updates the caution indicator.
    """
    st.subheader("YADE — View Transactions")

    # Query voyages (optionally by location)
    with get_session() as s:
        q = s.query(YadeVoyage).order_by(YadeVoyage.date.desc(), YadeVoyage.id.desc())
        voyages: List[YadeVoyage] = q.all()
        if location_id:
            voyages = [v for v in voyages if int(getattr(v, "location_id", 0) or 0) == int(location_id)]

    # Get unique values for filters
    all_yades = sorted(set(v.yade_name for v in voyages if v.yade_name), key=str)
    all_convoys = sorted(set(v.convoy_no for v in voyages if v.convoy_no), key=str)
    all_creators = sorted(set(getattr(v, "created_by", None) for v in voyages if getattr(v, "created_by", None)), key=str)
    all_dates = [v.date for v in voyages if v.date]
    min_date = min(all_dates) if all_dates else date.today()
    max_date = date.today()  # No future dates allowed

    # Compact filters in 4 columns
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        filter_date = st.date_input("📅 Date", value=max_date, min_value=min_date, max_value=max_date, 
                                     format="DD/MM/YYYY", key="yade_filter_date")
    with f2:
        filter_yade = st.selectbox("🚢 YADE No", ["All"] + all_yades, key="yade_filter_yade")
    with f3:
        filter_convoy = st.selectbox("🚛 Convoy No", ["All"] + all_convoys, key="yade_filter_convoy")
    with f4:
        filter_creator = st.selectbox("👤 Created By", ["All"] + all_creators, key="yade_filter_creator")

    tabs = st.tabs(["List", "Yade Loading/Offloading"])
    with tabs[0]:
        _two_col_header(
            ["Date", "Yade No", "Convoy No", "Before NSV (bbls)", "After NSV (bbls)", "Net (bbls)", "Created by", "Action"],
            [0.13,   0.16,      0.16,        0.12,                 0.12,               0.12,        0.11,         0.08],
        )
        edit_id = st.session_state.get("yade_row_open")
        for v in voyages:
            if filter_date and v.date != filter_date:
                continue
            if filter_yade != "All" and v.yade_name != filter_yade:
                continue
            if filter_convoy != "All" and v.convoy_no != filter_convoy:
                continue
            if filter_creator != "All" and getattr(v, "created_by", None) != filter_creator:
                continue

            with get_session() as s:
                totals = preview_or_summary_totals(s, v.id)
            before_nsv = float(totals["before"].get("NSV", 0.0) or 0.0)
            after_nsv  = float(totals["after"].get("NSV", 0.0) or 0.0)
            net_nsv    = float(totals["net"].get("NSV", 0.0) or 0.0)

            cols = st.columns([0.13, 0.16, 0.16, 0.12, 0.12, 0.12, 0.11, 0.08])
            cols[0].write(str(v.date or ""))
            cols[1].write(v.yade_name or "")
            cols[2].write(v.convoy_no or "")
            cols[3].write(f"{before_nsv:,.2f}")
            cols[4].write(f"{after_nsv:,.2f}")
            cols[5].write(f"{net_nsv:,.2f}")

            created_by = getattr(v, "created_by", None)
            updated_by = getattr(v, "updated_by", None)
            updated_at = getattr(v, "updated_at", None)
            cols[6].markdown(_caution_badge(created_by, updated_by, updated_at), unsafe_allow_html=True)

            with cols[7]:
                c = st.columns(3)
                view_btn = c[0].button("👁️", key=f"yade_view_{v.id}")
                del_btn  = c[1].button("🗑️", key=f"yade_del_{v.id}")
                pdf_btn  = c[2].button("📕", key=f"yade_pdf_{v.id}")

            if pdf_btn:
                pdf = _build_toa_pdf_bytes(v.id)
                if pdf:
                    _open_pdf_blob_inline(pdf)

            if del_btn:
                st.session_state[f"yade_show_delete_ui_{v.id}"] = True

            if st.session_state.get(f"yade_show_delete_ui_{v.id}"):
                def delete_yade_record():
                    with get_session() as s:
                        obj = s.query(YadeVoyage).filter(YadeVoyage.id == v.id).one_or_none()
                        if obj:
                            from recycle_bin import RecycleBinManager
                            from models import YadeDip, YadeSampleParam, YadeSealDetail, TOAYadeSummary
                            u = user or {}
                            dips = s.query(YadeDip).filter(YadeDip.voyage_id == v.id).all()
                            sample_params = s.query(YadeSampleParam).filter(YadeSampleParam.voyage_id == v.id).all()
                            seals = s.query(YadeSealDetail).filter(YadeSealDetail.voyage_id == v.id).all()
                            toa = s.query(TOAYadeSummary).filter(TOAYadeSummary.voyage_id == v.id).all()
                            payload = RecycleBinManager.snapshot_record(obj)
                            payload["_related_dips"] = [RecycleBinManager.snapshot_record(d) for d in dips]
                            payload["_related_sample_params"] = [RecycleBinManager.snapshot_record(sp) for sp in sample_params]
                            payload["_related_seals"] = [RecycleBinManager.snapshot_record(seal) for seal in seals]
                            payload["_related_toa"] = [RecycleBinManager.snapshot_record(t) for t in toa]
                            RecycleBinManager.archive_payload(
                                session=s,
                                resource_type="YadeVoyage",
                                resource_id=str(v.id),
                                payload=payload,
                                username=u.get("username", "unknown"),
                                user_id=u.get("id"),
                                location_id=st.session_state.get("active_location_id"),
                                reason="User deleted from View Transactions",
                                label=f"Voyage {v.voyage_no or v.id}"
                            )
                            s.delete(obj)
                            s.commit()
                
                deletion_result = render_deletion_ui(
                    resource_type="YadeVoyage",
                    resource_id=v.id,
                    resource_label=f"YADE Voyage {v.voyage_no or v.id}",
                    delete_func=delete_yade_record,
                    user=user,
                    location_id=st.session_state.get("active_location_id"),
                    on_success_message="YADE voyage moved to recycle bin",
                    metadata={"voyage_no": v.voyage_no, "convoy_no": v.convoy_no},
                    button_key_prefix=f"yade_{v.id}"
                )
                
                # Close the prompt on any button click (delete success, cancel, or error)
                if deletion_result is not None:
                    st.session_state.pop(f"yade_show_delete_ui_{v.id}", None)
                    st.rerun()

            if view_btn or (edit_id == v.id):
                st.session_state["yade_row_open"] = v.id
                with st.expander(f"📝 Edit: {v.voyage_no or v.id}", expanded=True):
                    hv1 = st.columns(3)
                    new_date = hv1[0].date_input("Date", value=v.date or date.today(), key=f"yade_hdr_date_{v.id}", label_visibility="collapsed")
                    new_voy  = hv1[1].text_input("Voyage", value=v.voyage_no or '', key=f"yade_hdr_voy_{v.id}", placeholder="Voyage No")
                    new_con  = hv1[2].text_input("Convoy", value=v.convoy_no or '', key=f"yade_hdr_con_{v.id}", placeholder="Convoy No")

                    with get_session() as s:
                        df_b = _dip_df_for_stage(s, v.id, "BEFORE")
                        df_a = _dip_df_for_stage(s, v.id, "AFTER")
                        from models import YadeSampleParam
                        sp_before = s.query(YadeSampleParam).filter(
                            YadeSampleParam.voyage_id == v.id,
                            func.upper(YadeSampleParam.stage) == "BEFORE"
                        ).one_or_none()
                        sp_after = s.query(YadeSampleParam).filter(
                            YadeSampleParam.voyage_id == v.id,
                            func.upper(YadeSampleParam.stage) == "AFTER"
                        ).one_or_none()

                    scols = st.columns(2)
                    with scols[0]:
                        if not df_b.empty:
                            df_b_compact = df_b[['tank_id', 'total_cm', 'water_cm']].copy()
                        else:
                            df_b_compact = df_b
                        ed_b = st.data_editor(df_b_compact, use_container_width=True, key=f"yade_ed_b_{v.id}", hide_index=True, height=150)
                        st.caption("Sample Parameters")
                        sp_b_obs_mode = st.selectbox("Obs Mode", ["Observed API", "Observed Density"], 
                                                      index=0 if (sp_before and "API" in (sp_before.obs_mode or "")) else 1,
                                                      key=f"sp_b_mode_{v.id}")
                        sp_b_cols = st.columns(2)
                        sp_b_obs_val = sp_b_cols[0].number_input("Obs Val", value=float(sp_before.obs_val if sp_before else 35.0), 
                                                                   step=0.1, format="%.2f", key=f"sp_b_val_{v.id}")
                        sp_b_ccf = sp_b_cols[1].number_input("CCF", value=float(sp_before.ccf if sp_before else 1.0), 
                                                              step=0.001, format="%.4f", key=f"sp_b_ccf_{v.id}")
                        sp_b_temps = st.columns(2)
                        sp_b_sample_temp = sp_b_temps[0].number_input("Sample T", value=float(sp_before.sample_temp if sp_before else 60.0), 
                                                                        step=0.1, format="%.1f", key=f"sp_b_stemp_{v.id}")
                        sp_b_tank_temp = sp_b_temps[1].number_input("Tank T", value=float(sp_before.tank_temp if sp_before else 60.0), 
                                                                      step=0.1, format="%.1f", key=f"sp_b_ttemp_{v.id}")
                        sp_b_bsw = st.number_input("BS&W %", value=float(sp_before.bsw_pct if sp_before else 0.0), 
                                                    step=0.01, format="%.2f", key=f"sp_b_bsw_{v.id}")

                    with scols[1]:
                        if not df_a.empty:
                            df_a_compact = df_a[['tank_id', 'total_cm', 'water_cm']].copy()
                        else:
                            df_a_compact = df_a
                        ed_a = st.data_editor(df_a_compact, use_container_width=True, key=f"yade_ed_a_{v.id}", hide_index=True, height=150)
                        st.caption("Sample Parameters")
                        sp_a_obs_mode = st.selectbox("Obs Mode ", ["Observed API", "Observed Density"], 
                                                      index=0 if (sp_after and "API" in (sp_after.obs_mode or "")) else 1,
                                                      key=f"sp_a_mode_{v.id}")
                        sp_a_cols = st.columns(2)
                        sp_a_obs_val = sp_a_cols[0].number_input("Obs Val ", value=float(sp_after.obs_val if sp_after else 35.0), 
                                                                   step=0.1, format="%.2f", key=f"sp_a_val_{v.id}")
                        sp_a_ccf = sp_a_cols[1].number_input("CCF ", value=float(sp_after.ccf if sp_after else 1.0), 
                                                              step=0.001, format="%.4f", key=f"sp_a_ccf_{v.id}")
                        sp_a_temps = st.columns(2)
                        sp_a_sample_temp = sp_a_temps[0].number_input("Sample T ", value=float(sp_after.sample_temp if sp_after else 60.0), 
                                                                        step=0.1, format="%.1f", key=f"sp_a_stemp_{v.id}")
                        sp_a_tank_temp = sp_a_temps[1].number_input("Tank T ", value=float(sp_after.tank_temp if sp_after else 60.0), 
                                                                      step=0.1, format="%.1f", key=f"sp_a_ttemp_{v.id}")
                        sp_a_bsw = st.number_input("BS&W % ", value=float(sp_after.bsw_pct if sp_after else 0.0), 
                                                    step=0.01, format="%.2f", key=f"sp_a_bsw_{v.id}")

                    if not df_b.empty and 'id' in df_b.columns:
                        for col in ['tank_id', 'total_cm', 'water_cm']:
                            if col in ed_b.columns:
                                df_b[col] = ed_b[col]
                        ed_b = df_b
                    if not df_a.empty and 'id' in df_a.columns:
                        for col in ['tank_id', 'total_cm', 'water_cm']:
                            if col in ed_a.columns:
                                df_a[col] = ed_a[col]
                        ed_a = df_a

                    bc = st.columns(3)
                    save_btn   = bc[0].button("💾 Save", key=f"yade_save_{v.id}", use_container_width=True)
                    cancel_btn = bc[1].button("↩️ Cancel", key=f"yade_cancel_{v.id}", use_container_width=True)
                    close_btn  = bc[2].button("✖️ Close", key=f"yade_close_{v.id}", use_container_width=True)

                    if cancel_btn:
                        st.session_state["yade_row_open"] = None
                        st.rerun()

                    if close_btn:
                        st.session_state["yade_row_open"] = None
                        st.rerun()

                    if save_btn:
                        try:
                            with get_session() as s:
                                obj = s.query(YadeVoyage).filter(YadeVoyage.id == v.id).one_or_none()
                                if not obj:
                                    st.error("Record no longer exists.")
                                    return

                                obj.date = new_date
                                if hasattr(obj, "voyage_no"):
                                    obj.voyage_no = (new_voy or "").strip()
                                obj.convoy_no = (new_con or "").strip()

                                u = user or {}
                                if hasattr(obj, "updated_by"):
                                    obj.updated_by = u.get("username", "unknown")
                                if hasattr(obj, "updated_at"):
                                    obj.updated_at = datetime.now()

                                n = _apply_dip_edits(s, ed_b.copy(), ed_a.copy(), v.id, user or {})

                                from models import YadeSampleParam
                                sp_b = s.query(YadeSampleParam).filter(
                                    YadeSampleParam.voyage_id == v.id,
                                    func.upper(YadeSampleParam.stage) == "BEFORE"
                                ).one_or_none()
                                if sp_b:
                                    sp_b.obs_mode = sp_b_obs_mode
                                    sp_b.obs_val = float(sp_b_obs_val)
                                    sp_b.ccf = float(sp_b_ccf)
                                    sp_b.sample_temp = float(sp_b_sample_temp)
                                    sp_b.tank_temp = float(sp_b_tank_temp)
                                    sp_b.bsw_pct = float(sp_b_bsw)
                                
                                sp_a = s.query(YadeSampleParam).filter(
                                    YadeSampleParam.voyage_id == v.id,
                                    func.upper(YadeSampleParam.stage) == "AFTER"
                                ).one_or_none()
                                if sp_a:
                                    sp_a.obs_mode = sp_a_obs_mode
                                    sp_a.obs_val = float(sp_a_obs_val)
                                    sp_a.ccf = float(sp_a_ccf)
                                    sp_a.sample_temp = float(sp_a_sample_temp)
                                    sp_a.tank_temp = float(sp_a_tank_temp)
                                    sp_a.bsw_pct = float(sp_a_bsw)

                                from toa_yade_calculator import compute_and_save_summary
                                compute_and_save_summary(s, v.id, created_by=u.get("username","operator"))

                                SecurityManager.log_audit(
                                    s, u.get("username","unknown"), "UPDATE",
                                    resource_type="YadeVoyage",
                                    resource_id=str(obj.id),
                                    details=f"Edited YADE voyage {obj.voyage_no or obj.id}; dips: {n}, params updated",
                                    user_id=u.get("id"),
                                    location_id=st.session_state.get("active_location_id"),
                                )
                                s.commit()

                            st.success("Saved. Recomputed TOA.")
                            st.session_state["yade_row_open"] = None
                            st.rerun()

                        except Exception as ex:
                            st.error(f"Save failed: {ex}")

    # Per-row edit state
    edit_id = st.session_state.get("yade_row_open")

    # Rows with filters
    for v in []:
        # Apply filters
        if filter_date and v.date != filter_date:
            continue
        if filter_yade != "All" and v.yade_name != filter_yade:
            continue
        if filter_convoy != "All" and v.convoy_no != filter_convoy:
            continue
        if filter_creator != "All" and getattr(v, "created_by", None) != filter_creator:
            continue

        # Totals (prefer summary; else compute from dips)
        with get_session() as s:
            totals = preview_or_summary_totals(s, v.id)
        before_nsv = float(totals["before"].get("NSV", 0.0) or 0.0)
        after_nsv  = float(totals["after"].get("NSV", 0.0) or 0.0)
        net_nsv    = float(totals["net"].get("NSV", 0.0) or 0.0)

        cols = st.columns([0.13, 0.16, 0.16, 0.12, 0.12, 0.12, 0.11, 0.08])
        cols[0].write(str(v.date or ""))
        cols[1].write(v.yade_name or "")
        cols[2].write(v.convoy_no or "")
        cols[3].write(f"{before_nsv:,.2f}")
        cols[4].write(f"{after_nsv:,.2f}")
        cols[5].write(f"{net_nsv:,.2f}")

        created_by = getattr(v, "created_by", None)
        updated_by = getattr(v, "updated_by", None)
        updated_at = getattr(v, "updated_at", None)
        cols[6].markdown(_caution_badge(created_by, updated_by, updated_at), unsafe_allow_html=True)

        with cols[7]:
            c = st.columns(3)
            view_btn = c[0].button("👁️", key=f"yade_view_{v.id}")
            del_btn  = c[1].button("🗑️", key=f"yade_del_{v.id}")
            pdf_btn  = c[2].button("📕", key=f"yade_pdf_{v.id}")

        # PDF
        if pdf_btn:
            pdf = _build_toa_pdf_bytes(v.id)
            if pdf:
                _open_pdf_blob_inline(pdf)

        if del_btn:
            st.session_state[f"yade_show_delete_ui_{v.id}"] = True

        # Deletion approval UI
        if st.session_state.get(f"yade_show_delete_ui_{v.id}"):
            def delete_yade_record():
                with get_session() as s:
                    obj = s.query(YadeVoyage).filter(YadeVoyage.id == v.id).one_or_none()
                    if obj:
                        from recycle_bin import RecycleBinManager
                        from models import YadeDip, YadeSampleParam, YadeSealDetail, TOAYadeSummary
                        u = user or {}
                        dips = s.query(YadeDip).filter(YadeDip.voyage_id == v.id).all()
                        sample_params = s.query(YadeSampleParam).filter(YadeSampleParam.voyage_id == v.id).all()
                        seals = s.query(YadeSealDetail).filter(YadeSealDetail.voyage_id == v.id).all()
                        toa = s.query(TOAYadeSummary).filter(TOAYadeSummary.voyage_id == v.id).all()
                        payload = RecycleBinManager.snapshot_record(obj)
                        payload["_related_dips"] = [RecycleBinManager.snapshot_record(d) for d in dips]
                        payload["_related_sample_params"] = [RecycleBinManager.snapshot_record(sp) for sp in sample_params]
                        payload["_related_seals"] = [RecycleBinManager.snapshot_record(seal) for seal in seals]
                        payload["_related_toa"] = [RecycleBinManager.snapshot_record(t) for t in toa]
                        RecycleBinManager.archive_payload(
                            session=s,
                            resource_type="YadeVoyage",
                            resource_id=str(v.id),
                            payload=payload,
                            username=u.get("username", "unknown"),
                            user_id=u.get("id"),
                            location_id=st.session_state.get("active_location_id"),
                            reason="User deleted from View Transactions",
                            label=f"Voyage {v.voyage_no or v.id}"
                        )
                        s.delete(obj)
                        s.commit()
            
            deletion_result = render_deletion_ui(
                resource_type="YadeVoyage",
                resource_id=v.id,
                resource_label=f"YADE Voyage {v.voyage_no or v.id}",
                delete_func=delete_yade_record,
                user=user,
                location_id=st.session_state.get("active_location_id"),
                on_success_message="YADE voyage moved to recycle bin",
                metadata={"voyage_no": v.voyage_no, "convoy_no": v.convoy_no},
                button_key_prefix=f"yade_{v.id}"
            )
            
            # Close the prompt on any button click (delete success, cancel, or error)
            if deletion_result is not None:
                st.session_state.pop(f"yade_show_delete_ui_{v.id}", None)
                st.rerun()

        # View / Inline editor - COMPACT VERSION
        if view_btn or (edit_id == v.id):
            st.session_state["yade_row_open"] = v.id
            with st.expander(f"📝 Edit: {v.voyage_no or v.id}", expanded=True):
                # Compact header
                hv1 = st.columns(3)
                new_date = hv1[0].date_input("Date", value=v.date or date.today(), key=f"yade_hdr_date_{v.id}", label_visibility="collapsed")
                new_voy  = hv1[1].text_input("Voyage", value=v.voyage_no or '', key=f"yade_hdr_voy_{v.id}", placeholder="Voyage No")
                new_con  = hv1[2].text_input("Convoy", value=v.convoy_no or '', key=f"yade_hdr_con_{v.id}", placeholder="Convoy No")

                # Load dips and sample params from DB
                with get_session() as s:
                    df_b = _dip_df_for_stage(s, v.id, "BEFORE")
                    df_a = _dip_df_for_stage(s, v.id, "AFTER")
                    
                    # Load sample parameters
                    from models import YadeSampleParam
                    sp_before = s.query(YadeSampleParam).filter(
                        YadeSampleParam.voyage_id == v.id,
                        func.upper(YadeSampleParam.stage) == "BEFORE"
                    ).one_or_none()
                    sp_after = s.query(YadeSampleParam).filter(
                        YadeSampleParam.voyage_id == v.id,
                        func.upper(YadeSampleParam.stage) == "AFTER"
                    ).one_or_none()
                
                # Compact dips and sample params side-by-side
                scols = st.columns(2)
                
                with scols[0]:
                    st.markdown("**⬅️ BEFORE**")
                    # Dips
                    if not df_b.empty:
                        df_b_compact = df_b[['tank_id', 'total_cm', 'water_cm']].copy()
                    else:
                        df_b_compact = df_b
                    ed_b = st.data_editor(df_b_compact, use_container_width=True, key=f"yade_ed_b_{v.id}", hide_index=True, height=150)
                    
                    # Sample params
                    st.caption("Sample Parameters")
                    sp_b_obs_mode = st.selectbox("Obs Mode", ["Observed API", "Observed Density"], 
                                                  index=0 if (sp_before and "API" in (sp_before.obs_mode or "")) else 1,
                                                  key=f"sp_b_mode_{v.id}")
                    sp_b_cols = st.columns(2)
                    sp_b_obs_val = sp_b_cols[0].number_input("Obs Val", value=float(sp_before.obs_val if sp_before else 35.0), 
                                                               step=0.1, format="%.2f", key=f"sp_b_val_{v.id}")
                    sp_b_ccf = sp_b_cols[1].number_input("CCF", value=float(sp_before.ccf if sp_before else 1.0), 
                                                          step=0.001, format="%.4f", key=f"sp_b_ccf_{v.id}")
                    sp_b_temps = st.columns(2)
                    sp_b_sample_temp = sp_b_temps[0].number_input("Sample T", value=float(sp_before.sample_temp if sp_before else 60.0), 
                                                                    step=0.1, format="%.1f", key=f"sp_b_stemp_{v.id}")
                    sp_b_tank_temp = sp_b_temps[1].number_input("Tank T", value=float(sp_before.tank_temp if sp_before else 60.0), 
                                                                  step=0.1, format="%.1f", key=f"sp_b_ttemp_{v.id}")
                    sp_b_bsw = st.number_input("BS&W %", value=float(sp_before.bsw_pct if sp_before else 0.0), 
                                                step=0.01, format="%.2f", key=f"sp_b_bsw_{v.id}")
                
                with scols[1]:
                    st.markdown("**➡️ AFTER**")
                    # Dips
                    if not df_a.empty:
                        df_a_compact = df_a[['tank_id', 'total_cm', 'water_cm']].copy()
                    else:
                        df_a_compact = df_a
                    ed_a = st.data_editor(df_a_compact, use_container_width=True, key=f"yade_ed_a_{v.id}", hide_index=True, height=150)
                    
                    # Sample params
                    st.caption("Sample Parameters")
                    sp_a_obs_mode = st.selectbox("Obs Mode ", ["Observed API", "Observed Density"], 
                                                  index=0 if (sp_after and "API" in (sp_after.obs_mode or "")) else 1,
                                                  key=f"sp_a_mode_{v.id}")
                    sp_a_cols = st.columns(2)
                    sp_a_obs_val = sp_a_cols[0].number_input("Obs Val ", value=float(sp_after.obs_val if sp_after else 35.0), 
                                                               step=0.1, format="%.2f", key=f"sp_a_val_{v.id}")
                    sp_a_ccf = sp_a_cols[1].number_input("CCF ", value=float(sp_after.ccf if sp_after else 1.0), 
                                                          step=0.001, format="%.4f", key=f"sp_a_ccf_{v.id}")
                    sp_a_temps = st.columns(2)
                    sp_a_sample_temp = sp_a_temps[0].number_input("Sample T ", value=float(sp_after.sample_temp if sp_after else 60.0), 
                                                                    step=0.1, format="%.1f", key=f"sp_a_stemp_{v.id}")
                    sp_a_tank_temp = sp_a_temps[1].number_input("Tank T ", value=float(sp_after.tank_temp if sp_after else 60.0), 
                                                                  step=0.1, format="%.1f", key=f"sp_a_ttemp_{v.id}")
                    sp_a_bsw = st.number_input("BS&W % ", value=float(sp_after.bsw_pct if sp_after else 0.0), 
                                                step=0.01, format="%.2f", key=f"sp_a_bsw_{v.id}")

                # Restore full structure for dip saving
                if not df_b.empty and 'id' in df_b.columns:
                    for col in ['tank_id', 'total_cm', 'water_cm']:
                        if col in ed_b.columns:
                            df_b[col] = ed_b[col]
                    ed_b = df_b
                if not df_a.empty and 'id' in df_a.columns:
                    for col in ['tank_id', 'total_cm', 'water_cm']:
                        if col in ed_a.columns:
                            df_a[col] = ed_a[col]
                    ed_a = df_a

                bc = st.columns(3)
                save_btn   = bc[0].button("💾 Save", key=f"yade_save_{v.id}", use_container_width=True)
                cancel_btn = bc[1].button("↩️ Cancel", key=f"yade_cancel_{v.id}", use_container_width=True)
                close_btn  = bc[2].button("✖️ Close", key=f"yade_close_{v.id}", use_container_width=True)

                if cancel_btn:
                    st.session_state["yade_row_open"] = None
                    st.rerun()

                if close_btn:
                    st.session_state["yade_row_open"] = None
                    st.rerun()

                if save_btn:
                    try:
                        with get_session() as s:
                            # 1) Update voyage header
                            obj = s.query(YadeVoyage).filter(YadeVoyage.id == v.id).one_or_none()
                            if not obj:
                                st.error("Record no longer exists.")
                                return

                            obj.date = new_date
                            if hasattr(obj, "voyage_no"):
                                obj.voyage_no = (new_voy or "").strip()
                            obj.convoy_no = (new_con or "").strip()

                            # audit fields
                            u = user or {}
                            if hasattr(obj, "updated_by"):
                                obj.updated_by = u.get("username", "unknown")
                            if hasattr(obj, "updated_at"):
                                obj.updated_at = datetime.now()

                            # 2) Update dips (both stages)
                            n = _apply_dip_edits(s, ed_b.copy(), ed_a.copy(), v.id, user or {})

                            # 3) Update sample parameters
                            from models import YadeSampleParam
                            
                            # BEFORE params
                            sp_b = s.query(YadeSampleParam).filter(
                                YadeSampleParam.voyage_id == v.id,
                                func.upper(YadeSampleParam.stage) == "BEFORE"
                            ).one_or_none()
                            if sp_b:
                                sp_b.obs_mode = sp_b_obs_mode
                                sp_b.obs_val = float(sp_b_obs_val)
                                sp_b.ccf = float(sp_b_ccf)
                                sp_b.sample_temp = float(sp_b_sample_temp)
                                sp_b.tank_temp = float(sp_b_tank_temp)
                                sp_b.bsw_pct = float(sp_b_bsw)
                            
                            # AFTER params
                            sp_a = s.query(YadeSampleParam).filter(
                                YadeSampleParam.voyage_id == v.id,
                                func.upper(YadeSampleParam.stage) == "AFTER"
                            ).one_or_none()
                            if sp_a:
                                sp_a.obs_mode = sp_a_obs_mode
                                sp_a.obs_val = float(sp_a_obs_val)
                                sp_a.ccf = float(sp_a_ccf)
                                sp_a.sample_temp = float(sp_a_sample_temp)
                                sp_a.tank_temp = float(sp_a_tank_temp)
                                sp_a.bsw_pct = float(sp_a_bsw)

                            # 4) Recompute TOA (persist summary)
                            from toa_yade_calculator import compute_and_save_summary
                            compute_and_save_summary(s, v.id, created_by=u.get("username","operator"))

                            # 5) Audit save
                            SecurityManager.log_audit(
                                s, u.get("username","unknown"), "UPDATE",
                                resource_type="YadeVoyage",
                                resource_id=str(obj.id),
                                details=f"Edited YADE voyage {obj.voyage_no or obj.id}; dips: {n}, params updated",
                                user_id=u.get("id"),
                                location_id=st.session_state.get("active_location_id"),
                            )
                            s.commit()

                        st.success("Saved. Recomputed TOA.")
                        st.session_state["yade_row_open"] = None
                        st.rerun()

                    except Exception as ex:
                        st.error(f"Save failed: {ex}")
    with tabs[1]:
        # Compact filter row (date range + yade + convoy)
        with get_session() as s:
            q = s.query(YadeVoyage).order_by(YadeVoyage.date.desc(), YadeVoyage.id.desc())
            voyages2: List[YadeVoyage] = q.all()
            if location_id:
                voyages2 = [v for v in voyages2 if int(getattr(v, "location_id", 0) or 0) == int(location_id)]

            # Build master rows (used for DB sync and filtering)
            ids = [v.id for v in voyages2]
            stages = s.query(TOAYadeStage).filter(TOAYadeStage.voyage_id.in_(ids)).all()
            smap: Dict[int, Dict[str, TOAYadeStage]] = {}
            for stg in stages:
                k = (stg.stage or "").strip().lower()
                smap.setdefault(stg.voyage_id, {})[k] = stg

            rows = []
            for v in voyages2:
                stg = smap.get(v.id, {})
                b = stg.get("before")
                a = stg.get("after")
                rob_q = float(getattr(b, "nsv_bbl", 0.0) or 0.0)
                rob_w = float(getattr(b, "fw_bbl", 0.0) or 0.0)
                tob_q = float(getattr(a, "nsv_bbl", 0.0) or 0.0)
                tob_w = float(getattr(a, "fw_bbl", 0.0) or 0.0)
                rows.append({
                    "Date": v.date,
                    "Convoy no": v.convoy_no or "",
                    "Yade No": v.yade_name or "",
                    "ROB Qty": round(rob_q, 2),
                    "ROB Water": round(rob_w, 2),
                    "TOB Qty": round(tob_q, 2),
                    "TOB Water": round(tob_w, 2),
                    "Net Loaded/Unloaded (bbls)": round(abs(float(tob_q - rob_q)), 2),
                    "Net Water Loaded/Unloaded (bbls)": round(abs(float(tob_w - rob_w)), 2),
                    "_voyage_id": v.id,
                    "_location_id": int(getattr(v, "location_id", 0) or 0),
                })

            # Persist to DB (upsert per voyage)
            for r in rows:
                try:
                    obj = s.query(YadeLoadOffload).filter(YadeLoadOffload.voyage_id == int(r["_voyage_id"]) ).one_or_none()
                    if not obj:
                        obj = YadeLoadOffload(
                            location_id=int(r["_location_id"]),
                            voyage_id=int(r["_voyage_id"]),
                            date=r["Date"],
                            convoy_no=str(r["Convoy no"]),
                            yade_no=str(r["Yade No"]),
                            rob_qty_bbl=float(r["ROB Qty"]),
                            rob_fw_bbl=float(r["ROB Water"]),
                            tob_qty_bbl=float(r["TOB Qty"]),
                            tob_fw_bbl=float(r["TOB Water"]),
                            net_qty_bbl=float(r["Net Loaded/Unloaded (bbls)"]),
                            net_fw_bbl=float(r["Net Water Loaded/Unloaded (bbls)"]),
                            created_by=(user or {}).get("username", "system"),
                        )
                        s.add(obj)
                    else:
                        obj.date = r["Date"]
                        obj.convoy_no = str(r["Convoy no"]) 
                        obj.yade_no = str(r["Yade No"]) 
                        obj.rob_qty_bbl = float(r["ROB Qty"]) 
                        obj.rob_fw_bbl = float(r["ROB Water"]) 
                        obj.tob_qty_bbl = float(r["TOB Qty"]) 
                        obj.tob_fw_bbl = float(r["TOB Water"]) 
                        obj.net_qty_bbl = abs(float(r["Net Loaded/Unloaded (bbls)"])) 
                        obj.net_fw_bbl = abs(float(r["Net Water Loaded/Unloaded (bbls)"])) 
                        obj.updated_by = (user or {}).get("username", "system")
                    s.flush()
                except Exception:
                    pass
            try:
                s.commit()
            except Exception:
                pass

        # Apply existing filters
        frows = []
        for r in rows:
            if filter_date and r["Date"] != filter_date:
                continue
            if filter_yade != "All" and r["Yade No"] != filter_yade:
                continue
            if filter_convoy != "All" and r["Convoy no"] != filter_convoy:
                continue
            frows.append(r)

        # Sort and add S.No
        frows = sorted(frows, key=lambda x: x["Date"], reverse=True)
        for i, r in enumerate(frows, start=1):
            r["S.no"] = i

        disp_cols = [
            "S.no",
            "Date",
            "Convoy no",
            "Yade No",
            "ROB Qty",
            "ROB Water",
            "TOB Qty",
            "TOB Water",
            "Net Loaded/Unloaded (bbls)",
            "Net Water Loaded/Unloaded (bbls)",
        ]
        df_disp = pd.DataFrame([{k: r[k] for k in disp_cols} for r in frows])
        if df_disp.empty:
            st.info("No records for the selected filters.")
            return
        st.dataframe(df_disp, use_container_width=True)

        # Downloads: CSV, XLSX, PDF and View PDF
        csv_bytes = df_disp.to_csv(index=False).encode("utf-8")
        from io import BytesIO
        xbuf = BytesIO()
        with pd.ExcelWriter(xbuf, engine="xlsxwriter") as writer:
            df_disp.to_excel(writer, index=False, sheet_name="Yade LO")
        xbuf.seek(0)

        def _generate_lo_pdf(dfpdf: pd.DataFrame) -> bytes:
            try:
                from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
                from reportlab.lib.pagesizes import A4, landscape
                from reportlab.lib import colors
                from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                from reportlab.lib.units import cm
                buf = BytesIO()
                doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=0.6*cm, rightMargin=0.6*cm, topMargin=0.7*cm, bottomMargin=0.7*cm)
                styles = getSampleStyleSheet()
                title = Paragraph("Yade Loading/Offloading", ParagraphStyle(name="title", parent=styles["Heading2"], alignment=1))
                elements = [title, Spacer(1, 0.3*cm)]
                headers = dfpdf.columns.tolist()
                data = [headers] + dfpdf.astype(str).values.tolist()
                tbl = Table(data, repeatRows=1)
                tbl.setStyle(TableStyle([
                    ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
                    ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f5f7fb")),
                    ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
                    ("ALIGN", (0,0), (-1,-1), "CENTER"),
                    ("FONTSIZE", (0,0), (-1,-1), 9),
                    ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#fbfcff")]),
                ]))
                elements.append(tbl)
                doc.build(elements)
                out = buf.getvalue()
                buf.close()
                return out
            except Exception:
                return b""

        pdf_bytes = _generate_lo_pdf(df_disp)
        btn_cols = st.columns(4)
        btn_cols[0].download_button("📥 CSV", data=csv_bytes, file_name="yade_loading_offloading.csv", mime="text/csv", use_container_width=True)
        btn_cols[1].download_button("📥 XLSX", data=xbuf.getvalue(), file_name="yade_loading_offloading.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        btn_cols[2].download_button("📥 PDF", data=pdf_bytes or b"", file_name="yade_loading_offloading.pdf", mime="application/pdf", use_container_width=True)
        if btn_cols[3].button("👁️ View PDF", use_container_width=True):
            if pdf_bytes:
                _open_pdf_blob_inline(pdf_bytes)
