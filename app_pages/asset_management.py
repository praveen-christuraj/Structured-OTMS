# app_pages/asset_management.py
import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO

from db import get_session
from models import (
    Location, Tank, TankStatus, CalibrationTank,
    Vessel, LocationVessel,
    Tanker, YadeBarge,
    Table11,
    TankerCalibration, YadeCalibration,
)
from security import SecurityManager
try:
    from recycle_bin import RecycleBinManager
except Exception:
    RecycleBinManager = None

# ---- optional helpers (defense-in-depth) ----
try:
    from permission_manager import PermissionManager
except Exception:
    PermissionManager = None


# ====================== generic guards & helpers ======================

def _is_admin(user) -> bool:
    role = (user or {}).get("role", "").lower()
    return role in ("admin-operations", "admin-it")

def _require_admin(user):
    if not _is_admin(user):
        st.warning("You don’t have permission to view this page.")
        return False
    return True

def _active_location(active_location_id):
    if not active_location_id:
        st.info("No active location selected. Go to **Home** and select a location.")
        return None, None
    with get_session() as session:
        loc = session.query(Location).get(active_location_id)
        if not loc:
            st.warning("Selected location was not found. Please re-select from **Home**.")
            return None, None
        return loc, f"{loc.name} ({loc.code})"

def _read_table(upload):
    """Read CSV or XLSX to DataFrame (utf-8; first sheet for xlsx)."""
    name = (upload.name or "").lower()
    if name.endswith(".csv"):
        return pd.read_csv(upload)
    if name.endswith(".xlsx"):
        return pd.read_excel(upload)
    raise ValueError("Unsupported file type. Please upload CSV or XLSX.")

def _normalize_headers(df: pd.DataFrame, aliases: dict[str, str]) -> pd.DataFrame:
    def norm_token(s: str) -> str:
        s = str(s).lower().strip()
        for ch in [" ", "_", "-", "(", ")"]:
            s = s.replace(ch, "")
        return s
    colmap = {}
    for c in df.columns:
        token = norm_token(c)
        target = aliases.get(token)
        if target:
            colmap[c] = target
    if colmap:
        df = df.rename(columns=colmap)
    return df

def _require_cols(df: pd.DataFrame, required: set):
    cols = {str(c).strip().lower() for c in df.columns}
    missing = [c for c in required if c.lower() not in cols]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

def _numeric(df: pd.DataFrame, cols):
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


# ====================== Tanks (per location) ======================

def _interpolate_volume_bbl(session, location_id: int, tank_name: str, dip_cm: float) -> float:
    """Linear interpolation on CalibrationTank for given dip_cm."""
    rows = (
        session.query(CalibrationTank)
        .filter(CalibrationTank.location_id == location_id, CalibrationTank.tank_name == tank_name)
        .order_by(CalibrationTank.dip_cm.asc())
        .all()
    )
    if not rows:
        return 0.0
    xs = [float(r.dip_cm) for r in rows]
    ys = [float(r.volume_bbl) for r in rows]
    if dip_cm <= xs[0]: return ys[0]
    if dip_cm >= xs[-1]: return ys[-1]
    import bisect
    i = bisect.bisect_left(xs, dip_cm)
    x0, x1 = xs[i-1], xs[i]
    y0, y1 = ys[i-1], ys[i]
    if x1 == x0: return y0
    return y0 + (y1 - y0) * ((dip_cm - x0) / (x1 - x0))

def _tab_tanks(active_location_id, user):
    st.subheader("🛢️ Tanks (per Location)")

    loc, loc_label = _active_location(active_location_id)
    if not loc:
        return
    st.caption(f"Active Location: **{loc_label}**")

    # ---- Create / list tanks ----
    with get_session() as session:
        tanks = session.query(Tank).filter(Tank.location_id == loc.id).order_by(Tank.name.asc()).all()

    with st.expander("➕ Add New Tank", expanded=False):
        with st.form("form_add_tank", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            with c1: t_name = st.text_input("Tank Name", max_chars=100)
            with c2: t_capacity = st.number_input("Capacity (bbl)", min_value=0.0, step=1.0)
            with c3: t_product = st.text_input("Product", value="Crude")
            with c4: status_label = st.selectbox("Status", ["ACTIVE", "INACTIVE"], index=0)
            submitted = st.form_submit_button("💾", use_container_width=True, help="Save Tank")

        if submitted:
            try:
                with get_session() as s:
                    exists = s.query(Tank).filter(Tank.location_id == loc.id, Tank.name == t_name.strip()).first()
                    if exists:
                        st.error("A tank with this name already exists at this location.")
                    else:
                        tank = Tank(
                            location_id=loc.id,
                            name=t_name.strip(),
                            capacity_bbl=float(t_capacity or 0.0),
                            product=t_product.strip() or "Crude",
                            status=TankStatus.ACTIVE if status_label == "ACTIVE" else TankStatus.INACTIVE,
                        )
                        s.add(tank); s.commit()
                        SecurityManager.log_audit(None,(user or {}).get("username","system"),"CREATE",
                            resource_type="Tank", resource_id=str(tank.id),
                            details=f"Created tank '{tank.name}' at {loc_label}",
                            user_id=(user or {}).get("id"), location_id=loc.id)
                        st.success(f"Tank **{tank.name}** added."); st.rerun()
            except Exception as ex:
                st.error(f"Failed to add tank: {ex}")

    st.markdown("#### Current Tanks")
    if not tanks:
        st.info("No tanks found for this location.")
    else:
        for t in tanks:
            with st.container(border=True):
                c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
                c1.markdown(f"**{t.name}**")
                c2.caption(f"Capacity: {t.capacity_bbl:.0f} bbl")
                c3.caption(f"Product: {t.product}")
                c4.caption(f"Status: {t.status.name}")
                with c5:
                    colA, colB = st.columns(2)
                    if colA.button("✏️", key=f"btn_edit_tank_{t.id}", help="Edit", use_container_width=False):
                        st.session_state[f"editing_tank_{t.id}"] = True
                    if colB.button("🗑️", key=f"del_tank_{t.id}", help="Delete", use_container_width=False):
                        st.session_state[f"confirm_del_tank_{t.id}"] = True

                if st.session_state.get(f"editing_tank_{t.id}"):
                    with st.form(f"form_edit_tank_{t.id}", clear_on_submit=False):
                        ec1, ec2, ec3, ec4 = st.columns(4)
                        with ec1: new_name = st.text_input("Tank Name", value=t.name, max_chars=100)
                        with ec2: new_cap = st.number_input("Capacity (bbl)", value=float(t.capacity_bbl or 0.0), step=1.0)
                        with ec3: new_prod = st.text_input("Product", value=t.product or "Crude")
                        with ec4:
                            new_status_label = st.selectbox("Status", ["ACTIVE","INACTIVE"],
                                                            index=0 if t.status == TankStatus.ACTIVE else 1)
                        saved = st.form_submit_button("💾", use_container_width=True, help="Update")
                        cancel = st.form_submit_button("❌", use_container_width=True, help="Cancel")

                    if saved:
                        try:
                            with get_session() as s:
                                obj = s.query(Tank).get(t.id)
                                obj.name = new_name.strip()
                                obj.capacity_bbl = float(new_cap or 0.0)
                                obj.product = new_prod.strip() or "Crude"
                                obj.status = TankStatus.ACTIVE if new_status_label == "ACTIVE" else TankStatus.INACTIVE
                                s.commit()
                                SecurityManager.log_audit(None,(user or {}).get("username","system"),"UPDATE",
                                    resource_type="Tank", resource_id=str(obj.id),
                                    details=f"Updated tank '{obj.name}' at {loc_label}",
                                    user_id=(user or {}).get("id"), location_id=loc.id)
                                st.success("Updated."); st.session_state.pop(f"editing_tank_{t.id}", None); st.rerun()
                        except Exception as ex:
                            st.error(f"Failed to update tank: {ex}")
                    elif cancel:
                        st.session_state.pop(f"editing_tank_{t.id}", None); st.rerun()

                if st.session_state.get(f"confirm_del_tank_{t.id}"):
                    st.error("Are you sure you want to delete this tank? This cannot be undone.")
                    dc1, dc2 = st.columns(2)
                    if dc1.button("✅ Yes, delete", key=f"y_del_tank_{t.id}", use_container_width=True):
                        try:
                            with get_session() as s:
                                obj = s.query(Tank).get(t.id)
                                if obj:
                                    if RecycleBinManager:
                                        try:
                                            RecycleBinManager.archive_record(
                                                s,
                                                obj,
                                                "Tank",
                                                username=(user or {}).get("username", "system"),
                                                user_id=(user or {}).get("id"),
                                                location_id=loc.id,
                                                reason=f"Deleted tank '{t.name}' at {loc_label}",
                                                label=str(t.id),
                                            )
                                            SecurityManager.log_audit(None,(user or {}).get("username","system"),"DELETE",
                                                resource_type="Tank", resource_id=str(t.id),
                                                details=f"Moved tank '{t.name}' to deleted records",
                                                user_id=(user or {}).get("id"), location_id=loc.id)
                                            s.commit()
                                            st.success("Tank moved to Deleted Records"); st.session_state.pop(f"confirm_del_tank_{t.id}", None); st.rerun()
                                        except Exception:
                                            s.delete(obj); s.commit()
                                            st.success("Deleted."); st.session_state.pop(f"confirm_del_tank_{t.id}", None); st.rerun()
                                    else:
                                        s.delete(obj); s.commit()
                                        st.success("Deleted."); st.session_state.pop(f"confirm_del_tank_{t.id}", None); st.rerun()
                        except Exception as ex:
                            st.error(f"Failed to delete: {ex}")
                    if dc2.button("❌ Cancel", key=f"n_del_tank_{t.id}", use_container_width=True):
                        st.session_state.pop(f"confirm_del_tank_{t.id}", None); st.rerun()

    # ---- Upload calibration (same tab) ----
    st.markdown("#### 📤 Upload Calibration (Tank)")
    with get_session() as s:
        tanks_here = s.query(Tank).filter(Tank.location_id == loc.id).order_by(Tank.name.asc()).all()
    tank_labels = [t.name for t in tanks_here]
    tank_by_name = {t.name: t for t in tanks_here}
    sel_tank = st.selectbox("Target Tank", options=tank_labels) if tank_labels else None
    st.caption("Required columns: **dip_cm, volume_bbl**. CSV/XLSX.")

    up = st.file_uploader("Select file", type=["csv","xlsx"], key="tank_cal_upl")
    df_preview = None
    if up is not None:
        try:
            df = _read_table(up)
            _require_cols(df, {"dip_cm", "volume_bbl"})
            df = _numeric(df, ["dip_cm", "volume_bbl"]).sort_values("dip_cm").reset_index(drop=True)
            st.markdown("**Preview (first 50 rows)**")
            st.dataframe(df.head(50), use_container_width=True, hide_index=True)
            df_preview = df
        except Exception as ex:
            st.error(f"Upload error: {ex}")

    if df_preview is not None and sel_tank:
        # overwrite check
        try:
            with get_session() as s:
                exist_cnt = s.query(CalibrationTank).filter(
                    CalibrationTank.location_id == loc.id,
                    CalibrationTank.tank_id == tank_by_name[sel_tank].id
                ).count()
            if exist_cnt > 0:
                st.warning(f"Existing calibration found for **{sel_tank}** ({exist_cnt} row(s)). Importing will overwrite.")
                overwrite_ok = st.checkbox(f"I confirm to overwrite calibration for {sel_tank}",
                                           key=f"tankcal_overwrite_{sel_tank}")
            else:
                st.success("No existing calibration found. A fresh set will be saved.")
                overwrite_ok = True
        except Exception as ex:
            overwrite_ok = False
            st.error(f"Can't check existing calibration: {ex}")

        if st.button("📥", key="tank_cal_import_btn", use_container_width=True, help="Import Calibration to DB"):
            if not overwrite_ok:
                st.error("Please tick the overwrite confirmation to proceed.")
            else:
                try:
                    with get_session() as s:
                        tnk = tank_by_name[sel_tank]
                        s.query(CalibrationTank).filter(
                            CalibrationTank.location_id == loc.id,
                            CalibrationTank.tank_id == tnk.id
                        ).delete()
                        s.bulk_save_objects([
                            CalibrationTank(
                                location_id=loc.id,
                                tank_id=tnk.id,
                                tank_name=tnk.name,
                                dip_cm=float(r["dip_cm"]),
                                volume_bbl=float(r["volume_bbl"])
                            ) for _, r in df_preview.iterrows()
                        ])
                        s.commit()
                        try:
                            SecurityManager.log_audit(None,(user or {}).get("username","system"),"IMPORT",
                                resource_type="CalibrationTank", resource_id=str(tnk.id),
                                details=f"Imported {len(df_preview)} rows for tank {tnk.name}",
                                user_id=(user or {}).get("id"), location_id=loc.id)
                        except Exception:
                            pass
                    st.success(f"Calibration imported for **{sel_tank}**: {len(df_preview)} rows."); st.rerun()
                except Exception as ex:
                    st.error(f"Failed to import calibration: {ex}")

    # ---- Quick lookup ----
    st.markdown("#### 🔎 Quick Volume Lookup")
    if tank_labels:
        q_tank = st.selectbox("Tank", tank_labels, key="quick_tank")
        q_dip = st.number_input("Dip (cm)", min_value=0.0, step=0.1, format="%.1f", key="quick_dip")
        if st.button("🧮", use_container_width=True, key="quick_calc_btn", help="Calculate Volume (bbl)"):
            with get_session() as s:
                vol = _interpolate_volume_bbl(s, loc.id, q_tank, float(q_dip or 0.0))
            st.success(f"Estimated Volume: **{vol:,.2f} bbl**")


# ====================== Vessels + Assign (combined) ======================

def _tab_vessels_assign(active_location_id, user):
    st.subheader("⛴️ Vessels & ⚓ Assign to Location")

    loc, loc_label = _active_location(active_location_id)
    if not loc:
        return
    st.caption(f"Active Location: **{loc_label}**")

    with get_session() as session:
        vessels = session.query(Vessel).order_by(Vessel.name.asc()).all()
        assigned = session.query(LocationVessel).filter(LocationVessel.location_id == loc.id).all()
        assigned_ids = {lv.vessel_id for lv in assigned}

    with st.expander("➕ Add New Vessel", expanded=False):
        with st.form("form_add_vessel", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            with c1: v_name = st.text_input("Vessel Name", max_chars=100)
            with c2: v_type = st.text_input("Type (e.g., MT, Barge)", max_chars=50)
            with c3: v_capacity = st.number_input("Capacity (bbl)", min_value=0.0, step=1.0)
            with c4: v_reg = st.text_input("Registration No.", max_chars=50)
            submitted_v = st.form_submit_button("💾", use_container_width=True, help="Save Vessel")

        if submitted_v:
            try:
                with get_session() as s:
                    exists = s.query(Vessel).filter(Vessel.name == v_name.strip()).first()
                    if exists:
                        st.error("A vessel with this name already exists.")
                    else:
                        v = Vessel(
                            name=v_name.strip(),
                            vessel_type=v_type.strip() or None,
                            capacity_bbl=float(v_capacity or 0.0) or None,
                            registration_no=v_reg.strip() or None,
                            status="ACTIVE",
                        )
                        s.add(v); s.commit()
                        SecurityManager.log_audit(None,(user or {}).get("username","system"),"CREATE",
                            resource_type="Vessel", resource_id=str(v.id),
                            details=f"Created vessel '{v.name}'",
                            user_id=(user or {}).get("id"))
                        st.success(f"Vessel **{v.name}** added."); st.rerun()
            except Exception as ex:
                st.error(f"Failed to add vessel: {ex}")

    st.markdown("#### Current Vessels")
    if not vessels:
        st.info("No vessels found.")
    else:
        for v in vessels:
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
                c1.markdown(f"**{v.name}**")
                c2.caption(f"Type: {v.vessel_type or '-'}")
                c3.caption(f"Capacity: {int(v.capacity_bbl or 0)} bbl")
                with c4:
                    colA, colB = st.columns(2)
                    if colA.button("✏️", key=f"btn_edit_vessel_{v.id}", help="Edit", use_container_width=False):
                        st.session_state[f"editing_vessel_{v.id}"] = True
                    if colB.button("🗑️", key=f"del_vessel_{v.id}", help="Delete", use_container_width=False):
                        st.session_state[f"confirm_del_vessel_{v.id}"] = True

                if st.session_state.get(f"editing_vessel_{v.id}"):
                    with st.form(f"form_edit_vessel_{v.id}", clear_on_submit=False):
                        ec1, ec2, ec3, ec4 = st.columns(4)
                        with ec1: new_name = st.text_input("Vessel Name", value=v.name, max_chars=100)
                        with ec2: new_type = st.text_input("Type", value=v.vessel_type or "", max_chars=50)
                        with ec3: new_cap = st.number_input("Capacity (bbl)", value=float(v.capacity_bbl or 0.0), step=1.0)
                        with ec4: new_reg = st.text_input("Registration No.", value=v.registration_no or "", max_chars=50)
                        saved = st.form_submit_button("💾", use_container_width=True, help="Update")
                        cancel = st.form_submit_button("❌", use_container_width=True, help="Cancel")

                    if saved:
                        try:
                            with get_session() as s:
                                obj = s.query(Vessel).get(v.id)
                                obj.name = new_name.strip()
                                obj.vessel_type = new_type.strip() or None
                                obj.capacity_bbl = float(new_cap or 0.0) or None
                                obj.registration_no = new_reg.strip() or None
                                s.commit()
                                SecurityManager.log_audit(None,(user or {}).get("username","system"),"UPDATE",
                                    resource_type="Vessel", resource_id=str(obj.id),
                                    details=f"Updated vessel '{obj.name}'",
                                    user_id=(user or {}).get("id"))
                                st.success("Updated."); st.session_state.pop(f"editing_vessel_{v.id}", None); st.rerun()
                        except Exception as ex:
                            st.error(f"Failed to update vessel: {ex}")
                    elif cancel:
                        st.session_state.pop(f"editing_vessel_{v.id}", None); st.rerun()

                if st.session_state.get(f"confirm_del_vessel_{v.id}"):
                    st.error("Are you sure you want to delete this vessel? This cannot be undone.")
                    dc1, dc2 = st.columns(2)
                    if dc1.button("✅ Yes, delete", key=f"y_del_vessel_{v.id}", use_container_width=True):
                        try:
                            with get_session() as s:
                                obj = s.query(Vessel).get(v.id)
                                if obj:
                                    if RecycleBinManager:
                                        try:
                                            RecycleBinManager.archive_record(
                                                s,
                                                obj,
                                                "Vessel",
                                                username=(user or {}).get("username", "system"),
                                                user_id=(user or {}).get("id"),
                                                location_id=loc.id,
                                                reason=f"Deleted vessel '{v.name}'",
                                                label=str(v.id),
                                            )
                                            SecurityManager.log_audit(None,(user or {}).get("username","system"),"DELETE",
                                                resource_type="Vessel", resource_id=str(v.id),
                                                details=f"Moved vessel '{v.name}' to deleted records",
                                                user_id=(user or {}).get("id"))
                                            s.commit()
                                            st.success("Vessel moved to Deleted Records"); st.session_state.pop(f"confirm_del_vessel_{v.id}", None); st.rerun()
                                        except Exception:
                                            s.delete(obj); s.commit()
                                            st.success("Deleted."); st.session_state.pop(f"confirm_del_vessel_{v.id}", None); st.rerun()
                                    else:
                                        s.delete(obj); s.commit()
                                        st.success("Deleted."); st.session_state.pop(f"confirm_del_vessel_{v.id}", None); st.rerun()
                        except Exception as ex:
                            st.error(f"Failed to delete: {ex}")
                    if dc2.button("❌ Cancel", key=f"n_del_vessel_{v.id}", use_container_width=True):
                        st.session_state.pop(f"confirm_del_vessel_{v.id}", None); st.rerun()

    # Assign to this location
    names = [v.name for v in vessels]; by_name = {v.name: v for v in vessels}
    selected = st.multiselect("Assign vessels to this location", names,
                              default=[v.name for v in vessels if v.id in assigned_ids])
    target_ids = {by_name[n].id for n in selected}

    if st.button("💾", use_container_width=True, help="Save Assignments"):
        try:
            with get_session() as s:
                # add new
                for v in vessels:
                    if v.id in target_ids and v.id not in assigned_ids:
                        s.add(LocationVessel(location_id=loc.id, vessel_id=v.id, is_active=True))
                # remove unselected
                for v in vessels:
                    if v.id in assigned_ids and v.id not in target_ids:
                        s.query(LocationVessel).filter(
                            LocationVessel.location_id == loc.id,
                            LocationVessel.vessel_id == v.id
                        ).delete()
                s.commit()
                SecurityManager.log_audit(None,(user or {}).get("username","system"),"UPDATE",
                    resource_type="LocationVessel", resource_id=str(loc.id),
                    details=f"Updated vessel assignments for {loc_label}: {sorted(list(target_ids))}",
                    user_id=(user or {}).get("id"), location_id=loc.id)
                st.success("Assignments saved."); st.rerun()
        except Exception as ex:
            st.error(f"Failed to save assignments: {ex}")

    st.markdown("#### Currently Assigned")
    if not assigned_ids:
        st.info("No vessels assigned to this location.")
    else:
        st.write(", ".join([n for n in names if by_name[n].id in assigned_ids]))


def _tab_fso_assign(active_location_id, user):
    st.subheader("⚓ FSO & Assign to Location")

    loc, loc_label = _active_location(active_location_id)
    if not loc:
        return
    st.caption(f"Active Location: **{loc_label}**")

    with get_session() as session:
        vessels = session.query(Vessel).filter((Vessel.vessel_type == "FSO") | (Vessel.vessel_type == None)).order_by(Vessel.name.asc()).all()
        assigned = session.query(LocationVessel).filter(LocationVessel.location_id == loc.id).all()
        assigned_ids = {lv.vessel_id for lv in assigned if getattr(lv.vessel, "vessel_type", None) == "FSO"}

    with st.expander("➕ Add New FSO", expanded=False):
        with st.form("form_add_fso", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            with c1: v_name = st.text_input("FSO Name", max_chars=100)
            with c2: v_capacity = st.number_input("Capacity (bbl)", min_value=0.0, step=1.0)
            with c3: v_reg = st.text_input("Registration No.", max_chars=50)
            with c4: status_label = st.selectbox("Status", ["ACTIVE", "INACTIVE"], index=0)
            submitted_v = st.form_submit_button("💾", use_container_width=True, help="Save FSO")

        if submitted_v:
            try:
                with get_session() as s:
                    exists = s.query(Vessel).filter(Vessel.name == v_name.strip()).first()
                    if exists:
                        st.error("A vessel with this name already exists.")
                    else:
                        v = Vessel(
                            name=v_name.strip(),
                            vessel_type="FSO",
                            capacity_bbl=float(v_capacity or 0.0) or None,
                            registration_no=v_reg.strip() or None,
                            status=status_label,
                        )
                        s.add(v); s.commit()
                        SecurityManager.log_audit(None,(user or {}).get("username","system"),"CREATE",
                            resource_type="Vessel", resource_id=str(v.id),
                            details=f"Created FSO '{v.name}'",
                            user_id=(user or {}).get("id"))
                        st.success(f"FSO **{v.name}** added."); st.rerun()
            except Exception as ex:
                st.error(f"Failed to add FSO: {ex}")

    st.markdown("#### Current FSOs")
    fsos = [v for v in vessels if (v.vessel_type or "").upper() == "FSO"]
    if not fsos:
        st.info("No FSOs found.")
    else:
        for v in fsos:
            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 1, 1])
                c1.markdown(f"**{v.name}**")
                c2.caption(f"Capacity: {int(v.capacity_bbl or 0)} bbl")
                with c3:
                    colA, colB = st.columns(2)
                    if colA.button("✏️", key=f"btn_edit_fso_{v.id}", help="Edit", use_container_width=False):
                        st.session_state[f"editing_fso_{v.id}"] = True
                    if colB.button("🗑️", key=f"del_fso_{v.id}", help="Delete", use_container_width=False):
                        st.session_state[f"confirm_del_fso_{v.id}"] = True

                if st.session_state.get(f"editing_fso_{v.id}"):
                    with st.form(f"form_edit_fso_{v.id}", clear_on_submit=False):
                        ec1, ec2, ec3, ec4 = st.columns(4)
                        with ec1: new_name = st.text_input("FSO Name", value=v.name, max_chars=100)
                        with ec2: new_cap = st.number_input("Capacity (bbl)", value=float(v.capacity_bbl or 0.0), step=1.0)
                        with ec3: new_reg = st.text_input("Registration No.", value=v.registration_no or "", max_chars=50)
                        with ec4:
                            new_status_label = st.selectbox("Status", ["ACTIVE","INACTIVE"], index=0 if (v.status or "ACTIVE") == "ACTIVE" else 1)
                        saved = st.form_submit_button("💾", use_container_width=True, help="Update")
                        cancel = st.form_submit_button("❌", use_container_width=True, help="Cancel")

                    if saved:
                        try:
                            with get_session() as s:
                                obj = s.query(Vessel).get(v.id)
                                obj.name = new_name.strip()
                                obj.capacity_bbl = float(new_cap or 0.0) or None
                                obj.registration_no = new_reg.strip() or None
                                obj.vessel_type = "FSO"
                                obj.status = new_status_label
                                s.commit()
                                SecurityManager.log_audit(None,(user or {}).get("username","system"),"UPDATE",
                                    resource_type="Vessel", resource_id=str(obj.id),
                                    details=f"Updated FSO '{obj.name}'",
                                    user_id=(user or {}).get("id"))
                                st.success("Updated."); st.session_state.pop(f"editing_fso_{v.id}", None); st.rerun()
                        except Exception as ex:
                            st.error(f"Failed to update FSO: {ex}")
                    elif cancel:
                        st.session_state.pop(f"editing_fso_{v.id}", None); st.rerun()

                if st.session_state.get(f"confirm_del_fso_{v.id}"):
                    st.error("Are you sure you want to delete this FSO? This cannot be undone.")
                    dc1, dc2 = st.columns(2)
                    if dc1.button("✅ Yes, delete", key=f"y_del_fso_{v.id}", use_container_width=True):
                        try:
                            with get_session() as s:
                                obj = s.query(Vessel).get(v.id)
                                if obj:
                                    s.delete(obj); s.commit()
                                    SecurityManager.log_audit(None,(user or {}).get("username","system"),"DELETE",
                                        resource_type="Vessel", resource_id=str(v.id),
                                        details=f"Deleted FSO '{v.name}'",
                                        user_id=(user or {}).get("id"))
                                    st.success("Deleted."); st.session_state.pop(f"confirm_del_fso_{v.id}", None); st.rerun()
                        except Exception as ex:
                            st.error(f"Failed to delete: {ex}")
                    if dc2.button("❌ Cancel", key=f"n_del_fso_{v.id}", use_container_width=True):
                        st.session_state.pop(f"confirm_del_fso_{v.id}", None); st.rerun()

    names = [v.name for v in fsos]; by_name = {v.name: v for v in fsos}
    selected = st.multiselect("Assign FSOs to this location", names,
                              default=[v.name for v in fsos if v.id in assigned_ids]) if names else []
    target_ids = {by_name[n].id for n in selected} if selected else set()

    if st.button("💾", use_container_width=True, help="Save FSO Assignments"):
        try:
            with get_session() as s:
                for v in fsos:
                    if v.id in target_ids and v.id not in assigned_ids:
                        s.add(LocationVessel(location_id=loc.id, vessel_id=v.id, is_active=True))
                for v in fsos:
                    if v.id in assigned_ids and v.id not in target_ids:
                        s.query(LocationVessel).filter(
                            LocationVessel.location_id == loc.id,
                            LocationVessel.vessel_id == v.id
                        ).delete()
                s.commit()
                SecurityManager.log_audit(None,(user or {}).get("username","system"),"UPDATE",
                    resource_type="LocationVessel", resource_id=str(loc.id),
                    details=f"Updated FSO assignments for {loc_label}: {sorted(list(target_ids))}",
                    user_id=(user or {}).get("id"), location_id=loc.id)
                st.success("FSO assignments saved."); st.rerun()
        except Exception as ex:
            st.error(f"Failed to save FSO assignments: {ex}")

    st.markdown("#### Currently Assigned FSOs")
    if not assigned_ids:
        st.info("No FSOs assigned to this location.")
    else:
        st.write(", ".join([n for n in names if by_name.get(n) and by_name[n].id in assigned_ids]))


# ====================== Tankers (master + calibration) ======================

def _tab_tankers(user):
    st.subheader("🚚 Tankers")

    with get_session() as session:
        tankers = session.query(Tanker).order_by(Tanker.name.asc()).all()

    # Add tanker
    with st.expander("➕ Add New Tanker", expanded=False):
        with st.form("form_add_tanker", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            with c1: t_name = st.text_input("Tanker ID / Name", max_chars=100)
            with c2: t_reg = st.text_input("Chassis No.", max_chars=50)  # <-- label updated
            with c3: t_cap = st.number_input("Capacity (litres)", min_value=0.0, step=100.0)
            with c4: t_status = st.selectbox("Status", ["ACTIVE", "INACTIVE"], index=0)
            st.caption("Optionally upload initial calibration chart for this tanker (CSV/XLSX)")
            up_new_cal = st.file_uploader("Calibration file (optional)", type=["csv","xlsx"], key="tanker_cal_new")
            submitted = st.form_submit_button("💾", use_container_width=True, help="Save Tanker")

        if submitted:
            try:
                with get_session() as s:
                    exists = s.query(Tanker).filter(Tanker.name == t_name.strip()).first()
                    if exists:
                        st.error("A tanker with this name already exists.")
                    else:
                        tk = Tanker(
                            name=t_name.strip(),
                            registration_no=t_reg.strip() or None,   # DB field remains the same
                            capacity_litres=float(t_cap or 0.0) or None,
                            status=TankStatus.ACTIVE if t_status == "ACTIVE" else TankStatus.INACTIVE,
                        )
                        s.add(tk); s.commit()
                        if up_new_cal is not None:
                            try:
                                df_new = _read_table(up_new_cal)
                                df_new = _normalize_headers(df_new, {
                                    "tankerid": "tanker_id",
                                    "chassisno": "chassis_no",
                                    "dipmm": "dip_mm",
                                    "volumelitres": "volume_litres",
                                    "volumelitre": "volume_litres",
                                    "volume": "volume_litres",
                                    "compartment": "compartment",
                                })
                                df_new.columns = [str(c).strip().lower() for c in df_new.columns]
                                _require_cols(df_new, {"tanker_id", "chassis_no", "dip_mm", "volume_litres"})
                                df_new["tanker_id"] = df_new["tanker_id"].astype(str).str.strip()
                                df_new["chassis_no"] = df_new["chassis_no"].astype(str).str.strip()
                                df_new = _numeric(df_new, ["dip_mm", "volume_litres"]).dropna(subset=["chassis_no","dip_mm","volume_litres"])
                                s.query(TankerCalibration).filter(
                                    TankerCalibration.tanker_id == int(tk.id),
                                    TankerCalibration.chassis_no.in_(sorted(set(df_new["chassis_no"].tolist())))
                                ).delete(synchronize_session=False)
                                objs = []
                                has_comp = "compartment" in df_new.columns
                                for _, r in df_new.iterrows():
                                    objs.append(TankerCalibration(
                                        tanker_id=int(tk.id),
                                        chassis_no=str(r["chassis_no"]),
                                        dip_mm=float(r["dip_mm"]),
                                        volume_litres=float(r["volume_litres"]),
                                        tanker_name=str(tk.name),
                                        compartment=(str(r["compartment"]).strip().upper() if has_comp and pd.notna(r.get("compartment")) else "C1")
                                    ))
                                if objs:
                                    s.bulk_save_objects(objs)
                                    s.commit()
                                    try:
                                        SecurityManager.log_audit(None,(user or {}).get("username","system"),"IMPORT",
                                            resource_type="TankerCalibration", resource_id=str(tk.id),
                                            details=f"Imported {len(objs)} calibration rows for tanker '{tk.name}'",
                                            user_id=(user or {}).get("id"))
                                    except Exception:
                                        pass
                            except Exception as ex:
                                st.warning(f"Calibration import failed: {ex}")
                        SecurityManager.log_audit(None,(user or {}).get("username","system"),"CREATE",
                            resource_type="Tanker", resource_id=str(tk.id),
                            details=f"Created tanker '{tk.name}'",
                            user_id=(user or {}).get("id"))
                        st.success(f"Tanker **{tk.name}** added."); st.rerun()
            except Exception as ex:
                st.error(f"Failed to add tanker: {ex}")

    # List tankers
    st.markdown("#### Current Tankers")
    if not tankers:
        st.info("No tankers found.")
    else:
        for tk in tankers:
            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 2, 1])
                c1.markdown(f"**{tk.name}**")
                c2.caption(f"Chassis: {tk.registration_no or '-'} | Capacity: {int(tk.capacity_litres or 0)} L")  # <-- caption updated
                with c3:
                    colA, colB = st.columns(2)
                    if colA.button("✏️", key=f"btn_edit_tanker_{tk.id}", help="Edit", use_container_width=False):
                        st.session_state[f"editing_tanker_{tk.id}"] = True
                    if colB.button("🗑️", key=f"del_tanker_{tk.id}", help="Delete", use_container_width=False):
                        st.session_state[f"confirm_del_tanker_{tk.id}"] = True

                if st.session_state.get(f"editing_tanker_{tk.id}"):
                    with st.form(f"form_edit_tanker_{tk.id}", clear_on_submit=False):
                        ec1, ec2, ec3, ec4 = st.columns(4)
                        with ec1: new_name = st.text_input("Tanker Name", value=tk.name, max_chars=100)
                        with ec2: new_reg = st.text_input("Chassis No.", value=tk.registration_no or "", max_chars=50)  # <-- label updated
                        with ec3: new_cap = st.number_input("Capacity (litres)", value=float(tk.capacity_litres or 0.0), step=100.0)
                        with ec4:
                            new_status = st.selectbox("Status", ["ACTIVE", "INACTIVE"],
                                                      index=0 if tk.status == TankStatus.ACTIVE else 1)
                        saved = st.form_submit_button("💾", use_container_width=True, help="Update")
                        cancel = st.form_submit_button("❌", use_container_width=True, help="Cancel")

                    if saved:
                        try:
                            with get_session() as s:
                                obj = s.query(Tanker).get(tk.id)
                                obj.name = new_name.strip()
                                obj.registration_no = new_reg.strip() or None   # still stored in registration_no
                                obj.capacity_litres = float(new_cap or 0.0) or None
                                obj.status = TankStatus.ACTIVE if new_status == "ACTIVE" else TankStatus.INACTIVE
                                s.commit()
                                SecurityManager.log_audit(None,(user or {}).get("username","system"),"UPDATE",
                                    resource_type="Tanker", resource_id=str(obj.id),
                                    details=f"Updated tanker '{obj.name}'",
                                    user_id=(user or {}).get("id"))
                                st.success("Updated."); st.session_state.pop(f"editing_tanker_{tk.id}", None); st.rerun()
                        except Exception as ex:
                            st.error(f"Failed to update tanker: {ex}")
                    elif cancel:
                        st.session_state.pop(f"editing_tanker_{tk.id}", None); st.rerun()

                if st.session_state.get(f"confirm_del_tanker_{tk.id}"):
                    st.error("Are you sure you want to delete this tanker? This cannot be undone.")
                    dc1, dc2 = st.columns(2)
                    if dc1.button("✅ Yes, delete", key=f"y_del_tanker_{tk.id}", use_container_width=True):
                        try:
                            with get_session() as s:
                                obj = s.query(Tanker).get(tk.id)
                                if obj:
                                    s.delete(obj); s.commit()
                                    SecurityManager.log_audit(None,(user or {}).get("username","system"),"DELETE",
                                        resource_type="Tanker", resource_id=str(tk.id),
                                        details=f"Deleted tanker '{tk.name}'",
                                        user_id=(user or {}).get("id"))
                                    st.success("Deleted."); st.session_state.pop(f"confirm_del_tanker_{tk.id}", None); st.rerun()
                        except Exception as ex:
                            st.error(f"Failed to delete: {ex}")
                    if dc2.button("❌ Cancel", key=f"n_del_tanker_{tk.id}", use_container_width=True):
                        st.session_state.pop(f"confirm_del_tanker_{tk.id}", None); st.rerun()

    # ---- Upload Tanker Calibration (same tab) ----
    st.markdown("#### 📤 Upload Tanker Calibration")
    st.caption("Required columns: **tanker_id, chassis_no, dip_mm, volume_litres**. CSV/XLSX.")
    up_tc = st.file_uploader("Select file", type=["csv","xlsx"], key="tanker_cal_upl")
    df_tc = None
    if up_tc is not None:
        try:
            df_tc = _read_table(up_tc)
            df_tc = _normalize_headers(df_tc, {
                "tankerid": "tanker_id",
                "chassisno": "chassis_no",
                "dipmm": "dip_mm",
                "volumelitres": "volume_litres",
                "volumelitre": "volume_litres",
                "volume": "volume_litres",
                "compartment": "compartment",
            })
            df_tc.columns = [str(c).strip().lower() for c in df_tc.columns]
            _require_cols(df_tc, {"tanker_id", "chassis_no", "dip_mm", "volume_litres"})
            df_tc["tanker_id"] = df_tc["tanker_id"].astype(str).str.strip()
            df_tc["chassis_no"] = df_tc["chassis_no"].astype(str).str.strip()
            df_tc = _numeric(df_tc, ["dip_mm", "volume_litres"]).dropna(subset=["chassis_no","dip_mm","volume_litres"])
            df_tc = df_tc.sort_values("dip_mm").reset_index(drop=True)
            with st.expander("Preview (first 30 rows)", expanded=True):
                st.dataframe(df_tc.head(30), use_container_width=True, hide_index=True)
        except Exception as ex:
            st.error(f"Upload error: {ex}")

    if df_tc is not None:
        # overwrite check
        try:
            with get_session() as s:
                t_all = s.query(Tanker).all()
                id_by_name = {t.name.strip(): int(t.id) for t in t_all}
                resolved_ids = sorted({id_by_name.get(str(x).strip(), None) for x in df_tc["tanker_id"].dropna().tolist()})
                resolved_ids = [i for i in resolved_ids if i is not None]
                chassis_set = sorted(set(df_tc["chassis_no"].dropna().tolist()))
                existing = 0
                if resolved_ids and chassis_set:
                    existing = s.query(TankerCalibration).filter(
                        TankerCalibration.tanker_id.in_(resolved_ids),
                        TankerCalibration.chassis_no.in_(chassis_set)
                    ).count()
            if existing > 0:
                st.warning("Existing calibration found for some (tanker_id, chassis_no) pairs. Importing will overwrite.")
                tc_over_ok = st.checkbox("I confirm to overwrite the existing tanker calibration", key="tanker_over_ck")
            else:
                st.success("No existing calibration found. A fresh set will be saved.")
                tc_over_ok = True
        except Exception as ex:
            tc_over_ok = False
            st.error(f"Can't check existing tanker calibration: {ex}")

        if st.button("📥", key="tanker_cal_import_btn", use_container_width=True, help="Import Tanker Calibration to DB"):
            if not tc_over_ok:
                st.error("Please tick the overwrite confirmation to proceed.")
            else:
                try:
                    with get_session() as s:
                        pairs = sorted(set(df_tc[["tanker_id","chassis_no"]].dropna().itertuples(index=False, name=None)))
                        t_all = s.query(Tanker).all()
                        id_by_name = {t.name.strip(): int(t.id) for t in t_all}
                        name_by_id = {int(t.id): t.name for t in t_all}
                        for tid_str, ch in pairs:
                            tid = id_by_name.get(str(tid_str).strip(), None)
                            if tid is not None:
                                s.query(TankerCalibration).filter(
                                    TankerCalibration.tanker_id == int(tid),
                                    TankerCalibration.chassis_no == str(ch)
                                ).delete(synchronize_session=False)
                        objs = []
                        has_comp = "compartment" in df_tc.columns
                        for _, r in df_tc.iterrows():
                            tid = id_by_name.get(str(r["tanker_id"]).strip(), None)
                            objs.append(TankerCalibration(
                                tanker_id=(int(tid) if tid is not None else None),
                                chassis_no=str(r["chassis_no"]),
                                dip_mm=float(r["dip_mm"]),
                                volume_litres=float(r["volume_litres"]),
                                tanker_name=(name_by_id.get(int(tid)) if tid is not None else str(r["tanker_id"]).strip()),
                                compartment=(str(r["compartment"]).strip().upper() if has_comp and pd.notna(r.get("compartment")) else "C1")
                            ))
                        s.bulk_save_objects(objs)
                        s.commit()
                        try:
                            SecurityManager.log_audit(None,(user or {}).get("username","system"),"IMPORT",
                                resource_type="TankerCalibration", resource_id="batch",
                                details=f"Imported {len(df_tc)} tanker calibration rows",
                                user_id=(user or {}).get("id"))
                        except Exception:
                            pass
                    st.success(f"Tanker calibration imported: {len(df_tc)} rows."); st.rerun()
                except Exception as ex:
                    st.error(f"Failed to import tanker calibration: {ex}")


# ====================== YADE Barges (master + calibration) ======================

def _tab_yade_barges(user):
    st.subheader("🛶 YADE Barges")

    with get_session() as session:
        barges = session.query(YadeBarge).order_by(YadeBarge.name.asc()).all()

    # Add YADE barge
    with st.expander("➕ Add New YADE Barge", expanded=False):
        with st.form("form_add_barge", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1: b_name = st.text_input("Barge Name", max_chars=100)
            with c2: b_design = st.selectbox("Design", ["6", "4"], index=0)
            submitted = st.form_submit_button("💾", use_container_width=True, help="Save Barge")

        if submitted:
            try:
                with get_session() as s:
                    exists = s.query(YadeBarge).filter(YadeBarge.name == b_name.strip()).first()
                    if exists:
                        st.error("A barge with this name already exists.")
                    else:
                        b = YadeBarge(name=b_name.strip(), design=b_design)
                        s.add(b); s.commit()
                        SecurityManager.log_audit(None,(user or {}).get("username","system"),"CREATE",
                            resource_type="YadeBarge", resource_id=str(b.id),
                            details=f"Created YADE barge '{b.name}'",
                            user_id=(user or {}).get("id"))
                        st.success(f"Barge **{b.name}** added."); st.rerun()
            except Exception as ex:
                st.error(f"Failed to add barge: {ex}")

    # List
    st.markdown("#### Current YADE Barges")
    if not barges:
        st.info("No YADE barges found.")
    else:
        st.markdown(
            """
            <style>
            .stButton>button { padding: 4px 8px; height: 28px; }
            div[data-testid="stHorizontalBlock"] { gap: 0.25rem; }
            </style>
            """,
            unsafe_allow_html=True,
        )
        for b in barges:
            with st.container(border=True):
                c1, c2, c3 = st.columns([6, 3, 1])
                c1.markdown(f"**{b.name}**")
                c2.caption(f"Design: {b.design}")
                with c3:
                    colA, colB = st.columns(2)
                    if colA.button("✏️", key=f"btn_edit_barge_{b.id}", help="Edit", use_container_width=False):
                        st.session_state[f"editing_barge_{b.id}"] = True
                    if colB.button("🗑️", key=f"del_barge_{b.id}", help="Delete", use_container_width=False):
                        st.session_state[f"confirm_del_barge_{b.id}"] = True

                if st.session_state.get(f"editing_barge_{b.id}"):
                    with st.form(f"form_edit_barge_{b.id}", clear_on_submit=False):
                        ec1, ec2 = st.columns(2)
                        with ec1: new_name = st.text_input("Barge Name", value=b.name, max_chars=100)
                        with ec2: new_design = st.selectbox("Design", ["6","4"], index=0 if b.design == "6" else 1)
                        saved = st.form_submit_button("💾", use_container_width=True, help="Update")
                        cancel = st.form_submit_button("❌", use_container_width=True, help="Cancel")

                    if saved:
                        try:
                            with get_session() as s:
                                obj = s.query(YadeBarge).get(b.id)
                                obj.name = new_name.strip()
                                obj.design = new_design
                                s.commit()
                                SecurityManager.log_audit(None,(user or {}).get("username","system"),"UPDATE",
                                    resource_type="YadeBarge", resource_id=str(obj.id),
                                    details=f"Updated YADE barge '{obj.name}'",
                                    user_id=(user or {}).get("id"))
                                st.success("Updated."); st.session_state.pop(f"editing_barge_{b.id}", None); st.rerun()
                        except Exception as ex:
                            st.error(f"Failed to update barge: {ex}")
                    elif cancel:
                        st.session_state.pop(f"editing_barge_{b.id}", None); st.rerun()

                if st.session_state.get(f"confirm_del_barge_{b.id}"):
                    st.error("Are you sure you want to delete this barge? This cannot be undone.")
                    dc1, dc2 = st.columns(2)
                    if dc1.button("✅ Yes, delete", key=f"y_del_barge_{b.id}", use_container_width=True):
                        try:
                            with get_session() as s:
                                obj = s.query(YadeBarge).get(b.id)
                                if obj:
                                    s.delete(obj); s.commit()
                                    SecurityManager.log_audit(None,(user or {}).get("username","system"),"DELETE",
                                        resource_type="YadeBarge", resource_id=str(b.id),
                                        details=f"Deleted YADE barge '{b.name}'",
                                        user_id=(user or {}).get("id"))
                                    st.success("Deleted."); st.session_state.pop(f"confirm_del_barge_{b.id}", None); st.rerun()
                        except Exception as ex:
                            st.error(f"Failed to delete: {ex}")
                    if dc2.button("❌ Cancel", key=f"n_del_barge_{b.id}", use_container_width=True):
                        st.session_state.pop(f"confirm_del_barge_{b.id}", None); st.rerun()

    # ---- Upload YADE Calibration (same tab) ----
    st.markdown("#### 📤 Upload YADE Calibration")
    with get_session() as s:
        yade_names = [y.name for y in s.query(YadeBarge).order_by(YadeBarge.name.asc()).all()]
    sel_yade = st.selectbox("YADE Name", options=yade_names) if yade_names else None
    st.caption("Required columns: **yade_name, tank_id, dip_mm, vol_bbl** (+ optional **mm1..mm9**). CSV/XLSX.")

    up_y = st.file_uploader("Select file", type=["csv","xlsx"], key="yade_cal_upl")
    dfy = None
    if up_y is not None:
        try:
            dfy = _read_table(up_y)
            # normalize
            dfy.columns = [str(c).strip().lower() for c in dfy.columns]
            _require_cols(dfy, {"yade_name", "tank_id", "dip_mm", "vol_bbl"})
            dfy["yade_name"] = dfy["yade_name"].astype(str).str.strip()
            dfy["tank_id"] = dfy["tank_id"].astype(str).str.upper().str.strip()
            if sel_yade:  # force to selected yade if chosen
                dfy["yade_name"] = sel_yade
            num_cols = ["dip_mm", "vol_bbl"] + [c for c in dfy.columns if c.startswith("mm")]
            dfy = _numeric(dfy, num_cols).dropna(subset=["dip_mm", "vol_bbl"])
            dfy = dfy.sort_values(["yade_name", "tank_id", "dip_mm"]).reset_index(drop=True)
            with st.expander("Preview (first 60 rows)", expanded=True):
                st.dataframe(dfy.head(60), use_container_width=True, hide_index=True)
        except Exception as ex:
            st.error(f"Upload error: {ex}")

    if dfy is not None:
        affected_yades = sorted(dfy["yade_name"].unique().tolist())
        pairs = sorted(dfy[["yade_name","tank_id"]].drop_duplicates().itertuples(index=False, name=None))
        st.info("**Will import calibration for:** " + ", ".join(affected_yades))
        st.caption("Pairs (YADE, Tank): " + ", ".join([f"({yn},{tk})" for yn, tk in pairs]))

        try:
            with get_session() as s:
                existing_rows = (
                    s.query(YadeCalibration.yade_name, YadeCalibration.tank_id)
                    .filter(YadeCalibration.yade_name.in_(affected_yades))
                    .all()
                )
            if existing_rows:
                existing_set = sorted(set(existing_rows))
                st.warning("Existing calibration found for pairs (will be overwritten): " +
                           ", ".join([f"({yn},{tk})" for yn, tk in existing_set]))
                y_over_ok = st.checkbox("I confirm to overwrite the existing YADE calibration", key="yade_over_ck")
            else:
                st.success("No existing calibration found. A fresh set will be saved.")
                y_over_ok = True
        except Exception as ex:
            y_over_ok = False
            st.error(f"Can't check existing YADE calibration: {ex}")

        if st.button("📥", key="yade_cal_import_btn", use_container_width=True, help="Import YADE Calibration to DB"):
            if not y_over_ok:
                st.error("Please tick the overwrite confirmation to proceed.")
            else:
                try:
                    with get_session() as s:
                        s.query(YadeCalibration).filter(YadeCalibration.yade_name.in_(affected_yades)).delete(synchronize_session=False)
                        objs = []
                        mm_cols = [c for c in ["mm1","mm2","mm3","mm4","mm5","mm6","mm7","mm8","mm9"] if c in dfy.columns]
                        for _, r in dfy.iterrows():
                            kwargs = dict(
                                yade_name=r["yade_name"],
                                tank_id=r["tank_id"],
                                dip_mm=float(r["dip_mm"]),
                                vol_bbl=float(r["vol_bbl"]),
                            )
                            for mcol in mm_cols:
                                val = r.get(mcol, None)
                                kwargs[mcol] = float(val) if pd.notna(val) else None
                            objs.append(YadeCalibration(**kwargs))
                        s.bulk_save_objects(objs); s.commit()
                        try:
                            SecurityManager.log_audit(None,(user or {}).get("username","system"),"IMPORT",
                                resource_type="YadeCalibration", resource_id="batch",
                                details=f"Imported YADE calibration rows: {len(objs)}",
                                user_id=(user or {}).get("id"))
                        except Exception:
                            pass
                    st.success(f"YADE calibration imported: {len(objs)} rows."); st.rerun()
                except Exception as ex:
                    st.error(f"Failed to import YADE calibration: {ex}")


# ====================== ASTM Table 11 (import) ======================

def _normalize_table11(df: pd.DataFrame) -> pd.DataFrame:
    """Detect API@60 and LT factor columns with flexible headers."""
    colmap = {}
    for c in df.columns:
        c_norm = str(c).strip().lower().replace(" ", "").replace("_", "")
        if c_norm in {"api60","apiat60f","api@60f","api@60","api60f","api"}:
            colmap[c] = "api60"
        if c_norm in {"ltf","ltfactor","lt","factor","lt_fact"}:
            colmap[c] = "lt_factor"
    if "api60" not in colmap.values() or "lt_factor" not in colmap.values():
        raise ValueError("Could not detect both required columns: API @ 60°F and LT factor.")
    df2 = df.rename(columns=colmap)[["api60","lt_factor"]].copy()
    df2["api60"] = pd.to_numeric(df2["api60"], errors="coerce")
    df2["lt_factor"] = pd.to_numeric(df2["lt_factor"], errors="coerce")
    df2 = df2.dropna(subset=["api60","lt_factor"])
    return df2.sort_values("api60").reset_index(drop=True)

def _tab_astm_table11(user):
    st.subheader("📚 ASTM Table 11 — Import (.xlsx)")
    up = st.file_uploader("Select ASTM Table 11 (.xlsx only)", type=["xlsx"], key="astm11_upl")

    df11_preview = None
    if up is not None:
        try:
            df11 = pd.read_excel(up)
            df11 = _normalize_table11(df11)
            st.markdown("**Preview (first 100 rows)**")
            st.dataframe(df11.head(100), use_container_width=True, hide_index=True)
            df11_preview = df11
        except Exception as ex:
            st.error(f"Upload error: {ex}")

    if df11_preview is not None:
        try:
            with get_session() as s:
                existing = s.query(Table11).count()
            if existing > 0:
                st.warning(f"Existing ASTM Table 11 has **{existing}** row(s). Importing will overwrite.")
                astm_overwrite_ok = st.checkbox("I confirm to overwrite ASTM Table 11", key="astm11_overwrite_ck")
            else:
                st.success("No existing ASTM Table 11 found. A fresh dataset will be saved.")
                astm_overwrite_ok = True
        except Exception as ex:
            st.error(f"Can't check existing ASTM Table 11: {ex}")
            astm_overwrite_ok = False

        if st.button("📥", key="astm11_import_btn", use_container_width=True, help="Import ASTM Table 11 to DB"):
            if not astm_overwrite_ok:
                st.error("Please tick the overwrite confirmation to proceed.")
            else:
                try:
                    with get_session() as s:
                        s.query(Table11).delete()
                        s.bulk_save_objects([
                            Table11(api60=float(r["api60"]), lt_factor=float(r["lt_factor"]))
                            for _, r in df11_preview.iterrows()
                        ])
                        s.commit()
                        try:
                            SecurityManager.log_audit(None,(user or {}).get("username","system"),"IMPORT",
                                resource_type="ASTMTable11", resource_id="Table11",
                                details=f"Imported ASTM Table 11 with {len(df11_preview)} rows",
                                user_id=(user or {}).get("id"))
                        except Exception:
                            pass
                    st.success(f"ASTM Table 11 imported: {len(df11_preview)} rows."); st.rerun()
                except Exception as ex:
                    st.error(f"Failed to import ASTM Table 11: {ex}")


# ====================== Page entry ======================

def render_asset_management_page(active_location_id, user):
    st.markdown("### 🧰 Asset Management")
    if not _require_admin(user): return
    st.markdown(
        """
        <style>
        .stButton>button { padding: 4px 8px; height: 28px; }
        div[data-testid=\"stHorizontalBlock\"] { gap: 0.25rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    tabs = st.tabs([
        "🛢️ Tanks",
        "⛴️ Vessels & ⚓ Assign",
        "⚓ FSO",
        "🚚 Tankers",
        "🛶 YADE Barges",
        "📚 ASTM Table 11",
    ])

    with tabs[0]: _tab_tanks(active_location_id, user)
    with tabs[1]: _tab_vessels_assign(active_location_id, user)
    with tabs[2]: _tab_fso_assign(active_location_id, user)
    with tabs[3]: _tab_tankers(user)
    with tabs[4]: _tab_yade_barges(user)
    with tabs[5]: _tab_astm_table11(user)
