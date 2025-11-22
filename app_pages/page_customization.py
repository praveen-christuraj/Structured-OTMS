# app_pages/page_customization.py
import streamlit as st
from typing import Dict, Any, List
from db import get_session
from models import Location
from permission_manager import PermissionManager

from location_config import (
    get_page_section_config,
    set_page_section_config,
)
from location_config import (
    get_dynamic_table_def, set_dynamic_table_def,
)
def _guard_admin(user) -> bool:
    if not user or not PermissionManager.can_access_management_pages(user):
        st.error("You do not have permission to access Page Customization.")
        return False
    return True

def _pick_location(active_location_id: int):
    if not active_location_id:
        st.warning("No active location selected on Home. Pick a location here for customization.")
        with get_session() as s:
            locs = s.query(Location).order_by(Location.name.asc()).all()
        if not locs:
            st.error("No locations found. Create one in Manage Locations.")
            return None, None

        labels = [f"{l.name} ({l.code})" for l in locs]
        lab2id = {labels[i]: locs[i].id for i in range(len(locs))}
        sel = st.selectbox("Select location", labels, key="pc_loc_pick")
        lid = lab2id.get(sel)
        if not lid:
            return None, None
        with get_session() as s:
            loc = s.query(Location).get(lid)
        return loc, f"{loc.name} ({loc.code})"

    with get_session() as s:
        loc = s.query(Location).get(active_location_id)
    if not loc:
        st.error("Active location not found. Re-select on Home.")
        return None, None
    return loc, f"{loc.name} ({loc.code})"

def _ensure_len(labels, n, filler_prefix):
    labels = list(labels or [])
    if len(labels) < n:
        labels += [f"{filler_prefix} {i+1}" for i in range(len(labels), n)]
    elif len(labels) > n:
        labels = labels[:n]
    return labels

def render_page_customization(user: Dict[str, Any]):
    st.markdown("### ⚙️ Page Customization")

    if not _guard_admin(user):
        return

    active_location_id = st.session_state.get("active_location_id")
    loc, loc_label = _pick_location(active_location_id)
    if not loc:
        return

    st.caption(f"Configuring for **{loc_label}**")
    st.markdown("---")

    loc_key = f"{loc.id}"

    # ==============================
    # 🧪 Condensate — Flow Meters (per location)
    # ==============================
    with st.expander("🧪 Condensate — Flow Meters (per location)", expanded=False):
        # load existing
        with get_session() as s:
            cfg = get_page_section_config(s, loc.id, page="tank_transactions", section="condensate_meters") or {}
        c_meters = list(cfg.get("meters") or [])

        st.caption(
            "Configure flow meters used in **Condensate Records**. "
            "Each meter has a Label, Meter Factor, and Unit (bbls or m³). "
            "If the unit is m³, net quantity will be converted to bbls with 6.289811."
        )

        # row builder
        def _row(m=None):
            m = m or {"label": "", "factor": 1.0, "unit": "bbls", "active": True}
            return {
                "label": str(m.get("label") or "").strip(),
                "factor": float(m.get("factor") or 1.0),
                "unit": (m.get("unit") or "bbls").lower(),  # "bbls" | "m3"
                "active": bool(m.get("active", True)),
            }

        # editable list
        st.markdown("#### Add / Edit Meters")
        add_cols = st.columns([0.40, 0.22, 0.20, 0.18])
        with add_cols[0]:
            new_label = st.text_input("Meter Label", key=f"pc_cond_label_{loc_key}")
        with add_cols[1]:
            new_factor = st.number_input("Meter Factor", min_value=0.0001, max_value=999999.0, step=0.0001, format="%.4f", key=f"pc_cond_factor_{loc_key}")
        with add_cols[2]:
            new_unit = st.selectbox("Unit", ["bbls", "m3"], index=0, key=f"pc_cond_unit_{loc_key}")
        with add_cols[3]:
            add_btn = st.button("➕ Add", key=f"pc_cond_add_{loc_key}", use_container_width=True)

        if add_btn:
            if not new_label.strip():
                st.error("Please enter a Meter Label.")
            else:
                c_meters.append(_row({"label": new_label, "factor": new_factor, "unit": new_unit, "active": True}))
                try:
                    with get_session() as s:
                        set_page_section_config(s, loc.id, "tank_transactions", "condensate_meters", {"meters": c_meters})
                        # audit
                        try:
                            SecurityManager.log_audit(
                                s, (user or {}).get("username", "system"), "CREATE",
                                resource_type="PageCustomization:CondensateMeter",
                                resource_id=str(loc.id),
                                details=f"Added condensate meter: {new_label} (factor={new_factor}, unit={new_unit})",
                                user_id=(user or {}).get("id"),
                                location_id=loc.id,
                                ip_address=st.session_state.get("client_ip"),
                                success=True,
                            )
                        except Exception:
                            pass
                    st.success("Meter added.")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Save failed: {ex}")

        st.markdown("#### Saved Meters")
        if not c_meters:
            st.info("No condensate meters configured yet.")
        else:
            for idx, m in enumerate(c_meters):
                row_key = f"pc_cond_row_{loc_key}_{idx}"
                st.write(f"**{idx+1}.** {m.get('label','')}  —  factor: {m.get('factor',1.0)}  —  unit: {m.get('unit','bbls')}  —  {'active' if m.get('active',True) else 'inactive'}")
                ecols = st.columns([0.22, 0.22, 0.22, 0.18, 0.16])
                with ecols[0]:
                    new_label_i = st.text_input("Label", value=m.get("label",""), key=f"{row_key}_lbl")
                with ecols[1]:
                    new_factor_i = st.number_input("Factor", value=float(m.get("factor",1.0)), step=0.0001, format="%.4f", key=f"{row_key}_fac")
                with ecols[2]:
                    new_unit_i = st.selectbox("Unit", ["bbls","m3"], index=(0 if (m.get("unit","bbls")=="bbls") else 1), key=f"{row_key}_unit")
                with ecols[3]:
                    new_active_i = st.checkbox("Active", value=bool(m.get("active",True)), key=f"{row_key}_act")
                with ecols[4]:
                    save_i = st.button("💾 Save", key=f"{row_key}_save", use_container_width=True)

                if save_i:
                    c_meters[idx] = _row({"label": new_label_i, "factor": new_factor_i, "unit": new_unit_i, "active": new_active_i})
                    try:
                        with get_session() as s:
                            set_page_section_config(s, loc.id, "tank_transactions", "condensate_meters", {"meters": c_meters})
                            # audit
                            try:
                                SecurityManager.log_audit(
                                    s, (user or {}).get("username","system"), "UPDATE",
                                    resource_type="PageCustomization:CondensateMeter",
                                    resource_id=f"{loc.id}:{idx}",
                                    details=f"Edited condensate meter idx={idx}: {c_meters[idx]}",
                                    user_id=(user or {}).get("id"),
                                    location_id=loc.id,
                                    ip_address=st.session_state.get("client_ip"),
                                    success=True,
                                )
                            except Exception:
                                pass
                        st.success("Updated.")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"Save failed: {ex}")

                # delete with confirm
                del_flag_key = f"{row_key}_delflag"
                if del_flag_key not in st.session_state:
                    st.session_state[del_flag_key] = False

                dcols = st.columns([0.84, 0.16])
                with dcols[1]:
                    if not st.session_state[del_flag_key]:
                        if st.button("🗑️ Delete", key=f"{row_key}_del", use_container_width=True):
                            st.session_state[del_flag_key] = True
                    else:
                        st.warning("Confirm delete?")
                        c1, c2 = st.columns(2)
                        if c1.button("✅ Yes", key=f"{row_key}_del_yes", use_container_width=True):
                            try:
                                new_list = [x for j, x in enumerate(c_meters) if j != idx]
                                with get_session() as s:
                                    set_page_section_config(s, loc.id, "tank_transactions", "condensate_meters", {"meters": new_list})
                                    # audit
                                    try:
                                        SecurityManager.log_audit(
                                            s, (user or {}).get("username","system"), "DELETE",
                                            resource_type="PageCustomization:CondensateMeter",
                                            resource_id=f"{loc.id}:{idx}",
                                            details=f"Deleted condensate meter idx={idx} ({m.get('label','')})",
                                            user_id=(user or {}).get("id"),
                                            location_id=loc.id,
                                            ip_address=st.session_state.get("client_ip"),
                                            success=True,
                                        )
                                    except Exception:
                                        pass
                                st.success("Deleted.")
                                st.session_state[del_flag_key] = False
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Delete failed: {ex}")
                        if c2.button("❌ No", key=f"{row_key}_del_no", use_container_width=True):
                            st.session_state[del_flag_key] = False

    # ============================
    # 💧 Produced Water — Table Builder (soft-coded)
    # ==============================
    with st.expander("💧 Produced Water — Table Definition (per location)", expanded=False):
        with get_session() as s:
            pw_def = get_dynamic_table_def(s, loc.id, page="tank_transactions", section="produced_water")
        pw_columns = list(pw_def.get("columns") or [])

        st.caption("Define the columns used in Produced Water data entry. Exactly one column can be 'date' (enforced as date picker). Others can be 'number' or 'text'.")
        n_cols = st.number_input("Number of columns", min_value=1, max_value=20, step=1, value=max(1, len(pw_columns) or 3), key=f"pc_pw_count_{loc_key}")

        # normalize length
        def _def_col(i):
            return {"name": f"col_{i+1}", "label": f"Column {i+1}", "type": "text", "required": False}
        if len(pw_columns) < n_cols:
            for i in range(len(pw_columns), n_cols):
                pw_columns.append(_def_col(i))
        elif len(pw_columns) > n_cols:
            pw_columns = pw_columns[:n_cols]

        date_seen = any(c.get("type") == "date" for c in pw_columns)
        for i in range(n_cols):
            c1, c2, c3, c4 = st.columns([0.28, 0.28, 0.24, 0.20])
            with c1:
                pw_columns[i]["name"] = st.text_input("Field name (no spaces)", value=pw_columns[i]["name"], key=f"pc_pw_name_{loc_key}_{i}")
            with c2:
                pw_columns[i]["label"] = st.text_input("Label", value=pw_columns[i]["label"], key=f"pc_pw_label_{loc_key}_{i}")
            with c3:
                current_type = pw_columns[i].get("type", "text")
                type_choice = st.selectbox("Type", ["text", "number", "date"], index=["text","number","date"].index(current_type), key=f"pc_pw_type_{loc_key}_{i}")
                # enforce single date column
                if type_choice == "date":
                    if not date_seen or current_type == "date":
                        pw_columns[i]["type"] = "date"
                        date_seen = True
                    else:
                        st.warning("Only one 'date' column allowed. Switching to 'text'.")
                        pw_columns[i]["type"] = "text"
                else:
                    pw_columns[i]["type"] = type_choice
            with c4:
                pw_columns[i]["required"] = st.checkbox("Required", value=bool(pw_columns[i].get("required", False)), key=f"pc_pw_req_{loc_key}_{i}")

        if st.button("💾 Save Produced Water Table", type="primary", key=f"pc_pw_save_{loc_key}"):
            try:
                with get_session() as s:
                    set_dynamic_table_def(s, loc.id, "tank_transactions", "produced_water", {"columns": pw_columns})
                    # audit
                    try:
                        SecurityManager.log_audit(
                            s, (user or {}).get("username","system"), "UPDATE",
                            resource_type="PageCustomization:PWDef", resource_id=str(loc.id),
                            details=f"Produced Water columns saved: {pw_columns}",
                            user_id=(user or {}).get("id"), location_id=loc.id, success=True,
                            ip_address=st.session_state.get("client_ip")
                        )
                    except Exception:
                        pass
                st.success("Produced Water definition saved.")
                st.rerun()
            except Exception as ex:
                st.error(f"Save failed: {ex}")

        st.markdown("##### Saved definition")
        if not pw_columns:
            st.info("No columns defined yet.")
        else:
            for j, c in enumerate(pw_columns, start=1):
                st.write(f"**{j}.** `{c['name']}` — {c['label']} — *{c['type']}* — {'required' if c.get('required') else 'optional'}")


    # ==============================
    # 🏭 Production — Table Builder (soft-coded)
    # ==============================
    with st.expander("🏭 Production — Table Definition (per location)", expanded=False):
        with get_session() as s:
            prod_def = get_dynamic_table_def(s, loc.id, page="tank_transactions", section="production")
        prod_columns = list(prod_def.get("columns") or [])

        st.caption("Define the columns used in Production data entry. Exactly one 'date' column. Others can be 'number' or 'text'.")
        n_cols = st.number_input("Number of columns", min_value=1, max_value=30, step=1, value=max(1, len(prod_columns) or 4), key=f"pc_prod_count_{loc_key}")

        def _def_col2(i):
            return {"name": f"col_{i+1}", "label": f"Column {i+1}", "type": "number", "required": False}
        if len(prod_columns) < n_cols:
            for i in range(len(prod_columns), n_cols):
                prod_columns.append(_def_col2(i))
        elif len(prod_columns) > n_cols:
            prod_columns = prod_columns[:n_cols]

        date_seen = any(c.get("type") == "date" for c in prod_columns)
        for i in range(n_cols):
            c1, c2, c3, c4 = st.columns([0.28, 0.28, 0.24, 0.20])
            with c1:
                prod_columns[i]["name"] = st.text_input("Field name (no spaces)", value=prod_columns[i]["name"], key=f"pc_prod_name_{loc_key}_{i}")
            with c2:
                prod_columns[i]["label"] = st.text_input("Label", value=prod_columns[i]["label"], key=f"pc_prod_label_{loc_key}_{i}")
            with c3:
                current_type = prod_columns[i].get("type", "number")
                type_choice = st.selectbox("Type", ["text", "number", "date"], index=["text","number","date"].index(current_type), key=f"pc_prod_type_{loc_key}_{i}")
                if type_choice == "date":
                    if not date_seen or current_type == "date":
                        prod_columns[i]["type"] = "date"
                        date_seen = True
                    else:
                        st.warning("Only one 'date' column allowed. Switching to 'number'.")
                        prod_columns[i]["type"] = "number"
                else:
                    prod_columns[i]["type"] = type_choice
            with c4:
                prod_columns[i]["required"] = st.checkbox("Required", value=bool(prod_columns[i].get("required", False)), key=f"pc_prod_req_{loc_key}_{i}")

        if st.button("💾 Save Production Table", type="primary", key=f"pc_prod_save_{loc_key}"):
            try:
                with get_session() as s:
                    set_dynamic_table_def(s, loc.id, "tank_transactions", "production", {"columns": prod_columns})
                    try:
                        SecurityManager.log_audit(
                            s, (user or {}).get("username","system"), "UPDATE",
                            resource_type="PageCustomization:ProductionDef", resource_id=str(loc.id),
                            details=f"Production columns saved: {prod_columns}",
                            user_id=(user or {}).get("id"), location_id=loc.id, success=True,
                            ip_address=st.session_state.get("client_ip")
                        )
                    except Exception:
                        pass
                st.success("Production definition saved.")
                st.rerun()
            except Exception as ex:
                st.error(f"Save failed: {ex}")

        st.markdown("##### Saved definition")
        if not prod_columns:
            st.info("No columns defined yet.")
        else:
            for j, c in enumerate(prod_columns, start=1):
                st.write(f"**{j}.** `{c['name']}` — {c['label']} — *{c['type']}* — {'required' if c.get('required') else 'optional'}")

    # ==============================================
    # 🧮 Meter Records (Meters & Factors)  <-- FULL CRUD + AUDIT
    # ==============================================
    with st.expander("🧮 Meter Records (Meters & Factors)", expanded=True):
        with get_session() as s:
            meters_cfg = get_page_section_config(s, loc.id, page="tank_transactions", section="meters")

        # structure: {"meters": [{"label": "...", "factor": 1.0000, "unit": "bbls"|"m3"}, ...]}
        meters = list(meters_cfg.get("meters") or [])
        count_default = len(meters) if len(meters) > 0 else 1

        nm = st.number_input(
            "Number of meters",
            min_value=1, max_value=24, value=count_default, step=1,
            key=f"pc_meters_count_{loc_key}"
        )

        # normalize list to size nm
        def _default_meter(i):
            return {"label": f"Meter {i+1}", "factor": 1.0000, "unit": "bbls"}

        if len(meters) < int(nm):
            for i in range(len(meters), int(nm)):
                meters.append(_default_meter(i))
        elif len(meters) > int(nm):
            meters = meters[: int(nm)]

        # --- Create/Update block (top) ---
        for i in range(int(nm)):
            st.markdown(f"**New/Update Slot {i+1}**")
            c1, c2, c3 = st.columns([0.45, 0.30, 0.25])

            with c1:
                meters[i]["label"] = st.text_input(
                    "Label",
                    value=str(meters[i].get("label", f"Meter {i+1}")),
                    key=f"pc_meter_label_{loc_key}_{i}"
                )
            with c2:
                meters[i]["factor"] = st.number_input(
                    "Meter factor",
                    min_value=0.0001, max_value=10.0,
                    step=0.0001, format="%.4f",
                    value=float(meters[i].get("factor", 1.0)),
                    key=f"pc_meter_factor_{loc_key}_{i}"
                )
            with c3:
                current_unit = (meters[i].get("unit") or "bbls").lower()
                meters[i]["unit"] = st.selectbox(
                    "Unit",
                    ["bbls", "m3"],
                    index=(0 if current_unit == "bbls" else 1),
                    key=f"pc_meter_unit_{loc_key}_{i}"
                )

            st.caption("Update factor here after each Meter Proving. Unit defines how readings are interpreted in Meter Records.")
            st.markdown("---")

        if st.button("💾 Save Meters & Factors", type="primary", key=f"pc_meters_save_{loc_key}"):
            try:
                payload = {"meters": meters}
                with get_session() as s:
                    set_page_section_config(s, loc.id, "tank_transactions", "meters", payload)
                    # ---- AUDIT (pass real session) ----
                    try:
                        ip = st.session_state.get("client_ip")  # set this elsewhere if you capture it
                        SecurityManager.log_audit(
                            s,
                            (user or {}).get("username", "system"),
                            "UPDATE",
                            resource_type="PageCustomization:MeterConfig",
                            resource_id=str(loc.id),
                            details=f"Saved {len(meters)} meter(s): {payload}",
                            user_id=(user or {}).get("id"),
                            location_id=loc.id,
                            ip_address=ip,
                            success=True,
                        )
                    except Exception:
                        pass
                st.success("Meter configuration saved.")
                st.rerun()
            except Exception as ex:
                st.error(f"Save failed: {ex}")


        # --- Saved meters table with Edit/Delete ---
        st.markdown("##### Saved meters")
        with get_session() as s:
            meters_cfg_live = get_page_section_config(s, loc.id, page="tank_transactions", section="meters")
        meters_live = list(meters_cfg_live.get("meters") or [])

        if not meters_live:
            st.info("No meters configured yet.")
        else:
            for idx, m in enumerate(meters_live):
                row_key = f"{loc_key}_{idx}"
                label = m.get("label") or f"Meter {idx+1}"
                factor = float(m.get("factor") or 1.0)
                unit = (m.get("unit") or "bbls").lower()

                st.write(
                    f"**{idx+1}. {label}** — Factor: `{factor:.4f}` — Unit: `{unit}`"
                )
                c1, c2, c3, c4, c5 = st.columns([0.36, 0.18, 0.16, 0.15, 0.15])

                # Edit mode toggle in session
                edit_flag_key = f"pc_meter_edit_flag_{row_key}"
                del_flag_key = f"pc_meter_del_flag_{row_key}"
                st.session_state.setdefault(edit_flag_key, False)
                st.session_state.setdefault(del_flag_key, False)

                if not st.session_state[edit_flag_key]:
                    # View row
                    with c4:
                        if st.button("✏️ Edit", key=f"pc_meter_edit_btn_{row_key}"):
                            st.session_state[edit_flag_key] = True
                            st.session_state[f"pc_edit_label_{row_key}"] = label
                            st.session_state[f"pc_edit_factor_{row_key}"] = factor
                            st.session_state[f"pc_edit_unit_{row_key}"] = unit
                    with c5:
                        if not st.session_state[del_flag_key]:
                            if st.button("🗑️ Delete", key=f"pc_meter_del_btn_{row_key}"):
                                st.session_state[del_flag_key] = True
                        else:
                            st.warning("Confirm delete?")
                            d1, d2 = st.columns(2)
                            with d1:
                                if st.button("✅ Yes", key=f"pc_meter_del_yes_{row_key}"):
                                    try:
                                        new_list = [x for j, x in enumerate(meters_live) if j != idx]
                                        payload = {"meters": new_list}
                                        with get_session() as s:
                                            set_page_section_config(s, loc.id, "tank_transactions", "meters", payload)
                                            # ---- AUDIT (pass real session) ----
                                            try:
                                                ip = st.session_state.get("client_ip")
                                                SecurityManager.log_audit(
                                                    s,
                                                    (user or {}).get("username", "system"),
                                                    "DELETE",
                                                    resource_type="PageCustomization:Meter",
                                                    resource_id=f"{loc.id}:{idx}",
                                                    details=f"Deleted meter #{idx+1} ({label})",
                                                    user_id=(user or {}).get("id"),
                                                    location_id=loc.id,
                                                    ip_address=ip,
                                                    success=True,
                                                )
                                            except Exception:
                                                pass
                                        st.success(f"Deleted meter: {label}")
                                        st.session_state[del_flag_key] = False
                                        st.rerun()
                                    except Exception as ex:
                                        st.error(f"Delete failed: {ex}")

                            with d2:
                                if st.button("❌ No", key=f"pc_meter_del_no_{row_key}"):
                                    st.session_state[del_flag_key] = False
                else:
                    # Edit row UI
                    with c1:
                        new_label = st.text_input(
                            "Label",
                            value=st.session_state.get(f"pc_edit_label_{row_key}", label),
                            key=f"pc_meter_edit_label_{row_key}"
                        )
                    with c2:
                        new_factor = st.number_input(
                            "Factor",
                            min_value=0.0001, max_value=10.0, step=0.0001, format="%.4f",
                            value=float(st.session_state.get(f"pc_edit_factor_{row_key}", factor)),
                            key=f"pc_meter_edit_factor_{row_key}"
                        )
                    with c3:
                        new_unit = st.selectbox(
                            "Unit",
                            ["bbls", "m3"],
                            index=(0 if (st.session_state.get(f"pc_edit_unit_{row_key}", unit) == "bbls") else 1),
                            key=f"pc_meter_edit_unit_{row_key}"
                        )
                    with c4:
                        if st.button("💾 Save", key=f"pc_meter_edit_save_{row_key}"):
                            try:
                                meters_live[idx] = {
                                    "label": (new_label or f"Meter {idx+1}").strip(),
                                    "factor": float(new_factor),
                                    "unit": new_unit.lower(),
                                }
                                payload = {"meters": meters_live}
                                with get_session() as s:
                                    set_page_section_config(s, loc.id, "tank_transactions", "meters", payload)
                                    # ---- AUDIT (pass real session) ----
                                    try:
                                        ip = st.session_state.get("client_ip")
                                        SecurityManager.log_audit(
                                            s,
                                            (user or {}).get("username", "system"),
                                            "UPDATE",
                                            resource_type="PageCustomization:Meter",
                                            resource_id=f"{loc.id}:{idx}",
                                            details=f"Edited meter #{idx+1} → {meters_live[idx]}",
                                            user_id=(user or {}).get("id"),
                                            location_id=loc.id,
                                            ip_address=ip,
                                            success=True,
                                        )
                                    except Exception:
                                        pass
                                st.success("Meter updated.")
                                st.session_state[edit_flag_key] = False
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Update failed: {ex}")

                    with c5:
                        if st.button("↩️ Cancel", key=f"pc_meter_edit_cancel_{row_key}"):
                            st.session_state[edit_flag_key] = False

                st.markdown("---")

    st.info("All changes take effect immediately on the corresponding pages.")
