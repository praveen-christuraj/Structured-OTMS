from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple
import base64
import pandas as pd
import streamlit as st
from sqlalchemy import and_, func

from db import get_session
from ui import header
from security import SecurityManager
from location_config import LocationConfig
from task_manager import TaskManager

from models import (
    Location,
    YadeBarge,
    YadeVoyage,
    TOAYadeSummary,
    TOAYadeStage,
    OTRVessel,
    LocationVessel,
    Vessel,
    ConvoyStatusYade,
    ConvoyStatusVessel,
)


def _st_safe_rerun():
    try:
        st.experimental_rerun()
    except Exception:
        st.rerun()


def render_convoy_status_page(active_location_id: Optional[int], user: Optional[Dict[str, Any]]):
    header("Convoy Status")

    if not user:
        st.error("Please login to access this page.")
        st.stop()

    role = (user.get("role") or "").lower()
    if role == "admin-it":
        st.error("🚫 Access Denied: Admin-IT users do not have access to operational pages.")
        st.stop()

    if not active_location_id and role != "admin-operations":
        st.error("No active location selected.")
        st.stop()

    def _norm(val: Optional[str]) -> str:
        return (val or "").strip()

    def _norm_name(val: Optional[str]) -> str:
        return _norm(val).lower()

    with get_session() as s:
        all_locations = s.query(Location).order_by(Location.name).all()
        active_loc = s.query(Location).get(active_location_id) if active_location_id else None

    allowed_loc_names = {"agge", "utapate", "lagos (ho)"}
    if role != "admin-operations":
        if not active_loc:
            st.error("Active location not found.")
            st.stop()
        if _norm_name(active_loc.name) not in allowed_loc_names:
            st.error("Convoy Status is restricted to Agge, Utapate, Lagos (HO), or administrators.")
            st.stop()

    target_location_id = active_loc.id if active_loc else None
    if role in ["admin-operations", "manager"]:
        allowed_objs = [loc for loc in all_locations if _norm_name(loc.name) in allowed_loc_names]
        if not allowed_objs:
            st.error("No eligible locations configured for Convoy Status.")
            st.stop()
        options = {loc.id: f"{loc.name} ({loc.code})" for loc in allowed_objs}
        default_id = st.session_state.get("convoy_status_admin_loc") or target_location_id or allowed_objs[0].id
        items = sorted(options.items(), key=lambda it: it[1])
        idx = [i for i, (lid, _) in enumerate(items) if lid == default_id]
        target_location_id = st.selectbox(
            "Select Location",
            items,
            format_func=lambda it: it[1],
            index=(idx[0] if idx else 0),
            key="convoy_status_admin_loc_selector",
        )[0]
        st.session_state["convoy_status_admin_loc"] = target_location_id
        with get_session() as s:
            target_loc = s.query(Location).get(target_location_id)
    else:
        target_loc = active_loc

    if not target_loc:
        st.error("Unable to determine selected location.")
        st.stop()

    target_loc_name = target_loc.name or "Unknown"
    target_loc_code = target_loc.code or ""
    target_norm = _norm_name(target_loc_name)
    st.success(f"Viewing Convoy Status for **{target_loc_name} ({target_loc_code})**")

    is_utapate = target_norm == "utapate"
    show_yade_tab = not is_utapate

    with get_session() as s:
        assigned_rows = s.query(LocationVessel).filter(LocationVessel.location_id == target_location_id, LocationVessel.is_active == True).all()
        assigned_vessel_ids = [row.vessel_id for row in assigned_rows]
        active_vessel_names = []
        if assigned_vessel_ids:
            _assigned = s.query(Vessel).filter(Vessel.id.in_(assigned_vessel_ids)).order_by(Vessel.name).all()
            active_vessel_names = [v.name for v in _assigned]

    source_location_ids = [target_location_id]

    with get_session() as s:
        yade_barges = s.query(YadeBarge).order_by(YadeBarge.name).all()

    vessel_id_map = {(_norm(v.name)).upper(): v.id for v in s.query(Vessel).filter(Vessel.id.in_(assigned_vessel_ids)).all()} if assigned_vessel_ids else {}

    def _load_yade_dropdown_data(target_date: date, loc_ids: List[int]):
        convoy_map: Dict[str, List[str]] = {}
        stock_map: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        if not loc_ids:
            return convoy_map, stock_map
        with get_session() as s:
            q = (
                s.query(
                    YadeVoyage.yade_name,
                    YadeVoyage.convoy_no,
                    YadeVoyage.voyage_no,
                    YadeVoyage.location_id,
                    YadeVoyage.date.label("voyage_date"),
                    YadeVoyage.after_gauge_date,
                    YadeVoyage.after_gauge_time,
                    TOAYadeStage.nsv_bbl,
                )
                .outerjoin(
                    TOAYadeStage,
                    and_(TOAYadeStage.voyage_id == YadeVoyage.id, func.upper(TOAYadeStage.stage) == "AFTER"),
                )
                .filter(YadeVoyage.location_id.in_(loc_ids))
                .order_by(
                    YadeVoyage.after_gauge_date.desc(),
                    YadeVoyage.after_gauge_time.desc().nullslast(),
                    YadeVoyage.date.desc(),
                )
                .limit(1000)
            )
            rows = q.all()
        for yname, convoy, vno, loc_id, vdate, sdate, stime, nsv_bbl in rows:
            yname = _norm(yname)
            convoy = _norm(convoy)
            if yname and convoy:
                convoy_map.setdefault(yname, [])
                if convoy not in convoy_map[yname]:
                    convoy_map[yname].append(convoy)
            if yname and convoy and isinstance(nsv_bbl, (int, float)):
                tlabel = stime.strftime("%H:%M") if stime else ""
                dlabel = sdate.strftime("%d-%b-%Y") if sdate else (vdate.strftime("%d-%b-%Y") if vdate else "")
                parts = [f"{float(nsv_bbl):,.2f} bbls"]
                if convoy:
                    parts.append(f"Convoy {convoy}")
                if tlabel:
                    parts.append(f"@ {tlabel}")
                if dlabel:
                    parts.append(f"on {dlabel}")
                label = " ".join(parts)
                stock_map.setdefault((yname, convoy), []).append({"label": label, "value": float(nsv_bbl)})
        for k in convoy_map:
            convoy_map[k] = sorted(convoy_map[k])
        return convoy_map, stock_map

    def _load_vessel_dropdown_data(target_date: date, loc_id: int, allowed_vessel_ids: List[int]):
        shuttle_map: Dict[str, List[str]] = {}
        stock_map: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        seen_by_vessel: Dict[str, set] = {}
        with get_session() as s:
            if not allowed_vessel_ids:
                otr_rows = []
            else:
                q = (
                    s.query(Vessel.name, OTRVessel.shuttle_no, OTRVessel.closing_stock, OTRVessel.time, OTRVessel.date)
                    .join(Vessel, Vessel.id == OTRVessel.vessel_id)
                    .filter(OTRVessel.location_id == loc_id, OTRVessel.vessel_id.in_(allowed_vessel_ids))
                    .order_by(OTRVessel.date.desc(), OTRVessel.time.desc().nullslast())
                    .limit(1000)
                )
                otr_rows = q.all()
        for vname, shuttle_no, closing_stock, tx_time, tx_date in otr_rows:
            vname = _norm(vname)
            shuttle_no = _norm(shuttle_no)
            seen = seen_by_vessel.setdefault(vname, set())
            if vname and shuttle_no and shuttle_no not in seen:
                seen.add(shuttle_no)
                shuttle_map.setdefault(vname, []).append(shuttle_no)
            if vname and closing_stock is not None:
                parts = [f"{float(closing_stock):,.2f} bbls"]
                if tx_time:
                    try:
                        parts.append(f"@ {tx_time.strftime('%H:%M')}")
                    except Exception:
                        parts.append(f"@ {tx_time}")
                if tx_date:
                    try:
                        parts.append(f"on {tx_date.strftime('%d-%b-%Y')}")
                    except Exception:
                        parts.append(f"on {tx_date}")
                label = " ".join(parts)
                stock_map.setdefault((vname, shuttle_no or ""), []).append({"label": label, "value": float(closing_stock)})
        for v in shuttle_map:
            shuttle_map[v] = sorted(shuttle_map[v])
        return shuttle_map, stock_map

    tab_specs: List[Tuple[str, str]] = []
    # Fetch per-location status options
    try:
        with get_session() as s:
            cfg = LocationConfig.get_config(s, target_location_id)
        cs = cfg.get("convoy_status", {}) if cfg else {}
        yade_status_options = list(cs.get("yade_statuses", []) or [])
        vessel_status_options = list(cs.get("vessel_statuses", []) or [])
    except Exception:
        yade_status_options, vessel_status_options = [], []

    if show_yade_tab:
        tab_specs.append(("Yade", "yade"))
    tab_specs.append(("Vessel", "vessel"))
    tab_specs.append(("Saved Entries", "saved"))
    tabs = st.tabs([label for label, _ in tab_specs])
    tab_idx = {kind: i for i, (_, kind) in enumerate(tab_specs)}

    if show_yade_tab:
        with tabs[tab_idx["yade"]]:
            if "convoy_status_yade_date" not in st.session_state:
                st.session_state["convoy_status_yade_date"] = date.today()
            yade_date = st.date_input("Select Date", max_value=date.today(), key="convoy_status_yade_date")
            convoy_map, yade_stock_map = _load_yade_dropdown_data(yade_date, source_location_ids)
            saved_yade = {}
            with get_session() as s:
                rows = s.query(ConvoyStatusYade).filter(ConvoyStatusYade.location_id == target_location_id, ConvoyStatusYade.date == yade_date).all()
                saved_yade = {row.yade_barge_id: row for row in rows}

            st.markdown("#### Yade Convoy Tracker")
            hc = st.columns([2.2, 2, 2, 2])
            hc[0].markdown("**YADE No**")
            hc[1].markdown("**Convoy**")
            hc[2].markdown("**Stock (After Loading NSV)**")
            hc[3].markdown("**Status**")

            status_opts_yade = (["Select status"] + yade_status_options) if yade_status_options else ["N/A"]

            for yade in yade_barges:
                rc = st.columns([2.2, 2, 2, 2])
                rc[0].markdown(f"**{yade.name}**")
                yname = _norm(yade.name)
                rec = saved_yade.get(yade.id)
                convoy_options = ["N/A"] + convoy_map.get(yname, [])
                if rec and rec.convoy_no and rec.convoy_no not in convoy_options:
                    convoy_options.append(rec.convoy_no)
                convoy_key = f"convoy_status_yade_{yade_date.isoformat()}_{yade.id}_convoy"
                if convoy_key not in st.session_state or st.session_state[convoy_key] not in convoy_options:
                    st.session_state[convoy_key] = rec.convoy_no if rec and rec.convoy_no else "N/A"
                selected_convoy = rc[1].selectbox("Convoy", convoy_options, key=convoy_key, label_visibility="collapsed")

                stock_candidates = yade_stock_map.get((yname, selected_convoy), [])
                stock_labels = ["N/A"] + [opt["label"] for opt in stock_candidates]
                if rec and rec.stock_display and rec.stock_display not in stock_labels:
                    stock_labels.append(rec.stock_display)
                stock_key = f"convoy_status_yade_{yade_date.isoformat()}_{yade.id}_stock"
                cur_stock = st.session_state.get(stock_key)
                if cur_stock not in stock_labels:
                    st.session_state[stock_key] = rec.stock_display if rec and rec.stock_display else "N/A"
                selected_stock = rc[2].selectbox("Stock", stock_labels, key=stock_key, label_visibility="collapsed")

                status_key = f"convoy_status_yade_{yade_date.isoformat()}_{yade.id}_status"
                cur_status = st.session_state.get(status_key)
                if cur_status not in status_opts_yade:
                    if rec and rec.status in status_opts_yade:
                        st.session_state[status_key] = rec.status
                    else:
                        st.session_state[status_key] = status_opts_yade[0]
                rc[3].selectbox("Status", status_opts_yade, key=status_key, label_visibility="collapsed")

        save_key = f"convoy_status_yade_save_{target_location_id}"
        if st.button(" Save YADE Status", key=save_key, use_container_width=True):
            try:
                with get_session() as s:
                    existing = s.query(ConvoyStatusYade).filter(ConvoyStatusYade.location_id == target_location_id, ConvoyStatusYade.date == yade_date).all()
                    existing_map = {row.yade_barge_id: row for row in existing}
                    changes = 0
                    for yade in yade_barges:
                        yname = _norm(yade.name)
                        convoy_key = f"convoy_status_yade_{yade_date.isoformat()}_{yade.id}_convoy"
                        stock_key = f"convoy_status_yade_{yade_date.isoformat()}_{yade.id}_stock"
                        status_key = f"convoy_status_yade_{yade_date.isoformat()}_{yade.id}_status"
                        selected_convoy = st.session_state.get(convoy_key, "N/A")
                        selected_stock = st.session_state.get(stock_key, "N/A")
                        selected_status = st.session_state.get(status_key, "Select status")
                        if selected_status in ("Select status", "N/A", ""):
                            continue
                        stock_value = None
                        for opt in yade_stock_map.get((yname, selected_convoy), []):
                            if opt["label"] == selected_stock:
                                stock_value = opt["value"]
                                break
                        record = existing_map.get(yade.id)
                        if not record:
                            record = ConvoyStatusYade(location_id=target_location_id, date=yade_date, yade_barge_id=yade.id, created_by=user.get("username", "unknown"))
                            s.add(record)
                        record.convoy_no = None if selected_convoy == "N/A" else selected_convoy
                        record.stock_display = None if selected_stock == "N/A" else selected_stock
                        record.stock_value_bbl = stock_value
                        record.status = selected_status
                        record.updated_by = user.get("username")
                        changes += 1
                    if changes > 0:
                        s.commit()
                        SecurityManager.log_audit(None, user["username"], "UPDATE", resource_type="ConvoyStatusYade", resource_id=f"{target_location_id}:{yade_date.isoformat()}", location_id=target_location_id, details=f"Saved {changes} YADE convoy rows for {yade_date}", user_id=user.get("id"))
                        st.success(f"YADE convoy status saved. {changes} record(s) updated.")
                    else:
                        st.warning("No valid entries to save. Please select a status for at least one YADE barge.")
                if changes > 0:
                    _st_safe_rerun()
            except Exception as ex:
                st.error(f"Failed to save YADE status: {ex}")
                import traceback
                st.code(traceback.format_exc())
    
    with tabs[tab_idx["vessel"]]:
        if "convoy_status_vessel_date" not in st.session_state:
            st.session_state["convoy_status_vessel_date"] = date.today()
        vessel_date = st.date_input("Select Date", max_value=date.today(), key="convoy_status_vessel_date")
        shuttle_map, vessel_stock_map = _load_vessel_dropdown_data(vessel_date, target_location_id, assigned_vessel_ids)
        saved_vessel = {}
        with get_session() as s:
            rows = s.query(ConvoyStatusVessel).filter(ConvoyStatusVessel.location_id == target_location_id, ConvoyStatusVessel.date == vessel_date).all()
            saved_vessel = {(row.vessel_name or "").upper(): row for row in rows}

        st.markdown("#### Vessel Convoy Tracker")
        hc = st.columns([2.2, 2, 2, 2])
        hc[0].markdown("**Vessel Name**")
        hc[1].markdown("**Shuttle No**")
        hc[2].markdown("**Stock (Closing)**")
        hc[3].markdown("**Status**")
        status_opts_vessel = (["Select status"] + vessel_status_options) if vessel_status_options else ["N/A"]

        for vname in active_vessel_names:
            rc = st.columns([2.2, 2, 2, 2])
            rc[0].markdown(f"**{vname}**")
            vkey = (_norm(vname)).upper()
            rec = saved_vessel.get(vkey)
            shuttle_options = ["N/A"] + shuttle_map.get(vname, [])
            if rec and rec.shuttle_no and rec.shuttle_no not in shuttle_options:
                shuttle_options.append(rec.shuttle_no)
            shuttle_key = f"convoy_status_vessel_{vessel_date.isoformat()}_{vkey}_shuttle"
            if shuttle_key not in st.session_state or st.session_state[shuttle_key] not in shuttle_options:
                st.session_state[shuttle_key] = rec.shuttle_no if rec and rec.shuttle_no else "N/A"
            selected_shuttle = rc[1].selectbox("Shuttle", shuttle_options, key=shuttle_key, label_visibility="collapsed")

            stock_candidates = vessel_stock_map.get((vname, selected_shuttle or ""), [])
            stock_labels = ["N/A"] + [opt["label"] for opt in stock_candidates]
            if rec and rec.stock_display and rec.stock_display not in stock_labels:
                stock_labels.append(rec.stock_display)
            stock_key = f"convoy_status_vessel_{vessel_date.isoformat()}_{vkey}_stock"
            if stock_key not in st.session_state or st.session_state[stock_key] not in stock_labels:
                st.session_state[stock_key] = rec.stock_display if rec and rec.stock_display else "N/A"
            rc[2].selectbox("Stock", stock_labels, key=stock_key, label_visibility="collapsed")

            status_key = f"convoy_status_vessel_{vessel_date.isoformat()}_{vkey}_status"
            cur_status = st.session_state.get(status_key)
            if cur_status not in status_opts_vessel:
                if rec and rec.status in status_opts_vessel:
                    st.session_state[status_key] = rec.status
                else:
                    st.session_state[status_key] = status_opts_vessel[0]
            rc[3].selectbox("Status", status_opts_vessel, key=status_key, label_visibility="collapsed")

        v_save_key = f"convoy_status_vessel_save_{target_location_id}"
        if st.button(" Save Vessel Status", key=v_save_key, use_container_width=True):
            try:
                with get_session() as s:
                    existing = s.query(ConvoyStatusVessel).filter(ConvoyStatusVessel.location_id == target_location_id, ConvoyStatusVessel.date == vessel_date).all()
                    existing_map = {(row.vessel_name or "").upper(): row for row in existing}
                    changes = 0
                    for vname in active_vessel_names:
                        vkey = (_norm(vname)).upper()
                        status_key = f"convoy_status_vessel_{vessel_date.isoformat()}_{vkey}_status"
                        selected_status = st.session_state.get(status_key, "Select status")
                        if selected_status in ("Select status", "N/A", ""):
                            continue
                        shuttle_key = f"convoy_status_vessel_{vessel_date.isoformat()}_{vkey}_shuttle"
                        stock_key = f"convoy_status_vessel_{vessel_date.isoformat()}_{vkey}_stock"
                        selected_shuttle = st.session_state.get(shuttle_key, "N/A")
                        selected_stock = st.session_state.get(stock_key, "N/A")
                        stock_value = None
                        for opt in vessel_stock_map.get((vname, selected_shuttle or ""), []):
                            if opt["label"] == selected_stock:
                                stock_value = opt["value"]
                                break
                        record = existing_map.get(vkey)
                        if not record:
                            record = ConvoyStatusVessel(location_id=target_location_id, date=vessel_date, vessel_name=vname, vessel_id=vessel_id_map.get(vkey), created_by=user.get("username", "unknown"))
                            s.add(record)
                        record.shuttle_no = None if selected_shuttle == "N/A" else selected_shuttle
                        record.stock_display = None if selected_stock == "N/A" else selected_stock
                        record.stock_value_bbl = stock_value
                        record.status = selected_status
                        record.updated_by = user.get("username")
                        changes += 1
                    if changes > 0:
                        s.commit()
                        SecurityManager.log_audit(None, user["username"], "UPDATE", resource_type="ConvoyStatusVessel", resource_id=f"{target_location_id}:{vessel_date.isoformat()}", location_id=target_location_id, details=f"Saved {changes} vessel convoy rows for {vessel_date}", user_id=user.get("id"))
                        st.success(f"Vessel convoy status saved. {changes} record(s) updated.")
                    else:
                        st.warning("No valid entries to save. Please select a status for at least one vessel.")
                if changes > 0:
                    _st_safe_rerun()
            except Exception as ex:
                st.error(f"Failed to save vessel status: {ex}")
                import traceback
                st.code(traceback.format_exc())

    with tabs[tab_idx["saved"]]:
        st.markdown("#### Saved Entries")
        fallback_notice = False
        
        # Debug information
        with st.expander("🔍 Debug Information", expanded=False):
            with get_session() as s:
                total_yade_all = s.query(ConvoyStatusYade).count()
                total_vessel_all = s.query(ConvoyStatusVessel).count()
                st.write(f"**Total records in database:**")
                st.write(f"- All YADE records: {total_yade_all}")
                st.write(f"- All Vessel records: {total_vessel_all}")
                st.write(f"- Current location ID: {target_location_id}")
        
        with get_session() as s:
            y_dates = [row[0] for row in s.query(ConvoyStatusYade.date).filter(ConvoyStatusYade.location_id == target_location_id).distinct().order_by(ConvoyStatusYade.date.desc()).all()]
            v_dates = [row[0] for row in s.query(ConvoyStatusVessel.date).filter(ConvoyStatusVessel.location_id == target_location_id).distinct().order_by(ConvoyStatusVessel.date.desc()).all()]
            
            # Debug: Show counts
            yade_total = s.query(ConvoyStatusYade).filter(ConvoyStatusYade.location_id == target_location_id).count()
            vessel_total = s.query(ConvoyStatusVessel).filter(ConvoyStatusVessel.location_id == target_location_id).count()

        if yade_total > 0 or vessel_total > 0:
            st.success(f"📊 Found {yade_total} YADE records and {vessel_total} Vessel records for this location.")
        else:
            st.info("ℹ️ No saved entries found for this location yet. Save entries in the YADE or Vessel tabs above.")

        y_col, v_col = st.columns(2)
        can_delete = role != "operator"

        with y_col:
            st.markdown("**YADE Entries**")
            if not y_dates:
                st.info("No YADE entries saved yet.")
            else:
                for idx, entry_date in enumerate(y_dates, start=1):
                    rc = st.columns([0.3, 1, 0.35, 0.35])
                    rc[0].markdown(f"**{idx}**")
                    rc[1].markdown(entry_date.strftime("%d-%b-%Y"))
                    view_key = f"convoy_status_view_yade_{entry_date}"
                    del_key = f"convoy_status_delete_yade_{entry_date}"
                    conf_key = f"convoy_status_confirm_delete_yade_{entry_date}"
                    if rc[2].button("👁️", key=view_key, use_container_width=True, help="View PDF"):
                        with get_session() as s:
                            rows = s.query(ConvoyStatusYade, YadeBarge.name).join(YadeBarge, ConvoyStatusYade.yade_barge_id == YadeBarge.id).filter(ConvoyStatusYade.location_id == target_location_id, ConvoyStatusYade.date == entry_date).order_by(YadeBarge.name).all()
                        pdf_rows = [[name, rec.convoy_no or "N/A", rec.stock_display or "-", rec.status] for rec, name in rows]
                        if not pdf_rows:
                            st.warning("No rows saved for that date.")
                        else:
                            pdf_bytes = _simple_pdf("YADE Convoy Status", f"{target_loc_name} • {entry_date:%d-%b-%Y}", ["YADE", "Convoy", "Stock", "Status"], pdf_rows)
                            _open_pdf(pdf_bytes, f"YADE Status - {target_loc_name}")
                            st.success("YADE PDF opened in a new tab.")
                    if rc[3].button("🗑️", key=del_key, use_container_width=True, help="Delete entry"):
                        st.session_state[conf_key] = True
                    if st.session_state.get(conf_key):
                        prompt = (
                            f"Confirm deletion of YADE snapshot for {entry_date:%d-%b-%Y}?" if can_delete else f"Request supervisor approval to delete YADE snapshot for {entry_date:%d-%b-%Y}?"
                        )
                        st.warning(prompt)
                        cc = st.columns(2)
                        if cc[0].button("✅ Confirm", key=f"{conf_key}_yes", use_container_width=True):
                            try:
                                if can_delete:
                                    _delete_convoy_snapshot("yade", target_location_id, entry_date, user)
                                    st.success("YADE snapshot deleted.")
                                else:
                                    _request_convoy_delete("yade", target_location_id, entry_date, user)
                                    st.success("Delete request sent to supervisor.")
                                st.session_state.pop(conf_key, None)
                                _st_safe_rerun()
                            except Exception as ex:
                                st.error(f"Delete failed: {ex}")
                                st.session_state.pop(conf_key, None)
                        if cc[1].button("❌ Cancel", key=f"{conf_key}_no", use_container_width=True):
                            st.session_state.pop(conf_key, None)

        with v_col:
            st.markdown("**Vessel Entries**")
            if not v_dates:
                st.info("No Vessel entries saved yet.")
            else:
                for idx, entry_date in enumerate(v_dates, start=1):
                    rc = st.columns([0.3, 1, 0.35, 0.35])
                    rc[0].markdown(f"**{idx}**")
                    rc[1].markdown(entry_date.strftime("%d-%b-%Y"))
                    view_key = f"convoy_status_view_vessel_{entry_date}"
                    del_key = f"convoy_status_delete_vessel_{entry_date}"
                    conf_key = f"convoy_status_confirm_delete_vessel_{entry_date}"
                    if rc[2].button("👁️", key=view_key, use_container_width=True, help="View PDF"):
                        with get_session() as s:
                            rows = s.query(ConvoyStatusVessel).filter(ConvoyStatusVessel.location_id == target_location_id, ConvoyStatusVessel.date == entry_date).order_by(ConvoyStatusVessel.vessel_name).all()
                        pdf_rows = [[rec.vessel_name, rec.shuttle_no or "N/A", rec.stock_display or "-", rec.status] for rec in rows]
                        if not pdf_rows:
                            st.warning("No rows saved for that date.")
                        else:
                            pdf_bytes = _simple_pdf("Vessel Convoy Status", f"{target_loc_name} • {entry_date:%d-%b-%Y}", ["Vessel", "Shuttle", "Stock", "Status"], pdf_rows)
                            _open_pdf(pdf_bytes, f"Vessel Status - {target_loc_name}")
                            st.success("Vessel PDF opened in a new tab.")
                    if rc[3].button("🗑️", key=del_key, use_container_width=True, help="Delete entry"):
                        st.session_state[conf_key] = True
                    if st.session_state.get(conf_key):
                        prompt = (
                            f"Confirm deletion of Vessel snapshot for {entry_date:%d-%b-%Y}?" if can_delete else f"Request supervisor approval to delete Vessel snapshot for {entry_date:%d-%b-%Y}?"
                        )
                        st.warning(prompt)
                        cc = st.columns(2)
                        if cc[0].button("✅ Confirm", key=f"{conf_key}_yes", use_container_width=True):
                            try:
                                if can_delete:
                                    _delete_convoy_snapshot("vessel", target_location_id, entry_date, user)
                                    st.success("Vessel snapshot deleted.")
                                else:
                                    _request_convoy_delete("vessel", target_location_id, entry_date, user)
                                    st.success("Delete request sent to supervisor.")
                                st.session_state.pop(conf_key, None)
                                _st_safe_rerun()
                            except Exception as ex:
                                st.error(f"Delete failed: {ex}")
                                st.session_state.pop(conf_key, None)
                        if cc[1].button("❌ Cancel", key=f"{conf_key}_no", use_container_width=True):
                            st.session_state.pop(conf_key, None)


def _open_pdf(pdf_bytes: bytes, title: str):
    b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    import streamlit.components.v1 as components
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


def _simple_pdf(title: str, subtitle: str, headers: List[str], rows: List[List[str]]) -> bytes:
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    elems = [Paragraph(f"<b>{title}</b>", styles["Title"]), Paragraph(subtitle, styles["Normal"]), Spacer(1, 12)]
    table = Table([headers] + rows, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    elems.append(table)
    doc.build(elems)
    data = buf.getvalue()
    buf.close()
    return data


def _delete_convoy_snapshot(kind: str, location_id: int, entry_date: date, user: Dict[str, Any]):
    model = ConvoyStatusYade if kind == "yade" else ConvoyStatusVessel
    resource_type = "ConvoyStatusYade" if kind == "yade" else "ConvoyStatusVessel"
    with get_session() as s:
        s.query(model).filter(model.location_id == location_id, model.date == entry_date).delete(synchronize_session=False)
        s.commit()
    SecurityManager.log_audit(None, user.get("username"), "DELETE", resource_type=resource_type, resource_id=f"{location_id}:{entry_date.isoformat()}", location_id=location_id, details=f"Deleted {kind.upper()} convoy snapshot for {entry_date.isoformat()}", user_id=user.get("id"))


def _request_convoy_delete(kind: str, location_id: int, entry_date: date, user: Dict[str, Any]):
    resource_type = "ConvoyStatusYade" if kind == "yade" else "ConvoyStatusVessel"
    resource_id = f"{location_id}:{entry_date.isoformat()}"
    label = f"{kind.upper()} snapshot {entry_date:%d-%b-%Y}"
    TaskManager.create_delete_request(resource_type=resource_type, resource_id=resource_id, resource_label=label, raised_by=user.get("username", "operator"), raised_by_role=(user.get("role") or "").lower(), location_id=location_id, metadata={"date": entry_date.isoformat(), "kind": kind})

