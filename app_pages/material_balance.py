from __future__ import annotations

from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Any, Dict, Optional

import base64
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from db import get_session
from ui import header
from auth import AuthManager
from material_balance_config import MaterialBalanceConfig
from material_balance_calculator import MaterialBalanceCalculator
from location_config import get_page_section_config
from report_engine import get_columns_for_source, ReportEngine
from models import get_custom_table_model
from ui_components import FormBuilder, Notifications, DashboardCard, TableDisplay, apply_custom_css

try:
    from models import Location, Tank, OTRRecord
except Exception:
    Location, Tank, OTRRecord = None, None, None  # type: ignore


def _guard_location(active_location_id: Optional[int]) -> tuple[Optional[Location], Optional[str]]:
    """Ensure there is an active location and return (Location, label)."""
    if not active_location_id:
        st.error("No active location selected. Please select a location from the Home page.")
        return None, None
    if Location is None:
        st.error("Location model is not available.")
        return None, None
    with get_session() as s:
        loc = s.query(Location).get(active_location_id)
        if not loc:
            st.error("Location not found. Please re-select on Home.")
            return None, None
        return loc, f"{loc.name} ({loc.code})"


def _get_otr_first_date(location_id: int) -> Optional[date]:
    if OTRRecord is None:
        return None
    try:
        from sqlalchemy import func
        with get_session() as s:
            dmin = (
                s.query(func.min(OTRRecord.date))
                .filter(OTRRecord.location_id == location_id)
                .scalar()
            )
        return dmin
    except Exception:
        return None

def _get_first_date_for_sources(location_id: int, columns_cfg: list) -> Optional[date]:
    try:
        sources = [c.get("data_source") for c in columns_cfg if c.get("data_source")]
        candidates = []
        for src in sources:
            Model = None
            try:
                if src in ReportEngine.DATA_SOURCES:
                    Model = ReportEngine.DATA_SOURCES[src]
                else:
                    Model = get_custom_table_model(src)
            except Exception:
                Model = None
            if not Model:
                continue
            cols = get_columns_for_source(src)
            date_fields = [c.get("field") for c in cols if c.get("type") == "date"]
            if not date_fields:
                continue
            field = date_fields[0]
            with get_session() as s:
                q = s.query(getattr(Model, field))
                if hasattr(Model, "location_id"):
                    q = q.filter(getattr(Model, "location_id") == location_id)
                v = q.order_by(getattr(Model, field).asc()).limit(1).scalar()
                if v:
                    candidates.append(v)
        if not candidates:
            return None
        return min(candidates)
    except Exception:
        return None


def _build_pdf(dataframe: pd.DataFrame, df_with_totals: pd.DataFrame, filter_info: str,
               location_name: str, username: str) -> bytes:
    """Generate professional Material Balance PDF report (A4 landscape, 0.5 cm margins)."""
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=0.5 * cm,
        rightMargin=0.5 * cm,
        topMargin=0.5 * cm,
        bottomMargin=0.5 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "MB_TITLE",
        parent=styles["Heading1"],
        fontSize=16,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1f4788"),
    )
    subtitle_style = ParagraphStyle(
        "MB_SUBTITLE",
        parent=styles["Normal"],
        fontSize=10,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#666666"),
    )

    elements = []
    elements.append(
        Paragraph(f"<b>MATERIAL BALANCE REPORT</b><br/><font size=14>{location_name}</font>", title_style)
    )
    elements.append(
        Paragraph(
            f"{filter_info}<br/>Generated: {datetime.now().strftime('%d-%b-%Y %H:%M')}",
            subtitle_style,
        )
    )
    elements.append(Spacer(1, 0.4 * cm))

    page_width = landscape(A4)[0] - (1.0 * cm)
    num_cols = len(df_with_totals.columns)
    col_widths = [page_width / num_cols for _ in range(num_cols)]

    header_style = ParagraphStyle(
        "MB_HEADER",
        parent=styles["Normal"],
        fontSize=7,
        leading=9,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    )

    table_data = [
        [
            Paragraph(f"<b><font color='white'>{col}</font></b>", header_style)
            for col in df_with_totals.columns
        ]
    ]

    cell_style = ParagraphStyle(
        "MB_CELL",
        parent=styles["Normal"],
        fontSize=6,
        leading=8,
        alignment=TA_CENTER,
    )

    for idx, row in df_with_totals.iterrows():
        row_cells = []
        for col in df_with_totals.columns:
            val = row[col]
            if col == "Date":
                cell_text = str(val)
            elif col == "Loss/Gain" and val not in ("", "TOTAL"):
                try:
                    numeric_val = float(val)
                    color = "#28a745" if numeric_val >= 0 else "#dc3545"
                    cell_text = f"<font color='{color}'><b>{numeric_val:,.2f}</b></font>"
                except Exception:
                    cell_text = str(val)
            elif val in ("", "TOTAL"):
                cell_text = str(val)
            else:
                try:
                    cell_text = f"{float(val):,.2f}"
                except Exception:
                    cell_text = str(val)

            if idx == len(df_with_totals) - 1 and val not in ("",):
                cell_text = f"<b>{cell_text}</b>"

            row_cells.append(Paragraph(cell_text, cell_style))
        table_data.append(row_cells)

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4788")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 7),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
                ("TOPPADDING", (0, 0), (-1, 0), 5),
                ("BACKGROUND", (0, 1), (-1, -2), colors.HexColor("#f8f9fa")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f8f9fa")]),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e9ecef")),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 6),
                ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#333333")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#1f4788")),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 1), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
            ]
        )
    )

    elements.append(table)
    elements.append(Spacer(1, 0.3 * cm))
    footer = Paragraph(
        f"<font size=7 color='#666666'>Generated by: {username} | OTMS - Oil Terminal Management System | "
        f"{datetime.now().strftime('%d-%b-%Y %H:%M:%S')}</font>",
        subtitle_style,
    )
    elements.append(footer)

    doc.build(elements)
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data

def _render_table_html(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    th = "".join([f"<th style='border:1px solid #ccc;padding:4px;background:#1f4788;color:#fff;font-weight:bold;font-size:12px'>{c}</th>" for c in cols])
    rows = []
    for _, r in df.iterrows():
        tds = []
        for c in cols:
            v = r[c]
            if c != "Date" and v not in ("", "TOTAL"):
                try:
                    v = f"{float(v):,.2f}"
                except Exception:
                    v = str(v)
            else:
                v = str(v)
            tds.append(f"<td style='border:1px solid #ccc;padding:4px;font-size:12px;text-align:center'>{v}</td>")
        rows.append("<tr>" + "".join(tds) + "</tr>")
    table = (
        "<div style='overflow-x:auto'>"
        + "<table style='border-collapse:collapse;width:100%'>"
        + f"<thead><tr>{th}</tr></thead>"
        + f"<tbody>{''.join(rows)}</tbody>"
        + "</table></div>"
    )
    return table


def render_material_balance_page(active_location_id: Optional[int], user: Dict[str, Any] | None) -> None:
    """Main Material Balance page for the rebuilt app."""
    header("Material Balance")

    # Admin-IT cannot access operational pages
    if user and user.get("role") == "admin-it":
        st.error("Access Denied: Admin-IT users do not have access to operational pages.")
        return

    # Guard location and user-location access
    loc, loc_label = _guard_location(active_location_id)
    if not loc:
        return

    if user and not AuthManager.can_access_location(user, loc.id):
        st.error("You do not have access to this location.")
        return

    location_code = loc.code
    location_name = loc.name
    st.info(f"📍 **Active Location:** {location_name} ({location_code})")

    st.markdown("### 📊 Material Balance Report")
    st.caption("Auto-calculated from OTR records based on the configured daily window.")

    # Check if material balance is configured for this location
    use_custom = False
    custom_cols_cfg = {}
    try:
        with get_session() as s:
            custom_cols_cfg = get_page_section_config(s, loc.id, page="material_balance", section="columns") or {}
    except Exception:
        custom_cols_cfg = {}

    custom_cols = list(custom_cols_cfg.get("columns", []))
    if custom_cols:
        use_custom = True
        st.success("Material Balance columns: Custom configuration active")
    else:
        cfg = MaterialBalanceConfig.get_config(location_code)
        if not cfg:
            st.warning(f"Material Balance is not configured for {location_name}")
            st.info("Please contact administrator to configure material balance for this location.")
            with st.expander("Debug Info"):
                st.write(f"Location Code: '{location_code}'")
                st.write(f"Available Configs: {list(MaterialBalanceConfig.LOCATION_COLUMNS.keys())}")
            return
        st.success(f"Material Balance configured for {cfg['name']}")

    # -------- Filters --------
    st.markdown("#### Filters")
    col_from, col_to, col_tank = st.columns(3)

    otr_first = _get_otr_first_date(loc.id)
    custom_cols = []
    try:
        with get_session() as s:
            custom_cols_cfg = get_page_section_config(s, loc.id, page="material_balance", section="columns") or {}
        custom_cols = list(custom_cols_cfg.get("columns", []))
    except Exception:
        custom_cols = []
    src_first = _get_first_date_for_sources(loc.id, custom_cols) if custom_cols else None
    earliest_candidates = [d for d in [src_first, otr_first] if d]
    earliest_first = min(earliest_candidates) if earliest_candidates else (date.today() - timedelta(days=7))
    default_from = earliest_first
    today = date.today()

    with col_from:
        mb_from = st.date_input(
            "From Date",
            value=st.session_state.get("mb_from", default_from),
            min_value=earliest_first,
            max_value=today,
            key="mb_from",
        )
    with col_to:
        mb_to = st.date_input(
            "To Date",
            value=st.session_state.get("mb_to", today),
            min_value=mb_from or earliest_first,
            max_value=today,
            key="mb_to",
        )

    # Clamp selected dates within allowed bounds
    if mb_from and mb_from < earliest_first:
        mb_from = earliest_first
    if mb_to and mb_to > today:
        mb_to = today

    with col_tank:
        if Tank is not None:
            with get_session() as s:
                tanks_all = (
                    s.query(Tank)
                    .filter(Tank.location_id == loc.id)
                    .order_by(Tank.name)
                    .all()
                )
            tank_opts = ["All Tanks"] + [t.name for t in tanks_all]
        else:
            tank_opts = ["All Tanks"]
        f_tank = st.selectbox("Tank", tank_opts, index=0, key="mb_tank")

    st.markdown("---")

    # Determine earliest OTR date for continuity
    earliest_otr = _get_otr_first_date(loc.id)

    try:
        earliest_allowed = earliest_first
        # Always calculate from earliest date to maintain continuity of opening/closing stocks
        # The date filter will be applied to the display only
        calc_from = earliest_allowed
        # Ensure end date is not in the future
        calc_to = mb_to if (mb_to and mb_to <= today) else today

        if use_custom:
            mb_rows = MaterialBalanceCalculator.calculate_material_balance_custom(
                entries=None,
                date_from=calc_from,
                date_to=calc_to,
                location_id=loc.id,
            )
        else:
            mb_rows = MaterialBalanceCalculator.calculate_material_balance(
                entries=None,
                location_code=location_code,
                date_from=calc_from,
                date_to=calc_to,
                location_id=loc.id,
            )

        if not mb_rows:
            st.info("No data available for material balance calculation.")
            st.info("Add transactions in Tank Transactions to see material balance here.")
            return

        df = pd.DataFrame(mb_rows)
        if df.empty:
            st.info("No data available for material balance calculation.")
            st.info("Add transactions in Tank Transactions to see material balance here.")
            return

        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
        if df.empty:
            st.info("No data available for material balance calculation.")
            return

        df_full = df.copy()

        def _anchor_value(series, default=0.0) -> float:
            try:
                raw = series
                if isinstance(raw, str):
                    raw = raw.replace(",", "")
                return float(raw if raw not in (None, "") else default)
            except Exception:
                try:
                    return float(raw)
                except Exception:
                    return float(default)

        # Apply date filter
        mask = (df_full["Date"].dt.date >= mb_from) & (df_full["Date"].dt.date <= mb_to)
        df = df_full.loc[mask].copy()
        if df.empty:
            st.info("No material balance rows within the selected filter range.")
            return

        # Opening stock: use the opening stock from the first filtered date
        # This is already calculated correctly in the material balance (previous day's closing)
        if "Opening Stock" in df.columns:
            opening_anchor = _anchor_value(df["Opening Stock"].iloc[0])
        else:
            opening_anchor = 0.0

        # Closing stock: use the closing stock from the last filtered date
        if "Closing Stock" in df.columns:
            closing_anchor = _anchor_value(df["Closing Stock"].iloc[-1])
        else:
            closing_anchor = 0.0

        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
        total_days = len(df)

        if use_custom:
            try:
                with get_session() as s:
                    custom_cols_cfg = get_page_section_config(s, loc.id, page="material_balance", section="columns") or {}
                custom_cols = list(custom_cols_cfg.get("columns", []))
            except Exception:
                custom_cols = []
            opening_labels = [c.get("label") for c in custom_cols if (c.get("type") or "").lower() == "opening"]
            closing_labels = [c.get("label") for c in custom_cols if (c.get("type") or "").lower() == "closing"]
            receipt_labels = [c.get("label") for c in custom_cols if (c.get("type") or "").lower() == "receipt"]
            dispatch_labels = [c.get("label") for c in custom_cols if (c.get("type") or "").lower() == "dispatch"]

            ordered_cols = ["Date"]
            if opening_labels and opening_labels[0] in df.columns:
                ordered_cols.append(opening_labels[0])
            elif "Opening Stock" in df.columns:
                ordered_cols.append("Opening Stock")
            for lbl in receipt_labels:
                if lbl in df.columns:
                    ordered_cols.append(lbl)
            for lbl in dispatch_labels:
                if lbl in df.columns:
                    ordered_cols.append(lbl)
            if "Book Closing Stock" in df.columns:
                ordered_cols.append("Book Closing Stock")
            if closing_labels and closing_labels[0] in df.columns:
                ordered_cols.append(closing_labels[0])
            elif "Closing Stock" in df.columns:
                ordered_cols.append("Closing Stock")
            if "Loss/Gain" in df.columns:
                ordered_cols.append("Loss/Gain")

            # Append any remaining columns not captured
            for col in df.columns:
                if col not in ordered_cols:
                    ordered_cols.append(col)
            df = df[ordered_cols]

        if use_custom:
            st.markdown(f"#### 📊 Material Balance - Custom ({total_days} days)")
        else:
            st.markdown(f"#### 📊 Material Balance - {cfg['name']} ({total_days} days)")
        st.caption("Auto-calculated from OTR records")

        # Summary metrics
        st.markdown("---")
        st.markdown("#### 📊 Summary")

        total_opening = opening_anchor
        total_closing = closing_anchor

        if use_custom:
            receipt_columns = [c.get("label") for c in custom_cols if c.get("type") == "receipt" and c.get("label") in df.columns]
        else:
            receipt_columns = [c for c in df.columns if "Receipt" in c and c not in ["Book Closing Stock"]]
        total_receipts = sum(df[c].sum() for c in receipt_columns) if receipt_columns else 0.0

        if use_custom:
            dispatch_columns = [c.get("label") for c in custom_cols if c.get("type") == "dispatch" and c.get("label") in df.columns]
        else:
            dispatch_columns = [c for c in df.columns if "Dispatch" in c or "dispatch" in c]
        total_dispatches = sum(df[c].sum() for c in dispatch_columns) if dispatch_columns else 0.0

        total_loss_gain = df["Loss/Gain"].sum() if "Loss/Gain" in df.columns else 0.0
        loss_gain_pct = (total_loss_gain / total_receipts * 100.0) if total_receipts > 0 else 0.0

        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            st.metric("Opening Stock", f"{total_opening:,.0f} bbls")
        with c2:
            st.metric("Total Receipts", f"{total_receipts:,.0f} bbls")
        with c3:
            st.metric("Total Dispatches", f"{total_dispatches:,.0f} bbls")
        with c4:
            st.metric("Closing Stock", f"{total_closing:,.0f} bbls")
        with c5:
            st.metric(
                "Total Loss/Gain",
                f"{total_loss_gain:,.2f} bbls",
                delta=f"{loss_gain_pct:.2f}%",
                delta_color="normal" if total_loss_gain >= 0 else "inverse",
            )

        st.caption(
            "Opening/Closing stocks always reflect the full data range; other metrics follow the active filters."
        )

        # Table with totals row
        st.markdown("---")
        
        # Identify opening/closing columns (including custom ones) that should not have totals
        exclude_from_totals = ["Opening Stock", "Closing Stock", "Book Closing Stock"]
        if use_custom:
            # Add custom opening and closing column labels
            opening_labels = [c.get("label") for c in custom_cols if (c.get("type") or "").lower() == "opening"]
            closing_labels = [c.get("label") for c in custom_cols if (c.get("type") or "").lower() == "closing"]
            exclude_from_totals.extend(opening_labels)
            exclude_from_totals.extend(closing_labels)
        
        totals_row: Dict[str, Any] = {"Date": "TOTAL"}
        for col in df.columns:
            if col == "Date":
                continue
            # Skip totals for Opening Stock, Closing Stock, and Book Closing Stock (they are just stock values, not cumulative)
            if col in exclude_from_totals:
                totals_row[col] = ""
            elif col == "Loss/Gain":
                totals_row[col] = round(df[col].sum(), 2)
            else:
                totals_row[col] = round(df[col].sum(), 2)

        df_with_totals = pd.concat([df, pd.DataFrame([totals_row])], ignore_index=True)

        st.markdown(_render_table_html(df_with_totals), unsafe_allow_html=True)

        try:
            from sqlalchemy import inspect, text
            from db import engine
            from sqlalchemy.types import Float, Text
            insp = inspect(engine)
            table_name = f"material_balance_{loc.id}"
            df_save = df.copy()
            df_save = df_save[df_save["Date"] != "TOTAL"]
            if table_name in insp.get_table_names():
                existing_cols = {c.get("name") for c in insp.get_columns(table_name)}
                desired_cols = list(df_save.columns)
                backend = "sqlite"
                try:
                    backend = engine.url.get_backend_name()
                except Exception:
                    backend = "sqlite"
                add_stmts = []
                for col in desired_cols:
                    if col not in existing_cols:
                        if col == "Date":
                            col_type = "TEXT" if backend == "sqlite" else ("DATE" if backend in ["postgresql", "mysql"] else "TEXT")
                        else:
                            col_type = "REAL" if backend == "sqlite" else ("DOUBLE PRECISION" if backend == "postgresql" else "DOUBLE")
                        add_stmts.append(f"ALTER TABLE {table_name} ADD COLUMN \"{col}\" {col_type}")
                if add_stmts:
                    with engine.begin() as conn:
                        for stmt in add_stmts:
                            try:
                                conn.execute(text(stmt))
                            except Exception:
                                pass
                with get_session() as s:
                    try:
                        s.execute(
                            text(f"DELETE FROM {table_name} WHERE Date BETWEEN :d1 AND :d2"),
                            {"d1": df_save["Date"].iloc[0], "d2": df_save["Date"].iloc[-1]},
                        )
                        s.commit()
                    except Exception:
                        pass
            # Persist material balance per location table (creates if missing)
            dtype_map = {}
            for c in df_save.columns:
                if c == "Date":
                    dtype_map[c] = Text()
                else:
                    dtype_map[c] = Float()
            df_save.to_sql(table_name, con=engine, if_exists="append", index=False, dtype=dtype_map)
        except Exception:
            pass

        # Export options
        st.markdown("---")
        st.markdown("#### 📤 Export Options")
        ex1, ex2, ex3 = st.columns(3)

        with ex1:
            fmt = st.selectbox("Download as", ["CSV", "XLSX"], index=0, key="mb_dl_fmt_new")
            if fmt == "CSV":
                data_bytes = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "⬇️ Download",
                    data=data_bytes,
                    file_name=f"MaterialBalance_{loc.code}_{mb_from}_{mb_to}.csv",
                    mime="text/csv",
                    key="mb_dl_csv_new",
                    use_container_width=True,
                )
            else:
                bio = BytesIO()
                with pd.ExcelWriter(bio, engine="xlsxwriter") as writer:
                    df.to_excel(writer, sheet_name="MaterialBalance", index=False)
                st.download_button(
                    "⬇️ Download",
                    data=bio.getvalue(),
                    file_name=f"MaterialBalance_{loc.code}_{mb_from}_{mb_to}.xlsx",
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                    key="mb_dl_xlsx_new",
                    use_container_width=True,
                )

        filter_info = f"Tank: {f_tank} | Period: {mb_from} to {mb_to}"

        with ex2:
            if st.button("📄", key="mb_pdf_dl_new", use_container_width=True, help="Download PDF"):
                pdf_bytes = _build_pdf(df, df_with_totals, filter_info, location_name, user["username"])
                st.download_button(
                    "💾 Save PDF",
                    data=pdf_bytes,
                    file_name=f"MaterialBalance_{loc.code}_{mb_from}_{mb_to}.pdf",
                    mime="application/pdf",
                    key="mb_pdf_dl_real_new",
                    use_container_width=True,
                )

        with ex3:
            if st.button("👁️", key="mb_pdf_view_new", use_container_width=True, help="View PDF"):
                pdf_bytes = _build_pdf(df, df_with_totals, filter_info, location_name, user["username"])
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
                    height=0,
                )
                st.success("PDF opened in new tab.")

    except Exception as ex:
        st.error(f"Failed to calculate material balance: {ex}")
        import traceback

        with st.expander("Error Details"):
            st.code(traceback.format_exc())
