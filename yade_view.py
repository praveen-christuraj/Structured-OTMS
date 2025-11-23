# yade_view.py
from __future__ import annotations
from typing import Dict, Any, Optional, List, Tuple

import streamlit as st
import pandas as pd
from datetime import date, datetime

from sqlalchemy.orm import Session
from sqlalchemy import func

from db import get_session
from models import YadeVoyage, YadeDip, TOAYadeSummary
from security import SecurityManager

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

    # Header
    _two_col_header(
        ["Date", "Voyage No", "Convoy No", "Before NSV (bbls)", "After NSV (bbls)", "Net (bbls)", "Created by", "Action"],
        [0.13,   0.16,        0.16,        0.12,                 0.12,               0.12,        0.11,         0.08],
    )

    # Per-row edit state
    edit_id = st.session_state.get("yade_row_open")

    # Rows with filters
    for v in voyages:
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

        # Row
        cols = st.columns([0.13, 0.16, 0.16, 0.12, 0.12, 0.12, 0.11, 0.08])
        cols[0].write(str(v.date or ""))
        cols[1].write(v.voyage_no or "")
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
            pdf_btn  = c[2].button("📄", key=f"yade_pdf_{v.id}")

        # PDF
        if pdf_btn:
            pdf = build_toa_pdf_yade(v.id)
            _open_pdf_blob_inline(pdf)

        if del_btn:
            st.session_state[f"yade_del_confirm_{v.id}"] = True

        if st.session_state.get(f"yade_del_confirm_{v.id}"):
            st.error(f"Delete YADE voyage {v.voyage_no or v.id}? This cannot be undone.")
            dc1, dc2 = st.columns(2)
            if dc1.button("✅ Yes", key=f"yade_del_yes_{v.id}"):
                try:
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
                            try:
                                SecurityManager.log_audit(
                                    s, u.get("username", "unknown"), "DELETE",
                                    resource_type="YadeVoyage",
                                    resource_id=str(v.id),
                                    details=f"Moved YADE voyage {v.voyage_no or v.id} to recycle bin",
                                    user_id=u.get("id"),
                                    location_id=st.session_state.get("active_location_id"),
                                )
                            except Exception:
                                pass
                            s.commit()
                    st.success("Moved to recycle bin.")
                    st.session_state.pop(f"yade_del_confirm_{v.id}", None)
                    st.rerun()
                except Exception as ex:
                    st.error(f"Delete failed: {ex}")
            if dc2.button("✖️ No", key=f"yade_del_no_{v.id}"):
                st.session_state.pop(f"yade_del_confirm_{v.id}", None)

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
