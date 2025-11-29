import re
import json
from datetime import date, datetime
from uuid import uuid4

import pandas as pd
import streamlit as st

from db import get_session
from ui import header
from auth import AuthManager
from permission_manager import PermissionManager
from location_config import LocationConfig


def render_bccr_page(active_location_id, user):
    header("BCCR")

    if not user:
        st.error("User session expired. Please sign in again.")
        st.stop()

    role = (user.get("role") or "").lower()
    if role == "admin-it":
        st.error("🚫 Access Denied: Admin-IT users do not have access to operational pages.")
        st.stop()

    if not active_location_id:
        st.error("⚠️ No active location selected. Please pick a location from Home.")
        st.stop()

    try:
        with get_session() as s:
            cfg = LocationConfig.get_config(s, active_location_id)
        if (cfg.get("page_access") or {}).get("BCCR") is False:
            st.error("⚠️ BCCR page is disabled for this location.")
            st.stop()
    except Exception:
        pass

    def _canon(txt):
        return re.sub(r"[^A-Z0-9]", "", str(txt or "").upper())

    allowed_loc_tokens = {"JETTY", "ASEMOKU", "ASEMOKUJETTY", "NDONI"}
    lagos_tokens = {"LAGOSHO", "LAGOS", "HO"}

    with get_session() as s:
        from location_manager import LocationManager
        current_loc = LocationManager.get_location_by_id(s, active_location_id)
        if not current_loc:
            st.error("Location not found.")
            st.stop()
        tokens = {_canon(current_loc.code), _canon(current_loc.name)}
        is_allowed_location = bool(tokens & allowed_loc_tokens)
        is_lagos_viewer = bool(tokens & lagos_tokens)

    can_select_location = role in ["admin-operations", "manager"] or is_lagos_viewer

    target_location_id = active_location_id
    if "bccr_target_location_id" not in st.session_state:
        st.session_state["bccr_target_location_id"] = active_location_id

    if can_select_location:
        with get_session() as s:
            from models import Location
            def _eligible(loc_obj):
                t = {_canon(loc_obj.code), _canon(loc_obj.name)}
                return bool(t & allowed_loc_tokens)
            eligible = [loc for loc in s.query(Location).order_by(Location.name).all() if _eligible(loc)]
        if eligible:
            options = {loc.id: f"{loc.name} ({loc.code})" for loc in eligible}
            default_id = st.session_state.get("bccr_target_location_id", active_location_id)
            if default_id not in options:
                default_id = eligible[0].id
            idx = [i for i, (lid, _) in enumerate(sorted(options.items(), key=lambda x: x[1])) if lid == default_id]
            target_location_id = st.selectbox(
                "📍 Select BCCR Location",
                options=sorted(options.items(), key=lambda x: x[1]),
                format_func=lambda opt: opt[1],
                index=(idx[0] if idx else 0),
                key="bccr_location_selector",
            )[0]
            st.session_state["bccr_target_location_id"] = target_location_id
    else:
        if not is_allowed_location:
            st.error("⚠️ BCCR is only available for Asemoku Jetty or Ndoni.")
            st.stop()
        st.session_state["bccr_target_location_id"] = active_location_id

    with get_session() as s:
        from location_manager import LocationManager
        target_loc = LocationManager.get_location_by_id(s, target_location_id)
        if not target_loc:
            st.error("Target location not found.")
            st.stop()
        target_location_name = target_loc.name or "Unknown"
        target_location_code = target_loc.code or ""

    st.info(f"📍 Viewing Location: {target_location_name} ({target_location_code})")

    st.session_state.setdefault("bccr_selected_yade", {})
    st.session_state.setdefault("bccr_selected_otr", {})
    st.session_state.setdefault("bccr_pending", {})
    st.session_state.setdefault("bccr_records", {})

    def _get_selection(store_key):
        store = st.session_state.setdefault(store_key, {})
        if target_location_id not in store:
            store[target_location_id] = set()
        return store[target_location_id]

    def _set_selection(store_key, values):
        st.session_state.setdefault(store_key, {})[target_location_id] = values

    def _get_pending():
        return st.session_state["bccr_pending"].get(target_location_id)

    def _set_pending(data):
        st.session_state["bccr_pending"][target_location_id] = data

    def _get_records():
        store = st.session_state["bccr_records"].setdefault(target_location_id, [])
        return store

    def _set_records(records):
        st.session_state["bccr_records"][target_location_id] = records

    def _load_bccr_records(location_id, date_from=None, date_to=None, convoy=None):
        rows = []
        try:
            with get_session() as s:
                from models import FlexibleRecord
                q = s.query(FlexibleRecord).filter(
                    FlexibleRecord.location_id == location_id,
                    FlexibleRecord.page == "bccr",
                    FlexibleRecord.section == "report",
                )
                if date_from:
                    q = q.filter(FlexibleRecord.tx_date >= date_from)
                if date_to:
                    q = q.filter(FlexibleRecord.tx_date <= date_to)
                q = q.order_by(FlexibleRecord.tx_date.desc(), FlexibleRecord.id.desc()).limit(500)
                recs = q.all()
                for r in recs:
                    try:
                        payload = json.loads(getattr(r, "data_json", "") or "{}")
                    except Exception:
                        payload = {}
                    if convoy and convoy.strip():
                        if convoy.strip().lower() not in (payload.get("convoy") or "").lower():
                            continue
                    rows.append({"_id": getattr(r, "id", None), **payload})
        except Exception:
            rows = []
        return rows

    def _generate_bccr_pdf(df, location_name, location_code, filters_text):
        from io import BytesIO
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import landscape, A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        from reportlab.lib.units import cm
        import numbers

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=0.5*cm, rightMargin=0.5*cm, topMargin=0.5*cm, bottomMargin=0.5*cm)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("BCCRTitle", parent=styles["Title"], alignment=TA_CENTER, fontSize=18)
        subtitle_style = ParagraphStyle("BCCRSubtitle", parent=styles["Heading3"], alignment=TA_CENTER, fontSize=12)
        filter_style = ParagraphStyle("BCCRFilters", parent=styles["BodyText"], alignment=TA_CENTER, fontSize=10)
        table_text_style = ParagraphStyle("BCCRTable", parent=styles["BodyText"], alignment=TA_LEFT, fontSize=9)
        elements = [Paragraph("BCCR Report", title_style), Paragraph(f"{location_name} ({location_code})", subtitle_style), Paragraph(filters_text, filter_style), Spacer(1, 8)]
        if df.empty:
            elements.append(Paragraph("No records available for the selected filters.", table_text_style))
        else:
            # Build header and rows using Paragraph for wrapping
            header_style = ParagraphStyle("BCCRHeader", parent=styles["BodyText"], alignment=TA_CENTER, fontSize=10)
            header_style.textColor = colors.white
            header_style.fontName = "Helvetica-Bold"
            body_style = ParagraphStyle("BCCRBody", parent=styles["BodyText"], alignment=TA_LEFT, fontSize=9)

            columns = list(df.columns)
            header_row = [Paragraph(str(c), header_style) for c in columns]
            table_data = [header_row]

            for _, row in df.iterrows():
                row_values = []
                for col in columns:
                    value = row[col]
                    if value is None:
                        txt = ""
                    elif isinstance(value, numbers.Integral):
                        txt = str(int(value))
                    elif isinstance(value, numbers.Number):
                        txt = f"{float(value):,.2f}"
                    else:
                        txt = str(value)
                    row_values.append(Paragraph(txt, body_style))
                table_data.append(row_values)

            # Compute column widths to fit exactly within the page content width
            available_width = doc.width
            numeric_cols = {
                "ROB Qty", "ROB Water", "TOB Qty", "TOB Water",
                "Net YADE Receipt", "Net Water", "BCCR Quantity",
                "BCCR Water", "S.No", "Date", "Difference Yade vs BCCR"
            }
            def _weight(col_name: str) -> float:
                if col_name == "Remarks":
                    return 3.0
                if col_name in {"Convoy No"}:
                    return 1.5
                if col_name in numeric_cols:
                    return 1.0
                return 1.2
            weights = [_weight(c) for c in columns]
            total_w = sum(weights) if sum(weights) > 0 else 1.0
            col_widths = [available_width * (w / total_w) for w in weights]

            table = Table(table_data, repeatRows=1, colWidths=col_widths, hAlign="LEFT")
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003366")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("FONTSIZE", (0, 1), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 1), (-1, -1), "LEFT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            elements.append(table)
        doc.build(elements)
        return buffer.getvalue()

    def _load_yade_transactions(location_id):
        with get_session() as s:
            from models import TOAYadeSummary, TOAYadeStage, YadeVoyage
            summaries = s.query(TOAYadeSummary, YadeVoyage).join(YadeVoyage, TOAYadeSummary.voyage_id == YadeVoyage.id).filter(YadeVoyage.location_id == location_id).order_by(TOAYadeSummary.date.desc() if hasattr(TOAYadeSummary, "date") else YadeVoyage.date.desc(), YadeVoyage.time.desc()).limit(200).all()
            if not summaries:
                return []
            voyage_ids = [summary.voyage_id for summary, _ in summaries]
            stages = s.query(TOAYadeStage).filter(TOAYadeStage.voyage_id.in_(voyage_ids)).all()
            stage_map = {}
            for stage in stages:
                key_raw = (getattr(stage, "stage", "") or "").strip().lower()
                key = (
                    "before" if ("before" in key_raw) else (
                        "after" if ("after" in key_raw) else key_raw
                    )
                )
                stage_map.setdefault(stage.voyage_id, {})[key] = stage
            rows = []
            for summary, voyage in summaries:
                per_stage = stage_map.get(summary.voyage_id, {})
                before = per_stage.get("before")
                after = per_stage.get("after")
                rob_qty = float((getattr(summary, "before_nsv_bbl", None) if hasattr(summary, "before_nsv_bbl") else None) or getattr(before, "nsv_bbl", 0.0) or 0.0)
                rob_bsw = float((getattr(summary, "before_bsw_bbl", None) if hasattr(summary, "before_bsw_bbl") else None) or getattr(before, "bsw_bbl", 0.0) or 0.0)
                rob_fw = float(getattr(before, "fw_bbl", 0.0) or 0.0)
                rob_water = rob_bsw if rob_bsw else rob_fw
                tob_qty = float((getattr(summary, "after_nsv_bbl", None) if hasattr(summary, "after_nsv_bbl") else None) or getattr(after, "nsv_bbl", 0.0) or 0.0)
                tob_bsw = float((getattr(summary, "after_bsw_bbl", None) if hasattr(summary, "after_bsw_bbl") else None) or getattr(after, "bsw_bbl", 0.0) or 0.0)
                tob_fw = float(getattr(after, "fw_bbl", 0.0) or 0.0)
                tob_water = tob_bsw if tob_bsw else tob_fw
                net_loaded = float((getattr(summary, "net_nsv_bbl", None) if hasattr(summary, "net_nsv_bbl") else None) or (tob_qty - rob_qty))
                net_bsw = float((getattr(summary, "net_bsw_bbl", None) if hasattr(summary, "net_bsw_bbl") else None) or (tob_bsw - rob_bsw))
                net_fw = float(tob_fw - rob_fw)
                net_water = net_bsw if net_bsw else net_fw
                rows.append({
                    "id": summary.voyage_id,
                    "Date": voyage.date,
                    "Convoy No": voyage.convoy_no or "",
                    "Yade No": voyage.yade_name or "",
                    "ROB Qty": round(rob_qty, 2),
                    "ROB Water": round(rob_water, 2),
                    "TOB Qty": round(tob_qty, 2),
                    "TOB Water": round(tob_water, 2),
                    "Net Loaded": round(net_loaded, 2),
                    "Net Water": round(net_water, 2),
                })
            return rows

    def _load_dispatch_rows(location_id):
        with get_session() as s:
            from models import OTRRecord, Tank
            records = s.query(OTRRecord).filter(OTRRecord.location_id == location_id).order_by(OTRRecord.date.asc(), OTRRecord.time.asc()).all()
            if not records:
                return []
            tank_ids = []
            for rec in records:
                try:
                    if rec.tank_id is not None:
                        tid = int(str(rec.tank_id))
                        tank_ids.append(tid)
                except Exception:
                    pass
            name_by_id = {}
            if tank_ids:
                try:
                    tanks = s.query(Tank).filter(Tank.location_id == location_id, Tank.id.in_(sorted(set(tank_ids)))).all()
                    name_by_id = {int(t.id): (t.name or "") for t in tanks}
                except Exception:
                    name_by_id = {}
            data = []
            for rec in records:
                tank_label = None
                try:
                    tid = int(str(rec.tank_id)) if rec.tank_id is not None else None
                    if tid is not None:
                        tank_label = name_by_id.get(tid)
                except Exception:
                    tank_label = None
                if not tank_label:
                    tank_label = rec.tank_id or ""
                data.append({
                    "id": rec.id,
                    "Ticket ID": rec.ticket_id,
                    "Tank": tank_label,
                    "Date": rec.date,
                    "Time": rec.time,
                    "Operation": rec.operation or "",
                    "NSV (bbl)": float(rec.nsv_bbl or 0.0),
                    "Free Water (bbl)": float(rec.free_water_bbl or 0.0),
                })
            if not data:
                return []
            df = pd.DataFrame(data)
            df["Tank"] = df["Tank"].fillna("")
            df["DT"] = pd.to_datetime(df["Date"]) + pd.to_timedelta(df["Time"].astype(str).replace("None", "00:00:00"))
            df.sort_values(["Tank", "DT"], inplace=True)
            df["Prev NSV"] = df.groupby("Tank")["NSV (bbl)"].shift(1)
            df["Prev FW"] = df.groupby("Tank")["Free Water (bbl)"].shift(1)
            df["Net Rece/Disp (bbls)"] = (df["NSV (bbl)"] - df["Prev NSV"]).abs()
            df["Net Water Rece/Disp (bbls)"] = df["Free Water (bbl)"] - df["Prev FW"]
            df = df[df["Operation"].str.strip().str.lower() == "dispatch to barge"]
            df = df.sort_values("Date", ascending=False).head(200)
            df["Net Rece/Disp (bbls)"] = df["Net Rece/Disp (bbls)"].round(2)
            df["Net Water Rece/Disp (bbls)"] = df["Net Water Rece/Disp (bbls)"].round(2)
            rows = df[["id", "Date", "Ticket ID", "Tank", "Operation", "Net Rece/Disp (bbls)", "Net Water Rece/Disp (bbls)"]].to_dict(orient="records")
            return rows

    yade_rows = _load_yade_transactions(target_location_id)
    otr_rows = _load_dispatch_rows(target_location_id)
    yade_lookup = {row["id"]: row for row in yade_rows}
    otr_lookup = {row["id"]: row for row in otr_rows}

    tab_map, tab_report = st.tabs(["Mapping", "BCCR Report"])

    def _render_selectable_table(rows, key_prefix, column_order, column_labels):
        if not rows:
            st.info("No records available.")
            return set()
        df = pd.DataFrame(rows).reset_index(drop=True)
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.strftime("%d-%b-%Y")
        df = df[column_order].copy()
        selection_key = f"{key_prefix}_selected"
        selected_ids = set(_get_selection(f"bccr_{selection_key}"))
        df.insert(0, "Select", df[column_order[0]].index.map(lambda idx: rows[idx]["id"] in selected_ids))
        df.insert(1, "Item ID", [rows[idx]["id"] for idx in range(len(rows))])
        editor_key = f"{key_prefix}_editor_{target_location_id}"
        edited = st.data_editor(
            df,
            hide_index=True,
            use_container_width=True,
            key=editor_key,
            column_config={
                "Select": st.column_config.CheckboxColumn("Select"),
                "Item ID": st.column_config.Column("ID", help="Internal reference", disabled=True),
                **{field: st.column_config.Column(column_labels.get(field, field)) for field in column_order}
            },
            disabled=[col for col in df.columns if col not in {"Select"}],
        )
        if isinstance(edited, pd.DataFrame):
            new_selected = set(edited.loc[edited["Select"], "Item ID"].astype(int).tolist())
        else:
            edited_df = pd.DataFrame(edited)
            new_selected = set(edited_df.loc[edited_df["Select"], "Item ID"].astype(int).tolist())
        _set_selection(f"bccr_{selection_key}", new_selected)
        return new_selected

    with tab_map:
        st.markdown("### Mapping")
        st.caption("Select YADE and Dispatch entries to compare and map them into BCCR records.")
        map_col1, map_col2 = st.columns(2)
        with map_col1:
            st.subheader("YADE Transactions (TOA)")
            yc1, yc2, yc3 = st.columns(3)
            with yc1:
                yade_convoy_filter = st.text_input("Convoy No", key=f"bccr_yade_convoy_{target_location_id}")
            with yc2:
                yade_no_filter = st.text_input("Yade No", key=f"bccr_yade_yade_{target_location_id}")
            with yc3:
                yade_date_filter = st.date_input("Date", value=None, key=f"bccr_yade_date_{target_location_id}")
            def _matches_yade(row):
                if yade_convoy_filter and yade_convoy_filter.strip():
                    if yade_convoy_filter.strip().lower() not in (row.get("Convoy No") or "").lower():
                        return False
                if yade_no_filter and yade_no_filter.strip():
                    if yade_no_filter.strip().lower() not in (row.get("Yade No") or "").lower():
                        return False
                if yade_date_filter and row.get("Date"):
                    if row["Date"] != yade_date_filter:
                        return False
                return True
            filtered_yade_rows = [r for r in yade_rows if _matches_yade(r)]
            yade_selected = _render_selectable_table(
                filtered_yade_rows,
                "yade",
                ["Date", "Convoy No", "Yade No", "ROB Qty", "ROB Water", "TOB Qty", "TOB Water", "Net Loaded", "Net Water"],
                {
                    "Date": "Date",
                    "Convoy No": "Convoy No",
                    "Yade No": "Yade No",
                    "ROB Qty": "ROB Qty (bbls)",
                    "ROB Water": "ROB Water (bbls)",
                    "TOB Qty": "TOB Qty (bbls)",
                    "TOB Water": "TOB Water (bbls)",
                    "Net Loaded": "Net Loaded (bbls)",
                    "Net Water": "Net Water (bbls)",
                }
            )
        with map_col2:
            st.subheader("Dispatch to Barge (OTR)")
            oc1, oc2 = st.columns(2)
            with oc1:
                otr_date_filter = st.date_input("Date", value=None, key=f"bccr_otr_date_{target_location_id}")
            with oc2:
                otr_tank_filter = st.text_input("Tank", key=f"bccr_otr_tank_{target_location_id}")
            def _matches_otr(row):
                if otr_date_filter and row.get("Date"):
                    if row["Date"] != otr_date_filter:
                        return False
                if otr_tank_filter and otr_tank_filter.strip():
                    if otr_tank_filter.strip().lower() not in (row.get("Tank") or "").lower():
                        return False
                return True
            filtered_otr_rows = [r for r in otr_rows if _matches_otr(r)]
            otr_selected = _render_selectable_table(
                filtered_otr_rows,
                "otr",
                ["Date", "Ticket ID", "Tank", "Operation", "Net Rece/Disp (bbls)", "Net Water Rece/Disp (bbls)"],
                {
                    "Date": "Date",
                    "Ticket ID": "Ticket",
                    "Tank": "Tank",
                    "Operation": "Operation",
                    "Net Rece/Disp (bbls)": "Net Rece/Disp (bbls)",
                    "Net Water Rece/Disp (bbls)": "Net Water Rece/Disp (bbls)",
                }
            )
        can_map = bool(yade_selected and otr_selected)
        if st.button("MAP Selected Rows", disabled=not can_map, type="primary"):
            if not can_map:
                st.warning("Please select at least one YADE record and one Dispatch record.")
            else:
                selected_yade_rows = [yade_lookup[row_id] for row_id in yade_selected if row_id in yade_lookup]
                selected_otr_rows = [otr_lookup[row_id] for row_id in otr_lookup]
                if not selected_yade_rows or not selected_otr_rows:
                    st.warning("Unable to locate selected rows. Please try again.")
                else:
                    pending_payload = {
                        "yade_ids": list(yade_selected),
                        "otr_ids": list(otr_selected),
                        "rob_qty": round(sum(r["ROB Qty"] for r in selected_yade_rows), 2),
                        "rob_water": round(sum(r["ROB Water"] for r in selected_yade_rows), 2),
                        "tob_qty": round(sum(r["TOB Qty"] for r in selected_yade_rows), 2),
                        "tob_water": round(sum(r["TOB Water"] for r in selected_yade_rows), 2),
                        "net_yade": round(sum(r["Net Loaded"] for r in selected_yade_rows), 2),
                        "net_water": round(sum(r["Net Water"] for r in selected_yade_rows), 2),
                        "bccr_qty": round(sum(r.get("Net Rece/Disp (bbls)", 0.0) for r in selected_otr_rows if isinstance(r.get("Net Rece/Disp (bbls)"), (int, float))), 2),
                        "bccr_water": round(sum(r.get("Net Water Rece/Disp (bbls)", 0.0) for r in selected_otr_rows if isinstance(r.get("Net Water Rece/Disp (bbls)"), (int, float))), 2),
                    }
                    _set_pending(pending_payload)
                    _set_selection("bccr_yade_selected", set())
                    _set_selection("bccr_otr_selected", set())
                    st.session_state.pop(f"yade_editor_{target_location_id}", None)
                    st.session_state.pop(f"otr_editor_{target_location_id}", None)
                    st.success("Selections mapped. Review and finalize in the BCCR Report tab.")

    with tab_report:
        st.markdown("### BCCR Report")
        pending_data = _get_pending()
        records_all = _load_bccr_records(target_location_id)
        rep_col1, rep_col2, rep_col3 = st.columns(3)
        with rep_col1:
            report_date_from = st.date_input("From", value=None, key=f"bccr_report_from_{target_location_id}")
        with rep_col2:
            report_date_to = st.date_input("To", value=None, key=f"bccr_report_to_{target_location_id}")
        with rep_col3:
            report_convoy_filter = st.text_input("Convoy No", key=f"bccr_report_convoy_{target_location_id}")
        export_container = st.container()
        if pending_data:
            st.info("Pending mapping detected. Review the values below and save to BCCR report.")
            default_sno = max([rec.get("sno", 0) for rec in records_all], default=0) + 1
            with st.form(f"bccr_add_form_{target_location_id}"):
                col1, col2 = st.columns(2)
                with col1:
                    new_sno = st.number_input("S.No", min_value=1, value=default_sno, step=1)
                    new_date = st.date_input("Date", value=date.today())
                    new_convoy = st.text_input("Convoy No", value="")
                    new_rob_qty = st.number_input("ROB Qty (bbls)", value=float(pending_data["rob_qty"]), format="%.2f")
                    new_rob_water = st.number_input("ROB Water (bbls)", value=float(pending_data["rob_water"]), format="%.2f")
                    new_tob_qty = st.number_input("TOB Qty (bbls)", value=float(pending_data["tob_qty"]), format="%.2f")
                with col2:
                    new_tob_water = st.number_input("TOB Water (bbls)", value=float(pending_data["tob_water"]), format="%.2f")
                    new_net_yade = st.number_input("Net YADE Receipt (bbls)", value=float(pending_data["net_yade"]), format="%.2f")
                    new_net_water = st.number_input("Net Water (bbls)", value=float(pending_data["net_water"]), format="%.2f")
                    new_bccr_qty = st.number_input("BCCR Quantity (bbls)", value=float(pending_data["bccr_qty"]), format="%.2f")
                    new_bccr_water = st.number_input("BCCR Water (bbls)", value=float(pending_data.get("bccr_water", 0.0)), format="%.2f")
                    difference_value = new_bccr_qty - new_net_yade
                    st.metric("Difference (BCCR - YADE)", f"{difference_value:,.2f} bbls")
                new_remarks = st.text_area("Remarks", value="")
                if st.form_submit_button("Save BCCR Mapping", type="primary"):
                    record = {
                        "sno": int(new_sno),
                        "date": new_date.strftime("%Y-%m-%d"),
                        "convoy": new_convoy,
                        "rob_qty": round(new_rob_qty, 2),
                        "rob_water": round(new_rob_water, 2),
                        "tob_qty": round(new_tob_qty, 2),
                        "tob_water": round(new_tob_water, 2),
                        "net_yade": round(new_net_yade, 2),
                        "net_water": round(new_net_water, 2),
                        "bccr_qty": round(new_bccr_qty, 2),
                        "bccr_water": round(new_bccr_water, 2),
                        "difference": round(difference_value, 2),
                        "remarks": new_remarks.strip(),
                    }
                    try:
                        with get_session() as s:
                            from models import FlexibleRecord
                            txd = new_date
                            fr = FlexibleRecord(
                                location_id=target_location_id,
                                page="bccr",
                                section="report",
                                tx_date=txd,
                                data_json=json.dumps(record),
                                created_by=(user or {}).get("username", "system"),
                            )
                            s.add(fr)
                            s.commit()
                            try:
                                from security import SecurityManager
                                SecurityManager.log_audit(
                                    s,
                                    (user or {}).get("username", "system"),
                                    "CREATE",
                                    resource_type="BCCRRecord",
                                    resource_id=str(getattr(fr, "id", "")),
                                    details=f"Saved BCCR mapping for convoy {new_convoy}",
                                    user_id=(user or {}).get("id"),
                                    location_id=target_location_id,
                                )
                            except Exception:
                                pass
                        _set_pending(None)
                        st.success("Mapping saved.")
                    except Exception as ex:
                        st.error(f"Failed to save mapping: {ex}")
        else:
            st.caption("Select records in the Mapping tab and click MAP to create a pending entry.")

        def _record_matches(rec):
            if report_date_filter:
                try:
                    rec_date = datetime.strptime(rec["date"], "%Y-%m-%d").date()
                    if rec_date != report_date_filter:
                        return False
                except Exception:
                    return False
            if report_convoy_filter and report_convoy_filter.strip():
                if report_convoy_filter.strip().lower() not in (rec.get("convoy") or "").lower():
                    return False
            return True

        filtered_records = _load_bccr_records(target_location_id, report_date_from, report_date_to, report_convoy_filter)
        column_map = {
            "sno": "S.No",
            "date": "Date",
            "convoy": "Convoy No",
            "rob_qty": "ROB Qty",
            "rob_water": "ROB Water",
            "tob_qty": "TOB Qty",
            "tob_water": "TOB Water",
            "net_yade": "Net YADE Receipt",
            "net_water": "Net Water",
            "bccr_qty": "BCCR Quantity",
            "bccr_water": "BCCR Water",
            "difference": "Difference Yade vs BCCR",
            "remarks": "Remarks",
        }
        download_df = pd.DataFrame()
        if filtered_records:
            records_df_sorted = pd.DataFrame(filtered_records).sort_values("sno")
            renamed_df = records_df_sorted.rename(columns=column_map)
            download_df = renamed_df.drop(columns=["id"], errors="ignore")
        export_disabled = download_df.empty
        filter_parts = []
        if report_date_from:
            filter_parts.append(f"From: {report_date_from.strftime('%d %b %Y')}")
        if report_date_to:
            filter_parts.append(f"To: {report_date_to.strftime('%d %b %Y')}")
        if report_convoy_filter and report_convoy_filter.strip():
            filter_parts.append(f"Convoy: {report_convoy_filter.strip()}")
        filter_description = " | ".join(filter_parts) if filter_parts else "No filters applied"
        if report_date_from and report_date_to:
            date_token = f"{report_date_from.strftime('%Y%m%d')}-{report_date_to.strftime('%Y%m%d')}"
        elif report_date_from:
            date_token = f"{report_date_from.strftime('%Y%m%d')}-ALL"
        elif report_date_to:
            date_token = f"ALL-{report_date_to.strftime('%Y%m%d')}"
        else:
            date_token = "ALL"
        convoy_raw = (report_convoy_filter or "").strip()
        convoy_token = re.sub(r"[^A-Za-z0-9]+", "_", convoy_raw).strip("_") or "ALL"
        location_token = _canon(target_location_code) or _canon(target_location_name) or "LOCATION"
        base_filename = f"BCCR_{location_token}_{date_token}_{convoy_token}"
        from io import BytesIO
        csv_bytes = download_df.to_csv(index=False).encode("utf-8") if not export_disabled else b""
        xlsx_bytes = b""
        if not export_disabled:
            xlsx_buffer = BytesIO()
            with pd.ExcelWriter(xlsx_buffer, engine="xlsxwriter") as writer:
                download_df.to_excel(writer, sheet_name="BCCR", index=False)
            xlsx_bytes = xlsx_buffer.getvalue()
        pdf_bytes = b""
        pdf_error_message = None
        if not export_disabled:
            try:
                pdf_bytes = _generate_bccr_pdf(download_df, target_location_name, target_location_code, filter_description)
            except Exception as exc:
                pdf_error_message = str(exc)
                pdf_bytes = b""
        with export_container:
            st.markdown("#### Export & Downloads")
            col_csv, col_xlsx, col_pdf, col_view = st.columns(4)
            with col_csv:
                st.download_button("📥 CSV", data=csv_bytes, file_name=f"{base_filename}.csv", mime="text/csv", disabled=export_disabled, key=f"bccr_csv_{target_location_id}")
            with col_xlsx:
                st.download_button("📥 XLSX", data=xlsx_bytes, file_name=f"{base_filename}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", disabled=export_disabled, key=f"bccr_xlsx_{target_location_id}")
            with col_pdf:
                st.download_button("📥 PDF", data=pdf_bytes, file_name=f"{base_filename}.pdf", mime="application/pdf", disabled=export_disabled or pdf_error_message is not None, key=f"bccr_pdf_{target_location_id}")
            with col_view:
                if st.button("👁️ View PDF", key=f"bccr_pdf_view_{target_location_id}", disabled=export_disabled or pdf_error_message is not None):
                    import base64
                    import streamlit.components.v1 as components
                    b64 = base64.b64encode(pdf_bytes).decode("utf-8")
                    components.html(
                        f"""
                        <script>
                            const pdfData = "{b64}";
                            const byteCharacters = atob(pdfData);
                            const byteNumbers = new Array(byteCharacters.length);
                            for (let i = 0; i < byteCharacters.length; i++) {{
                                byteNumbers[i] = byteCharacters.charCodeAt(i);
                            }}
                            const byteArray = new Uint8Array(byteNumbers);
                            const file = new Blob([byteArray], {{ type: "application/pdf" }});
                            const fileURL = URL.createObjectURL(file);
                            window.open(fileURL, "_blank");
                        </script>
                        """,
                        height=0,
                    )
                    st.success("BCCR PDF opened in a new tab.")
            if pdf_error_message:
                st.warning(f"PDF export unavailable: {pdf_error_message}")
        if filtered_records:
            st.subheader("Mapped Records")
            st.dataframe(download_df, use_container_width=True, hide_index=True)
            for rec in filtered_records:
                rid = rec.get("_id")
                if st.button(f"Delete S.No {rec['sno']}", key=f"bccr_delete_{rid}"):
                    try:
                        with get_session() as s:
                            from models import FlexibleRecord
                            obj = s.query(FlexibleRecord).get(rid)
                            if obj:
                                try:
                                    from recycle_bin import RecycleBinManager
                                    RecycleBinManager.archive_record(
                                        s,
                                        obj,
                                        "FlexibleRecord:BCCR",
                                        username=(user or {}).get("username", "system"),
                                        user_id=(user or {}).get("id"),
                                        location_id=target_location_id,
                                        reason=f"Deleted BCCR mapping S.No {rec['sno']}",
                                        label=str(rid),
                                    )
                                    s.commit()
                                except Exception:
                                    s.delete(obj)
                                    s.commit()
                        st.success(f"Deleted mapping S.No {rec['sno']}")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"Failed to delete mapping: {ex}")
        else:
            st.info("No BCCR mappings found for the current filters.")
