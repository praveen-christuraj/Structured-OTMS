from __future__ import annotations

import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional

from db import get_session
from ui import header
from auth import AuthManager
from permission_manager import PermissionManager
from location_manager import LocationManager
from models import YadeVoyage, TOAYadeStage, Location, YadeDip, YadeSampleParam
from sqlalchemy import func
from toa_yade_calculator import compute_and_save_summary
from security import SecurityManager
from action_logger_utils import log_export_action
from location_config import get_yade_tracking_config




def render_yade_tracking_page(active_location_id: int | None, user: Dict[str, Any] | None) -> None:
    header("Yade Tracking")

    if not active_location_id:
        st.error("No active location selected. Select a location on Home.")
        st.stop()

    user = user or {}
    if user:
        if not AuthManager.can_access_location(user, active_location_id):
            st.error("You do not have access to this location.")
            st.stop()

    with get_session() as s:
        loc = LocationManager.get_location_by_id(s, active_location_id)
        if not loc:
            st.error("Location not found.")
            st.stop()
        st.info(f"Active Location: {loc.name} ({loc.code})")

        role = user.get("role", "operator")
        can_view = PermissionManager.can_access_operational_pages(user) and PermissionManager.can_access_feature(
            s, active_location_id, "yade_transactions", role
        )

        if not can_view:
            allowed = PermissionManager.get_allowed_locations_for_feature(s, "yade_transactions")
            st.error("Access Denied")
            st.warning(f"Yade Tracking is not available at {loc.name}")
            if allowed:
                st.info(f"Available at: {', '.join(allowed)}")
            st.caption(f"Current Location: {loc.name} ({loc.code})")
            st.stop()

        yt_cfg = get_yade_tracking_config(s, loc.id)
        st.session_state.setdefault("yt_cmp_records", [])
        st.session_state.setdefault("yt_delete_target", None)
        st.session_state.setdefault("yt_pending_map", None)
        if yt_cfg.get("is_sender") or yt_cfg.get("is_receiver"):
            st.caption(f"Active Location: {loc.name} ({loc.code})")
            dcols = st.columns(2)
            default_from = date.today() - timedelta(days=30)
            start_date = dcols[0].date_input("From", value=default_from, max_value=date.today(), key="yt_from")
            end_date = dcols[1].date_input("To", value=date.today(), max_value=date.today(), key="yt_to")

            def _voyages_for(location_ids: List[int]) -> List[YadeVoyage]:
                if not location_ids:
                    return []
                q = s.query(YadeVoyage).filter(YadeVoyage.location_id.in_(location_ids))
                if start_date:
                    q = q.filter(YadeVoyage.date >= start_date)
                if end_date:
                    q = q.filter(YadeVoyage.date <= end_date)
                return q.order_by(YadeVoyage.date.desc(), YadeVoyage.time.desc()).limit(400).all()

            def _stages_map(voyage_ids: List[int]) -> Dict[int, Dict[str, TOAYadeStage]]:
                if not voyage_ids:
                    return {}
                rows = s.query(TOAYadeStage).filter(TOAYadeStage.voyage_id.in_(voyage_ids)).all()
                out: Dict[int, Dict[str, TOAYadeStage]] = {}
                for r in rows:
                    out.setdefault(r.voyage_id, {})[(r.stage or "").strip().lower()] = r
                return out

            sender_voyages = _voyages_for([loc.id]) if yt_cfg.get("is_sender") else []
            receiver_source_ids = yt_cfg.get("receiver_sources", []) if yt_cfg.get("is_receiver") else []
            receiver_voyages = _voyages_for(receiver_source_ids)
            sender_stage_map = _stages_map([v.id for v in sender_voyages])
            receiver_stage_map = _stages_map([v.id for v in receiver_voyages])
            sender_by_key = { (str(v.convoy_no or ""), str(v.yade_name or "")) : v for v in sender_voyages }

            loc_lookup = {l.id: {"name": l.name, "code": l.code} for l in s.query(Location).all()}

            def _net_nsv(stages: Dict[str, TOAYadeStage]) -> Optional[float]:
                if not stages:
                    return None
                b = stages.get("before")
                a = stages.get("after")
                if not a or not b:
                    return None
                try:
                    return float((getattr(a, "nsv_bbl", 0.0) or 0.0) - (getattr(b, "nsv_bbl", 0.0) or 0.0))
                except Exception:
                    return None

            def _key(v: YadeVoyage) -> tuple:
                return (str(v.convoy_no or ""), str(v.yade_name or ""))

            receiver_keys_here = set(_key(v) for v in s.query(YadeVoyage).filter(YadeVoyage.location_id == loc.id).all())
            receiver_aliases = yt_cfg.get("receiver_aliases") or [loc.name, loc.code]

            _TANK_ORDER = ["C1", "C2", "P1", "P2", "S1", "S2"]
            def _get_barge_tanks_and_limits(yade_name: str, design: str) -> tuple[list[str], dict]:
                try:
                    from models import YadeCalibration
                    rows = (
                        s.query(YadeCalibration.tank_id, func.max(YadeCalibration.dip_mm).label("max_dip_mm"))
                        .filter(YadeCalibration.yade_name == yade_name)
                        .group_by(YadeCalibration.tank_id)
                        .all()
                    )
                except Exception:
                    rows = []
                if rows:
                    tank_ids = [r.tank_id for r in rows]
                    tank_ids = sorted(tank_ids, key=lambda t: _TANK_ORDER.index(t) if t in _TANK_ORDER else 999)
                    max_by_tank = {r.tank_id: (float(r.max_dip_mm or 0.0) / 10.0) for r in rows}
                    return tank_ids, max_by_tank
                if str(design) == "4":
                    tank_ids = ["P1", "P2", "S1", "S2"]
                else:
                    tank_ids = ["C1", "C2", "P1", "P2", "S1", "S2"]
                return tank_ids, {t: 9999.0 for t in tank_ids}

            tabs = st.tabs(["Mapping", "Comparison"]) if (yt_cfg.get("is_sender") or yt_cfg.get("is_receiver")) else [st.container()]

            with tabs[0]:
                dep_rows = []
                def _norm_label(s: str) -> str:
                    return (s or "").strip().lower().replace(" ", "").replace("-", "").replace("_", "")

                for v in receiver_voyages:
                    if receiver_aliases:
                        tokens = {_norm_label(t) for t in receiver_aliases if t}
                        val = _norm_label(v.destination or "")
                        if tokens and val not in tokens:
                            continue
                    stages = receiver_stage_map.get(v.id, {})
                    b = stages.get("before")
                    a = stages.get("after")
                    bn = float(getattr(b, "nsv_bbl", 0.0) or 0.0) if b else None
                    bw = float(getattr(b, "fw_bbl", 0.0) or 0.0) if b else None
                    an = float(getattr(a, "nsv_bbl", 0.0) or 0.0) if a else None
                    aw = float(getattr(a, "fw_bbl", 0.0) or 0.0) if a else None
                    net_qty = None
                    net_wat = None
                    if bn is not None and an is not None:
                        net_qty = float(an) - float(bn)
                    if bw is not None and aw is not None:
                        net_wat = float(aw) - float(bw)
                    dep_rows.append(
                        {
                            "Date": v.date,
                            "Yade No": v.yade_name,
                            "Convoy No": v.convoy_no,
                            "ROB Qty": bn,
                            "ROB Water": bw,
                            "TOB Qty": an,
                            "TOB Water": aw,
                            "Net Qty": net_qty,
                            "Net Water": net_wat,
                            "Loaded Location": loc_lookup.get(v.location_id, {}).get("name", v.location_id),
                            "Item ID": int(v.id),
                            "Select": False,
                        }
                    )

                local_voyages = s.query(YadeVoyage).filter(YadeVoyage.location_id == loc.id).order_by(YadeVoyage.date.desc(), YadeVoyage.time.desc()).limit(400).all()
                local_stage_map = _stages_map([v.id for v in local_voyages])
                arr_rows = []
                for v in local_voyages:
                    stages = local_stage_map.get(v.id, {})
                    b = stages.get("before")
                    a = stages.get("after")
                    bn = float(getattr(b, "nsv_bbl", 0.0) or 0.0) if b else None
                    bw = float(getattr(b, "fw_bbl", 0.0) or 0.0) if b else None
                    an = float(getattr(a, "nsv_bbl", 0.0) or 0.0) if a else None
                    aw = float(getattr(a, "fw_bbl", 0.0) or 0.0) if a else None
                    net_qty = None
                    net_wat = None
                    if bn is not None and an is not None:
                        net_qty = float(an) - float(bn)
                    if bw is not None and aw is not None:
                        net_wat = float(aw) - float(bw)
                    arr_rows.append(
                        {
                            "Date": v.date,
                            "Yade No": v.yade_name,
                            "Convoy No": v.convoy_no,
                            "ROB Qty": bn,
                            "ROB Water": bw,
                            "TOB Qty": an,
                            "TOB Water": aw,
                            "Net Qty": net_qty,
                            "Net Water": net_wat,
                            "Unloaded Location": loc.name,
                            "Item ID": int(v.id),
                            "Select": False,
                        }
                    )

                cA, cB = st.columns(2)
                with cA:
                    st.markdown("#### Jetty Departure")
                    yades_dep = sorted({r.get("Yade No") for r in dep_rows if r.get("Yade No")})
                    convoys_dep = sorted({r.get("Convoy No") for r in dep_rows if r.get("Convoy No")})
                    fc = st.columns(4)
                    with fc[0]:
                        dep_from = st.date_input("From", value=start_date, max_value=date.today(), key="yt_dep_from")
                    with fc[1]:
                        dep_to = st.date_input("To", value=end_date, max_value=date.today(), key="yt_dep_to")
                    with fc[2]:
                        dep_yade = st.selectbox("Yade No", ["All"] + yades_dep, key="yt_dep_yade")
                    with fc[3]:
                        dep_convoy = st.selectbox("Convoy No", ["All"] + convoys_dep, key="yt_dep_convoy")
                    filtered_dep_rows = []
                    for r in dep_rows:
                        d0 = r.get("Date")
                        if dep_from and dep_to and not (dep_from <= d0 <= dep_to):
                            continue
                        if dep_yade != "All" and r.get("Yade No") != dep_yade:
                            continue
                        if dep_convoy != "All" and r.get("Convoy No") != dep_convoy:
                            continue
                        filtered_dep_rows.append(r)
                    df_dep = pd.DataFrame(filtered_dep_rows).reset_index(drop=True)
                    dep_order = [
                        "Date","Yade No","Convoy No","ROB Qty","ROB Water","TOB Qty","TOB Water","Net Qty","Net Water","Loaded Location"
                    ]
                    expected_dep = ["Select","Item ID"] + dep_order
                    if df_dep.empty:
                        df_dep = pd.DataFrame(columns=expected_dep)
                    else:
                        missing = [c for c in expected_dep if c not in df_dep.columns]
                        for c in missing:
                            df_dep[c] = None
                        df_dep = df_dep[expected_dep]
                    dep_disabled = [col for col in df_dep.columns if col not in {"Select"}]
                    dep_df = st.data_editor(
                        df_dep,
                        hide_index=True,
                        use_container_width=True,
                        key="yt_map_dep",
                        column_config={
                            "Select": st.column_config.CheckboxColumn("Select"),
                            "Item ID": st.column_config.Column("ID", disabled=True),
                        },
                        disabled=dep_disabled,
                    )
                with cB:
                    st.markdown("#### Agge Arrival")
                    yades_arr = sorted({r.get("Yade No") for r in arr_rows if r.get("Yade No")})
                    convoys_arr = sorted({r.get("Convoy No") for r in arr_rows if r.get("Convoy No")})
                    fc2 = st.columns(4)
                    with fc2[0]:
                        arr_from = st.date_input("From", value=start_date, max_value=date.today(), key="yt_arr_from")
                    with fc2[1]:
                        arr_to = st.date_input("To", value=end_date, max_value=date.today(), key="yt_arr_to")
                    with fc2[2]:
                        arr_yade = st.selectbox("Yade No", ["All"] + yades_arr, key="yt_arr_yade")
                    with fc2[3]:
                        arr_convoy = st.selectbox("Convoy No", ["All"] + convoys_arr, key="yt_arr_convoy")
                    filtered_arr_rows = []
                    for r in arr_rows:
                        d0 = r.get("Date")
                        if arr_from and arr_to and not (arr_from <= d0 <= arr_to):
                            continue
                        if arr_yade != "All" and r.get("Yade No") != arr_yade:
                            continue
                        if arr_convoy != "All" and r.get("Convoy No") != arr_convoy:
                            continue
                        filtered_arr_rows.append(r)
                    df_arr = pd.DataFrame(filtered_arr_rows).reset_index(drop=True)
                    arr_order = [
                        "Date","Yade No","Convoy No","ROB Qty","ROB Water","TOB Qty","TOB Water","Net Qty","Net Water","Unloaded Location"
                    ]
                    expected_arr = ["Select","Item ID"] + arr_order
                    if df_arr.empty:
                        df_arr = pd.DataFrame(columns=expected_arr)
                    else:
                        missing = [c for c in expected_arr if c not in df_arr.columns]
                        for c in missing:
                            df_arr[c] = None
                        df_arr = df_arr[expected_arr]
                    arr_disabled = [col for col in df_arr.columns if col not in {"Select"}]
                    arr_df = st.data_editor(
                        df_arr,
                        hide_index=True,
                        use_container_width=True,
                        key="yt_map_arr",
                        column_config={
                            "Select": st.column_config.CheckboxColumn("Select"),
                            "Item ID": st.column_config.Column("ID", disabled=True),
                        },
                        disabled=arr_disabled,
                    )

                mcols = st.columns(3)
                if mcols[2].button("Map Selected", type="primary", key="yt_map_do"):
                    try:
                        if isinstance(dep_df, pd.DataFrame):
                            dep_selected = dep_df.loc[dep_df["Select"], :]
                        else:
                            dep_selected = pd.DataFrame(dep_df)
                            dep_selected = dep_selected.loc[dep_selected["Select"], :]
                        if isinstance(arr_df, pd.DataFrame):
                            arr_selected = arr_df.loc[arr_df["Select"], :]
                        else:
                            arr_selected = pd.DataFrame(arr_df)
                            arr_selected = arr_selected.loc[arr_selected["Select"], :]
                        if dep_selected.shape[0] != 1 or arr_selected.shape[0] != 1:
                            st.error("Select exactly one row in each table to map.")
                        else:
                            dep_row = dep_selected.iloc[0].to_dict()
                            arr_row = arr_selected.iloc[0].to_dict()
                            if str(dep_row.get("Yade No")) != str(arr_row.get("Yade No")) or str(dep_row.get("Convoy No")) != str(arr_row.get("Convoy No")):
                                st.error("Yade No and Convoy No must match to map.")
                            else:
                                item = {
                                    "Date": arr_row.get("Date") or dep_row.get("Date"),
                                    "Yade No": dep_row.get("Yade No"),
                                    "Convoy No": dep_row.get("Convoy No"),
                                    "TOB Qty": float(dep_row.get("TOB Qty") or 0.0),
                                    "TOB Water": float(dep_row.get("TOB Water") or 0.0),
                                    "ROB Qty": float(arr_row.get("ROB Qty") or 0.0),
                                    "ROB Water": float(arr_row.get("ROB Water") or 0.0),
                                }
                                item["Qty Variance"] = round(item["ROB Qty"] - item["TOB Qty"], 2)
                                item["Water Variance"] = round(item["ROB Water"] - item["TOB Water"], 2)
                                store = st.session_state.setdefault("yt_yade_map", [])
                                store.append(item)
                                st.session_state["yt_pending_map"] = item
                                st.success("Mapped. See Comparison tab.")
                    except Exception as ex:
                        st.error(f"Mapping failed: {ex}")

            with tabs[1]:
                pending_item = st.session_state.get("yt_pending_map")
                if pending_item:
                    st.info("Pending mapping found. Provide date and remarks, then save.")
                    qty_disp = float(pending_item.get("TOB Qty") or 0.0)
                    qty_recv = float(pending_item.get("ROB Qty") or 0.0)
                    qty_var  = float(pending_item.get("Qty Variance") or 0.0)
                    wat_disp = float(pending_item.get("TOB Water") or 0.0)
                    wat_recv = float(pending_item.get("ROB Water") or 0.0)
                    wat_var  = float(pending_item.get("Water Variance") or 0.0)
                    pc = st.columns(4)
                    pc[0].metric("Dispatch Qty (bbls)", f"{qty_disp:,.2f}", delta=None, delta_color="off")
                    pc[1].metric("Receipt Qty (bbls)", f"{qty_recv:,.2f}", delta=f"{qty_var:,.2f}", delta_color="normal")
                    pc[2].metric("Dispatch Water (bbls)", f"{wat_disp:,.2f}", delta=None, delta_color="off")
                    pc[3].metric("Receipt Water (bbls)", f"{wat_recv:,.2f}", delta=f"{wat_var:,.2f}", delta_color="normal")
                    fcols = st.columns([0.25, 0.55, 0.20])
                    with fcols[0]:
                        map_date = st.date_input("Date", value=date.today(), max_value=date.today(), key="yt_cmp_date")
                    with fcols[1]:
                        map_remarks = st.text_input("Remarks", placeholder="Add remarks (optional)", key="yt_cmp_remarks")
                    with fcols[2]:
                        if st.button("💾 Save Mapping", use_container_width=True, key="yt_cmp_save"):
                            rec = {
                                "Date": map_date,
                                "Yade No": pending_item.get("Yade No"),
                                "Convoy No": pending_item.get("Convoy No"),
                                "TOB Qty": float(pending_item.get("TOB Qty") or 0.0),
                                "TOB Water": float(pending_item.get("TOB Water") or 0.0),
                                "ROB Qty": float(pending_item.get("ROB Qty") or 0.0),
                                "ROB Water": float(pending_item.get("ROB Water") or 0.0),
                                "Qty Variance": float(pending_item.get("Qty Variance") or 0.0),
                                "Water Variance": float(pending_item.get("Water Variance") or 0.0),
                                "Remarks": (map_remarks or "").strip(),
                            }
                            st.session_state["yt_cmp_records"].append(rec)
                            st.session_state["yt_pending_map"] = None
                            try:
                                SecurityManager.log_audit(
                                    s,
                                    user.get("username", "unknown"),
                                    "CREATE",
                                    resource_type="YadeTrackingMapping",
                                    resource_id=f"{rec.get('Yade No')}|{rec.get('Convoy No')}|{map_date}",
                                    details="Saved mapping row from Yade Tracking comparison",
                                    user_id=user.get("id"),
                                    location_id=loc.id,
                                )
                            except Exception:
                                pass
                            st.success("Mapping row saved.")
                            st.rerun()

                saved = st.session_state.get("yt_cmp_records", [])
                cols = [
                    "Date","Yade No","Convoy No","TOB Qty","TOB Water","ROB Qty","ROB Water","Qty Variance","Water Variance","Remarks"
                ]
                df_cmp = pd.DataFrame(saved, columns=cols)
                st.markdown("##### Saved mappings")
                if df_cmp.empty:
                    st.info("No comparison rows captured yet.")
                else:
                    widths = [0.12, 0.14, 0.14, 0.12, 0.12, 0.12, 0.12, 0.14, 0.14, 0.12]
                    hdr_cols = st.columns(widths)
                    hdr_cols[0].markdown("**Date**")
                    hdr_cols[1].markdown("**Yade No**")
                    hdr_cols[2].markdown("**Convoy No**")
                    hdr_cols[3].markdown("**TOB Qty**")
                    hdr_cols[4].markdown("**TOB Water**")
                    hdr_cols[5].markdown("**ROB Qty**")
                    hdr_cols[6].markdown("**ROB Water**")
                    hdr_cols[7].markdown("**Qty Variance**")
                    hdr_cols[8].markdown("**Water Variance**")
                    hdr_cols[9].markdown("**Actions**")
                    for i, rec in enumerate(df_cmp.to_dict(orient="records")):
                        row_cols = st.columns(widths)
                        dval = rec.get("Date")
                        row_cols[0].markdown(dval.strftime("%Y-%m-%d") if hasattr(dval, "strftime") else str(dval or ""))
                        row_cols[1].markdown(str(rec.get("Yade No") or ""))
                        row_cols[2].markdown(str(rec.get("Convoy No") or ""))
                        row_cols[3].markdown(f"{float(rec.get('TOB Qty') or 0.0):,.2f}")
                        row_cols[4].markdown(f"{float(rec.get('TOB Water') or 0.0):,.2f}")
                        row_cols[5].markdown(f"{float(rec.get('ROB Qty') or 0.0):,.2f}")
                        row_cols[6].markdown(f"{float(rec.get('ROB Water') or 0.0):,.2f}")
                        row_cols[7].markdown(f"{float(rec.get('Qty Variance') or 0.0):,.2f}")
                        row_cols[8].markdown(f"{float(rec.get('Water Variance') or 0.0):,.2f}")
                        rid = f"{rec.get('Yade No')}|{rec.get('Convoy No')}|{rec.get('Date')}|{i}"
                        if row_cols[9].button("🗑️", key=f"yt_cmp_del_{rid}", help="Delete mapping row"):
                            st.session_state["yt_delete_target"] = {"index": i, "record": rec}
                            st.rerun()
                    csv_bytes = df_cmp.to_csv(index=False).encode("utf-8")
                    from io import BytesIO
                    xbuf = BytesIO()
                    with pd.ExcelWriter(xbuf, engine="xlsxwriter") as writer:
                        df_cmp.to_excel(writer, index=False, sheet_name="Comparison")
                    xbuf.seek(0)
                    def _generate_cmp_pdf(dfpdf: pd.DataFrame) -> bytes:
                        try:
                            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
                            from reportlab.lib.pagesizes import A4, landscape
                            from reportlab.lib import colors
                            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                            from reportlab.lib.units import cm
                            buf = BytesIO()
                            doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=0.6*cm, rightMargin=0.6*cm, topMargin=0.7*cm, bottomMargin=0.7*cm)
                            styles = getSampleStyleSheet()
                            hdr = Paragraph("YADE Mapping Comparison", ParagraphStyle(name="hdr", parent=styles["Heading2"], alignment=1, textColor=colors.white))
                            hdr_tbl = Table([[hdr]], colWidths=[doc.width])
                            hdr_tbl.setStyle(TableStyle([
                                ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#0B3D91")),
                                ("ALIGN", (0,0), (-1,-1), "CENTER"),
                                ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                                ("FONTSIZE", (0,0), (-1,-1), 14),
                                ("BOTTOMPADDING", (0,0), (-1,-1), 10),
                                ("TOPPADDING", (0,0), (-1,-1), 10),
                            ]))
                            elements = [hdr_tbl, Spacer(1, 0.25*cm)]
                            headers = dfpdf.columns.tolist()
                            data_rows = [headers] + dfpdf.astype(str).values.tolist()
                            tbl = Table(data_rows, repeatRows=1)
                            tbl.setStyle(TableStyle([
                                ("GRID", (0,0), (-1,-1), 0.25, colors.HexColor("#D0D4DA")),
                                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E9EDF5")),
                                ("TEXTCOLOR", (0,0), (-1,0), colors.HexColor("#0B3D91")),
                                ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
                                ("ALIGN", (0,0), (-1,-1), "CENTER"),
                                ("FONTSIZE", (0,0), (-1,-1), 9),
                                ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F7F9FC")]),
                            ]))
                            elements.append(tbl)
                            elements.append(Spacer(1, 0.2*cm))
                            try:
                                sums = {
                                    "TOB Qty": pd.to_numeric(dfpdf.get("TOB Qty"), errors="coerce").sum(),
                                    "TOB Water": pd.to_numeric(dfpdf.get("TOB Water"), errors="coerce").sum(),
                                    "ROB Qty": pd.to_numeric(dfpdf.get("ROB Qty"), errors="coerce").sum(),
                                    "ROB Water": pd.to_numeric(dfpdf.get("ROB Water"), errors="coerce").sum(),
                                    "Qty Variance": pd.to_numeric(dfpdf.get("Qty Variance"), errors="coerce").sum(),
                                    "Water Variance": pd.to_numeric(dfpdf.get("Water Variance"), errors="coerce").sum(),
                                }
                            except Exception:
                                sums = {k: 0.0 for k in ["TOB Qty","TOB Water","ROB Qty","ROB Water","Qty Variance","Water Variance"]}
                            summary_cells = [
                                f"TOB Qty: {sums['TOB Qty']:,.2f}",
                                f"TOB Water: {sums['TOB Water']:,.2f}",
                                f"ROB Qty: {sums['ROB Qty']:,.2f}",
                                f"ROB Water: {sums['ROB Water']:,.2f}",
                                f"Qty Var: {sums['Qty Variance']:,.2f}",
                                f"Water Var: {sums['Water Variance']:,.2f}",
                            ]
                            col_w = doc.width/6.0
                            sum_tbl = Table([summary_cells], colWidths=[col_w]*6)
                            sum_tbl.setStyle(TableStyle([
                                ("GRID", (0,0), (-1,-1), 0.25, colors.HexColor("#D0D4DA")),
                                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E9EDF5")),
                                ("TEXTCOLOR", (0,0), (-1,0), colors.HexColor("#0B3D91")),
                                ("FONTNAME", (0,0), (-1,-1), "Helvetica"),
                                ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
                                ("ALIGN", (0,0), (-1,-1), "CENTER"),
                                ("FONTSIZE", (0,0), (-1,-1), 9),
                                ("TOPPADDING", (0,0), (-1,-1), 6),
                                ("BOTTOMPADDING", (0,0), (-1,-1), 6),
                            ]))
                            elements.append(sum_tbl)
                            doc.build(elements)
                            out = buf.getvalue()
                            buf.close()
                            return out
                        except Exception:
                            return b""
                    pdf_bytes = _generate_cmp_pdf(df_cmp)
                    dcols = st.columns(4)
                    dcols[0].download_button(
                        "📥 CSV",
                        data=csv_bytes,
                        file_name="yade_mapping_comparison.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key="yt_cmp_csv",
                        on_click=lambda: log_export_action("YadeTrackingComparison", "CSV", len(df_cmp), user, loc.id)
                    )
                    dcols[1].download_button(
                        "📥 XLSX",
                        data=xbuf.getvalue(),
                        file_name="yade_mapping_comparison.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        key="yt_cmp_xlsx",
                        on_click=lambda: log_export_action("YadeTrackingComparison", "XLSX", len(df_cmp), user, loc.id)
                    )
                    dcols[2].download_button(
                        "📥 PDF",
                        data=pdf_bytes or b"",
                        file_name="yade_mapping_comparison.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        key="yt_cmp_pdf",
                        on_click=lambda: log_export_action("YadeTrackingComparison", "PDF", len(df_cmp), user, loc.id)
                    )
                    if dcols[3].button("👁️ View PDF", use_container_width=True, key="yt_cmp_view_pdf"):
                        if pdf_bytes:
                            import base64, streamlit.components.v1 as components
                            b64 = base64.b64encode(pdf_bytes).decode("ascii")
                            components.html(
                                f"""
                                <script>
                                (function(){{
                                    const w = window.open("");
                                    w.document.write('<html><head><title>YADE Mapping Comparison</title></head>'+\
                                                     '<body style="margin:0"><iframe width="100%" height="100%" src="data:application/pdf;base64,{b64}"></iframe></body></html>');
                                }})();
                                </script>
                                """,
                                height=0,
                            )
                            try:
                                SecurityManager.log_audit(
                                    s,
                                    user.get("username", "unknown"),
                                    "VIEW",
                                    resource_type="YadeTrackingComparison",
                                    resource_id=str(loc.id),
                                    details="Viewed YADE tracking comparison PDF",
                                    user_id=user.get("id"),
                                    location_id=loc.id,
                                )
                            except Exception:
                                pass

                    pass

                target = st.session_state.get("yt_delete_target")
                if target:
                    t_rec = target.get("record") or {}
                    t_date = t_rec.get("Date")
                    t_lbl = f"{t_rec.get('Yade No')} · Convoy {t_rec.get('Convoy No')} · {t_date}"
                    st.warning(f"Confirm deletion of mapping row {t_lbl}?")
                    dcs = st.columns(2)
                    if dcs[0].button("Yes, delete", key="yt_cmp_confirm_delete"):
                        try:
                            idx = int(target.get("index"))
                            saved = st.session_state.get("yt_cmp_records", [])
                            if 0 <= idx < len(saved):
                                removed = saved.pop(idx)
                                st.session_state["yt_cmp_records"] = saved
                                try:
                                    SecurityManager.log_audit(
                                        s,
                                        user.get("username", "unknown"),
                                        "DELETE",
                                        resource_type="YadeTrackingMapping",
                                        resource_id=f"{removed.get('Yade No')}|{removed.get('Convoy No')}|{removed.get('Date')}",
                                        details="Deleted Yade Tracking mapping row",
                                        user_id=user.get("id"),
                                        location_id=loc.id,
                                    )
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        st.session_state["yt_delete_target"] = None
                        st.success("Mapping row deleted.")
                        st.rerun()
                    if dcs[1].button("Cancel", key="yt_cmp_cancel_delete"):
                        st.session_state["yt_delete_target"] = None
                        st.rerun()
                    csv_bytes = df_cmp.to_csv(index=False).encode("utf-8")
                    from io import BytesIO
                    xbuf = BytesIO()
                    with pd.ExcelWriter(xbuf, engine="xlsxwriter") as writer:
                        df_cmp.to_excel(writer, index=False, sheet_name="Comparison")
                    xbuf.seek(0)
                    def _generate_cmp_pdf(dfpdf: pd.DataFrame) -> bytes:
                        try:
                            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
                            from reportlab.lib.pagesizes import A4, landscape
                            from reportlab.lib import colors
                            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                            from reportlab.lib.units import cm
                            buf = BytesIO()
                            doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=0.6*cm, rightMargin=0.6*cm, topMargin=0.7*cm, bottomMargin=0.7*cm)
                            styles = getSampleStyleSheet()
                            hdr = Paragraph("YADE Mapping Comparison", ParagraphStyle(name="hdr", parent=styles["Heading2"], alignment=1, textColor=colors.white))
                            hdr_tbl = Table([[hdr]], colWidths=[doc.width])
                            hdr_tbl.setStyle(TableStyle([
                                ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#0B3D91")),
                                ("ALIGN", (0,0), (-1,-1), "CENTER"),
                                ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                                ("FONTSIZE", (0,0), (-1,-1), 14),
                                ("BOTTOMPADDING", (0,0), (-1,-1), 10),
                                ("TOPPADDING", (0,0), (-1,-1), 10),
                            ]))
                            elements = [hdr_tbl, Spacer(1, 0.25*cm)]
                            headers = dfpdf.columns.tolist()
                            data_rows = [headers] + dfpdf.astype(str).values.tolist()
                            tbl = Table(data_rows, repeatRows=1)
                            tbl.setStyle(TableStyle([
                                ("GRID", (0,0), (-1,-1), 0.25, colors.HexColor("#D0D4DA")),
                                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E9EDF5")),
                                ("TEXTCOLOR", (0,0), (-1,0), colors.HexColor("#0B3D91")),
                                ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
                                ("ALIGN", (0,0), (-1,-1), "CENTER"),
                                ("FONTSIZE", (0,0), (-1,-1), 9),
                                ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F7F9FC")]),
                            ]))
                            elements.append(tbl)
                            doc.build(elements)
                            out = buf.getvalue()
                            buf.close()
                            return out
                        except Exception:
                            return b""
                    pdf_bytes = _generate_cmp_pdf(df_cmp)
                    dcols = st.columns(4)
                    dcols[0].download_button(
                        "📥 CSV",
                        data=csv_bytes,
                        file_name="yade_mapping_comparison.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key="yt_cmp_csv2",
                        on_click=lambda: log_export_action("YadeTrackingComparison", "CSV", len(df_cmp), user, loc.id)
                    )
                    dcols[1].download_button(
                        "📥 XLSX",
                        data=xbuf.getvalue(),
                        file_name="yade_mapping_comparison.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        key="yt_cmp_xlsx2",
                        on_click=lambda: log_export_action("YadeTrackingComparison", "XLSX", len(df_cmp), user, loc.id)
                    )
                    dcols[2].download_button(
                        "📥 PDF",
                        data=pdf_bytes or b"",
                        file_name="yade_mapping_comparison.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        key="yt_cmp_pdf2",
                        on_click=lambda: log_export_action("YadeTrackingComparison", "PDF", len(df_cmp), user, loc.id)
                    )
                    if dcols[3].button("👁️ View PDF", use_container_width=True, key="yt_cmp_view_pdf2"):
                        if pdf_bytes:
                            import base64, streamlit.components.v1 as components
                            b64 = base64.b64encode(pdf_bytes).decode("ascii")
                            components.html(
                                f"""
                                <script>
                                (function(){{
                                    const w = window.open("");
                                    w.document.write('<html><head><title>YADE Mapping Comparison</title></head>'+\
                                                     '<body style="margin:0"><iframe width="100%" height="100%" src="data:application/pdf;base64,{b64}"></iframe></body></html>');
                                }})();
                                </script>
                                """,
                                height=0,
                            )
                            try:
                                SecurityManager.log_audit(
                                    s,
                                    user.get("username", "unknown"),
                                    "VIEW",
                                    resource_type="YadeTrackingComparison",
                                    resource_id=str(loc.id),
                                    details="Viewed YADE tracking comparison PDF",
                                    user_id=user.get("id"),
                                    location_id=loc.id,
                                )
                            except Exception:
                                pass
            return

            tab_labels: List[str] = []
            if yt_cfg.get("is_sender"):
                tab_labels.append("Sender Desk")
            if yt_cfg.get("is_receiver"):
                tab_labels += ["Receiver Desk", "Completed Trips", "Comparison Report", "STS"]
            if not tab_labels:
                st.info("This location is neither sender nor receiver for yade tracking.")
                return
            tabs = st.tabs(tab_labels) if len(tab_labels) > 1 else [st.container()]
            tab_idx = 0

            if yt_cfg.get("is_sender"):
                with tabs[tab_idx]:
                    rows = []
                    receiver_lookup = {(str(v.convoy_no or ""), str(v.yade_name or "")) for v in receiver_voyages}
                    for v in sender_voyages:
                        stages = sender_stage_map.get(v.id, {})
                        b = stages.get("before")
                        a = stages.get("after")
                        bn = float(getattr(b, "nsv_bbl", 0.0) or 0.0) if b else None
                        an = float(getattr(a, "nsv_bbl", 0.0) or 0.0) if a else None
                        net = _net_nsv(stages)
                        status = "RECEIVED" if _key(v) in receiver_lookup else "PENDING"
                        rows.append(
                            {
                                "Date": v.date,
                                "Convoy": v.convoy_no,
                                "Yade": v.yade_name,
                                "From": loc_lookup.get(v.location_id, {}).get("name", v.location_id),
                                "Destination": v.destination,
                                "ROB NSV (bbl)": bn,
                                "TOB NSV (bbl)": an,
                                "Net (bbl)": net,
                                "Status": status,
                            }
                        )
                    st.markdown("#### Sender Desk")
                    df_sender = pd.DataFrame(rows)
                    st.dataframe(df_sender, use_container_width=True, hide_index=True)
                    if not df_sender.empty:
                        st.download_button(
                            "Export CSV",
                            data=df_sender.to_csv(index=False).encode("utf-8"),
                            file_name="yade_sender_desk.csv",
                            mime="text/csv",
                            key="yt_sender_export",
                        )
                tab_idx += 1

            if yt_cfg.get("is_receiver"):
                with tabs[tab_idx]:
                    pending = []
                    for v in receiver_voyages:
                        if receiver_aliases:
                            tokens = {t.strip().lower() for t in receiver_aliases if t}
                            val = (v.destination or "").strip().lower().replace(" ", "").replace("-", "").replace("_", "")
                            if tokens and val not in tokens:
                                continue
                        matched = _key(v) in receiver_keys_here
                        if matched:
                            continue
                        stages = receiver_stage_map.get(v.id, {})
                        b = stages.get("before")
                        a = stages.get("after")
                        bn = float(getattr(b, "nsv_bbl", 0.0) or 0.0) if b else None
                        an = float(getattr(a, "nsv_bbl", 0.0) or 0.0) if a else None
                        net = _net_nsv(stages)
                        pending.append(
                            {
                                "Date": v.date,
                                "Convoy": v.convoy_no,
                                "Yade": v.yade_name,
                                "From": loc_lookup.get(v.location_id, {}).get("name", v.location_id),
                                "Destination": v.destination,
                                "ROB NSV (bbl)": bn,
                                "TOB NSV (bbl)": an,
                                "Net (bbl)": net,
                                "Status": "PENDING",
                                "_id": v.id,
                            }
                        )
                    st.markdown("#### Receiver Desk")
                    df_pending = pd.DataFrame(pending)
                    st.dataframe(df_pending.drop(columns=["_id"], errors="ignore"), use_container_width=True, hide_index=True)
                    if not df_pending.empty:
                        st.download_button(
                            "Export CSV",
                            data=df_pending.drop(columns=["_id"], errors="ignore").to_csv(index=False).encode("utf-8"),
                            file_name="yade_receiver_pending.csv",
                            mime="text/csv",
                            key="yt_receiver_pending_export",
                        )
                        sel_opts = [
                            (
                                f"{r['Date']} · Convoy {r['Convoy']} · {r['Yade']}",
                                int(r["_id"])
                            ) for _, r in df_pending.iterrows()
                        ]
                        labels = [lbl for lbl, _ in sel_opts]
                        ids = {lbl: vid for lbl, vid in sel_opts}
                        sel_label = st.selectbox("Select voyage to receive", options=labels, key="yt_recv_select")
                        if sel_label:
                            vid = ids.get(sel_label)
                            v = next((x for x in receiver_voyages if x.id == vid), None)
                            if v:
                                s_v = sender_by_key.get(_key(v))
                                s_after = sender_stage_map.get(getattr(s_v, "id", -1), {}).get("after") if s_v else None
                                prefill_nsv = float(getattr(s_after, "nsv_bbl", 0.0) or 0.0) if s_after else 0.0
                                tank_ids, max_by = _get_barge_tanks_and_limits(str(v.yade_name or ""), str(v.design or ""))
                                st.markdown("##### Dips (cm)")
                                dip_cols = st.columns(2, gap="large")
                                with dip_cols[0]:
                                    st.markdown("#### Before")
                                    bc1, bc2 = st.columns(2)
                                    recv_date = bc1.date_input("Date", value=date.today(), max_value=date.today(), key="yt_recv_date")
                                    recv_time = bc2.time_input("Time", value=datetime.now().time(), key="yt_recv_time")
                                    dips_before: Dict[str, Dict[str, float]] = {}
                                    for tid in tank_ids:
                                        max_cm = float(max_by.get(tid, 9999.0))
                                        r1, r2, r3 = st.columns([0.22, 0.39, 0.39])
                                        with r1:
                                            st.text_input("Tank", value=tid, disabled=True, key=f"yt_recv_before_tank_{tid}")
                                        with r2:
                                            tot = st.number_input("Total Dip (cm)", min_value=0.0, max_value=max_cm, step=0.1, value=0.0, key=f"yt_recv_before_total_{tid}")
                                        with r3:
                                            wat = st.number_input("Water Dip (cm)", min_value=0.0, max_value=max_cm, step=0.1, value=0.0, key=f"yt_recv_before_water_{tid}")
                                        dips_before[tid] = {"total_cm": float(tot or 0.0), "water_cm": float(wat or 0.0)}
                                with dip_cols[1]:
                                    st.markdown("#### After")
                                    ac1, ac2 = st.columns(2)
                                    after_date = ac1.date_input("Date", value=date.today(), max_value=date.today(), key="yt_recv_after_date")
                                    after_time = ac2.time_input("Time", value=datetime.now().time(), key="yt_recv_after_time")
                                    dips_after: Dict[str, Dict[str, float]] = {}
                                    for tid in tank_ids:
                                        max_cm = float(max_by.get(tid, 9999.0))
                                        r1, r2, r3 = st.columns([0.22, 0.39, 0.39])
                                        with r1:
                                            st.text_input("Tank", value=tid, disabled=True, key=f"yt_recv_after_tank_{tid}")
                                        with r2:
                                            tot = st.number_input("Total Dip (cm)", min_value=0.0, max_value=max_cm, step=0.1, value=0.0, key=f"yt_recv_after_total_{tid}")
                                        with r3:
                                            wat = st.number_input("Water Dip (cm)", min_value=0.0, max_value=max_cm, step=0.1, value=0.0, key=f"yt_recv_after_water_{tid}")
                                        dips_after[tid] = {"total_cm": float(tot or 0.0), "water_cm": float(wat or 0.0)}
                                st.markdown("##### Sample Parameters")
                                sp_cols = st.columns(2, gap="large")
                                with sp_cols[0]:
                                    st.markdown("#### Before")
                                    sc1, sc2, sc3 = st.columns(3)
                                    obs_mode = sc1.selectbox("Observed", ["Observed API", "Observed Density"], key="yt_sp_mode")
                                    obs_val = sc2.number_input("Value", min_value=0.0, step=0.01, key="yt_sp_val")
                                    sample_unit = sc3.selectbox("Unit", ["F", "C"], key="yt_sp_unit")
                                    sc4, sc5, sc6 = st.columns(3)
                                    sample_temp = sc4.number_input("Sample Temp", min_value=0.0, step=0.1, key="yt_sp_sample_temp")
                                    tank_temp = sc5.number_input("Tank Temp", min_value=0.0, step=0.1, key="yt_sp_tank_temp")
                                    ccf = sc6.number_input("CCF", min_value=0.0, step=0.001, value=1.0, key="yt_sp_ccf")
                                    sc7 = st.columns(1)[0]
                                    bsw_pct = sc7.number_input("BS&W %", min_value=0.0, max_value=100.0, step=0.1, key="yt_sp_bsw")
                                with sp_cols[1]:
                                    st.markdown("#### After")
                                    s2c1, s2c2, s2c3 = st.columns(3)
                                    obs_mode_a = s2c1.selectbox("Observed", ["Observed API", "Observed Density"], key="yt_sp2_mode")
                                    obs_val_a = s2c2.number_input("Value", min_value=0.0, step=0.01, key="yt_sp2_val")
                                    sample_unit_a = s2c3.selectbox("Unit", ["F", "C"], key="yt_sp2_unit")
                                    s2c4, s2c5, s2c6 = st.columns(3)
                                    sample_temp_a = s2c4.number_input("Sample Temp", min_value=0.0, step=0.1, key="yt_sp2_sample_temp")
                                    tank_temp_a = s2c5.number_input("Tank Temp", min_value=0.0, step=0.1, key="yt_sp2_tank_temp")
                                    ccf_a = s2c6.number_input("CCF", min_value=0.0, step=0.001, value=1.0, key="yt_sp2_ccf")
                                    s2c7, s2c8 = st.columns(2)
                                    bsw_pct_a = s2c7.number_input("BS&W %", min_value=0.0, max_value=100.0, step=0.1, key="yt_sp2_bsw")
                                    save = s2c8.button("Save Receipt", type="primary", key="yt_recv_save")
                                if save:
                                    # Guard rail: ensure destination matches this receiver's aliases
                                    try:
                                        alias_tokens = {t.strip().lower().replace(" ", "").replace("-", "").replace("_", "") for t in (receiver_aliases or []) if t}
                                        dest_norm = (str(v.destination or "").strip().lower().replace(" ", "").replace("-", "").replace("_", ""))
                                        if alias_tokens and dest_norm not in alias_tokens:
                                            st.error("Destination does not match this receiver's configuration. Receipt blocked.")
                                            raise RuntimeError("Receiver alias mismatch")
                                        with get_session() as s2:
                                            exist = (
                                                s2.query(YadeVoyage)
                                                .filter(YadeVoyage.location_id == loc.id)
                                                .filter(YadeVoyage.convoy_no == str(v.convoy_no or ""))
                                                .filter(YadeVoyage.yade_name == str(v.yade_name or ""))
                                                .one_or_none()
                                            )
                                            if not exist:
                                                new_v = YadeVoyage(
                                                    location_id=loc.id,
                                                    yade_name=str(v.yade_name or ""),
                                                    design=str(v.design or ""),
                                                    voyage_no=str(v.voyage_no or ""),
                                                    convoy_no=str(v.convoy_no or ""),
                                                    date=recv_date,
                                                    time=recv_time,
                                                    cargo=str(v.cargo or ""),
                                                    destination=str(v.destination or ""),
                                                    loading_berth=str(v.loading_berth or ""),
                                                    before_gauge_date=recv_date,
                                                    before_gauge_time=recv_time,
                                                    after_gauge_date=after_date,
                                                    after_gauge_time=after_time,
                                                    created_by=user.get("username", "system"),
                                                )
                                                s2.add(new_v)
                                                s2.flush()
                                                vid2 = int(new_v.id)
                                            else:
                                                exist.date = recv_date
                                                exist.time = recv_time
                                                exist.before_gauge_date = recv_date
                                                exist.before_gauge_time = recv_time
                                                exist.after_gauge_date = after_date
                                                exist.after_gauge_time = after_time
                                                exist.updated_by = user.get("username", "system")
                                                exist.updated_at = datetime.utcnow()
                                                s2.flush()
                                                vid2 = int(exist.id)
                                            s2.query(YadeDip).filter(YadeDip.voyage_id == vid2).filter(func.upper(YadeDip.stage) == "BEFORE").delete()
                                            for tank_id, vals in dips_before.items():
                                                s2.add(YadeDip(voyage_id=vid2, tank_id=tank_id, stage="BEFORE", total_cm=float(vals.get("total_cm", 0.0)), water_cm=float(vals.get("water_cm", 0.0))))
                                            s2.query(YadeDip).filter(YadeDip.voyage_id == vid2).filter(func.upper(YadeDip.stage) == "AFTER").delete()
                                            for tank_id, vals in dips_after.items():
                                                s2.add(YadeDip(voyage_id=vid2, tank_id=tank_id, stage="AFTER", total_cm=float(vals.get("total_cm", 0.0)), water_cm=float(vals.get("water_cm", 0.0))))
                                            sp = (
                                                s2.query(YadeSampleParam)
                                                .filter(YadeSampleParam.voyage_id == vid2)
                                                .filter(func.upper(YadeSampleParam.stage) == "BEFORE")
                                                .one_or_none()
                                            )
                                            if not sp:
                                                sp = YadeSampleParam(voyage_id=vid2, stage="BEFORE")
                                                s2.add(sp)
                                                s2.flush()
                                            sp.obs_mode = obs_mode
                                            sp.obs_val = float(obs_val or 0.0)
                                            sp.sample_unit = sample_unit
                                            sp.sample_temp = float(sample_temp or 0.0)
                                            sp.tank_temp = float(tank_temp or 0.0)
                                            sp.ccf = float(ccf or 1.0)
                                            sp.bsw_pct = float(bsw_pct or 0.0)
                                            sp2 = (
                                                s2.query(YadeSampleParam)
                                                .filter(YadeSampleParam.voyage_id == vid2)
                                                .filter(func.upper(YadeSampleParam.stage) == "AFTER")
                                                .one_or_none()
                                            )
                                            if not sp2:
                                                sp2 = YadeSampleParam(voyage_id=vid2, stage="AFTER")
                                                s2.add(sp2)
                                                s2.flush()
                                            sp2.obs_mode = obs_mode_a
                                            sp2.obs_val = float(obs_val_a or 0.0)
                                            sp2.sample_unit = sample_unit_a
                                            sp2.sample_temp = float(sample_temp_a or 0.0)
                                            sp2.tank_temp = float(tank_temp_a or 0.0)
                                            sp2.ccf = float(ccf_a or 1.0)
                                            sp2.bsw_pct = float(bsw_pct_a or 0.0)
                                            s2.flush()
                                            compute_and_save_summary(s2, vid2, created_by=user.get("username", "system"))
                                            s2.commit()
                                            try:
                                                SecurityManager.log_audit(
                                                    s2,
                                                    user.get("username", "system"),
                                                    "CREATE",
                                                    resource_type="YadeVoyage:Receiver",
                                                    resource_id=str(vid2),
                                                    details=f"Receiver BEFORE captured for {v.yade_name} convoy {v.convoy_no}",
                                                    user_id=user.get("id"),
                                                    location_id=loc.id,
                                                    ip_address=st.session_state.get("client_ip"),
                                                    success=True,
                                                )
                                            except Exception:
                                                pass
                                        st.success("Saved receipt. Entry created for receiver location.")
                                        st.rerun()
                                    except Exception as ex:
                                        st.error(f"Save failed: {ex}")
                tab_idx += 1

                with tabs[tab_idx]:
                    completed = []
                    for v in receiver_voyages:
                        if receiver_aliases:
                            tokens = {t.strip().lower() for t in receiver_aliases if t}
                            val = (v.destination or "").strip().lower().replace(" ", "").replace("-", "").replace("_", "")
                            if tokens and val not in tokens:
                                continue
                        matched = _key(v) in receiver_keys_here
                        if not matched:
                            continue
                        stages = receiver_stage_map.get(v.id, {})
                        b = stages.get("before")
                        a = stages.get("after")
                        bn = float(getattr(b, "nsv_bbl", 0.0) or 0.0) if b else None
                        an = float(getattr(a, "nsv_bbl", 0.0) or 0.0) if a else None
                        net = _net_nsv(stages)
                        completed.append(
                            {
                                "Date": v.date,
                                "Convoy": v.convoy_no,
                                "Yade": v.yade_name,
                                "From": loc_lookup.get(v.location_id, {}).get("name", v.location_id),
                                "Destination": v.destination,
                                "ROB NSV (bbl)": bn,
                                "TOB NSV (bbl)": an,
                                "Net (bbl)": net,
                                "Status": "RECEIVED",
                            }
                        )
                    st.markdown("#### Completed Trips")
                    df_completed = pd.DataFrame(completed)
                    st.dataframe(df_completed, use_container_width=True, hide_index=True)
                    if not df_completed.empty:
                        st.download_button(
                            "Export CSV",
                            data=df_completed.to_csv(index=False).encode("utf-8"),
                            file_name="yade_receiver_completed.csv",
                            mime="text/csv",
                            key="yt_receiver_completed_export",
                        )
                tab_idx += 1

                with tabs[tab_idx]:
                    pairs: Dict[tuple, Dict[str, Any]] = {}
                    # Use the local receiver entries for the 'receiver_before' side of the comparison
                    local_voyages = s.query(YadeVoyage).filter(YadeVoyage.location_id == loc.id).all()
                    local_by_key = { _key(v): v for v in local_voyages }
                    local_stage_map = _stages_map([v.id for v in local_voyages])

                    for k, v_local in local_by_key.items():
                        tokens = {t.strip().lower() for t in receiver_aliases if t}
                        val = (v_local.destination or "").strip().lower().replace(" ", "").replace("-", "").replace("_", "")
                        if tokens and val not in tokens:
                            continue
                        r_stages = local_stage_map.get(v_local.id, {})
                        r_before = r_stages.get("before")
                        r_before_nsv = float(getattr(r_before, "nsv_bbl", 0.0) or 0.0) if r_before else None
                        pairs.setdefault(k, {})["receiver_before"] = r_before_nsv

                    for v in sender_voyages:
                        k = _key(v)
                        s_stages = sender_stage_map.get(v.id, {})
                        s_after = s_stages.get("after")
                        s_after_nsv = float(getattr(s_after, "nsv_bbl", 0.0) or 0.0) if s_after else None
                        pairs.setdefault(k, {})["sender_after"] = s_after_nsv
                    cmp_rows = []
                    for (conv, yname), data in pairs.items():
                        s_net = data.get("sender_after")
                        r_net = data.get("receiver_before")
                        var = None
                        if s_net is not None and r_net is not None:
                            var = float(r_net) - float(s_net)
                        cmp_rows.append(
                            {
                                "Convoy": conv,
                                "Yade": yname,
                                "Sender After NSV (bbl)": s_net,
                                "Receiver Before NSV (bbl)": r_net,
                                "Variance (bbl)": var,
                            }
                        )
                    st.markdown("#### Comparison Report")
                    df_cmp = pd.DataFrame(cmp_rows)
                    st.dataframe(df_cmp, use_container_width=True, hide_index=True)
                    if not df_cmp.empty:
                        st.download_button(
                            "Export CSV",
                            data=df_cmp.to_csv(index=False).encode("utf-8"),
                            file_name="yade_comparison_before_after.csv",
                            mime="text/csv",
                            key="yt_cmp_export",
                        )
                tab_idx += 1
                with tabs[tab_idx]:
                    st.markdown("#### STS Dispatch")
                    if receiver_source_ids:
                        src_options = [(lid, loc_lookup.get(lid, {}).get("name", str(lid))) for lid in receiver_source_ids]
                        src_labels = [name for _, name in src_options]
                        src_by_label = {name: lid for lid, name in src_options}
                        c_sts1, c_sts2, c_sts3 = st.columns(3)
                        sel_src_label = c_sts1.selectbox("Source Location", options=src_labels, key="yt_sts_src")
                        sts_yade = c_sts2.text_input("Yade Name", key="yt_sts_yade")
                        sts_convoy = c_sts3.text_input("Convoy No", key="yt_sts_convoy")
                        c_sts4, c_sts5, c_sts6 = st.columns(3)
                        sts_date = c_sts4.date_input("Dispatch Date", value=date.today(), max_value=date.today(), key="yt_sts_date")
                        sts_time = c_sts5.time_input("Dispatch Time", value=datetime.now().time(), key="yt_sts_time")
                        sts_after_nsv = c_sts6.number_input("Sender After NSV (bbl)", min_value=0.0, value=0.0, step=0.01, key="yt_sts_after_nsv")
                        if st.button("Save STS Dispatch", type="primary", key="yt_sts_save"):
                            try:
                                src_id = src_by_label.get(sel_src_label)
                                if not src_id:
                                    raise RuntimeError("Source location required")
                                with get_session() as s2:
                                    ref = (
                                        s2.query(YadeVoyage)
                                        .filter(YadeVoyage.yade_name == str(sts_yade or ""))
                                        .order_by(YadeVoyage.created_at.desc())
                                        .first()
                                    )
                                    design_val = str(getattr(ref, "design", "NA") or "NA")
                                    new_v = YadeVoyage(
                                        location_id=int(src_id),
                                        yade_name=str(sts_yade or ""),
                                        design=design_val,
                                        voyage_no=str(sts_convoy or ""),
                                        convoy_no=str(sts_convoy or ""),
                                        date=sts_date,
                                        time=sts_time,
                                        cargo="STS",
                                        destination=str(loc.name or loc.code or ""),
                                        loading_berth="STS",
                                        before_gauge_date=sts_date,
                                        before_gauge_time=sts_time,
                                        after_gauge_date=sts_date,
                                        after_gauge_time=sts_time,
                                        created_by=user.get("username", "system"),
                                    )
                                    s2.add(new_v)
                                    s2.flush()
                                    stg = TOAYadeStage(voyage_id=int(new_v.id), stage="after", nsv_bbl=float(sts_after_nsv or 0.0))
                                    s2.add(stg)
                                    s2.commit()
                                    try:
                                        SecurityManager.log_audit(
                                            s2,
                                            user.get("username", "system"),
                                            "CREATE",
                                            resource_type="YadeVoyage:STS",
                                            resource_id=str(new_v.id),
                                            details=f"STS dispatch created from {src_id} to {loc.name}",
                                            user_id=user.get("id"),
                                            location_id=loc.id,
                                            ip_address=st.session_state.get("client_ip"),
                                            success=True,
                                        )
                                    except Exception:
                                        pass
                                st.success("STS dispatch saved. It will appear in Receiver Desk pending list.")
                                st.rerun()
                            except Exception as ex:
                                st.error(f"STS save failed: {ex}")
                    else:
                        st.info("No receiver sources configured for this location. Set them in Location Settings → Yade Tracking.")
                return

        else:
            st.info("Yade Tracking requires sender/receiver configuration. Enable roles in Location Settings.")
            return

